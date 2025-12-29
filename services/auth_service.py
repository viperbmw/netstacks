"""
Authentication Service for NetStacks

Business logic for user authentication, session management, and auth config.
"""

import logging
import secrets
from typing import Any, Dict, List, Optional, Tuple

import hashlib
import hmac

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except Exception:
    bcrypt = None
    _BCRYPT_AVAILABLE = False

import database as db
from utils.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError
)

# Import auth providers (these are external modules)
try:
    import auth_ldap
except ImportError:
    auth_ldap = None

try:
    import auth_oidc
except ImportError:
    auth_oidc = None

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

    @staticmethod
    def _sha256_hex(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def _looks_like_sha256_hex(value: str) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower())

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password.

        Uses bcrypt when available; falls back to legacy SHA256-hex.
        """
        if _BCRYPT_AVAILABLE:
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        return AuthService._sha256_hex(password)

    @staticmethod
    def verify_password(stored_hash: str, provided_password: str) -> bool:
        """Verify a password against a stored hash.

        Supports bcrypt (preferred) and legacy SHA256-hex.
        """
        if not stored_hash or not provided_password:
            return False

        if isinstance(stored_hash, str) and stored_hash.startswith('$2'):
            if not _BCRYPT_AVAILABLE:
                log.error("bcrypt hash present but bcrypt not installed")
                return False
            try:
                return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
            except Exception:
                return False

        if AuthService._looks_like_sha256_hex(stored_hash):
            return hmac.compare_digest(stored_hash, AuthService._sha256_hex(provided_password))

        return False

    def get_user(self, username: str) -> Optional[Dict]:
        """Get user from database."""
        return db.get_user(username)

    def create_user(
        self,
        username: str,
        password: str,
        auth_source: str = 'local'
    ) -> bool:
        """
        Create a new user.

        Args:
            username: Username
            password: Plain text password (will be hashed)
            auth_source: Source of authentication (local, ldap, oidc)

        Returns:
            True if successful
        """
        password_hash = self.hash_password(password)
        return db.create_user(username, password_hash, auth_source)

    def create_default_user(self) -> None:
        """Create default admin user if no users exist."""
        try:
            if not self.get_user('admin'):
                self.create_user('admin', 'admin', 'local')
                log.info("Created default admin user (username: admin, password: admin)")
        except Exception as e:
            log.error(f"Error creating default user: {e}")

    def authenticate(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Authenticate user using all enabled authentication methods.

        Args:
            username: Username to authenticate
            password: Password to verify

        Returns:
            Tuple of (success, user_info, auth_method)
        """
        # Get all enabled auth methods ordered by priority
        auth_configs = db.get_enabled_auth_configs()

        # Add local auth with its configured priority
        local_priority = int(db.get_setting('local_auth_priority', '999'))
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
                    result = self._authenticate_local(username, password)
                    if result[0]:
                        return result

                elif auth_type == 'ldap':
                    result = self._authenticate_ldap(username, password, config_data)
                    if result[0]:
                        return result

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
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Authenticate against local database."""
        user = self.get_user(username)
        if user and self.verify_password(user['password_hash'], password):
            log.info(f"User {username} authenticated via local auth")
            return True, {'username': username, 'auth_method': 'local'}, 'local'
        log.info(f"Local auth failed for {username}")
        return False, None, None

    def _authenticate_ldap(
        self,
        username: str,
        password: str,
        config_data: Dict
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Authenticate against LDAP server."""
        if not auth_ldap:
            log.warning("LDAP module not available")
            return False, None, None

        success, user_info = auth_ldap.authenticate_ldap(
            username, password, config_data
        )

        if success:
            log.info(f"User {username} authenticated via LDAP")
            # Create/update local user record for LDAP user
            if not self.get_user(username):
                self.create_user(username, secrets.token_urlsafe(32), 'ldap')
            return True, user_info, 'ldap'

        return False, None, None

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
            AuthenticationError: If current password is invalid
            NotFoundError: If user not found
        """
        user = self.get_user(username)
        if not user:
            raise NotFoundError(f"User not found: {username}")

        if not self.verify_password(user['password_hash'], current_password):
            raise AuthenticationError("Current password is incorrect")

        new_hash = self.hash_password(new_password)
        success = db.update_user_password(username, new_hash)

        if success:
            log.info(f"Password changed for user {username}")

        return success


class OIDCService:
    """
    Service for OIDC authentication flow.

    Handles:
    - OIDC authorization URL generation
    - OIDC callback processing
    - User creation from OIDC claims
    """

    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    def get_authorization_url(
        self,
        config_data: Dict
    ) -> Tuple[str, str]:
        """
        Generate OIDC authorization URL.

        Args:
            config_data: OIDC configuration dict

        Returns:
            Tuple of (authorization_url, state)

        Raises:
            ValidationError: If OIDC module not available
        """
        if not auth_oidc:
            raise ValidationError("OIDC module not available")

        return auth_oidc.get_oidc_authorization_url(config_data)

    def process_callback(
        self,
        code: str,
        state: str,
        expected_state: str,
        config_data: Dict
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Process OIDC callback.

        Args:
            code: Authorization code from callback
            state: State parameter from callback
            expected_state: State we sent in authorization request
            config_data: OIDC configuration dict

        Returns:
            Tuple of (success, user_info)
        """
        if not auth_oidc:
            return False, None

        success, user_info = auth_oidc.authenticate_oidc_callback(
            code, state, expected_state, config_data
        )

        if success and user_info:
            username = user_info.get('username')
            if username and not self.auth_service.get_user(username):
                # Create local user record for OIDC user
                self.auth_service.create_user(
                    username,
                    secrets.token_urlsafe(32),
                    'oidc'
                )

        return success, user_info


class AuthConfigService:
    """
    Service for managing authentication configurations.

    Handles:
    - Auth config CRUD operations
    - Enabling/disabling auth methods
    - Testing auth connections
    """

    VALID_AUTH_TYPES = ['local', 'ldap', 'oidc']

    def get_all_configs(self) -> List[Dict]:
        """Get all authentication configurations."""
        return db.get_all_auth_configs()

    def get_enabled_configs(self) -> List[Dict]:
        """Get all enabled authentication configurations."""
        return db.get_enabled_auth_configs()

    def get_config(self, auth_type: str) -> Optional[Dict]:
        """
        Get specific authentication configuration.

        Args:
            auth_type: Type of authentication (local, ldap, oidc)

        Returns:
            Auth config dict or None
        """
        return db.get_auth_config(auth_type)

    def save_config(
        self,
        auth_type: str,
        config_data: Dict,
        is_enabled: bool = True,
        priority: int = 0
    ) -> bool:
        """
        Save authentication configuration.

        Args:
            auth_type: Type of authentication
            config_data: Configuration data dict
            is_enabled: Whether auth method is enabled
            priority: Priority order (lower = higher priority)

        Returns:
            True if successful

        Raises:
            ValidationError: If auth_type is invalid
        """
        if auth_type not in self.VALID_AUTH_TYPES:
            raise ValidationError(f"Invalid auth_type: {auth_type}")

        db.save_auth_config(auth_type, config_data, is_enabled, priority)
        log.info(f"{auth_type.upper()} configuration saved")
        return True

    def delete_config(self, auth_type: str) -> bool:
        """
        Delete authentication configuration.

        Args:
            auth_type: Type of authentication

        Returns:
            True if successful

        Raises:
            NotFoundError: If config not found
        """
        success = db.delete_auth_config(auth_type)
        if not success:
            raise NotFoundError(f"Configuration not found: {auth_type}")
        log.info(f"{auth_type.upper()} configuration deleted")
        return True

    def toggle_config(self, auth_type: str, enabled: bool) -> bool:
        """
        Enable or disable authentication method.

        Args:
            auth_type: Type of authentication
            enabled: Whether to enable

        Returns:
            True if successful

        Raises:
            NotFoundError: If config not found
        """
        success = db.toggle_auth_config(auth_type, enabled)
        if not success:
            raise NotFoundError(f"Configuration not found: {auth_type}")

        status = 'enabled' if enabled else 'disabled'
        log.info(f"{auth_type.upper()} authentication {status}")
        return True

    def get_local_priority(self) -> int:
        """Get local authentication priority."""
        priority = db.get_setting('local_auth_priority', '999')
        return int(priority)

    def set_local_priority(self, priority: int) -> bool:
        """Set local authentication priority."""
        db.set_setting('local_auth_priority', str(priority))
        log.info(f"Updated local auth priority to: {priority}")
        return True

    def test_ldap(self, config: Dict) -> Tuple[bool, str]:
        """
        Test LDAP connection.

        Args:
            config: LDAP configuration dict

        Returns:
            Tuple of (success, message)
        """
        if not auth_ldap:
            return False, "LDAP module not available"

        log.info(
            f"Testing LDAP with config: server={config.get('server')}, "
            f"base_dn={config.get('base_dn')}"
        )
        return auth_ldap.test_ldap_connection(config)

    def test_oidc(self, config: Dict) -> Tuple[bool, str]:
        """
        Test OIDC configuration.

        Args:
            config: OIDC configuration dict

        Returns:
            Tuple of (success, message)
        """
        if not auth_oidc:
            return False, "OIDC module not available"

        log.info("Testing OIDC configuration")
        log.info(f"Issuer: {config.get('issuer', 'MISSING')}")
        return auth_oidc.test_oidc_connection(config)
