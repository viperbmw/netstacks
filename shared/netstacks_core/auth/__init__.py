"""
Authentication module for NetStacks Core

Provides:
- JWT token creation and validation
- FastAPI authentication middleware
- Password hashing utilities
"""

from .jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenData,
    TokenType,
)

from .middleware import (
    get_current_user,
    get_current_user_optional,
    require_auth,
)

from .password import (
    hash_password,
    verify_password,
)

__all__ = [
    # JWT
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "TokenData",
    "TokenType",
    # Middleware
    "get_current_user",
    "get_current_user_optional",
    "require_auth",
    # Password
    "hash_password",
    "verify_password",
]
