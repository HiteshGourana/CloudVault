"""
backend/services/file_operations_service.py
───────────────────────────────────────────
File Operations Service coordinating DB metadata and AWS S3 objects.

Handles:
  - Streaming File Download
  - Physical Rename (S3 Copy + Delete)
  - Physical Move (S3 Copy + Delete to new prefix)
  - Physical Copy (S3 Copy + new metadata entry)
  - Soft Delete & Restore
  - Bulk operations (Delete, Move, Copy)
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
import boto3
import botocore.exceptions
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.file import File, UploadStatus
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.folder_repo import FolderRepository
from backend.services.activity_service import ActivityService
from backend.utils.encryption import CredentialManager
from backend.utils.upload_utils import generate_unique_filename


# ─────────────────────────────────────────────────────────────────────────────
# boto3 S3 Error mapping helper
# ─────────────────────────────────────────────────────────────────────────────

_S3_OP_ERRORS = {
    "NoSuchKey": (status.HTTP_404_NOT_FOUND, "The requested file object does not exist in S3."),
    "AccessDenied": (status.HTTP_403_FORBIDDEN, "Access denied. Check AWS IAM permissions for this action."),
    "NoSuchBucket": (status.HTTP_404_NOT_FOUND, "The S3 bucket was not found."),
}


def _raise_for_s3_op_error(exc: botocore.exceptions.ClientError, context_msg: str) -> None:
    """Decodes S3 operation failures and returns targeted HTTP Status Codes."""
    code = exc.response.get("Error", {}).get("Code", "Unknown")
    if code in _S3_OP_ERRORS:
        http_code, msg = _S3_OP_ERRORS[code]
    else:
        http_code = status.HTTP_500_INTERNAL_SERVER_ERROR;
        msg = f"{context_msg}: S3 returned error code {code}"
        
    raise HTTPException(status_code=http_code, detail=msg)


class FileOperationsService:
    """Orchestrates file operations on S3 and coordinates corresponding database updates."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._file_repo = FileRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._folder_repo = FolderRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_s3_client_and_bucket(self, bucket_id: uuid.UUID) -> tuple[Any, Any]:
        """Retrieves verified S3 client and local Bucket record using bucket UUID."""
        aws_account = self._aws_repo.get_by_user_id(self._user.id)
        if not aws_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not connected.",
            )

        bucket = self._bucket_repo.get_by_id(bucket_id)
        if not bucket or bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bucket not found or not owned by you.",
            )

        secret_key = CredentialManager.decrypt(aws_account.secret_access_key_encrypted)
        
        session = boto3.Session(
            aws_access_key_id=aws_account.access_key_id,
            aws_secret_access_key=secret_key,
            region_name=bucket.region,
        )
        s3_client = session.client("s3")
        return s3_client, bucket

    def _get_verified_file(self, file_id: uuid.UUID, allow_deleted: bool = False) -> File:
        """Retrieves and validates ownership of a file record. Filters out soft-deleted files unless specified."""
        file_record = self._file_repo.get_by_id(file_id)
        if not file_record or file_record.bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )
            
        if file_record.is_deleted and not allow_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File has been soft-deleted.",
            )
            
        return file_record

    # ── Download File ─────────────────────────────────────────────────────────

    def download_file(self, file_id: uuid.UUID) -> StreamingResponse:
        """
        Retrieves a streaming file response directly from S3.
        
        Validates:
          - User and Bucket ownership
          - Object existence (head check before streaming)
          
        Returns:
          FastAPI StreamingResponse wrapping S3 Body stream.
        """
        file_record = self._get_verified_file(file_id)
        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket_id)

        try:
            # Check object existence and permissions in S3 first
            s3_client.head_object(Bucket=bucket.bucket_name, Key=file_record.s3_key)
            
            # Fetch object stream
            s3_response = s3_client.get_object(Bucket=bucket.bucket_name, Key=file_record.s3_key)
            
            logger.info("Downloading file | key={} size_bytes={}", file_record.s3_key, file_record.size_bytes)
            
            # Return streamed response
            return StreamingResponse(
                content=s3_response["Body"],
                media_type=file_record.mime_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{file_record.file_name}"',
                    "Content-Length": str(file_record.size_bytes),
                },
            )
            
        except botocore.exceptions.ClientError as exc:
            _raise_for_s3_op_error(exc, "Download failed")
            raise

    # ── Rename File ───────────────────────────────────────────────────────────

    def rename_file(self, file_id: uuid.UUID, new_name: str) -> File:
        """
        Renames both S3 object key and metadata in database.
        
        S3 rename strategy:
          1. Copy object to new key path.
          2. Delete old object key.
        """
        file_record = self._get_verified_file(file_id)
        name_cleaned = new_name.strip()
        
        if not name_cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New filename cannot be empty.",
            )

        # Enforce extension match
        _, old_ext = os.path.splitext(file_record.file_name.lower())
        _, new_ext = os.path.splitext(name_cleaned.lower())
        if old_ext != new_ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change file extension. Extension must remain '{old_ext}'.",
            )

        # Check duplicate sibling collisions (excludes soft deleted)
        if self._file_repo.exists_in_folder(file_record.bucket_id, file_record.folder_id, name_cleaned):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{name_cleaned}' already exists in this folder.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket_id)
        
        old_key = file_record.s3_key
        # Calculate new key path prefix
        folder_prefix = file_record.folder.full_path if file_record.folder else ""
        new_key = f"{folder_prefix}{name_cleaned}"

        try:
            # 1. Copy S3 Object
            s3_client.copy_object(
                Bucket=bucket.bucket_name,
                CopySource={"Bucket": bucket.bucket_name, "Key": old_key},
                Key=new_key,
            )
            # 2. Delete Old S3 Object
            s3_client.delete_object(Bucket=bucket.bucket_name, Key=old_key)
            
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 rename copy/delete failed for {}: {}", old_key, str(exc))
            _raise_for_s3_op_error(exc, "Rename failed")

        # 3. Update DB metadata
        file_record.file_name = name_cleaned
        file_record.s3_key = new_key
        self._file_repo.update(file_record)
        
        logger.success("File renamed successfully | old_key={} new_key={}", old_key, new_key)
        return file_record

    # ── Move File ─────────────────────────────────────────────────────────────

    def move_file(self, file_id: uuid.UUID, new_folder_id: Optional[uuid.UUID]) -> File:
        """Moves file between folders, updating S3 key prefix location and database metadata."""
        file_record = self._get_verified_file(file_id)

        if file_record.folder_id == new_folder_id:
            return file_record

        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket_id)

        # Verify destination folder is valid
        folder_prefix = ""
        if new_folder_id:
            target_folder = self._folder_repo.get_by_id(new_folder_id)
            if not target_folder or target_folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target parent folder not found.",
                )
            folder_prefix = target_folder.full_path

        # Check duplicate sibling collisions at destination
        if self._file_repo.exists_in_folder(bucket.id, new_folder_id, file_record.file_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{file_record.file_name}' already exists in the destination folder.",
            )

        old_key = file_record.s3_key
        new_key = f"{folder_prefix}{file_record.file_name}"

        try:
            # 1. Copy S3 Object
            s3_client.copy_object(
                Bucket=bucket.bucket_name,
                CopySource={"Bucket": bucket.bucket_name, "Key": old_key},
                Key=new_key,
            )
            # 2. Delete Old S3 Object
            s3_client.delete_object(Bucket=bucket.bucket_name, Key=old_key)
            
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 move copy/delete failed for {}: {}", old_key, str(exc))
            _raise_for_s3_op_error(exc, "Move failed")

        # 3. Update DB metadata
        file_record.folder_id = new_folder_id
        file_record.s3_key = new_key
        self._file_repo.update(file_record)

        logger.success("File moved successfully | old_key={} new_key={}", old_key, new_key)
        return file_record

    # ── Copy File ─────────────────────────────────────────────────────────────

    def copy_file(self, file_id: uuid.UUID, destination_folder_id: Optional[uuid.UUID] = None) -> File:
        """
        Copies S3 object to destination folder and registers new file metadata.
        Generates auto-rename unique filename if path collision occurs at destination.
        """
        file_record = self._get_verified_file(file_id)
        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket_id)

        # Verify destination folder
        folder_prefix = ""
        if destination_folder_id:
            dest_folder = self._folder_repo.get_by_id(destination_folder_id)
            if not dest_folder or dest_folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target destination folder not found.",
                )
            folder_prefix = dest_folder.full_path

        # Resolve duplicate name conflicts at destination (default strategy: auto rename)
        def exists_callback(name_candidate: str) -> bool:
            return self._file_repo.exists_in_folder(bucket.id, destination_folder_id, name_candidate)

        original_name = file_record.file_name
        final_name = generate_unique_filename(exists_callback, original_name)
        new_key = f"{folder_prefix}{final_name}"

        try:
            # 1. Copy S3 Object
            s3_client.copy_object(
                Bucket=bucket.bucket_name,
                CopySource={"Bucket": bucket.bucket_name, "Key": file_record.s3_key},
                Key=new_key,
            )
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 copy object failed: {}", str(exc))
            _raise_for_s3_op_error(exc, "Copy failed")

        # 2. Insert new file record to database
        new_record = self._file_repo.create(
            bucket_id=bucket.id,
            folder_id=destination_folder_id,
            file_name=final_name,
            original_file_name=file_record.original_file_name,
            extension=file_record.extension,
            mime_type=file_record.mime_type,
            size_bytes=file_record.size_bytes,
            s3_key=new_key,
            storage_class=file_record.storage_class,
        )
        # Inherit completion status of copied original file
        new_record.upload_status = UploadStatus.COMPLETED.value
        self._file_repo.update(new_record)

        logger.success("File copied successfully | source_key={} dest_key={}", file_record.s3_key, new_key)
        return new_record

    # ── Soft Delete File ──────────────────────────────────────────────────────

    def soft_delete_file(self, file_id: uuid.UUID) -> None:
        """
        Soft deletes the file metadata and physically removes the S3 object.
        """
        file_record = self._get_verified_file(file_id)
        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket_id)

        try:
            # Delete S3 object
            s3_client.delete_object(Bucket=bucket.bucket_name, Key=file_record.s3_key)
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 delete object failed for {}: {}", file_record.s3_key, str(exc))
            _raise_for_s3_op_error(exc, "Delete failed")

        file_record.is_deleted = True
        file_record.deleted_at = datetime.now(timezone.utc)
        file_record.upload_status = UploadStatus.DELETED.value
        self._file_repo.update(file_record)

        logger.info("File deleted physically from S3 and marked as deleted in DB | key={}", file_record.s3_key)

        # Audit log
        try:
            ActivityService.log_activity(
                self._db,
                user_id=self._user.id,
                action="FileDelete",
                resource_type="file",
                resource_id=str(file_record.id),
                status_code="success",
                message=f"File '{file_record.file_name}' permanently deleted from S3 bucket '{file_record.bucket.bucket_name}'.",
            )
        except Exception:
            pass

    # ── Restore Soft Deleted File ─────────────────────────────────────────────

    def restore_file(self, file_id: uuid.UUID) -> File:
        """Restores a soft-deleted file by removing soft-delete tags and resetting status."""
        file_record = self._get_verified_file(file_id, allow_deleted=True)
        
        if not file_record.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not deleted and cannot be restored.",
            )

        # Duplication check: verify no active file with the same name exists in parent folder
        if self._file_repo.exists_in_folder(file_record.bucket_id, file_record.folder_id, file_record.file_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot restore: an active file named '{file_record.file_name}' already exists in the folder.",
            )

        # Remove soft delete marks
        file_record.is_deleted = False
        file_record.deleted_at = None
        file_record.upload_status = UploadStatus.COMPLETED.value
        self._file_repo.update(file_record)
        
        logger.success("File restored successfully | key={}", file_record.s3_key)
        return file_record

    # ── Bulk Operations ───────────────────────────────────────────────────────

    def bulk_delete(self, file_ids: List[uuid.UUID]) -> List[uuid.UUID]:
        """
        Batch-deletes multiple files from S3 and soft-marks them in the database.

        Strategy:
          1. Verify ownership of all requested files (filters out not-found/wrong-user).
          2. Group by bucket — issue one S3 delete_objects batch call per bucket
             (up to 1000 keys per API call, which is the S3 maximum).
          3. Bulk-update the DB records in a single UPDATE statement.

        Returns:
            List of successfully deleted file UUIDs.
        """
        from collections import defaultdict
        from datetime import datetime, timezone

        # Step 1: Resolve + verify all file records
        verified: list[File] = []
        for file_id in file_ids:
            try:
                file_record = self._get_verified_file(file_id)
                verified.append(file_record)
            except Exception as exc:
                logger.warning("Bulk delete: skipping file '{}' — {}", str(file_id), str(exc))

        if not verified:
            return []

        # Step 2: Group by bucket and issue batch S3 delete_objects
        by_bucket: dict[uuid.UUID, list] = defaultdict(list)
        for file_record in verified:
            by_bucket[file_record.bucket_id].append(file_record)

        succeeded: list[uuid.UUID] = []
        failed_ids: set[uuid.UUID] = set()

        for bucket_id, records in by_bucket.items():
            try:
                s3_client, bucket = self._get_s3_client_and_bucket(bucket_id)
                keys = [{"Key": r.s3_key} for r in records]

                # S3 delete_objects: max 1000 keys per call
                for i in range(0, len(keys), 1000):
                    chunk_keys = keys[i : i + 1000]
                    chunk_records = records[i : i + 1000]
                    response = s3_client.delete_objects(
                        Bucket=bucket.bucket_name,
                        Delete={"Objects": chunk_keys, "Quiet": False},
                    )
                    # Mark successfully deleted S3 keys
                    deleted_keys = {d["Key"] for d in response.get("Deleted", [])}
                    errored_keys = {e["Key"] for e in response.get("Errors", [])}

                    for r in chunk_records:
                        if r.s3_key in errored_keys:
                            logger.warning("S3 delete_objects error for key '{}' in bulk", r.s3_key)
                            failed_ids.add(r.id)
                        else:
                            succeeded.append(r.id)

            except Exception as exc:
                logger.warning("Bulk delete: S3 batch call failed for bucket '{}': {}", str(bucket_id), str(exc))
                for r in records:
                    failed_ids.add(r.id)

        # Step 3: Bulk soft-delete DB records for all succeeded files
        if succeeded:
            now = datetime.now(timezone.utc)
            (
                self._db.query(File)
                .filter(File.id.in_(succeeded))
                .update(
                    {
                        "is_deleted": True,
                        "deleted_at": now,
                        "upload_status": UploadStatus.DELETED.value,
                    },
                    synchronize_session=False,
                )
            )
            self._db.commit()
            logger.info("Bulk delete complete — {} file(s) deleted, {} failed", len(succeeded), len(failed_ids))

        return succeeded



    def bulk_move(self, file_ids: List[uuid.UUID], target_folder_id: Optional[uuid.UUID]) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Moves multiple files sequentially. Returns tuple of (succeeded_ids, failed_ids)."""
        succeeded: list[uuid.UUID] = []
        failed: list[uuid.UUID] = []
        
        for file_id in file_ids:
            try:
                self.move_file(file_id, target_folder_id)
                succeeded.append(file_id)
            except Exception as exc:
                logger.warning("Bulk move item failed for '{}': {}", str(file_id), str(exc))
                failed.append(file_id)
                
        return succeeded, failed

    def bulk_copy(self, file_ids: List[uuid.UUID], destination_folder_id: Optional[uuid.UUID]) -> tuple[list[File], list[uuid.UUID]]:
        """Copies multiple files sequentially. Returns tuple of (succeeded_records, failed_ids)."""
        succeeded: list[File] = []
        failed: list[uuid.UUID] = []
        
        for file_id in file_ids:
            try:
                new_record = self.copy_file(file_id, destination_folder_id)
                succeeded.append(new_record)
            except Exception as exc:
                logger.warning("Bulk copy item failed for '{}': {}", str(file_id), str(exc))
                failed.append(file_id)
                
        return succeeded, failed
