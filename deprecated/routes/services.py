"""
Service Routes
Service instances, templates, and service management pages
"""
from flask import Blueprint, jsonify, request, render_template
import logging
import re

from routes.auth import login_required
import database as db
from services.stack_service import ServiceInstanceService
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions
from utils.exceptions import NotFoundError

log = logging.getLogger(__name__)

services_bp = Blueprint('services', __name__)

# Initialize service
service_instance_service = ServiceInstanceService()


# ============================================================================
# Service Pages
# ============================================================================

@services_bp.route('/services')
@login_required
def services_page():
    """Render services management page."""
    return render_template('services.html')


# /service-stacks page is in routes/stacks.py

# ============================================================================
# Service Template API
# ============================================================================

@services_bp.route('/api/services/templates', methods=['GET'])
@login_required
@handle_exceptions
def get_service_templates():
    """
    List all available service templates from local database.
    Returns only deploy-type templates.
    """
    all_templates = db.get_all_templates()
    templates = [
        {'name': t['name'], 'description': t.get('description', '')}
        for t in all_templates
        if t.get('type', 'deploy') == 'deploy'
    ]
    return success_response(data={'templates': templates})


@services_bp.route('/api/services/templates/<template_name>/schema', methods=['GET'])
@login_required
@handle_exceptions
def get_service_template_schema(template_name):
    """
    Get schema for a service template by extracting variables from template.

    Returns a schema with properties derived from Jinja2 variable patterns
    found in the template content.
    """
    # Strip .j2 extension if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    # Get template content
    template_content = db.get_template_content(template_name)
    if not template_content:
        return success_response(data={'schema': None})

    # Extract variables from template
    variable_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
    variables = list(set(re.findall(variable_pattern, template_content)))

    # Build a simple schema from extracted variables
    schema = {
        'properties': {var: {'type': 'string'} for var in variables},
        'required': variables
    }

    return success_response(data={'schema': schema})


# ============================================================================
# Service Instance API - Read Operations
# ============================================================================

@services_bp.route('/api/services/instances', methods=['GET'])
@login_required
@handle_exceptions
def get_service_instances():
    """List all template-based service instances from database."""
    instances = service_instance_service.get_all()
    return success_response(data={'instances': instances})


@services_bp.route('/api/services/instances/<service_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_service_instance(service_id):
    """Get details of a specific template-based service instance."""
    instance = service_instance_service.get(service_id)
    if not instance:
        raise NotFoundError(
            f'Service not found: {service_id}',
            resource_type='ServiceInstance',
            resource_id=service_id
        )
    return success_response(data={'instance': instance})


# ============================================================================
# Service Instance Operations - Complex routes remain in app.py
# ============================================================================
#
# The following routes require Celery task execution, template rendering,
# and device connections. They remain in app.py for now:
#
# - POST /api/services/instances/create - Creates service and deploys to device
# - POST /api/services/instances/<service_id>/healthcheck - Validates config on device
# - POST /api/services/instances/<service_id>/redeploy - Redeploys using Celery
# - POST /api/services/instances/<service_id>/delete - Removes config from device
# - POST /api/services/instances/<service_id>/check_status - Checks Celery task status
# - POST /api/services/instances/<service_id>/validate - Validates against device/backup
# - POST /api/services/instances/sync-states - Syncs states from Celery tasks
