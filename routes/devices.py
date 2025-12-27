"""
Device Routes
Device management, Netbox sync, manual devices, device overrides
"""

from flask import Blueprint, jsonify, request, render_template
import logging

from routes.auth import login_required
import database as db
from services.device_service import (
    get_devices as device_service_get_devices,
    get_cached_devices as device_service_get_cached,
    clear_device_cache as device_service_clear_cache
)
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
# Device List API
# ============================================================================

@devices_bp.route('/api/devices', methods=['GET', 'POST'])
@login_required
@handle_exceptions
def get_devices():
    """
    Get device list from manual devices and Netbox (if configured).
    Uses centralized device cache from device_service.

    GET: Returns all devices
    POST: Accepts filters in request body
    """
    # Get filters from request if provided (POST body)
    filters = []
    if request.method == 'POST' and request.json:
        filter_list = request.json.get('filters', [])
        for f in filter_list:
            if 'key' in f and 'value' in f:
                filters.append({'key': f['key'], 'value': f['value']})

    # Use device service to get devices (handles caching internally)
    result = device_service_get_devices(filters=filters)
    return jsonify(result)


@devices_bp.route('/api/devices/clear-cache', methods=['POST'])
@login_required
@handle_exceptions
def clear_device_cache():
    """Clear the device cache."""
    device_service_clear_cache()
    return success_response(message='Cache cleared successfully')


@devices_bp.route('/api/devices/cached', methods=['GET'])
@login_required
@handle_exceptions
def get_cached_devices():
    """
    Get devices from cache only - does NOT call NetBox.
    Uses centralized device cache from device_service.
    """
    devices = device_service_get_cached()
    return success_response(data={
        'devices': devices,
        'from_cache': True,
        'count': len(devices)
    })


# ============================================================================
# Manual Device Management API
# ============================================================================

@devices_bp.route('/api/manual-devices', methods=['GET'])
@login_required
@handle_exceptions
def get_manual_devices():
    """Get all manual devices."""
    devices = db.get_all_manual_devices()
    return success_response(data={'devices': devices})


@devices_bp.route('/api/manual-devices', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def add_manual_device():
    """
    Add a new manual device.

    Expected JSON body:
    {
        "device_name": "router1",
        "device_type": "cisco_ios",
        "host": "192.168.1.1",
        "port": 22,
        "username": "admin",
        "password": "secret"
    }
    """
    data = request.get_json()
    device_name = data.get('device_name', '').strip()
    device_type = data.get('device_type', '').strip()
    host = data.get('host', '').strip()
    port = data.get('port', 22)
    username = data.get('username', '').strip()
    password = data.get('password', '')

    # Validation
    errors = {}
    if not device_name:
        errors['device_name'] = ['Device name is required']
    if not device_type:
        errors['device_type'] = ['Device type is required']
    if not host:
        errors['host'] = ['Host/IP is required']

    if errors:
        raise ValidationError('Validation failed', field_errors=errors)

    # Check if device already exists
    existing = db.get_manual_device(device_name)
    if existing:
        raise ConflictError(
            f'Device {device_name} already exists',
            conflicting_field='device_name'
        )

    # Add device
    device_data = {
        'device_name': device_name,
        'device_type': device_type,
        'host': host,
        'port': port,
        'username': username,
        'password': password
    }
    db.save_manual_device(device_data)

    log.info(f"Manual device added: {device_name}")
    return success_response(message=f'Device {device_name} added successfully')


@devices_bp.route('/api/manual-devices/<device_name>', methods=['GET'])
@login_required
@handle_exceptions
def get_manual_device(device_name):
    """Get a single manual device by name."""
    device = db.get_manual_device(device_name)
    if not device:
        raise NotFoundError(
            f'Device not found: {device_name}',
            resource_type='ManualDevice',
            resource_id=device_name
        )
    return success_response(data={'device': device})


@devices_bp.route('/api/manual-devices/<device_name>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_manual_device(device_name):
    """Update a manual device."""
    data = request.get_json()

    # Get existing device
    existing = db.get_manual_device(device_name)
    if not existing:
        raise NotFoundError(
            f'Device not found: {device_name}',
            resource_type='ManualDevice',
            resource_id=device_name
        )

    # Update fields
    device_data = {
        'device_name': device_name,
        'device_type': data.get('device_type', existing['device_type']).strip(),
        'host': data.get('host', existing['host']).strip(),
        'port': data.get('port', existing['port']),
        'username': data.get('username', existing.get('username', '')).strip(),
        'password': data.get('password', existing.get('password', ''))
    }

    # Validation
    errors = {}
    if not device_data['device_type']:
        errors['device_type'] = ['Device type is required']
    if not device_data['host']:
        errors['host'] = ['Host/IP is required']

    if errors:
        raise ValidationError('Validation failed', field_errors=errors)

    db.save_manual_device(device_data)

    log.info(f"Manual device updated: {device_name}")
    return success_response(message=f'Device {device_name} updated successfully')


@devices_bp.route('/api/manual-devices/<device_name>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_manual_device(device_name):
    """Delete a manual device."""
    if db.delete_manual_device(device_name):
        log.info(f"Manual device deleted: {device_name}")
        return success_response(message=f'Device {device_name} deleted successfully')
    else:
        raise NotFoundError(
            f'Device not found: {device_name}',
            resource_type='ManualDevice',
            resource_id=device_name
        )


# ============================================================================
# Device Override API
# ============================================================================

@devices_bp.route('/api/device-overrides', methods=['GET'])
@login_required
@handle_exceptions
def get_all_device_overrides():
    """Get all device overrides."""
    overrides = db.get_all_device_overrides()
    return success_response(data={'overrides': overrides})


@devices_bp.route('/api/device-overrides/<device_name>', methods=['GET'])
@login_required
@handle_exceptions
def get_device_override(device_name):
    """Get device-specific overrides for a device."""
    override = db.get_device_override(device_name)
    if not override:
        return success_response(
            data={'override': None},
            message='No override found for this device'
        )
    return success_response(data={'override': override})


@devices_bp.route('/api/device-overrides/<device_name>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def save_device_override(device_name):
    """Save or update device-specific overrides."""
    data = request.get_json()
    data['device_name'] = device_name

    # Don't store empty strings - convert to None
    for key in ['device_type', 'host', 'username', 'password', 'secret', 'notes']:
        if key in data and data[key] == '':
            data[key] = None

    # Convert numeric fields
    for key in ['port', 'timeout', 'conn_timeout', 'auth_timeout', 'banner_timeout']:
        if key in data and data[key] is not None:
            if data[key] == '' or data[key] == 0:
                data[key] = None
            else:
                try:
                    data[key] = int(data[key])
                except (ValueError, TypeError):
                    data[key] = None

    if db.save_device_override(data):
        log.info(f"Device override saved for: {device_name}")
        return success_response(message=f'Override saved for {device_name}')
    else:
        raise ValidationError('Failed to save override')


@devices_bp.route('/api/device-overrides/<device_name>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_device_override(device_name):
    """Delete device-specific overrides."""
    if db.delete_device_override(device_name):
        log.info(f"Device override deleted: {device_name}")
        return success_response(message=f'Override deleted for {device_name}')
    else:
        raise NotFoundError(
            f'Override not found for: {device_name}',
            resource_type='DeviceOverride',
            resource_id=device_name
        )
