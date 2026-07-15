"""
backend/core/security.py
────────────────────────
Password hashing and verification utilities.

Why bcrypt?
  - Designed specifically for password hashing (slow by design).
  - Automatically salts every hash — same password produces different hashes.
  - The work factor (rounds) is tunable as hardware gets faster.
  - Industry standard, battle-tested.

Why passlib?
  - Abstracts over multiple hashing backends.
  - `deprecated="auto"` will automatically upgrade old hashes to the current
    scheme on next login — future-proofs the system.
  - Constant-time verification prevents timing attacks.

Work factor:
  rounds=12 is the current OWASP recommendation for bcrypt.
  At rounds=12, a single hash takes ~250ms — expensive for attackers,
  acceptable for users.

Usage:
    from backend.core.security import hash_password, verify_password

    hashed = hash_password("MySecret123")
    is_valid = verify_password("MySecret123", hashed)  # True
    is_valid = verify_password("WrongPass", hashed)     # False
"""

from passlib.context import CryptContext

# ── Bcrypt Context ────────────────────────────────────────────────────────────
# Created once at module load — CryptContext is thread-safe and reusable.
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",    # Auto-rehash older schemes on next login
    bcrypt__rounds=12,    # OWASP recommended work factor
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.

    Args:
        plain_password: The raw password string from the user's input.

    Returns:
        A bcrypt hash string (e.g. "$2b$12$...") safe to store in the DB.

    Security:
        - A unique random salt is generated for every call.
        - Two calls with the same input produce different hashes.
        - The hash includes the salt — no separate storage needed.
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain_password:  The raw password to check (from login request).
        hashed_password: The stored bcrypt hash from the database.

    Returns:
        True  — password matches the hash.
        False — password does not match.

    Security:
        - Uses constant-time comparison internally (passlib guarantee).
        - Returns False instead of raising on mismatch — callers decide the response.
    """
    return _pwd_context.verify(plain_password, hashed_password)
