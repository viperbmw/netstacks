"""
Credential Encryption Utilities for NetStacks

Provides secure encryption/decryption of device credentials using Fernet
symmetric encryption. The encryption key is derived from a master secret
that should be set via environment variable NETSTACKS_ENCRYPTION_KEY.

Security features:
- Fernet encryption (AES-128-CBC with HMAC-SHA256)
- Key derivation using PBKDF2
- Automatic key generation with warnings
- Backward compatibility for unencrypted credentials
- Encrypted values are prefixed with 'enc:' for identification
"""

import os
import base64
import logging
import secrets
import warnings
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger(__name__)

# Prefix for encrypted values to identify them
ENCRYPTED_PREFIX = 'enc:'

# Static salt for key derivation (should be consistent across restarts)
KEY_DERIVATION_SALT = b'netstacks_credential_salt_v1'


def _get_encryption_key() -> bytes:
    """
    Get or generate the encryption key.

    The key is derived from NETSTACKS_ENCRYPTION_KEY environment variable.
    If not set, generates a warning and uses a fallback (NOT SECURE for production).

    Returns:
        bytes: 32-byte Fernet-compatible key
    """
    master_secret = os.environ.get('NETSTACKS_ENCRYPTION_KEY')

    if not master_secret:
        warnings.warn(
            "NETSTACKS_ENCRYPTION_KEY environment variable not set! "
            "Using auto-generated key. Credentials will NOT be portable between restarts. "
            "Set NETSTACKS_ENCRYPTION_KEY in production for persistent credential encryption.",
            RuntimeWarning
        )
        # Fallback: use a combination of other secrets for some entropy
        secret_key = os.environ.get('SECRET_KEY', 'netstacks_default_fallback')
        master_secret = f"auto_generated_{secret_key}"

    # Derive a proper key from the master secret using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=KEY_DERIVATION_SALT,
        iterations=480000,  # OWASP recommended minimum
    )

    key = base64.urlsafe_b64encode(kdf.derive(master_secret.encode()))
    return key


def _get_fernet() -> Fernet:
    """Get a Fernet instance with the derived key."""
    return Fernet(_get_encryption_key())


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential value.

    Args:
        plaintext: The credential to encrypt

    Returns:
        str: Encrypted value prefixed with 'enc:' for identification
    """
    if not plaintext:
        return plaintext

    # Already encrypted
    if plaintext.startswith(ENCRYPTED_PREFIX):
        return plaintext

    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(plaintext.encode())
        return ENCRYPTED_PREFIX + encrypted.decode()
    except Exception as e:
        log.error(f"Error encrypting credential: {e}")
        raise


def decrypt_credential(encrypted: str) -> str:
    """
    Decrypt a credential value.

    Handles both encrypted and unencrypted (legacy) values gracefully.

    Args:
        encrypted: The encrypted credential (with 'enc:' prefix) or plaintext

    Returns:
        str: Decrypted plaintext value
    """
    if not encrypted:
        return encrypted

    # Not encrypted (legacy plaintext credential)
    if not encrypted.startswith(ENCRYPTED_PREFIX):
        log.debug("Credential is not encrypted (legacy plaintext)")
        return encrypted

    try:
        fernet = _get_fernet()
        # Remove prefix and decrypt
        encrypted_data = encrypted[len(ENCRYPTED_PREFIX):]
        decrypted = fernet.decrypt(encrypted_data.encode())
        return decrypted.decode()
    except InvalidToken:
        log.error("Failed to decrypt credential - invalid token or wrong key")
        raise ValueError("Failed to decrypt credential - check NETSTACKS_ENCRYPTION_KEY")
    except Exception as e:
        log.error(f"Error decrypting credential: {e}")
        raise


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted."""
    return bool(value and value.startswith(ENCRYPTED_PREFIX))


def encrypt_if_needed(value: str) -> str:
    """
    Encrypt a value only if it's not already encrypted.

    Useful for migration scenarios.

    Args:
        value: Credential value (may be plaintext or encrypted)

    Returns:
        str: Encrypted value
    """
    if not value or is_encrypted(value):
        return value
    return encrypt_credential(value)


def migrate_plaintext_credential(value: str) -> Optional[str]:
    """
    Migrate a plaintext credential to encrypted format.

    Returns None if the value is already encrypted or empty.

    Args:
        value: Credential that may need migration

    Returns:
        str: Encrypted value, or None if no migration needed
    """
    if not value or is_encrypted(value):
        return None
    return encrypt_credential(value)


def generate_encryption_key() -> str:
    """
    Generate a new random encryption key suitable for NETSTACKS_ENCRYPTION_KEY.

    This is a utility function for admins to generate a secure key.

    Returns:
        str: A secure random key string
    """
    return secrets.token_urlsafe(32)
