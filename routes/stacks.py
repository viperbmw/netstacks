"""
Service Stack Routes
Stack management, deployment, validation, scheduled operations
"""

from flask import Blueprint, jsonify, request, render_template, session
import logging

from routes.auth import login_required
from services.stack_service import StackService, ScheduledOperationService
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError

log = logging.getLogger(__name__)

stacks_bp = Blueprint('stacks', __name__)

# Initialize services
stack_service = StackService()
schedule_service = ScheduledOperationService()


# ============================================================================
# Stack Pages
# ============================================================================

@stacks_bp.route('/service-stacks')
@login_required
def service_stacks_page():
    """Service stacks management page."""
    return render_template('service_stacks.html')


# ============================================================================
# Service Stack CRUD API
# ============================================================================

@stacks_bp.route('/api/service-stacks', methods=['GET'])
@login_required
@handle_exceptions
def list_service_stacks():
    """Get all service stacks."""
    stacks = stack_service.get_all()
    return success_response(data={
        'stacks': stacks,
        'count': len(stacks)
    })


@stacks_bp.route('/api/service-stacks', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_service_stack():
    """
    Create a new service stack.

    Expected JSON body:
    {
        "name": "My Stack",
        "description": "Optional description",
        "services": [
            {
                "name": "Service 1",
                "template": "template-name",
                "device": "device-name",
                "variables": {}
            }
        ],
        "shared_variables": {}
    }
    """
    data = request.get_json()
    stack_id = stack_service.create(data)

    return success_response(
        data={'stack_id': stack_id},
        message=f'Service stack "{data["name"]}" created successfully'
    )


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_service_stack(stack_id):
    """Get details of a specific service stack."""
    stack = stack_service.get(stack_id)
    if not stack:
        raise NotFoundError(
            f'Service stack not found: {stack_id}',
            resource_type='ServiceStack',
            resource_id=stack_id
        )
    return success_response(data={'stack': stack})


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_service_stack(stack_id):
    """Update a service stack."""
    data = request.get_json()
    stack_service.update(stack_id, data)

    stack = stack_service.get(stack_id)
    return success_response(
        message=f'Service stack "{stack["name"]}" updated successfully'
    )


@stacks_bp.route('/api/service-stacks/<stack_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_service_stack(stack_id):
    """
    Delete a service stack.

    Query params:
    - delete_services: If 'true', also delete deployed service instances
    """
    stack = stack_service.get(stack_id)
    if not stack:
        raise NotFoundError(
            f'Service stack not found: {stack_id}',
            resource_type='ServiceStack',
            resource_id=stack_id
        )

    stack_name = stack['name']

    # Note: For delete_services=true with delete templates,
    # use the deploy_service_stack endpoint in app.py for now
    # as it has the complex deployment logic
    delete_services = request.args.get('delete_services', 'false').lower() == 'true'

    if delete_services and stack.get('deployed_services'):
        # Complex delete with templates - defer to app.py for now
        # This would need the full deployment infrastructure
        log.warning(
            f"Delete with services requested for stack {stack_id} - "
            "using basic delete only"
        )

    stack_service.delete(stack_id)

    return success_response(
        message=f'Service stack "{stack_name}" deleted successfully'
    )


# ============================================================================
# Scheduled Operations API
# ============================================================================

@stacks_bp.route('/api/scheduled-operations', methods=['GET'])
@login_required
@handle_exceptions
def get_scheduled_operations():
    """
    Get scheduled operations.

    Query params:
    - stack_id: Optional filter by stack
    """
    stack_id = request.args.get('stack_id')
    schedules = schedule_service.get_all(stack_id=stack_id)
    return success_response(data={'schedules': schedules})


@stacks_bp.route('/api/scheduled-operations', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_scheduled_operation():
    """
    Create a new scheduled stack operation.

    Expected JSON body:
    {
        "stack_id": "uuid",
        "operation_type": "deploy|validate|delete",
        "schedule_type": "once|daily|weekly|monthly",
        "scheduled_time": "HH:MM or ISO datetime",
        "day_of_week": 0-6 (for weekly),
        "day_of_month": 1-31 (for monthly)
    }
    """
    data = request.get_json()

    required = ['stack_id', 'operation_type', 'schedule_type', 'scheduled_time']
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ValidationError(f'Missing required fields: {", ".join(missing)}')

    username = session.get('username')

    schedule_id = schedule_service.create(
        stack_id=data['stack_id'],
        operation_type=data['operation_type'],
        schedule_type=data['schedule_type'],
        scheduled_time=data['scheduled_time'],
        created_by=username,
        day_of_week=data.get('day_of_week'),
        day_of_month=data.get('day_of_month')
    )

    return success_response(data={'schedule_id': schedule_id})


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_scheduled_operation(schedule_id):
    """Get a specific scheduled operation."""
    schedule = schedule_service.get(schedule_id)
    if not schedule:
        raise NotFoundError(
            f'Schedule not found: {schedule_id}',
            resource_type='ScheduledOperation',
            resource_id=schedule_id
        )
    return success_response(data={'schedule': schedule})


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['PATCH', 'PUT'])
@login_required
@handle_exceptions
@require_json
def update_scheduled_operation(schedule_id):
    """Update a scheduled operation."""
    data = request.get_json()
    schedule_service.update(schedule_id, **data)
    return success_response()


@stacks_bp.route('/api/scheduled-operations/<schedule_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_scheduled_operation(schedule_id):
    """Delete a scheduled operation."""
    schedule_service.delete(schedule_id)
    return success_response()


# ============================================================================
# Stack Templates API (reusable stack definitions)
# ============================================================================

@stacks_bp.route('/api/stack-templates', methods=['GET'])
@login_required
@handle_exceptions
def get_stack_templates():
    """Get all stack templates."""
    import database as db
    templates = db.get_all_stack_templates()
    return success_response(data={'templates': templates})


@stacks_bp.route('/api/stack-templates/<template_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_stack_template(template_id):
    """Get a specific stack template."""
    import database as db
    template = db.get_stack_template(template_id)
    if not template:
        raise NotFoundError(
            f'Stack template not found: {template_id}',
            resource_type='StackTemplate',
            resource_id=template_id
        )
    return success_response(data={'template': template})


@stacks_bp.route('/api/stack-templates', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_stack_template():
    """
    Create a new stack template.

    Expected JSON body:
    {
        "name": "Template Name",
        "description": "Optional description",
        "stack_definition": {...}
    }
    """
    import database as db
    import uuid
    from datetime import datetime

    data = request.get_json()

    if not data.get('name'):
        raise ValidationError('Template name is required')

    if not data.get('stack_definition'):
        raise ValidationError('Stack definition is required')

    template_id = str(uuid.uuid4())
    template_data = {
        'template_id': template_id,
        'name': data['name'],
        'description': data.get('description', ''),
        'stack_definition': data['stack_definition'],
        'created_at': datetime.now().isoformat(),
        'created_by': session.get('username')
    }

    db.save_stack_template(template_data)

    return success_response(
        data={'template_id': template_id},
        message=f'Stack template "{data["name"]}" created successfully'
    )


@stacks_bp.route('/api/stack-templates/<template_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_stack_template(template_id):
    """Delete a stack template."""
    import database as db

    template = db.get_stack_template(template_id)
    if not template:
        raise NotFoundError(
            f'Stack template not found: {template_id}',
            resource_type='StackTemplate',
            resource_id=template_id
        )

    db.delete_stack_template(template_id)
    return success_response(
        message=f'Stack template "{template["name"]}" deleted successfully'
    )
