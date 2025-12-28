"""
Settings Routes
Application settings, Netbox configuration, menu customization

Settings routes proxy to auth microservice (auth:8011)
"""

from flask import Blueprint, jsonify, request, render_template
import logging

from routes.auth import login_required
from services.proxy import proxy_auth_request
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError

log = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)


# ============================================================================
# Settings Page
# ============================================================================

@settings_bp.route('/settings')
@login_required
def settings_page():
    """Settings page - renders the settings HTML template"""
    return render_template('settings.html')


# ============================================================================
# Settings API Endpoints - Proxied to Auth Microservice
# ============================================================================

@settings_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    """
    Get current application settings.
    Proxied to auth:8011/api/settings/settings
    """
    return proxy_auth_request('/api/settings/settings')


@settings_bp.route('/api/settings', methods=['POST', 'PUT'])
@login_required
def save_settings():
    """
    Save application settings.
    Proxied to auth:8011/api/settings/settings

    Expected JSON body:
    {
        "netbox_url": "https://netbox.example.com",
        "netbox_token": "token-here",
        "verify_ssl": false,
        "netbox_filters": [],
        "cache_ttl": 300,
        "default_username": "",
        "default_password": "",
        "system_timezone": "UTC"
    }
    """
    return proxy_auth_request('/api/settings/settings')


@settings_bp.route('/api/settings/<category>', methods=['GET'])
@login_required
def get_settings_by_category(category):
    """
    Get settings by category.
    Proxied to auth:8011/api/settings/{category}
    """
    return proxy_auth_request('/api/settings/{category}', category=category)
