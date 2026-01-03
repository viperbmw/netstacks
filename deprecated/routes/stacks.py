"""
Service Stack Routes
Stack management, deployment, validation, scheduled operations
Proxied to config microservice (config:8002)
"""

from flask import Blueprint, render_template
import logging

from routes.auth import login_required
from services.proxy import proxy_config_request

log = logging.getLogger(__name__)

stacks_bp = Blueprint('stacks', __name__)


# ============================================================================
# Stack Pages
# ============================================================================

@stacks_bp.route('/service-stacks')
@login_required
def service_stacks_page():
    """Service stacks management page."""
    return render_template('service-stacks.html')


# ============================================================================
# Service Stack CRUD API - Proxied to Config Microservice
# ============================================================================

@stacks_bp.route('/api/service-stacks', methods=['GET'])
@login_required
def list_service_stacks():
    """
    Get all service stacks.
    Proxied to config:8002/api/service-stacks
    """
    return proxy_config_request('/api/service-stacks')


@stacks_bp.route('/api/service-stacks', methods=['POST'])
@login_required
def create_service_stack():
    """
    Create a new service stack.
    Proxied to config:8002/api/service-stacks
    """
    return proxy_config_request('/api/service-stacks')


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['GET'])
@login_required
def get_service_stack(stack_id):
    """
    Get details of a specific service stack.
    Proxied to config:8002/api/service-stacks/{stack_id}
    """
    return proxy_config_request('/api/service-stacks/{stack_id}', stack_id=stack_id)


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['PUT'])
@login_required
def update_service_stack(stack_id):
    """
    Update a service stack.
    Proxied to config:8002/api/service-stacks/{stack_id}
    """
    return proxy_config_request('/api/service-stacks/{stack_id}', stack_id=stack_id)


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['DELETE'])
@login_required
def delete_service_stack(stack_id):
    """
    Delete a service stack.
    Proxied to config:8002/api/service-stacks/{stack_id}
    """
    return proxy_config_request('/api/service-stacks/{stack_id}', stack_id=stack_id)


# ============================================================================
# Scheduled Operations API - Proxied to Config Microservice
# ============================================================================

@stacks_bp.route('/api/scheduled-operations', methods=['GET'])
@login_required
def get_scheduled_operations():
    """
    Get scheduled operations.
    Proxied to config:8002/api/scheduled-operations
    """
    return proxy_config_request('/api/scheduled-operations')


@stacks_bp.route('/api/scheduled-operations', methods=['POST'])
@login_required
def create_scheduled_operation():
    """
    Create a new scheduled stack operation.
    Proxied to config:8002/api/scheduled-operations
    """
    return proxy_config_request('/api/scheduled-operations')


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['GET'])
@login_required
def get_scheduled_operation(schedule_id):
    """
    Get a specific scheduled operation.
    Proxied to config:8002/api/scheduled-operations/{schedule_id}
    """
    return proxy_config_request('/api/scheduled-operations/{schedule_id}', schedule_id=schedule_id)


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['PATCH', 'PUT'])
@login_required
def update_scheduled_operation(schedule_id):
    """
    Update a scheduled operation.
    Proxied to config:8002/api/scheduled-operations/{schedule_id}
    """
    return proxy_config_request('/api/scheduled-operations/{schedule_id}', schedule_id=schedule_id)


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['DELETE'])
@login_required
def delete_scheduled_operation(schedule_id):
    """
    Delete a scheduled operation.
    Proxied to config:8002/api/scheduled-operations/{schedule_id}
    """
    return proxy_config_request('/api/scheduled-operations/{schedule_id}', schedule_id=schedule_id)


# ============================================================================
# Stack Templates API - Proxied to Config Microservice
# These are reusable stack definitions, different from config templates
# ============================================================================

@stacks_bp.route('/api/stack-templates', methods=['GET'])
@login_required
def get_stack_templates():
    """
    Get all stack templates.
    Proxied to config:8002/api/stack-templates
    """
    return proxy_config_request('/api/stack-templates')


@stacks_bp.route('/api/stack-templates/<template_id>', methods=['GET'])
@login_required
def get_stack_template(template_id):
    """
    Get a specific stack template.
    Proxied to config:8002/api/stack-templates/{template_id}
    """
    return proxy_config_request('/api/stack-templates/{template_id}', template_id=template_id)


@stacks_bp.route('/api/stack-templates', methods=['POST'])
@login_required
def create_stack_template():
    """
    Create a new stack template.
    Proxied to config:8002/api/stack-templates
    """
    return proxy_config_request('/api/stack-templates')


@stacks_bp.route('/api/stack-templates/<template_id>', methods=['PUT'])
@login_required
def update_stack_template(template_id):
    """
    Update a stack template.
    Proxied to config:8002/api/stack-templates/{template_id}
    """
    return proxy_config_request('/api/stack-templates/{template_id}', template_id=template_id)


@stacks_bp.route('/api/stack-templates/<template_id>', methods=['DELETE'])
@login_required
def delete_stack_template(template_id):
    """
    Delete a stack template.
    Proxied to config:8002/api/stack-templates/{template_id}
    """
    return proxy_config_request('/api/stack-templates/{template_id}', template_id=template_id)
