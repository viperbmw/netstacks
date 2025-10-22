"""
OIDC (OpenID Connect) Authentication Module for NetStacks
Provides OAuth2/OIDC authentication for providers like Okta, Azure AD, Keycloak, etc.
"""
import logging
import secrets
from typing import Dict, Optional, Tuple
from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt
import requests

log = logging.getLogger(__name__)


class OIDCAuthenticator:
    """OIDC authentication handler"""

    def __init__(self, config: Dict, flask_app=None):
        """
        Initialize OIDC authenticator

        Args:
            config: Dictionary containing OIDC configuration
                - client_id: OAuth2 client ID
                - client_secret: OAuth2 client secret
                - discovery_url: OIDC discovery URL (.well-known/openid-configuration)
                - redirect_uri: OAuth2 redirect URI
                - scopes: List of OAuth2 scopes (default: ['openid', 'profile', 'email'])
                - issuer: Token issuer (for validation and auto-discovery)
                - authorize_url: Authorization endpoint URL (if not using discovery)
                - token_url: Token endpoint URL (if not using discovery)
                - userinfo_url: UserInfo endpoint URL (if not using discovery)
                - jwks_uri: JWKS endpoint URL (if not using discovery)
            flask_app: Flask application instance
        """
        self.config = config
        self.client_id = config.get('client_id', '')
        self.client_secret = config.get('client_secret', '')
        self.issuer = config.get('issuer', '')

        # If discovery_url not provided but issuer is, construct discovery URL
        self.discovery_url = config.get('discovery_url', '')
        if not self.discovery_url and self.issuer:
            # Standard OIDC discovery path
            issuer = self.issuer.rstrip('/')
            self.discovery_url = f"{issuer}/.well-known/openid-configuration"

        self.redirect_uri = config.get('redirect_uri', '')
        self.scopes = config.get('scopes', ['openid', 'profile', 'email'])
        if isinstance(self.scopes, str):
            self.scopes = self.scopes.split()

        # Direct endpoint URLs (if not using discovery)
        self.authorize_url = config.get('authorize_url')
        self.token_url = config.get('token_url')
        self.userinfo_url = config.get('userinfo_url')
        self.jwks_uri = config.get('jwks_uri')

        self.flask_app = flask_app
        self.oauth = None
        self._discovery_data = None

    def _fetch_discovery_document(self) -> Optional[Dict]:
        """Fetch OIDC discovery document"""
        if self._discovery_data:
            return self._discovery_data

        if not self.discovery_url:
            return None

        try:
            response = requests.get(self.discovery_url, timeout=10)
            response.raise_for_status()
            self._discovery_data = response.json()
            log.info(f"OIDC: Fetched discovery document from {self.discovery_url}")
            return self._discovery_data
        except Exception as e:
            log.error(f"OIDC: Failed to fetch discovery document: {e}")
            return None

    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Get OIDC authorization URL

        Args:
            state: OAuth2 state parameter (generated if not provided)

        Returns:
            Tuple of (authorization_url, state)
        """
        if not state:
            state = secrets.token_urlsafe(32)

        # Get authorize URL from discovery or config
        authorize_url = self.authorize_url
        if not authorize_url:
            discovery = self._fetch_discovery_document()
            if discovery:
                authorize_url = discovery.get('authorization_endpoint')

        if not authorize_url:
            raise ValueError("OIDC: No authorization endpoint configured")

        # Build authorization URL
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'scope': ' '.join(self.scopes),
            'redirect_uri': self.redirect_uri,
            'state': state
        }

        param_str = '&'.join([f"{k}={requests.utils.quote(v)}" for k, v in params.items()])
        auth_url = f"{authorize_url}?{param_str}"

        log.info(f"OIDC: Generated authorization URL")
        return auth_url, state

    def exchange_code_for_token(self, code: str) -> Optional[Dict]:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from callback

        Returns:
            Token response dictionary or None
        """
        # Get token URL from discovery or config
        token_url = self.token_url
        if not token_url:
            discovery = self._fetch_discovery_document()
            if discovery:
                token_url = discovery.get('token_endpoint')

        if not token_url:
            log.error("OIDC: No token endpoint configured")
            return None

        try:
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.redirect_uri,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }

            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            log.info("OIDC: Successfully exchanged code for token")
            return token_data

        except Exception as e:
            log.error(f"OIDC: Failed to exchange code for token: {e}")
            return None

    def get_user_info(self, access_token: str) -> Optional[Dict]:
        """
        Get user information using access token

        Args:
            access_token: OAuth2 access token

        Returns:
            User information dictionary or None
        """
        # Get userinfo URL from discovery or config
        userinfo_url = self.userinfo_url
        if not userinfo_url:
            discovery = self._fetch_discovery_document()
            if discovery:
                userinfo_url = discovery.get('userinfo_endpoint')

        if not userinfo_url:
            log.error("OIDC: No userinfo endpoint configured")
            return None

        try:
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(userinfo_url, headers=headers, timeout=10)
            response.raise_for_status()

            user_info = response.json()
            log.info(f"OIDC: Retrieved user info for user: {user_info.get('sub', 'unknown')}")
            return user_info

        except Exception as e:
            log.error(f"OIDC: Failed to get user info: {e}")
            return None

    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict]]:
        """
        Verify and decode ID token

        Args:
            token: ID token to verify

        Returns:
            Tuple of (valid: bool, claims: dict or None)
        """
        try:
            # Get JWKS URI from discovery or config
            jwks_uri = self.jwks_uri
            if not jwks_uri:
                discovery = self._fetch_discovery_document()
                if discovery:
                    jwks_uri = discovery.get('jwks_uri')

            if not jwks_uri:
                log.error("OIDC: No JWKS URI configured")
                return False, None

            # Fetch JWKS
            jwks_response = requests.get(jwks_uri, timeout=10)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()

            # Verify and decode token
            claims = jwt.decode(token, jwks)

            # Verify issuer if configured
            if self.issuer and claims.get('iss') != self.issuer:
                log.error(f"OIDC: Token issuer mismatch. Expected: {self.issuer}, Got: {claims.get('iss')}")
                return False, None

            # Verify audience (client_id)
            if claims.get('aud') != self.client_id:
                log.error("OIDC: Token audience mismatch")
                return False, None

            log.info("OIDC: Token verified successfully")
            return True, claims

        except Exception as e:
            log.error(f"OIDC: Token verification failed: {e}")
            return False, None

    def authenticate_callback(self, code: str, state: str, expected_state: str) -> Tuple[bool, Optional[Dict]]:
        """
        Handle OIDC callback and authenticate user

        Args:
            code: Authorization code from callback
            state: State parameter from callback
            expected_state: Expected state value

        Returns:
            Tuple of (success: bool, user_info: dict or None)
        """
        # Verify state
        if state != expected_state:
            log.error("OIDC: State mismatch")
            return False, None

        # Exchange code for token
        token_data = self.exchange_code_for_token(code)
        if not token_data:
            return False, None

        access_token = token_data.get('access_token')
        id_token = token_data.get('id_token')

        if not access_token:
            log.error("OIDC: No access token in response")
            return False, None

        # Verify ID token if present
        if id_token:
            valid, claims = self.verify_token(id_token)
            if not valid:
                log.error("OIDC: ID token verification failed")
                return False, None

        # Get user info
        user_info = self.get_user_info(access_token)
        if not user_info:
            return False, None

        # Standardize user info
        standardized_user = {
            'username': user_info.get('preferred_username') or user_info.get('email') or user_info.get('sub'),
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'sub': user_info.get('sub'),
            'auth_method': 'oidc',
            'raw_user_info': user_info
        }

        log.info(f"OIDC: Successfully authenticated user: {standardized_user['username']}")
        return True, standardized_user

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test OIDC configuration

        Returns:
            Tuple of (success: bool, message: str)
        """
        log.info(f"Testing OIDC connection - client_id: {self.client_id[:10] if self.client_id else 'None'}..., discovery_url: {self.discovery_url}")

        if not self.client_id or not self.client_secret:
            log.error("Missing client_id or client_secret")
            return False, "Missing client_id or client_secret"

        if not self.discovery_url and not (self.authorize_url and self.token_url):
            log.error("Missing discovery_url or explicit endpoint URLs")
            return False, "Missing issuer URL or explicit endpoint URLs"

        # Try to fetch discovery document
        if self.discovery_url:
            log.info(f"Fetching OIDC discovery document from: {self.discovery_url}")
            discovery = self._fetch_discovery_document()
            if not discovery:
                return False, f"Failed to fetch discovery document from {self.discovery_url}. Verify the issuer URL is correct."

            required_endpoints = ['authorization_endpoint', 'token_endpoint', 'userinfo_endpoint']
            missing = [ep for ep in required_endpoints if ep not in discovery]

            if missing:
                return False, f"Discovery document missing endpoints: {', '.join(missing)}"

            log.info("OIDC discovery successful - all required endpoints found")

        return True, "OIDC configuration is valid"


def get_oidc_authorization_url(config: Dict, state: Optional[str] = None) -> Tuple[str, str]:
    """
    Get OIDC authorization URL

    Args:
        config: OIDC configuration dictionary
        state: OAuth2 state parameter

    Returns:
        Tuple of (authorization_url, state)
    """
    authenticator = OIDCAuthenticator(config)
    return authenticator.get_authorization_url(state)


def authenticate_oidc_callback(code: str, state: str, expected_state: str, config: Dict) -> Tuple[bool, Optional[Dict]]:
    """
    Handle OIDC callback

    Args:
        code: Authorization code
        state: State parameter
        expected_state: Expected state value
        config: OIDC configuration dictionary

    Returns:
        Tuple of (success: bool, user_info: dict or None)
    """
    authenticator = OIDCAuthenticator(config)
    return authenticator.authenticate_callback(code, state, expected_state)


def test_oidc_connection(config: Dict) -> Tuple[bool, str]:
    """
    Test OIDC configuration

    Args:
        config: OIDC configuration dictionary

    Returns:
        Tuple of (success: bool, message: str)
    """
    authenticator = OIDCAuthenticator(config)
    return authenticator.test_connection()
