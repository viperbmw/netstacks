"""
Authentication Routes
Login, logout, OIDC, session management, and auth configuration
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, jsonify
)
from functools import wraps
from datetime import datetime
import logging

from services.auth_service import AuthService, OIDCService, AuthConfigService
from services.microservice_client import microservice_client
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, AuthenticationError, NotFoundError

log = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Initialize services
auth_service = AuthService()
oidc_service = OIDCService(auth_service)
auth_config_service = AuthConfigService()


# ============================================================================
# Login Required Decorator
# ============================================================================

def login_required(f):
    """
    Decorator to require login for routes.

    Uses JWT-only authentication via Authorization header.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        import jwt
        import os

        # Check for JWT token in Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token:
                try:
                    secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
                    payload = jwt.decode(token, secret, algorithms=['HS256'])
                    # Token is valid - set username in request context
                    request.jwt_user = payload.get('sub')
                    request.jwt_payload = payload
                    return f(*args, **kwargs)
                except jwt.ExpiredSignatureError:
                    log.warning("JWT token expired")
                    if request.path.startswith('/api/'):
                        return jsonify({'error': 'Token expired', 'code': 'TOKEN_EXPIRED'}), 401
                except jwt.InvalidTokenError as e:
                    log.warning(f"Invalid JWT token: {e}")

        # No valid auth - redirect to login for HTML, return 401 for API
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('auth.login', next=request.url))
    return decorated_function


def get_current_user():
    """Get the current authenticated user from JWT or return 'unknown'."""
    return getattr(request, 'jwt_user', None) or 'unknown'


# ============================================================================
# Login/Logout Routes
# ============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if request.method == 'GET':
        # Check if OIDC is enabled for SSO button
        auth_configs = auth_config_service.get_enabled_configs()
        oidc_enabled = any(
            config['auth_type'] == 'oidc' for config in auth_configs
        )

        return render_template('login.html', oidc_enabled=oidc_enabled)

    # Handle POST - login attempt
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return render_template(
            'login.html',
            error='Username and password are required'
        )

    # Try auth microservice first
    ms_success, ms_user_info = microservice_client.login(username, password)

    jwt_tokens = None
    if ms_success:
        # Login successful via microservice - get JWT tokens
        jwt_tokens = {
            'access_token': microservice_client.get_jwt_token(),
            'refresh_token': microservice_client.get_refresh_token(),
            'expires_in': 1800  # 30 minutes default
        }
        log.info(f"User {username} logged in successfully via auth microservice")
    else:
        # Fallback to local auth service if microservice unavailable
        success, user_info, auth_method = auth_service.authenticate(
            username, password
        )

        if not success:
            return render_template(
                'login.html',
                error='Invalid username or password'
            )

        # Login successful via local auth - generate JWT tokens locally
        import jwt as pyjwt
        import os
        from datetime import timedelta

        secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
        now = datetime.utcnow()
        access_expires = now + timedelta(minutes=30)
        refresh_expires = now + timedelta(days=7)

        access_token = pyjwt.encode({
            'sub': username,
            'iat': now,
            'exp': access_expires,
            'type': 'access',
            'auth_method': auth_method
        }, secret, algorithm='HS256')

        refresh_token = pyjwt.encode({
            'sub': username,
            'iat': now,
            'exp': refresh_expires,
            'type': 'refresh'
        }, secret, algorithm='HS256')

        jwt_tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': 1800
        }
        log.info(f"User {username} logged in successfully via local {auth_method}")

    # Always return JWT tokens via redirect page (stores in localStorage)
    if jwt_tokens and jwt_tokens.get('access_token'):
        return render_template(
            'login_redirect.html',
            jwt_tokens=jwt_tokens,
            redirect_url=url_for('pages.index')
        )

    # Fallback if no tokens (shouldn't happen)
    return render_template('login.html', error='Authentication failed')


@auth_bp.route('/logout')
def logout():
    """
    Logout endpoint.

    For JWT-only auth, the frontend clears localStorage tokens.
    This endpoint just redirects to login page and logs the action.
    """
    # Try to get username from JWT if available
    username = get_current_user()
    log.info(f"User {username} logged out")
    return redirect(url_for('auth.login'))


# ============================================================================
# OIDC Routes
# ============================================================================

@auth_bp.route('/login/oidc')
def login_oidc():
    """Initiate OIDC login flow."""
    # Get OIDC configuration
    oidc_config = auth_config_service.get_config('oidc')

    if not oidc_config or not oidc_config.get('is_enabled'):
        return render_template(
            'login.html',
            error='OIDC authentication is not configured'
        )

    try:
        # Generate authorization URL
        config_data = oidc_config['config_data']
        auth_url, state = oidc_service.get_authorization_url(config_data)

        # Store state in session for verification
        session['oidc_state'] = state
        session['oidc_redirect'] = request.args.get('next', url_for('pages.index'))

        # Redirect to OIDC provider
        return redirect(auth_url)

    except Exception as e:
        log.error(f"Error initiating OIDC login: {e}", exc_info=True)
        return render_template(
            'login.html',
            error='Failed to initiate SSO login'
        )


@auth_bp.route('/login/oidc/callback')
def login_oidc_callback():
    """Handle OIDC callback."""
    # Get authorization code and state from callback
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    if error:
        log.error(f"OIDC callback error: {error}")
        return render_template(
            'login.html',
            error=f'SSO authentication failed: {error}'
        )

    if not code or not state:
        return render_template(
            'login.html',
            error='Invalid SSO callback'
        )

    # Verify state
    expected_state = session.get('oidc_state')
    if not expected_state or state != expected_state:
        log.error("OIDC state mismatch")
        return render_template(
            'login.html',
            error='SSO authentication failed: Invalid state'
        )

    # Get OIDC configuration
    oidc_config = auth_config_service.get_config('oidc')
    if not oidc_config:
        return render_template(
            'login.html',
            error='OIDC authentication is not configured'
        )

    try:
        # Process callback
        config_data = oidc_config['config_data']
        success, user_info = oidc_service.process_callback(
            code, state, expected_state, config_data
        )

        if not success or not user_info:
            return render_template(
                'login.html',
                error='SSO authentication failed'
            )

        username = user_info['username']

        # Login successful - generate JWT tokens
        import jwt as pyjwt
        import os
        from datetime import timedelta

        secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
        now = datetime.utcnow()
        access_expires = now + timedelta(minutes=30)
        refresh_expires = now + timedelta(days=7)

        access_token = pyjwt.encode({
            'sub': username,
            'iat': now,
            'exp': access_expires,
            'type': 'access',
            'auth_method': 'oidc'
        }, secret, algorithm='HS256')

        refresh_token = pyjwt.encode({
            'sub': username,
            'iat': now,
            'exp': refresh_expires,
            'type': 'refresh'
        }, secret, algorithm='HS256')

        jwt_tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': 1800
        }

        log.info(f"User {username} logged in successfully via OIDC")

        # Get redirect URL (stored before OIDC flow started)
        redirect_url = session.pop('oidc_redirect', url_for('pages.index'))
        session.pop('oidc_state', None)

        # Return JWT tokens via redirect page (stores in localStorage)
        return render_template(
            'login_redirect.html',
            jwt_tokens=jwt_tokens,
            redirect_url=redirect_url
        )

    except Exception as e:
        log.error(f"Error processing OIDC callback: {e}", exc_info=True)
        return render_template(
            'login.html',
            error='SSO authentication failed'
        )


# ============================================================================
# Token Refresh API
# ============================================================================

@auth_bp.route('/api/auth/refresh', methods=['POST'])
@require_json
def refresh_token():
    """
    Refresh JWT access token using a refresh token.

    Expected JSON body:
    {
        "refresh_token": "jwt-refresh-token"
    }
    """
    import jwt as pyjwt
    import os
    from datetime import timedelta

    data = request.get_json()
    refresh_token = data.get('refresh_token')

    if not refresh_token:
        return jsonify({'error': 'Refresh token required'}), 400

    try:
        secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
        payload = pyjwt.decode(refresh_token, secret, algorithms=['HS256'])

        # Verify it's a refresh token
        if payload.get('type') != 'refresh':
            return jsonify({'error': 'Invalid token type'}), 400

        username = payload.get('sub')
        if not username:
            return jsonify({'error': 'Invalid token'}), 400

        # Generate new access token
        now = datetime.utcnow()
        access_expires = now + timedelta(minutes=30)

        access_token = pyjwt.encode({
            'sub': username,
            'iat': now,
            'exp': access_expires,
            'type': 'access'
        }, secret, algorithm='HS256')

        log.info(f"Access token refreshed for user {username}")

        return jsonify({
            'access_token': access_token,
            'expires_in': 1800
        })

    except pyjwt.ExpiredSignatureError:
        log.warning("Refresh token expired")
        return jsonify({'error': 'Refresh token expired'}), 401
    except pyjwt.InvalidTokenError as e:
        log.warning(f"Invalid refresh token: {e}")
        return jsonify({'error': 'Invalid refresh token'}), 401


# ============================================================================
# Auth Configuration API Routes
# ============================================================================

@auth_bp.route('/authentication')
@login_required
def authentication_page():
    """Authentication configuration page."""
    return render_template('admin.html')


@auth_bp.route('/api/auth/configs', methods=['GET'])
@login_required
@handle_exceptions
def get_auth_configs():
    """Get all authentication configurations."""
    configs = auth_config_service.get_all_configs()
    return success_response(data={'configs': configs})


@auth_bp.route('/api/auth/config/<auth_type>', methods=['GET'])
@login_required
@handle_exceptions
def get_auth_config(auth_type):
    """Get specific authentication configuration."""
    config = auth_config_service.get_config(auth_type)
    if not config:
        raise NotFoundError(f"Configuration not found: {auth_type}")
    return jsonify(config)


@auth_bp.route('/api/auth/config', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def save_auth_config():
    """
    Save authentication configuration.

    Expected JSON body:
    {
        "auth_type": "ldap",
        "config_data": {...},
        "is_enabled": true,
        "priority": 1
    }
    """
    data = request.get_json()
    auth_type = data.get('auth_type')
    config_data = data.get('config_data', {})
    is_enabled = data.get('is_enabled', True)
    priority = data.get('priority', 0)

    if not auth_type:
        raise ValidationError('auth_type is required')

    auth_config_service.save_config(
        auth_type, config_data, is_enabled, priority
    )

    return success_response(
        message=f'{auth_type.upper()} configuration saved successfully'
    )


@auth_bp.route('/api/auth/config/<auth_type>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_auth_config(auth_type):
    """Delete authentication configuration."""
    auth_config_service.delete_config(auth_type)
    return success_response(
        message=f'{auth_type.upper()} configuration deleted successfully'
    )


@auth_bp.route('/api/auth/config/<auth_type>/toggle', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def toggle_auth_config(auth_type):
    """Enable or disable authentication method."""
    data = request.get_json()
    enabled = data.get('enabled', True)

    log.info(f"Toggling {auth_type} to {'enabled' if enabled else 'disabled'}")
    auth_config_service.toggle_config(auth_type, enabled)

    status = 'enabled' if enabled else 'disabled'
    return success_response(
        message=f'{auth_type.upper()} authentication {status} successfully'
    )


@auth_bp.route('/api/auth/test/ldap', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def test_ldap_connection():
    """Test LDAP connection."""
    data = request.get_json()
    config = data.get('config', {})

    success, message = auth_config_service.test_ldap(config)

    return jsonify({
        'success': success,
        'message': message
    })


@auth_bp.route('/api/auth/test/oidc', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def test_oidc_connection():
    """Test OIDC configuration."""
    data = request.get_json()
    config = data.get('config', {})

    success, message = auth_config_service.test_oidc(config)

    return jsonify({
        'success': success,
        'message': message
    })


@auth_bp.route('/api/auth/local/priority', methods=['GET', 'POST'])
@login_required
@handle_exceptions
def local_auth_priority():
    """Get or set local authentication priority."""
    if request.method == 'GET':
        priority = auth_config_service.get_local_priority()
        return success_response(data={'priority': priority})

    # POST
    data = request.get_json()
    priority = data.get('priority', 999)
    auth_config_service.set_local_priority(priority)

    return success_response(message='Local auth priority updated')
