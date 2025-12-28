"""
Authentication Service

Business logic for user authentication, session management, and auth config.
"""

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from netstacks_core.db import User, AuthConfig, Setting
from netstacks_core.auth.password import hash_password, verify_password
from netstacks_core.auth import create_access_token, create_refresh_token

log = logging.getLogger(__name__)


class AuthService:
    """
    Service for user authentication.

    Handles:
    - Password hashing and verification
    - Multi-method authentication (local, LDAP, OIDC)
    - User lookup and creation
    """

    VALID_AUTH_TYPES = ['local', 'ldap', 'oidc']

    def __init__(self, session: Session):
        self.session = session

    def get_user(self, username: str) -> Optional[User]:
        """Get user from database."""
        return self.session.query(User).filter(User.username == username).first()

    def create_user(
        self,
        username: str,
        password: str,
        auth_source: str = 'local'
    ) -> User:
        """
        Create a new user.

        Args:
            username: Username
            password: Plain text password (will be hashed)
            auth_source: Source of authentication (local, ldap, oidc)

        Returns:
            Created User object
        """
        user = User(
            username=username,
            password_hash=hash_password(password),
            auth_source=auth_source,
        )
        self.session.add(user)
        self.session.commit()
        log.info(f"Created user: {username}")
        return user

    def authenticate(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Authenticate user using all enabled authentication methods.

        Args:
            username: Username to authenticate
            password: Password to verify

        Returns:
            Tuple of (success, user, auth_method)
        """
        # Get all enabled auth methods ordered by priority
        auth_configs = self._get_enabled_auth_configs()

        # Add local auth with its configured priority
        local_priority = self._get_local_auth_priority()
        auth_configs.append({
            'auth_type': 'local',
            'priority': local_priority,
            'config_data': {}
        })

        # Sort all methods by priority
        auth_configs.sort(key=lambda x: x.get('priority', 999))

        log.info(
            f"Authentication order for {username}: "
            f"{[(c['auth_type'], c['priority']) for c in auth_configs]}"
        )

        for auth_config in auth_configs:
            auth_type = auth_config['auth_type']
            config_data = auth_config.get('config_data', {})

            try:
                log.info(f"Trying {auth_type} authentication for {username}")

                if auth_type == 'local':
                    success, user = self._authenticate_local(username, password)
                    if success:
                        return True, user, 'local'

                elif auth_type == 'ldap':
                    success, user = self._authenticate_ldap(
                        username, password, config_data
                    )
                    if success:
                        return True, user, 'ldap'

                elif auth_type == 'oidc':
                    # OIDC requires redirect flow, not direct password auth
                    pass

            except Exception as e:
                log.error(
                    f"Error during {auth_type} authentication for user {username}: {e}"
                )
                continue

        # All authentication methods failed
        log.warning(f"Authentication failed for user {username}")
        return False, None, None

    def _authenticate_local(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[User]]:
        """Authenticate against local database."""
        user = self.get_user(username)
        if user and verify_password(user.password_hash, password):
            log.info(f"User {username} authenticated via local auth")
            return True, user
        log.info(f"Local auth failed for {username}")
        return False, None

    def _authenticate_ldap(
        self,
        username: str,
        password: str,
        config_data: Dict
    ) -> Tuple[bool, Optional[User]]:
        """Authenticate against LDAP server."""
        # TODO: Implement LDAP authentication
        log.warning("LDAP authentication not yet implemented")
        return False, None

    def _get_enabled_auth_configs(self) -> List[Dict]:
        """Get all enabled auth configs."""
        configs = self.session.query(AuthConfig).filter(
            AuthConfig.is_enabled == True
        ).order_by(AuthConfig.priority).all()

        return [
            {
                'auth_type': c.auth_type,
                'priority': c.priority,
                'config_data': c.config_data or {}
            }
            for c in configs
        ]

    def _get_local_auth_priority(self) -> int:
        """Get local authentication priority."""
        setting = self.session.query(Setting).filter(
            Setting.key == 'local_auth_priority'
        ).first()
        if setting:
            try:
                return int(setting.value)
            except (ValueError, TypeError):
                pass
        return 999

    def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Change user password.

        Args:
            username: Username
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            True if successful

        Raises:
            ValueError: If current password is invalid or user not found
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"User not found: {username}")

        if not verify_password(user.password_hash, current_password):
            raise ValueError("Current password is incorrect")

        user.password_hash = hash_password(new_password)
        self.session.commit()

        log.info(f"Password changed for user {username}")
        return True

    def create_tokens(
        self,
        user: User,
        access_token_minutes: int = 30
    ) -> Tuple[str, str]:
        """
        Create access and refresh tokens for user.

        Args:
            user: User object
            access_token_minutes: Access token expiration in minutes

        Returns:
            Tuple of (access_token, refresh_token)
        """
        roles = ["admin"] if user.username == "admin" else ["user"]

        access_token = create_access_token(
            username=user.username,
            auth_method=user.auth_source or "local",
            roles=roles,
        )
        refresh_token = create_refresh_token(username=user.username)

        return access_token, refresh_token
