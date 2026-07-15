"""
backend/api/upload.py
─────────────────────
API routes for the CloudVault S3 Upload Engine.

All routes require authentication via `get_current_user`.
"""

import asyncio
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.file import FileMetadataResponse
from backend.schemas.upload import MultiUploadResponse, UploadResponse, UploadStatusResponse
from backend.services.auth_service import get_current_user
from backend.services.upload_service import UploadService

router = APIRouter(
    prefix="/upload",
    tags=["S3 Upload Engine"],
)


@router.post(
    "/file",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single file",
    description=(
        "Uploads a single file to S3 using multipart form-data. "
        "Extracts extensions, validates sizes, applies unique name resolutions, "
        "and updates the database lifecycle metadata status upon completion."
    ),
    responses={
        201: {"description": "File uploaded and registered successfully."},
        400: {"description": "Bad Request. Size validation or extension checks failed."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket or parent folder directory not found."},
        409: {"description": "Conflict. Filename duplication under 'reject' strategy."},
        413: {"description": "Request Entity Too Large. Exceeds max 100MB limit."},
    },
)
async def upload_single_file(
    file: UploadFile,
    bucket_name: str = Form(..., description="Target S3 bucket name"),
    folder_id: Optional[uuid.UUID] = Form(None, description="Parent folder UUID. Null indicates bucket root."),
    duplicate_strategy: str = Form(
        "rename", description="Duplication handling strategy: 'rename' (auto-rename), 'overwrite', or 'reject'."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Upload a single file (non-blocking async handler)."""
    service = UploadService(db, current_user)
    # Offload blocking boto3 S3 I/O to a thread so the event loop stays free
    file_record = await asyncio.to_thread(
        service.upload_file,
        bucket_name,
        folder_id,
        file,
        duplicate_strategy,
    )
    return UploadResponse(
        message="File uploaded successfully.",
        file=FileMetadataResponse.model_validate(file_record),
    )


@router.post(
    "/files",
    response_model=MultiUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload multiple files",
    description=(
        "Uploads a list of files sequentially. "
        "Returns a list of successfully registered files and names of those that failed."
    ),
    responses={
        200: {"description": "Multi-upload batch complete."},
        401: {"description": "Unauthorized."},
    },
)
async def upload_multiple_files(
    files: List[UploadFile],
    bucket_name: str = Form(..., description="Target S3 bucket name"),
    folder_id: Optional[uuid.UUID] = Form(None, description="Parent folder UUID"),
    duplicate_strategy: str = Form("rename", description="Duplication strategy: rename, overwrite, or reject"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MultiUploadResponse:
    """Upload multiple files in parallel (non-blocking async handler)."""
    service = UploadService(db, current_user)
    # upload_multiple_files uses ThreadPoolExecutor internally;
    # wrap in asyncio.to_thread so we don't block the event loop.
    succeeded, failed = await asyncio.to_thread(
        service.upload_multiple_files,
        bucket_name,
        folder_id,
        files,
        duplicate_strategy,
    )
    return MultiUploadResponse(
        message="Multi-upload batch completed.",
        uploaded_files=[FileMetadataResponse.model_validate(f) for f in succeeded],
        failed_files=failed,
    )


@router.post(
    "/folder",
    response_model=MultiUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a local folder structure",
    description=(
        "Uploads multiple files while reconstructing local directory structures. "
        "Accepts a matching list of relative path values. Re-creates missing folders "
        "inside the DB and on S3 automatically before transferring contents."
    ),
    responses={
        200: {"description": "Folder hierarchy upload complete."},
        401: {"description": "Unauthorized."},
    },
)
async def upload_folder_structure(
    files: List[UploadFile],
    relative_paths: List[str] = Form(..., description="Matching list of relative file paths (e.g. 'docs/resume.pdf')"),
    bucket_name: str = Form(..., description="Target S3 bucket name"),
    folder_id: Optional[uuid.UUID] = Form(None, description="Target parent destination UUID"),
    duplicate_strategy: str = Form("rename", description="Duplication strategy: rename, overwrite, or reject"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MultiUploadResponse:
    """Upload a folder structure (non-blocking async handler)."""
    service = UploadService(db, current_user)
    succeeded, failed = await asyncio.to_thread(
        service.upload_folder,
        bucket_name,
        folder_id,
        files,
        relative_paths,
        duplicate_strategy,
    )
    return MultiUploadResponse(
        message="Folder upload complete.",
        uploaded_files=[FileMetadataResponse.model_validate(f) for f in succeeded],
        failed_files=failed,
    )


@router.get(
    "/status/{file_id}",
    response_model=UploadStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get upload status",
    description="Returns real-time progress percentages and error details for active uploads.",
    responses={
        200: {"description": "Status and progress retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "File not found."},
    },
)
def get_upload_status(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadStatusResponse:
    """Get upload status."""
    service = UploadService(db, current_user)
    status_info = service.get_upload_status(file_id)
    return UploadStatusResponse(
        file_id=status_info["file_id"],
        upload_status=status_info["upload_status"],
        progress_percentage=status_info["progress_percentage"],
        error_message=status_info["error_message"],
    )


@router.post(
    "/retry/{file_id}",
    status_code=status.HTTP_200_OK,
    summary="Retry a failed upload",
    description=(
        "Attempts to retry a failed upload. "
        "If the file is already found on S3, heals the record to 'Completed'. "
        "Otherwise, resets the status back to 'Pending' so the client can re-upload."
    ),
    responses={
        200: {"description": "Retry request processed."},
        400: {"description": "Bad Request. File is not in Failed state."},
        401: {"description": "Unauthorized."},
        404: {"description": "File metadata not found."},
    },
)
def retry_failed_upload(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retry failed upload."""
    service = UploadService(db, current_user)
    result = service.retry_upload(file_id)
    # Return dynamic response based on healing outcome
    return {
        "message": result["message"],
        "file": FileMetadataResponse.model_validate(result["file"]),
    }
