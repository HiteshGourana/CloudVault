"""
backend/api/folder.py
─────────────────────
API routes for S3 Virtual Folder Management.

All routes require authentication via `get_current_user`.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.folder import (
    FolderCreate,
    FolderDeleteResponse,
    FolderDetailsResponse,
    FolderMove,
    FolderRename,
    FolderResponse,
    FolderTreeResponse,
)
from backend.services.auth_service import get_current_user
from backend.services.folder_service import FolderService

router = APIRouter(
    prefix="/folders",
    tags=["S3 Virtual Folders"],
)


@router.post(
    "",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new virtual folder",
    description=(
        "Creates a virtual folder in S3 by uploading a 0-byte directory placeholder object "
        "and caching the metadata in the database. Folder names cannot contain slashes or illegal characters."
    ),
    responses={
        201: {"description": "Folder created successfully."},
        400: {"description": "Bad Request. Invalid parameters or parent directory constraint violations."},
        401: {"description": "Unauthorized."},
        409: {"description": "Conflict. A folder with the same name already exists in this folder path."},
    },
)
def create_folder(
    payload: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FolderResponse:
    """Create a virtual folder."""
    service = FolderService(db, current_user)
    folder = service.create_folder(payload)
    return FolderResponse.model_validate(folder)


@router.get(
    "",
    response_model=list[FolderResponse],
    status_code=status.HTTP_200_OK,
    summary="List folders",
    description=(
        "Lists direct child folders inside a bucket. Supports optional filtering by parent folder UUID. "
        "If parent_folder_id is omitted or null, lists root-level folders."
    ),
    responses={
        200: {"description": "Subfolders list retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket not found."},
    },
)
def list_folders(
    bucket_name: str = Query(..., description="S3 bucket name"),
    parent_folder_id: Optional[uuid.UUID] = Query(
        None, description="Filter by parent folder UUID. If null, displays root-level folders."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FolderResponse]:
    """List sub-folders in directory."""
    service = FolderService(db, current_user)
    folders = service.list_folders(bucket_name, parent_folder_id)
    return [FolderResponse.model_validate(f) for f in folders]


@router.get(
    "/tree",
    response_model=list[FolderTreeResponse],
    status_code=status.HTTP_200_OK,
    summary="Get hierarchical folder tree",
    description=(
        "Builds and returns a complete nested hierarchical directory tree "
        "of all folders within the specified S3 bucket."
    ),
    responses={
        200: {"description": "Hierarchical folder tree retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Bucket not found."},
    },
)
def get_folder_tree(
    bucket_name: str = Query(..., description="S3 bucket name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FolderTreeResponse]:
    """Get the full folder tree."""
    service = FolderService(db, current_user)
    return service.get_folder_tree(bucket_name)


@router.get(
    "/{folder_id}",
    response_model=FolderDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get folder details",
    description="Returns detailed metadata of a specific virtual folder, including child count.",
    responses={
        200: {"description": "Folder details retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Folder not found."},
    },
)
def get_folder_details(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FolderDetailsResponse:
    """Get virtual folder details."""
    service = FolderService(db, current_user)
    return service.get_folder_details(folder_id)


@router.put(
    "/{folder_id}/rename",
    response_model=FolderResponse,
    status_code=status.HTTP_200_OK,
    summary="Rename folder",
    description=(
        "Renames a virtual folder. This copies all S3 object prefixes inside the folder "
        "to the new prefix, deletes the old objects on S3, and recursively updates DB cache paths."
    ),
    responses={
        200: {"description": "Folder renamed successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Folder not found."},
        409: {"description": "Conflict. Folder with the same name already exists in target directory."},
    },
)
def rename_folder(
    folder_id: uuid.UUID,
    payload: FolderRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FolderResponse:
    """Rename a virtual folder."""
    service = FolderService(db, current_user)
    folder = service.rename_folder(folder_id, payload)
    return FolderResponse.model_validate(folder)


@router.put(
    "/{folder_id}/move",
    response_model=FolderResponse,
    status_code=status.HTTP_200_OK,
    summary="Move folder",
    description=(
        "Moves a virtual folder to another parent directory. "
        "Copies S3 prefixes, deletes old objects, and updates DB paths recursively. "
        "Validates against circular hierarchy loops (moving directory into its subfolders)."
    ),
    responses={
        200: {"description": "Folder moved successfully."},
        400: {"description": "Bad Request. Circular movement detected or invalid targets."},
        401: {"description": "Unauthorized."},
        404: {"description": "Folder or target parent folder not found."},
        409: {"description": "Conflict. Sibling directory collision in target path."},
    },
)
def move_folder(
    folder_id: uuid.UUID,
    payload: FolderMove,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FolderResponse:
    """Move a virtual folder."""
    service = FolderService(db, current_user)
    folder = service.move_folder(folder_id, payload)
    return FolderResponse.model_validate(folder)


@router.delete(
    "/{folder_id}",
    response_model=FolderDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete an empty folder",
    description=(
        "Deletes an empty virtual folder. If the folder contains subfolders or files "
        "registered on S3 under its prefix path, the operation is blocked with a 409 Conflict error. "
        "CloudVault does not perform silent or recursive data deletion to protect user content."
    ),
    responses={
        200: {"description": "Folder deleted successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Folder not found."},
        409: {"description": "Conflict. Folder is not empty."},
    },
)
def delete_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FolderDeleteResponse:
    """Delete an empty virtual folder."""
    service = FolderService(db, current_user)
    service.delete_folder(folder_id)
    return FolderDeleteResponse(
        message="Folder has been successfully deleted from AWS S3 and tracking database.",
        folder_id=folder_id,
    )
