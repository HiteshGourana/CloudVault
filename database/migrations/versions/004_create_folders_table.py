"""create_folders_table

Revision ID: 004_create_folders_table
Revises: 003_create_buckets_table
Create Date: 2026-06-29

Sprint 4 — Virtual Folder Management

Creates the `folders` table with:
  - UUID primary key
  - bucket_id FK → buckets.id (CASCADE DELETE)
  - parent_folder_id FK → folders.id (CASCADE DELETE, nullable)
  - folder_name, full_path strings
  - Unique sibling names check: uq_folders_sibling_names (bucket_id, parent_folder_id, folder_name)
  - Unique paths check: uq_folders_bucket_path (bucket_id, full_path)
  - Indexes on foreign keys
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_create_folders_table"
down_revision: Union[str, None] = "003_create_buckets_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the folders table."""
    op.create_table(
        "folders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — internal folder identifier",
        ),
        sa.Column(
            "bucket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="References the bucket this folder belongs to — CASCADE DELETE",
        ),
        sa.Column(
            "parent_folder_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="References the parent folder. Null indicates a root-level folder",
        ),
        sa.Column(
            "folder_name",
            sa.String(length=255),
            nullable=False,
            comment="The display name of the folder (e.g., 'reports')",
        ),
        sa.Column(
            "full_path",
            sa.String(length=1024),
            nullable=False,
            comment="The absolute S3 prefix path ending with a slash (e.g., 'documents/reports/')",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Modification timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["bucket_id"],
            ["buckets.id"],
            ondelete="CASCADE",
            name="fk_folders_bucket_id_buckets",
        ),
        sa.ForeignKeyConstraint(
            ["parent_folder_id"],
            ["folders.id"],
            ondelete="CASCADE",
            name="fk_folders_parent_folder_id_folders",
        ),
        sa.UniqueConstraint("bucket_id", "parent_folder_id", "folder_name", name="uq_folders_sibling_names"),
        sa.UniqueConstraint("bucket_id", "full_path", name="uq_folders_bucket_path"),
        comment="Stores folder metadata for faster navigation within CloudVault",
    )

    # Indexes
    op.create_index("ix_folders_bucket_id", "folders", ["bucket_id"], unique=False)
    op.create_index("ix_folders_parent_folder_id", "folders", ["parent_folder_id"], unique=False)


def downgrade() -> None:
    """Drop the folders table."""
    op.drop_index("ix_folders_parent_folder_id", table_name="folders")
    op.drop_index("ix_folders_bucket_id", table_name="folders")
    op.drop_table("folders")
