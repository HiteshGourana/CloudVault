"""
backend/models/activity_log.py
──────────────────────────────
SQLAlchemy 2.0 ORM model for the activity_logs table.

Sprint 10 — Enterprise Features (Audit, Search, Notifications & Admin)
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base

if TYPE_CHECKING:
    from backend.models.user import User

class ActivityLog(Base):
    """
    Tracks audit trail logs of user actions within CloudVault.
    
    This is an immutable record storage. Once written, logs cannot be modified or updated.
    """

    __tablename__ = "activity_logs"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — unique activity log identifier",
    )

    # ── Foreign Key ───────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="The user who executed the action — CASCADE DELETE",
    )

    # ── Log Parameters ────────────────────────────────────────────────────────
    action: Mapped[str] = mapped_column(
        String(127),
        nullable=False,
        comment="Action execution key (e.g., 'User Login', 'Bucket Created')",
    )
    resource_type: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        comment="Categorized resource type affected (e.g., 'file', 'bucket', 'user')",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(63),
        nullable=True,
        comment="Identifier key representing the target entity resource",
    )
    status: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        comment="Outcome status ('success', 'failure')",
    )
    message: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Detailed log description description message",
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address used (supports IPv4/IPv6 standard max format)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="User Agent header string of browser client",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Log timestamp — immutable",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User")# type: ignore[name-defined]

    # ── Constraints & Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_activity_logs_user_id", "user_id"),
        Index("ix_activity_logs_action", "action"),
        Index("ix_activity_logs_created_at", "created_at"),
        Index("ix_activity_logs_resource_type", "resource_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityLog id={self.id!s} "
            f"user={self.user_id!s} "
            f"action={self.action!r} "
            f"status={self.status}>"
        )
