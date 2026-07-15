"""
backend/core/config.py
──────────────────────
Centralised application configuration using Pydantic v2 BaseSettings.

How it works:
  - Pydantic reads each field from the environment (or .env file).
  - Field names are CASE-SENSITIVE and must match the keys in .env exactly.
  - @lru_cache ensures Settings() is constructed only once per process,
    making it safe and cheap to call get_settings() anywhere in the codebase.
  - Other modules should import `settings` directly rather than
    instantiating Settings() themselves.

Usage:
    from backend.core.config import settings
    print(settings.DATABASE_URL)
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application settings loaded from environment variables.

    The .env file at the project root is read automatically.
    In production, set these as real environment variables — no .env needed.
    """

    # ── Application ──────────────────────────────────────────
    APP_NAME: str = Field(default="CloudVault", description="Human-readable application name")
    APP_VERSION: str = Field(default="0.1.0", description="Current semantic version")
    DEBUG: bool = Field(default=False, description="Enable debug mode (verbose logs, auto-reload)")

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = Field(
        ...,  # Required — no default, must be set in .env
        description="PostgreSQL connection string: postgresql://user:pass@host:port/dbname",
    )

    # ── Security ─────────────────────────────────────────────
    SECRET_KEY: str = Field(
        ...,  # Required — must be set in .env
        description="Secret key for signing JWT tokens. Generate with: openssl rand -hex 32",
    )
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="JWT token lifetime in minutes"
    )

    # ── AWS ──────────────────────────────────────────────────
    DEFAULT_AWS_REGION: str = Field(
        default="us-east-1", description="Default AWS region for SDK calls"
    )

    # ── Credential Encryption ─────────────────────────────────
    # Used to encrypt AWS secret keys before storing in the database.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    #
    # PRODUCTION WARNING: Storing encrypted credentials in the DB is acceptable
    # for learning/demo. In production, replace this with AWS Secrets Manager
    # or HashiCorp Vault via the CredentialManager abstraction in utils/encryption.py.
    CREDENTIAL_ENCRYPTION_KEY: str = Field(
        ...,
        description=(
            "Fernet symmetric key for encrypting AWS secret keys at rest. "
            "Generate: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ),
    )

    # ── Pydantic Settings Config ──────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",              # Load from .env at project root
        env_file_encoding="utf-8",
        case_sensitive=True,          # APP_NAME ≠ app_name
        extra="ignore",               # Silently ignore unknown env vars
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.

    Cached after first call — thread-safe and process-safe.
    Use this in FastAPI dependency injection:

        def my_route(settings: Settings = Depends(get_settings)):
            ...
    """
    return Settings()


# ── Module-level singleton ────────────────────────────────────
# Import this directly for non-dependency-injection usage:
#   from backend.core.config import settings
settings: Settings = get_settings()
