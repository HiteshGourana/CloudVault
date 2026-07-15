"""
backend/schemas/dashboard.py
────────────────────────────
Pydantic v2 schemas for the Dashboard & Analytics module.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Sub-schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserAWSOverview(BaseModel):
    """User AWS account details overview."""
    
    connected_account_id: Optional[str] = Field(description="12-digit AWS account ID")
    iam_arn: Optional[str] = Field(description="IAM User ARN")
    default_region: Optional[str] = Field(description="Connected S3 home region")
    is_connected: bool = Field(description="True if AWS credentials are valid")


class StorageSummary(BaseModel):
    """General storage aggregates."""
    
    total_buckets: int = Field(description="Total count of buckets")
    total_folders: int = Field(description="Total count of virtual folders")
    total_files: int = Field(description="Total count of files (excluding Deleted)")
    total_shared_files: int = Field(description="Total count of active file shared links")
    storage_used_bytes: int = Field(description="Sum of sizes of all uploaded files in bytes")


class BucketShortSummary(BaseModel):
    """Short summary of a single S3 bucket."""
    
    bucket_id: uuid.UUID = Field(description="Bucket local UUID")
    bucket_name: str = Field(description="S3 bucket name")
    region: str = Field(description="AWS region")
    file_count: int = Field(description="Total files inside this bucket")
    size_bytes: int = Field(description="Aggregate storage bytes used by this bucket")


class FileTypeStats(BaseModel):
    """File type distribution statistics."""
    
    count: int = Field(description="Number of files in this category")
    size_bytes: int = Field(description="Total bytes in this category")
    percentage: float = Field(description="Percentage representation by count relative to total files")


# ─────────────────────────────────────────────────────────────────────────────
# API Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class DashboardOverviewResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/overview"""

    aws_connection: UserAWSOverview = Field(description="AWS connection status")
    storage: StorageSummary = Field(description="Storage aggregates overview")
    buckets: List[BucketShortSummary] = Field(description="Overview list of buckets usage")


class StorageAnalyticsResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/storage"""

    total_size_bytes: int = Field(description="Aggregate storage bytes used across all buckets")
    average_file_size_bytes: float = Field(description="Average file size across all files")
    largest_file_name: Optional[str] = Field(description="Name of the largest file")
    largest_file_size_bytes: int = Field(description="Size of the largest file in bytes")
    smallest_file_name: Optional[str] = Field(description="Name of the smallest file")
    smallest_file_size_bytes: int = Field(description="Size of the smallest file in bytes")
    
    # Bucket stats
    largest_bucket_name: Optional[str] = Field(description="Name of the bucket using most storage")
    largest_bucket_size_bytes: int = Field(description="Storage bytes used by largest bucket")
    average_bucket_size_bytes: float = Field(description="Average storage used per bucket")
    average_folder_size_bytes: float = Field(description="Average storage used per folder")


class FileAnalyticsResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/files"""

    total_files: int = Field(description="Total number of active files")
    distribution: Dict[str, FileTypeStats] = Field(
        description="Stats grouped by categories: PDF, Images, Videos, Audio, Documents, Archives, Others"
    )


class BucketAnalyticsResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/buckets"""

    bucket_name: str = Field(description="S3 bucket name")
    creation_date: Optional[datetime] = Field(description="Creation date returned by S3")
    file_count: int = Field(description="Number of files stored inside this bucket")
    total_size_bytes: int = Field(description="Aggregate size in bytes")
    folder_count: int = Field(description="Number of virtual folders in this bucket")
    last_updated: Optional[datetime] = Field(description="Last modified timestamp of files in this bucket")


class FolderAnalyticsResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/folders"""

    folder_name: str = Field(description="Virtual folder display name")
    parent_folder_name: Optional[str] = Field(description="Parent folder display name. Null if root child.")
    full_path: str = Field(description="Absolute path prefix ending in slash")
    file_count: int = Field(description="Number of files nested inside this folder (recursive)")
    size_bytes: int = Field(description="Aggregate size of all files nested inside this folder (recursive)")
    subfolder_count: int = Field(description="Number of direct sub-folders")


class LargestFileResponse(BaseModel):
    """Response item — GET /api/v1/dashboard/largest-files"""

    file_id: uuid.UUID = Field(description="File UUID")
    file_name: str = Field(description="Filename")
    s3_key: str = Field(description="S3 storage key path")
    bucket_name: str = Field(description="S3 bucket name")
    size_bytes: int = Field(description="File size in bytes")
    mime_type: str = Field(description="MIME Content-Type")
    created_at: datetime = Field(description="Creation timestamp")


class LargestBucketResponse(BaseModel):
    """Response item — GET /api/v1/dashboard/largest-buckets"""

    bucket_id: uuid.UUID = Field(description="Bucket local UUID")
    bucket_name: str = Field(description="S3 bucket name")
    region: str = Field(description="AWS region")
    total_size_bytes: int = Field(description="Aggregate size in bytes")
    file_count: int = Field(description="Total count of files")


class RecentActivityResponse(BaseModel):
    """Response body — GET /api/v1/dashboard/recent"""

    recent_files: List[LargestFileResponse] = Field(description="Recently uploaded files (up to 10)")
    recent_buckets: List[LargestBucketResponse] = Field(description="Recently connected/created buckets (up to 10)")
    recent_shares: List[Dict[str, Any]] = Field(description="Recently shared files (up to 10)")
