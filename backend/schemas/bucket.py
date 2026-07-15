"""
backend/schemas/bucket.py
──────────────────────────
Pydantic v2 schemas for the S3 Bucket Management module.

Sprint 3 schemas:
  - BucketCreate          : POST /buckets request body
  - BucketResponse        : Single bucket in list view (from DB + basic AWS data)
  - BucketListResponse    : Wrapper for GET /buckets response
  - BucketDetailsResponse : GET /buckets/{name} — enriched with real-time AWS data
  - BucketDeleteResponse  : DELETE /buckets/{name} confirmation
  - BucketExistsResponse  : POST /buckets/{name}/exists result
  - BucketOwnershipResponse: POST /buckets/{name}/ownership result

Schema separation:
  BucketResponse (list view) — fast, uses mostly DB-cached data.
  BucketDetailsResponse (detail view) — slower, fetches real-time AWS metadata.
  This design keeps list endpoints fast for accounts with many buckets.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────


class BucketCreate(BaseModel):
    """
    Request body — POST /api/v1/buckets

    Validation:
      - bucket_name is pre-validated by validate_bucket_name() in the service.
        Pydantic strips whitespace only; AWS rules are checked in the service layer.
      - region is validated against VALID_AWS_REGIONS in the service.
    """

    bucket_name: str = Field(
        ...,
        min_length=3,
        max_length=63,
        description="S3 bucket name (globally unique, lowercase, 3-63 chars)",
        examples=["my-cloudvault-bucket", "company-backup-2026"],
    )
    region: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="AWS region where the bucket will be created",
        examples=["us-east-1", "ap-south-1", "eu-west-1"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class BucketResponse(BaseModel):
    """
    Single bucket entry — used in GET /buckets list and POST /buckets response.

    Populated primarily from local DB metadata for speed.
    Fields marked Optional may be None for buckets discovered from AWS
    that were not created through CloudVault (no local DB record exists).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Internal CloudVault record UUID")
    bucket_name: str = Field(description="S3 bucket name")
    region: str = Field(description="AWS region where the bucket resides")
    creation_date: datetime | None = Field(
        description="Bucket creation date from AWS (may be null for discovered buckets)"
    )
    bucket_type: str = Field(description="Visibility: private | public | unknown")
    versioning_enabled: bool = Field(description="Whether S3 versioning is enabled")
    encryption_enabled: bool = Field(description="Whether server-side encryption is configured")
    created_at: datetime = Field(description="When this CloudVault record was created (UTC)")
    updated_at: datetime = Field(description="When this CloudVault record was last updated (UTC)")


class BucketListResponse(BaseModel):
    """Response body — GET /api/v1/buckets"""

    total: int = Field(description="Total number of buckets returned")
    managed: int = Field(description="Buckets tracked in CloudVault DB")
    buckets: list[BucketResponse] = Field(description="List of bucket records")


class BucketDetailsResponse(BaseModel):
    """
    Response body — GET /api/v1/buckets/{bucket_name}

    Always fetches real-time data from AWS for versioning, encryption, and
    public access settings. Slower than BucketResponse but always accurate.
    """

    bucket_name: str = Field(description="S3 bucket name")
    region: str = Field(description="AWS region (fetched real-time from S3)")
    creation_date: datetime | None = Field(description="Bucket creation date from AWS")

    # Versioning
    versioning_enabled: bool = Field(description="True if versioning is currently Enabled")
    versioning_status: str = Field(
        description="Exact versioning state: 'Enabled', 'Suspended', or 'Disabled'"
    )

    # Encryption
    encryption_enabled: bool = Field(description="True if SSE is configured on this bucket")
    encryption_type: str | None = Field(
        description="Encryption algorithm: 'AES256', 'aws:kms', or null if not encrypted"
    )

    # Public access
    public_access_blocked: bool | None = Field(
        description=(
            "True = all four public-access-block settings are enabled (most secure). "
            "False = at least one public access path is open. "
            "null = could not determine (likely missing s3:GetBucketPublicAccessBlock permission)."
        )
    )
    bucket_type: str = Field(description="Derived from public_access_blocked: private | public | unknown")


class BucketDeleteResponse(BaseModel):
    """Response body — DELETE /api/v1/buckets/{bucket_name}"""

    message: str = Field(description="Confirmation message")
    bucket_name: str = Field(description="The name of the deleted bucket")
    objects_deleted: int = Field(default=0, description="Number of S3 objects removed during force-empty (0 for normal delete)")
    versions_deleted: int = Field(default=0, description="Number of S3 object versions/delete-markers removed during force-empty")


class BucketExistsResponse(BaseModel):
    """Response body — POST /api/v1/buckets/{bucket_name}/exists"""

    bucket_name: str = Field(description="The bucket name that was checked")
    exists: bool = Field(
        description=(
            "True if the bucket exists AND is accessible with the connected credentials. "
            "False if the bucket does not exist. "
            "Note: a 403 (access denied) still means the bucket exists globally."
        )
    )
    accessible: bool = Field(
        description="True if the bucket exists and the connected account can access it"
    )


class BucketOwnershipResponse(BaseModel):
    """Response body — POST /api/v1/buckets/{bucket_name}/ownership"""

    bucket_name: str = Field(description="The bucket name that was checked")
    is_owner: bool = Field(
        description=(
            "True if the connected AWS account owns this bucket "
            "(i.e., the bucket appears in list_buckets() for the connected account)."
        )
    )
    message: str = Field(description="Human-readable ownership status")
