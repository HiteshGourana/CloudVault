"""
backend/models/bucket.py
─────────────────────────
SQLAlchemy 2.0 ORM model for the buckets table.

Sprint 3 — Bucket Management.

Design decisions:
  - UUID primary key: no enumerable IDs in URLs.
  - bucket_name UNIQUE: enforced at DB level; AWS also enforces global uniqueness.
  - user_id FK + aws_account_id FK: double-anchored — every bucket is linked to
    both the application user and the connected AWS account record.
  - CASCADE DELETE on both FKs:
      · Delete a user   → their buckets are removed from CloudVault DB.
      · Delete an AWS account connection → associated bucket records are removed.
      (Actual S3 buckets in AWS are NOT affected — only the local tracking records.)
  - bucket_type: "private" | "public" — derived from S3 public access block settings.
  - creation_date: from AWS (may differ from created_at which is our record creation time).
  - versioning_enabled / encryption_enabled: last-known state from AWS; updated on sync.

Important distinction:
  This table stores METADATA about buckets, not bucket contents.
  The actual files live in S3. Deleting a row here does NOT delete the S3 bucket.

Relationship diagram:
  User ──────────────────────── (1:N) ──→ Bucket
  AWSAccount ─────────────────── (1:N) ──→ Bucket
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.models.user import User
    from backend.models.aws_account import AWSAccount
    from backend.models.folder import Folder
    from backend.models.file import File

class BucketType(str, enum.Enum):
    """
    Visibility classification of an S3 bucket.

    Derived from AWS S3 Public Access Block settings:
      PRIVATE : All four public-access-block settings are True (recommended).
      PUBLIC  : At least one public-access-block setting is False.
      UNKNOWN : Could not determine (permissions error on get_public_access_block).
    """

    PRIVATE = "private"
    PUBLIC = "public"
    UNKNOWN = "unknown"


class Bucket(Base):
    """
    Tracks S3 bucket metadata for CloudVault-managed and discovered buckets.

    One User (via aws_account) can have multiple Buckets.
    Bucket names are globally unique in S3 — enforced at both DB and AWS levels.
    """

    __tablename__ = "buckets"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — internal record identifier",
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owning application user — CASCADE DELETE",
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aws_accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="Connected AWS account record (aws_accounts.id UUID) — CASCADE DELETE",
    )

    # ── S3 Identity ───────────────────────────────────────────────────────────
    bucket_name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        unique=True,
        comment="S3 bucket name — globally unique across all AWS accounts",
    )
    region: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="AWS region where the bucket resides (e.g., us-east-1)",
    )

    # ── AWS Metadata ──────────────────────────────────────────────────────────
    creation_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Bucket creation timestamp from AWS — may differ from created_at",
    )
    bucket_type: Mapped[str] = mapped_column(
        SAEnum(BucketType, name="bucket_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BucketType.PRIVATE.value,
        server_default=BucketType.PRIVATE.value,
        comment="Visibility: private | public | unknown (from public access block settings)",
    )
    versioning_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if S3 versioning is Enabled (not Suspended or never enabled)",
    )
    encryption_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if server-side encryption is configured on the bucket",
    )

    # ── CloudVault Timestamps (UTC) ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this CloudVault record was created (NOT the S3 bucket creation time)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="When this CloudVault record was last updated",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="buckets",
    )
    aws_account: Mapped["AWSAccount"] = relationship(  # type: ignore[name-defined]
        "AWSAccount",
        back_populates="buckets",
    )
    # Sprint 4: S3 folders metadata cache linked to the bucket
    folders: Mapped[list["Folder"]] = relationship(  # type: ignore[name-defined]
        "Folder",
        back_populates="bucket",
        cascade="all, delete-orphan",
    )
    # Sprint 5: S3 files metadata linked to the bucket
    files: Mapped[list["File"]] = relationship(  # type: ignore[name-defined]
        "File",
        back_populates="bucket",
        cascade="all, delete-orphan",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_buckets_user_id", "user_id"),
        Index("ix_buckets_aws_account_id", "aws_account_id"),
        Index("ix_buckets_bucket_name", "bucket_name"),
        Index("ix_buckets_region", "region"),
    )

    def __repr__(self) -> str:
        return (
            f"<Bucket id={self.id!s} "
            f"name={self.bucket_name!r} "
            f"region={self.region!r}>"
        )
