"""create_files_table

Revision ID: 005_create_files_table
Revises: 004_create_folders_table
Create Date: 2026-06-29

Sprint 5 — File Metadata Management

Creates the `files` table with:
  - UUID primary key
  - bucket_id FK → buckets.id (CASCADE DELETE)
  - folder_id FK → folders.id (CASCADE DELETE, nullable)
  - file_name, original_file_name, extension, mime_type, s3_key, checksum, storage_class strings
  - size_bytes BigInteger (supporting files > 2GB)
  - upload_status Enum ("Pending", "Uploading", "Completed", "Failed", "Deleted")
  - created_at, updated_at timestamps (UTC)
  - Indexes on foreign keys and frequently queried fields
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_create_files_table"
down_revision: Union[str, None] = "004_create_folders_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the files table."""
    # Define the upload status enum type for postgres
    upload_status_enum = sa.Enum("Pending", "Uploading", "Completed", "Failed", "Deleted", "Cancelled", name="upload_status_enum")
    
    op.create_table(
        "files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — unique file identifier",
        ),
        sa.Column(
            "bucket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The bucket this file belongs to — CASCADE DELETE",
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="The parent virtual folder this file is located in. Null indicates root level.",
        ),
        sa.Column(
            "file_name",
            sa.String(length=255),
            nullable=False,
            comment="The display name of the file (e.g., 'invoice.pdf')",
        ),
        sa.Column(
            "original_file_name",
            sa.String(length=255),
            nullable=False,
            comment="The original filename on upload request",
        ),
        sa.Column(
            "extension",
            sa.String(length=32),
            nullable=False,
            comment="Lowercase file extension cache including dot (e.g., '.pdf')",
        ),
        sa.Column(
            "mime_type",
            sa.String(length=127),
            nullable=False,
            comment="Standard Internet Media Type / Content-Type (e.g., 'application/pdf')",
        ),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
            comment="File size in bytes",
        ),
        sa.Column(
            "s3_key",
            sa.String(length=1024),
            nullable=False,
            comment="The exact storage key path inside S3 bucket (e.g., 'documents/reports/invoice.pdf')",
        ),
        sa.Column(
            "checksum",
            sa.String(length=128),
            nullable=True,
            comment="File hashing digest (MD5/ETag or SHA-256) for verification",
        ),
        sa.Column(
            "storage_class",
            sa.String(length=32),
            server_default="STANDARD",
            nullable=False,
            comment="S3 storage tier (e.g., STANDARD, GLACIER, DEEP_ARCHIVE)",
        ),
        sa.Column(
            "upload_status",
            upload_status_enum,
            server_default="Pending",
            nullable=False,
            comment="Tracks upload status: Pending | Uploading | Completed | Failed | Deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="File registration timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last modifications timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["bucket_id"],
            ["buckets.id"],
            ondelete="CASCADE",
            name="fk_files_bucket_id_buckets",
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["folders.id"],
            ondelete="CASCADE",
            name="fk_files_folder_id_folders",
        ),
        comment="Tracks file metadata records within CloudVault before/after uploads",
    )

    # Indexes
    op.create_index("ix_files_bucket_id", "files", ["bucket_id"], unique=False)
    op.create_index("ix_files_folder_id", "files", ["folder_id"], unique=False)
    op.create_index("ix_files_upload_status", "files", ["upload_status"], unique=False)
    op.create_index("ix_files_extension", "files", ["extension"], unique=False)


def downgrade() -> None:
    """Drop the files table."""
    op.drop_index("ix_files_extension", table_name="files")
    op.drop_index("ix_files_upload_status", table_name="files")
    op.drop_index("ix_files_folder_id", table_name="files")
    op.drop_index("ix_files_bucket_id", table_name="files")
    op.drop_table("files")
    
    # Drop the enum type
    upload_status_enum = sa.Enum("Pending", "Uploading", "Completed", "Failed", "Deleted", "Cancelled", name="upload_status_enum")
    upload_status_enum.drop(op.get_bind(), checkfirst=True)
