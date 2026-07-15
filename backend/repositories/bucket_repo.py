"""
backend/repositories/bucket_repo.py
─────────────────────────────────────
Data access layer for the buckets table.

Responsibilities:
  - All SQL queries for `buckets` live here.
  - No boto3 calls. No business logic. No HTTP exceptions.
  - Returns ORM instances or None — callers decide what to do with None.

Design notes:
  - get_all_by_user() returns a map keyed by bucket_name for O(1) lookup
    during list_buckets() enrichment.
  - create_or_update() handles both CloudVault-created and externally-discovered
    buckets transparently.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.bucket import Bucket, BucketType


class BucketRepository:
    """Encapsulates all database operations for the buckets table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_name(self, bucket_name: str) -> Bucket | None:
        """Fetch a bucket record by its S3 bucket name (globally unique)."""
        return (
            self._db.query(Bucket)
            .filter(Bucket.bucket_name == bucket_name)
            .first()
        )

    def get_by_id(self, record_id: uuid.UUID) -> Bucket | None:
        """Fetch a bucket record by its CloudVault UUID."""
        return self._db.get(Bucket, record_id)

    def get_all_by_user(self, user_id: uuid.UUID) -> list[Bucket]:
        """
        Return all bucket records belonging to a user, ordered by bucket_name.

        Used by list_buckets() to enrich the real-time AWS list with local metadata.
        """
        return (
            self._db.query(Bucket)
            .filter(Bucket.user_id == user_id)
            .order_by(Bucket.bucket_name)
            .all()
        )

    def get_all_by_user_as_map(self, user_id: uuid.UUID) -> dict[str, Bucket]:
        """
        Return all user bucket records as a dict keyed by bucket_name.

        O(1) lookup by name. Used during list enrichment.

        Returns:
            {"my-bucket": <Bucket>, "other-bucket": <Bucket>, ...}
        """
        return {b.bucket_name: b for b in self.get_all_by_user(user_id)}

    def exists_by_name(self, bucket_name: str) -> bool:
        """Fast existence check — queries only the id column."""
        return (
            self._db.query(Bucket.id)
            .filter(Bucket.bucket_name == bucket_name)
            .first()
        ) is not None

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        user_id: uuid.UUID,
        aws_account_id: uuid.UUID,
        bucket_name: str,
        region: str,
        creation_date: datetime | None = None,
        bucket_type: str = BucketType.PRIVATE.value,
        versioning_enabled: bool = False,
        encryption_enabled: bool = False,
    ) -> Bucket:
        """
        Insert a new bucket record.

        Args:
            user_id:           Owning application user's UUID.
            aws_account_id:    UUID of the aws_accounts record (NOT the 12-digit AWS ID).
            bucket_name:       S3 bucket name (globally unique).
            region:            AWS region slug.
            creation_date:     Bucket creation time from AWS (optional).
            bucket_type:       "private" | "public" | "unknown".
            versioning_enabled: Whether versioning was enabled at creation.
            encryption_enabled: Whether encryption was enabled at creation.

        Returns:
            The committed and refreshed Bucket instance.
        """
        bucket = Bucket(
            user_id=user_id,
            aws_account_id=aws_account_id,
            bucket_name=bucket_name,
            region=region,
            creation_date=creation_date,
            bucket_type=bucket_type,
            versioning_enabled=versioning_enabled,
            encryption_enabled=encryption_enabled,
        )
        self._db.add(bucket)
        self._db.commit()
        self._db.refresh(bucket)
        return bucket

    def update_metadata(
        self,
        bucket: Bucket,
        *,
        versioning_enabled: bool | None = None,
        encryption_enabled: bool | None = None,
        bucket_type: str | None = None,
        creation_date: datetime | None = None,
    ) -> Bucket:
        """
        Update cached metadata fields on an existing bucket record.

        Only updates fields that are explicitly provided (not None).
        Used after fetching real-time data from AWS to keep the DB in sync.

        Args:
            bucket: The existing Bucket ORM object to update.
            **kwargs: Fields to update (only non-None values are applied).

        Returns:
            The updated and committed Bucket instance.
        """
        if versioning_enabled is not None:
            bucket.versioning_enabled = versioning_enabled
        if encryption_enabled is not None:
            bucket.encryption_enabled = encryption_enabled
        if bucket_type is not None:
            bucket.bucket_type = bucket_type
        if creation_date is not None and bucket.creation_date is None:
            bucket.creation_date = creation_date

        self._db.commit()
        self._db.refresh(bucket)
        return bucket

    def delete(self, bucket: Bucket) -> None:
        """
        Permanently delete a bucket record from the CloudVault database.

        Called AFTER the actual S3 bucket has been successfully deleted from AWS.
        Does NOT delete the S3 bucket itself.

        Args:
            bucket: The Bucket ORM instance to remove.
        """
        self._db.delete(bucket)
        self._db.commit()

    def delete_by_name(self, bucket_name: str) -> bool:
        """
        Delete a bucket record by name if it exists.

        Returns:
            True if a record was found and deleted, False if no record existed.
        """
        bucket = self.get_by_name(bucket_name)
        if bucket is None:
            return False
        self.delete(bucket)
        return True
