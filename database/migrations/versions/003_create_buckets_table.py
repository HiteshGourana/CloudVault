"""create_buckets_table

Revision ID: 003_create_buckets_table
Revises: 002_create_aws_accounts_table
Create Date: 2026-06-29

Sprint 3 — S3 Bucket Management

Creates the `buckets` table with:
  - UUID primary key
  - user_id FK → users.id (CASCADE DELETE)
  - aws_account_id FK → aws_accounts.id (CASCADE DELETE)
  - bucket_name (unique, indexed)
  - region, creation_date, bucket_type (Enum), versioning_enabled, encryption_enabled
  - created_at, updated_at timestamps (UTC)
  - Named indexes for efficient querying
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_create_buckets_table"
down_revision: Union[str, None] = "002_create_aws_accounts_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the buckets table."""
    # Define the bucket type enum type for postgres
    bucket_type_enum = sa.Enum("private", "public", "unknown", name="bucket_type_enum")
    
    op.create_table(
        "buckets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — internal record identifier",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Owning application user — CASCADE DELETE",
        ),
        sa.Column(
            "aws_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Connected AWS account record (aws_accounts.id UUID) — CASCADE DELETE",
        ),
        sa.Column(
            "bucket_name",
            sa.String(length=63),
            nullable=False,
            comment="S3 bucket name — globally unique across all AWS accounts",
        ),
        sa.Column(
            "region",
            sa.String(length=32),
            nullable=False,
            comment="AWS region where the bucket resides (e.g., us-east-1)",
        ),
        sa.Column(
            "creation_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Bucket creation timestamp from AWS — may differ from created_at",
        ),
        sa.Column(
            "bucket_type",
            bucket_type_enum,
            server_default="private",
            nullable=False,
            comment="Visibility: private | public | unknown (from public access block settings)",
        ),
        sa.Column(
            "versioning_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True if S3 versioning is Enabled",
        ),
        sa.Column(
            "encryption_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True if server-side encryption is configured on the bucket",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When this CloudVault record was created (NOT the S3 bucket creation time)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When this CloudVault record was last updated",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_buckets_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["aws_account_id"],
            ["aws_accounts.id"],
            ondelete="CASCADE",
            name="fk_buckets_aws_account_id_aws_accounts",
        ),
        sa.UniqueConstraint("bucket_name", name="uq_buckets_bucket_name"),
        comment="Tracks S3 bucket metadata for CloudVault-managed and discovered buckets",
    )

    # Indexes
    op.create_index("ix_buckets_user_id", "buckets", ["user_id"], unique=False)
    op.create_index("ix_buckets_aws_account_id", "buckets", ["aws_account_id"], unique=False)
    op.create_index("ix_buckets_bucket_name", "buckets", ["bucket_name"], unique=False)
    op.create_index("ix_buckets_region", "buckets", ["region"], unique=False)


def downgrade() -> None:
    """Drop the buckets table."""
    op.drop_index("ix_buckets_region", table_name="buckets")
    op.drop_index("ix_buckets_bucket_name", table_name="buckets")
    op.drop_index("ix_buckets_aws_account_id", table_name="buckets")
    op.drop_index("ix_buckets_user_id", table_name="buckets")
    op.drop_table("buckets")
    
    # Drop the enum type
    bucket_type_enum = sa.Enum("private", "public", "unknown", name="bucket_type_enum")
    bucket_type_enum.drop(op.get_bind(), checkfirst=True)
