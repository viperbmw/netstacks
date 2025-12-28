"""
Utilities module for NetStacks Core

Provides:
- Credential encryption/decryption
- Timezone handling
- DateTime utilities
- Standardized API responses
"""

from .encryption import (
    encrypt_credential,
    decrypt_credential,
    is_encrypted,
    encrypt_if_needed,
    generate_encryption_key,
)

from .timezone import (
    get_system_timezone,
    utc_now,
    utc_now_iso,
    to_utc,
    parse_iso_datetime,
    format_for_display,
    datetime_to_iso,
)

from .datetime import (
    utc_now as dt_utc_now,
    format_iso,
    parse_iso,
    utc_timestamp,
    from_timestamp,
)

from .responses import (
    success_response,
    error_response,
    paginated_response,
    APIResponse,
)

__all__ = [
    # Encryption
    "encrypt_credential",
    "decrypt_credential",
    "is_encrypted",
    "encrypt_if_needed",
    "generate_encryption_key",
    # Timezone
    "get_system_timezone",
    "utc_now",
    "utc_now_iso",
    "to_utc",
    "parse_iso_datetime",
    "format_for_display",
    "datetime_to_iso",
    # DateTime
    "format_iso",
    "parse_iso",
    "utc_timestamp",
    "from_timestamp",
    # Responses
    "success_response",
    "error_response",
    "paginated_response",
    "APIResponse",
]
