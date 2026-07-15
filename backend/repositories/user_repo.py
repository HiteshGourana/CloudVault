"""
backend/repositories/user_repo.py
──────────────────────────────────
Data access layer for the users table.

Repository pattern responsibilities:
  - ALL raw database queries live here — nowhere else.
  - No business logic. No HTTP exceptions.
  - Returns ORM objects or None — callers decide what to do with None.
  - Services call repositories; routes call services.

Why this separation?
  - Testability: mock the repo in service tests without touching the DB.
  - Single responsibility: queries in one place, rules in another.
  - Sprint 3+ can add caching here (e.g. Redis) without changing service code.

SQLAlchemy 2.0 notes:
  - Session.get(Model, pk) is the preferred 2.0 API for PK lookups (replaces query().get()).
  - query() is still supported in 2.0 but will be removed in 3.0.
    For non-PK queries, using select() + Session.execute() is 2.0 style.
    We use query() here for readability — refactor to select() in a future sprint.
"""

import uuid

from sqlalchemy.orm import Session

from backend.models.user import User


class UserRepository:
    """
    Encapsulates all database read/write operations for the users table.

    Instantiate with a SQLAlchemy Session (injected via get_db dependency).
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Read Operations ───────────────────────────────────────────────────────

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Fetch a user by UUID primary key.

        Uses Session.get() — SQLAlchemy 2.0 preferred PK lookup.
        Returns None if not found (no exception raised here).

        Args:
            user_id: The user's UUID.

        Returns:
            User instance or None.
        """
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """
        Fetch a user by email address.

        Email is normalised (lowercase + stripped) before querying
        to match how emails are stored at creation time.

        Args:
            email: Raw email string (will be normalised here).

        Returns:
            User instance or None.
        """
        normalised = email.lower().strip()
        return (
            self._db.query(User)
            .filter(User.email == normalised)
            .first()
        )

    def exists_by_email(self, email: str) -> bool:
        """
        Fast existence check without loading the full User object.

        Used during registration to guard against duplicate emails.
        Queries only the id column (SELECT id FROM users WHERE email = ...)
        which is more efficient than SELECT *.

        Args:
            email: Raw email string (will be normalised).

        Returns:
            True if an account with this email exists.
        """
        normalised = email.lower().strip()
        return (
            self._db.query(User.id)
            .filter(User.email == normalised)
            .first()
        ) is not None

    # ── Write Operations ──────────────────────────────────────────────────────

    def create(
        self,
        *,                          # Force keyword-only arguments
        full_name: str,
        email: str,
        password_hash: str,
    ) -> User:
        """
        Insert a new user row and return the committed ORM object.

        Args:
            full_name:     Display name — stored stripped of leading/trailing whitespace.
            email:         Email — stored normalised (lowercase + stripped).
            password_hash: bcrypt hash from security.hash_password().

        Returns:
            The fully populated User instance after commit + refresh.

        Note:
            After db.commit(), the session expires the object. db.refresh()
            re-loads all columns (including server-generated defaults like
            created_at) from the database before returning.
        """
        user = User(
            full_name=full_name.strip(),
            email=email.lower().strip(),
            password_hash=password_hash,
        )
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)  # Reload from DB to get server-generated values
        return user
