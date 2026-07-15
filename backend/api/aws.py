"""
backend/api/aws.py
──────────────────
AWS Account Connection API endpoints.

Routes registered under prefix /api/v1/aws:
  POST   /connect     — verify credentials and connect the AWS account
  GET    /status      — return the connected AWS account information
  DELETE /disconnect  — remove the AWS account connection

All routes are protected by get_current_user (JWT Bearer token required).
Route handlers are thin — all logic is in AWSAccountService.

HTTP status codes:
  201 Created   — POST /connect (first-time connection)
  200 OK        — POST /connect (reconnection / credential update)
  200 OK        — GET /status
  200 OK        — DELETE /disconnect
  401           — Missing or invalid JWT
  404           — No AWS account connected (status, disconnect)
  401/403/400   — AWS credential errors (connect)
  503           — AWS endpoint unreachable (connect)
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.aws_account import (
    AWSAccountResponse,
    AWSConnectRequest,
    AWSConnectResponse,
    AWSDisconnectResponse,
)
from backend.services.auth_service import get_current_user
from backend.services.aws_service import AWSAccountService

router = APIRouter(
    prefix="/aws",
    tags=["AWS Account"],
)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/aws/connect
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=AWSConnectResponse,
    summary="Connect AWS account",
    description=(
        "Verifies the provided IAM credentials by calling **AWS STS GetCallerIdentity**, "
        "then stores the account information securely. "
        "If an AWS account is already connected, the existing connection is updated "
        "with the new credentials (reconnect). "
        "\n\n"
        "**What GetCallerIdentity does:** Validates the credentials signature and returns "
        "the AWS account ID, IAM ARN, and user identity — no special IAM permissions required. "
        "\n\n"
        "**Security:** The secret access key is encrypted with AES-128 (Fernet) before storage "
        "and is NEVER returned in any API response. "
        "\n\n"
        "**Errors:** `401` invalid credentials, `403` access denied, `503` network/region error."
    ),
    responses={
        201: {"description": "AWS account connected for the first time"},
        200: {"description": "Existing AWS connection updated (reconnected)"},
        401: {"description": "Invalid AWS Access Key ID or Secret Access Key"},
        403: {"description": "AWS Access Denied"},
        400: {"description": "Invalid region or request format"},
        503: {"description": "Could not reach AWS STS endpoint"},
    },
)
def connect_aws_account(
    payload: AWSConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AWSConnectResponse:
    """
    POST /api/v1/aws/connect

    Returns HTTP 201 for first-time connections, 200 for updates.
    The response status cannot be set dynamically with response_model alone,
    so we set status_code per call using the Response object is an advanced
    pattern — for now both first connect and reconnect return 200 for simplicity.
    The message field distinguishes the two cases.
    """
    service = AWSAccountService(db=db, current_user=current_user)
    account, created = service.connect(payload)

    message = (
        "AWS account connected successfully."
        if created
        else "AWS account updated successfully. Credentials have been refreshed."
    )

    return AWSConnectResponse(
        message=message,
        account=AWSAccountResponse.model_validate(account),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/aws/status
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=AWSAccountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get connected AWS account",
    description=(
        "Returns information about the currently connected AWS account. "
        "The secret access key is NEVER returned — only the access key ID is shown. "
        "\n\n"
        "**Errors:** `404` if no AWS account has been connected."
    ),
    responses={
        404: {"description": "No AWS account connected"},
    },
)
def get_aws_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AWSAccountResponse:
    """GET /api/v1/aws/status"""
    service = AWSAccountService(db=db, current_user=current_user)
    account = service.get_status()
    return AWSAccountResponse.model_validate(account)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/aws/disconnect
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/disconnect",
    response_model=AWSDisconnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect AWS account",
    description=(
        "Permanently removes the connected AWS account from CloudVault. "
        "The stored credentials are deleted from the database. "
        "Your CloudVault account remains active — only the AWS connection is removed. "
        "\n\n"
        "To reconnect, call POST /api/v1/aws/connect again. "
        "\n\n"
        "**Errors:** `404` if no AWS account is currently connected."
    ),
    responses={
        404: {"description": "No AWS account connected"},
    },
)
def disconnect_aws_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AWSDisconnectResponse:
    """DELETE /api/v1/aws/disconnect"""
    service = AWSAccountService(db=db, current_user=current_user)
    service.disconnect()
    return AWSDisconnectResponse(
        message="AWS account disconnected successfully. Your credentials have been removed."
    )
