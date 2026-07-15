"""
backend/schemas/user.py
───────────────────────
Pydantic v2 schemas for User-related request and response bodies.

Schema responsibilities:
  - UserCreate       : Validates incoming registration data.
  - UserResponse     : Shapes outgoing user data (strips password_hash).
  - CurrentUserResponse : Alias for UserResponse used on GET /auth/me.

Pydantic v2 notes:
  - model_config = ConfigDict(from_attributes=True) replaces orm_mode = True.
  - Field(...) with min_length/max_length enforces length at request time,
    before the data ever touches the database.
  - EmailStr requires the `email-validator` package to be installed.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """
    Request body — POST /api/v1/auth/register

    Validation rules applied automatically by Pydantic:
      - full_name : 2–255 characters, stripped of leading/trailing spaces.
      - email     : Must be a syntactically valid email address.
      - password  : 8–128 characters (length only — strength check in service).
    """

    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="User's full display name",
        examples=["Alice Johnson"],
    )
    email: EmailStr = Field(
        ...,
        description="Unique email address used for login",
        examples=["alice@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Account password — minimum 8 characters",
        examples=["SecureP@ss123"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserResponse(BaseModel):
    """
    Response body — POST /api/v1/auth/register

    Never exposes password_hash or any internal security fields.
    from_attributes=True allows Pydantic to read directly from SQLAlchemy
    ORM objects without manual .model_validate() calls.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique user identifier")
    full_name: str = Field(description="User's display name")
    email: str = Field(description="User's email address")
    is_active: bool = Field(description="Whether the account is active")
    created_at: datetime = Field(description="Account creation timestamp (UTC)")


class CurrentUserResponse(UserResponse):
    """
    Response body — GET /api/v1/auth/me

    Identical to UserResponse — kept as a separate class so future sprints
    can add fields (e.g. aws_account_count) without touching UserResponse.
    """

    pass
