"""create_enterprise_tables

Revision ID: 008_create_enterprise_tables
Revises: 007_create_shared_links_table
Create Date: 2026-06-29

Sprint 10 — Enterprise Features

Modifications:
  - Adds is_admin column to users table
  - Creates activity_logs table (UUID key, user_id, action, resource details, ip, user_agent, timestamps)
  - Creates notifications table (UUID key, user_id, title, message, notification_type, is_read, timestamps)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_create_enterprise_tables"
down_revision: Union[str, None] = "007_create_shared_links_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply Enterprise database changes."""
    # 1. Update users table with is_admin column
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if user is a system administrator",
        ),
    )

    # 2. Create activity_logs table
    op.create_table(
        "activity_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — unique activity log identifier",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The user who executed the action — CASCADE DELETE",
        ),
        sa.Column(
            "action",
            sa.String(length=127),
            nullable=False,
            comment="Action execution key (e.g. 'User Login', 'Bucket Created')",
        ),
        sa.Column(
            "resource_type",
            sa.String(length=63),
            nullable=False,
            comment="Categorized resource type affected (e.g. 'file', 'bucket', 'user')",
        ),
        sa.Column(
            "resource_id",
            sa.String(length=63),
            nullable=True,
            comment="Identifier key representing the target entity resource",
        ),
        sa.Column(
            "status",
            sa.String(length=63),
            nullable=False,
            comment="Outcome status ('success', 'failure')",
        ),
        sa.Column(
            "message",
            sa.String(length=1024),
            nullable=False,
            comment="Detailed log description description message",
        ),
        sa.Column(
            "ip_address",
            sa.String(length=45),
            nullable=True,
            comment="IP address used (supports IPv4/IPv6 standard max format)",
        ),
        sa.Column(
            "user_agent",
            sa.String(length=512),
            nullable=True,
            comment="User Agent header string of browser client",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Log timestamp — immutable",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_activity_logs_user_id_users",
        ),
        comment="Tracks audit trail logs of user actions within CloudVault",
    )

    # Activity log indexes
    op.create_index("ix_activity_logs_user_id", "activity_logs", ["user_id"], unique=False)
    op.create_index("ix_activity_logs_action", "activity_logs", ["action"], unique=False)
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"], unique=False)
    op.create_index("ix_activity_logs_resource_type", "activity_logs", ["resource_type"], unique=False)

    # 3. Create notifications table
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 — unique notification identifier",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The recipient user UUID — CASCADE DELETE",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
            comment="Short notification title (e.g. 'Upload Failed')",
        ),
        sa.Column(
            "message",
            sa.String(length=1024),
            nullable=False,
            comment="Detailed notification text",
        ),
        sa.Column(
            "notification_type",
            sa.String(length=63),
            nullable=False,
            comment="Alert category",
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True if user has acknowledged the notification",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Timestamp when alert was triggered",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_notifications_user_id_users",
        ),
        comment="System notification alerts targeted for a specific User",
    )

    # Notifications indexes
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"], unique=False)
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)


def downgrade() -> None:
    """Revert Enterprise database changes."""
    # Drop notifications table & indexes
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

    # Drop activity_logs table & indexes
    op.drop_index("ix_activity_logs_resource_type", table_name="activity_logs")
    op.drop_index("ix_activity_logs_created_at", table_name="activity_logs")
    op.drop_index("ix_activity_logs_action", table_name="activity_logs")
    op.drop_index("ix_activity_logs_user_id", table_name="activity_logs")
    op.drop_table("activity_logs")

    # Drop users.is_admin column
    op.drop_column("users", "is_admin")
