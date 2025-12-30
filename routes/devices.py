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

    If request body contains 'filters', proxy to /api/devices/list endpoint.
    Otherwise, it's a device creation request which gets proxied to /api/devices.
    """
    data = request.get_json() or {}

    # Check if this is a filter request (from dashboard)
    if 'filters' in data:
        # Proxy to devices microservice list endpoint
        return proxy_devices_request('/api/devices/list')

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


@devices_bp.route('/api/devices/sync', methods=['POST'])
@login_required
def sync_devices():
    """
    Sync devices from NetBox.
    Proxied to devices:8004/api/devices/sync
    """
    return proxy_devices_request('/api/devices/sync')


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
    Test device connectivity via Celery task.

    This dispatches a real Netmiko connection test to the Celery workers.
    Returns a task_id that can be polled for results.
    """
    import requests
    import os
    from services.microservice_client import microservice_client
    from services.celery_device_service import celery_device_service

    # Get device from microservice
    response, error = microservice_client.call_devices('GET', f'/api/devices/{device_name}')

    if error or not response or response.status_code != 200:
        return error_response(f"Device not found: {device_name}", status_code=404)

    device_data = response.json().get('data', {}).get('device', {})

    if not device_data:
        return error_response(f"Device not found: {device_name}", status_code=404)

    # Get credentials (try device-specific overrides first, then defaults from settings)
    override_resp, _ = microservice_client.call_devices('GET', f'/api/device-overrides/{device_name}')
    override = {}
    if override_resp and override_resp.status_code == 200:
        override = override_resp.json().get('data', {}).get('override', {})

    # Get default credentials from settings
    settings_resp, _ = microservice_client.call_auth('GET', '/api/settings')
    settings = {}
    if settings_resp and settings_resp.status_code == 200:
        settings = settings_resp.json().get('data', {})

    # Build connection args
    connection_args = {
        'device_type': device_data.get('device_type', 'cisco_ios'),
        'host': device_data.get('host'),
        'port': override.get('port') or device_data.get('port', 22),
        'username': override.get('username') or settings.get('default_username', ''),
        'password': override.get('password') or settings.get('default_password', ''),
    }

    if override.get('enable_password'):
        connection_args['secret'] = override['enable_password']

    # Check if credentials are configured
    if not connection_args.get('username') or not connection_args.get('password'):
        return error_response(
            "Device credentials not configured. Set default credentials in Settings or add device-specific credentials.",
            status_code=400
        )

    # Dispatch connectivity test task
    task_id = celery_device_service.execute_test_connectivity(connection_args)

    return success_response(
        data={
            'task_id': task_id,
            'device': device_name,
            'host': connection_args.get('host'),
            'device_type': connection_args.get('device_type'),
            'status': 'pending',
            'message': 'Connectivity test started'
        }
    )


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


