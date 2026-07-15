"""
backend/schemas/file.py
───────────────────────
Pydantic v2 schemas for File Metadata Management.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class FileCreateMetadata(BaseModel):
    """Request body — POST /api/v1/files"""

    bucket_name: str = Field(
        ...,
        description="S3 bucket name where the file will be located",
        examples=["my-cloudvault-bucket"],
    )
    folder_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Parent virtual folder UUID. Null if the file is at the root level.",
        examples=[None],
    )
    file_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="The display name of the file (e.g. 'report.pdf'). Must include extension.",
        examples=["report.pdf"],
    )
    size_bytes: int = Field(
        ...,
        gt=0,
        description="Expected file size in bytes",
        examples=[1048576],
    )
    mime_type: str = Field(
        ...,
        min_length=3,
        max_length=127,
        description="Internet Media Type / Content-Type of the file",
        examples=["application/pdf"],
    )


class FileRename(BaseModel):
    """Request body — PUT /api/v1/files/{file_id}/rename"""

    new_file_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="New display name of the file (must include same extension)",
        examples=["final_report.pdf"],
    )


class FileMove(BaseModel):
    """Request body — PUT /api/v1/files/{file_id}/move"""

    new_folder_id: Optional[uuid.UUID] = Field(
        default=None,
        description="The destination folder UUID. Set to null to move to bucket root.",
        examples=[None],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class FileMetadataResponse(BaseModel):
    """Response representation of a file metadata record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique file UUID")
    bucket_id: uuid.UUID = Field(description="Associated bucket record UUID")
    folder_id: Optional[uuid.UUID] = Field(description="Associated parent virtual folder UUID")
    file_name: str = Field(description="The display name of the file")
    original_file_name: str = Field(description="Original filename on upload request")
    extension: str = Field(description="Lowercase file extension cache including dot")
    mime_type: str = Field(description="Internet Media Type (Content-Type)")
    size_bytes: int = Field(description="File size in bytes")
    s3_key: str = Field(description="Internal storage path key in S3")
    checksum: Optional[str] = Field(description="File integrity hash value")
    storage_class: str = Field(description="AWS S3 storage tier class")
    upload_status: str = Field(description="Upload lifecycle status enum")
    created_at: datetime = Field(description="Registration timestamp")
    updated_at: datetime = Field(description="Last modifications timestamp")


class FileListResponse(BaseModel):
    """Paginated, sorted, and filtered wrapper response for files list."""

    page: int = Field(description="Current page index (1-indexed)")
    page_size: int = Field(description="Number of items returned per page")
    total_pages: int = Field(description="Total count of available pages")
    total_items: int = Field(description="Total count of files matching filters")
    files: list[FileMetadataResponse] = Field(description="List of file metadata records")


class CategorySummary(BaseModel):
    """Summarized file counts and aggregate size for a folder type group."""
    
    count: int = Field(description="Total count of files in this category")
    total_size_bytes: int = Field(description="Aggregate file size in bytes for this category")


class FileTypesResponse(BaseModel):
    """Response body — GET /api/v1/files/types"""

    categories: dict[str, CategorySummary] = Field(
        description="Map of categories: PDF, Images, Videos, Audio, Archives, Documents, Others"
    )


class FileDeleteResponse(BaseModel):
    """Response body — DELETE /api/v1/files/{file_id}"""

    message: str = Field(description="Success message confirmation")
    file_id: uuid.UUID = Field(description="The UUID of the soft-deleted file")


class BulkDeleteRequest(BaseModel):
    """Request body — POST /api/v1/files/bulk/delete"""

    file_ids: list[uuid.UUID] = Field(..., description="List of file UUIDs to soft delete")


class BulkMoveRequest(BaseModel):
    """Request body — POST /api/v1/files/bulk/move"""

    file_ids: list[uuid.UUID] = Field(..., description="List of file UUIDs to move")
    target_folder_id: Optional[uuid.UUID] = Field(
        default=None, description="The destination folder UUID. Set to null to move to bucket root."
    )


class BulkCopyRequest(BaseModel):
    """Request body — POST /api/v1/files/bulk/copy"""

    file_ids: list[uuid.UUID] = Field(..., description="List of file UUIDs to duplicate")
    destination_folder_id: Optional[uuid.UUID] = Field(
        default=None, description="The destination folder UUID. Set to null to copy to bucket root."
    )

