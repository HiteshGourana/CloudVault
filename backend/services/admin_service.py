"""
backend/services/admin_service.py
──────────────────────────────────
Administration Dashboard Service.

Provides metrics and reports for system administrators.
"""

from typing import Any, List
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.aws_account import AWSAccount
from backend.models.bucket import Bucket
from backend.models.file import File
from backend.models.user import User
from backend.schemas.enterprise import AdminOverviewResponse, AdminRecentAWSConnection


class AdminService:
    """Computes global aggregates across all users. Enforces admin-only access."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        
        # Enforce admin constraints at service boundary
        if not self._user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Administrator privileges required.",
            )

    def get_admin_dashboard(self) -> AdminOverviewResponse:
        """Gathers global database statistics and recent registrations/connections."""
        # Counts
        total_users = self._db.query(func.count(User.id)).scalar() or 0
        total_aws = self._db.query(func.count(AWSAccount.id)).scalar() or 0
        total_buckets = self._db.query(func.count(Bucket.id)).scalar() or 0
        total_files = self._db.query(func.count(File.id)).filter(File.is_deleted == False).scalar() or 0
        total_storage = (
            self._db.query(func.sum(File.size_bytes))
            .filter(File.is_deleted == False)
            .scalar() or 0
        )

        # Recent registrations (up to 10)
        recent_users = (
            self._db.query(User)
            .order_by(User.created_at.desc())
            .limit(10)
            .all()
        )
        recent_regs = [
            {
                "user_id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "created_at": u.created_at,
            }
            for u in recent_users
        ]

        # Recent AWS connections (up to 10)
        recent_aws_records = (
            self._db.query(AWSAccount)
            .order_by(AWSAccount.created_at.desc())
            .limit(10)
            .all()
        )
        recent_connections = [
            AdminRecentAWSConnection(
                user_id=acc.user_id,
                user_email=acc.user.email if acc.user else "unknown",
                aws_account_id=acc.aws_account_id,
                region=acc.region,
                connected_at=acc.created_at,
            )
            for acc in recent_aws_records
        ]

        return AdminOverviewResponse(
            total_users=total_users,
            connected_aws_accounts=total_aws,
            total_buckets=total_buckets,
            total_files=total_files,
            total_storage_bytes=total_storage,
            recent_registrations=recent_regs,
            recent_aws_connections=recent_connections,
        )
