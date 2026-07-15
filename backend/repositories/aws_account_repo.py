"""
backend/repositories/aws_account_repo.py
──────────────────────────────────────────
Data access layer for the aws_accounts table.

Responsibilities:
  - All SQL queries for aws_accounts live here — not in services or routes.
  - No business logic. No HTTPExceptions. No boto3 calls.
  - Returns ORM instances or None — callers decide what to do with None.

Upsert pattern:
  The connect flow uses create_or_update() to handle both the first-time
  connection and reconnection (credential update) cases transparently.
  This avoids exposing the "does a row already exist?" decision to the service layer.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.aws_account import AWSAccount


class AWSAccountRepository:
    """Encapsulates all database operations for the aws_accounts table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_user_id(self, user_id: uuid.UUID) -> AWSAccount | None:
        """
        Fetch the AWS account record for a given user.

        Returns None if the user has not connected an AWS account yet.
        """
        return (
            self._db.query(AWSAccount)
            .filter(AWSAccount.user_id == user_id)
            .first()
        )

    def get_by_id(self, record_id: uuid.UUID) -> AWSAccount | None:
        """Fetch by primary key."""
        return self._db.get(AWSAccount, record_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        user_id: uuid.UUID,
        aws_account_id: str,
        iam_arn: str,
        iam_user_name: str | None,
        region: str,
        access_key_id: str,
        secret_access_key_encrypted: str,
    ) -> AWSAccount:
        """
        Insert a new AWS account record.

        Args:
            user_id:                    Owning user's UUID.
            aws_account_id:             12-digit AWS account ID from STS.
            iam_arn:                    Full IAM ARN from STS.
            iam_user_name:              IAM username (nullable).
            region:                     AWS region slug.
            access_key_id:              Plain-text access key ID.
            secret_access_key_encrypted: Fernet-encrypted secret access key.

        Returns:
            The newly created and committed AWSAccount instance.
        """
        account = AWSAccount(
            user_id=user_id,
            aws_account_id=aws_account_id,
            iam_arn=iam_arn,
            iam_user_name=iam_user_name,
            region=region,
            access_key_id=access_key_id,
            secret_access_key_encrypted=secret_access_key_encrypted,
            is_connected=True,
            connected_at=datetime.now(timezone.utc),
        )
        self._db.add(account)
        self._db.commit()
        self._db.refresh(account)
        return account

    def update(
        self,
        account: AWSAccount,
        *,
        aws_account_id: str,
        iam_arn: str,
        iam_user_name: str | None,
        region: str,
        access_key_id: str,
        secret_access_key_encrypted: str,
    ) -> AWSAccount:
        """
        Update an existing AWS account record with new credential information.

        Called when the user reconnects (updates credentials or region).

        Args:
            account: The existing AWSAccount ORM object to update.
            **kwargs: New field values (see field descriptions in create()).

        Returns:
            The updated and committed AWSAccount instance.
        """
        account.aws_account_id = aws_account_id
        account.iam_arn = iam_arn
        account.iam_user_name = iam_user_name
        account.region = region
        account.access_key_id = access_key_id
        account.secret_access_key_encrypted = secret_access_key_encrypted
        account.is_connected = True
        account.connected_at = datetime.now(timezone.utc)
        # updated_at is handled automatically by the ORM onupdate= callback.
        self._db.commit()
        self._db.refresh(account)
        return account

    def create_or_update(
        self,
        *,
        user_id: uuid.UUID,
        aws_account_id: str,
        iam_arn: str,
        iam_user_name: str | None,
        region: str,
        access_key_id: str,
        secret_access_key_encrypted: str,
    ) -> tuple[AWSAccount, bool]:
        """
        Upsert — create a new record or update the existing one for this user.

        Returns:
            (account, created) where created=True means a new row was inserted.

        This is the only method the service layer calls for the connect flow.
        It abstracts the "first connection vs. reconnection" decision entirely.
        """
        existing = self.get_by_user_id(user_id)

        if existing is not None:
            account = self.update(
                existing,
                aws_account_id=aws_account_id,
                iam_arn=iam_arn,
                iam_user_name=iam_user_name,
                region=region,
                access_key_id=access_key_id,
                secret_access_key_encrypted=secret_access_key_encrypted,
            )
            return account, False   # False = updated, not created

        account = self.create(
            user_id=user_id,
            aws_account_id=aws_account_id,
            iam_arn=iam_arn,
            iam_user_name=iam_user_name,
            region=region,
            access_key_id=access_key_id,
            secret_access_key_encrypted=secret_access_key_encrypted,
        )
        return account, True        # True = newly created

    def delete(self, account: AWSAccount) -> None:
        """
        Permanently remove the AWS account record (hard delete).

        Called by the disconnect endpoint.
        The user's account remains active — only the AWS connection is removed.
        """
        self._db.delete(account)
        self._db.commit()
