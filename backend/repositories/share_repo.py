"""
backend/repositories/share_repo.py
──────────────────────────────────
Data access layer for the shared_links table.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.shared_link import SharedLink


class ShareRepository:
    """Encapsulates all database queries and writes for the shared_links table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, share_id: uuid.UUID) -> SharedLink | None:
        """Fetch share link by its UUID primary key."""
        return self._db.get(SharedLink, share_id)

    def get_by_token(self, token: str) -> SharedLink | None:
        """Fetch share link record using its unique share token."""
        return (
            self._db.query(SharedLink)
            .filter(SharedLink.share_token == token)
            .first()
        )

    def get_active_shares_by_user(self, user_id: uuid.UUID) -> List[SharedLink]:
        """
        Returns all non-revoked, non-expired share link records created by a user.
        """
        now = datetime.now(timezone.utc)
        return (
            self._db.query(SharedLink)
            .filter(
                SharedLink.user_id == user_id,
                SharedLink.is_active == True,
                SharedLink.expires_at > now,
            )
            .order_by(SharedLink.created_at.desc())
            .all()
        )

    def get_history_by_user(self, user_id: uuid.UUID) -> List[SharedLink]:
        """Returns all share link records created by a user (active, expired, and revoked)."""
        return (
            self._db.query(SharedLink)
            .filter(SharedLink.user_id == user_id)
            .order_by(SharedLink.created_at.desc())
            .all()
        )

    def create(
        self,
        *,
        user_id: uuid.UUID,
        file_id: Optional[uuid.UUID],
        share_type: str,
        expires_at: datetime,
    ) -> SharedLink:
        """Insert a new shared link metadata record."""
        # Note: share_token is auto-generated as a UUID string by default in ORM model
        share = SharedLink(
            user_id=user_id,
            file_id=file_id,
            share_type=share_type,
            expires_at=expires_at,
            is_active=True,
        )
        self._db.add(share)
        self._db.commit()
        self._db.refresh(share)
        return share

    def update(self, share: SharedLink) -> SharedLink:
        """Commit updates to a shared link record."""
        self._db.commit()
        self._db.refresh(share)
        return share
