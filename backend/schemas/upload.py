"""
backend/schemas/upload.py
─────────────────────────
Pydantic schemas for the Upload Engine module.
"""

import uuid
from typing import Optional
from pydantic import BaseModel, Field

from backend.schemas.file import FileMetadataResponse


class UploadStatusResponse(BaseModel):
    """Response body — GET /api/v1/upload/status/{file_id}"""

    file_id: uuid.UUID = Field(description="Unique file UUID")
    upload_status: str = Field(description="Upload status lifecycle state")
    progress_percentage: float = Field(description="Upload progress percentage (0.0 to 100.0)")
    error_message: Optional[str] = Field(default=None, description="Details of failure if status is Failed")


class UploadResponse(BaseModel):
    """Response body — POST /api/v1/upload/file"""

    message: str = Field(description="Success message confirmation")
    file: FileMetadataResponse = Field(description="Details of uploaded file metadata")


class MultiUploadResponse(BaseModel):
    """Response body — POST /api/v1/upload/files and POST /api/v1/upload/folder"""

    message: str = Field(description="Status confirmation message")
    uploaded_files: list[FileMetadataResponse] = Field(description="Metadata records of successfully uploaded files")
    failed_files: list[str] = Field(description="Names of files that failed validation or transfer")
