"""
backend/schemas/auth.py
───────────────────────
Pydantic v2 schemas for authentication request and response bodies.

Schema responsibilities:
  - UserLogin     : Validates login credentials (email + password).
  - TokenResponse : Shapes the JWT token returned after successful login.

Kept separate from user.py because auth schemas are not user profile schemas —
they serve a different API concern and may diverge in future sprints.
"""

from pydantic import BaseModel, EmailStr, Field
from .user import CurrentUserResponse


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserLogin(BaseModel):
    """
    Request body — POST /api/v1/auth/login

    Both fields are required. Password min_length=1 avoids confusing
    "field required" vs "field too short" error messages on empty input.
    """

    email: EmailStr = Field(
        ...,
        description="Registered email address",
        examples=["alice@example.com"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Account password",
        examples=["SecureP@ss123"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """
    Response body — POST /api/v1/auth/login

    The access_token is a signed JWT Bearer token.
    Include it in subsequent requests as:
      Authorization: Bearer <access_token>

    token_type is always "bearer" — included for OAuth2 spec compliance
    and for clients that consume this field programmatically.
    """

    access_token: str = Field(
        ...,
        description="Signed JWT Bearer access token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type — always 'bearer' for JWT authentication",
    )


class TokenWithUserResponse(TokenResponse):
    """
    Extended token response that includes the authenticated user's profile.

    This is returned by POST /api/v1/auth/login to make it convenient for
    clients to initialise their local session state without an extra call.
    """

    user: CurrentUserResponse
