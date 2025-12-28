"""
Device Routes
Device management, Netbox sync, manual devices, device overrides

Device routes proxy to devices microservice (devices:8004)
"""

from flask import Blueprint, jsonify, request, render_template
import logging

from routes.auth import login_required
from services.proxy import proxy_devices_request
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError, ConflictError

log = logging.getLogger(__name__)

devices_bp = Blueprint('devices', __name__)


# ============================================================================
# Device Pages
# ============================================================================

@devices_bp.route('/devices')
@login_required
def devices_page():
    """Device management page."""
    return render_template('devices.html')


# ============================================================================
# Device List API - Proxied to Devices Microservice
# ============================================================================

@devices_bp.route('/api/devices', methods=['GET'])
@login_required
def get_devices():
    """
    Get device list from devices microservice.
    Proxied to devices:8004/api/devices
    """
    return proxy_devices_request('/api/devices')


@devices_bp.route('/api/devices', methods=['POST'])
@login_required
def create_or_filter_devices():
    """
    Handle POST to /api/devices.

    If request body contains 'filters', this is a device list request (legacy dashboard).
    Otherwise, it's a device creation request which gets proxied.
    """
    data = request.get_json() or {}

    # Check if this is a filter request (from dashboard)
    if 'filters' in data:
        # Use local device service to get devices with filters
        from services.device_service import get_devices as device_service_get_devices
        filters = data.get('filters', [])
        result = device_service_get_devices(filters=filters)
        return jsonify({
            'success': result.get('success', True),
            'devices': result.get('devices', []),
            'cached': result.get('cached', False),
            'sources': result.get('sources', [])
        })

    # Otherwise, proxy to devices microservice for device creation
    return proxy_devices_request('/api/devices')


@devices_bp.route('/api/devices/clear-cache', methods=['POST'])
@login_required
def clear_device_cache():
    """
    Clear the device cache.
    Proxied to devices:8004/api/devices/clear-cache
    """
    return proxy_devices_request('/api/devices/clear-cache')


@devices_bp.route('/api/devices/cached', methods=['GET'])
@login_required
def get_cached_devices():
    """
    Get devices from cache only - does NOT call NetBox.
    Proxied to devices:8004/api/devices/cached
    """
    return proxy_devices_request('/api/devices/cached')


@devices_bp.route('/api/devices/<device_name>', methods=['GET'])
@login_required
def get_device(device_name):
    """
    Get a single device by name.
    Proxied to devices:8004/api/devices/{device_name}
    """
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


@devices_bp.route('/api/devices/<device_name>', methods=['PUT'])
@login_required
def update_device(device_name):
    """
    Update a device.
    Proxied to devices:8004/api/devices/{device_name}
    """
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


@devices_bp.route('/api/devices/<device_name>', methods=['DELETE'])
@login_required
def delete_device(device_name):
    """
    Delete a device.
    Proxied to devices:8004/api/devices/{device_name}
    """
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


@devices_bp.route('/api/devices/<device_name>/test', methods=['POST'])
@login_required
def test_device(device_name):
    """
    Test device connectivity.
    Proxied to devices:8004/api/devices/{device_name}/test
    """
    return proxy_devices_request('/api/devices/{device_name}/test', device_name=device_name)


# ============================================================================
# Manual Device Management API - Aliases for backward compatibility
# These routes map to the same devices microservice endpoints
# ============================================================================

@devices_bp.route('/api/manual-devices', methods=['GET'])
@login_required
def get_manual_devices():
    """
    Get all manual devices.
    Proxied to devices:8004/api/devices?source=manual
    """
    return proxy_devices_request('/api/devices?source=manual')


@devices_bp.route('/api/manual-devices', methods=['POST'])
@login_required
def add_manual_device():
    """
    Add a new manual device.
    Proxied to devices:8004/api/devices
    """
    return proxy_devices_request('/api/devices')


@devices_bp.route('/api/manual-devices/<device_name>', methods=['GET'])
@login_required
def get_manual_device(device_name):
    """Get a single manual device by name."""
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


@devices_bp.route('/api/manual-devices/<device_name>', methods=['PUT'])
@login_required
def update_manual_device(device_name):
    """Update a manual device."""
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


@devices_bp.route('/api/manual-devices/<device_name>', methods=['DELETE'])
@login_required
def delete_manual_device(device_name):
    """Delete a manual device."""
    return proxy_devices_request('/api/devices/{device_name}', device_name=device_name)


# ============================================================================
# Device Override API - Proxied to Devices Microservice
# ============================================================================

@devices_bp.route('/api/device-overrides', methods=['GET'])
@login_required
def get_all_device_overrides():
    """
    Get all device overrides.
    Proxied to devices:8004/api/device-overrides
    """
    return proxy_devices_request('/api/device-overrides')


@devices_bp.route('/api/device-overrides/<device_name>', methods=['GET'])
@login_required
def get_device_override(device_name):
    """
    Get device-specific overrides for a device.
    Proxied to devices:8004/api/device-overrides/{device_name}
    """
    return proxy_devices_request('/api/device-overrides/{device_name}', device_name=device_name)


@devices_bp.route('/api/device-overrides/<device_name>', methods=['PUT'])
@login_required
def save_device_override(device_name):
    """
    Save or update device-specific overrides.
    Proxied to devices:8004/api/device-overrides/{device_name}
    """
    return proxy_devices_request('/api/device-overrides/{device_name}', device_name=device_name)


@devices_bp.route('/api/device-overrides/<device_name>', methods=['DELETE'])
@login_required
def delete_device_override(device_name):
    """
    Delete device-specific overrides.
    Proxied to devices:8004/api/device-overrides/{device_name}
    """
    return proxy_devices_request('/api/device-overrides/{device_name}', device_name=device_name)


# ============================================================================
# Credentials API - Proxied to Devices Microservice
# ============================================================================

@devices_bp.route('/api/credentials', methods=['GET'])
@login_required
def get_credentials():
    """
    Get all credentials (masked).
    Proxied to devices:8004/api/credentials
    """
    return proxy_devices_request('/api/credentials')


@devices_bp.route('/api/credentials', methods=['POST'])
@login_required
def create_credential():
    """
    Create a new credential.
    Proxied to devices:8004/api/credentials
    """
    return proxy_devices_request('/api/credentials')


@devices_bp.route('/api/credentials/<credential_id>', methods=['GET'])
@login_required
def get_credential(credential_id):
    """
    Get a single credential.
    Proxied to devices:8004/api/credentials/{credential_id}
    """
    return proxy_devices_request('/api/credentials/{credential_id}', credential_id=credential_id)


@devices_bp.route('/api/credentials/<credential_id>', methods=['PUT'])
@login_required
def update_credential(credential_id):
    """
    Update a credential.
    Proxied to devices:8004/api/credentials/{credential_id}
    """
    return proxy_devices_request('/api/credentials/{credential_id}', credential_id=credential_id)


@devices_bp.route('/api/credentials/<credential_id>', methods=['DELETE'])
@login_required
def delete_credential(credential_id):
    """
    Delete a credential.
    Proxied to devices:8004/api/credentials/{credential_id}
    """
    return proxy_devices_request('/api/credentials/{credential_id}', credential_id=credential_id)


@devices_bp.route('/api/credentials/<credential_id>/default', methods=['POST'])
@login_required
def set_default_credential(credential_id):
    """
    Set a credential as default.
    Proxied to devices:8004/api/credentials/{credential_id}/default
    """
    return proxy_devices_request('/api/credentials/{credential_id}/default', credential_id=credential_id)
