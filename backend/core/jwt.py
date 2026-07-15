"""
backend/core/jwt.py
───────────────────
JWT token creation, decoding, and FastAPI security scheme.

Token structure (HS256):
  Header  : {"alg": "HS256", "typ": "JWT"}
  Payload : {"sub": "<user_uuid>", "iat": <unix_ts>, "exp": <unix_ts>}
  Signature: HMAC-SHA256(base64(header) + "." + base64(payload), SECRET_KEY)

Why HS256?
  - Symmetric — sign and verify with the same SECRET_KEY.
  - Simple for single-service deployments.
  - Sprint 2+ can upgrade to RS256 (asymmetric) if needed for microservices.

Why HTTPBearer over OAuth2PasswordBearer?
  - Our login endpoint accepts JSON (not OAuth2 form data).
  - HTTPBearer correctly models our flow: client receives a token from /login
    and presents it in the Authorization header on subsequent requests.
  - OAuth2PasswordBearer expects a form-based /token endpoint — wrong pattern here.
  - HTTPBearer adds the padlock icon in Swagger UI, allowing testers to paste
    their JWT token directly.

Usage:
    from backend.core.jwt import create_access_token, extract_user_id, http_bearer

    # Create a token
    token = create_access_token(subject=str(user.id))

    # In a FastAPI dependency
    def get_current_user(creds = Depends(http_bearer)):
        user_id = extract_user_id(creds.credentials)
        ...
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # noqa: F401
from jose import JWTError, jwt

from backend.core.config import settings

# ── Claim Keys ────────────────────────────────────────────────────────────────
_SUBJECT_CLAIM: str = "sub"   # Standard JWT subject claim — stores user UUID
_ISSUED_AT_CLAIM: str = "iat" # Issued-at claim — for audit and token age checks
_EXPIRES_CLAIM: str = "exp"   # Expiry — handled automatically by python-jose

# ── HTTP Bearer Security Scheme ───────────────────────────────────────────────
# auto_error=False: lets get_current_user raise a proper 401 instead of
# the default 403 that FastAPI raises when the header is absent.
http_bearer = HTTPBearer(
    scheme_name="Bearer Token",
    description=(
        "Enter your JWT access token obtained from POST /api/v1/auth/login. "
        "Do NOT include the 'Bearer' prefix — paste the token string only."
    ),
    auto_error=False,  # Disable automatic 403; we raise 401 manually
)


def create_access_token(
    subject: str | uuid.UUID,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed HS256 JWT access token.

    Args:
        subject:       The token subject — the user's UUID string stored in "sub".
        expires_delta: Override the default expiry from settings.

    Returns:
        A compact JWT string: "<header>.<payload>.<signature>"

    Payload example:
        {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "iat": 1719650000,
            "exp": 1719651800
        }
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        _SUBJECT_CLAIM: str(subject),
        _ISSUED_AT_CLAIM: now,
        _EXPIRES_CLAIM: expire,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    python-jose automatically validates:
      - Signature integrity (wrong SECRET_KEY → JWTError)
      - Expiry (past "exp" claim → ExpiredSignatureError, a JWTError subclass)
      - Algorithm match

    Args:
        token: Raw JWT string from the Authorization header.

    Returns:
        The decoded payload dictionary.

    Raises:
        HTTPException 401: If the token is invalid, expired, or tampered with.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def extract_user_id(token: str) -> uuid.UUID:
    """
    Decode a token and extract the user UUID from the "sub" claim.

    Args:
        token: Raw JWT string.

    Returns:
        The user's UUID.

    Raises:
        HTTPException 401: If "sub" is missing, or not a valid UUID string.
    """
    payload = decode_access_token(token)
    subject: str | None = payload.get(_SUBJECT_CLAIM)

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the subject ('sub') claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
