"""update_files_soft_delete

Revision ID: 006_update_files_soft_delete
Revises: 005_create_files_table
Create Date: 2026-06-29

Sprint 7 — File Operations

Adds soft deletion columns to the `files` table:
  - is_deleted (Boolean, default False)
  - deleted_at (DateTime with timezone, nullable)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_update_files_soft_delete"
down_revision: Union[str, None] = "005_create_files_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add soft delete tracking columns to files table."""
    op.add_column(
        "files",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if the file is soft-deleted and moved to trash",
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the file was soft-deleted",
        ),
    )


def downgrade() -> None:
    """Remove soft delete tracking columns from files table."""
    op.drop_column("files", "deleted_at")
    op.drop_column("files", "is_deleted")
