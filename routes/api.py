"""
API Routes
API resources, menu items, and general API endpoints (non-Celery)
"""
from flask import Blueprint, jsonify, request, session
import logging
import uuid

from routes.auth import login_required
import database as db
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError

log = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


# ============================================================================
# API Documentation
# ============================================================================

@api_bp.route('/api-docs')
@login_required
@handle_exceptions
def api_docs():
    """API documentation - show local Celery-based API info."""
    return success_response(data={
        'message': 'NetStacks API',
        'endpoints': {
            '/api/celery/getconfig': 'Execute show commands via Celery',
            '/api/celery/setconfig': 'Push configuration via Celery',
            '/api/celery/task/<task_id>': 'Get task status',
            '/api/v2/templates': 'Template management'
        }
    })


# ============================================================================
# Menu Items API
# ============================================================================

@api_bp.route('/api/menu-items', methods=['GET'])
@login_required
@handle_exceptions
def get_menu_items():
    """Get all menu items."""
    menu_items = db.get_menu_items()
    return success_response(data={'menu_items': menu_items})


@api_bp.route('/api/menu-items', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def update_menu_items():
    """
    Update menu items order and visibility.

    Expected JSON body:
    {
        "menu_items": [
            {"id": "dashboard", "order": 1, "visible": true},
            ...
        ]
    }
    """
    data = request.get_json()
    menu_items = data.get('menu_items', [])

    if not menu_items:
        raise ValidationError('No menu items provided')

    db.update_menu_order(menu_items)
    log.info("Menu items updated successfully")
    return success_response(message='Menu items updated successfully')


# ============================================================================
# API Resources CRUD
# ============================================================================

@api_bp.route('/api/api-resources', methods=['GET'])
@login_required
@handle_exceptions
def get_api_resources():
    """Get all API resources."""
    resources = db.get_all_api_resources()
    return success_response(data={'resources': resources})


@api_bp.route('/api/api-resources', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_api_resource():
    """
    Create a new API resource.

    Expected JSON body:
    {
        "name": "Resource Name",
        "base_url": "https://api.example.com",
        "description": "Optional description",
        "auth_type": "none|bearer|api_key|basic|custom",
        "auth_token": "token for bearer/api_key",
        "auth_username": "username for basic",
        "auth_password": "password for basic",
        "custom_headers": {}
    }
    """
    data = request.get_json()

    if not data.get('name') or not data.get('base_url'):
        raise ValidationError('Name and Base URL are required')

    resource_id = str(uuid.uuid4())
    created_by = session.get('username', 'unknown')

    db.create_api_resource(
        resource_id=resource_id,
        name=data.get('name'),
        description=data.get('description', ''),
        base_url=data.get('base_url'),
        auth_type=data.get('auth_type', 'none'),
        auth_token=data.get('auth_token', ''),
        auth_username=data.get('auth_username', ''),
        auth_password=data.get('auth_password', ''),
        custom_headers=data.get('custom_headers'),
        created_by=created_by
    )

    log.info(f"API Resource created: {data.get('name')} by {created_by}")
    return success_response(data={'resource_id': resource_id})


@api_bp.route('/api/api-resources/<resource_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_api_resource(resource_id):
    """Get a specific API resource."""
    resource = db.get_api_resource(resource_id)
    if not resource:
        raise NotFoundError(
            f'Resource not found: {resource_id}',
            resource_type='APIResource',
            resource_id=resource_id
        )
    return success_response(data={'resource': resource})


@api_bp.route('/api/api-resources/<resource_id>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_api_resource(resource_id):
    """Update an existing API resource."""
    data = request.get_json()

    if not data.get('name') or not data.get('base_url'):
        raise ValidationError('Name and Base URL are required')

    # Verify resource exists
    existing = db.get_api_resource(resource_id)
    if not existing:
        raise NotFoundError(
            f'Resource not found: {resource_id}',
            resource_type='APIResource',
            resource_id=resource_id
        )

    db.update_api_resource(
        resource_id=resource_id,
        name=data.get('name'),
        description=data.get('description', ''),
        base_url=data.get('base_url'),
        auth_type=data.get('auth_type', 'none'),
        auth_token=data.get('auth_token', ''),
        auth_username=data.get('auth_username', ''),
        auth_password=data.get('auth_password', ''),
        custom_headers=data.get('custom_headers')
    )

    log.info(f"API Resource updated: {resource_id}")
    return success_response()


@api_bp.route('/api/api-resources/<resource_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_api_resource(resource_id):
    """Delete an API resource."""
    # Verify resource exists
    existing = db.get_api_resource(resource_id)
    if not existing:
        raise NotFoundError(
            f'Resource not found: {resource_id}',
            resource_type='APIResource',
            resource_id=resource_id
        )

    db.delete_api_resource(resource_id)
    log.info(f"API Resource deleted: {resource_id}")
    return success_response()


# ============================================================================
# Config Backup CRUD (non-Celery operations)
# ============================================================================

@api_bp.route('/api/config-backups', methods=['GET'])
@login_required
@handle_exceptions
def list_config_backups():
    """List config backups with optional filters."""
    device_name = request.args.get('device')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    backups = db.get_config_backups(device_name=device_name, limit=limit, offset=offset)
    summary = db.get_backup_summary()

    return success_response(data={
        'backups': backups,
        'summary': summary,
        'limit': limit,
        'offset': offset
    })


@api_bp.route('/api/config-backups/<backup_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_config_backup(backup_id):
    """Get a specific backup by ID."""
    backup = db.get_config_backup(backup_id)
    if not backup:
        raise NotFoundError(
            f'Backup not found: {backup_id}',
            resource_type='ConfigBackup',
            resource_id=backup_id
        )
    return success_response(data={'backup': backup})


@api_bp.route('/api/config-backups/<backup_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_config_backup(backup_id):
    """Delete a specific backup."""
    if db.delete_config_backup(backup_id):
        log.info(f"Config backup deleted: {backup_id}")
        return success_response(message='Backup deleted')
    else:
        raise NotFoundError(
            f'Backup not found: {backup_id}',
            resource_type='ConfigBackup',
            resource_id=backup_id
        )


@api_bp.route('/api/config-backups/device/<device_name>/latest', methods=['GET'])
@login_required
@handle_exceptions
def get_latest_device_backup(device_name):
    """Get the latest backup for a specific device."""
    backup = db.get_latest_backup_for_device(device_name)
    if not backup:
        raise NotFoundError(
            f'No backup found for device: {device_name}',
            resource_type='ConfigBackup',
            resource_id=device_name
        )
    return success_response(data={'backup': backup})


@api_bp.route('/api/backup-schedule', methods=['GET'])
@login_required
@handle_exceptions
def get_backup_schedule():
    """Get the backup schedule configuration."""
    schedule = db.get_backup_schedule()
    if not schedule:
        # Return defaults
        schedule = {
            'schedule_id': 'default',
            'enabled': False,
            'interval_hours': 24,
            'retention_days': 30,
            'juniper_set_format': True,
            'include_filters': [],
            'exclude_patterns': []
        }
    return success_response(data={'schedule': schedule})


@api_bp.route('/api/backup-schedule', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_backup_schedule():
    """
    Update the backup schedule configuration.

    Expected JSON body:
    {
        "enabled": true,
        "interval_hours": 24,
        "retention_days": 30,
        "juniper_set_format": true,
        "include_filters": [],
        "exclude_patterns": []
    }
    """
    data = request.get_json()

    schedule_data = {
        'schedule_id': 'default',
        'enabled': data.get('enabled', False),
        'interval_hours': data.get('interval_hours', 24),
        'retention_days': data.get('retention_days', 30),
        'juniper_set_format': data.get('juniper_set_format', True),
        'include_filters': data.get('include_filters', []),
        'exclude_patterns': data.get('exclude_patterns', [])
    }

    db.save_backup_schedule(schedule_data)
    log.info(f"Backup schedule updated: enabled={schedule_data['enabled']}, interval={schedule_data['interval_hours']}h")

    return success_response(
        message='Backup schedule updated',
        data={'schedule': schedule_data}
    )


@api_bp.route('/api/config-backups/cleanup', methods=['POST'])
@login_required
@handle_exceptions
def cleanup_old_backups():
    """Delete backups older than retention period."""
    data = request.get_json() or {}
    retention_days = data.get('retention_days')

    if not retention_days:
        schedule = db.get_backup_schedule()
        retention_days = schedule.get('retention_days', 30) if schedule else 30

    deleted_count = db.delete_old_backups(retention_days)
    log.info(f"Cleaned up {deleted_count} old backups (older than {retention_days} days)")

    return success_response(data={
        'deleted_count': deleted_count,
        'retention_days': retention_days
    })


# ============================================================================
# Routes that remain in app.py (require Celery):
# ============================================================================
#
# - /api/tasks - Get task list (queries Celery)
# - /api/tasks/metadata - Get task metadata
# - /api/task/<task_id> - Get task status (queries Celery)
# - /api/task/<task_id>/result - Get task result (queries Celery)
# - /api/workers - Get Celery worker info
# - /api/workers/tasks - Get registered Celery tasks
# - /api/config-backups/run-single - Triggers Celery backup task
# - /api/config-backups/run-all - Triggers Celery backup tasks
# - /api/config-backups/task/<task_id> - Check backup task status
# - /api/config-backups/cleanup-orphans - Uses device cache (could be migrated)
# - /api/proxy-api-call - Makes external HTTP requests
