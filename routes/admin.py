"""
Admin Routes
User management, admin pages, and user preferences
"""

from flask import Blueprint, jsonify, request, render_template, session
import logging

from routes.auth import login_required
from services.user_service import UserService
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json

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
