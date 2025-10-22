"""
LDAP Authentication Module for NetStacks
Provides LDAP/Active Directory authentication
"""
import ldap
from ldap.filter import escape_filter_chars
import logging
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)


class LDAPAuthenticator:
    """LDAP authentication handler"""

    def __init__(self, config: Dict):
        """
        Initialize LDAP authenticator

        Args:
            config: Dictionary containing LDAP configuration
                - server: LDAP server URL (ldap://server or ldaps://server)
                - port: LDAP port (default: 389 for ldap, 636 for ldaps)
                - base_dn: Base DN for searches
                - bind_dn: Bind DN for authentication (optional)
                - bind_password: Bind password (optional)
                - user_filter: LDAP filter for finding users (e.g., (uid={username}))
                - attributes: List of attributes to retrieve
                - use_ssl: Whether to use SSL (default: False)
                - verify_cert: Whether to verify SSL certificate (default: True)
                - timeout: Connection timeout in seconds (default: 10)
        """
        self.config = config
        self.server = config.get('server', '')
        self.port = config.get('port', 389)
        self.base_dn = config.get('base_dn', '')
        self.bind_dn = config.get('bind_dn')
        self.bind_password = config.get('bind_password')
        self.user_filter = config.get('user_filter', '(uid={username})')
        self.attributes = config.get('attributes', ['uid', 'cn', 'mail', 'displayName'])
        self.use_ssl = config.get('use_ssl', False)
        self.verify_cert = config.get('verify_cert', True)
        self.timeout = config.get('timeout', 10)

    def _get_ldap_connection(self) -> ldap.ldapobject.LDAPObject:
        """Create and return an LDAP connection"""
        # Check if port is already in server URL
        if ':' in self.server.split('://')[-1]:
            ldap_url = self.server
        else:
            ldap_url = f"{self.server}:{self.port}"

        log.info(f"Connecting to LDAP URL: {ldap_url}")

        # Set LDAP options
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT,
                       ldap.OPT_X_TLS_DEMAND if self.verify_cert else ldap.OPT_X_TLS_NEVER)
        ldap.set_option(ldap.OPT_NETWORK_TIMEOUT, self.timeout)
        ldap.set_option(ldap.OPT_TIMEOUT, self.timeout)

        # Initialize connection
        conn = ldap.initialize(ldap_url)
        conn.protocol_version = ldap.VERSION3

        if self.use_ssl:
            conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            conn.start_tls_s()

        return conn

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        Authenticate a user against LDAP

        Args:
            username: Username to authenticate
            password: Password to verify

        Returns:
            Tuple of (success: bool, user_info: dict or None)
        """
        if not username or not password:
            log.warning("LDAP auth: Empty username or password")
            return False, None

        if not self.server or not self.base_dn:
            log.error("LDAP auth: Invalid configuration - missing server or base_dn")
            return False, None

        conn = None
        try:
            conn = self._get_ldap_connection()

            # Bind with service account if configured
            if self.bind_dn and self.bind_password:
                log.info(f"LDAP auth: Binding with service account: {self.bind_dn}")
                conn.simple_bind_s(self.bind_dn, self.bind_password)
            else:
                log.info("LDAP auth: Using anonymous bind")

            # Search for user
            search_filter = self.user_filter.format(username=escape_filter_chars(username))
            log.info(f"LDAP auth: Searching for user with filter: {search_filter}")

            result = conn.search_s(
                self.base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                self.attributes
            )

            if not result:
                log.warning(f"LDAP auth: User not found: {username}")
                return False, None

            # Get user DN and attributes
            user_dn, user_attrs = result[0]
            log.info(f"LDAP auth: Found user DN: {user_dn}")

            # Try to bind as the user to verify password
            try:
                user_conn = self._get_ldap_connection()
                user_conn.simple_bind_s(user_dn, password)
                user_conn.unbind_s()
                log.info(f"LDAP auth: Successfully authenticated user: {username}")

                # Extract user information
                user_info = {
                    'username': username,
                    'dn': user_dn,
                    'auth_method': 'ldap'
                }

                # Add requested attributes
                for attr in self.attributes:
                    if attr in user_attrs:
                        # Get first value for single-valued attributes
                        values = user_attrs[attr]
                        if isinstance(values, list) and len(values) > 0:
                            user_info[attr] = values[0].decode('utf-8') if isinstance(values[0], bytes) else values[0]

                return True, user_info

            except ldap.INVALID_CREDENTIALS:
                log.warning(f"LDAP auth: Invalid credentials for user: {username}")
                return False, None

        except ldap.SERVER_DOWN:
            log.error(f"LDAP auth: Server is down or unreachable: {self.server}")
            return False, None
        except ldap.TIMEOUT:
            log.error(f"LDAP auth: Connection timeout to: {self.server}")
            return False, None
        except ldap.LDAPError as e:
            log.error(f"LDAP auth error: {e}")
            return False, None
        except Exception as e:
            log.error(f"LDAP auth unexpected error: {e}", exc_info=True)
            return False, None
        finally:
            if conn:
                try:
                    conn.unbind_s()
                except:
                    pass

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test LDAP connection

        Returns:
            Tuple of (success: bool, message: str)
        """
        log.info(f"Testing LDAP connection to {self.server}")
        if not self.server or not self.base_dn:
            log.error("Missing required configuration: server or base_dn")
            return False, "Missing required configuration: server or base_dn"

        conn = None
        try:
            log.info("Initializing LDAP connection...")
            conn = self._get_ldap_connection()

            # Try to bind
            if self.bind_dn and self.bind_password:
                log.info(f"Attempting bind with service account: {self.bind_dn}")
                conn.simple_bind_s(self.bind_dn, self.bind_password)
                log.info("Bind successful")
            else:
                log.info("Attempting anonymous bind")
                conn.simple_bind_s()  # Anonymous bind

            # Try a simple search to verify base_dn
            log.info(f"Searching base DN: {self.base_dn}")
            result = conn.search_s(
                self.base_dn,
                ldap.SCOPE_BASE,
                '(objectClass=*)',
                []
            )
            log.info("Search successful")

            return True, "LDAP connection successful"

        except ldap.INVALID_CREDENTIALS:
            return False, "Invalid bind credentials"
        except ldap.SERVER_DOWN:
            return False, f"LDAP server is down or unreachable: {self.server}"
        except ldap.TIMEOUT:
            return False, f"Connection timeout to: {self.server}"
        except ldap.NO_SUCH_OBJECT:
            return False, f"Base DN not found: {self.base_dn}"
        except ldap.LDAPError as e:
            return False, f"LDAP error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
        finally:
            if conn:
                try:
                    conn.unbind_s()
                except:
                    pass


def authenticate_ldap(username: str, password: str, config: Dict) -> Tuple[bool, Optional[Dict]]:
    """
    Convenience function for LDAP authentication

    Args:
        username: Username to authenticate
        password: Password to verify
        config: LDAP configuration dictionary

    Returns:
        Tuple of (success: bool, user_info: dict or None)
    """
    authenticator = LDAPAuthenticator(config)
    return authenticator.authenticate(username, password)


def test_ldap_connection(config: Dict) -> Tuple[bool, str]:
    """
    Test LDAP connection

    Args:
        config: LDAP configuration dictionary

    Returns:
        Tuple of (success: bool, message: str)
    """
    authenticator = LDAPAuthenticator(config)
    return authenticator.test_connection()
