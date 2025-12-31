"""
Device Routes
Device management, Netbox sync, manual devices, device overrides

Device routes proxy to devices microservice (devices:8004)
"""

from flask import Blueprint, jsonify, request, render_template, session
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
    """Unified device management page with snapshots and backup features."""
    return render_template('config_backups.html')


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

    # Save task to history for monitor page
    from app import save_task_id
    save_task_id(task_id, device_name=f"test:{device_name}:{task_id}")

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


@devices_bp.route('/api/device-overrides', methods=['POST'])
@login_required
def create_device_override():
    """
    Create or update device-specific overrides.
    Proxied to devices:8004/api/device-overrides
    """
    return proxy_devices_request('/api/device-overrides')


# ============================================================================
# Device Reload API
# ============================================================================

@devices_bp.route('/api/devices/reload', methods=['POST'])
@login_required
def reload_devices():
    """
    Clear device cache and resync from NetBox.
    Proxied to devices:8004/api/devices/sync
    """
    return proxy_devices_request('/api/devices/sync')


# ============================================================================
# Bulk Device Operations API
# ============================================================================

@devices_bp.route('/api/devices/bulk/test', methods=['POST'])
@login_required
def bulk_test_devices():
    """
    Test connectivity to multiple devices.
    Returns task IDs for polling.
    """
    from services.celery_device_service import celery_device_service
    from services.microservice_client import microservice_client

    data = request.get_json() or {}
    device_names = data.get('devices', [])

    if not device_names:
        return error_response("No devices specified", status_code=400)

    task_ids = []

    # Get settings for default credentials
    settings_resp, _ = microservice_client.call_auth('GET', '/api/settings')
    settings = {}
    if settings_resp and settings_resp.status_code == 200:
        settings = settings_resp.json().get('data', {})

    for device_name in device_names:
        # Get device details
        response, error = microservice_client.call_devices('GET', f'/api/devices/{device_name}')

        if error or not response or response.status_code != 200:
            continue

        device_data = response.json().get('data', {}).get('device', {})

        if not device_data:
            continue

        # Get device-specific overrides
        override_resp, _ = microservice_client.call_devices('GET', f'/api/device-overrides/{device_name}')
        override = {}
        if override_resp and override_resp.status_code == 200:
            override = override_resp.json().get('data', {}).get('override', {})

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

        # Skip if no credentials
        if not connection_args.get('username') or not connection_args.get('password'):
            continue

        task_id = celery_device_service.execute_test_connectivity(connection_args)
        task_ids.append(task_id)

        # Save task to history for monitor page
        from app import save_task_id
        save_task_id(task_id, device_name=f"test:{device_name}:{task_id}")

    return success_response(data={'task_ids': task_ids})


@devices_bp.route('/api/devices/bulk/get-config', methods=['POST'])
@login_required
def bulk_get_config():
    """
    Get configuration from multiple devices.
    Returns task IDs for polling.
    """
    from services.celery_device_service import celery_device_service
    from services.microservice_client import microservice_client

    data = request.get_json() or {}
    device_names = data.get('devices', [])
    command = data.get('command', 'show running-config')
    use_textfsm = data.get('use_textfsm', False)
    custom_username = data.get('username')
    custom_password = data.get('password')

    if not device_names:
        return error_response("No devices specified", status_code=400)

    task_ids = []

    # Get settings for default credentials
    settings_resp, _ = microservice_client.call_auth('GET', '/api/settings')
    settings = {}
    if settings_resp and settings_resp.status_code == 200:
        settings = settings_resp.json().get('data', {})

    for device_name in device_names:
        # Get device details
        response, error = microservice_client.call_devices('GET', f'/api/devices/{device_name}')

        if error or not response or response.status_code != 200:
            continue

        device_data = response.json().get('data', {}).get('device', {})

        if not device_data:
            continue

        # Get device-specific overrides
        override_resp, _ = microservice_client.call_devices('GET', f'/api/device-overrides/{device_name}')
        override = {}
        if override_resp and override_resp.status_code == 200:
            override = override_resp.json().get('data', {}).get('override', {})

        # Build connection args
        connection_args = {
            'device_type': device_data.get('device_type', 'cisco_ios'),
            'host': device_data.get('host'),
            'port': override.get('port') or device_data.get('port', 22),
            'username': custom_username or override.get('username') or settings.get('default_username', ''),
            'password': custom_password or override.get('password') or settings.get('default_password', ''),
        }

        if override.get('enable_password'):
            connection_args['secret'] = override['enable_password']

        # Skip if no credentials
        if not connection_args.get('username') or not connection_args.get('password'):
            continue

        task_id = celery_device_service.execute_get_config(
            connection_args,
            command=command,
            use_textfsm=use_textfsm
        )
        task_ids.append(task_id)

        # Save task to history for monitor page
        from app import save_task_id
        save_task_id(task_id, device_name=f"get-config:{device_name}:{task_id}")

    return success_response(data={'task_ids': task_ids})


@devices_bp.route('/api/devices/bulk/set-config', methods=['POST'])
@login_required
def bulk_set_config():
    """
    Set configuration on multiple devices.
    Returns task IDs for polling.
    """
    from services.celery_device_service import celery_device_service
    from services.microservice_client import microservice_client

    data = request.get_json() or {}
    device_names = data.get('devices', [])
    config = data.get('config', '')
    template_name = data.get('template_name')
    template_vars = data.get('template_vars', {})
    dry_run = data.get('dry_run', False)
    custom_username = data.get('username')
    custom_password = data.get('password')

    if not device_names:
        return error_response("No devices specified", status_code=400)

    if not config and not template_name:
        return error_response("No config or template specified", status_code=400)

    task_ids = []

    # Get settings for default credentials
    settings_resp, _ = microservice_client.call_auth('GET', '/api/settings')
    settings = {}
    if settings_resp and settings_resp.status_code == 200:
        settings = settings_resp.json().get('data', {})

    # If using template, render it first
    final_config = config
    if template_name:
        template_resp, _ = microservice_client.call_config('GET', f'/api/templates/{template_name}')
        if template_resp and template_resp.status_code == 200:
            template_data = template_resp.json().get('data', {}).get('template', {})
            template_content = template_data.get('content', '')
            # Render with Jinja2
            from jinja2 import Template
            try:
                jinja_template = Template(template_content)
                final_config = jinja_template.render(**template_vars)
            except Exception as e:
                return error_response(f"Template rendering error: {str(e)}", status_code=400)
        else:
            return error_response(f"Template not found: {template_name}", status_code=404)

    for device_name in device_names:
        # Get device details
        response, error = microservice_client.call_devices('GET', f'/api/devices/{device_name}')

        if error or not response or response.status_code != 200:
            continue

        device_data = response.json().get('data', {}).get('device', {})

        if not device_data:
            continue

        # Get device-specific overrides
        override_resp, _ = microservice_client.call_devices('GET', f'/api/device-overrides/{device_name}')
        override = {}
        if override_resp and override_resp.status_code == 200:
            override = override_resp.json().get('data', {}).get('override', {})

        # Build connection args
        connection_args = {
            'device_type': device_data.get('device_type', 'cisco_ios'),
            'host': device_data.get('host'),
            'port': override.get('port') or device_data.get('port', 22),
            'username': custom_username or override.get('username') or settings.get('default_username', ''),
            'password': custom_password or override.get('password') or settings.get('default_password', ''),
        }

        if override.get('enable_password'):
            connection_args['secret'] = override['enable_password']

        # Skip if no credentials
        if not connection_args.get('username') or not connection_args.get('password'):
            continue

        task_id = celery_device_service.execute_set_config(
            connection_args,
            config=final_config,
            dry_run=dry_run
        )
        task_ids.append(task_id)

        # Save task to history for monitor page
        from app import save_task_id
        save_task_id(task_id, device_name=f"set-config:{device_name}:{task_id}")

    return success_response(data={'task_ids': task_ids})


@devices_bp.route('/api/devices/bulk/backup', methods=['POST'])
@login_required
def bulk_backup_devices():
    """
    Backup configuration from multiple devices.
    Returns task IDs for polling.
    """
    from services.celery_device_service import celery_device_service
    from services.microservice_client import microservice_client

    data = request.get_json() or {}
    device_names = data.get('devices', [])

    if not device_names:
        return error_response("No devices specified", status_code=400)

    task_ids = []

    # Forward JWT token from request
    auth_header = request.headers.get('Authorization', '')
    extra_headers = {'Authorization': auth_header} if auth_header else None

    # Get settings for default credentials
    settings_resp, _ = microservice_client.call_auth('GET', '/api/settings', extra_headers=extra_headers)
    settings = {}
    if settings_resp and settings_resp.status_code == 200:
        settings = settings_resp.json().get('data', {})

    for device_name in device_names:
        # Get device details
        response, error = microservice_client.call_devices('GET', f'/api/devices/{device_name}', extra_headers=extra_headers)

        if error or not response or response.status_code != 200:
            continue

        device_data = response.json().get('data', {}).get('device', {})

        if not device_data:
            continue

        # Get device-specific overrides
        override_resp, _ = microservice_client.call_devices('GET', f'/api/device-overrides/{device_name}', extra_headers=extra_headers)
        override = {}
        if override_resp and override_resp.status_code == 200:
            resp_data = override_resp.json().get('data', {})
            override = resp_data.get('override') if resp_data else {}
            override = override or {}  # Ensure it's never None

        # Build connection args
        connection_args = {
            'device_type': device_data.get('device_type', 'cisco_ios'),
            'host': device_data.get('host'),
            'port': override.get('port') or device_data.get('port') or 22,
            'username': override.get('username') or settings.get('default_username', ''),
            'password': override.get('password') or settings.get('default_password', ''),
        }

        if override.get('enable_password'):
            connection_args['secret'] = override['enable_password']
        elif override.get('secret'):
            connection_args['secret'] = override['secret']

        # Skip if no credentials
        if not connection_args.get('username') or not connection_args.get('password'):
            continue

        # Get username from session or JWT
        username = session.get('username') or getattr(request, 'jwt_user', 'unknown')

        task_id = celery_device_service.execute_backup(
            connection_args=connection_args,
            device_name=device_name,
            device_platform=device_data.get('platform'),
            created_by=username
        )
        task_ids.append(task_id)

        # Save task to history for monitor page
        from app import save_task_id
        save_task_id(task_id, device_name=f"backup:{device_name}:{task_id}")

    return success_response(data={'task_ids': task_ids})


@devices_bp.route('/api/devices/bulk/delete', methods=['POST'])
@login_required
def bulk_delete_devices():
    """
    Delete multiple manual devices.
    Only manual devices can be deleted.
    """
    data = request.get_json() or {}
    device_names = data.get('devices', [])

    if not device_names:
        return error_response("No devices specified", status_code=400)

    deleted = 0
    errors = []

    for device_name in device_names:
        # Proxy delete request to devices microservice
        response = proxy_devices_request(
            '/api/devices/{device_name}',
            device_name=device_name
        )

        # Check if delete was successful
        try:
            result = response.get_json()
            if result.get('success'):
                deleted += 1
            else:
                errors.append(f"{device_name}: {result.get('error', 'Unknown error')}")
        except Exception:
            errors.append(f"{device_name}: Failed to parse response")

    return success_response(data={
        'deleted': deleted,
        'errors': errors if errors else None
    })


