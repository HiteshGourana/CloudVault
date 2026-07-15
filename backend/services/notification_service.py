"""
backend/services/notification_service.py
────────────────────────────────────────
Notifications Management Service.

Handles generating alerts (S3 uploads, connection updates, warnings)
and managing read states.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.notification import Notification
from backend.models.user import User
from backend.schemas.enterprise import NotificationListResponse, NotificationResponse


class NotificationService:
    """Manages notifications generation, read statuses, and lists alerts."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user

    @staticmethod
    def create_notification(
        db: Session,
        *,
        user_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str,
    ) -> Notification:
        """
        Creates and commits a new alert notification.
        
        Can be statically triggered by other services during lifecycle events.
        """
        try:
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            
            logger.info("Notification triggered | title='{}' user_id={}", title, str(user_id))
            return notification
            
        except Exception as exc:
            db.rollback()
            logger.error("Failed to commit notification: {}", str(exc))
            raise RuntimeError("Database notification failure.")

    def list_notifications(self) -> NotificationListResponse:
        """Returns unread counts along with list of all alerts for the user."""
        records = (
            self._db.query(Notification)
            .filter(Notification.user_id == self._user.id)
            .order_by(Notification.created_at.desc())
            .all()
        )

        unread_count = sum(1 for n in records if not n.is_read)

        return NotificationListResponse(
            unread_count=unread_count,
            notifications=[NotificationResponse.model_validate(n) for n in records],
        )

    def mark_read(self, notification_id: uuid.UUID) -> NotificationResponse:
        """Marks specific notification as read. Validates ownership."""
        notification = self._db.get(Notification, notification_id)
        if not notification or notification.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        notification.is_read = True
        self._db.commit()
        self._db.refresh(notification)
        
        logger.info("Notification marked read | id={}", str(notification_id))
        return NotificationResponse.model_validate(notification)

    def mark_all_read(self) -> int:
        """Marks all unread alerts of the current user as read. Returns count updated."""
        unread = (
            self._db.query(Notification)
            .filter(Notification.user_id == self._user.id, Notification.is_read == False)
            .all()
        )
        
        count = len(unread)
        for n in unread:
            n.is_read = True
            
        self._db.commit()
        logger.info("All notifications marked read | count={} user_id={}", count, str(self._user.id))
        return count
