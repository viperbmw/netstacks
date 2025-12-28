"""
Admin Routes
User management, admin pages, and user preferences

Note: Authentication config routes are in routes/auth.py to avoid duplication.
User management routes proxy to auth microservice (auth:8011)
"""

from flask import Blueprint, jsonify, request, render_template, session
import logging

from routes.auth import login_required
from services.proxy import proxy_auth_request
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError

log = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


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
# User Management API - Proxied to Auth Microservice
# ============================================================================

@admin_bp.route('/api/users', methods=['GET'])
@login_required
def get_users():
    """Get list of all users. Proxied to auth:8011/api/auth/users"""
    return proxy_auth_request('/api/auth/users')


@admin_bp.route('/api/users', methods=['POST'])
@login_required
def create_user():
    """
    Create a new user. Proxied to auth:8011/api/auth/users

    Expected JSON body:
    {
        "username": "newuser",
        "password": "password123"
    }
    """
    return proxy_auth_request('/api/auth/users')


@admin_bp.route('/api/users/<username>/password', methods=['PUT', 'POST'])
@login_required
def change_password(username):
    """
    Change user password. Proxied to auth:8011/api/auth/users/{username}/password

    Expected JSON body:
    {
        "current_password": "oldpass",
        "new_password": "newpass"
    }
    """
    return proxy_auth_request('/api/auth/users/{username}/password', username=username)


@admin_bp.route('/api/users/<username>', methods=['DELETE'])
@login_required
def delete_user(username):
    """Delete a user. Proxied to auth:8011/api/auth/users/{username}"""
    return proxy_auth_request('/api/auth/users/{username}', username=username)


@admin_bp.route('/api/users/<username>', methods=['GET'])
@login_required
def get_user(username):
    """Get a specific user. Proxied to auth:8011/api/auth/users/{username}"""
    return proxy_auth_request('/api/auth/users/{username}', username=username)


# ============================================================================
# User Theme/Preferences API - Proxied to Auth Microservice
# ============================================================================

@admin_bp.route('/api/user/theme', methods=['GET'])
@login_required
def get_user_theme():
    """Get current user's theme preference."""
    username = session.get('username')
    return proxy_auth_request('/api/auth/users/{username}/theme', username=username)


@admin_bp.route('/api/user/theme', methods=['POST', 'PUT'])
@login_required
def set_user_theme():
    """
    Set current user's theme preference.

    Expected JSON body:
    {
        "theme": "dark"  // or "light"
    }
    """
    username = session.get('username')
    return proxy_auth_request('/api/auth/users/{username}/theme', username=username)


# Note: Authentication page and API routes are defined in routes/auth.py
# to avoid duplicate route registrations
