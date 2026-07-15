"""
backend/main.py
───────────────
FastAPI application entry point.

Sprint 0: Health check foundation.
Sprint 1: Authentication routes registered under /api/v1/auth.
Sprint 2: AWS Account connection routes registered under /api/v1/aws.
Sprint 3: Amazon S3 Bucket Management routes registered under /api/v1/buckets.
Sprint 4: Virtual Folder Management routes registered under /api/v1/folders.
Sprint 5: File Metadata Management routes registered under /api/v1/files.
Sprint 6: S3 Upload Engine routes registered under /api/v1/upload.
Sprint 8: Secure File Sharing routes registered under /api/v1/share.
Sprint 9: Dashboard & Analytics routes registered under /api/v1/dashboard.
Sprint 10: Enterprise Features routes (audit, notifications, search, admin, health) registered under /api/v1/.

Lifespan pattern (FastAPI 0.93+):
  Using @asynccontextmanager instead of the deprecated on_event() decorators.
  Code before `yield` runs on startup; code after `yield` runs on shutdown.

Running:
    uvicorn backend.main:app --reload          (development)
    uvicorn backend.main:app --host 0.0.0.0   (production)
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from loguru import logger

from backend.api.auth import router as auth_router
from backend.api.aws import router as aws_router
from backend.api.bucket import router as bucket_router
from backend.api.folder import router as folder_router
from backend.api.file import router as file_router
from backend.api.upload import router as upload_router
from backend.api.share import router as share_router
from backend.api.dashboard import router as dashboard_router
from backend.api.enterprise import router as enterprise_router
from backend.core.config import settings
from backend.core.constants import API_V1_PREFIX, APP_DESCRIPTION, APP_NAME, APP_VERSION
from backend.core.database import check_database_connection
from backend.middleware.logger import setup_logging


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """
    Application lifespan manager.

    Startup:
      1. Initialise logging.
      2. Verify database connectivity (fail-fast on misconfiguration).

    Shutdown:
      1. Log graceful shutdown message.
      (SQLAlchemy connection pool is cleaned up automatically by the engine.)
    """
    # ── Startup ───────────────────────────────────────────────
    setup_logging(debug=settings.DEBUG)

    logger.info("-" * 55)
    logger.info("  {name} v{version} - Starting up", name=APP_NAME, version=APP_VERSION)
    logger.info("  DEBUG mode : {debug}", debug=settings.DEBUG)
    logger.info("-" * 55)

    # Verify database is reachable before accepting traffic.
    db_ok: bool = check_database_connection()
    if db_ok:
        logger.success("Database connection - OK")
    else:
        # Log the warning but do NOT crash here.
        # In production, swap this for a hard raise after DB is provisioned.
        logger.warning(
            "Database connection - FAILED. "
            "Ensure PostgreSQL is running and DATABASE_URL is correct."
        )

    yield  # Application is running — serving requests

    # ── Shutdown ──────────────────────────────────────────────
    logger.info("-" * 55)
    logger.info("  {name} - Shutting down gracefully", name=APP_NAME)
    logger.info("-" * 55)


# ── Application Instance ───────────────────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    # Swagger/ReDoc always available in development.
    # In production, set DOCS_ENABLED=False via environment and guard here.
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ── Routers ────────────────────────────────────────────────────────────────────
# Sprint 1: Authentication
app.include_router(auth_router, prefix=API_V1_PREFIX)

# Sprint 2: AWS Account Connection
app.include_router(aws_router, prefix=API_V1_PREFIX)

# Sprint 3: Amazon S3 Bucket Management
app.include_router(bucket_router, prefix=API_V1_PREFIX)

# Sprint 4: S3 Virtual Folder Management
app.include_router(folder_router, prefix=API_V1_PREFIX)

# Sprint 5: File Metadata Management
app.include_router(file_router, prefix=API_V1_PREFIX)

# Sprint 6: S3 Upload Engine
app.include_router(upload_router, prefix=API_V1_PREFIX)

# Sprint 8: Secure File Sharing
app.include_router(share_router, prefix=API_V1_PREFIX)

# Sprint 9: Dashboard & Analytics
app.include_router(dashboard_router, prefix=API_V1_PREFIX)

# Sprint 10: Enterprise Features
app.include_router(enterprise_router, prefix=API_V1_PREFIX)

# Sprint 11+: Add new routers below following the same pattern:
# app.include_router(log_router,    prefix=API_V1_PREFIX)


# ── Health Check ───────────────────────────────────────────────────────────────
@app.get(
    "/",
    summary="Health Check",
    description="Returns the current operational status of the CloudVault API.",
    tags=["Health"],
)
async def health_check() -> dict[str, Any]:
    """
    GET /

    Confirms the API server is running.
    Used by load balancers and container orchestrators for liveness probes.

    Returns:
        {"status": "running", "project": "CloudVault"}
    """
    logger.debug("Health check requested")
    return {
        "status": "running",
        "project": APP_NAME,
    }
