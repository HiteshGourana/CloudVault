"""
backend/middleware/logger.py
────────────────────────────
Application-wide logging configuration using Loguru.

Why Loguru over the stdlib logging module?
  - Zero-config JSON/structured output support.
  - Built-in log rotation and retention by size or time.
  - Thread-safe by default.
  - Cleaner, more readable API.

Log destinations:
  1. stdout  — human-readable coloured output for local dev / container logs.
  2. File    — rotating file in backend/logs/cloudvault.log for persistence.

Log levels (in ascending severity):
  TRACE → DEBUG → INFO → SUCCESS → WARNING → ERROR → CRITICAL

In production (DEBUG=False):
  - stdout logs at INFO and above.
  - File logs at DEBUG and above (full detail for post-mortem analysis).

In development (DEBUG=True):
  - stdout logs at DEBUG and above (verbose).

Usage:
    from loguru import logger

    logger.info("Server started")
    logger.warning("Low disk space: {space}MB", space=42)
    logger.error("Failed to connect to DB")
    logger.exception("Unhandled exception")   # includes stack trace
"""

import io
import sys
from pathlib import Path

from loguru import logger

from backend.core.constants import LOG_RETENTION_DAYS, LOG_ROTATION_SIZE

# ── Log file destination ──────────────────────────────────────
# Resolve to: CloudVault/backend/logs/cloudvault.log
_LOG_DIR: Path = Path(__file__).parent.parent / "logs"
_LOG_FILE: Path = _LOG_DIR / "cloudvault.log"

# Ensure the logs directory exists at import time.
# The directory is already created by the folder scaffold,
# but this guard makes the module self-contained.
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(debug: bool = False) -> None:
    """
    Initialise all Loguru log handlers.

    Call this ONCE during application startup (inside the FastAPI lifespan).
    Calling it multiple times is safe — existing handlers are removed first.

    Args:
        debug: When True, stdout handler switches from INFO to DEBUG level.
    """
    # Remove the default Loguru handler (writes to stderr with basic format).
    logger.remove()

    # ── Handler 1: Stdout (console) ───────────────────────────
    # Coloured, human-readable output. Perfect for local dev and
    # container log aggregators (Docker, ECS, CloudWatch).
    stdout_level: str = "DEBUG" if debug else "INFO"
    # On Windows, sys.stdout uses cp1252 by default which cannot
    # encode Unicode characters. Wrap sys.stdout.buffer in UTF-8
    # so Loguru can write any Unicode log message safely.
    _stdout_utf8 = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

    logger.add(
        _stdout_utf8,
        level=stdout_level,
        colorize=False,  # Colorize requires a true TTY; disabled to avoid ANSI escape issues on Windows
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <9} | "
            "{name}:{function}:{line} "
            "- {message}"
        ),
        backtrace=True,   # Show full traceback on exceptions
        diagnose=debug,   # Show variable values in tracebacks (dev only)
    )

    # ── Handler 2: Rotating file ──────────────────────────────
    # Always logs at DEBUG regardless of the app mode.
    # Rotates at LOG_ROTATION_SIZE (10 MB), retains for LOG_RETENTION_DAYS (30 days).
    # Old log files are compressed to .zip to save disk space.
    logger.add(
        _LOG_FILE,
        level="DEBUG",
        rotation=LOG_ROTATION_SIZE,
        retention=LOG_RETENTION_DAYS,
        compression="zip",
        enqueue=True,   # Write logs in a background thread — non-blocking
        backtrace=True,
        diagnose=False,  # Never log variable values to file in production
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <9} | "
            "{name}:{function}:{line} — {message}"
        ),
    )

    logger.info(
        "Logging initialised | level={level} | log_file={file}",
        level=stdout_level,
        file=str(_LOG_FILE),
    )
