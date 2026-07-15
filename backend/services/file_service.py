"""
backend/services/file_service.py
────────────────────────────────
Service layer for File Metadata Management.
"""

from datetime import datetime, timezone
import mimetypes
import os
import uuid
from typing import Any, Optional, Sequence
import boto3
import botocore.exceptions
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.file import File, UploadStatus
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.folder_repo import FolderRepository
from backend.utils.encryption import CredentialManager
from backend.schemas.file import (
    CategorySummary,
    FileCreateMetadata,
    FileListResponse,
    FileMetadataResponse,
    FileMove,
    FileRename,
    FileTypesResponse,
)

# ── File Extension Categorization Maps ────────────────────────────────────────
_CATEGORY_GROUPS = {
    "PDF": {".pdf"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".tiff", ".ico"},
    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"},
    "Audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"},
    "Archives": {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".tgz"},
    "Documents": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".md", ".pdf", ".rtf", ".odt"},
}


def get_category_for_extension(ext: str) -> str:
    """Maps a lowercased extension (e.g. '.pdf') to its category group."""
    cleaned_ext = ext.strip().lower()
    
    # Check groups
    # Note: PDF is included in Documents in instructions, but instructions list PDF and Documents separately.
    # Grouped categories: PDF, Images, Videos, Audio, Archives, Documents, Others.
    # Let's map .pdf to "PDF", and doc/docx etc. to "Documents".
    if cleaned_ext == ".pdf":
        return "PDF"
        
    for cat, extensions in _CATEGORY_GROUPS.items():
        if cleaned_ext in extensions:
            return cat
            
    return "Others"


class FileService:
    """Manages file metadata lifecycles, validation, filtering, sorting, and pagination."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._file_repo = FileRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._folder_repo = FolderRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_user_aws_account_id(self) -> Optional[uuid.UUID]:
        """Returns the UUID of the user's connected AWS account, or None."""
        account = self._aws_repo.get_by_user_id(self._user.id)
        return account.id if account else None

    def _is_bucket_owned_by_user(self, bucket) -> bool:
        """Check bucket ownership via aws_account_id (more reliable than user_id alone)."""
        if bucket.user_id == self._user.id:
            return True
        # Fallback: check if the bucket's aws_account belongs to this user
        account_id = self._get_user_aws_account_id()
        if account_id and bucket.aws_account_id == account_id:
            return True
        return False

    def _verify_bucket_and_folder(self, bucket_name: str, folder_id: Optional[uuid.UUID]) -> tuple[Any, Optional[Any]]:
        """Verifies bucket and folder existence and user ownership."""
        bucket = self._bucket_repo.get_by_name(bucket_name)
        if not bucket or not self._is_bucket_owned_by_user(bucket):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' not found or not accessible by you.",
            )

        folder = None
        if folder_id:
            folder = self._folder_repo.get_by_id(folder_id)
            if not folder or folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified parent folder not found in this bucket.",
                )
        return bucket, folder

    def _sync_s3_objects(self, bucket, aws_account) -> int:
        """
        Scan S3 objects in the bucket and auto-register any files not yet in the
        CloudVault database. Files uploaded directly to S3 (bypassing CloudVault
        upload flow) will appear in the file explorer after sync.

        Returns:
            Number of newly imported file records.
        """
        try:
            secret_key = CredentialManager.decrypt(aws_account.secret_access_key_encrypted)
            session = boto3.Session(
                aws_access_key_id=aws_account.access_key_id,
                aws_secret_access_key=secret_key,
                region_name=bucket.region,
            )
            s3 = session.client("s3")

            # Build a set of all s3_keys already tracked in the DB for this bucket
            existing_keys = {
                row[0]
                for row in self._db.query(File.s3_key)
                .filter(File.bucket_id == bucket.id, File.is_deleted == False)
                .all()
            }

            imported = 0
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket.bucket_name)

            for page in pages:
                for obj in page.get("Contents", []):
                    key: str = obj["Key"]

                    # Skip folder placeholder objects (keys ending with '/')
                    if key.endswith("/"):
                        continue

                    # Skip if already registered
                    if key in existing_keys:
                        continue

                    # Parse file name and extension from the S3 key
                    file_name = os.path.basename(key)
                    if not file_name:
                        continue

                    _, ext = os.path.splitext(file_name.lower())
                    if not ext:
                        ext = ".bin"

                    detected_mime, _ = mimetypes.guess_type(file_name)
                    mime = detected_mime or "application/octet-stream"
                    size_bytes = obj.get("Size", 0)

                    try:
                        file_record = self._file_repo.create(
                            bucket_id=bucket.id,
                            folder_id=None,  # Root-level for externally uploaded files
                            file_name=file_name,
                            original_file_name=file_name,
                            extension=ext,
                            mime_type=mime,
                            size_bytes=size_bytes,
                            s3_key=key,
                        )
                        # Mark as Completed since it already exists in S3
                        file_record.upload_status = UploadStatus.COMPLETED.value
                        self._db.commit()
                        existing_keys.add(key)
                        imported += 1
                    except Exception as insert_err:
                        self._db.rollback()
                        logger.debug("Skipped S3 key '{}' during sync: {}", key, str(insert_err))

            if imported > 0:
                logger.info(
                    "S3 sync imported {} new file(s) from bucket '{}' | user_id={}",
                    imported, bucket.bucket_name, str(self._user.id),
                )
            return imported

        except botocore.exceptions.ClientError as e:
            logger.warning(
                "S3 sync skipped for bucket '{}' — AWS error: {}",
                bucket.bucket_name, str(e),
            )
            return 0
        except Exception as e:
            logger.warning(
                "S3 sync error for bucket '{}': {}",
                bucket.bucket_name, str(e),
            )
            return 0



    # ── Create File Metadata ──────────────────────────────────────────────────

    def create_metadata(self, data: FileCreateMetadata) -> File:
        """
        Creates file metadata:
          1. Validates filename and extension presence.
          2. Verifies bucket and folder ownership/existence.
          3. Checks for filename collisions inside the target directory.
          4. Automatically detects extension and mime_type.
          5. Generates the target S3 key based on folder hierarchy prefix.
          6. Persists metadata record with PENDING upload status.
        """
        # Filename validation
        name = data.file_name.strip()
        if len(name) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot exceed 255 characters.",
            )

        # Detect extension
        _, ext = os.path.splitext(name.lower())
        if not ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename must include a valid extension (e.g. '.txt').",
            )

        # Validate bucket/folder
        bucket, folder = self._verify_bucket_and_folder(data.bucket_name, data.folder_id)

        # Check duplicate name collision in target folder (excludes deleted)
        if self._file_repo.exists_in_folder(bucket.id, data.folder_id, name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{name}' already exists in this folder directory.",
            )

        # Detect Mime type if unknown
        detected_mime, _ = mimetypes.guess_type(name)
        mime = data.mime_type or detected_mime or "application/octet-stream"

        # Generate S3 key prefix path
        folder_prefix = folder.full_path if folder else ""
        s3_key = f"{folder_prefix}{name}"

        file_record = self._file_repo.create(
            bucket_id=bucket.id,
            folder_id=data.folder_id,
            file_name=name,
            original_file_name=name,
            extension=ext,
            mime_type=mime,
            size_bytes=data.size_bytes,
            s3_key=s3_key,
        )

        logger.success(
            "File metadata created | name={} bucket={} s3_key={} size={} user_id={}",
            name, bucket.bucket_name, s3_key, data.size_bytes, str(self._user.id)
        )
        return file_record

    # ── Get File Metadata ─────────────────────────────────────────────────────

    def get_metadata(self, file_id: uuid.UUID) -> File:
        """Fetch file metadata by its UUID. Raises 404 if file is not found or is soft-deleted."""
        file_record = self._file_repo.get_by_id(file_id)
        if not file_record or file_record.bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File metadata not found.",
            )
            
        if file_record.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File has been deleted.",
            )
            
        return file_record

    # ── List Files Paginated ──────────────────────────────────────────────────

    def list_files(
        self,
        bucket_name: str,
        folder_id: Optional[uuid.UUID] = None,
        filter_root: bool = False,
        extension: Optional[str] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> FileListResponse:
        """List files metadata with sorting, filtering, and pagination support."""
        # Find bucket and verify ownership
        bucket = self._bucket_repo.get_by_name(bucket_name)
        if not bucket or not self._is_bucket_owned_by_user(bucket):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' not found.",
            )

        # Validate folder if passed
        if folder_id:
            folder = self._folder_repo.get_by_id(folder_id)
            if not folder or folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found.",
                )

        # Pull paginated files
        files, total_items = self._file_repo.list_files_paginated(
            bucket_id=bucket.id,
            folder_id=folder_id,
            filter_root=filter_root,
            extension=extension,
            status_filter=status_filter,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Calculate pages
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1

        return FileListResponse(
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_items=total_items,
            files=[FileMetadataResponse.model_validate(f) for f in files],
        )

    # ── Rename File Metadata ──────────────────────────────────────────────────

    def rename_metadata(self, file_id: uuid.UUID, data: FileRename) -> File:
        """
        Renames file metadata in the database:
          - Verifies file belongs to authenticated user and is not deleted.
          - Enforces identical extensions during rename.
          - Validates filename format & duplicate sibling names check.
          - Does NOT rename S3 object.
        """
        file_record = self.get_metadata(file_id)
        new_name = data.new_file_name.strip()

        if len(new_name) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot exceed 255 characters.",
            )

        # Enforce extension match
        _, old_ext = os.path.splitext(file_record.file_name.lower())
        _, new_ext = os.path.splitext(new_name.lower())

        if old_ext != new_ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change file extension during rename. Extension must remain '{old_ext}'.",
            )

        # Sibling duplicate collision check
        if self._file_repo.exists_in_folder(file_record.bucket_id, file_record.folder_id, new_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{new_name}' already exists in this folder directory.",
            )

        file_record.file_name = new_name
        self._file_repo.update(file_record)

        logger.success(
            "File metadata renamed | file_id={} old_name={} new_name={} user_id={}",
            str(file_id), file_record.original_file_name, new_name, str(self._user.id)
        )
        return file_record

    # ── Move File Metadata ────────────────────────────────────────────────────

    def move_metadata(self, file_id: uuid.UUID, data: FileMove) -> File:
        """
        Moves file metadata to another parent directory.
        Checks for path collisions at the destination.
        """
        file_record = self.get_metadata(file_id)

        if file_record.folder_id == data.new_folder_id:
            return file_record

        # Validate target folder
        if data.new_folder_id:
            target_folder = self._folder_repo.get_by_id(data.new_folder_id)
            if not target_folder or target_folder.bucket_id != file_record.bucket_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target destination folder not found in this bucket.",
                )

        # Sibling duplication check at target destination
        if self._file_repo.exists_in_folder(file_record.bucket_id, data.new_folder_id, file_record.file_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{file_record.file_name}' already exists in the target folder directory.",
            )

        file_record.folder_id = data.new_folder_id
        # Note: Do not update s3_key since the S3 object location wasn't changed.
        # It's an internal logical move in this sprint.
        self._file_repo.update(file_record)

        logger.success(
            "File metadata moved | file_id={} file_name={} new_folder_id={} user_id={}",
            str(file_id), file_record.file_name, str(data.new_folder_id), str(self._user.id)
        )
        return file_record

    # ── Soft Delete Metadata ──────────────────────────────────────────────────

    def delete_metadata(self, file_id: uuid.UUID) -> None:
        """
        Soft deletes the file metadata by setting is_deleted = True.
        Does NOT execute S3 DeleteObject.
        """
        file_record = self.get_metadata(file_id)

        file_record.upload_status = UploadStatus.DELETED.value
        file_record.is_deleted = True
        file_record.deleted_at = datetime.now(timezone.utc)
        self._file_repo.update(file_record)

        logger.info(
            "File metadata soft deleted | file_id={} file_name={} user_id={}",
            str(file_id), file_record.file_name, str(self._user.id)
        )

    # ── Get File Types Aggregate Summaries ────────────────────────────────────

    def get_grouped_file_types(self) -> FileTypesResponse:
        """Computes aggregate totals (counts, total size) by categories."""
        summaries = self._file_repo.get_user_file_types_summary(self._user.id)

        # Initialise empty categories mapping
        categories = {
            "PDF": CategorySummary(count=0, total_size_bytes=0),
            "Images": CategorySummary(count=0, total_size_bytes=0),
            "Videos": CategorySummary(count=0, total_size_bytes=0),
            "Audio": CategorySummary(count=0, total_size_bytes=0),
            "Archives": CategorySummary(count=0, total_size_bytes=0),
            "Documents": CategorySummary(count=0, total_size_bytes=0),
            "Others": CategorySummary(count=0, total_size_bytes=0),
        }

        for ext, count, total_size in summaries:
            cat = get_category_for_extension(ext)
            size = int(total_size) if total_size else 0
            
            categories[cat].count += count
            categories[cat].total_size_bytes += size

        return FileTypesResponse(categories=categories)
