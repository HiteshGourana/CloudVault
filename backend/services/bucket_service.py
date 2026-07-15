"""
backend/services/bucket_service.py
────────────────────────────────────
S3 bucket operations and business logic.

Two classes with distinct responsibilities:

  S3BucketOperator (stateless — no DB, no HTTP state):
    - Creates boto3 sessions from user credentials.
    - Executes all S3 API calls.
    - Returns Python dataclasses (not Pydantic models).
    - Raises HTTPException on all AWS-level failures.
    - NEVER logs credentials.

  BucketService (stateful — orchestrates operator + repository):
    - Verifies the user has a connected AWS account.
    - Delegates S3 operations to S3BucketOperator.
    - Persists/removes metadata in the local DB via BucketRepository.
    - Owns all business-rule HTTP exceptions (404, 409, etc.).

──────────────────────────────────────────────────────────────────────────────
S3 API calls used and why:

  list_buckets()
    Returns all buckets owned by the AWS account (name + creation date only).
    One API call. Region NOT included — fetched separately via get_bucket_location.

  create_bucket(Bucket, [CreateBucketConfiguration])
    Creates a new bucket. CRITICAL: for us-east-1, omit CreateBucketConfiguration
    entirely — passing LocationConstraint="us-east-1" raises IllegalLocationConstraintException.

  head_bucket(Bucket)
    Checks if a bucket exists and is accessible.
    Returns 200 → exists and accessible.
    Returns 403 → bucket exists globally but this account cannot access it.
    Returns 404 → bucket does not exist.

  delete_bucket(Bucket)
    Deletes a bucket. Must be empty. Raises BucketNotEmpty otherwise.
    CloudVault NEVER deletes bucket contents automatically.

  get_bucket_location(Bucket)
    Returns the bucket's region.
    us-east-1 returns None for LocationConstraint (legacy AWS behavior).

  get_bucket_versioning(Bucket)
    Returns versioning status: "Enabled", "Suspended", or {} (never configured).

  get_bucket_encryption(Bucket)
    Returns encryption config. Raises ServerSideEncryptionConfigurationNotFoundError
    if SSE is not configured (not an error — means unencrypted).

  get_public_access_block(Bucket)
    Returns the four public access block settings. Raises NoSuchPublicAccessBlockConfiguration
    if settings were never explicitly configured (means defaults apply).

──────────────────────────────────────────────────────────────────────────────
boto3 Error Codes handled:

  Credential errors:
    InvalidClientTokenId      → 401 (wrong access key ID)
    SignatureDoesNotMatch     → 401 (wrong secret key)
    ExpiredTokenException     → 401 (expired credentials)

  Bucket lifecycle errors:
    BucketAlreadyExists       → 409 (name taken globally)
    BucketAlreadyOwnedByYou   → 409 (you own it already)
    NoSuchBucket              → 404 (doesn't exist)
    BucketNotEmpty            → 409 (must empty before delete)

  Permission errors:
    AccessDenied              → 403 (missing IAM permissions)

  Format/config errors:
    InvalidBucketName         → 422 (AWS rejected the name)
    IllegalLocationConstraintException → 422 (region/constraint mismatch)

  Rate/limit errors:
    TooManyBuckets            → 429 (hit AWS 100-bucket limit)
    OperationAborted          → 409 (conflict, retry)

  Network errors:
    EndpointConnectionError   → 503 (network / invalid region)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
import botocore.exceptions
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.bucket import Bucket, BucketType
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.schemas.bucket import BucketCreate
from backend.services.activity_service import ActivityService
from backend.utils.encryption import CredentialManager
from backend.utils.validators import validate_aws_region, validate_bucket_name


# ─────────────────────────────────────────────────────────────────────────────
# Value Objects (dataclasses returned by S3BucketOperator)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class S3BucketSummary:
    """Basic info from list_buckets — one entry per bucket."""

    name: str
    creation_date: datetime | None


@dataclass
class S3BucketDetails:
    """
    Real-time bucket details collected from multiple S3 API calls.
    Used to populate BucketDetailsResponse.
    """

    name: str
    region: str
    creation_date: datetime | None
    versioning_status: str          # "Enabled" | "Suspended" | "Disabled"
    versioning_enabled: bool
    encryption_enabled: bool
    encryption_type: str | None     # "AES256" | "aws:kms" | None
    public_access_blocked: bool | None  # None if check was not permitted


# ─────────────────────────────────────────────────────────────────────────────
# boto3 Error → HTTPException Mapping
# ─────────────────────────────────────────────────────────────────────────────

_S3_CLIENT_ERRORS: dict[str, tuple[int, str]] = {
    # ── Credential errors ──────────────────────────────────────────────────
    "InvalidClientTokenId": (
        status.HTTP_401_UNAUTHORIZED,
        "Invalid AWS Access Key ID. Please reconnect your AWS account.",
    ),
    "SignatureDoesNotMatch": (
        status.HTTP_401_UNAUTHORIZED,
        "Invalid AWS Secret Access Key. Please reconnect your AWS account.",
    ),
    "ExpiredTokenException": (
        status.HTTP_401_UNAUTHORIZED,
        "AWS credentials have expired. Please reconnect your AWS account.",
    ),
    "AuthFailure": (
        status.HTTP_401_UNAUTHORIZED,
        "AWS authentication failed. Please check your credentials.",
    ),
    # ── Bucket lifecycle errors ────────────────────────────────────────────
    "BucketAlreadyExists": (
        status.HTTP_409_CONFLICT,
        (
            "Bucket name is already taken globally. "
            "S3 bucket names must be unique across all AWS accounts worldwide. "
            "Choose a different name."
        ),
    ),
    "BucketAlreadyOwnedByYou": (
        status.HTTP_409_CONFLICT,
        "You already own a bucket with this name in the same region.",
    ),
    "NoSuchBucket": (
        status.HTTP_404_NOT_FOUND,
        "The specified S3 bucket does not exist.",
    ),
    "BucketNotEmpty": (
        status.HTTP_409_CONFLICT,
        (
            "Cannot delete: the bucket is not empty. "
            "Delete all objects and versions inside the bucket first. "
            "CloudVault will never automatically delete your data."
        ),
    ),
    # ── Permission errors ──────────────────────────────────────────────────
    "AccessDenied": (
        status.HTTP_403_FORBIDDEN,
        (
            "Access denied. Your IAM user lacks the required S3 permission. "
            "Ensure your IAM policy includes the necessary s3:* actions."
        ),
    ),
    # ── Name/format errors ─────────────────────────────────────────────────
    "InvalidBucketName": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "AWS rejected the bucket name as invalid. Review bucket naming rules.",
    ),
    "IllegalLocationConstraintException": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        (
            "Region constraint error. "
            "This usually happens when creating a bucket in us-east-1 with an explicit LocationConstraint. "
            "Please try again."
        ),
    ),
    # ── Rate/limit errors ──────────────────────────────────────────────────
    "TooManyBuckets": (
        status.HTTP_429_TOO_MANY_REQUESTS,
        (
            "AWS account has reached the maximum number of buckets (100 by default). "
            "Delete unused buckets or request a limit increase in the AWS Service Quotas console."
        ),
    ),
    "OperationAborted": (
        status.HTTP_409_CONFLICT,
        "Operation aborted due to a conflicting concurrent request. Please retry.",
    ),
}


def _raise_for_s3_error(exc: botocore.exceptions.ClientError) -> None:
    """
    Convert a botocore ClientError into a FastAPI HTTPException.

    Maps AWS error codes to structured HTTP responses.
    Never forwards raw boto3 exception details to the client.
    """
    error_info = exc.response.get("Error", {})
    error_code: str = error_info.get("Code", "Unknown")

    if error_code in _S3_CLIENT_ERRORS:
        http_status, message = _S3_CLIENT_ERRORS[error_code]
    else:
        logger.warning("Unmapped S3 error code: {} | message: {}", error_code, error_info.get("Message", ""))
        http_status = status.HTTP_400_BAD_REQUEST
        message = f"AWS S3 returned error code '{error_code}'. Check your credentials and permissions."

    raise HTTPException(status_code=http_status, detail=message)


# ─────────────────────────────────────────────────────────────────────────────
# S3BucketOperator — Pure AWS API Calls (No DB, No HTTP State)
# ─────────────────────────────────────────────────────────────────────────────


class S3BucketOperator:
    """
    Stateless boto3 S3 wrapper.

    All methods make AWS API calls and return Python dataclasses.
    No database access. No business logic. No side effects.
    Testable by mocking boto3.Session.

    Instantiated per-request from the user's decrypted credentials.
    The session is created once per instance and reused for all operations.
    """

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> None:
        """
        Create a boto3 session with user-provided credentials.

        Args:
            access_key_id:     AWS access key ID (plain text).
            secret_access_key: AWS secret access key (plain text, decrypted at call site).
            region:            Default region for the boto3 session.

        SECURITY: Credentials are used here only to create the session.
                  They are never logged, stored, or returned.
        """
        self._session = boto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        self._default_region = region
        # S3 client — region matters for some operations but S3 is globally accessible
        self._s3 = self._session.client("s3", region_name=region)

    # ── Bucket Listing ────────────────────────────────────────────────────────

    def list_buckets(self) -> list[S3BucketSummary]:
        """
        Return basic info for all S3 buckets in the connected AWS account.

        How it works:
          - Calls S3 ListBuckets (1 API call).
          - Returns ALL buckets owned by the authenticated account — no pagination needed.
          - Only includes Name and CreationDate. Region NOT included (requires N extra calls).

        Returns:
            List of S3BucketSummary — empty list if account has no buckets.
        """
        try:
            response = self._s3.list_buckets()
            return [
                S3BucketSummary(
                    name=bucket["Name"],
                    creation_date=bucket.get("CreationDate"),
                )
                for bucket in response.get("Buckets", [])
            ]
        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_error(exc)
            raise  # unreachable — satisfies type checker

    # ── Bucket Creation ───────────────────────────────────────────────────────

    def create_bucket(self, name: str, region: str) -> S3BucketSummary:
        """
        Create an S3 bucket in the specified region.

        CRITICAL us-east-1 behaviour:
          When creating a bucket in us-east-1 (AWS's classic/default region),
          you MUST NOT pass CreateBucketConfiguration with LocationConstraint.
          Passing LocationConstraint="us-east-1" raises IllegalLocationConstraintException.
          All other regions require CreateBucketConfiguration.

        How it works:
          - Calls S3 CreateBucket.
          - For us-east-1: CreateBucket(Bucket=name)
          - For other regions: CreateBucket(Bucket=name,
              CreateBucketConfiguration={"LocationConstraint": region})
          - Returns immediately after creation (does not wait for bucket to be reachable).

        Args:
            name:   Validated bucket name.
            region: Target AWS region for the bucket.

        Returns:
            S3BucketSummary with name and approximate creation time.

        Raises:
            HTTPException 409: BucketAlreadyExists or BucketAlreadyOwnedByYou.
            HTTPException 422: Invalid bucket name or region constraint error.
            HTTPException 429: TooManyBuckets limit reached.
        """
        try:
            if region == "us-east-1":
                # us-east-1 special case — NO CreateBucketConfiguration
                self._s3.create_bucket(Bucket=name)
            else:
                self._s3.create_bucket(
                    Bucket=name,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )
            return S3BucketSummary(
                name=name,
                creation_date=datetime.now(timezone.utc),
            )
        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_error(exc)
            raise

    # ── Bucket Existence ──────────────────────────────────────────────────────

    def head_bucket(self, name: str) -> dict[str, bool]:
        """
        Check whether a bucket exists and is accessible.

        How it works:
          - Calls S3 HeadBucket — a lightweight metadata request (no content transferred).
          - HTTP 200 → bucket exists and credentials have access.
          - HTTP 403 → bucket exists globally but this account lacks s3:GetBucketAcl or similar.
          - HTTP 404 → bucket does not exist anywhere in AWS.
          - HTTP 301 → bucket exists but in a different region (PermanentRedirect).

        Returns:
            {"exists": bool, "accessible": bool}
            exists=True, accessible=True  → bucket found and accessible
            exists=True, accessible=False → bucket found but access denied (owned by another account)
            exists=False, accessible=False → bucket does not exist
        """
        try:
            self._s3.head_bucket(Bucket=name)
            return {"exists": True, "accessible": True}

        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            http_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)

            if error_code == "404" or http_code == 404:
                return {"exists": False, "accessible": False}

            if error_code == "403" or http_code == 403:
                # Bucket exists somewhere in AWS but this account cannot access it
                return {"exists": True, "accessible": False}

            if error_code == "PermanentRedirect" or http_code == 301:
                # Bucket exists in a different region
                return {"exists": True, "accessible": True}

            _raise_for_s3_error(exc)
            raise

        except botocore.exceptions.EndpointConnectionError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to AWS S3. Check your network and region.",
            )

    # ── Bucket Deletion ───────────────────────────────────────────────────────

    def delete_bucket(self, name: str) -> None:
        """
        Delete an empty S3 bucket.

        How it works:
          - Calls S3 DeleteBucket.
          - AWS rejects the request with BucketNotEmpty if the bucket contains
            any objects, delete markers, or non-current versions.
          - CloudVault NEVER automatically deletes bucket contents.
          - The actual S3 delete is permanent and cannot be undone.

        Raises:
            HTTPException 409: BucketNotEmpty — bucket has objects/versions.
            HTTPException 404: NoSuchBucket — bucket already deleted.
            HTTPException 403: AccessDenied — missing s3:DeleteBucket permission.
        """
        try:
            self._s3.delete_bucket(Bucket=name)
        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_error(exc)
            raise

    # ── Force Empty Bucket ──────────────────────────────────────────────────────────────

    def empty_bucket(self, name: str) -> tuple[int, int]:
        """
        Delete ALL objects and ALL versions/delete-markers from a bucket.

        Uses S3 delete_objects (batch up to 1000 keys per call) for maximum
        efficiency. Handles both non-versioned buckets (list_objects_v2) and
        versioned buckets (list_object_versions).

        Returns:
            (objects_deleted, versions_deleted) counts.

        Raises:
            HTTPException 403: AccessDenied — missing s3:DeleteObject permission.
            HTTPException 404: NoSuchBucket — bucket was removed concurrently.
        """
        objects_deleted = 0
        versions_deleted = 0

        try:
            # ── Step 1: Delete all current objects (non-versioned or current versions) ──
            obj_paginator = self._s3.get_paginator("list_objects_v2")
            for page in obj_paginator.paginate(Bucket=name):
                contents = page.get("Contents", [])
                if not contents:
                    continue
                delete_payload = [
                    {"Key": obj["Key"]} for obj in contents
                ]
                # Batch delete up to 1000 objects per API call
                for i in range(0, len(delete_payload), 1000):
                    chunk = delete_payload[i : i + 1000]
                    self._s3.delete_objects(
                        Bucket=name,
                        Delete={"Objects": chunk, "Quiet": True},
                    )
                    objects_deleted += len(chunk)

            # ── Step 2: Delete all versions and delete-markers (versioned buckets) ──
            ver_paginator = self._s3.get_paginator("list_object_versions")
            try:
                for page in ver_paginator.paginate(Bucket=name):
                    version_list: list[dict] = []
                    for v in page.get("Versions", []):
                        version_list.append({"Key": v["Key"], "VersionId": v["VersionId"]})
                    for dm in page.get("DeleteMarkers", []):
                        version_list.append({"Key": dm["Key"], "VersionId": dm["VersionId"]})

                    if not version_list:
                        continue

                    for i in range(0, len(version_list), 1000):
                        chunk = version_list[i : i + 1000]
                        self._s3.delete_objects(
                            Bucket=name,
                            Delete={"Objects": chunk, "Quiet": True},
                        )
                        versions_deleted += len(chunk)

            except botocore.exceptions.ClientError as exc:
                # If versioning was never configured, list_object_versions may
                # return an error on some older configurations — safe to ignore.
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in ("NoSuchBucket", "AccessDenied"):
                    logger.warning("list_object_versions skipped for '{}': {}", name, code)
                elif code == "AccessDenied":
                    _raise_for_s3_error(exc)

        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_error(exc)
            raise

        logger.info(
            "Bucket emptied | name={} objects_deleted={} versions_deleted={}",
            name, objects_deleted, versions_deleted,
        )
        return objects_deleted, versions_deleted

    # ── Bucket Location ───────────────────────────────────────────────────────

    def get_bucket_location(self, name: str) -> str:
        """
        Return the AWS region where the bucket resides.

        How it works:
          - Calls S3 GetBucketLocation.
          - Returns LocationConstraint from the response.
          - us-east-1 returns null/None for LocationConstraint (legacy AWS behavior).
            We normalise None → "us-east-1".

        Returns:
            AWS region slug (e.g., "us-east-1", "ap-south-1").
        """
        try:
            response = self._s3.get_bucket_location(Bucket=name)
            location = response.get("LocationConstraint")
            # None means us-east-1 (the original/default region)
            return location or "us-east-1"
        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_error(exc)
            raise

    # ── Bucket Details ────────────────────────────────────────────────────────

    def get_bucket_details(self, name: str) -> S3BucketDetails:
        """
        Collect real-time bucket details from multiple S3 API calls.

        Calls made (in order):
          1. GetBucketLocation  → region
          2. GetBucketVersioning → versioning status
          3. GetBucketEncryption → encryption config
          4. GetPublicAccessBlock → public access settings

        For calls 2-4, permission errors are handled gracefully
        (returns None/False instead of raising) since some IAM policies
        restrict these read operations.

        Returns:
            S3BucketDetails with all collected metadata.
        """
        # ── Region ────────────────────────────────────────────────────────────
        region = self.get_bucket_location(name)

        # ── Versioning ────────────────────────────────────────────────────────
        versioning_status = "Disabled"
        versioning_enabled = False
        try:
            v_resp = self._s3.get_bucket_versioning(Bucket=name)
            raw_status = v_resp.get("Status", "")
            if raw_status == "Enabled":
                versioning_status = "Enabled"
                versioning_enabled = True
            elif raw_status == "Suspended":
                versioning_status = "Suspended"
                versioning_enabled = False
            else:
                versioning_status = "Disabled"  # Never configured
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "AccessDenied":
                logger.warning("get_bucket_versioning failed for {}: {}", name, code)

        # ── Encryption ────────────────────────────────────────────────────────
        encryption_enabled = False
        encryption_type: str | None = None
        try:
            e_resp = self._s3.get_bucket_encryption(Bucket=name)
            rules = (
                e_resp.get("ServerSideEncryptionConfiguration", {})
                .get("Rules", [])
            )
            if rules:
                encryption_enabled = True
                algo = (
                    rules[0]
                    .get("ApplyServerSideEncryptionByDefault", {})
                    .get("SSEAlgorithm", "AES256")
                )
                encryption_type = algo
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            # Not encrypted — these codes are normal "not found" responses
            if code not in (
                "ServerSideEncryptionConfigurationNotFoundError",
                "NoSuchServerSideEncryptionConfiguration",
                "AccessDenied",
            ):
                logger.warning("get_bucket_encryption unexpected error for {}: {}", name, code)

        # ── Public Access Block ───────────────────────────────────────────────
        public_access_blocked: bool | None = None
        try:
            pa_resp = self._s3.get_public_access_block(Bucket=name)
            config = pa_resp.get("PublicAccessBlockConfiguration", {})
            # All four settings must be True for the bucket to be fully private
            public_access_blocked = all(
                [
                    config.get("BlockPublicAcls", False),
                    config.get("IgnorePublicAcls", False),
                    config.get("BlockPublicPolicy", False),
                    config.get("RestrictPublicBuckets", False),
                ]
            )
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("NoSuchPublicAccessBlockConfiguration", "AccessDenied"):
                logger.warning("get_public_access_block failed for {}: {}", name, code)
            public_access_blocked = None  # Cannot determine

        return S3BucketDetails(
            name=name,
            region=region,
            creation_date=None,  # Filled in by BucketService from list_buckets or DB
            versioning_status=versioning_status,
            versioning_enabled=versioning_enabled,
            encryption_enabled=encryption_enabled,
            encryption_type=encryption_type,
            public_access_blocked=public_access_blocked,
        )

    # ── Ownership Check ───────────────────────────────────────────────────────

    def is_bucket_in_account(self, name: str, all_buckets: list[S3BucketSummary] | None = None) -> bool:
        """
        Check if a bucket is owned by the connected AWS account.

        How it works:
          - S3 list_buckets() ONLY returns buckets owned by the authenticated account.
          - If the target bucket appears in that list, the account owns it.
          - If a pre-fetched bucket list is provided (to avoid a redundant API call),
            it is used directly.

        Args:
            name:        The bucket name to check.
            all_buckets: Optional pre-fetched list from list_buckets() to reuse.

        Returns:
            True if the connected account owns this bucket.
        """
        if all_buckets is None:
            all_buckets = self.list_buckets()
        return any(b.name == name for b in all_buckets)


# Transient in-memory storage of recently deleted buckets to manage S3 eventual consistency
RECENTLY_DELETED_BUCKETS: dict[str, datetime] = {}


# ─────────────────────────────────────────────────────────────────────────────
# BucketService — Business Logic + DB Orchestration
# ─────────────────────────────────────────────────────────────────────────────


class BucketService:
    """
    Orchestrates S3 bucket operations for the authenticated user.

    Instantiated once per request with a DB session and the current user.
    Gets the user's AWS credentials from the connected AWSAccount record.
    """

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._bucket_repo = BucketRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_operator_and_account(self) -> tuple[S3BucketOperator, Any]:
        """
        Get the S3BucketOperator initialised with the user's AWS credentials.

        Fetches the connected AWSAccount, decrypts the secret key, and
        creates a fresh boto3 session.

        Returns:
            (operator, aws_account) tuple.

        Raises:
            HTTPException 404: If the user has no connected AWS account.
        """
        account = self._aws_repo.get_by_user_id(self._user.id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No AWS account connected. "
                    "Call POST /api/v1/aws/connect first to link your AWS account."
                ),
            )

        secret_key = CredentialManager.decrypt(account.secret_access_key_encrypted)

        operator = S3BucketOperator(
            access_key_id=account.access_key_id,
            secret_access_key=secret_key,
            region=account.region,
        )
        return operator, account

    # ── List Buckets ──────────────────────────────────────────────────────────

    def list_buckets(self) -> list[Bucket]:
        """
        List all S3 buckets in the connected AWS account.
        """
        operator, account = self._get_operator_and_account()

        # Step 1: Real-time bucket list from AWS
        aws_buckets = operator.list_buckets()

        # Clean up stale/old recently deleted bucket entries (older than 30s)
        now = datetime.now(timezone.utc)
        for name in list(RECENTLY_DELETED_BUCKETS.keys()):
            if (now - RECENTLY_DELETED_BUCKETS[name]).total_seconds() > 30.0:
                RECENTLY_DELETED_BUCKETS.pop(name, None)

        # Filter out recently deleted buckets from S3's list (S3 eventual consistency)
        aws_buckets = [b for b in aws_buckets if b.name not in RECENTLY_DELETED_BUCKETS]

        aws_names = {b.name for b in aws_buckets}
        aws_by_name = {b.name: b for b in aws_buckets}

        # Step 2: Local DB records (O(1) lookup map)
        local_map = self._bucket_repo.get_all_by_user_as_map(self._user.id)

        result: list[Bucket] = []

        for aws_bucket in aws_buckets:
            name = aws_bucket.name

            if name in local_map:
                # CloudVault-managed: update creation_date if not set
                local = local_map[name]
                if local.creation_date is None and aws_bucket.creation_date:
                    self._bucket_repo.update_metadata(
                        local, creation_date=aws_bucket.creation_date
                    )
                result.append(local)
            else:
                # Discovered bucket (created outside CloudVault) —
                # Store a minimal record so future list calls are enriched.
                # Wrap in try/except: a UNIQUE constraint violation (same bucket_name
                # already recorded under a different row) must NOT crash the whole listing.
                try:
                    region = operator.get_bucket_location(name)
                except HTTPException:
                    region = account.region  # Fallback to account's default region

                try:
                    discovered = self._bucket_repo.create(
                        user_id=self._user.id,
                        aws_account_id=account.id,
                        bucket_name=name,
                        region=region,
                        creation_date=aws_bucket.creation_date,
                        bucket_type=BucketType.UNKNOWN.value,
                    )
                    result.append(discovered)
                except Exception as db_err:  # IntegrityError (duplicate bucket_name) or other
                    self._bucket_repo._db.rollback()
                    logger.warning(
                        "Could not create discovered-bucket DB record for '{}' — possibly a duplicate. Fetching existing record. err={}",
                        name, str(db_err),
                    )
                    # Try to fetch whichever row already exists and still show this bucket
                    existing = self._bucket_repo.get_by_name(name)
                    if existing is not None:
                        result.append(existing)

        # Remove DB records for buckets that no longer exist in AWS.
        # Grace period: if the DB record is less than 120 seconds old, keep it in
        # the listing — it was just created and S3 may not have propagated it yet.
        for name, local in local_map.items():
            if name not in aws_names:
                try:
                    created_ts = local.created_at
                    # Normalise to UTC-aware for safe subtraction
                    if created_ts.tzinfo is None:
                        created_ts = created_ts.replace(tzinfo=timezone.utc)
                    age = (now - created_ts).total_seconds()
                except Exception:
                    age = 999  # On any error, treat as old

                if age < 120.0:
                    # Keep recently created bucket in results (eventual consistency)
                    result.append(local)
                    logger.info(
                        "Keeping recently created bucket in list (grace period, age={:.1f}s) | name={}",
                        age, name,
                    )
                else:
                    logger.info(
                        "Bucket {} no longer in AWS account — removing local record | user_id={}",
                        name, str(self._user.id)
                    )
                    self._bucket_repo.delete(local)

        logger.info(
            "Listed {} buckets | user_id={}", len(result), str(self._user.id)
        )
        return sorted(result, key=lambda b: b.bucket_name)

    # ── Create Bucket ─────────────────────────────────────────────────────────

    def create_bucket(self, data: BucketCreate) -> Bucket:
        """
        Validate, create an S3 bucket, and store its metadata locally.

        Steps:
          1. Validate bucket_name and region (client-side, before AWS call).
          2. Check if bucket_name already exists in local DB (fast check).
          3. Call S3 CreateBucket.
          4. Store bucket metadata in local DB.

        Args:
            data: Validated BucketCreate request payload.

        Returns:
            The created Bucket ORM instance.

        Raises:
            HTTPException 422: Invalid bucket name or region.
            HTTPException 409: Bucket name already taken (locally or globally).
            HTTPException 403: Missing s3:CreateBucket permission.
        """
        # Step 1: Validate locally (avoids slow round-trip for obvious errors)
        validate_bucket_name(data.bucket_name)
        validate_aws_region(data.region)

        operator, account = self._get_operator_and_account()

        # Step 2: Check local DB first (fast path for duplicates we created)
        if self._bucket_repo.exists_by_name(data.bucket_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A bucket named '{data.bucket_name}' is already tracked in CloudVault.",
            )

        # Step 3: Create in AWS (will raise 409 if globally taken)
        operator.create_bucket(name=data.bucket_name, region=data.region)

        # Step 4: Store metadata locally
        bucket = self._bucket_repo.create(
            user_id=self._user.id,
            aws_account_id=account.id,
            bucket_name=data.bucket_name,
            region=data.region,
            creation_date=datetime.now(timezone.utc),
            bucket_type=BucketType.PRIVATE.value,  # New buckets default to private
        )

        logger.success(
            "Bucket created | name={} region={} user_id={}",
            data.bucket_name, data.region, str(self._user.id),
        )

        # Audit log
        try:
            ActivityService.log_activity(
                self._db,
                user_id=self._user.id,
                action="BucketCreate",
                resource_type="bucket",
                resource_id=data.bucket_name,
                status_code="success",
                message=f"S3 bucket '{data.bucket_name}' created in region {data.region}.",
            )
        except Exception:
            pass

        return bucket

    # ── Get Bucket Details ────────────────────────────────────────────────────

    def get_bucket_details(self, bucket_name: str) -> tuple[S3BucketDetails, Bucket | None]:
        """
        Return real-time bucket details from AWS, supplemented by local DB metadata.

        Steps:
          1. Call S3 GetBucketLocation, GetBucketVersioning, GetBucketEncryption,
             GetPublicAccessBlock (4 API calls).
          2. Get DB record for supplementary metadata (creation_date).
          3. Update DB with fresh versioning/encryption state.
          4. Return combined result.

        Returns:
            (S3BucketDetails, Optional[Bucket]) — details from AWS + DB record.

        Raises:
            HTTPException 404: Bucket does not exist in AWS.
            HTTPException 403: Missing read permissions.
        """
        operator, _ = self._get_operator_and_account()

        # Get real-time details from AWS
        details = operator.get_bucket_details(bucket_name)

        # Supplement with DB creation_date if available
        local = self._bucket_repo.get_by_name(bucket_name)
        if local:
            details.creation_date = local.creation_date
            # Update cached metadata in DB
            bucket_type = _derive_bucket_type(details.public_access_blocked)
            self._bucket_repo.update_metadata(
                local,
                versioning_enabled=details.versioning_enabled,
                encryption_enabled=details.encryption_enabled,
                bucket_type=bucket_type,
            )

        logger.info(
            "Bucket details fetched | name={} user_id={}",
            bucket_name, str(self._user.id),
        )
        return details, local

    # ── Delete Bucket ─────────────────────────────────────────────────────────

    def delete_bucket(self, bucket_name: str) -> None:
        """
        Delete an S3 bucket and remove its local DB record.

        Steps:
          1. Verify the bucket exists in AWS (head_bucket).
          2. Call S3 DeleteBucket — AWS rejects if not empty.
          3. Remove local DB record on success.

        CloudVault NEVER automatically deletes bucket contents.

        Raises:
            HTTPException 404: Bucket not found.
            HTTPException 409: Bucket is not empty.
            HTTPException 403: Missing s3:DeleteBucket permission.
        """
        operator, _ = self._get_operator_and_account()

        # Check existence first to give a 404 before attempting delete
        check = operator.head_bucket(bucket_name)
        if not check["exists"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' does not exist.",
            )

        if not check["accessible"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bucket '{bucket_name}' exists but is not accessible with your credentials.",
            )

        # Delete from AWS (raises 409 if not empty)
        operator.delete_bucket(bucket_name)

        # Record this deletion to prevent eventual consistency listing races
        RECENTLY_DELETED_BUCKETS[bucket_name] = datetime.now(timezone.utc)

        # Remove local DB record (if tracked)
        removed = self._bucket_repo.delete_by_name(bucket_name)

        logger.info(
            "Bucket deleted | name={} db_record_removed={} user_id={}",
            bucket_name, removed, str(self._user.id),
        )

        # Audit log
        try:
            ActivityService.log_activity(
                self._db,
                user_id=self._user.id,
                action="BucketDelete",
                resource_type="bucket",
                resource_id=bucket_name,
                status_code="success",
                message=f"S3 bucket '{bucket_name}' permanently deleted.",
            )
        except Exception:
            pass

    # ── Force Empty & Delete Bucket ────────────────────────────────────────────────────────

    def force_delete_bucket(self, bucket_name: str) -> tuple[int, int]:
        """
        Force-empty ALL objects and versions from the bucket then permanently delete it.

        Steps:
          1. Verify bucket existence and accessibility.
          2. Use S3BucketOperator.empty_bucket() to batch-delete all objects and
             all version markers (handles versioned buckets correctly).
          3. Call S3 DeleteBucket (now succeeds because bucket is empty).
          4. Remove the local DB tracking record.

        Returns:
            (objects_deleted, versions_deleted) — counts of what was wiped.

        Raises:
            HTTPException 404: Bucket not found.
            HTTPException 403: Missing s3:DeleteObject or s3:DeleteBucket permission.
        """
        operator, _ = self._get_operator_and_account()

        check = operator.head_bucket(bucket_name)
        if not check["exists"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' does not exist.",
            )
        if not check["accessible"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bucket '{bucket_name}' exists but is not accessible with your credentials.",
            )

        # Empty all objects and versions from S3
        objects_deleted, versions_deleted = operator.empty_bucket(bucket_name)
        logger.info(
            "Force-empty complete | name={} objects={} versions={} | now deleting bucket",
            bucket_name, objects_deleted, versions_deleted,
        )

        # Now the bucket is empty — delete it
        operator.delete_bucket(bucket_name)

        # Record deletion to prevent eventual-consistency listing races
        RECENTLY_DELETED_BUCKETS[bucket_name] = datetime.now(timezone.utc)

        # Remove local DB tracking record
        removed = self._bucket_repo.delete_by_name(bucket_name)

        logger.info(
            "Bucket force-deleted | name={} db_record_removed={} user_id={}",
            bucket_name, removed, str(self._user.id),
        )
        return objects_deleted, versions_deleted

    # ── Check Existence ───────────────────────────────────────────────────────

    def check_exists(self, bucket_name: str) -> dict[str, bool]:
        """
        Check if an S3 bucket exists and is accessible.

        Returns:
            {"exists": bool, "accessible": bool}
        """
        operator, _ = self._get_operator_and_account()
        result = operator.head_bucket(bucket_name)

        logger.info(
            "Bucket existence check | name={} exists={} user_id={}",
            bucket_name, result["exists"], str(self._user.id),
        )
        return result

    # ── Verify Ownership ──────────────────────────────────────────────────────

    def verify_ownership(self, bucket_name: str) -> dict[str, Any]:
        """
        Verify that the connected AWS account owns the specified bucket.

        How it works:
          S3 list_buckets() returns ONLY buckets owned by the authenticated account.
          If bucket_name appears in that list, the account owns it.

        Returns:
            {"is_owner": bool, "message": str}
        """
        operator, _ = self._get_operator_and_account()
        all_buckets = operator.list_buckets()
        is_owner = operator.is_bucket_in_account(bucket_name, all_buckets)

        message = (
            f"The connected AWS account owns '{bucket_name}'."
            if is_owner
            else f"'{bucket_name}' is not owned by the connected AWS account."
        )

        logger.info(
            "Bucket ownership check | name={} is_owner={} user_id={}",
            bucket_name, is_owner, str(self._user.id),
        )
        return {"is_owner": is_owner, "message": message}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _derive_bucket_type(public_access_blocked: bool | None) -> str:
    """
    Derive bucket_type string from the public access block result.

    True  → all four block settings are enabled → "private"
    False → at least one path to public access → "public"
    None  → could not determine → "unknown"
    """
    if public_access_blocked is True:
        return BucketType.PRIVATE.value
    if public_access_blocked is False:
        return BucketType.PUBLIC.value
    return BucketType.UNKNOWN.value
