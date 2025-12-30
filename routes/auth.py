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

    Supports both:
    - Flask session-based auth (for browser sessions)
    - JWT token auth via Authorization header (for API calls)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Flask session first
        if 'username' in session:
            return f(*args, **kwargs)

        # Check for JWT token in Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token:
                # Validate JWT token via auth microservice
                try:
                    import jwt
                    import os
                    secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
                    payload = jwt.decode(token, secret, algorithms=['HS256'])
                    # Token is valid - set username in request context
                    request.jwt_user = payload.get('sub')
                    return f(*args, **kwargs)
                except jwt.ExpiredSignatureError:
                    log.warning("JWT token expired")
                except jwt.InvalidTokenError as e:
                    log.warning(f"Invalid JWT token: {e}")

        # No valid auth - redirect to login for HTML, return 401 for API
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('auth.login', next=request.url))
    return decorated_function


# ============================================================================
# Login/Logout Routes
# ============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if request.method == 'GET':
        # If already logged in, redirect to dashboard
        if 'username' in session:
            return redirect(url_for('pages.index'))

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
        # Login successful via microservice - JWT tokens stored in session
        session['username'] = username
        session['auth_method'] = ms_user_info.get('auth_method', 'local') if ms_user_info else 'local'
        session['login_time'] = datetime.now().isoformat()
        if ms_user_info:
            session['user_info'] = ms_user_info
        # Get JWT tokens from session to pass to frontend
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

        # Login successful - create session
        session['username'] = username
        session['auth_method'] = auth_method
        session['login_time'] = datetime.now().isoformat()

        if user_info:
            session['user_info'] = user_info

        log.info(f"User {username} logged in successfully via local {auth_method}")

    # If we have JWT tokens, render a page that stores them and redirects
    if jwt_tokens and jwt_tokens.get('access_token'):
        return render_template(
            'login_redirect.html',
            jwt_tokens=jwt_tokens,
            redirect_url=url_for('pages.index')
        )

    # Redirect to dashboard
    return redirect(url_for('pages.index'))


@auth_bp.route('/logout')
def logout():
    """Logout and clear session."""
    username = session.get('username', 'unknown')
    microservice_client.clear_tokens()
    session.clear()
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

        # Login successful - create session
        session['username'] = username
        session['auth_method'] = 'oidc'
        session['login_time'] = datetime.now().isoformat()
        session['user_info'] = user_info

        log.info(f"User {username} logged in successfully via OIDC")

        # Redirect to original destination or dashboard
        redirect_url = session.pop('oidc_redirect', url_for('pages.index'))
        session.pop('oidc_state', None)

        return redirect(redirect_url)

    except Exception as e:
        log.error(f"Error processing OIDC callback: {e}", exc_info=True)
        return render_template(
            'login.html',
            error='SSO authentication failed'
        )


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
