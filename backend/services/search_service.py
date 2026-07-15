"""
backend/services/search_service.py
──────────────────────────────────
Unified Enterprise Search Service.

Allows global keywords-based searches across connected Buckets, Folders,
Files, and Shared Links, using database indexes to optimize query performance.
"""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models.bucket import Bucket
from backend.models.file import File, UploadStatus
from backend.models.folder import Folder
from backend.models.shared_link import SharedLink
from backend.models.user import User
from backend.schemas.bucket import BucketResponse
from backend.schemas.file import FileMetadataResponse
from backend.schemas.folder import FolderResponse
from backend.schemas.share import ShareResponse
from backend.schemas.enterprise import UnifiedSearchResponse


class SearchService:
    """Orchestrates unified lookup queries matching keyword filters."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user

    def execute_search(
        self,
        *,
        keyword: Optional[str] = None,
        bucket_id: Optional[uuid.UUID] = None,
        folder_id: Optional[uuid.UUID] = None,
        extension: Optional[str] = None,
        status_filter: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> UnifiedSearchResponse:
        """
        Queries all tables sequentially using index-backed fields.
        Returns a single merged response.
        """
        # Clean keyword
        kw = keyword.strip() if keyword else ""

        # ── 1. Search Buckets ─────────────────────────────────────────────────
        bucket_query = self._db.query(Bucket).filter(Bucket.user_id == self._user.id)
        if kw:
            bucket_query = bucket_query.filter(Bucket.bucket_name.ilike(f"%{kw}%"))
        if bucket_id:
            bucket_query = bucket_query.filter(Bucket.id == bucket_id)
        if start_date:
            bucket_query = bucket_query.filter(Bucket.created_at >= start_date)
        if end_date:
            bucket_query = bucket_query.filter(Bucket.created_at <= end_date)
            
        buckets = bucket_query.all()

        # ── 2. Search Folders ─────────────────────────────────────────────────
        folder_query = self._db.query(Folder).join(Bucket, Folder.bucket_id == Bucket.id).filter(
            Bucket.user_id == self._user.id
        )
        if kw:
            folder_query = folder_query.filter(Folder.folder_name.ilike(f"%{kw}%"))
        if bucket_id:
            folder_query = folder_query.filter(Folder.bucket_id == bucket_id)
        if folder_id:
            # Sibling folders search
            folder_query = folder_query.filter(Folder.parent_folder_id == folder_id)
        if start_date:
            folder_query = folder_query.filter(Folder.created_at >= start_date)
        if end_date:
            folder_query = folder_query.filter(Folder.created_at <= end_date)
            
        folders = folder_query.all()

        # ── 3. Search Files ───────────────────────────────────────────────────
        file_query = self._db.query(File).join(Bucket, File.bucket_id == Bucket.id).filter(
            Bucket.user_id == self._user.id,
            File.is_deleted == False,
        )
        if kw:
            file_query = file_query.filter(File.file_name.ilike(f"%{kw}%"))
        if bucket_id:
            file_query = file_query.filter(File.bucket_id == bucket_id)
        if folder_id:
            file_query = file_query.filter(File.folder_id == folder_id)
        if extension:
            ext = extension.strip().lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            file_query = file_query.filter(File.extension == ext)
        if status_filter:
            file_query = file_query.filter(File.upload_status == status_filter)
        if start_date:
            file_query = file_query.filter(File.created_at >= start_date)
        if end_date:
            file_query = file_query.filter(File.created_at <= end_date)
            
        files = file_query.all()

        # ── 4. Search Shared Links ────────────────────────────────────────────
        share_query = self._db.query(SharedLink).filter(SharedLink.user_id == self._user.id)
        if kw:
            # Query shared link token or file name match
            share_query = (
                share_query.outerjoin(File, SharedLink.file_id == File.id)
                .filter(
                    or_(
                        SharedLink.share_token.ilike(f"%{kw}%"),
                        File.file_name.ilike(f"%{kw}%"),
                    )
                )
            )
        if start_date:
            share_query = share_query.filter(SharedLink.created_at >= start_date)
        if end_date:
            share_query = share_query.filter(SharedLink.created_at <= end_date)
            
        shares = share_query.all()

        # Build Response wrappers
        # Convert ORM instances to responses. Exclude transient fields like presigned_url.
        shares_response = []
        for s in shares:
            res = ShareResponse.model_validate(s)
            res.presigned_url = ""
            shares_response.append(res)

        return UnifiedSearchResponse(
            buckets=[BucketResponse.model_validate(b) for b in buckets],
            folders=[FolderResponse.model_validate(f) for f in folders],
            files=[FileMetadataResponse.model_validate(f) for f in files],
            shares=shares_response,
        )
