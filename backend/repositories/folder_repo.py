"""
backend/repositories/folder_repo.py
───────────────────────────────────
Data access layer for the folders table.
"""

import uuid
from sqlalchemy.orm import Session
from backend.models.folder import Folder


class FolderRepository:
    """Encapsulates all database query and write operations for the folders table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, folder_id: uuid.UUID) -> Folder | None:
        """Fetch folder by its UUID primary key."""
        return self._db.get(Folder, folder_id)

    def get_by_path(self, bucket_id: uuid.UUID, full_path: str) -> Folder | None:
        """Fetch folder by its bucket and S3 prefix path."""
        return (
            self._db.query(Folder)
            .filter(Folder.bucket_id == bucket_id, Folder.full_path == full_path)
            .first()
        )

    def get_all_in_bucket(self, bucket_id: uuid.UUID) -> list[Folder]:
        """Fetch all folders within a bucket, sorted by full path length."""
        return (
            self._db.query(Folder)
            .filter(Folder.bucket_id == bucket_id)
            .order_by(Folder.full_path)
            .all()
        )

    def get_by_parent(self, bucket_id: uuid.UUID, parent_folder_id: uuid.UUID | None) -> list[Folder]:
        """Fetch direct child folders of a parent folder (or root folders if parent is None)."""
        return (
            self._db.query(Folder)
            .filter(Folder.bucket_id == bucket_id, Folder.parent_folder_id == parent_folder_id)
            .order_by(Folder.folder_name)
            .all()
        )

    def exists_sibling_name(self, bucket_id: uuid.UUID, parent_folder_id: uuid.UUID | None, name: str) -> bool:
        """Check if a folder with the same name already exists under the same parent directory."""
        return (
            self._db.query(Folder.id)
            .filter(
                Folder.bucket_id == bucket_id,
                Folder.parent_folder_id == parent_folder_id,
                Folder.folder_name == name,
            )
            .first()
        ) is not None

    def create(
        self,
        *,
        bucket_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        folder_name: str,
        full_path: str,
    ) -> Folder:
        """Insert a new folder record and return the ORM object."""
        folder = Folder(
            bucket_id=bucket_id,
            parent_folder_id=parent_folder_id,
            folder_name=folder_name,
            full_path=full_path,
        )
        self._db.add(folder)
        self._db.commit()
        self._db.refresh(folder)
        return folder

    def delete(self, folder: Folder) -> None:
        """Permanently delete a folder record."""
        self._db.delete(folder)
        self._db.commit()

    def update(self, folder: Folder) -> Folder:
        """Commit updates to a folder object."""
        self._db.commit()
        self._db.refresh(folder)
        return folder
