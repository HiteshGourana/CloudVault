"""
backend/models/file.py
──────────────────────
SQLAlchemy 2.0 ORM model for the files table.

Sprint 5 — File Metadata Management.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.models.bucket import Bucket
    from backend.models.folder import Folder
    from backend.models.shared_link import SharedLink


class UploadStatus(str, enum.Enum):
    """
    Tracks the lifecycle status of file metadata.
    
    PENDING   : Metadata registered; upload not yet initiated.
    UPLOADING : Upload is actively in-progress.
    COMPLETED : File successfully verified in S3.
    FAILED    : Upload failed or interrupted.
    DELETED   : Soft-deleted (hidden from standard listings, but retained in DB).
    """

    PENDING = "Pending"
    UPLOADING = "Uploading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    DELETED = "Deleted"
    CANCELLED = "Cancelled"


class File(Base):
    """
    Represents metadata for a file in CloudVault.
    
    Each file record tracks the status, location, size, and properties of an S3 object.
    It maps to a specific Bucket and optionally a parent Folder.
    """

    __tablename__ = "files"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 — unique file identifier",
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("buckets.id", ondelete="CASCADE"),
        nullable=False,
        comment="The bucket this file belongs to — CASCADE DELETE",
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        comment="The parent virtual folder this file is located in. Null indicates root level.",
    )

    # ── File Properties ───────────────────────────────────────────────────────
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The display name of the file (e.g., 'invoice.pdf')",
    )
    original_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The original filename on upload request",
    )
    extension: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Lowercase file extension including dot (e.g., '.pdf')",
    )
    mime_type: Mapped[str] = mapped_column(
        String(127),
        nullable=False,
        comment="Standard Internet Media Type / Content-Type (e.g., 'application/pdf')",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes (BigInteger to support files > 2GB)",
    )
    s3_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="The exact storage key path inside S3 bucket (e.g., 'documents/reports/invoice.pdf')",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="File hashing digest (MD5/ETag or SHA-256) for verification",
    )
    storage_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="STANDARD",
        server_default="STANDARD",
        comment="S3 storage tier (e.g., STANDARD, GLACIER, DEEP_ARCHIVE)",
    )
    upload_status: Mapped[str] = mapped_column(
        SAEnum(UploadStatus, name="upload_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UploadStatus.PENDING.value,
        server_default=UploadStatus.PENDING.value,
        comment="Tracks upload status: Pending | Uploading | Completed | Failed | Deleted",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="File registration timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last modifications timestamp",
    )
    # ── Soft Delete Tracking (Sprint 7) ────────────────────────────────────────
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if the file is soft-deleted and moved to trash",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the file was soft-deleted",
    )
    bucket: Mapped["Bucket"] = relationship("Bucket", back_populates="files")  
    folder: Mapped["Folder | None"] = relationship("Folder", back_populates="files") 
    # Sprint 8: S3 shared links generated for this file
    shared_links: Mapped[list["SharedLink"]] = relationship( 
        "SharedLink",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    # ── Constraints & Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_files_bucket_id", "bucket_id"),
        Index("ix_files_folder_id", "folder_id"),
        Index("ix_files_upload_status", "upload_status"),
        Index("ix_files_extension", "extension"),
    )

    def __repr__(self) -> str:
        return (
            f"<File id={self.id!s} "
            f"name={self.file_name!r} "
            f"size={self.size_bytes} "
            f"status={self.upload_status}>"
        )
