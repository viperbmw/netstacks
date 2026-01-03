"""
User Service for NetStacks

Business logic for user management, themes, and preferences.
"""

import logging
from typing import Dict, List, Optional

import database as db
from services.auth_service import AuthService
from utils.exceptions import (
    NotFoundError,
    ValidationError,
    AuthorizationError,
    ConflictError
)

log = logging.getLogger(__name__)


class UserService:
    """
    Service for user management.

    Handles:
    - User CRUD operations
    - Password management
    - Theme preferences
    """

    VALID_THEMES = ['dark', 'light']

    def __init__(self):
        self.auth_service = AuthService()

    def get_all(self) -> List[Dict]:
        """
        Get all users.

        Returns:
            List of user dicts (without sensitive data)
        """
        users = db.get_all_users()
        # Ensure no password hashes are returned
        return [
            {
                'username': u['username'],
                'created_at': u.get('created_at', 'Unknown')
            }
            for u in users
        ]

    def get(self, username: str) -> Optional[Dict]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            User dict or None
        """
        user = db.get_user(username)
        if user:
            # Don't return password hash
            return {
                'username': user['username'],
                'theme': user.get('theme', 'dark'),
                'auth_source': user.get('auth_source', 'local'),
                'created_at': user.get('created_at')
            }
        return None

    def create(self, username: str, password: str) -> bool:
        """
        Create a new user.

        Args:
            username: Username for new user
            password: Plain text password

        Returns:
            True if successful

        Raises:
            ValidationError: If username or password missing
            ConflictError: If user already exists
        """
        if not username or not password:
            raise ValidationError(
                'Username and password are required',
                field_errors={
                    'username': ['Username is required'] if not username else [],
                    'password': ['Password is required'] if not password else []
                }
            )

        # Check if user already exists
        if self.auth_service.get_user(username):
            raise ConflictError(
                f'User {username} already exists',
                conflicting_field='username'
            )

        # Create user
        self.auth_service.create_user(username, password, 'local')
        log.info(f"User {username} created")
        return True

    def delete(self, username: str, current_username: str) -> bool:
        """
        Delete a user.

        Args:
            username: Username to delete
            current_username: Username of user performing deletion

        Returns:
            True if successful

        Raises:
            ValidationError: If trying to delete own account or admin
            NotFoundError: If user not found
        """
        # Can't delete yourself
        if current_username == username:
            raise ValidationError('You cannot delete your own account')

        # Can't delete admin user
        if username == 'admin':
            raise ValidationError('Cannot delete admin user')

        # Delete user
        if db.delete_user(username):
            log.info(f"User {username} deleted by {current_username}")
            return True
        else:
            raise NotFoundError(
                f"User not found: {username}",
                resource_type='User',
                resource_id=username
            )

    def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
        requesting_username: str
    ) -> bool:
        """
        Change user password.

        Args:
            username: Username whose password to change
            current_password: Current password for verification
            new_password: New password to set
            requesting_username: Username making the request

        Returns:
            True if successful

        Raises:
            AuthorizationError: If trying to change another user's password
            ValidationError: If passwords missing
            NotFoundError: If user not found
            AuthenticationError: If current password is incorrect
        """
        # Users can only change their own password
        if requesting_username != username:
            raise AuthorizationError('You can only change your own password')

        if not current_password or not new_password:
            raise ValidationError(
                'Current and new password are required',
                field_errors={
                    'current_password': ['Current password is required'] if not current_password else [],
                    'new_password': ['New password is required'] if not new_password else []
                }
            )

        # Use auth service for password change (handles verification)
        return self.auth_service.change_password(
            username, current_password, new_password
        )

    def get_theme(self, username: str) -> str:
        """
        Get user's theme preference.

        Args:
            username: Username

        Returns:
            Theme name ('dark' or 'light')
        """
        return db.get_user_theme(username)

    def set_theme(self, username: str, theme: str) -> bool:
        """
        Set user's theme preference.

        Args:
            username: Username
            theme: Theme name ('dark' or 'light')

        Returns:
            True if successful

        Raises:
            ValidationError: If theme is invalid
        """
        if theme not in self.VALID_THEMES:
            raise ValidationError(
                f'Invalid theme. Must be one of: {", ".join(self.VALID_THEMES)}'
            )

        if db.set_user_theme(username, theme):
            log.info(f"User {username} changed theme to {theme}")
            return True
        else:
            raise NotFoundError(
                f"User not found: {username}",
                resource_type='User',
                resource_id=username
            )
