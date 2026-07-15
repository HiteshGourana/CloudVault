"""create_shared_links_table

Revision ID: 007_create_shared_links_table
Revises: 006_update_files_soft_delete
Create Date: 2026-06-29

Sprint 8 — File Sharing & Secure Access

Creates the `shared_links` table with:
  - UUID primary key
  - user_id FK → users.id (CASCADE DELETE)
  - file_id FK → files.id (CASCADE DELETE, nullable)
  - share_token (unique string)
  - share_type Enum ("Download", "Upload")
  - is_active Boolean (default True)
  - expires_at, created_at, revoked_at timestamps (UTC)
  - Indexes on token and foreign keys
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_create_shared_links_table"
down_revision: Union[str, None] = "006_update_files_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the shared_links table."""
    # Define share type enum type for postgres
    share_type_enum = sa.Enum("Download", "Upload", name="share_type_enum")

    op.create_table(
        "shared_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — unique shared link identifier",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="References the user who created the share — CASCADE DELETE",
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="References the shared file. Null for upload sharing.",
        ),
        sa.Column(
            "share_token",
            sa.String(length=255),
            nullable=False,
            comment="Secure unique token key identifying the share",
        ),
        sa.Column(
            "share_type",
            share_type_enum,
            nullable=False,
            comment="Authorizations category: Download | Upload",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="True if the share is active and hasn't been manually revoked",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Expiration timestamp. Link is invalid after this UTC time.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the share was manually revoked",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_shared_links_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            ondelete="CASCADE",
            name="fk_shared_links_file_id_files",
        ),
        sa.UniqueConstraint("share_token", name="uq_shared_links_share_token"),
        comment="Tracks sharing metadata for S3 pre-signed URLs generated within CloudVault",
    )

    # Indexes
    op.create_index("ix_shared_links_user_id", "shared_links", ["user_id"], unique=False)
    op.create_index("ix_shared_links_file_id", "shared_links", ["file_id"], unique=False)
    op.create_index("ix_shared_links_share_token", "shared_links", ["share_token"], unique=False)


def downgrade() -> None:
    """Drop the shared_links table."""
    op.drop_index("ix_shared_links_share_token", table_name="shared_links")
    op.drop_index("ix_shared_links_file_id", table_name="shared_links")
    op.drop_index("ix_shared_links_user_id", table_name="shared_links")
    op.drop_table("shared_links")

    # Drop the enum type
    share_type_enum = sa.Enum("Download", "Upload", name="share_type_enum")
    share_type_enum.drop(op.get_bind(), checkfirst=True)
