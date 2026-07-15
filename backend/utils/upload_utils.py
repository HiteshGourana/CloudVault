"""
backend/utils/upload_utils.py
─────────────────────────────
Reusable utility functions for file uploads and validations.
"""

import mimetypes
import os
from typing import Optional, Set
from fastapi import HTTPException, status

# ── Blocked File Extensions ──────────────────────────────────────────────────
# Production security: reject potentially executable or harmful files
BLOCKED_EXTENSIONS: Set[str] = {
    ".exe", ".bat", ".sh", ".cmd", ".msi", ".vbs", ".js", ".scr", ".pif", ".cpl", ".reg"
}

# Max upload limit default: 100MB
DEFAULT_MAX_UPLOAD_SIZE = 100 * 1024 * 1024


def validate_file_properties(
    filename: str,
    size_bytes: int,
    content_type: str,
    max_size: int = DEFAULT_MAX_UPLOAD_SIZE,
) -> tuple[str, str]:
    """
    Validates file properties before triggering upload stream.
    
    Checks:
      - Empty filename.
      - Filename length (max 255).
      - Executable extensions (blocked for security).
      - Empty file (0 bytes).
      - Maximum file size.
      - Invalid MIME structure.
      
    Returns:
      Tuple of (cleaned_filename, lowercase_extension)
    """
    if not filename or not filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty.",
        )

    name = filename.strip()
    if len(name) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot exceed 255 characters.",
        )

    # Extract extension
    _, ext = os.path.splitext(name.lower())
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must contain a valid extension (e.g. '.pdf').",
        )

    # Check blocked extensions
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploading files with extension '{ext}' is blocked for security reasons.",
        )

    # Check file sizes
    if size_bytes <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty (0 bytes) and cannot be uploaded.",
        )

    if size_bytes > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed upload size of {max_size / (1024*1024):.0f}MB.",
        )

    # Validate MIME type structure
    if not content_type or "/" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MIME type content format.",
        )

    return name, ext


def generate_unique_filename(
    existing_check_callback,
    folder_name: str,
) -> str:
    """
    Checks if folder_name exists using existing_check_callback.
    If it exists, renames: 'file.txt' -> 'file(1).txt' -> 'file(2).txt'
    until a free filename is found.
    
    Args:
        existing_check_callback: Callable[[str], bool] that returns True if name is taken.
        folder_name: Original target filename.
    """
    if not existing_check_callback(folder_name):
        return folder_name

    base, ext = os.path.splitext(folder_name)
    counter = 1
    
    while True:
        candidate = f"{base}({counter}){ext}"
        if not existing_check_callback(candidate):
            return candidate
        counter += 1
