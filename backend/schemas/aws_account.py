"""
backend/schemas/aws_account.py
───────────────────────────────
Pydantic v2 schemas for the AWS Account Connection module.

Sprint 2 schemas:
  - AWSConnectRequest      : Validates incoming credentials for POST /aws/connect.
  - AWSAccountResponse     : Outgoing account info — NEVER includes secret_access_key.
  - AWSDisconnectResponse  : Confirmation message for DELETE /aws/disconnect.

Security contract enforced by schemas:
  - secret_access_key is accepted in AWSConnectRequest (input).
  - secret_access_key is NEVER present in any response schema.
  - access_key_id IS included in responses (it is not a secret — visible in CloudTrail).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class AWSConnectRequest(BaseModel):
    """
    Request body — POST /api/v1/aws/connect

    Accepts AWS IAM long-lived credentials.

    Validation rules:
      - access_key_id  : AWS access key IDs are 16–128 chars, typically 20 chars
                         starting with "AKIA" (permanent) or "ASIA" (temporary).
      - secret_access_key : 40+ character base64 string. No length cap enforced
                            here — let boto3/STS detect format errors.
      - region         : AWS region slug (e.g., "us-east-1", "ap-south-1").
                         Format validated at the service layer via boto3.
    """

    access_key_id: str = Field(
        ...,
        min_length=16,
        max_length=128,
        description="AWS IAM Access Key ID (starts with AKIA or ASIA)",
        examples=["AKIAIOSFODNN7EXAMPLE"],
    )
    secret_access_key: str = Field(
        ...,
        min_length=1,
        description="AWS IAM Secret Access Key — stored encrypted, never returned in responses",
        examples=["wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"],
    )
    region: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="AWS region slug where credentials will be verified",
        examples=["ap-south-1", "us-east-1", "eu-west-1"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class AWSAccountResponse(BaseModel):
    """
    Response body — POST /api/v1/aws/connect and GET /api/v1/aws/status

    Returns all account metadata EXCEPT the secret_access_key.
    The access_key_id is included — it is not sensitive (visible in CloudTrail).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Internal record UUID")
    aws_account_id: str = Field(description="12-digit AWS account ID")
    iam_arn: str = Field(description="Full IAM ARN of the connected identity")
    iam_user_name: str | None = Field(
        description="IAM username — null for root or role-based credentials"
    )
    region: str = Field(description="Connected AWS region")
    access_key_id: str = Field(description="AWS Access Key ID (not a secret)")
    is_connected: bool = Field(description="Whether the connection is active")
    connected_at: datetime = Field(description="Last successful connection timestamp (UTC)")
    updated_at: datetime = Field(description="Last record update timestamp (UTC)")


class AWSConnectResponse(BaseModel):
    """
    Response body — POST /api/v1/aws/connect (wraps AWSAccountResponse with a message)
    """

    message: str = Field(description="Human-readable result message")
    account: AWSAccountResponse = Field(description="Connected account details")


class AWSDisconnectResponse(BaseModel):
    """
    Response body — DELETE /api/v1/aws/disconnect
    """

    message: str = Field(description="Disconnect confirmation message")
