"""
backend/schemas/enterprise.py
─────────────────────────────
Pydantic v2 schemas for Sprint 10 Enterprise Features.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.bucket import BucketResponse
from backend.schemas.folder import FolderResponse
from backend.schemas.file import FileMetadataResponse
from backend.schemas.share import ShareResponse


# ─────────────────────────────────────────────────────────────────────────────
# Activity & Audit Trail Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ActivityLogResponse(BaseModel):
    """Log entry response for audit trail."""
    
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique activity log UUID")
    user_id: uuid.UUID = Field(description="The user who executed the action")
    action: str = Field(description="Action executed (e.g. 'User Login')")
    resource_type: str = Field(description="Resource category (e.g. 'file', 'bucket')")
    resource_id: Optional[str] = Field(description="UUID or key of target resource")
    status: str = Field(description="Outcome: 'success' or 'failure'")
    message: str = Field(description="Descriptive activity log details")
    ip_address: Optional[str] = Field(description="IP address used")
    user_agent: Optional[str] = Field(description="User agent of the client")
    created_at: datetime = Field(description="Timestamp when event occurred")


class ActivityLogListResponse(BaseModel):
    """Paginated listing wrapper for activity logs."""

    page: int = Field(description="Current page index")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total pages count")
    total_items: int = Field(description="Total matching logs count")
    logs: List[ActivityLogResponse] = Field(description="Matching activity logs")


# ─────────────────────────────────────────────────────────────────────────────
# Notifications Schemas
# ─────────────────────────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    """Notification response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique notification UUID")
    user_id: uuid.UUID = Field(description="Recipient user UUID")
    title: str = Field(description="Short notification title")
    message: str = Field(description="Detailed notification text")
    notification_type: str = Field(description="Alert category")
    is_read: bool = Field(description="True if read by user")
    created_at: datetime = Field(description="Timestamp when alert occurred")


class NotificationListResponse(BaseModel):
    """Unread count + list wrapper for notifications."""

    unread_count: int = Field(description="Count of currently unread notifications")
    notifications: List[NotificationResponse] = Field(description="Notifications list")


class NotificationUnreadCountResponse(BaseModel):
    """Simple unread count response."""

    unread_count: int = Field(description="Count of unread alerts")


# ─────────────────────────────────────────────────────────────────────────────
# Global Search Schemas
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedSearchResponse(BaseModel):
    """Unified search results grouped by resource categories."""

    buckets: List[BucketResponse] = Field(default=[], description="Matching S3 buckets connected")
    folders: List[FolderResponse] = Field(default=[], description="Matching virtual folders")
    files: List[FileMetadataResponse] = Field(default=[], description="Matching files metadata")
    shares: List[ShareResponse] = Field(default=[], description="Matching active shared links")


# ─────────────────────────────────────────────────────────────────────────────
# Admin Dashboard Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AdminRecentAWSConnection(BaseModel):
    """Summary of a recently connected AWS account for admin review."""

    user_id: uuid.UUID = Field(description="User UUID")
    user_email: str = Field(description="User Email")
    aws_account_id: str = Field(description="12-digit AWS Account ID")
    region: str = Field(description="Connected S3 Default Region")
    connected_at: datetime = Field(description="Connection timestamp")


class AdminOverviewResponse(BaseModel):
    """Response body — GET /api/v1/admin/dashboard"""

    total_users: int = Field(description="Total registered users in system")
    connected_aws_accounts: int = Field(description="Total connected user AWS accounts")
    total_buckets: int = Field(description="Total buckets tracked globally")
    total_files: int = Field(description="Total files tracked globally")
    total_storage_bytes: int = Field(description="Sum of file sizes globally in bytes")
    
    # Recents
    recent_registrations: List[Dict[str, Any]] = Field(description="Latest registered users (up to 10)")
    recent_aws_connections: List[AdminRecentAWSConnection] = Field(description="Latest AWS connections (up to 10)")


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring & Health Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SystemHealthResponse(BaseModel):
    """Response body — GET /api/v1/health"""

    status: str = Field(description="General system health: 'healthy' | 'degraded'")
    database: str = Field(description="Database connectivity status: 'online' | 'offline'")
    aws_connectivity: str = Field(description="AWS STS credential handshake validation: 'online' | 'offline' | 'unconnected'")
    timestamp: datetime = Field(description="Current server time (UTC)")


class SystemMetricsResponse(BaseModel):
    """Response body — GET /api/v1/metrics"""

    database_connections_active: int = Field(description="Approximate active DB transactions count")
    total_api_requests_received: int = Field(description="Simulated total requests received since startup")
    active_user_sessions: int = Field(description="Approximate number of logged-in users")
    uptime_seconds: int = Field(description="Uptime duration in seconds")


class SystemInfoResponse(BaseModel):
    """Response body — GET /api/v1/system/info"""

    app_name: str = Field(description="Application title")
    version: str = Field(description="API engine version")
    environment: str = Field(description="Deployment environment (e.g. development, production)")
    uptime_seconds: int = Field(description="Uptime duration in seconds")
    python_version: str = Field(description="Python interpreter version runtime details")
