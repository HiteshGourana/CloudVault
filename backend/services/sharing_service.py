"""
backend/services/sharing_service.py
───────────────────────────────────
File Sharing and Secure Access Service.

Orchestrates S3 pre-signed downloads and POST uploads.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import boto3
import botocore.exceptions
from botocore.client import Config
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.shared_link import SharedLink, ShareType
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.folder_repo import FolderRepository
from backend.repositories.share_repo import ShareRepository
from backend.schemas.share import (
    ShareDownloadRequest,
    ShareHistoryEntry,
    ShareHistoryResponse,
    ShareResponse,
    ShareUploadRequest,
)
from backend.utils.encryption import CredentialManager

# ── Allowed Expiration Window Mapping ─────────────────────────────────────────
_EXPIRATION_DELTAS = {
    "15m": (900, timedelta(minutes=15)),
    "1h": (3600, timedelta(hours=1)),
    "24h": (86400, timedelta(days=1)),
    "7d": (604800, timedelta(days=7)),
}


def parse_expiration_window(exp_str: str) -> Tuple[int, datetime]:
    """
    Parses expiration string ('15m', '1h', '24h', '7d') into seconds and absolute expiration datetime.
    
    Raises 400 Bad Request on invalid keys.
    """
    if exp_str not in _EXPIRATION_DELTAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid expiration range. Supported: '15m', '1h', '24h', '7d'.",
        )
    seconds, delta = _EXPIRATION_DELTAS[exp_str]
    expires_at = datetime.now(timezone.utc) + delta
    return seconds, expires_at


class SharingService:
    """Orchestrates secure link creation, verification, revocation, and listing histories."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._share_repo = ShareRepository(db)
        self._file_repo = FileRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._folder_repo = FolderRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_s3_client_and_bucket(self, bucket_name: str) -> tuple[Any, Any]:
        """Retrieves verified S3 client and local Bucket record."""
        aws_account = self._aws_repo.get_by_user_id(self._user.id)
        if not aws_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not connected.",
            )

        bucket = self._bucket_repo.get_by_name(bucket_name)
        if not bucket or bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' not found or not owned by you.",
            )

        secret_key = CredentialManager.decrypt(aws_account.secret_access_key_encrypted)

        # Build the region-specific endpoint URL.
        # This is CRITICAL for pre-signed URL correctness: without it, boto3 signs against
        # the global endpoint (s3.amazonaws.com) but the generated URL resolves to the regional
        # endpoint — causing a SignatureDoesNotMatch error when the client opens the link.
        region = bucket.region
        if region == "us-east-1":
            # us-east-1 still uses the legacy global endpoint for backwards compatibility
            endpoint_url = "https://s3.amazonaws.com"
        else:
            endpoint_url = f"https://s3.{region}.amazonaws.com"

        session = boto3.Session(
            aws_access_key_id=aws_account.access_key_id,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        s3_client = session.client(
            "s3",
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        return s3_client, bucket


    # ── Generate Download URL ─────────────────────────────────────────────────

    def generate_download_url(self, data: ShareDownloadRequest) -> ShareResponse:
        """
        Generates a secure S3 Pre-Signed Download URL:
          1. Verifies file metadata existence and user ownership.
          2. Computes the expiration window delta.
          3. Issues the GET pre-signed URL from S3 (boto3 generate_presigned_url).
          4. Caches token metadata record in database.
        """
        file_record = self._file_repo.get_by_id(data.file_id)
        if not file_record or file_record.bucket.user_id != self._user.id or file_record.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(file_record.bucket.bucket_name)
        seconds, expires_at = parse_expiration_window(data.expiration)

        try:
            # Check S3 object presence first
            s3_client.head_object(Bucket=bucket.bucket_name, Key=file_record.s3_key)
            
            # Generate pre-signed URL
            presigned_url = s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket.bucket_name,
                    "Key": file_record.s3_key,
                },
                ExpiresIn=seconds,
            )
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 pre-signed download URL generation failed: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate S3 pre-signed URL. Verify bucket permissions.",
            )

        # Store metadata in DB
        share_record = self._share_repo.create(
            user_id=self._user.id,
            file_id=file_record.id,
            share_type=ShareType.DOWNLOAD.value,
            expires_at=expires_at,
        )

        logger.success(
            "Pre-signed download URL created | file_id={} expires_at={} user_id={}",
            str(file_record.id), str(expires_at), str(self._user.id)
        )
        
        return ShareResponse(
            id=share_record.id,
            file_id=share_record.file_id,
            user_id=share_record.user_id,
            share_token=share_record.share_token,
            share_type=share_record.share_type,
            expires_at=share_record.expires_at,
            is_active=share_record.is_active,
            created_at=share_record.created_at,
            revoked_at=share_record.revoked_at,
            presigned_url=presigned_url,
        )

    # ── Generate Upload URL ───────────────────────────────────────────────────

    def generate_upload_url(self, data: ShareUploadRequest) -> ShareResponse:
        """
        Generates a secure S3 Pre-Signed Upload POST payload:
          1. Verifies bucket ownership and destination folder existence.
          2. Computes the target S3 key path.
          3. Generates the pre-signed POST dictionary (containing URL + fields).
          4. Persists shared link metadata record in database (no associated file_id yet).
        """
        s3_client, bucket = self._get_s3_client_and_bucket(data.bucket_name)

        # Verify folder if supplied
        folder_prefix = ""
        if data.folder_id:
            folder = self._folder_repo.get_by_id(data.folder_id)
            if not folder or folder.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found.",
                )
            folder_prefix = folder.full_path

        # Validate filename format
        filename_cleaned = data.filename.strip()
        if "/" in filename_cleaned or "\\" in filename_cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot contain path slashes.",
            )

        s3_key = f"{folder_prefix}{filename_cleaned}"
        seconds, expires_at = parse_expiration_window(data.expiration)

        try:
            # Generate pre-signed POST (includes URL and policy signature fields)
            post_response = s3_client.generate_presigned_post(
                Bucket=bucket.bucket_name,
                Key=s3_key,
                ExpiresIn=seconds,
            )
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 pre-signed POST upload generation failed: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate S3 pre-signed upload payload.",
            )

        # Store metadata in DB (file_id is null for uploads)
        share_record = self._share_repo.create(
            user_id=self._user.id,
            file_id=None,
            share_type=ShareType.UPLOAD.value,
            expires_at=expires_at,
        )

        logger.success(
            "Pre-signed upload payload created | key={} expires_at={} user_id={}",
            s3_key, str(expires_at), str(self._user.id)
        )

        return ShareResponse(
            id=share_record.id,
            file_id=None,
            user_id=share_record.user_id,
            share_token=share_record.share_token,
            share_type=share_record.share_type,
            expires_at=share_record.expires_at,
            is_active=share_record.is_active,
            created_at=share_record.created_at,
            revoked_at=share_record.revoked_at,
            presigned_url=post_response["url"],
            form_fields=post_response["fields"],
        )

    # ── List Active Shares ────────────────────────────────────────────────────

    def list_active_shares(self) -> List[SharedLink]:
        """Returns all non-expired, non-revoked shared links generated by the user."""
        return self._share_repo.get_active_shares_by_user(self._user.id)

    # ── Get Share Details ─────────────────────────────────────────────────────

    def get_share_details(self, share_id: uuid.UUID) -> SharedLink:
        """Fetch shared link record details by UUID. Validates ownership."""
        share = self._share_repo.get_by_id(share_id)
        if not share or share.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share record not found.",
            )
        return share

    # ── Revoke Share ──────────────────────────────────────────────────────────

    def revoke_share(self, share_id: uuid.UUID) -> None:
        """
        Revokes a shared link in the database:
          - Marks `is_active = False` and sets `revoked_at = now()`.
          - Already-issued pre-signed URLs remain valid in S3 until their AWS
            expiration (S3 checks signed headers directly at request time).
        """
        share = self.get_share_details(share_id)
        if not share.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Share is already revoked.",
            )

        share.is_active = False
        share.revoked_at = datetime.now(timezone.utc)
        self._share_repo.update(share)
        
        logger.info("Share link revoked | share_id={}", str(share_id))

    # ── Get Sharing History ────────────────────────────────────────────────────

    def get_sharing_history(self) -> ShareHistoryResponse:
        """
        Returns complete share logs history (active, revoked, and expired).
        Resolves expiration status dynamically relative to current server time.
        """
        records = self._share_repo.get_history_by_user(self._user.id)
        now = datetime.now(timezone.utc)
        
        entries: List[ShareHistoryEntry] = []
        active_count = 0

        for r in records:
            is_expired = r.expires_at <= now
            is_currently_active = r.is_active and not is_expired
            
            if is_currently_active:
                active_count += 1
                
            file_name = r.file.file_name if r.file else None
            s3_key = r.file.s3_key if r.file else None

            entries.append(
                ShareHistoryEntry(
                    id=r.id,
                    file_id=r.file_id,
                    file_name=file_name,
                    s3_key=s3_key,
                    share_type=r.share_type,
                    created_at=r.created_at,
                    expires_at=r.expires_at,
                    is_active=r.is_active,
                    is_expired=is_expired,
                    revoked_at=r.revoked_at,
                )
            )

        return ShareHistoryResponse(
            total=len(entries),
            active=active_count,
            shares=entries,
        )
