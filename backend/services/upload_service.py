"""
backend/services/upload_service.py
──────────────────────────────────
Core S3 Upload Engine Service.

Performance optimizations applied:
  - S3 TransferConfig: multipart uploads (≥8 MB chunks), 10 concurrent TCP streams.
  - S3 client cache: boto3 Session/client reused per (user_id, bucket_name).
  - Parallel batch uploads: ThreadPoolExecutor replaces sequential for-loop.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
import boto3
import botocore.exceptions
from boto3.s3.transfer import TransferConfig
from fastapi import HTTPException, UploadFile, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.file import File, UploadStatus
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.folder_repo import FolderRepository
from backend.utils.encryption import CredentialManager
from backend.utils.upload_utils import generate_unique_filename, validate_file_properties

# ── Global In-Memory Progress Cache ───────────────────────────────────────────
# Tracks active upload progress. Cleaned up after upload completes or fails.
UPLOAD_PROGRESS: Dict[uuid.UUID, Dict[str, Any]] = {}

# ── S3 Client Cache ────────────────────────────────────────────────────────────
# Reuses boto3 Session + S3 client per (user_id, bucket_name) to avoid
# re-creating clients on every upload request (significant overhead reduction).
_S3_CLIENT_CACHE: Dict[Tuple[uuid.UUID, str], Any] = {}

# ── S3 Transfer Configuration ──────────────────────────────────────────────────
# Controls multipart upload behaviour for boto3:
#   multipart_threshold : files >= 8 MB are split into parts and uploaded in parallel.
#   multipart_chunksize : each part is 16 MB — fewer round-trips for large files.
#   max_concurrency     : up to 10 simultaneous TCP connections per file transfer.
#   use_threads         : enable threading inside boto3 transfer manager.
S3_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,   # 8 MB
    multipart_chunksize=16 * 1024 * 1024,  # 16 MB
    max_concurrency=10,
    use_threads=True,
)


class UploadProgressCallback:
    """Callback class passed to boto3 to track real-time upload progress."""

    def __init__(self, file_id: uuid.UUID, total_bytes: int) -> None:
        self.file_id = file_id
        self.total_bytes = total_bytes
        self.uploaded_bytes = 0
        
        # Initialise progress entry
        UPLOAD_PROGRESS[self.file_id] = {
            "progress": 0.0,
            "error": None,
        }

    def __call__(self, bytes_amount: int) -> None:
        self.uploaded_bytes += bytes_amount
        if self.total_bytes > 0:
            percentage = (self.uploaded_bytes / self.total_bytes) * 100
            # Cap progress at 99.9% during S3 transfer, set to 100% only after DB update
            UPLOAD_PROGRESS[self.file_id]["progress"] = min(percentage, 99.9)


class UploadService:
    """Orchestrates file checks, duplicate strategies, boto3 streams, and status updates."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._file_repo = FileRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._folder_repo = FolderRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_s3_client_and_bucket(self, bucket_name: str) -> tuple[Any, Any]:
        """Retrieves verified S3 client and local Bucket record.

        The boto3 S3 client is cached per (user_id, bucket_name) to avoid
        the overhead of constructing a new Session + client on every upload.
        """
        aws_account = self._aws_repo.get_by_user_id(self._user.id)
        if not aws_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not connected.",
            )

        bucket = self._bucket_repo.get_by_name(bucket_name)
        # Allow access if bucket is owned by the user OR belongs to the user's connected AWS account
        bucket_accessible = (
            bucket is not None and (
                bucket.user_id == self._user.id or
                bucket.aws_account_id == aws_account.id
            )
        )
        if not bucket_accessible:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' not found or not accessible by you.",
            )

        # Return cached S3 client if available for this (user, bucket) pair
        cache_key: Tuple[uuid.UUID, str] = (self._user.id, bucket_name)
        if cache_key not in _S3_CLIENT_CACHE:
            secret_key = CredentialManager.decrypt(aws_account.secret_access_key_encrypted)
            session = boto3.Session(
                aws_access_key_id=aws_account.access_key_id,
                aws_secret_access_key=secret_key,
                region_name=bucket.region,
            )
            _S3_CLIENT_CACHE[cache_key] = session.client("s3")
            logger.debug("S3 client created and cached for user={} bucket={}", self._user.id, bucket_name)
        else:
            logger.debug("S3 client reused from cache for user={} bucket={}", self._user.id, bucket_name)

        return _S3_CLIENT_CACHE[cache_key], bucket

    def _handle_duplicate_strategy(
        self,
        bucket_id: uuid.UUID,
        folder_id: Optional[uuid.UUID],
        original_name: str,
        strategy: str,
    ) -> tuple[str, Optional[File]]:
        """
        Applies duplication handling strategies.
        
        Strategies:
          - reject    : raises 409 Conflict.
          - overwrite : returns original name and the existing File record.
          - rename    : auto-renames e.g. "resume.pdf" -> "resume(1).pdf".
        """
        exists = self._file_repo.exists_in_folder(bucket_id, folder_id, original_name)
        if not exists:
            return original_name, None

        if strategy == "reject":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{original_name}' already exists in the target directory.",
            )
        elif strategy == "overwrite":
            # Find the existing record to update it
            existing = (
                self._db.query(File)
                .filter(
                    File.bucket_id == bucket_id,
                    File.folder_id == folder_id,
                    File.file_name == original_name,
                    File.upload_status != UploadStatus.DELETED.value,
                )
                .first()
            )
            return original_name, existing
        else:
            # Default strategy: rename
            def exists_callback(name_candidate: str) -> bool:
                return self._file_repo.exists_in_folder(bucket_id, folder_id, name_candidate)

            unique_name = generate_unique_filename(exists_callback, original_name)
            return unique_name, None

    # ── Upload Single File ────────────────────────────────────────────────────

    def upload_file(
        self,
        bucket_name: str,
        folder_id: Optional[uuid.UUID],
        file: UploadFile,
        duplicate_strategy: str = "rename",
    ) -> File:
        """
        Uploads a single file:
          1. Validates properties (blocked extensions, file size, mime).
          2. Verifies bucket and folder details.
          3. Applies duplicate strategy to calculate target name.
          4. Creates pending DB metadata.
          5. Streams content to S3 with progress reporting.
          6. Updates status to Completed (or Failed on errors).
        """
        s3_client, bucket = self._get_s3_client_and_bucket(bucket_name)

        # Get file size (requires seeking file stream)
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0) # Reset stream pointer

        # Validate file properties
        cleaned_name, ext = validate_file_properties(
            filename=file.filename,
            size_bytes=size,
            content_type=file.content_type,
        )

        # Verify parent folder details
        folder = None
        if folder_id:
            folder = self._folder_repo.get_by_id(folder_id)
            if not folder or folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found.",
                )

        # Resolve duplicate name conflicts
        final_name, existing_record = self._handle_duplicate_strategy(
            bucket.id, folder_id, cleaned_name, duplicate_strategy
        )

        # Form S3 Key prefix
        folder_prefix = folder.full_path if folder else ""
        s3_key = f"{folder_prefix}{final_name}"

        # Insert or update metadata as PENDING
        if existing_record:
            file_record = existing_record
            file_record.upload_status = UploadStatus.PENDING.value
            file_record.size_bytes = size
            file_record.mime_type = file.content_type
            file_record.s3_key = s3_key
            self._file_repo.update(file_record)
        else:
            file_record = self._file_repo.create(
                bucket_id=bucket.id,
                folder_id=folder_id,
                file_name=final_name,
                original_file_name=cleaned_name,
                extension=ext,
                mime_type=file.content_type,
                size_bytes=size,
                s3_key=s3_key,
            )

        # Setup Progress tracking
        progress_cb = UploadProgressCallback(file_record.id, size)
        
        # Trigger AWS S3 upload stream
        try:
            file_record.upload_status = UploadStatus.UPLOADING.value
            self._file_repo.update(file_record)
            
            logger.info("Upload started | key={} size={}", s3_key, size)
            
            # Stream content to S3 with multipart + parallel TCP via TransferConfig
            s3_client.upload_fileobj(
                Fileobj=file.file,
                Bucket=bucket.bucket_name,
                Key=s3_key,
                Callback=progress_cb,
                ExtraArgs={"ContentType": file.content_type},
                Config=S3_TRANSFER_CONFIG,
            )
            
            # Success: update DB state to Completed
            file_record.upload_status = UploadStatus.COMPLETED.value
            self._file_repo.update(file_record)
            
            # Force progress to 100%
            UPLOAD_PROGRESS[file_record.id] = {"progress": 100.0, "error": None}
            logger.success("Upload completed | key={}", s3_key)
            
        except botocore.exceptions.ClientError as exc:
            error_msg = str(exc)
            logger.error("AWS S3 upload failed for {}: {}", s3_key, error_msg)
            
            # Fail: update DB state to Failed
            file_record.upload_status = UploadStatus.FAILED.value
            self._file_repo.update(file_record)
            
            UPLOAD_PROGRESS[file_record.id] = {"progress": progress_cb.uploaded_bytes / size * 100, "error": error_msg}
            _raise_for_upload_error(exc)
            
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Unexpected error during S3 upload of {}: {}", s3_key, error_msg)
            
            file_record.upload_status = UploadStatus.FAILED.value
            self._file_repo.update(file_record)
            
            UPLOAD_PROGRESS[file_record.id] = {"progress": progress_cb.uploaded_bytes / size * 100, "error": error_msg}
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload failed: {error_msg}",
            )

        return file_record

    # ── Upload Multiple Files ─────────────────────────────────────────────────

    def upload_multiple_files(
        self,
        bucket_name: str,
        folder_id: Optional[uuid.UUID],
        files: List[UploadFile],
        duplicate_strategy: str = "rename",
        max_workers: int = 5,
    ) -> tuple[list[File], list[str]]:
        """
        Uploads multiple files in parallel using a ThreadPoolExecutor.

        Each file is submitted as an independent task to the thread pool so
        that up to `max_workers` files transfer simultaneously instead of
        waiting for one to finish before starting the next.

        Args:
            max_workers: Maximum number of concurrent upload threads.
                         Capped at min(len(files), max_workers) to avoid
                         spawning unnecessary threads for small batches.
        """
        succeeded: list[File] = []
        failed: list[str] = []

        # Cap workers to actual file count — no point spinning up idle threads
        workers = min(len(files), max_workers)
        logger.info("Parallel multi-upload | files={} workers={}", len(files), workers)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            # Map each future back to its original filename for error reporting
            future_to_name = {
                pool.submit(
                    self.upload_file, bucket_name, folder_id, f, duplicate_strategy
                ): (f.filename or "unknown")
                for f in files
            }

            for future in as_completed(future_to_name):
                filename = future_to_name[future]
                try:
                    file_record = future.result()
                    succeeded.append(file_record)
                except Exception as exc:
                    logger.warning("Parallel upload failed for '{}': {}", filename, str(exc))
                    failed.append(filename)

        return succeeded, failed

    # ── Upload Folder (Preserving hierarchy) ──────────────────────────────────

    def upload_folder(
        self,
        bucket_name: str,
        folder_id: Optional[uuid.UUID],
        files: List[UploadFile],
        relative_paths: List[str],
        duplicate_strategy: str = "rename",
    ) -> tuple[list[File], list[str]]:
        """
        Uploads local directory hierarchies, preserving prefix folders structure:
          1. Verifies bucket and folder constraints.
          2. Parses relative paths to build nested virtual folders.
          3. Creates missing folders (DB and S3 placeholders).
          4. Maps files to the correct subfolders.
          5. Calls upload_file sequentially for each file.
        """
        if len(files) != len(relative_paths):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Files list size does not match relative_paths size.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(bucket_name)
        succeeded: list[File] = []
        failed: list[str] = []

        # Cache of folder IDs to optimize path traversals
        # Key: tuple of folder names path. Value: UUID of folder.
        # Initialize with the initial root/folder_id
        path_cache: dict[tuple[str, ...], Optional[uuid.UUID]] = {}

        for file, rel_path in zip(files, relative_paths):
            try:
                # Clean path separations
                normalized_path = rel_path.replace("\\", "/").strip("/")
                parts = normalized_path.split("/")
                
                if len(parts) <= 1:
                    # File sits directly in target parent folder
                    target_parent_id = folder_id
                else:
                    # Folder hierarchy exists
                    dir_parts = parts[:-1]
                    target_parent_id = self._resolve_nested_folders(
                        bucket=bucket,
                        s3_client=s3_client,
                        parent_id=folder_id,
                        folder_segments=dir_parts,
                        path_cache=path_cache,
                    )
                
                # Upload the file mapping to the resolved subfolder
                file_record = self.upload_file(bucket.bucket_name, target_parent_id, file, duplicate_strategy)
                succeeded.append(file_record)
                
            except Exception as exc:
                logger.warning("Folder item upload failed for '{}': {}", rel_path, str(exc))
                failed.append(rel_path)

        return succeeded, failed

    def _resolve_nested_folders(
        self,
        bucket: Any,
        s3_client: Any,
        parent_id: Optional[uuid.UUID],
        folder_segments: List[str],
        path_cache: dict[tuple[str, ...], Optional[uuid.UUID]],
    ) -> uuid.UUID:
        """
        Recursively resolves or creates nested subfolders in database and S3.
        Returns the leaf folder UUID.
        """
        current_parent_id = parent_id
        accumulated_path: List[str] = []
        
        # Traverse segment by segment
        for segment in folder_segments:
            segment_cleaned = segment.strip()
            if not segment_cleaned:
                continue
            
            accumulated_path.append(segment_cleaned)
            cache_key = tuple(accumulated_path)
            
            # Check cache
            if cache_key in path_cache:
                current_parent_id = path_cache[cache_key]
                continue
                
            # If not in cache, query DB
            # S3 prefix requires prefix ending in /
            parent_prefix = ""
            if current_parent_id:
                p_folder = self._folder_repo.get_by_id(current_parent_id)
                if p_folder:
                    parent_prefix = p_folder.full_path
            
            full_path = f"{parent_prefix}{segment_cleaned}/"
            
            existing_folder = self._folder_repo.get_by_path(bucket.id, full_path)
            if existing_folder:
                current_parent_id = existing_folder.id
            else:
                # Create the missing subfolder
                try:
                    s3_client.put_object(
                        Bucket=bucket.bucket_name,
                        Key=full_path,
                        Body=b"",
                        ContentType="application/x-directory",
                    )
                except Exception as exc:
                    logger.error("Failed to write folder placeholder: {}", str(exc))
                    raise RuntimeError("AWS folder placeholder creation failed.")
                
                new_folder = self._folder_repo.create(
                    bucket_id=bucket.id,
                    parent_folder_id=current_parent_id,
                    folder_name=segment_cleaned,
                    full_path=full_path,
                )
                current_parent_id = new_folder.id
                
            # Cache it
            path_cache[cache_key] = current_parent_id
            
        return current_parent_id

    # ── Get Status ────────────────────────────────────────────────────────────

    def get_upload_status(self, file_id: uuid.UUID) -> dict[str, Any]:
        """Returns the real-time status and progress percentage."""
        file_record = self._file_repo.get_by_id(file_id)
        if not file_record or file_record.bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File metadata record not found.",
            )

        progress = 0.0
        error_msg = None
        
        # Pull from real-time progress cache if active
        if file_id in UPLOAD_PROGRESS:
            progress = UPLOAD_PROGRESS[file_id]["progress"]
            error_msg = UPLOAD_PROGRESS[file_id]["error"]
        elif file_record.upload_status == UploadStatus.COMPLETED.value:
            progress = 100.0
            
        return {
            "file_id": file_id,
            "upload_status": file_record.upload_status,
            "progress_percentage": progress,
            "error_message": error_msg,
        }

    # ── Retry Upload ──────────────────────────────────────────────────────────

    def retry_upload(self, file_id: uuid.UUID) -> dict[str, Any]:
        """
        Retries a failed upload.
        Since HTTP file streams are transient, in this metadata tier we check S3.
        If the file object is already fully present in S3, we update the status to Completed.
        Otherwise, we transition it back to Pending so the client knows it can re-attempt.
        """
        file_record = self._file_repo.get_by_id(file_id)
        if not file_record or file_record.bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File metadata not found.",
            )

        if file_record.upload_status != UploadStatus.FAILED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only uploads in 'Failed' state can be retried.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket.bucket_name)

        # Healing heuristic: check if S3 actually contains the key
        try:
            logger.info("Retry upload initiated for: {}", file_record.s3_key)
            s3_client.head_object(Bucket=bucket.bucket_name, Key=file_record.s3_key)
            
            # File exists in S3! Mark Completed
            file_record.upload_status = UploadStatus.COMPLETED.value
            self._file_repo.update(file_record)
            
            logger.success("Retry completed: File found on S3. Marked as Completed.")
            return {
                "message": "Healed: File was verified successfully on S3. Status upgraded to Completed.",
                "file": file_record,
            }
        except botocore.exceptions.ClientError as exc:
            # File is missing in S3. Transition back to Pending so client can retry upload.
            file_record.upload_status = UploadStatus.PENDING.value
            self._file_repo.update(file_record)
            
            logger.info("File not found on S3. Reset status to Pending for client retry.")
            return {
                "message": "File not found on S3. Reset metadata status to Pending. Please resubmit payload.",
                "file": file_record,
            }


# ─────────────────────────────────────────────────────────────────────────────
# AWS Error Handler Mapping
# ─────────────────────────────────────────────────────────────────────────────

_S3_UPLOAD_ERRORS = {
    "AccessDenied": (status.HTTP_403_FORBIDDEN, "Access denied. Check AWS IAM permissions for S3 PutObject."),
    "NoSuchBucket": (status.HTTP_404_NOT_FOUND, "The target S3 bucket does not exist."),
    "EntityTooLarge": (status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "AWS S3 rejects this file size as too large."),
    "InvalidAccessKeyId": (status.HTTP_401_UNAUTHORIZED, "AWS Access Key is invalid."),
    "SignatureDoesNotMatch": (status.HTTP_401_UNAUTHORIZED, "AWS credentials signature mismatch."),
}


def _raise_for_upload_error(exc: botocore.exceptions.ClientError) -> None:
    """Parses S3 exceptions and returns targeted HTTP Status Codes."""
    code = exc.response.get("Error", {}).get("Code", "Unknown")
    if code in _S3_UPLOAD_ERRORS:
        http_code, msg = _S3_UPLOAD_ERRORS[code]
    else:
        http_code = status.HTTP_400_BAD_REQUEST
        msg = f"S3 Upload failed with error code: {code}"
        
    raise HTTPException(status_code=http_code, detail=msg)
