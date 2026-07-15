"""
backend/api/enterprise.py
─────────────────────────
API routes for Sprint 10 Enterprise Features:
  - Activity Logs & Audit Trail (/activity)
  - Notifications (/notifications)
  - Global Search (/search)
  - Admin Dashboard (/admin)
  - System Monitoring (/health, /metrics, /system/info)
"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.enterprise import (
    AdminOverviewResponse,
    ActivityLogListResponse,
    ActivityLogResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
    SystemHealthResponse,
    SystemInfoResponse,
    SystemMetricsResponse,
    UnifiedSearchResponse,
)
from backend.services.activity_service import ActivityService
from backend.services.admin_service import AdminService
from backend.services.auth_service import get_current_user
from backend.services.monitoring_service import MonitoringService, increment_request_counter
from backend.services.notification_service import NotificationService
from backend.services.search_service import SearchService

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring Endpoints (Unauthenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=SystemHealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Monitoring"],
    summary="Get system health status",
    description="Validates database connectivity and displays user AWS STS connection health state.",
)
def get_system_health(
    db: Session = Depends(get_db),
    # Optional authentication to check S3 credentials connection status if connected
    current_user: Optional[User] = Depends(get_current_user),
) -> SystemHealthResponse:
    """Get system health."""
    increment_request_counter()
    service = MonitoringService(db, current_user)
    return service.check_health()


@router.get(
    "/metrics",
    response_model=SystemMetricsResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Monitoring"],
    summary="Get system metrics statistics",
    description="Returns approximate active database connections, session statistics, and uptime details.",
)
def get_system_metrics(db: Session = Depends(get_db)) -> SystemMetricsResponse:
    """Get system metrics."""
    increment_request_counter()
    service = MonitoringService(db)
    return service.get_metrics()


@router.get(
    "/system/info",
    response_model=SystemInfoResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Monitoring"],
    summary="Get system configuration details",
    description="Returns deployed environment parameters, application version, and uptime metadata.",
)
def get_system_info(db: Session = Depends(get_db)) -> SystemInfoResponse:
    """Get system configuration info."""
    increment_request_counter()
    service = MonitoringService(db)
    return service.get_system_info()


# ─────────────────────────────────────────────────────────────────────────────
# Activity Logs / Audit Trail Endpoints (Authenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/activity",
    response_model=ActivityLogListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Audit Trails"],
    summary="List and search audit logs",
    description=(
        "Retrieves a paginated list of user activity audit logs. "
        "Supports filtering by action keyword, resource category, date ranges, and status. "
        "Standard users are scoped to their own logs; Administrators can query all user logs globally."
    ),
)
def list_activity_logs(
    action: Optional[str] = Query(None, description="Filter by action keyword (e.g. 'Login')"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (e.g. 'bucket')"),
    status_filter: Optional[str] = Query(None, description="Filter by status ('success', 'failure')"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this timestamp"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this timestamp"),
    page: int = Query(1, ge=1, description="Page index (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Logs per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityLogListResponse:
    """List activity logs."""
    increment_request_counter()
    service = ActivityService(db, current_user)
    return service.search_logs(
        action=action,
        resource_type=resource_type,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/activity/search",
    response_model=ActivityLogListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Audit Trails"],
    summary="Search audit logs alias",
    description="Alias endpoint mapping to GET /activity for search compatibility.",
)
def search_activity_logs(
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityLogListResponse:
    """Search logs alias."""
    return list_activity_logs(
        action=action,
        resource_type=resource_type,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/activity/{id}",
    response_model=ActivityLogResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Audit Trails"],
    summary="Get activity log details",
    description="Returns comprehensive details of an individual activity log record. Standard users are restricted to their own logs.",
)
def get_activity_log_details(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityLogResponse:
    """Get activity log details."""
    increment_request_counter()
    service = ActivityService(db, current_user)
    log_record = service.get_log_by_id(id)
    return ActivityLogResponse.model_validate(log_record)


# ─────────────────────────────────────────────────────────────────────────────
# Notifications Endpoints (Authenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Notifications"],
    summary="List notifications alerts",
    description="Returns unread count along with a listing of all notifications triggered for the authenticated user.",
)
def list_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    """List notifications."""
    increment_request_counter()
    service = NotificationService(db, current_user)
    return service.list_notifications()


@router.put(
    "/notifications/{id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Notifications"],
    summary="Mark notification as read",
    description="Acknowledges an individual notification alert, updating its status to read.",
)
def mark_notification_as_read(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Mark notification as read."""
    increment_request_counter()
    service = NotificationService(db, current_user)
    return service.mark_read(id)


@router.put(
    "/notifications/read-all",
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Notifications"],
    summary="Mark all notifications as read",
    description="Acknowledges all unread notifications of the current user simultaneously.",
)
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark all notifications as read."""
    increment_request_counter()
    service = NotificationService(db, current_user)
    count = service.mark_all_read()
    return {
        "message": f"Successfully marked {count} notifications as read.",
        "updated_count": count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Global Search Endpoints (Authenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/search",
    response_model=UnifiedSearchResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Search"],
    summary="Execute global search",
    description=(
        "Executes a global keyword search across Buckets, virtual Folders, Files, and Shared Links. "
        "Supports query filters by bucket, parent folder, file extension, status, and creation dates."
    ),
)
def execute_global_search(
    q: Optional[str] = Query(None, description="Search keyword query matches on names or tokens"),
    bucket_id: Optional[uuid.UUID] = Query(None, description="Scope search to specific bucket"),
    folder_id: Optional[uuid.UUID] = Query(None, description="Scope search to folder prefix directory"),
    extension: Optional[str] = Query(None, description="Filter by file extension (e.g. '.pdf')"),
    status: Optional[str] = Query(None, description="Filter by file upload status (Pending/Completed)"),
    start_date: Optional[datetime] = Query(None, description="Filter resources created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter resources created before this date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnifiedSearchResponse:
    """Execute unified search."""
    increment_request_counter()
    service = SearchService(db, current_user)
    return service.execute_search(
        keyword=q,
        bucket_id=bucket_id,
        folder_id=folder_id,
        extension=extension,
        status_filter=status,
        start_date=start_date,
        end_date=end_date,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin Dashboard Endpoints (Admin-Only Authenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/admin/dashboard",
    response_model=AdminOverviewResponse,
    status_code=status.HTTP_200_OK,
    tags=["Enterprise Administration"],
    summary="Get admin statistics overview",
    description="Returns global aggregates across all user profiles (user counts, connected AWS accounts, total storage, total files, recent connection logs). Restricted to Admin users.",
)
def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    """Get administrator dashboard statistics."""
    increment_request_counter()
    service = AdminService(db, current_user)
    return service.get_admin_dashboard()
