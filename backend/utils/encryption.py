"""
backend/utils/encryption.py
────────────────────────────
Symmetric encryption/decryption for sensitive values stored in the database.

Algorithm: Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
Key source: CREDENTIAL_ENCRYPTION_KEY in settings (loaded from .env).

Why Fernet?
  - Authenticated encryption: tampering with the ciphertext is detected.
  - Includes timestamp and HMAC — more secure than raw AES-CBC.
  - Simple API: encrypt returns a URL-safe base64 string, safe for DB TEXT columns.

PRODUCTION ADVISORY:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Storing encrypted AWS credentials in a relational database     │
  │  is acceptable for LEARNING / DEMO purposes ONLY.              │
  │                                                                  │
  │  In production you MUST use one of:                             │
  │    - AWS Secrets Manager (boto3 secretsmanager client)          │
  │    - HashiCorp Vault (hvac library)                             │
  │    - Azure Key Vault / GCP Secret Manager                       │
  │                                                                  │
  │  To replace this module with Secrets Manager:                   │
  │    1. Implement CredentialManager.store() / retrieve()          │
  │       to call AWS Secrets Manager instead of Fernet.            │
  │    2. No changes needed to service or repository layers.        │
  └─────────────────────────────────────────────────────────────────┘

Usage:
    from backend.utils.encryption import CredentialManager

    encrypted = CredentialManager.encrypt("my-secret-key")
    plain     = CredentialManager.decrypt(encrypted)
"""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from backend.core.config import settings


class CredentialManager:
    """
    Abstraction layer for encrypting and decrypting sensitive credential values.

    All AWS secret keys pass through this class before touching the database.
    Replace the implementation of encrypt() and decrypt() to switch backends
    (e.g., AWS Secrets Manager) without changing any other code.
    """

    @staticmethod
    def _get_fernet() -> Fernet:
        """
        Return a Fernet instance initialised with the configured key.

        The key is loaded from settings on every call so that key rotation
        (restart with a new key) takes effect immediately.

        Raises:
            ValueError: If CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key.
        """
        try:
            return Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        except (ValueError, Exception) as exc:
            raise RuntimeError(
                "CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc

    @classmethod
    def encrypt(cls, plain_text: str) -> str:
        """
        Encrypt a plain-text string and return a URL-safe base64 ciphertext.

        Args:
            plain_text: The sensitive value to encrypt (e.g., AWS secret key).

        Returns:
            Encrypted string — safe to store in a database TEXT column.

        Raises:
            RuntimeError: If the configured Fernet key is invalid.
        """
        fernet = cls._get_fernet()
        return fernet.encrypt(plain_text.encode()).decode()

    @classmethod
    def decrypt(cls, encrypted_text: str) -> str:
        """
        Decrypt a Fernet ciphertext and return the original plain-text string.

        Args:
            encrypted_text: The ciphertext returned by encrypt().

        Returns:
            The original plain-text string.

        Raises:
            HTTPException 500: If decryption fails (key mismatch or tampered data).
        """
        fernet = cls._get_fernet()
        try:
            return fernet.decrypt(encrypted_text.encode()).decode()
        except InvalidToken as exc:
            # This should never happen in normal operation.
            # If it does, the encryption key has been rotated or the data is corrupt.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Failed to decrypt stored credentials. "
                    "The encryption key may have changed. Please reconnect your AWS account."
                ),
            ) from exc
