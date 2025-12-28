"""
Authentication routes
"""

import logging
from fastapi import APIRouter, HTTPException, status, Depends

from netstacks_core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    TokenData,
    TokenType,
)
from netstacks_core.db import get_session, User
from netstacks_core.auth.password import hash_password, verify_password

from app.config import get_settings
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    UserInfo,
)

log = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT tokens.
    """
    session = get_session()
    try:
        # Find user
        user = session.query(User).filter(User.username == request.username).first()

        if not user:
            log.warning(f"Login failed: user not found - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Verify password
        if not verify_password(user.password_hash, request.password):
            log.warning(f"Login failed: invalid password - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Create tokens
        roles = ["admin"] if user.username == "admin" else ["user"]
        access_token = create_access_token(
            username=user.username,
            auth_method=user.auth_source or "local",
            roles=roles,
        )
        refresh_token = create_refresh_token(username=user.username)

        log.info(f"User {request.username} logged in successfully")

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserInfo(
                username=user.username,
                auth_method=user.auth_source or "local",
                roles=roles,
                theme=user.theme or "dark",
            )
        )

    finally:
        session.close()


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.
    """
    # Decode refresh token
    token_data = decode_token(request.refresh_token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    if token_data.type != TokenType.REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    # Get user to verify they still exist
    session = get_session()
    try:
        user = session.query(User).filter(User.username == token_data.sub).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Create new access token
        roles = ["admin"] if user.username == "admin" else ["user"]
        access_token = create_access_token(
            username=user.username,
            auth_method=user.auth_source or "local",
            roles=roles,
        )

        log.info(f"Token refreshed for user {user.username}")

        return RefreshResponse(
            access_token=access_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    finally:
        session.close()


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """
    Get current authenticated user info.
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.username == current_user.sub).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return UserInfo(
            username=user.username,
            auth_method=user.auth_source or "local",
            roles=current_user.roles,
            theme=user.theme or "dark",
        )

    finally:
        session.close()


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout current user.

    Note: JWT tokens are stateless, so this just returns success.
    For true logout, implement token blacklisting.
    """
    log.info(f"User {current_user.sub} logged out")
    return {"success": True, "message": "Logged out successfully"}
