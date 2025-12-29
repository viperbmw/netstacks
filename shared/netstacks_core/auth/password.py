"""Password hashing utilities.

Functional goals:
- Work across both the Flask monolith and FastAPI microservices.
- Prefer modern hashes (bcrypt) when the runtime has support.
- Preserve backwards compatibility for legacy SHA256-hex hashes.

This module intentionally avoids hard dependencies on bcrypt/passlib in the
shared library so services can opt-in via their own requirements.
"""

import hashlib
import hmac
import secrets
from typing import Optional


def _sha256_hex(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _looks_like_sha256_hex(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower())


def _try_passlib_context():
    """Return a passlib CryptContext if passlib is available, else None."""
    try:
        from passlib.context import CryptContext

        # bcrypt is preferred; passlib will raise if backend isn't available
        return CryptContext(schemes=["bcrypt"], deprecated="auto")
    except Exception:
        return None


def _bcrypt_hash(password: str) -> Optional[str]:
    """Hash with bcrypt if available; otherwise return None."""
    pwd = _try_passlib_context()
    if pwd is None:
        # Try python's bcrypt module directly if installed
        try:
            import bcrypt
            return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        except Exception:
            return None
    try:
        return pwd.hash(password)
    except Exception:
        return None


def _bcrypt_verify(stored_hash: str, password: str) -> Optional[bool]:
    """Verify bcrypt hash if possible; returns None if bcrypt backend unavailable."""
    pwd = _try_passlib_context()
    if pwd is not None:
        try:
            return pwd.verify(password, stored_hash)
        except Exception:
            return False

    try:
        import bcrypt
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return None


def hash_password(password: str) -> str:
    """
    Hash a password.

    Prefers bcrypt when available; otherwise falls back to legacy SHA256-hex.

    Args:
        password: The plain text password to hash

    Returns:
        The hexadecimal hash of the password
    """
    bcrypt_hash = _bcrypt_hash(password)
    if bcrypt_hash:
        return bcrypt_hash
    return _sha256_hex(password)


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Verify a password against a stored hash.

    Args:
        stored_hash: The stored password hash
        provided_password: The password to verify

    Returns:
        True if the password matches, False otherwise
    """
    if not stored_hash or not provided_password:
        return False

    # bcrypt hashes typically start with $2a$, $2b$, $2y$
    if isinstance(stored_hash, str) and stored_hash.startswith("$2"):
        bcrypt_ok = _bcrypt_verify(stored_hash, provided_password)
        # If bcrypt support isn't present in this runtime, treat as failure.
        return bool(bcrypt_ok) if bcrypt_ok is not None else False

    # Legacy SHA256 hex
    if _looks_like_sha256_hex(stored_hash):
        return hmac.compare_digest(stored_hash, _sha256_hex(provided_password))

    # Unknown format
    return False


def generate_random_password(length: int = 32) -> str:
    """
    Generate a cryptographically secure random password.

    Useful for creating temporary passwords or tokens.

    Args:
        length: The length of the password to generate

    Returns:
        A URL-safe random string
    """
    return secrets.token_urlsafe(length)
