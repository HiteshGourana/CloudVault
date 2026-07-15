"""create_users_table

Revision ID: 001_create_users_table
Revises:
Create Date: 2026-06-29

Sprint 1 — Authentication Module

Creates the `users` table with:
  - UUID primary key
  - email (unique, indexed)
  - full_name, password_hash
  - is_active boolean with server default
  - timezone-aware created_at, updated_at
  - Named indexes for fast login lookups and active-user filters
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_create_users_table"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the users table."""
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 - unique user identifier",
        ),
        sa.Column(
            "full_name",
            sa.String(length=255),
            nullable=False,
            comment="User's display name (2-255 characters)",
        ),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
            comment="Unique lowercase email - used as login identifier",
        ),
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
            comment="bcrypt hash - NEVER store plain-text password here",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="False = account suspended; active users can log in",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Account creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last modification timestamp - auto-updated on every UPDATE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        comment="Registered CloudVault user accounts",
    )

    # Named indexes — allow clean up() and down() in future migrations
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)


def downgrade() -> None:
    """Drop the users table and all associated indexes."""
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
