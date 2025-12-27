"""
Settings Routes
Application settings, Netbox configuration, menu customization
"""

from flask import Blueprint, jsonify, request, render_template
import logging

from services.settings_service import SettingsService, MenuService
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError

log = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# Initialize services
settings_service = SettingsService()
menu_service = MenuService()


# ============================================================================
# Settings Page
# ============================================================================

@settings_bp.route('/settings')
def settings_page():
    """Settings page - renders the settings HTML template"""
    # Note: login_required decorator should be added when auth middleware is ready
    return render_template('settings.html')


# ============================================================================
# Settings API Endpoints
# ============================================================================

@settings_bp.route('/api/settings', methods=['GET'])
@handle_exceptions
def get_settings():
    """
    Get current application settings.

    Returns settings from database with sensitive values masked.
    Includes system timezone from environment variable.
    """
    settings = settings_service.get_all(mask_sensitive=True)
    return success_response(data={'settings': settings})


@settings_bp.route('/api/settings', methods=['POST'])
@handle_exceptions
@require_json
def save_settings():
    """
    Save application settings.

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
    data = request.get_json()

    log.info("[SETTINGS] Received settings save request")

    # Prepare settings dict
    settings_data = {
        'netbox_url': data.get('netbox_url'),
        'netbox_token': data.get('netbox_token'),
        'verify_ssl': data.get('verify_ssl', False),
        'netbox_filters': data.get('netbox_filters', []),
        'cache_ttl': data.get('cache_ttl', 300),
        'default_username': data.get('default_username', ''),
        'default_password': data.get('default_password', ''),
        'system_timezone': data.get('system_timezone', 'UTC')
    }

    settings_service.save(settings_data)

    log.info("Settings saved successfully")
    return success_response(message='Settings saved successfully')


# ============================================================================
# Menu Items API Endpoints
# ============================================================================

@settings_bp.route('/api/menu-items', methods=['GET'])
@handle_exceptions
def get_menu_items():
    """
    Get all menu items.

    Returns list of menu items with order and visibility.
    """
    menu_items = menu_service.get_all()
    return success_response(data={'menu_items': menu_items})


@settings_bp.route('/api/menu-items', methods=['POST'])
@handle_exceptions
@require_json
def update_menu_items():
    """
    Update menu items order and visibility.

    Expected JSON body:
    {
        "menu_items": [
            {"item_id": "devices", "order_index": 1, "visible": true},
            {"item_id": "templates", "order_index": 2, "visible": true},
            ...
        ]
    }
    """
    data = request.get_json()
    menu_items = data.get('menu_items', [])

    if not menu_items:
        raise ValidationError('No menu items provided')

    menu_service.update_order(menu_items)

    log.info("Menu items updated successfully")
    return success_response(message='Menu items updated successfully')
