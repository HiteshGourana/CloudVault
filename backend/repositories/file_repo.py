"""
backend/repositories/file_repo.py
─────────────────────────────────
Data access layer for the files table.
"""

import uuid
from typing import Optional, Sequence
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from backend.models.file import File, UploadStatus


class FileRepository:
    """Encapsulates all database query and write operations for the files table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, file_id: uuid.UUID) -> File | None:
        """Fetch file by its UUID primary key. Retains soft-deleted files in direct fetches."""
        return self._db.get(File, file_id)

    def exists_in_folder(self, bucket_id: uuid.UUID, folder_id: Optional[uuid.UUID], file_name: str) -> bool:
        """
        Check if a file with the same name already exists in the same folder.
        Excludes soft-deleted files from conflict checking.
        """
        return (
            self._db.query(File.id)
            .filter(
                File.bucket_id == bucket_id,
                File.folder_id == folder_id,
                File.file_name == file_name,
                File.upload_status != UploadStatus.DELETED.value,
            )
            .first()
        ) is not None

    def create(
        self,
        *,
        bucket_id: uuid.UUID,
        folder_id: Optional[uuid.UUID],
        file_name: str,
        original_file_name: str,
        extension: str,
        mime_type: str,
        size_bytes: int,
        s3_key: str,
        storage_class: str = "STANDARD",
    ) -> File:
        """Insert a new file metadata record."""
        file_record = File(
            bucket_id=bucket_id,
            folder_id=folder_id,
            file_name=file_name,
            original_file_name=original_file_name,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            s3_key=s3_key,
            storage_class=storage_class,
            upload_status=UploadStatus.PENDING.value,
        )
        self._db.add(file_record)
        self._db.commit()
        self._db.refresh(file_record)
        return file_record

    def update(self, file_record: File) -> File:
        """Commit changes to a file metadata record."""
        self._db.commit()
        self._db.refresh(file_record)
        return file_record

    def list_files_paginated(
        self,
        bucket_id: uuid.UUID,
        folder_id: Optional[uuid.UUID] = None,
        filter_root: bool = False,
        extension: Optional[str] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[Sequence[File], int]:
        """
        Queries, filters, sorts, and paginates files metadata list.
        
        Args:
            bucket_id: The bucket UUID to search within.
            folder_id: Specific folder UUID.
            filter_root: If True, folder_id is explicitly ignored and only folder_id IS NULL is queried.
            extension: Lowercase extension filter (e.g. '.pdf').
            status_filter: Specific upload status filter. If None, excludes UploadStatus.DELETED.
            page: 1-indexed page.
            page_size: number of items per page.
            sort_by: name, date, size, extension.
            sort_order: asc, desc.
            
        Returns:
            Tuple of (list of File, total items count matching filters)
        """
        query = self._db.query(File).filter(File.bucket_id == bucket_id)

        # Folder level filtering
        if filter_root:
            query = query.filter(File.folder_id.is_(None))
        elif folder_id is not None:
            query = query.filter(File.folder_id == folder_id)

        # Extension filtering
        if extension:
            ext = extension.strip().lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            query = query.filter(File.extension == ext)

        # Status filtering
        if status_filter:
            query = query.filter(File.upload_status == status_filter)
        
        # Exclude soft-deleted files by default (unless explicitly filtering for Deleted status)
        if status_filter == UploadStatus.DELETED.value:
            query = query.filter(File.is_deleted == True)
        else:
            query = query.filter(File.is_deleted == False)

        # Get total item count before paginating
        total_items = query.count()

        # Sorting mapping
        sort_field = File.created_at
        if sort_by == "name":
            sort_field = File.file_name
        elif sort_by == "size":
            sort_field = File.size_bytes
        elif sort_by == "extension":
            sort_field = File.extension

        if sort_order == "asc":
            query = query.order_by(sort_field.asc())
        else:
            query = query.order_by(sort_field.desc())

        # Pagination offsets
        offset = (page - 1) * page_size
        files = query.limit(page_size).offset(offset).all()

        return files, total_items

    def get_user_file_types_summary(self, user_id: uuid.UUID) -> list[tuple[str, int, int]]:
        """
        Returns group details of user files by extension categories.
        
        Returns:
            List of tuples: (extension, count, total_size_bytes) for active files owned by the user.
        """
        # Join files with buckets to restrict matching user files
        from backend.models.bucket import Bucket
        return (
            self._db.query(
                File.extension,
                func.count(File.id),
                func.sum(File.size_bytes),
            )
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == user_id,
                File.is_deleted == False,
            )
            .group_by(File.extension)
            .all()
        )
