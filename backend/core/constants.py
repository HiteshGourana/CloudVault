"""
backend/core/constants.py
─────────────────────────
Static project-level constants that never change at runtime.

These are NOT environment-dependent — they are compiled into
the application itself. For environment-dependent values (database
URL, secret key, etc.), see config.py.
"""

# ── Application ──────────────────────────────────────────────
APP_NAME: str = "CloudVault"
APP_VERSION: str = "0.1.0"
APP_DESCRIPTION: str = "AWS S3 Storage Management Platform"

# ── API ──────────────────────────────────────────────────────
API_V1_PREFIX: str = "/api/v1"

# ── Pagination defaults ───────────────────────────────────────
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# ── File upload limits (Sprint 2+) ───────────────────────────
MAX_FILE_SIZE_MB: int = 5_120        # 5 GB
ALLOWED_UPLOAD_CHUNK_SIZE: int = 8 * 1024 * 1024  # 8 MB

# ── Logging ──────────────────────────────────────────────────
LOG_ROTATION_SIZE: str = "10 MB"
LOG_RETENTION_DAYS: str = "30 days"
