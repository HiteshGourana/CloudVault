"""
backend/models/folder.py
────────────────────────
SQLAlchemy 2.0 ORM model for the folders table.

Sprint 4 — Virtual Folder Management.

A folder in S3 is represented by a prefix ending with a slash (/).
We cache folder metadata locally to enable fast hierarchical querying,
tree building, and validation, keeping it synchronized with S3 objects.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Folder(Base):
    """
    Represents a virtual folder.
    
    A folder always belongs to a specific Bucket, and may optionally have a parent folder (hierarchical).
    """

    __tablename__ = "folders"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — internal folder identifier",
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("buckets.id", ondelete="CASCADE"),
        nullable=False,
        comment="References the bucket this folder belongs to — CASCADE DELETE",
    )
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        comment="References the parent folder. Null indicates a root-level folder",
    )

    # ── Properties ────────────────────────────────────────────────────────────
    folder_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The display name of the folder (e.g., 'reports')",
    )
    full_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="The absolute S3 prefix path ending with a slash (e.g., 'documents/reports/')",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Modification timestamp",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    bucket: Mapped["Bucket"] = relationship("Bucket", back_populates="folders")  # type: ignore[name-defined]
    
    # Self-referential relationship for parent/child navigation
    parent: Mapped["Folder | None"] = relationship(
        "Folder",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    # Sprint 5: S3 files metadata cached inside this virtual folder
    files: Mapped[list["File"]] = relationship(  # type: ignore[name-defined]
        "File",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    # ── Constraints & Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        # Sibling folders under the same parent folder within a bucket must have unique names
        UniqueConstraint("bucket_id", "parent_folder_id", "folder_name", name="uq_folders_sibling_names"),
        # Unique paths within the same bucket
        UniqueConstraint("bucket_id", "full_path", name="uq_folders_bucket_path"),
        Index("ix_folders_bucket_id", "bucket_id"),
        Index("ix_folders_parent_folder_id", "parent_folder_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Folder id={self.id!s} "
            f"name={self.folder_name!r} "
            f"full_path={self.full_path!r}>"
        )
