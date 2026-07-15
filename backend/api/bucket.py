"""
backend/api/bucket.py
─────────────────────
API routes for Amazon S3 Bucket Management.

Routes registered under prefix /api/v1/buckets:
  GET    /                     — List S3 buckets
  POST   /                     — Create a new S3 bucket
  GET    /{bucket_name}        — Get bucket details (real-time from AWS)
  DELETE /{bucket_name}        — Delete an empty S3 bucket
  POST   /{bucket_name}/exists    — Check if bucket exists and is accessible
  POST   /{bucket_name}/ownership — Check if the connected AWS account owns the bucket

All routes require authentication via `get_current_user`.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.bucket import (
    BucketCreate,
    BucketDeleteResponse,
    BucketDetailsResponse,
    BucketExistsResponse,
    BucketListResponse,
    BucketOwnershipResponse,
    BucketResponse,
)
from backend.services.auth_service import get_current_user
from backend.services.bucket_service import BucketService

router = APIRouter(
    prefix="/buckets",
    tags=["S3 Buckets"],
)


@router.get(
    "",
    response_model=BucketListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all S3 buckets",
    description=(
        "Lists all S3 buckets owned by the connected AWS account. "
        "This checks AWS in real-time, matches against local database tracking records, "
        "and auto-creates database metadata entries for any newly discovered external buckets."
    ),
    responses={
        200: {"description": "S3 buckets listed successfully"},
        401: {"description": "Unauthorized. Invalid or missing JWT token."},
        404: {"description": "AWS account not connected."},
    },
)
def list_buckets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketListResponse:
    """List all S3 buckets."""
    service = BucketService(db, current_user)
    buckets = service.list_buckets()
    
    # Calculate counts
    total = len(buckets)
    # Managed buckets are those created/tracked with known creation_date or bucket_type != unknown
    # But strictly, all listed buckets now get a tracking row. We'll count those with PRIVATE or PUBLIC type.
    managed = sum(1 for b in buckets if b.bucket_type in ("private", "public"))
    
    return BucketListResponse(
        total=total,
        managed=managed,
        buckets=[BucketResponse.model_validate(b) for b in buckets],
    )


@router.post(
    "",
    response_model=BucketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new S3 bucket",
    description=(
        "Creates a new globally unique Amazon S3 bucket. "
        "Validates naming constraints locally and ensures region compatibility. "
        "If successful, a local tracking record is stored in the database."
    ),
    responses={
        201: {"description": "S3 bucket created successfully"},
        400: {"description": "Bad Request. Invalid bucket name, region, or duplicate creation."},
        401: {"description": "Unauthorized."},
        409: {"description": "Conflict. Bucket name already exists globally or is tracked locally."},
        422: {"description": "Validation Error. Invalid bucket name structure."},
    },
)
def create_bucket(
    payload: BucketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketResponse:
    """Create a new S3 bucket."""
    service = BucketService(db, current_user)
    bucket = service.create_bucket(payload)
    return BucketResponse.model_validate(bucket)


@router.get(
    "/{bucket_name}",
    response_model=BucketDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get bucket details",
    description=(
        "Fetches real-time metadata from AWS for a specific bucket, "
        "including versioning status, server-side encryption, and public access blocks. "
        "Also syncs/updates the cached state in the local database."
    ),
    responses={
        200: {"description": "Bucket details retrieved successfully"},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden. IAM credentials lack permissions to fetch details."},
        404: {"description": "Not Found. S3 bucket does not exist or isn't connected."},
    },
)
def get_bucket_details(
    bucket_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketDetailsResponse:
    """Get detailed metadata for a bucket."""
    service = BucketService(db, current_user)
    details, local_db_record = service.get_bucket_details(bucket_name)
    
    # Map S3BucketDetails dataclass + DB attributes to BucketDetailsResponse
    # Derive bucket type if details doesn't have it explicitly as a type
    from backend.services.bucket_service import _derive_bucket_type
    bucket_type = _derive_bucket_type(details.public_access_blocked)
    
    return BucketDetailsResponse(
        bucket_name=details.name,
        region=details.region,
        creation_date=details.creation_date,
        versioning_enabled=details.versioning_enabled,
        versioning_status=details.versioning_status,
        encryption_enabled=details.encryption_enabled,
        encryption_type=details.encryption_type,
        public_access_blocked=details.public_access_blocked,
        bucket_type=bucket_type,
    )


@router.delete(
    "/{bucket_name}",
    response_model=BucketDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete an S3 bucket",
    description=(
        "Permanently deletes an S3 bucket from AWS and removes its tracking record from the local database. "
        "**Normal mode** (`force_empty=false`, default): the bucket must already be empty — "
        "AWS rejects deletion with 409 Conflict if it contains any objects or versions. "
        "**Force mode** (`force_empty=true`): CloudVault first batch-deletes ALL objects "
        "and ALL version markers from the bucket (using S3 `delete_objects` in chunks of 1000), "
        "then deletes the now-empty bucket. ⚠️ This is irreversible — all data will be permanently lost."
    ),
    responses={
        200: {"description": "S3 bucket deleted successfully"},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden. Access denied to delete bucket or its objects."},
        404: {"description": "Not Found. S3 bucket does not exist."},
        409: {"description": "Conflict. Bucket is not empty (only in normal mode)."},
    },
)
def delete_bucket(
    bucket_name: str,
    force_empty: bool = Query(
        False,
        description=(
            "When true, all objects and version markers are deleted first, "
            "then the (now empty) bucket is removed. Irreversible — use with caution."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketDeleteResponse:
    """Delete an S3 bucket, optionally force-emptying it first."""
    service = BucketService(db, current_user)

    if force_empty:
        objects_deleted, versions_deleted = service.force_delete_bucket(bucket_name)
        total = objects_deleted + versions_deleted
        return BucketDeleteResponse(
            message=(
                f"Bucket '{bucket_name}' was force-emptied "
                f"({objects_deleted} object(s) + {versions_deleted} version/marker(s) removed) "
                f"and permanently deleted from AWS S3."
            ),
            bucket_name=bucket_name,
            objects_deleted=objects_deleted,
            versions_deleted=versions_deleted,
        )

    # Normal delete — bucket must be empty
    service.delete_bucket(bucket_name)
    return BucketDeleteResponse(
        message=f"Bucket '{bucket_name}' has been successfully deleted from AWS S3 and tracking database.",
        bucket_name=bucket_name,
        objects_deleted=0,
        versions_deleted=0,
    )



@router.post(
    "/{bucket_name}/exists",
    response_model=BucketExistsResponse,
    status_code=status.HTTP_200_OK,
    summary="Check if bucket exists",
    description=(
        "Queries S3 (via HeadBucket) to determine if a bucket exists globally, "
        "and whether the currently connected AWS credentials have access to it."
    ),
    responses={
        200: {"description": "Bucket existence checked successfully"},
        401: {"description": "Unauthorized."},
    },
)
def check_bucket_exists(
    bucket_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketExistsResponse:
    """Check if bucket exists."""
    service = BucketService(db, current_user)
    result = service.check_exists(bucket_name)
    return BucketExistsResponse(
        bucket_name=bucket_name,
        exists=result["exists"],
        accessible=result["accessible"],
    )


@router.post(
    "/{bucket_name}/ownership",
    response_model=BucketOwnershipResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify bucket ownership",
    description=(
        "Verifies if the currently connected AWS account owns the specified bucket. "
        "This lists the account's S3 buckets and checks for a match."
    ),
    responses={
        200: {"description": "Ownership check completed successfully"},
        401: {"description": "Unauthorized."},
    },
)
def verify_bucket_ownership(
    bucket_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BucketOwnershipResponse:
    """Verify bucket ownership."""
    service = BucketService(db, current_user)
    result = service.verify_ownership(bucket_name)
    return BucketOwnershipResponse(
        bucket_name=bucket_name,
        is_owner=result["is_owner"],
        message=result["message"],
    )
