"""
backend/services/dashboard_service.py
──────────────────────────────────────
Dashboard and Analytics reporting service.

Executes database-level aggregations to compile storage and usage metrics.
Avoids N+1 querying by utilizing explicit SQL JOINs, GROUP BYs, and aggregate functions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.models.aws_account import AWSAccount
from backend.models.bucket import Bucket
from backend.models.file import File, UploadStatus
from backend.models.folder import Folder
from backend.models.shared_link import SharedLink
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.folder_repo import FolderRepository
from backend.repositories.share_repo import ShareRepository
from backend.schemas.dashboard import (
    BucketShortSummary,
    DashboardOverviewResponse,
    FileAnalyticsResponse,
    FileTypeStats,
    FolderAnalyticsResponse,
    LargestBucketResponse,
    LargestFileResponse,
    RecentActivityResponse,
    StorageAnalyticsResponse,
    StorageSummary,
    UserAWSOverview,
)
from backend.services.file_service import get_category_for_extension


class DashboardService:
    """Computes aggregate analytics and logs statistics for the dashboard endpoints."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._file_repo = FileRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._folder_repo = FolderRepository(db)
        self._aws_repo = AWSAccountRepository(db)
        self._share_repo = ShareRepository(db)

    # ── User AWS Overview Helper ──────────────────────────────────────────────

    def _get_aws_overview(self) -> UserAWSOverview:
        """Retrieves AWS account connectivity parameters."""
        aws_account = self._aws_repo.get_by_user_id(self._user.id)
        if not aws_account:
            return UserAWSOverview(
                connected_account_id=None,
                iam_arn=None,
                default_region=None,
                is_connected=False,
            )
        return UserAWSOverview(
            connected_account_id=aws_account.aws_account_id,
            iam_arn=aws_account.iam_arn,
            default_region=aws_account.region,
            is_connected=aws_account.is_connected,
        )

    # ── Dashboard Overview ────────────────────────────────────────────────────

    def get_overview(self) -> DashboardOverviewResponse:
        """
        Gathers general aggregates:
          - AWS account overview
          - Total storage, buckets, folders, files, and active shares
          - List of buckets with sizes and file counts
        """
        aws_info = self._get_aws_overview()

        # Database aggregates
        total_buckets = (
            self._db.query(func.count(Bucket.id))
            .filter(Bucket.user_id == self._user.id)
            .scalar() or 0
        )
        total_folders = (
            self._db.query(func.count(Folder.id))
            .filter(Folder.bucket.has(user_id=self._user.id))
            .scalar() or 0
        )
        total_files = (
            self._db.query(func.count(File.id))
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == self._user.id,
                File.is_deleted == False,
                File.upload_status == UploadStatus.COMPLETED.value,
            )
            .scalar() or 0
        )
        
        now = datetime.now(timezone.utc)
        total_shares = (
            self._db.query(func.count(SharedLink.id))
            .filter(
                SharedLink.user_id == self._user.id,
                SharedLink.is_active == True,
                SharedLink.expires_at > now,
            )
            .scalar() or 0
        )

        total_storage = (
            self._db.query(func.sum(File.size_bytes))
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == self._user.id,
                File.is_deleted == False,
                File.upload_status == UploadStatus.COMPLETED.value,
            )
            .scalar() or 0
        )

        # Buckets summary list
        bucket_records = self._bucket_repo.get_all_by_user(self._user.id)
        bucket_summaries: List[BucketShortSummary] = []
        
        for b in bucket_records:
            b_size = (
                self._db.query(func.sum(File.size_bytes))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            b_count = (
                self._db.query(func.count(File.id))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            bucket_summaries.append(
                BucketShortSummary(
                    bucket_id=b.id,
                    bucket_name=b.bucket_name,
                    region=b.region,
                    file_count=b_count,
                    size_bytes=b_size,
                )
            )

        return DashboardOverviewResponse(
            aws_connection=aws_info,
            storage=StorageSummary(
                total_buckets=total_buckets,
                total_folders=total_folders,
                total_files=total_files,
                total_shared_files=total_shares,
                storage_used_bytes=total_storage,
            ),
            buckets=bucket_summaries,
        )

    # ── Storage Analytics ─────────────────────────────────────────────────────

    def get_storage_analytics(self) -> StorageAnalyticsResponse:
        """Computes comprehensive statistics for files, folders, and buckets."""
        # General file statistics
        stats = (
            self._db.query(
                func.count(File.id),
                func.sum(File.size_bytes),
                func.avg(File.size_bytes),
                func.max(File.size_bytes),
                func.min(File.size_bytes),
            )
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == self._user.id,
                File.is_deleted == False,
                File.upload_status == UploadStatus.COMPLETED.value,
            )
            .first()
        )

        total_files = stats[0] or 0
        total_size = stats[1] or 0
        avg_file_size = float(stats[2]) if stats[2] is not None else 0.0
        max_size = stats[3] or 0
        min_size = stats[4] or 0

        # Retrieve filenames for largest and smallest files
        largest_file_name = None
        if max_size > 0:
            lf = (
                self._db.query(File.file_name)
                .join(Bucket, File.bucket_id == Bucket.id)
                .filter(
                    Bucket.user_id == self._user.id,
                    File.size_bytes == max_size,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .first()
            )
            largest_file_name = lf[0] if lf else None

        smallest_file_name = None
        if total_files > 0:
            sf = (
                self._db.query(File.file_name)
                .join(Bucket, File.bucket_id == Bucket.id)
                .filter(
                    Bucket.user_id == self._user.id,
                    File.size_bytes == min_size,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .first()
            )
            smallest_file_name = sf[0] if sf else None

        # Bucket Statistics
        buckets = self._bucket_repo.get_all_by_user(self._user.id)
        bucket_count = len(buckets)
        avg_bucket_size = (total_size / bucket_count) if bucket_count > 0 else 0.0

        # Find largest bucket details
        largest_bucket_name = None
        largest_bucket_size = 0
        
        for b in buckets:
            b_size = (
                self._db.query(func.sum(File.size_bytes))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            if b_size > largest_bucket_size:
                largest_bucket_size = b_size
                largest_bucket_name = b.bucket_name

        # Folder Statistics
        folder_count = (
            self._db.query(func.count(Folder.id))
            .filter(Folder.bucket.has(user_id=self._user.id))
            .scalar() or 0
        )
        avg_folder_size = (total_size / folder_count) if folder_count > 0 else 0.0

        return StorageAnalyticsResponse(
            total_size_bytes=total_size,
            average_file_size_bytes=avg_file_size,
            largest_file_name=largest_file_name,
            largest_file_size_bytes=max_size,
            smallest_file_name=smallest_file_name,
            smallest_file_size_bytes=min_size,
            largest_bucket_name=largest_bucket_name,
            largest_bucket_size_bytes=largest_bucket_size,
            average_bucket_size_bytes=avg_bucket_size,
            average_folder_size_bytes=avg_folder_size,
        )

    # ── File Type Distribution Analytics ──────────────────────────────────────

    def get_file_analytics(self) -> FileAnalyticsResponse:
        """Aggregates counts, total sizes, and percentages grouped by file categories."""
        summaries = self._file_repo.get_user_file_types_summary(self._user.id)

        # Setup standard distribution structures
        categories = {
            "PDF": {"count": 0, "size": 0},
            "Images": {"count": 0, "size": 0},
            "Videos": {"count": 0, "size": 0},
            "Audio": {"count": 0, "size": 0},
            "Archives": {"count": 0, "size": 0},
            "Documents": {"count": 0, "size": 0},
            "Others": {"count": 0, "size": 0},
        }

        total_files = 0
        for ext, count, total_size in summaries:
            cat = get_category_for_extension(ext)
            size = int(total_size) if total_size else 0
            
            categories[cat]["count"] += count
            categories[cat]["size"] += size
            total_files += count

        # Convert to FileTypeStats schemas containing percentages
        distribution: Dict[str, FileTypeStats] = {}
        for cat, data in categories.items():
            count = data["count"]
            pct = (count / total_files * 100) if total_files > 0 else 0.0
            
            distribution[cat] = FileTypeStats(
                count=count,
                size_bytes=data["size"],
                percentage=round(pct, 2),
            )

        return FileAnalyticsResponse(
            total_files=total_files,
            distribution=distribution,
        )

    # ── Bucket Details Analytics ──────────────────────────────────────────────

    def get_bucket_analytics(self) -> List[Any]:
        """Compiles detailed usage profiles for each S3 bucket connected to the account."""
        buckets = self._bucket_repo.get_all_by_user(self._user.id)
        analytics = []

        for b in buckets:
            # Aggregate stats
            stats = (
                self._db.query(
                    func.count(File.id),
                    func.sum(File.size_bytes),
                    func.max(File.updated_at),
                )
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .first()
            )

            file_count = stats[0] or 0
            total_size = stats[1] or 0
            last_updated = stats[2]

            folder_count = (
                self._db.query(func.count(Folder.id))
                .filter(Folder.bucket_id == b.id)
                .scalar() or 0
            )

            analytics.append(
                {
                    "bucket_name": b.bucket_name,
                    "creation_date": b.creation_date,
                    "file_count": file_count,
                    "total_size_bytes": total_size,
                    "folder_count": folder_count,
                    "last_updated": last_updated,
                }
            )

        return analytics

    # ── Folder Details Analytics ──────────────────────────────────────────────

    def get_folder_analytics(self) -> List[FolderAnalyticsResponse]:
        """
        Compiles details for virtual folders.
        Recursively calculates counts and sizes of nested files using prefix queries.
        """
        # Retrieve folders in user's buckets
        folders = (
            self._db.query(Folder)
            .join(Bucket, Folder.bucket_id == Bucket.id)
            .filter(Bucket.user_id == self._user.id)
            .all()
        )

        analytics: List[FolderAnalyticsResponse] = []

        for f in folders:
            # Query nested files recursively: S3 key starts with folder path prefix
            nested_stats = (
                self._db.query(
                    func.count(File.id),
                    func.sum(File.size_bytes),
                )
                .filter(
                    File.bucket_id == f.bucket_id,
                    File.s3_key.startswith(f.full_path),
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .first()
            )

            file_count = nested_stats[0] or 0
            total_size = nested_stats[1] or 0

            # Count direct subfolders in database
            subfolder_count = (
                self._db.query(func.count(Folder.id))
                .filter(Folder.parent_folder_id == f.id)
                .scalar() or 0
            )

            parent_name = f.parent.folder_name if f.parent else None

            analytics.append(
                FolderAnalyticsResponse(
                    folder_name=f.folder_name,
                    parent_folder_name=parent_name,
                    full_path=f.full_path,
                    file_count=file_count,
                    size_bytes=total_size,
                    subfolder_count=subfolder_count,
                )
            )

        return analytics

    # ── Recent Activity Summaries ─────────────────────────────────────────────

    def get_recent_activity(self) -> RecentActivityResponse:
        """Gathers recent folders, buckets, shares, and files created on this account (up to 10 entries)."""
        # Recent files
        recent_files_records = (
            self._db.query(File)
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == self._user.id,
                File.is_deleted == False,
                File.upload_status == UploadStatus.COMPLETED.value,
            )
            .order_by(File.created_at.desc())
            .limit(10)
            .all()
        )
        recent_files = [
            LargestFileResponse(
                file_id=f.id,
                file_name=f.file_name,
                s3_key=f.s3_key,
                bucket_name=f.bucket.bucket_name,
                size_bytes=f.size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
            )
            for f in recent_files_records
        ]

        # Recent buckets
        recent_buckets_records = (
            self._db.query(Bucket)
            .filter(Bucket.user_id == self._user.id)
            .order_by(Bucket.created_at.desc())
            .limit(10)
            .all()
        )
        
        recent_buckets = []
        for b in recent_buckets_records:
            b_size = (
                self._db.query(func.sum(File.size_bytes))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            b_count = (
                self._db.query(func.count(File.id))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            recent_buckets.append(
                LargestBucketResponse(
                    bucket_id=b.id,
                    bucket_name=b.bucket_name,
                    region=b.region,
                    total_size_bytes=b_size,
                    file_count=b_count,
                )
            )

        # Recent shares
        recent_shares_records = (
            self._db.query(SharedLink)
            .filter(SharedLink.user_id == self._user.id)
            .order_by(SharedLink.created_at.desc())
            .limit(10)
            .all()
        )
        
        recent_shares = []
        now = datetime.now(timezone.utc)
        for s in recent_shares_records:
            recent_shares.append(
                {
                    "share_id": s.id,
                    "file_name": s.file.file_name if s.file else None,
                    "share_type": s.share_type,
                    "is_active": s.is_active and s.expires_at > now,
                    "created_at": s.created_at,
                }
            )

        return RecentActivityResponse(
            recent_files=recent_files,
            recent_buckets=recent_buckets,
            recent_shares=recent_shares,
        )

    # ── Top Largest Files ─────────────────────────────────────────────────────

    def get_largest_files(self) -> List[LargestFileResponse]:
        """Returns the top 10 largest active files owned by the user."""
        records = (
            self._db.query(File)
            .join(Bucket, File.bucket_id == Bucket.id)
            .filter(
                Bucket.user_id == self._user.id,
                File.is_deleted == False,
                File.upload_status == UploadStatus.COMPLETED.value,
            )
            .order_by(File.size_bytes.desc())
            .limit(10)
            .all()
        )

        return [
            LargestFileResponse(
                file_id=f.id,
                file_name=f.file_name,
                s3_key=f.s3_key,
                bucket_name=f.bucket.bucket_name,
                size_bytes=f.size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
            )
            for f in records
        ]

    # ── Top Largest Buckets ───────────────────────────────────────────────────

    def get_largest_buckets(self) -> List[LargestBucketResponse]:
        """Returns the top 10 largest buckets connected to this account."""
        buckets = self._bucket_repo.get_all_by_user(self._user.id)
        results = []

        for b in buckets:
            b_size = (
                self._db.query(func.sum(File.size_bytes))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            b_count = (
                self._db.query(func.count(File.id))
                .filter(
                    File.bucket_id == b.id,
                    File.is_deleted == False,
                    File.upload_status == UploadStatus.COMPLETED.value,
                )
                .scalar() or 0
            )
            results.append(
                LargestBucketResponse(
                    bucket_id=b.id,
                    bucket_name=b.bucket_name,
                    region=b.region,
                    total_size_bytes=b_size,
                    file_count=b_count,
                )
            )

        # Sort desc by size and limit to top 10
        sorted_results = sorted(results, key=lambda x: x.total_size_bytes, reverse=True)
        return sorted_results[:10]
