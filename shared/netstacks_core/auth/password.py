"""
Password Hashing Utilities for NetStacks

Provides secure password hashing and verification using SHA256.
Note: For production, consider using bcrypt or argon2.
"""

import hashlib
import secrets


def hash_password(password: str) -> str:
    """
    Hash a password using SHA256.

    Args:
        password: The plain text password to hash

    Returns:
        The hexadecimal hash of the password
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Verify a password against a stored hash.

    Args:
        stored_hash: The stored password hash
        provided_password: The password to verify

    Returns:
        True if the password matches, False otherwise
    """
    return stored_hash == hash_password(provided_password)


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
