"""
FastAPI Authentication Middleware for NetStacks

Provides dependency injection functions for protecting routes.
"""

import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .jwt import decode_token, is_token_expired, TokenData, TokenType

log = logging.getLogger(__name__)

# HTTP Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)

# Dev mode - disable auth when NETSTACKS_DEV_MODE=true
DEV_MODE = os.environ.get("NETSTACKS_DEV_MODE", "").lower() in ("true", "1", "yes")

# Mock user for dev mode
DEV_USER = TokenData(
    sub="admin",
    exp=9999999999,
    iat=0,
    type=TokenType.ACCESS,
    auth_method="dev",
    roles=["admin"],
)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> TokenData:
    """
    Get the current authenticated user from the JWT token.

    This is a FastAPI dependency that can be used to protect routes.

    Usage:
        @app.get("/protected")
        async def protected_route(user: TokenData = Depends(get_current_user)):
            return {"username": user.sub}

    Args:
        credentials: The HTTP Authorization credentials from the request

    Returns:
        TokenData containing the user information

    Raises:
        HTTPException: 401 if no valid token is provided
    """
    # Dev mode bypass
    if DEV_MODE:
        return DEV_USER

    if credentials is None:
        log.warning("No authorization credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    token_data = decode_token(token)

    if token_data is None:
        log.warning("Invalid token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_expired(token_data):
        log.warning(f"Expired token for user: {token_data.sub}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.type != TokenType.ACCESS:
        log.warning(f"Non-access token used for authentication: {token_data.type}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[TokenData]:
    """
    Get the current user if authenticated, or None if not.

    This is a FastAPI dependency for routes that can work both authenticated
    and unauthenticated.

    Usage:
        @app.get("/public")
        async def public_route(user: Optional[TokenData] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello, {user.sub}"}
            return {"message": "Hello, anonymous"}

    Args:
        credentials: The HTTP Authorization credentials from the request

    Returns:
        TokenData if authenticated, None otherwise
    """
    if credentials is None:
        return None

    token = credentials.credentials
    token_data = decode_token(token)

    if token_data is None:
        return None

    if is_token_expired(token_data):
        return None

    if token_data.type != TokenType.ACCESS:
        return None

    return token_data


def require_auth(user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Alias for get_current_user for semantic clarity.

    Usage:
        @app.get("/admin")
        async def admin_route(user: TokenData = Depends(require_auth)):
            return {"admin": user.sub}
    """
    return user


class RoleChecker:
    """
    Dependency class for checking user roles.

    Usage:
        admin_only = RoleChecker(["admin"])

        @app.get("/admin")
        async def admin_route(user: TokenData = Depends(admin_only)):
            return {"admin": user.sub}
    """

    def __init__(self, required_roles: list[str]):
        """
        Initialize the role checker.

        Args:
            required_roles: List of roles that are allowed access
        """
        self.required_roles = required_roles

    async def __call__(
        self,
        user: TokenData = Depends(get_current_user)
    ) -> TokenData:
        """
        Check if the user has any of the required roles.

        Args:
            user: The authenticated user's token data

        Returns:
            TokenData if user has required role

        Raises:
            HTTPException: 403 if user doesn't have required role
        """
        if not any(role in user.roles for role in self.required_roles):
            log.warning(
                f"User {user.sub} lacks required roles. "
                f"Has: {user.roles}, Needs: {self.required_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user
