"""
User Service

Business logic for user management, themes, and preferences.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import User
from netstacks_core.auth.password import hash_password, verify_password

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

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """
        Get all users.

        Returns:
            List of user dicts (without sensitive data)
        """
        users = self.session.query(User).all()
        return [
            {
                'username': u.username,
                'theme': u.theme or 'dark',
                'auth_source': u.auth_source or 'local',
                'created_at': u.created_at,
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
        user = self.session.query(User).filter(User.username == username).first()
        if user:
            return {
                'username': user.username,
                'theme': user.theme or 'dark',
                'auth_source': user.auth_source or 'local',
                'created_at': user.created_at,
            }
        return None

    def create(self, username: str, password: str) -> Dict:
        """
        Create a new user.

        Args:
            username: Username for new user
            password: Plain text password

        Returns:
            Created user dict

        Raises:
            ValueError: If user already exists
        """
        # Check if user already exists
        existing = self.session.query(User).filter(
            User.username == username
        ).first()
        if existing:
            raise ValueError(f"User {username} already exists")

        # Create user
        user = User(
            username=username,
            password_hash=hash_password(password),
            auth_source='local',
        )
        self.session.add(user)
        self.session.commit()

        log.info(f"User {username} created")
        return {
            'username': user.username,
            'theme': user.theme or 'dark',
            'auth_source': user.auth_source,
            'created_at': user.created_at,
        }

    def delete(self, username: str, current_username: str) -> bool:
        """
        Delete a user.

        Args:
            username: Username to delete
            current_username: Username of user performing deletion

        Returns:
            True if successful

        Raises:
            ValueError: If trying to delete own account or admin
        """
        # Can't delete yourself
        if current_username == username:
            raise ValueError('Cannot delete your own account')

        # Can't delete admin user
        if username == 'admin':
            raise ValueError('Cannot delete admin user')

        user = self.session.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")

        self.session.delete(user)
        self.session.commit()

        log.info(f"User {username} deleted by {current_username}")
        return True

    def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Change user password.

        Args:
            username: Username whose password to change
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            True if successful

        Raises:
            ValueError: If passwords invalid or user not found
        """
        user = self.session.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")

        if not verify_password(user.password_hash, current_password):
            raise ValueError("Current password is incorrect")

        user.password_hash = hash_password(new_password)
        self.session.commit()

        log.info(f"Password changed for user {username}")
        return True

    def get_theme(self, username: str) -> str:
        """
        Get user's theme preference.

        Args:
            username: Username

        Returns:
            Theme name ('dark' or 'light')
        """
        user = self.session.query(User).filter(User.username == username).first()
        if user:
            return user.theme or 'dark'
        return 'dark'

    def set_theme(self, username: str, theme: str) -> bool:
        """
        Set user's theme preference.

        Args:
            username: Username
            theme: Theme name ('dark' or 'light')

        Returns:
            True if successful

        Raises:
            ValueError: If theme is invalid or user not found
        """
        if theme not in self.VALID_THEMES:
            raise ValueError(f"Invalid theme. Must be one of: {', '.join(self.VALID_THEMES)}")

        user = self.session.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")

        user.theme = theme
        self.session.commit()

        log.info(f"User {username} changed theme to {theme}")
        return True
