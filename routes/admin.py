"""
Admin Routes
User management, admin pages, authentication config, and user preferences
"""

from flask import Blueprint, jsonify, request, render_template, session
import logging

from routes.auth import login_required
from services.user_service import UserService
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError
import database as db
import auth_ldap
import auth_oidc

log = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

# Initialize services
user_service = UserService()


# ============================================================================
# Admin Pages
# ============================================================================

@admin_bp.route('/admin')
@login_required
def admin_page():
    """Admin dashboard page."""
    return render_template('admin.html')


@admin_bp.route('/users')
@login_required
def users_page():
    """User management page."""
    return render_template('admin.html')


# ============================================================================
# User Management API
# ============================================================================

@admin_bp.route('/api/users', methods=['GET'])
@login_required
@handle_exceptions
def get_users():
    """Get list of all users."""
    users = user_service.get_all()
    return success_response(data={'users': users})


@admin_bp.route('/api/users', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_user():
    """
    Create a new user.

    Expected JSON body:
    {
        "username": "newuser",
        "password": "password123"
    }
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user_service.create(username, password)

    current_user = session.get('username')
    log.info(f"User {username} created by {current_user}")

    return success_response(message=f'User {username} created successfully')


@admin_bp.route('/api/users/<username>/password', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def change_password(username):
    """
    Change user password.

    Expected JSON body:
    {
        "current_password": "oldpass",
        "new_password": "newpass"
    }
    """
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    requesting_username = session.get('username')

    user_service.change_password(
        username, current_password, new_password, requesting_username
    )

    log.info(f"Password changed for user {username}")
    return success_response(message='Password changed successfully')


@admin_bp.route('/api/users/<username>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_user(username):
    """Delete a user."""
    current_username = session.get('username')

    user_service.delete(username, current_username)

    log.info(f"User {username} deleted by {current_username}")
    return success_response(message=f'User {username} deleted successfully')


# ============================================================================
# User Theme/Preferences API
# ============================================================================

@admin_bp.route('/api/user/theme', methods=['GET'])
@login_required
@handle_exceptions
def get_user_theme():
    """Get current user's theme preference."""
    username = session.get('username')
    theme = user_service.get_theme(username)
    return success_response(data={'theme': theme})


@admin_bp.route('/api/user/theme', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def set_user_theme():
    """
    Set current user's theme preference.

    Expected JSON body:
    {
        "theme": "dark"  // or "light"
    }
    """
    username = session.get('username')
    data = request.get_json()
    theme = data.get('theme', 'dark')

    user_service.set_theme(username, theme)

    return success_response(
        message='Theme updated successfully',
        data={'theme': theme}
    )


# ============================================================================
# Authentication Page
# ============================================================================

@admin_bp.route('/authentication')
@login_required
def authentication_page():
    """Authentication configuration page."""
    return render_template('admin.html')


# ============================================================================
# Authentication Config API
# ============================================================================

@admin_bp.route('/api/auth/configs', methods=['GET'])
@login_required
@handle_exceptions
def get_auth_configs():
    """Get all authentication configurations."""
    configs = db.get_all_auth_configs()
    return success_response(data={'configs': configs})


@admin_bp.route('/api/auth/config/<auth_type>', methods=['GET'])
@login_required
@handle_exceptions
def get_auth_config(auth_type):
    """Get specific authentication configuration."""
    config = db.get_auth_config(auth_type)
    if not config:
        raise NotFoundError(
            f'Auth config not found: {auth_type}',
            resource_type='AuthConfig',
            resource_id=auth_type
        )
    return jsonify(config)


@admin_bp.route('/api/auth/config', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def save_auth_config():
    """
    Save authentication configuration.

    Expected JSON body:
    {
        "auth_type": "ldap|oidc|local",
        "config_data": {...},
        "is_enabled": true,
        "priority": 0
    }
    """
    data = request.get_json()
    auth_type = data.get('auth_type')
    config_data = data.get('config_data', {})
    is_enabled = data.get('is_enabled', True)
    priority = data.get('priority', 0)

    if not auth_type:
        raise ValidationError('auth_type is required')

    if auth_type not in ['local', 'ldap', 'oidc']:
        raise ValidationError('Invalid auth_type. Must be local, ldap, or oidc')

    db.save_auth_config(auth_type, config_data, is_enabled, priority)

    return success_response(
        message=f'{auth_type.upper()} configuration saved successfully'
    )


@admin_bp.route('/api/auth/config/<auth_type>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_auth_config(auth_type):
    """Delete authentication configuration."""
    success = db.delete_auth_config(auth_type)
    if not success:
        raise NotFoundError(
            f'Auth config not found: {auth_type}',
            resource_type='AuthConfig',
            resource_id=auth_type
        )
    return success_response(
        message=f'{auth_type.upper()} configuration deleted successfully'
    )


@admin_bp.route('/api/auth/config/<auth_type>/toggle', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def toggle_auth_config(auth_type):
    """Enable or disable authentication method."""
    data = request.get_json()
    enabled = data.get('enabled', True)

    log.info(f"Toggling {auth_type} to {'enabled' if enabled else 'disabled'}")
    success = db.toggle_auth_config(auth_type, enabled)

    if not success:
        raise NotFoundError(
            f'Auth config not found: {auth_type}',
            resource_type='AuthConfig',
            resource_id=auth_type
        )

    status = 'enabled' if enabled else 'disabled'
    log.info(f"{auth_type.upper()} authentication {status} successfully")
    return success_response(
        message=f'{auth_type.upper()} authentication {status} successfully'
    )


@admin_bp.route('/api/auth/test/ldap', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def test_ldap_connection():
    """Test LDAP connection with provided configuration."""
    data = request.get_json()
    config = data.get('config', {})

    log.info(f"Testing LDAP with config: server={config.get('server')}, base_dn={config.get('base_dn')}")

    success, message = auth_ldap.test_ldap_connection(config)

    return jsonify({
        'success': success,
        'message': message
    })


@admin_bp.route('/api/auth/test/oidc', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def test_oidc_connection():
    """Test OIDC configuration."""
    data = request.get_json()
    config = data.get('config', {})

    log.info("Testing OIDC connection")
    log.info(f"Issuer: {config.get('issuer', 'MISSING')}")

    success, message = auth_oidc.test_oidc_connection(config)

    return jsonify({
        'success': success,
        'message': message
    })


@admin_bp.route('/api/auth/local/priority', methods=['GET', 'POST'])
@login_required
@handle_exceptions
def local_auth_priority():
    """Get or set local authentication priority."""
    if request.method == 'GET':
        priority = db.get_setting('local_auth_priority', '999')
        return success_response(data={'priority': int(priority)})
    else:
        data = request.get_json() or {}
        priority = data.get('priority', 999)
        db.set_setting('local_auth_priority', str(priority))
        log.info(f"Updated local auth priority to: {priority}")
        return success_response(message='Local auth priority updated')
