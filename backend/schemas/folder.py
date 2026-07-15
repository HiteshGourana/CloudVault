"""
backend/schemas/folder.py
─────────────────────────
Pydantic v2 schemas for Virtual Folder Management.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class FolderCreate(BaseModel):
    """Request body — POST /api/v1/folders"""

    bucket_name: str = Field(
        ...,
        description="S3 bucket name where the folder should be created",
        examples=["my-cloudvault-bucket"],
    )
    folder_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Folder display name (e.g., 'reports'). No trailing slashes allowed.",
        examples=["reports"],
    )
    parent_folder_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID of parent folder. If null, the folder is created at the root level.",
        examples=[None],
    )


class FolderRename(BaseModel):
    """Request body — PUT /api/v1/folders/{folder_id}/rename"""

    new_folder_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="New display name of the folder",
        examples=["invoices"],
    )


class FolderMove(BaseModel):
    """Request body — PUT /api/v1/folders/{folder_id}/move"""

    new_parent_folder_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target parent folder UUID. Set to null to move the folder to the bucket root level.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class FolderResponse(BaseModel):
    """Detailed response representation of a single folder record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique folder UUID identifier")
    bucket_id: uuid.UUID = Field(description="Associated local bucket record UUID")
    parent_folder_id: Optional[uuid.UUID] = Field(description="Parent folder record UUID")
    folder_name: str = Field(description="Display name of the folder")
    full_path: str = Field(description="Full path/prefix of the folder ending in a slash")
    created_at: datetime = Field(description="Folder creation timestamp")
    updated_at: datetime = Field(description="Folder modification timestamp")


class FolderDetailsResponse(BaseModel):
    """Response body — GET /api/v1/folders/{folder_id}"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique folder UUID identifier")
    bucket_name: str = Field(description="S3 bucket name")
    folder_name: str = Field(description="Folder display name")
    full_path: str = Field(description="Folder S3 prefix path")
    child_folders_count: int = Field(description="Number of direct sub-folders under this folder")
    created_at: datetime = Field(description="Creation timestamp")


class FolderTreeResponse(BaseModel):
    """Recursive folder hierarchy tree representation."""

    id: uuid.UUID = Field(description="Folder UUID")
    folder_name: str = Field(description="Display name of the folder")
    full_path: str = Field(description="S3 prefix path")
    children: list["FolderTreeResponse"] = Field(
        default=[],
        description="List of child folders nested directly under this folder",
    )


class FolderDeleteResponse(BaseModel):
    """Response body — DELETE /api/v1/folders/{folder_id}"""

    message: str = Field(description="Success message details")
    folder_id: uuid.UUID = Field(description="The UUID of the deleted folder")
