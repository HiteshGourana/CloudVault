"""
backend/services/auth_service.py
──────────────────────────────────
Authentication business logic and the get_current_user FastAPI dependency.

Layer responsibilities:
  AuthService class:
    - register() : validates business rules, hashes password, persists user.
    - login()    : verifies credentials, checks account status, issues JWT.

  get_current_user() function:
    - A FastAPI dependency injected into protected route handlers.
    - Extracts the Bearer token → decodes JWT → loads user from DB.
    - Raises HTTP 401/403 on any failure; returns User on success.

Security notes:
  - login() returns the SAME error message for "user not found" and "wrong password"
    to prevent email enumeration attacks (attacker cannot distinguish the two cases).
  - All authentication failures are logged at WARNING level for monitoring.
  - All successes are logged at SUCCESS level (loguru extension) for audit.

HTTPException ownership:
  All HTTP exceptions originate here (service layer), never in the repository.
  This keeps the repository reusable across different transport layers (HTTP, CLI, etc.)
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.jwt import create_access_token, extract_user_id, http_bearer
from backend.core.security import hash_password, verify_password
from backend.models.user import User
from backend.repositories.user_repo import UserRepository
from backend.schemas.auth import TokenResponse
from backend.schemas.user import UserCreate
from backend.services.activity_service import ActivityService


# ─────────────────────────────────────────────────────────────────────────────
# AuthService — Registration and Login
# ─────────────────────────────────────────────────────────────────────────────


class AuthService:
    """
    Handles all authentication business logic.

    Instantiated once per request — the db Session is scoped to the request.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = UserRepository(db)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, data: UserCreate) -> User:
        """
        Register a new user account.

        Steps:
          1. Check for duplicate email (fast existence query).
          2. Hash the plain-text password using bcrypt.
          3. Persist the new user to the database.

        Args:
            data: Validated UserCreate payload from the request body.

        Returns:
            The newly created User ORM instance.

        Raises:
            HTTPException 409: If the email is already registered.
        """
        if self._repo.exists_by_email(data.email):
            logger.warning(
                "Registration rejected - email already registered | email={}",
                data.email,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        password_hash = hash_password(data.password)

        user = self._repo.create(
            full_name=data.full_name,
            email=data.email,
            password_hash=password_hash,
        )

        logger.success(
            "User registered successfully | id={} email={}",
            str(user.id),
            user.email,
        )

        # Audit log — fire-and-forget, never crash registration on log failure
        try:
            ActivityService.log_activity(
                self._db,
                user_id=user.id,
                action="Register",
                resource_type="user",
                resource_id=str(user.id),
                status_code="success",
                message=f"New user account registered: {user.email}",
            )
        except Exception:
            pass  # Log failure must not block registration

        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> TokenResponse:
        """
        Authenticate a user and issue a JWT access token.

        Steps:
          1. Look up the user by email (None if not found).
          2. Verify password against stored bcrypt hash.
          3. Check the account is active.
          4. Create and return a JWT access token.

        Anti-enumeration design:
          Steps 1 and 2 return the same generic error message.
          An attacker cannot determine whether the email exists.

        Args:
            email:    Raw email from the login request body.
            password: Raw plain-text password from the request body.

        Returns:
            TokenResponse with access_token and token_type.

        Raises:
            HTTPException 401: For any invalid credential combination.
            HTTPException 403: If the account exists but is inactive.
        """
        user = self._repo.get_by_email(email)

        # ── Credential check (constant-time comparison via passlib) ───────────
        # We evaluate verify_password even when user is None to avoid
        # short-circuit timing differences that could leak email existence.
        _dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        password_ok = verify_password(
            password,
            user.password_hash if user is not None else _dummy_hash,
        )

        if user is None or not password_ok:
            logger.warning(
                "Login failed - invalid credentials | email={}", email
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            logger.warning(
                "Login failed - account inactive | id={} email={}",
                str(user.id),
                user.email,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Please contact support.",
            )

        token = create_access_token(subject=str(user.id))

        logger.success(
            "User logged in | id={} email={}", str(user.id), user.email
        )

        # Audit log — fire-and-forget
        try:
            ActivityService.log_activity(
                self._db,
                user_id=user.id,
                action="Login",
                resource_type="user",
                resource_id=str(user.id),
                status_code="success",
                message=f"User authenticated successfully: {user.email}",
            )
        except Exception:
            pass

        return TokenResponse(access_token=token, token_type="bearer")


# ─────────────────────────────────────────────────────────────────────────────
# get_current_user — FastAPI Dependency for Protected Routes
# ─────────────────────────────────────────────────────────────────────────────


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency — authenticates every protected route request.

    Inject into any route that requires authentication:
        @router.get("/protected")
        def my_route(user: User = Depends(get_current_user)):
            ...

    Flow:
      1. HTTPBearer reads "Authorization: Bearer <token>" from the header.
         If the header is absent, credentials=None (auto_error=False).
      2. extract_user_id() decodes the JWT → validates signature + expiry → returns UUID.
      3. UserRepository loads the user from the DB by UUID.
      4. Active check: inactive users are rejected even with a valid token.

    Args:
        credentials: HTTP Bearer credentials extracted by FastAPI, or None.
        db:          Database session (request-scoped, injected via get_db).

    Returns:
        The authenticated, active User ORM instance.

    Raises:
        HTTPException 401: Missing token, invalid token, expired token, user not found.
        HTTPException 403: Valid token but account is deactivated.
    """
    # ── Step 1: Ensure the Authorization header is present ────────────────────
    if credentials is None:
        logger.warning("Protected route accessed without token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── Step 2: Decode JWT and extract user UUID ──────────────────────────────
    user_id: uuid.UUID = extract_user_id(credentials.credentials)

    # ── Step 3: Load user from DB ─────────────────────────────────────────────
    repo = UserRepository(db)
    user = repo.get_by_id(user_id)

    if user is None:
        logger.warning(
            "Auth failed - user not found (stale token?) | id={}", str(user_id)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Your token may be stale — please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── Step 4: Account status check ──────────────────────────────────────────
    if not user.is_active:
        logger.warning(
            "Auth failed - account deactivated | id={} email={}",
            str(user.id),
            user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is deactivated.",
        )

    return user
