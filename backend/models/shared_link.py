"""
backend/models/shared_link.py
─────────────────────────────
SQLAlchemy 2.0 ORM model for the shared_links table.

Sprint 8 — File Sharing & Secure Access.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class ShareType(str, enum.Enum):
    """
    Specifies the action authorized by the pre-signed URL.
    
    DOWNLOAD : Authorizes GET requests to retrieve S3 objects.
    UPLOAD   : Authorizes POST/PUT requests to upload S3 objects.
    """

    DOWNLOAD = "Download"
    UPLOAD = "Upload"


class SharedLink(Base):
    """
    Tracks sharing metadata for pre-signed URLs generated within CloudVault.
    
    Links are tied to a User (the owner) and optionally a File (for download sharing).
    S3 Pre-Signed URLs are transient and computed on-the-fly; only token metadata is persisted.
    """

    __tablename__ = "shared_links"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — unique shared link identifier",
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="References the user who created the share — CASCADE DELETE",
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=True,
        comment="References the shared file metadata. Null for upload links (file does not exist yet).",
    )

    # ── Share Tokens & Properties ─────────────────────────────────────────────
    share_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        comment="Secure unique token key identifying the share",
    )
    share_type: Mapped[str] = mapped_column(
        SAEnum(ShareType, name="share_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        comment="Authorizations category: Download | Upload",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="True if the share is active and hasn't been manually revoked",
    )

    # ── Lifecycle Timestamps ──────────────────────────────────────────────────
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Expiration timestamp. Link is invalid after this UTC time.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Creation timestamp",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the share was manually revoked",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="shared_links")  # type: ignore[name-defined]
    file: Mapped["File | None"] = relationship("File", back_populates="shared_links")  # type: ignore[name-defined]

    # ── Constraints & Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_shared_links_user_id", "user_id"),
        Index("ix_shared_links_file_id", "file_id"),
        Index("ix_shared_links_share_token", "share_token"),
    )

    def __repr__(self) -> str:
        return (
            f"<SharedLink id={self.id!s} "
            f"token={self.share_token!r} "
            f"type={self.share_type} "
            f"active={self.is_active}>"
        )
