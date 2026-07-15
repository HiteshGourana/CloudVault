"""
backend/api/share.py
────────────────────
API routes for secure S3 File Sharing and Link Management.

All routes require authentication via get_current_user.
"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.share import (
    ShareDownloadRequest,
    ShareHistoryResponse,
    ShareResponse,
    ShareRevokeResponse,
    ShareUploadRequest,
)
from backend.services.auth_service import get_current_user
from backend.services.sharing_service import SharingService

router = APIRouter(
    prefix="/share",
    tags=["Secure Sharing"],
)


@router.post(
    "/download",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate pre-signed download URL",
    description=(
        "Generates an S3 pre-signed download URL for a file. "
        "The URL expires after the chosen duration (15m, 1h, 24h, 7d). "
        "Validates that the file exists and is owned by the user."
    ),
    responses={
        201: {"description": "Download link generated successfully."},
        400: {"description": "Bad Request. Invalid expiration window."},
        401: {"description": "Unauthorized."},
        404: {"description": "File not found or not owned by you."},
    },
)
def generate_download_link(
    payload: ShareDownloadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareResponse:
    """Generate pre-signed download URL."""
    service = SharingService(db, current_user)
    return service.generate_download_url(payload)


@router.post(
    "/upload",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate pre-signed upload POST fields",
    description=(
        "Generates S3 pre-signed upload POST fields for a file. "
        "This allows third-party clients to upload a file directly to a specific path "
        "in your S3 bucket without disclosing your credentials. "
        "Expires after the chosen duration."
    ),
    responses={
        201: {"description": "Upload policy fields generated successfully."},
        400: {"description": "Bad Request. Invalid path, folder, or expiration."},
        401: {"description": "Unauthorized."},
        404: {"description": "Target bucket or folder not found."},
    },
)
def generate_upload_link(
    payload: ShareUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareResponse:
    """Generate pre-signed upload URL fields."""
    service = SharingService(db, current_user)
    return service.generate_upload_url(payload)


@router.get(
    "",
    response_model=list[ShareResponse],
    status_code=status.HTTP_200_OK,
    summary="List active share links",
    description="Returns a list of all currently active (non-revoked, non-expired) shared links created by you.",
    responses={
        200: {"description": "Active shares list retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def list_active_shares(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ShareResponse]:
    """List active shares."""
    service = SharingService(db, current_user)
    shares = service.list_active_shares()
    # presigned_url and form_fields are not returned in standard lists as they are transient in-memory elements
    # We populate dummy empty fields for schema compliance
    result = []
    for s in shares:
        res = ShareResponse.model_validate(s)
        res.presigned_url = ""
        result.append(res)
    return result


@router.get(
    "/history",
    response_model=ShareHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get sharing history logs",
    description="Returns complete logs of all shares created by the user, including active, revoked, and expired links.",
    responses={
        200: {"description": "Sharing history retrieved successfully."},
        401: {"description": "Unauthorized."},
    },
)
def get_sharing_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareHistoryResponse:
    """Get sharing history."""
    service = SharingService(db, current_user)
    return service.get_sharing_history()


@router.get(
    "/{share_id}",
    response_model=ShareResponse,
    status_code=status.HTTP_200_OK,
    summary="Get share link details",
    description="Returns details for a specific shared link record created by you.",
    responses={
        200: {"description": "Share details retrieved successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Share record not found."},
    },
)
def get_share_details(
    share_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareResponse:
    """Get share details."""
    service = SharingService(db, current_user)
    share = service.get_share_details(share_id)
    res = ShareResponse.model_validate(share)
    res.presigned_url = "" # pre-signed URLs are transient and not cached in standard checks
    return res


@router.delete(
    "/{share_id}",
    response_model=ShareRevokeResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke share link",
    description=(
        "Revokes a shared link in the database. "
        "The link token will be deactivated, and it will no longer show up as active. "
        "Note: Already-issued pre-signed URLs remain valid in S3 until their S3 expiration duration."
    ),
    responses={
        200: {"description": "Share revoked successfully."},
        400: {"description": "Bad Request. Share is already revoked."},
        401: {"description": "Unauthorized."},
        404: {"description": "Share record not found."},
    },
)
def revoke_share(
    share_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareRevokeResponse:
    """Revoke a shared link."""
    service = SharingService(db, current_user)
    service.revoke_share(share_id)
    return ShareRevokeResponse(
        message="Share has been successfully revoked.",
        share_id=share_id,
    )
