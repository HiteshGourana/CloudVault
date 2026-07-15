"""
backend/api/file.py
───────────────────
API routes for File Metadata Management.

All routes require authentication via `get_current_user`.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.file import (
    BulkCopyRequest,
    BulkDeleteRequest,
    BulkMoveRequest,
    FileCreateMetadata,
    FileDeleteResponse,
    FileListResponse,
    FileMetadataResponse,
    FileMove,
    FileRename,
    FileTypesResponse,
)
from backend.services.auth_service import get_current_user
from backend.services.file_operations_service import FileOperationsService
from backend.services.file_service import FileService

router = APIRouter(
    prefix="/files",
    tags=["File Metadata"],
)


@router.post(
    "/sync",
    status_code=status.HTTP_200_OK,
    summary="Sync S3 objects into CloudVault",
    description=(
        "Scans the specified S3 bucket for objects not yet tracked in the CloudVault database "
        "and imports them as file metadata records. Useful for files uploaded directly to S3 "
        "bypassing the CloudVault upload flow. This is an opt-in operation — it is no longer "
        "run automatically on every file list request."
    ),
    responses={
        200: {"description": "S3 sync completed."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket not found."},
    },
)
def sync_s3_objects(
    bucket_name: str = Query(..., description="S3 bucket name to sync"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Trigger a manual S3 → CloudVault sync for a bucket."""
    service = FileService(db, current_user)

    bucket = service._bucket_repo.get_by_name(bucket_name)
    if not bucket or not service._is_bucket_owned_by_user(bucket):
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' not found.")

    aws_account = service._aws_repo.get_by_user_id(current_user.id)
    if not aws_account:
        return {"bucket_name": bucket_name, "imported": 0, "message": "No AWS account connected."}

    imported = service._sync_s3_objects(bucket, aws_account)
    return {
        "bucket_name": bucket_name,
        "imported": imported,
        "message": f"S3 sync complete. {imported} new file(s) imported from S3.",
    }


@router.post(
    "",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register file metadata",
    description=(
        "Registers a new file metadata record in the database before the file is uploaded. "
        "Enforces folder existence checks, name conflict checking, and parses extension details. "
        "The status starts as 'Pending' and the file's target S3 key path is computed automatically."
    ),
    responses={
        201: {"description": "File metadata registered successfully."},
        400: {"description": "Bad Request. Invalid extension or path formatting."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket or target parent folder not found."},
        409: {"description": "Conflict. A file with the same name already exists in target folder."},
    },
)
def register_file_metadata(
    payload: FileCreateMetadata,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Register file metadata."""
    service = FileService(db, current_user)
    file_record = service.create_metadata(payload)
    return FileMetadataResponse.model_validate(file_record)


@router.get(
    "",
    response_model=FileListResponse,
    status_code=status.HTTP_200_OK,
    summary="List files metadata",
    description=(
        "Retrieves a paginated list of file metadata records in a bucket. "
        "Supports filtering by folder, extension, and upload status. Excludes deleted files by default. "
        "Includes page, page_size, total_pages, and total_items headers."
    ),
    responses={
        200: {"description": "Files list retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket not found."},
    },
)
def list_files_metadata(
    bucket_name: str = Query(..., description="S3 bucket name"),
    folder_id: Optional[uuid.UUID] = Query(None, description="Specific parent folder UUID"),
    filter_root: bool = Query(
        False, description="If true, ignores folder_id and queries files at the root level only."
    ),
    extension: Optional[str] = Query(None, description="Filter by file extension (e.g. '.pdf' or 'pdf')"),
    status: Optional[str] = Query(None, description="Filter by upload status (Pending/Uploading/Completed/Failed)"),
    page: int = Query(1, ge=1, description="Page index (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query(
        "date", description="Field to sort by: 'name' (filename), 'date' (creation date), 'size' (size), 'extension'"
    ),
    sort_order: str = Query("desc", description="Sort direction: 'asc' (ascending) or 'desc' (descending)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileListResponse:
    """List files metadata with sorting, filtering, and pagination."""
    # Convert Sort By to match database mapping
    db_sort_by = "created_at"
    if sort_by == "name":
        db_sort_by = "name"
    elif sort_by == "size":
        db_sort_by = "size"
    elif sort_by == "extension":
        db_sort_by = "extension"

    service = FileService(db, current_user)
    return service.list_files(
        bucket_name=bucket_name,
        folder_id=folder_id,
        filter_root=filter_root,
        extension=extension,
        status_filter=status,
        page=page,
        page_size=page_size,
        sort_by=db_sort_by,
        sort_order=sort_order.lower(),
    )


@router.get(
    "/types",
    response_model=FileTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated file types summaries",
    description="Returns aggregate counts and size statistics of user files grouped by major extension categories.",
    responses={
        200: {"description": "Aggregate statistics retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_file_types_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileTypesResponse:
    """Get aggregated file types counts."""
    service = FileService(db, current_user)
    return service.get_grouped_file_types()


@router.get(
    "/{file_id}",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get file metadata details",
    description="Fetches full details of a specific active file metadata record by its UUID.",
    responses={
        200: {"description": "File details retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "File metadata not found or soft-deleted."},
    },
)
def get_file_metadata(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Get file metadata."""
    service = FileService(db, current_user)
    file_record = service.get_metadata(file_id)
    return FileMetadataResponse.model_validate(file_record)


@router.get(
    "/{file_id}/download",
    summary="Download file",
    description=(
        "Retrieves a streaming binary response of the file directly from S3. "
        "Verifies user ownership, bucket properties, and AWS S3 object existence before streaming."
    ),
    responses={
        200: {"description": "Streaming file download initiated."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden. Missing read permissions on AWS S3 key."},
        404: {"description": "Not Found. File metadata or S3 object does not exist."},
    },
)
def download_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download a file."""
    service = FileOperationsService(db, current_user)
    return service.download_file(file_id)


@router.put(
    "/{file_id}/rename",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Rename file",
    description=(
        "Renames a file on both AWS S3 and in the local metadata database. "
        "AWS S3 rename is achieved by copying the object to a new key and deleting the old key. "
        "Enforces identical extensions and path duplication checks."
    ),
    responses={
        200: {"description": "File renamed successfully."},
        400: {"description": "Bad Request. Extension mismatch or formatting validation failures."},
        401: {"description": "Unauthorized."},
        404: {"description": "File not found."},
        409: {"description": "Conflict. Filename already exists in folder directory."},
    },
)
def rename_file(
    file_id: uuid.UUID,
    payload: FileRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Rename a file."""
    service = FileOperationsService(db, current_user)
    file_record = service.rename_file(file_id, payload.new_file_name)
    return FileMetadataResponse.model_validate(file_record)


@router.put(
    "/{file_id}/move",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Move file between folders",
    description=(
        "Moves a file to another folder in the same bucket. "
        "Copies the S3 object to the new key prefix path, deletes the old object, and updates DB metadata."
    ),
    responses={
        200: {"description": "File moved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "File or destination folder not found."},
        409: {"description": "Conflict. Duplicate name collision in destination directory."},
    },
)
def move_file(
    file_id: uuid.UUID,
    payload: FileMove,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Move a file."""
    service = FileOperationsService(db, current_user)
    file_record = service.move_file(file_id, payload.new_folder_id)
    return FileMetadataResponse.model_validate(file_record)


@router.post(
    "/{file_id}/copy",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Copy file",
    description=(
        "Copies an S3 object to a target folder, creating a new metadata record in the DB. "
        "Generates a unique filename (with incrementing suffix) if name collisions occur."
    ),
    responses={
        201: {"description": "File copied successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "File or destination parent folder not found."},
    },
)
def copy_file(
    file_id: uuid.UUID,
    destination_folder_id: Optional[uuid.UUID] = Query(
        None, description="Destination folder UUID. Null indicates bucket root level."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Copy a file."""
    service = FileOperationsService(db, current_user)
    file_record = service.copy_file(file_id, destination_folder_id)
    return FileMetadataResponse.model_validate(file_record)


@router.delete(
    "/{file_id}",
    response_model=FileDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete file",
    description=(
        "Soft-deletes file metadata by setting `is_deleted = True`. "
        "The S3 object is kept intact to allow future restoration. "
        "Soft-deleted files are hidden from standard directory listings."
    ),
    responses={
        200: {"description": "File soft-deleted successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "File not found."},
    },
)
def delete_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileDeleteResponse:
    """Soft delete a file."""
    service = FileOperationsService(db, current_user)
    service.soft_delete_file(file_id)
    return FileDeleteResponse(
        message="File has been successfully soft-deleted.",
        file_id=file_id,
    )


@router.post(
    "/{file_id}/restore",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore soft-deleted file",
    description="Restores a soft-deleted file by removing the deletion tags and restoring its status to Completed.",
    responses={
        200: {"description": "File restored successfully."},
        400: {"description": "Bad Request. File is not deleted."},
        401: {"description": "Unauthorized."},
        404: {"description": "File not found."},
        409: {"description": "Conflict. Active file with identical name exists in parent folder."},
    },
)
def restore_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    """Restore a soft-deleted file."""
    service = FileOperationsService(db, current_user)
    file_record = service.restore_file(file_id)
    return FileMetadataResponse.model_validate(file_record)


@router.post(
    "/bulk/delete",
    status_code=status.HTTP_200_OK,
    summary="Bulk soft delete files",
    description="Accepts a list of file UUIDs and soft deletes them sequentially.",
    responses={
        200: {"description": "Bulk delete completed."},
        401: {"description": "Unauthorized."},
    },
)
def bulk_delete_files(
    payload: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk soft delete files."""
    service = FileOperationsService(db, current_user)
    succeeded = service.bulk_delete(payload.file_ids)
    return {
        "message": f"Bulk delete completed. Successfully soft deleted {len(succeeded)} of {len(payload.file_ids)} files.",
        "deleted_file_ids": succeeded,
    }


@router.post(
    "/bulk/move",
    status_code=status.HTTP_200_OK,
    summary="Bulk move files",
    description="Accepts a list of file UUIDs and moves them to a destination parent folder.",
    responses={
        200: {"description": "Bulk move completed."},
        401: {"description": "Unauthorized."},
    },
)
def bulk_move_files(
    payload: BulkMoveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk move files."""
    service = FileOperationsService(db, current_user)
    succeeded, failed = service.bulk_move(payload.file_ids, payload.target_folder_id)
    return {
        "message": "Bulk move completed.",
        "moved_count": len(succeeded),
        "failed_count": len(failed),
        "moved_file_ids": succeeded,
        "failed_file_ids": failed,
    }


@router.post(
    "/bulk/copy",
    status_code=status.HTTP_200_OK,
    summary="Bulk copy files",
    description="Accepts a list of file UUIDs and duplicates them to a target folder.",
    responses={
        200: {"description": "Bulk copy completed."},
        401: {"description": "Unauthorized."},
    },
)
def bulk_copy_files(
    payload: BulkCopyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk copy files."""
    service = FileOperationsService(db, current_user)
    succeeded, failed = service.bulk_copy(payload.file_ids, payload.destination_folder_id)
    return {
        "message": "Bulk copy completed.",
        "copied_count": len(succeeded),
        "failed_count": len(failed),
        "copied_files": [FileMetadataResponse.model_validate(f) for f in succeeded],
        "failed_file_ids": failed,
    }

