"""
backend/services/monitoring_service.py
──────────────────────────────────────
Monitoring and System Metrics Service.

Calculates API operational health, checks database connections,
and validates STS connection states.
"""

import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
import boto3
import botocore.exceptions
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.repositories.aws_account_repo import AWSAccountRepository
from backend.repositories.bucket_repo import BucketRepository
from backend.utils.encryption import CredentialManager

# ── Global Server Startup Timestamp ───────────────────────────────────────────
START_TIME = time.time()

# Request Counter cache
API_REQUEST_COUNTER = 0


def increment_request_counter() -> None:
    """Helper to track request counters."""
    global API_REQUEST_COUNTER
    API_REQUEST_COUNTER += 1


class MonitoringService:
    """Retrieves operational diagnostics for the health, metrics, and info routes."""

    def __init__(self, db: Session, current_user: Optional[User] = None) -> None:
        self._db = db
        self._user = current_user
        self._aws_repo = AWSAccountRepository(db)

    def check_health(self) -> dict:
        """
        Runs diagnostics:
          1. Database ping (SELECT 1 query).
          2. AWS STS token call (if user has connected AWS credentials).
        """
        # ── Check DB ──────────────────────────────────────────────────────────
        try:
            self._db.execute(text("SELECT 1"))
            db_status = "online"
        except Exception:
            db_status = "offline"

        # ── Check AWS STS ─────────────────────────────────────────────────────
        aws_status = "unconnected"
        if self._user:
            acc = self._aws_repo.get_by_user_id(self._user.id)
            if acc:
                try:
                    secret_key = CredentialManager.decrypt(acc.secret_access_key_encrypted)
                    client = boto3.client(
                        "sts",
                        aws_access_key_id=acc.access_key_id,
                        aws_secret_access_key=secret_key,
                        region_name=acc.region,
                    )
                    # Verify credentials against AWS
                    client.get_caller_identity()
                    aws_status = "online"
                except Exception:
                    aws_status = "offline"

        # Overall Status
        overall = "healthy"
        if db_status == "offline" or aws_status == "offline":
            overall = "degraded"

        return {
            "status": overall,
            "database": db_status,
            "aws_connectivity": aws_status,
            "timestamp": datetime.now(timezone.utc),
        }

    def get_metrics(self) -> dict:
        """Calculates system metrics, request counts, and active connections."""
        uptime = int(time.time() - START_TIME)
        
        # Approximate DB connection pool stats
        active_conns = 1
        try:
            # PostgreSQL connection query
            res = self._db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
            active_conns = int(res) if res is not None else 1
        except Exception:
            pass

        return {
            "database_connections_active": active_conns,
            "total_api_requests_received": API_REQUEST_COUNTER,
            "active_user_sessions": 1,  # Mock estimate session counter
            "uptime_seconds": uptime,
        }

    def get_system_info(self) -> dict:
        """Returns hardware, library, and application config details."""
        uptime = int(time.time() - START_TIME)
        from backend.core.config import settings
        
        return {
            "app_name": "CloudVault API",
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT,
            "uptime_seconds": uptime,
            "python_version": sys.version,
        }
