"""
backend/api/dashboard.py
────────────────────────
API routes for Dashboard & Analytics calculations.

All routes require authentication via `get_current_user`.
"""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.dashboard import (
    BucketAnalyticsResponse,
    DashboardOverviewResponse,
    FileAnalyticsResponse,
    FolderAnalyticsResponse,
    LargestBucketResponse,
    LargestFileResponse,
    RecentActivityResponse,
    StorageAnalyticsResponse,
)
from backend.services.auth_service import get_current_user
from backend.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard & Analytics"],
)


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard overview",
    description="Returns aggregate overview metrics including AWS account details, bucket counts, folder counts, file counts, and storage usage.",
    responses={
        200: {"description": "Overview metrics retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    """Get dashboard overview aggregates."""
    service = DashboardService(db, current_user)
    return service.get_overview()


@router.get(
    "/storage",
    response_model=StorageAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get storage analytics",
    description="Calculates detailed statistics of file sizes (average, largest, smallest) and bucket storage usage profiles.",
    responses={
        200: {"description": "Storage statistics calculated successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_storage_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StorageAnalyticsResponse:
    """Get detailed storage statistics."""
    service = DashboardService(db, current_user)
    return service.get_storage_analytics()


@router.get(
    "/files",
    response_model=FileAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get file analytics and type distribution",
    description="Calculates file count, total size, and percentage distribution grouped by major extension categories (PDF, Image, Video, Audio, Archive, Document, Others).",
    responses={
        200: {"description": "File distribution analytics retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_file_type_distribution(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileAnalyticsResponse:
    """Get file type distribution statistics."""
    service = DashboardService(db, current_user)
    return service.get_file_analytics()


@router.get(
    "/buckets",
    response_model=List[BucketAnalyticsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get bucket analytics list",
    description="Compiles detailed usage statistics (file counts, aggregate sizes, folder counts, and last modified dates) for each connected S3 bucket.",
    responses={
        200: {"description": "Bucket analytics profiles retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_bucket_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[BucketAnalyticsResponse]:
    """Get connected S3 buckets analytics list."""
    service = DashboardService(db, current_user)
    data = service.get_bucket_analytics()
    return [BucketAnalyticsResponse.model_validate(item) for item in data]


@router.get(
    "/folders",
    response_model=List[FolderAnalyticsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get folder analytics list",
    description="Returns detailed nested statistics (nested file counts, aggregate folder sizes recursively, and direct child folder counts) for all virtual folders.",
    responses={
        200: {"description": "Folder analytics profiles retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_folder_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[FolderAnalyticsResponse]:
    """Get virtual folders analytics list."""
    service = DashboardService(db, current_user)
    return service.get_folder_analytics()


@router.get(
    "/recent",
    response_model=RecentActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recent activity log",
    description="Returns a listing of recently uploaded files, connected buckets, and created shared links (up to 10 entries per category).",
    responses={
        200: {"description": "Recent activity logs retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_recent_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecentActivityResponse:
    """Get recent activity summaries."""
    service = DashboardService(db, current_user)
    return service.get_recent_activity()


@router.get(
    "/largest-files",
    response_model=List[LargestFileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get top 10 largest files",
    description="Returns the top 10 largest active files uploaded across all user buckets.",
    responses={
        200: {"description": "Largest files list retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_largest_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[LargestFileResponse]:
    """Get the top 10 largest files."""
    service = DashboardService(db, current_user)
    return service.get_largest_files()


@router.get(
    "/largest-buckets",
    response_model=List[LargestBucketResponse],
    status_code=status.HTTP_200_OK,
    summary="Get top 10 largest buckets",
    description="Returns the top 10 largest connected buckets sorted by aggregate storage usage size.",
    responses={
        200: {"description": "Largest buckets list retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_largest_buckets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[LargestBucketResponse]:
    """Get the top 10 largest buckets."""
    service = DashboardService(db, current_user)
    return service.get_largest_buckets()
