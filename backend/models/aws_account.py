"""
backend/models/aws_account.py
──────────────────────────────
SQLAlchemy 2.0 ORM model for the aws_accounts table.

Sprint 2 — one table, one row per user.

Design decisions:
  - UUID primary key: no enumerable IDs exposed in URLs.
  - user_id UNIQUE: enforces one active connection per user at DB level.
    A second attempt to INSERT for the same user_id raises IntegrityError —
    handled at the service layer as an upsert (update existing row).
  - access_key_id stored in plain text: it is not a secret — AWS access key IDs
    are visible in IAM consoles and CloudTrail logs.
  - secret_access_key_encrypted: Fernet-encrypted via CredentialManager.
    NEVER stored or logged in plain text.
  - is_connected: allows soft "disconnection" without deleting the row.
    For this sprint, DELETE /aws/disconnect performs a hard delete.
  - connected_at: set on every successful connect/reconnect.
  - updated_at: auto-updated on every row change.

Relationship with users:
  - One User → at most One AWSAccount (1:1, enforced by UNIQUE on user_id).
  - cascade="all, delete-orphan": deleting a user also deletes their AWS record.

SECURITY NOTE:
  This table stores long-lived IAM access keys encrypted with Fernet.
  For production workloads, use short-lived IAM roles via AWS STS AssumeRole
  or store credentials in AWS Secrets Manager — not in your application DB.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.user import User
    from backend.models.bucket import Bucket

class AWSAccount(Base):
    """
    Stores an authenticated user's connected AWS account credentials.

    One row per application user (enforced by unique constraint on user_id).
    """

    __tablename__ = "aws_accounts"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — unique record identifier",
    )

    # ── Foreign Key ───────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # Enforces one-connection-per-user at DB level
        comment="References the owning user — CASCADE DELETE on user removal",
    )

    # ── AWS Account Identity (from STS GetCallerIdentity) ─────────────────────
    aws_account_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="12-digit AWS account ID returned by STS GetCallerIdentity",
    )
    iam_arn: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Full IAM ARN (e.g., arn:aws:iam::123456789012:user/alice)",
    )
    iam_user_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="IAM username extracted from ARN — null for root/role credentials",
    )

    # ── Connection Configuration ──────────────────────────────────────────────
    region: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="AWS region used for the connection (e.g., us-east-1)",
    )

    # ── Credentials (access_key_id is not a secret; secret key is encrypted) ──
    access_key_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="AWS access key ID — not secret, returned in API responses",
    )
    secret_access_key_encrypted: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment=(
            "Fernet-encrypted AWS secret access key. "
            "Decrypted only at runtime — NEVER returned in API responses. "
            "PRODUCTION: replace with AWS Secrets Manager reference."
        ),
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_connected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="True = credentials verified and account is active",
    )

    # ── Timestamps (UTC) ──────────────────────────────────────────────────────
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Last successful credential verification timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last row modification timestamp — auto-updated on every UPDATE",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="aws_account",
    )

    # Sprint 3: One AWSAccount → many Bucket records (local metadata only).
    # Removing an AWS connection also removes CloudVault bucket tracking records.
    # (Actual S3 buckets in AWS are NOT deleted — only the local records.)
    buckets: Mapped[list["Bucket"]] = relationship(  # type: ignore[name-defined]
        "Bucket",
        back_populates="aws_account",
        cascade="all, delete-orphan",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_aws_accounts_user_id", "user_id"),          # Fast user lookup
        Index("ix_aws_accounts_aws_account_id", "aws_account_id"),  # Filter by AWS account
    )

    def __repr__(self) -> str:
        return (
            f"<AWSAccount id={self.id!s} "
            f"user_id={self.user_id!s} "
            f"aws_account_id={self.aws_account_id!r} "
            f"connected={self.is_connected}>"
        )
