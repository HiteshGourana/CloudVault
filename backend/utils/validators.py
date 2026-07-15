"""
backend/utils/validators.py
─────────────────────────────
Reusable input validators for CloudVault.

Sprint 3 — Bucket name and AWS region validation.

AWS Bucket Naming Rules (enforced here before any API call):
  1. 3–63 characters
  2. Lowercase letters (a-z), digits (0-9), hyphens (-) ONLY
  3. Must START with a letter or digit
  4. Must END with a letter or digit (no trailing hyphen)
  5. Cannot look like an IPv4 address (e.g., 192.168.1.1)
  6. No uppercase letters (AWS rejects with InvalidBucketName)
  7. No underscores, dots for new buckets (dot-separated names were supported
     in old virtual-hosted URLs but are discouraged — enforcing hyphen-only)

Validating before calling AWS saves a round-trip to S3 and gives a clearer
error message than the generic AWS error response.

References:
  https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
"""

import re

from fastapi import HTTPException, status

# ── Compiled Patterns ─────────────────────────────────────────────────────────
_BUCKET_NAME_RE = re.compile(
    r"^[a-z0-9]"        # Must start with lowercase letter or digit
    r"[a-z0-9\-]*"      # Middle: any combo of letters, digits, hyphens
    r"[a-z0-9]$"        # Must end with lowercase letter or digit
)

# IPv4 address pattern — bucket names cannot look like an IP address
_IP_ADDRESS_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# ── Supported AWS Regions ─────────────────────────────────────────────────────
# Maintained manually — new regions should be added as AWS announces them.
# We validate regions client-side to give a faster, clearer error than boto3's
# EndpointConnectionError (which can take up to 30 seconds to time out).
VALID_AWS_REGIONS: frozenset[str] = frozenset(
    {
        # North America
        "us-east-1", "us-east-2",
        "us-west-1", "us-west-2",
        "ca-central-1", "ca-west-1",
        # South America
        "sa-east-1",
        # Europe
        "eu-central-1", "eu-central-2",
        "eu-west-1", "eu-west-2", "eu-west-3",
        "eu-north-1", "eu-south-1", "eu-south-2",
        # Asia Pacific
        "ap-east-1",
        "ap-south-1", "ap-south-2",
        "ap-southeast-1", "ap-southeast-2", "ap-southeast-3", "ap-southeast-4",
        "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
        # Middle East & Africa
        "me-south-1", "me-central-1",
        "af-south-1",
        "il-central-1",
    }
)


def validate_bucket_name(name: str) -> None:
    """
    Validate an S3 bucket name against AWS naming rules.

    Raises HTTPException 422 with a descriptive message if the name is invalid.
    Does nothing (returns None) if the name is valid.

    Args:
        name: The proposed bucket name from the API request.

    Raises:
        HTTPException 422: If the name violates any AWS naming rule.

    Examples:
        validate_bucket_name("my-valid-bucket")  # OK
        validate_bucket_name("MyBucket")          # raises 422
        validate_bucket_name("bucket_name")       # raises 422
        validate_bucket_name("ab")                # raises 422 (too short)
        validate_bucket_name("192.168.1.1")       # raises 422 (IP address)
    """
    errors: list[str] = []

    # Rule 1: Length
    if len(name) < 3:
        errors.append(
            f"Too short: '{name}' is {len(name)} character(s). Minimum is 3."
        )
    elif len(name) > 63:
        errors.append(
            f"Too long: '{name}' is {len(name)} characters. Maximum is 63."
        )

    # Rule 2: Character set + start/end (only check if length is valid for regex)
    if 3 <= len(name) <= 63:
        if not _BUCKET_NAME_RE.match(name):
            errors.append(
                "Invalid characters or format. "
                "Use only lowercase letters (a-z), digits (0-9), and hyphens (-). "
                "Must start and end with a letter or digit. "
                f"Got: '{name}'"
            )

    # Rule 3: Not an IP address
    if _IP_ADDRESS_RE.match(name):
        errors.append(f"Cannot be formatted as an IP address: '{name}'")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "field": "bucket_name",
                "value": name,
                "errors": errors,
                "aws_rules": (
                    "3-63 chars | lowercase letters, numbers, hyphens only | "
                    "start and end with letter or number | not an IP address"
                ),
            },
        )


def validate_aws_region(region: str) -> None:
    """
    Validate an AWS region slug.

    Raises HTTPException 422 if the region is not in the known list.
    Does nothing if valid.

    Args:
        region: AWS region slug (e.g., "us-east-1").

    Raises:
        HTTPException 422: If the region is not recognised.
    """
    if region not in VALID_AWS_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "field": "region",
                "value": region,
                "error": f"'{region}' is not a recognised AWS region.",
                "examples": ["us-east-1", "ap-south-1", "eu-west-1", "us-west-2"],
            },
        )
