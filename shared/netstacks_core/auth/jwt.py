"""
JWT Token Utilities for NetStacks

Provides functions for creating and validating JWT tokens used for authentication.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum

from pydantic import BaseModel
from jose import jwt, JWTError

log = logging.getLogger(__name__)

# JWT Configuration - can be overridden via environment variables
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get('REFRESH_TOKEN_EXPIRE_DAYS', '7'))


class TokenType(str, Enum):
    """Token type enumeration"""
    ACCESS = "access"
    REFRESH = "refresh"


class TokenData(BaseModel):
    """Data contained in a JWT token"""
    sub: str  # Subject (username)
    exp: datetime  # Expiration time
    iat: datetime  # Issued at time
    type: TokenType  # Token type (access or refresh)
    auth_method: Optional[str] = None  # Authentication method used
    roles: list[str] = []  # User roles


def create_access_token(
    username: str,
    auth_method: str = "local",
    roles: Optional[list[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create an access token for a user.

    Args:
        username: The username to create a token for
        auth_method: The authentication method used (local, ldap, oidc)
        roles: Optional list of user roles
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT access token string
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "exp": expire,
        "iat": now,
        "type": TokenType.ACCESS.value,
        "auth_method": auth_method,
        "roles": roles or [],
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    log.debug(f"Created access token for user: {username}")

    return token


def create_refresh_token(
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a refresh token for a user.

    Args:
        username: The username to create a token for
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token string
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": username,
        "exp": expire,
        "iat": now,
        "type": TokenType.REFRESH.value,
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    log.debug(f"Created refresh token for user: {username}")

    return token


def decode_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string to decode

    Returns:
        TokenData if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        return TokenData(
            sub=payload["sub"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            type=TokenType(payload["type"]),
            auth_method=payload.get("auth_method"),
            roles=payload.get("roles", []),
        )

    except JWTError as e:
        log.warning(f"JWT decode error: {e}")
        return None

    except Exception as e:
        log.error(f"Unexpected error decoding token: {e}")
        return None


def is_token_expired(token_data: TokenData) -> bool:
    """
    Check if a token is expired.

    Args:
        token_data: The decoded token data

    Returns:
        True if expired, False otherwise
    """
    return datetime.now(timezone.utc) > token_data.exp
