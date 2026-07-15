"""
backend/schemas/share.py
────────────────────────
Pydantic v2 schemas for S3 File Sharing & Secure Access.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class ShareDownloadRequest(BaseModel):
    """Request body — POST /api/v1/share/download"""

    file_id: uuid.UUID = Field(
        ...,
        description="The file UUID to share",
    )
    expiration: str = Field(
        default="1h",
        description="Expiration time window: '15m' (15 mins), '1h' (1 hour), '24h' (24 hours), '7d' (7 days)",
        examples=["15m", "1h", "24h", "7d"],
    )


class ShareUploadRequest(BaseModel):
    """Request body — POST /api/v1/share/upload"""

    bucket_name: str = Field(
        ...,
        description="Target S3 bucket name where the file will be uploaded",
        examples=["my-cloudvault-bucket"],
    )
    folder_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target folder UUID destination path. Null indicates bucket root.",
    )
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Target filename (must include extension)",
        examples=["resume.pdf"],
    )
    expiration: str = Field(
        default="1h",
        description="Expiration time window: '15m', '1h', '24h', '7d'",
        examples=["15m", "1h", "24h", "7d"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class ShareResponse(BaseModel):
    """Full detail response of generated share link record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique shared link record UUID")
    file_id: Optional[uuid.UUID] = Field(description="Shared file UUID. Null for upload sharing.")
    user_id: uuid.UUID = Field(description="UUID of user who generated this share")
    share_token: str = Field(description="Secure unique key token representing the share")
    share_type: str = Field(description="Authorizations type (Download / Upload)")
    expires_at: datetime = Field(description="Expiration timestamp (UTC)")
    is_active: bool = Field(description="True if the share is active and hasn't been revoked")
    created_at: datetime = Field(description="Share link generation timestamp")
    revoked_at: Optional[datetime] = Field(description="Revocation timestamp if manually revoked")
    
    # Pre-Signed details (generated dynamically in-memory, not persisted in DB)
    presigned_url: str = Field(
        description="The generated S3 pre-signed URL (or upload endpoint URL for S3 POST uploads)"
    )
    form_fields: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Required fields dictionary (form parameters) for S3 pre-signed POST uploads",
    )


class ShareHistoryEntry(BaseModel):
    """Individual entry in sharing history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Share record UUID")
    file_id: Optional[uuid.UUID] = Field(description="File UUID if download share")
    file_name: Optional[str] = Field(default=None, description="Shared filename if download share")
    s3_key: Optional[str] = Field(default=None, description="S3 Key location if download share")
    share_type: str = Field(description="Download / Upload")
    created_at: datetime = Field(description="Creation time")
    expires_at: datetime = Field(description="Expiration time")
    is_active: bool = Field(description="True if currently active (not revoked)")
    is_expired: bool = Field(description="True if expired based on current server time")
    revoked_at: Optional[datetime] = Field(description="Revoked timestamp")


class ShareHistoryResponse(BaseModel):
    """Response body — GET /api/v1/share/history"""

    total: int = Field(description="Total count of shares in history")
    active: int = Field(description="Count of currently active (non-expired, non-revoked) shares")
    shares: list[ShareHistoryEntry] = Field(description="History records")


class ShareRevokeResponse(BaseModel):
    """Response body — DELETE /api/v1/share/{share_id}"""

    message: str = Field(description="Revocation confirmation message")
    share_id: uuid.UUID = Field(description="The UUID of the revoked share")
