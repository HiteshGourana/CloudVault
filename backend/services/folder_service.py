"""
backend/services/folder_service.py
──────────────────────────────────
Virtual Folder Management Service for Amazon S3.

Provides hierarchical folder controls over flat S3 keys.
All folders end in a slash (/).
"""

import uuid
from typing import Any, Optional
import boto3
import botocore.exceptions
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.models.folder import Folder
from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.repositories.folder_repo import FolderRepository
from backend.schemas.folder import (
    FolderCreate,
    FolderDetailsResponse,
    FolderMove,
    FolderRename,
    FolderTreeResponse,
)
from backend.services.bucket_service import BucketService, S3BucketOperator


# ── Illegal Folder Name Characters ──────────────────────────────────────────
# Windows/Linux forbidden characters in folder names
_ILLEGAL_CHARACTERS = set('\\/:*?"<>|')


def validate_folder_name(name: str) -> None:
    """
    Validates folder name format.
    
    Rules:
      - Cannot be empty.
      - Cannot contain trailing or leading slashes.
      - Cannot contain illegal filename characters: \\ / : * ? " < > |
      - Max length 255 characters.
    """
    if not name or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder name cannot be empty.",
        )
    
    stripped = name.strip()
    if len(stripped) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder name cannot exceed 255 characters.",
        )

    # Check for illegal characters
    for char in stripped:
        if char in _ILLEGAL_CHARACTERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Folder name contains illegal character: '{char}'",
            )
            
    # S3 specific check: cannot contain duplicate slashes or backslashes
    if "/" in stripped or "\\" in stripped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder name cannot contain slashes. Slashes represent folder separation.",
        )


class FolderService:
    """Orchestrates virtual folder metadata and S3 placeholder objects."""

    def __init__(self, db: Session, current_user: User) -> None:
        self._db = db
        self._user = current_user
        self._folder_repo = FolderRepository(db)
        self._bucket_repo = BucketRepository(db)
        self._aws_repo = AWSAccountRepository(db)

    def _get_s3_client_and_bucket(self, bucket_name: str) -> tuple[Any, Any]:
        """
        Retrieves the initialized boto3 S3 client and the local Bucket ORM model.
        
        Guarantees that the bucket exists in CloudVault database and is owned by the user.
        """
        # Ensure the user has connected an AWS account
        aws_account = self._aws_repo.get_by_user_id(self._user.id)
        if not aws_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AWS account not connected.",
            )

        # Get local bucket record
        bucket = self._bucket_repo.get_by_name(bucket_name)
        if not bucket or bucket.user_id != self._user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bucket '{bucket_name}' not found or not owned by you.",
            )

        # Decrypt credentials to create boto3 operator
        from backend.utils.encryption import CredentialManager
        secret_key = CredentialManager.decrypt(aws_account.secret_access_key_encrypted)
        
        session = boto3.Session(
            aws_access_key_id=aws_account.access_key_id,
            aws_secret_access_key=secret_key,
            region_name=bucket.region,
        )
        s3_client = session.client("s3")
        return s3_client, bucket

    # ── Create Folder ─────────────────────────────────────────────────────────

    def create_folder(self, data: FolderCreate) -> Folder:
        """
        Creates a virtual folder:
          1. Validates folder name format.
          2. Builds full prefix path (ending with /).
          3. Checks sibling name duplicates.
          4. Verifies path size limit (1024).
          5. Creates a 0-byte S3 placeholder key (full_path).
          6. Persists folder entry in DB.
        """
        validate_folder_name(data.folder_name)
        
        s3_client, bucket = self._get_s3_client_and_bucket(data.bucket_name)
        
        # Verify parent exists if provided
        parent_path = ""
        if data.parent_folder_id:
            parent = self._folder_repo.get_by_id(data.parent_folder_id)
            if not parent or parent.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found.",
                )
            parent_path = parent.full_path

        # Generate target S3 key/prefix path
        full_path = f"{parent_path}{data.folder_name.strip()}/"
        
        # Validate path limit
        if len(full_path) > 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder path exceeds S3 maximum key length of 1024 characters.",
            )

        # Check sibling duplicates
        if self._folder_repo.exists_sibling_name(bucket.id, data.parent_folder_id, data.folder_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A folder named '{data.folder_name}' already exists in this directory.",
            )

        try:
            # Create a 0-byte S3 placeholder object for the virtual folder
            s3_client.put_object(
                Bucket=bucket.bucket_name,
                Key=full_path,
                Body=b"",
                ContentType="application/x-directory",
            )
        except botocore.exceptions.ClientError as exc:
            logger.error("Failed to create S3 folder placeholder: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create folder in S3. Check AWS permissions.",
            )

        # Cache metadata in database
        folder = self._folder_repo.create(
            bucket_id=bucket.id,
            parent_folder_id=data.parent_folder_id,
            folder_name=data.folder_name.strip(),
            full_path=full_path,
        )

        logger.success(
            "Folder created successfully | bucket={} path={} user_id={}",
            bucket.bucket_name, full_path, str(self._user.id)
        )
        return folder

    # ── List Folders ──────────────────────────────────────────────────────────

    def list_folders(self, bucket_name: str, parent_id: Optional[uuid.UUID] = None) -> list[Folder]:
        """Lists direct subfolders under a parent folder (or root folders if parent is None)."""
        _, bucket = self._get_s3_client_and_bucket(bucket_name)
        return self._folder_repo.get_by_parent(bucket.id, parent_id)

    # ── Get Folder Tree ───────────────────────────────────────────────────────

    def get_folder_tree(self, bucket_name: str) -> list[FolderTreeResponse]:
        """
        Constructs and returns the full hierarchical folder tree for a bucket.
        Uses cached DB metadata to compile recursively.
        """
        _, bucket = self._get_s3_client_and_bucket(bucket_name)
        all_folders = self._folder_repo.get_all_in_bucket(bucket.id)
        
        # Build lookup table keyed by id
        nodes: dict[uuid.UUID, FolderTreeResponse] = {}
        for f in all_folders:
            nodes[f.id] = FolderTreeResponse(
                id=f.id,
                folder_name=f.folder_name,
                full_path=f.full_path,
                children=[],
            )

        root_nodes: list[FolderTreeResponse] = []
        for f in all_folders:
            node = nodes[f.id]
            if f.parent_folder_id is None:
                root_nodes.append(node)
            else:
                parent_node = nodes.get(f.parent_folder_id)
                if parent_node is not None:
                    parent_node.children.append(node)
                else:
                    # Parent missing from DB cache, treat as root node
                    root_nodes.append(node)

        return root_nodes

    # ── Rename Folder ─────────────────────────────────────────────────────────

    def rename_folder(self, folder_id: uuid.UUID, data: FolderRename) -> Folder:
        """
        Renames a folder:
          1. Validates new folder name.
          2. Verifies folder exists and isn't root.
          3. Checks sibling duplicates.
          4. Copies all S3 objects under the old prefix to the new prefix.
          5. Deletes old S3 keys.
          6. Updates paths recursively for all subfolders in the DB.
        """
        validate_folder_name(data.new_folder_name)
        
        folder = self._folder_repo.get_by_id(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(folder.bucket.bucket_name)
        
        # Verify no duplicate sibling exists
        if self._folder_repo.exists_sibling_name(bucket.id, folder.parent_folder_id, data.new_folder_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A sibling directory named '{data.new_folder_name}' already exists.",
            )

        old_prefix = folder.full_path
        # Compute new path
        parent_path = folder.parent.full_path if folder.parent else ""
        new_prefix = f"{parent_path}{data.new_folder_name.strip()}/"

        # Update S3 objects prefix recursively
        self._s3_rename_prefix(s3_client, bucket.bucket_name, old_prefix, new_prefix)

        # Update folder name in database
        folder.folder_name = data.new_folder_name.strip()
        folder.full_path = new_prefix
        self._folder_repo.update(folder)

        # Recursively update all child folders paths in the database
        self._db_recursive_update_paths(bucket.id, old_prefix, new_prefix)

        logger.success(
            "Folder renamed successfully | old_prefix={} new_prefix={} user_id={}",
            old_prefix, new_prefix, str(self._user.id)
        )
        return folder

    # ── Move Folder ───────────────────────────────────────────────────────────

    def move_folder(self, folder_id: uuid.UUID, data: FolderMove) -> Folder:
        """
        Moves a folder to a new parent:
          1. Verifies folder exists.
          2. Prevents circular movement (cannot move into own subfolder/self).
          3. Sibling duplicate checks.
          4. Copies underlying S3 object keys.
          5. Deletes original S3 objects.
          6. Recursively updates DB records paths.
        """
        folder = self._folder_repo.get_by_id(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found.",
            )

        # Direct move to parent check
        if folder.parent_folder_id == data.new_parent_folder_id:
            return folder

        s3_client, bucket = self._get_s3_client_and_bucket(folder.bucket.bucket_name)

        # Check circular move
        if data.new_parent_folder_id:
            if data.new_parent_folder_id == folder.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder into itself.",
                )
            
            # Trace ancestors of the target parent to check if the folder is in the path
            ancestor_id = data.new_parent_folder_id
            while ancestor_id:
                ancestor = self._folder_repo.get_by_id(ancestor_id)
                if not ancestor:
                    break
                if ancestor.id == folder.id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot move a folder into one of its subfolders (circular move).",
                    )
                ancestor_id = ancestor.parent_folder_id

            target_parent = self._folder_repo.get_by_id(data.new_parent_folder_id)
            if not target_parent or target_parent.bucket_id != bucket.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target parent folder not found.",
                )
            parent_path = target_parent.full_path
        else:
            parent_path = ""

        # Check sibling duplicate names in destination directory
        if self._folder_repo.exists_sibling_name(bucket.id, data.new_parent_folder_id, folder.folder_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A folder named '{folder.folder_name}' already exists in the target directory.",
            )

        old_prefix = folder.full_path
        new_prefix = f"{parent_path}{folder.folder_name}/"

        # Update S3 object keys
        self._s3_rename_prefix(s3_client, bucket.bucket_name, old_prefix, new_prefix)

        # Update database fields
        folder.parent_folder_id = data.new_parent_folder_id
        folder.full_path = new_prefix
        self._folder_repo.update(folder)

        # Recursively update nested child paths in the database
        self._db_recursive_update_paths(bucket.id, old_prefix, new_prefix)

        logger.success(
            "Folder moved successfully | folder={} old_prefix={} new_parent_path={} user_id={}",
            folder.folder_name, old_prefix, new_prefix, str(self._user.id)
        )
        return folder

    # ── Delete Folder ─────────────────────────────────────────────────────────

    def delete_folder(self, folder_id: uuid.UUID) -> None:
        """
        Deletes a virtual folder:
          - Verifies the directory has no database child folders.
          - Queries S3 ListObjects to verify there are no files/keys other than the folder placeholder.
          - If empty, deletes placeholder object in S3 and removes the DB record.
          - If not empty, raises HTTP 409 Conflict.
        """
        folder = self._folder_repo.get_by_id(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found.",
            )

        s3_client, bucket = self._get_s3_client_and_bucket(folder.bucket.bucket_name)

        # 1. DB Empty Check (subfolders exist?)
        children = self._folder_repo.get_by_parent(bucket.id, folder.id)
        if children:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete folder: it contains subfolders. Delete nested folders first.",
            )

        # 2. S3 Empty Check (files exist under this prefix?)
        # List all keys matching the folder's full_path prefix
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket.bucket_name, Prefix=folder.full_path)
            
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    # If we find ANY key that is not exactly the folder placeholder itself, the folder contains files
                    if key != folder.full_path:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Cannot delete folder: it contains files. Delete all files inside first.",
                        )
        except botocore.exceptions.ClientError as exc:
            logger.error("Failed to query objects for deletion check: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to query folder contents on AWS S3.",
            )

        # 3. Perform Deletion
        try:
            # Delete S3 placeholder key
            s3_client.delete_object(Bucket=bucket.bucket_name, Key=folder.full_path)
        except botocore.exceptions.ClientError as exc:
            logger.error("Failed to delete folder placeholder in S3: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete virtual S3 folder placeholder.",
            )

        # Delete database record
        self._folder_repo.delete(folder)

        logger.info(
            "Folder deleted successfully | folder_name={} path={} user_id={}",
            folder.folder_name, folder.full_path, str(self._user.id)
        )

    # ── Get Folder Details ────────────────────────────────────────────────────

    def get_folder_details(self, folder_id: uuid.UUID) -> FolderDetailsResponse:
        """Fetch details about a virtual folder, including child count."""
        folder = self._folder_repo.get_by_id(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found.",
            )
            
        children = self._folder_repo.get_by_parent(folder.bucket_id, folder.id)
        
        return FolderDetailsResponse(
            id=folder.id,
            bucket_name=folder.bucket.bucket_name,
            folder_name=folder.folder_name,
            full_path=folder.full_path,
            child_folders_count=len(children),
            created_at=folder.created_at,
        )

    # ── Private AWS Helper Methods ────────────────────────────────────────────

    def _s3_rename_prefix(self, s3_client: Any, bucket_name: str, old_prefix: str, new_prefix: str) -> None:
        """Copies all keys matching the old_prefix to the new_prefix, then deletes old keys."""
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Prefix=old_prefix)
            
            # Keep track of objects we need to delete
            objects_to_delete = []
            
            for page in pages:
                for obj in page.get("Contents", []):
                    old_key = obj["Key"]
                    # Replace prefix in path
                    suffix = old_key[len(old_prefix):]
                    new_key = f"{new_prefix}{suffix}"
                    
                    # Copy object
                    copy_source = {"Bucket": bucket_name, "Key": old_key}
                    s3_client.copy_object(
                        Bucket=bucket_name,
                        CopySource=copy_source,
                        Key=new_key,
                    )
                    
                    objects_to_delete.append({"Key": old_key})
            
            # Batch delete old objects (boto3 allows up to 1000 keys per call)
            if objects_to_delete:
                # Split delete requests into batches of 1000
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": batch, "Quiet": True},
                    )
        except botocore.exceptions.ClientError as exc:
            logger.error("AWS S3 prefix renaming failed: {}", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to move underlying files or subdirectories on AWS S3.",
            )

    def _db_recursive_update_paths(self, bucket_id: uuid.UUID, old_prefix: str, new_prefix: str) -> None:
        """
        Finds all nested folders under `old_prefix` in the database and updates their `full_path`
        to match the `new_prefix`.
        """
        all_folders = self._folder_repo.get_all_in_bucket(bucket_id)
        for folder in all_folders:
            if folder.full_path.startswith(old_prefix) and folder.full_path != new_prefix:
                suffix = folder.full_path[len(old_prefix):]
                folder.full_path = f"{new_prefix}{suffix}"
                self._folder_repo.update(folder)
