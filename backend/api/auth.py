"""
backend/api/auth.py
───────────────────
Authentication API endpoints — thin route handlers only.

Routes registered under prefix /api/v1/auth:
  POST /register — create a new user account
  POST /login    — authenticate and receive a JWT
  GET  /me       — return the current user's profile (protected)
  POST /logout   — stateless logout (JWT discard instruction)

Architecture principle:
  Route handlers contain NO business logic.
  They only:
    1. Accept validated Pydantic input.
    2. Call the service layer.
    3. Return the service result as the HTTP response.

All logic (validation, hashing, DB queries, token creation) lives in
AuthService and UserRepository — not here.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.auth import TokenResponse, UserLogin, TokenWithUserResponse
from backend.schemas.user import CurrentUserResponse, UserCreate, UserResponse
from backend.repositories.user_repo import UserRepository
from backend.services.auth_service import AuthService, get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/auth/register
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new CloudVault account. "
        "Returns the user profile (without password). "
        "**Errors:** `422` for invalid input, `409` if email already registered."
    ),
    responses={
        409: {"description": "Email already registered"},
        422: {"description": "Validation error (invalid email, short password, etc.)"},
    },
)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """
    Register a new user account.

    - Validates email format and password length (handled by Pydantic).
    - Checks for duplicate emails (handled by AuthService).
    - Hashes the password with bcrypt before storage.
    - Returns the created user profile — never returns the password.
    """
    return AuthService(db).register(payload)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/auth/login
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenWithUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and get access token",
    description=(
        "Authenticates the user with email and password. "
        "Returns a JWT Bearer token. "
        "Include the token in subsequent requests: `Authorization: Bearer <token>`. "
        "**Errors:** `401` for invalid credentials, `403` for inactive accounts."
    ),
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "Account is deactivated"},
    },
)
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
) -> TokenWithUserResponse:
    """
    Authenticate and receive a JWT access token.

    The same error is returned for wrong email AND wrong password
    to prevent email enumeration attacks.
    """
    # Authenticate and issue token
    token_resp = AuthService(db).login(payload.email, payload.password)

    # Load the user profile to return alongside the token so the client
    # can initialise session state without an extra request.
    user = UserRepository(db).get_by_email(payload.email)

    return {
        "access_token": token_resp.access_token,
        "token_type": token_resp.token_type,
        "user": user,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/auth/me
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description=(
        "Returns the profile of the currently authenticated user. "
        "**Requires:** `Authorization: Bearer <token>` header. "
        "**Errors:** `401` for missing/invalid/expired token, `403` for inactive account."
    ),
    responses={
        401: {"description": "Missing, invalid, or expired token"},
        403: {"description": "Account is deactivated"},
    },
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Return the authenticated user's profile.

    get_current_user dependency handles all token validation.
    This handler simply returns the resolved user object.
    """
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/auth/logout
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout",
    description=(
        "Stateless logout — instructs the client to discard the JWT. "
        "Because JWTs are stateless, the server cannot invalidate them without "
        "a token blacklist (Redis-backed, planned for a future sprint). "
        "**Client action required:** always discard the token on receipt of this response."
    ),
)
def logout() -> dict[str, str]:
    """
    Instruct the client to discard its JWT.

    This endpoint intentionally does NOT require authentication.
    A client that has lost its token can still call this endpoint cleanly.

    Sprint 3+: implement a Redis-backed token blacklist here.
    """
    return {
        "message": (
            "Logged out successfully. "
            "Please discard your access token on the client side."
        ),
    }
