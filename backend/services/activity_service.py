"""
backend/services/activity_service.py
────────────────────────────────────
Activity Logs & Audit Trail Service.

Tracks user operations, records them in an immutable activity_logs table,
and provides filtering and paginated lookups.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models.activity_log import ActivityLog
from backend.models.user import User
from backend.schemas.enterprise import ActivityLogListResponse, ActivityLogResponse


class ActivityService:
    """Provides methods for registering audit records and filtering historical user logs."""

    def __init__(self, db: Session, current_user: Optional[User] = None) -> None:
        self._db = db
        self._user = current_user

    @staticmethod
    def log_activity(
        db: Session,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        status_code: str = "success",
        message: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ActivityLog:
        """
        Creates and commits an immutable log entry.
        
        Can be invoked statically from any service layer.
        """
        try:
            log_record = ActivityLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status_code,
                message=message,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=datetime.now(timezone.utc),
            )
            db.add(log_record)
            db.commit()
            db.refresh(log_record)
            
            # Write a structured application trace log
            logger.info(
                "Audit Log Registered | action='{}' user_id={} status={} message='{}'",
                action, str(user_id), status_code, message
            )
            return log_record
            
        except Exception as exc:
            db.rollback()
            logger.error("Failed to commit audit activity log entry: {}", str(exc))
            raise RuntimeError("Database logging failure.")

    def get_log_by_id(self, log_id: uuid.UUID) -> ActivityLog:
        """Retrieves individual log record. Admin users can view any log; normal users can only view their own."""
        if not self._user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        log_record = self._db.get(ActivityLog, log_id)
        if not log_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity log not found.",
            )

        if not self._user.is_admin and log_record.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to view this activity log.",
            )

        return log_record

    def search_logs(
        self,
        *,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        status_filter: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ActivityLogListResponse:
        """
        Retrieves paginated, filtered audit logs.
        Normal users are scoped to their own logs; admin users can query globally.
        """
        if not self._user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        query = self._db.query(ActivityLog)

        # Scoping
        if not self._user.is_admin:
            query = query.filter(ActivityLog.user_id == self._user.id)

        # Apply Filters
        if action:
            query = query.filter(ActivityLog.action.ilike(f"%{action}%"))
        if resource_type:
            query = query.filter(ActivityLog.resource_type == resource_type)
        if status_filter:
            query = query.filter(ActivityLog.status == status_filter)
        if start_date:
            query = query.filter(ActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(ActivityLog.created_at <= end_date)

        # Counts
        total_items = query.count()
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1

        # Pagination & Execution
        offset = (page - 1) * page_size
        records = (
            query.order_by(ActivityLog.created_at.desc())
            .limit(page_size)
            .offset(offset)
            .all()
        )

        return ActivityLogListResponse(
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_items=total_items,
            logs=[ActivityLogResponse.model_validate(r) for r in records],
        )
