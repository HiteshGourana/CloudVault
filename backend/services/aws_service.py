"""
backend/services/aws_service.py
─────────────────────────────────
AWS credential verification and account management business logic.

Two classes with distinct responsibilities:

  AWSCredentialVerifier (stateless — no DB, no HTTP state):
    - Creates a boto3 session from raw credentials.
    - Calls STS GetCallerIdentity to verify credentials.
    - Returns an AWSIdentity dataclass on success.
    - Raises HTTPException on all AWS-level failures.
    - NEVER logs credentials.

  AWSAccountService (stateful — uses DB + verifier):
    - Orchestrates connect / status / disconnect flows.
    - Calls AWSCredentialVerifier to verify, then AWSAccountRepository to persist.
    - Encrypts the secret key before any DB write via CredentialManager.
    - Owns all HTTPExceptions for business-rule violations.

Why STS GetCallerIdentity?
  - Requires ZERO IAM permissions — any valid credential can call it.
  - Returns: Account (12-digit ID), Arn (full IAM ARN), UserId.
  - Lightweight, fast, and free.
  - Industry-standard method for "prove you own these credentials".
  - Works for IAM users, IAM roles, and federated identities.

boto3 error codes handled:
  Code                   | Meaning
  ─────────────────────────────────────────────────────────
  InvalidClientTokenId   | Wrong access key ID
  SignatureDoesNotMatch  | Wrong secret access key
  AccessDenied           | Credentials valid but STS blocked (rare)
  ExpiredTokenException  | Temporary credentials expired
  AuthFailure            | General auth failure
  RequestExpired         | System clock skew > 15 minutes
  EndpointConnectionError| Network issue / invalid region
  NoCredentialsError     | Credentials not provided (should not reach here)

CREDENTIAL SECURITY:
  Credentials are NEVER logged — even at DEBUG level.
  The boto3 session object is created but never persisted.
  Only the encrypted form of secret_access_key touches the database.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3
import botocore.exceptions
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.aws_account import AWSAccount
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.schemas.aws_account import AWSConnectRequest
from backend.utils.encryption import CredentialManager


# ─────────────────────────────────────────────────────────────────────────────
# Value Object — AWS Identity
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AWSIdentity:
    """
    Immutable result from STS GetCallerIdentity.

    Frozen dataclass — no accidental mutation after creation.
    Not a Pydantic model — keeps AWS logic completely independent of HTTP concerns.
    """

    aws_account_id: str     # 12-digit AWS account number
    iam_arn: str            # Full ARN: arn:aws:iam::123456789012:user/alice
    iam_user_name: str | None  # "alice" for IAM users, None for root/roles


# ─────────────────────────────────────────────────────────────────────────────
# boto3 Error → HTTP Exception Mapping
# ─────────────────────────────────────────────────────────────────────────────

# Maps AWS error codes to user-facing messages and HTTP status codes.
# Keys must match botocore's Error.Code values exactly.
_AWS_CLIENT_ERRORS: dict[str, tuple[int, str]] = {
    "InvalidClientTokenId": (
        status.HTTP_401_UNAUTHORIZED,
        "Invalid AWS Access Key ID. Verify the key in your IAM console.",
    ),
    "SignatureDoesNotMatch": (
        status.HTTP_401_UNAUTHORIZED,
        "Invalid AWS Secret Access Key. The signature verification failed.",
    ),
    "AccessDenied": (
        status.HTTP_403_FORBIDDEN,
        "Access denied. Your credentials are valid but lack STS GetCallerIdentity permission (very rare).",
    ),
    "ExpiredTokenException": (
        status.HTTP_401_UNAUTHORIZED,
        "AWS credentials have expired. Please generate new long-lived credentials.",
    ),
    "AuthFailure": (
        status.HTTP_401_UNAUTHORIZED,
        "AWS authentication failed. Check your credentials and try again.",
    ),
    "RequestExpired": (
        status.HTTP_400_BAD_REQUEST,
        "AWS request expired. Your system clock may be out of sync (must be within 15 minutes of AWS time).",
    ),
    "InvalidAction": (
        status.HTTP_400_BAD_REQUEST,
        "Invalid AWS action. The configured region may not support STS.",
    ),
}


def _raise_for_client_error(exc: botocore.exceptions.ClientError) -> None:
    """
    Convert a botocore ClientError into a FastAPI HTTPException.

    Extracts the AWS error code and maps it to a human-friendly message.
    Falls back to a generic message for unmapped error codes.

    IMPORTANT: The original exception details (including any credentials
    that might appear in error messages) are NOT forwarded to the client.
    """
    error_code: str = exc.response.get("Error", {}).get("Code", "Unknown")

    if error_code in _AWS_CLIENT_ERRORS:
        http_status, message = _AWS_CLIENT_ERRORS[error_code]
    else:
        # Unmapped error — log the code for debugging, return generic message
        logger.warning("Unmapped AWS error code: {}", error_code)
        http_status = status.HTTP_400_BAD_REQUEST
        message = f"AWS returned an error ({error_code}). Check your credentials and region."

    raise HTTPException(status_code=http_status, detail=message)


# ─────────────────────────────────────────────────────────────────────────────
# AWSCredentialVerifier — Pure AWS API Calls (No DB, No HTTP State)
# ─────────────────────────────────────────────────────────────────────────────


class AWSCredentialVerifier:
    """
    Verifies AWS credentials by calling STS GetCallerIdentity.

    Stateless — no database, no request state, no side effects.
    Can be tested independently by mocking boto3.

    How GetCallerIdentity works:
      1. A boto3 STS client is created using the provided credentials.
      2. The call is signed with HMAC-SHA256 using the secret key.
      3. AWS validates the signature against the stored key for that access key ID.
      4. On success, AWS returns: Account, Arn, UserId.
      5. No IAM permissions are required — available to any valid identity.
    """

    @staticmethod
    def verify(
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> AWSIdentity:
        """
        Call STS GetCallerIdentity and return the verified identity.

        Args:
            access_key_id:     AWS access key ID.
            secret_access_key: AWS secret access key (plain text — used only here, never stored).
            region:            AWS region slug for the STS endpoint.

        Returns:
            AWSIdentity with account_id, arn, and username.

        Raises:
            HTTPException 401: Invalid credentials.
            HTTPException 403: Access denied.
            HTTPException 400: Bad request or region error.
            HTTPException 503: Network/endpoint issue.

        SECURITY: Credentials are used to create the boto3 session object only.
                  They are never logged, never returned, never persisted here.
        """
        try:
            session = boto3.Session(
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
            )
            sts = session.client("sts")
            response = sts.get_caller_identity()

        except botocore.exceptions.ClientError as exc:
            _raise_for_client_error(exc)
            raise  # unreachable — for type checker

        except botocore.exceptions.EndpointConnectionError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Could not connect to the AWS STS endpoint. "
                    "Verify the region name and your network connectivity."
                ),
            )

        except botocore.exceptions.NoCredentialsError:
            # Should not reach here since we always pass credentials explicitly.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS credentials were not provided.",
            )

        except botocore.exceptions.PartialCredentialsError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incomplete AWS credentials. Both access_key_id and secret_access_key are required.",
            )

        except Exception as exc:
            # Catch-all for unexpected boto3 errors — log without credential details.
            logger.error("Unexpected AWS error during credential verification: {}", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while verifying AWS credentials.",
            ) from exc

        # ── Parse STS response ────────────────────────────────────────────────
        aws_account_id: str = response["Account"]
        iam_arn: str = response["Arn"]
        iam_user_name: str | None = AWSCredentialVerifier._extract_iam_username(iam_arn)

        return AWSIdentity(
            aws_account_id=aws_account_id,
            iam_arn=iam_arn,
            iam_user_name=iam_user_name,
        )

    @staticmethod
    def _extract_iam_username(arn: str) -> str | None:
        """
        Extract the IAM username from a full ARN string.

        ARN formats handled:
          arn:aws:iam::123456789012:user/alice        → "alice"
          arn:aws:iam::123456789012:user/team/alice   → "alice" (last segment)
          arn:aws:iam::123456789012:root              → None
          arn:aws:sts::123456789012:assumed-role/...  → None

        Args:
            arn: Full IAM ARN string from STS.

        Returns:
            IAM username string or None for non-user identities.
        """
        try:
            # ARN parts: arn:partition:service:region:account:resource
            resource = arn.split(":", maxsplit=5)[-1]  # e.g., "user/alice" or "root"

            if resource.startswith("user/"):
                # Take the last path segment for paths like "user/team/alice"
                return resource.split("/")[-1]

            return None  # Root, role, federated, etc.

        except (IndexError, AttributeError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# AWSAccountService — Business Logic + DB Orchestration
# ─────────────────────────────────────────────────────────────────────────────


class AWSAccountService:
    """
    Orchestrates AWS account connection, status retrieval, and disconnection.

    Instantiated once per request with a DB session and the current user.
    """

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._repo = AWSAccountRepository(db)

    # ── Connect ───────────────────────────────────────────────────────────────

    def connect(self, data: AWSConnectRequest) -> tuple[AWSAccount, bool]:
        """
        Verify AWS credentials and store the account connection.

        Steps:
          1. Call STS GetCallerIdentity to verify credentials and get account info.
          2. Encrypt the secret access key with Fernet.
          3. Upsert the record (create if first time, update if reconnecting).

        Args:
            data: Validated AWSConnectRequest with credentials and region.

        Returns:
            (account, created) where created=True for first-time connections.

        Raises:
            HTTPException 401/403/400/503: Various AWS credential errors.
        """
        # Step 1: Verify with AWS STS — raises HTTPException on failure
        identity = AWSCredentialVerifier.verify(
            access_key_id=data.access_key_id,
            secret_access_key=data.secret_access_key,
            region=data.region,
        )

        # Step 2: Encrypt the secret key before touching the DB
        encrypted_secret = CredentialManager.encrypt(data.secret_access_key)

        # Step 3: Upsert the record
        account, created = self._repo.create_or_update(
            user_id=self._user.id,
            aws_account_id=identity.aws_account_id,
            iam_arn=identity.iam_arn,
            iam_user_name=identity.iam_user_name,
            region=data.region,
            access_key_id=data.access_key_id,
            secret_access_key_encrypted=encrypted_secret,
        )

        action = "connected" if created else "reconnected"
        logger.success(
            "AWS account {} | user_id={} aws_account_id={} region={}",
            action,
            str(self._user.id),
            identity.aws_account_id,
            data.region,
        )

        return account, created

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> AWSAccount:
        """
        Return the current user's connected AWS account.
        Checks dynamically if the AWS connection is active/valid, with a 60-second cache.

        Raises:
            HTTPException 404: If no AWS account has been connected.
        """
        account = self._repo.get_by_user_id(self._user.id)

        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No AWS account connected. "
                    "Call POST /api/v1/aws/connect to link your AWS account."
                ),
            )

        # 60-second verification caching cool-down
        now = datetime.now(timezone.utc)
        connected_ts = account.connected_at
        if connected_ts.tzinfo is None:
            connected_ts = connected_ts.replace(tzinfo=timezone.utc)

        time_since_check = (now - connected_ts).total_seconds()
        if time_since_check < 60.0:
            logger.debug(
                "Returning cached AWS status for user_id={} | checked={:.1f}s ago",
                self._user.id,
                time_since_check,
            )
            return account

        try:
            secret_key = CredentialManager.decrypt(account.secret_access_key_encrypted)
            AWSCredentialVerifier.verify(
                access_key_id=account.access_key_id,
                secret_access_key=secret_key,
                region=account.region,
            )
            # Connection is active, update DB if it was false or update the check time
            account.is_connected = True
            account.connected_at = datetime.now(timezone.utc)
            self._db.commit()
            self._db.refresh(account)
        except Exception as exc:
            # Connection is inactive, update DB status and timestamp
            logger.warning(
                "AWS credential verification failed during status check for user_id={}: {}",
                self._user.id,
                str(exc)
            )
            account.is_connected = False
            account.connected_at = datetime.now(timezone.utc)
            self._db.commit()
            self._db.refresh(account)

        return account

    # ── Disconnect ────────────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """
        Permanently remove the user's AWS account connection.

        Deletes the row from aws_accounts. The user's CloudVault account
        remains active — only the AWS connection is removed.

        Raises:
            HTTPException 404: If no AWS account is connected.
        """
        account = self._repo.get_by_user_id(self._user.id)

        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AWS account connected. Nothing to disconnect.",
            )

        self._repo.delete(account)

        logger.info(
            "AWS account disconnected | user_id={} aws_account_id={}",
            str(self._user.id),
            account.aws_account_id,
        )
