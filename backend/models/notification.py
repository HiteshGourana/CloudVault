"""
backend/models/notification.py
──────────────────────────────
SQLAlchemy 2.0 ORM model for the notifications table.

Sprint 10 — Enterprise Features (Audit, Search, Notifications & Admin)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Notification(Base):
    """
    Represents system notification alerts targeted for a specific User.
    """

    __tablename__ = "notifications"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — unique notification identifier",
    )

    # ── Foreign Key ───────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="The recipient user UUID — CASCADE DELETE",
    )

    # ── Notification Properties ───────────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Short notification title (e.g. 'Upload Failed')",
    )
    message: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Detailed notification message text description",
    )
    notification_type: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        comment="Alert category (e.g., 'upload_status', 'aws_connection', 'storage_warning')",
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if user has acknowledged the notification",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp when alert was triggered",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]

    # ── Constraints & Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id!s} "
            f"user={self.user_id!s} "
            f"title={self.title!r} "
            f"read={self.is_read}>"
        )
