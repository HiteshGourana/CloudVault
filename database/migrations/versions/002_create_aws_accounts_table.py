"""create_aws_accounts_table

Revision ID: 002_create_aws_accounts_table
Revises: 001_create_users_table
Create Date: 2026-06-29

Sprint 2 — AWS Account Connection

Creates the `aws_accounts` table with:
  - UUID primary key
  - user_id FK → users.id with CASCADE DELETE
  - UNIQUE constraint on user_id (one connection per user)
  - AWS identity fields (account_id, iam_arn, iam_user_name)
  - Encrypted credential storage (access_key_id plain, secret_access_key Fernet-encrypted)
  - is_connected boolean with server default
  - timezone-aware connected_at and updated_at

Rollback:
  alembic downgrade -1
  This drops the aws_accounts table and all its indexes.
  Users table is NOT affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_create_aws_accounts_table"
down_revision: Union[str, None] = "001_create_users_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the aws_accounts table."""
    op.create_table(
        "aws_accounts",

        # ── Primary Key ───────────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — unique record identifier",
        ),

        # ── Foreign Key ───────────────────────────────────────────────────────
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Owning user — CASCADE DELETE removes this row when user is deleted",
        ),

        # ── AWS Identity ──────────────────────────────────────────────────────
        sa.Column(
            "aws_account_id",
            sa.String(length=20),
            nullable=False,
            comment="12-digit AWS account ID from STS GetCallerIdentity",
        ),
        sa.Column(
            "iam_arn",
            sa.String(length=2048),
            nullable=False,
            comment="Full IAM ARN returned by STS",
        ),
        sa.Column(
            "iam_user_name",
            sa.String(length=128),
            nullable=True,
            comment="IAM username — null for root or role credentials",
        ),

        # ── Connection Settings ───────────────────────────────────────────────
        sa.Column(
            "region",
            sa.String(length=32),
            nullable=False,
            comment="AWS region used for the STS verification call",
        ),

        # ── Credentials ───────────────────────────────────────────────────────
        sa.Column(
            "access_key_id",
            sa.String(length=128),
            nullable=False,
            comment="AWS access key ID — not sensitive, returned in API responses",
        ),
        sa.Column(
            "secret_access_key_encrypted",
            sa.String(length=512),
            nullable=False,
            comment=(
                "Fernet-encrypted secret access key. "
                "NEVER returned in API responses. "
                "PRODUCTION: replace with AWS Secrets Manager reference."
            ),
        ),

        # ── Status ────────────────────────────────────────────────────────────
        sa.Column(
            "is_connected",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="True = credentials verified and active",
        ),

        # ── Timestamps ────────────────────────────────────────────────────────
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last successful credential verification time (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last row modification time (UTC)",
        ),

        # ── Constraints ───────────────────────────────────────────────────────
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_aws_accounts_user_id_users",
        ),
        sa.UniqueConstraint("user_id", name="uq_aws_accounts_user_id"),

        comment="Connected AWS account credentials for each CloudVault user",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_aws_accounts_user_id", "aws_accounts", ["user_id"], unique=False)
    op.create_index("ix_aws_accounts_aws_account_id", "aws_accounts", ["aws_account_id"], unique=False)


def downgrade() -> None:
    """Drop the aws_accounts table."""
    op.drop_index("ix_aws_accounts_aws_account_id", table_name="aws_accounts")
    op.drop_index("ix_aws_accounts_user_id", table_name="aws_accounts")
    op.drop_table("aws_accounts")
