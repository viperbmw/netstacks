"""
User management routes
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends

from netstacks_core.auth import get_current_user, TokenData
from netstacks_core.auth.password import hash_password, verify_password
from netstacks_core.db import get_session, User
from netstacks_core.utils import success_response, error_response

from app.schemas.users import (
    UserCreate,
    UserResponse,
    UserList,
    PasswordChange,
    ThemeUpdate,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=UserList)
async def list_users(current_user: TokenData = Depends(get_current_user)):
    """
    List all users.
    """
    session = get_session()
    try:
        users = session.query(User).all()
        user_list = [
            UserResponse(
                username=u.username,
                theme=u.theme or "dark",
                auth_source=u.auth_source or "local",
                created_at=u.created_at,
            )
            for u in users
        ]
        return UserList(data=user_list, total=len(user_list))
    finally:
        session.close()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create a new user.
    """
    session = get_session()
    try:
        # Check if user already exists
        existing = session.query(User).filter(User.username == request.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User {request.username} already exists"
            )

        # Create user
        user = User(
            username=request.username,
            password_hash=hash_password(request.password),
            auth_source="local",
        )
        session.add(user)
        session.commit()

        log.info(f"User {request.username} created by {current_user.sub}")

        return success_response(
            data={"username": request.username},
            message=f"User {request.username} created successfully"
        )

    finally:
        session.close()


@router.get("/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get user by username.
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
            )

        return UserResponse(
            username=user.username,
            theme=user.theme or "dark",
            auth_source=user.auth_source or "local",
            created_at=user.created_at,
        )

    finally:
        session.close()


@router.delete("/{username}")
async def delete_user(
    username: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Delete a user.
    """
    # Can't delete yourself
    if current_user.sub == username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Can't delete admin
    if username == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin user"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
            )

        session.delete(user)
        session.commit()

        log.info(f"User {username} deleted by {current_user.sub}")

        return success_response(message=f"User {username} deleted successfully")

    finally:
        session.close()


@router.api_route("/{username}/password", methods=["POST", "PUT"])
async def change_password(
    username: str,
    request: PasswordChange,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Change user password.
    """
    # Users can only change their own password
    if current_user.sub != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only change your own password"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
            )

        # Verify current password
        if not verify_password(user.password_hash, request.current_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

        # Update password
        user.password_hash = hash_password(request.new_password)
        session.commit()

        log.info(f"Password changed for user {username}")

        return success_response(message="Password changed successfully")

    finally:
        session.close()


@router.get("/{username}/theme")
async def get_theme(
    username: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get user theme preference.
    """
    # Users can only get their own theme
    if current_user.sub != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access your own theme"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
            )

        return success_response(data={"theme": user.theme or "dark"})

    finally:
        session.close()


@router.put("/{username}/theme")
async def update_theme(
    username: str,
    request: ThemeUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update user theme preference.
    """
    # Users can only change their own theme
    if current_user.sub != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only change your own theme"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
            )

        user.theme = request.theme
        session.commit()

        log.info(f"Theme updated to {request.theme} for user {username}")

        return success_response(
            data={"theme": request.theme},
            message="Theme updated successfully"
        )

    finally:
        session.close()
