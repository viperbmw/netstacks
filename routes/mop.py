"""
MOP (Method of Procedures) Routes
MOP management, execution, step types
"""

from flask import Blueprint, jsonify, request, render_template, session
from sqlalchemy import text
import logging
import json
import uuid

from routes.auth import login_required
import database as db
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError, NotFoundError

log = logging.getLogger(__name__)

mop_bp = Blueprint('mop', __name__)


# ============================================================================
# MOP Pages
# ============================================================================

@mop_bp.route('/mop')
@login_required
def mop_page():
    """MOP management page."""
    return render_template('mop.html')


@mop_bp.route('/step-types')
@login_required
def step_types_page():
    """Step types management page."""
    return render_template('step_types.html')


# ============================================================================
# MOP CRUD API
# ============================================================================

@mop_bp.route('/api/mops', methods=['GET'])
@login_required
@handle_exceptions
def get_mops():
    """Get all MOPs (workflows)."""
    with db.get_db() as session_db:
        result = session_db.execute(text('''
            SELECT mop_id, name, description, devices, enabled, created_at, updated_at
            FROM mops
            ORDER BY created_at DESC
        '''))
        mops = [dict(row._mapping) for row in result.fetchall()]
        return success_response(data={'mops': mops})


@mop_bp.route('/api/mops', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_mop():
    """
    Create a new MOP (workflow).

    Expected JSON body:
    {
        "name": "MOP Name",
        "description": "Optional description",
        "yaml_content": "... MOP YAML ..."
    }
    """
    data = request.get_json()
    mop_id = str(uuid.uuid4())

    # Extract devices from YAML content
    devices = []
    yaml_content = data.get('yaml_content', '')
    if yaml_content:
        try:
            import yaml as yaml_lib
            yaml_data = yaml_lib.safe_load(yaml_content)
            devices = yaml_data.get('devices', [])
            log.info(f"Extracted {len(devices)} devices from YAML for new MOP")
        except Exception as e:
            log.warning(f"Could not parse YAML to extract devices: {e}")

    with db.get_db() as session_db:
        session_db.execute(text('''
            INSERT INTO mops (mop_id, name, description, yaml_content, devices, created_by)
            VALUES (:mop_id, :name, :description, :yaml_content, :devices, :created_by)
        '''), {
            'mop_id': mop_id,
            'name': data.get('name'),
            'description': data.get('description'),
            'yaml_content': yaml_content,
            'devices': json.dumps(devices),
            'created_by': session.get('username')
        })

    return success_response(data={'mop_id': mop_id})


@mop_bp.route('/api/mops/<mop_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_mop(mop_id):
    """Get a specific MOP."""
    with db.get_db() as session_db:
        result = session_db.execute(
            text('SELECT * FROM mops WHERE mop_id = :mop_id'),
            {'mop_id': mop_id}
        )
        mop = result.fetchone()

        if not mop:
            raise NotFoundError(
                f'MOP not found: {mop_id}',
                resource_type='MOP',
                resource_id=mop_id
            )

        return success_response(data={'mop': dict(mop._mapping)})


@mop_bp.route('/api/mops/<mop_id>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_mop(mop_id):
    """Update a MOP."""
    data = request.get_json()

    # Extract devices from YAML content
    devices = []
    yaml_content = data.get('yaml_content', '')
    if yaml_content:
        try:
            import yaml as yaml_lib
            yaml_data = yaml_lib.safe_load(yaml_content)
            devices = yaml_data.get('devices', [])
            log.info(f"Extracted {len(devices)} devices from YAML for MOP update")
        except Exception as e:
            log.warning(f"Could not parse YAML to extract devices: {e}")

    with db.get_db() as session_db:
        session_db.execute(text('''
            UPDATE mops
            SET name = :name, description = :description, yaml_content = :yaml_content,
                devices = :devices, updated_at = CURRENT_TIMESTAMP
            WHERE mop_id = :mop_id
        '''), {
            'name': data.get('name'),
            'description': data.get('description'),
            'yaml_content': yaml_content,
            'devices': json.dumps(devices),
            'mop_id': mop_id
        })

    return success_response()


@mop_bp.route('/api/mops/<mop_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_mop(mop_id):
    """Delete a MOP."""
    with db.get_db() as session_db:
        session_db.execute(
            text('DELETE FROM mops WHERE mop_id = :mop_id'),
            {'mop_id': mop_id}
        )

    return success_response()


# ============================================================================
# MOP Execution API
# ============================================================================

@mop_bp.route('/api/mops/<mop_id>/executions', methods=['GET'])
@login_required
@handle_exceptions
def get_mop_executions(mop_id):
    """Get executions for a specific MOP."""
    with db.get_db() as session_db:
        result = session_db.execute(text('''
            SELECT execution_id, mop_id, status, started_at, completed_at,
                   started_by, results
            FROM mop_executions
            WHERE mop_id = :mop_id
            ORDER BY started_at DESC
        '''), {'mop_id': mop_id})
        executions = [dict(row._mapping) for row in result.fetchall()]
        return success_response(data={'executions': executions})


@mop_bp.route('/api/mop-executions/<execution_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_mop_execution(execution_id):
    """Get a specific MOP execution."""
    with db.get_db() as session_db:
        result = session_db.execute(text('''
            SELECT e.*, m.name as mop_name
            FROM mop_executions e
            JOIN mops m ON e.mop_id = m.mop_id
            WHERE e.execution_id = :execution_id
        '''), {'execution_id': execution_id})
        execution = result.fetchone()

        if not execution:
            raise NotFoundError(
                f'Execution not found: {execution_id}',
                resource_type='MOPExecution',
                resource_id=execution_id
            )

        return success_response(data={'execution': dict(execution._mapping)})


@mop_bp.route('/api/mop-executions/running', methods=['GET'])
@login_required
@handle_exceptions
def get_running_executions():
    """Get all running MOP executions."""
    with db.get_db() as session_db:
        result = session_db.execute(text('''
            SELECT e.*, m.name as mop_name
            FROM mop_executions e
            JOIN mops m ON e.mop_id = m.mop_id
            WHERE e.status = 'running'
            ORDER BY e.started_at DESC
        '''))
        executions = [dict(row._mapping) for row in result.fetchall()]
        return success_response(data={'executions': executions})


# Note: /api/mops/<mop_id>/execute is complex and remains in app.py
# It requires the MOP engine and device connection infrastructure


# ============================================================================
# Step Types API
# ============================================================================

@mop_bp.route('/api/step-types', methods=['GET'])
@login_required
@handle_exceptions
def get_step_types():
    """Get all step types."""
    step_types = db.get_all_step_types_full()
    return success_response(data={'step_types': step_types})


@mop_bp.route('/api/step-types/<step_type_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_step_type(step_type_id):
    """Get a specific step type."""
    step_type = db.get_step_type(step_type_id)
    if not step_type:
        raise NotFoundError(
            f'Step type not found: {step_type_id}',
            resource_type='StepType',
            resource_id=step_type_id
        )
    return success_response(data={'step_type': step_type})


@mop_bp.route('/api/step-types', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_step_type():
    """
    Create a new step type.

    Expected JSON body:
    {
        "name": "Step Type Name",
        "action_type": "get_config|set_config|api_call|validate|wait|manual|deploy_stack",
        "description": "Optional description",
        "config": {}
    }
    """
    data = request.get_json()

    if not data.get('name'):
        raise ValidationError('Name is required')

    if not data.get('action_type'):
        raise ValidationError('Action type is required')

    # Validate action type
    valid_action_types = [
        'get_config', 'set_config', 'api_call', 'validate',
        'wait', 'manual', 'deploy_stack'
    ]
    if data.get('action_type') not in valid_action_types:
        raise ValidationError(
            f'Invalid action type. Must be one of: {valid_action_types}'
        )

    # For api_call types, validate URL is provided
    if data.get('action_type') == 'api_call':
        config = data.get('config', {})
        if not config.get('url'):
            raise ValidationError('URL is required for API Call step types')

    step_type_id = db.save_step_type(data)
    return success_response(data={'step_type_id': step_type_id})


@mop_bp.route('/api/step-types/<step_type_id>', methods=['PUT'])
@login_required
@handle_exceptions
@require_json
def update_step_type(step_type_id):
    """Update a step type."""
    data = request.get_json()
    data['step_type_id'] = step_type_id

    existing = db.get_step_type(step_type_id)
    if not existing:
        raise NotFoundError(
            f'Step type not found: {step_type_id}',
            resource_type='StepType',
            resource_id=step_type_id
        )

    db.save_step_type(data)
    return success_response()


@mop_bp.route('/api/step-types/<step_type_id>', methods=['DELETE'])
@login_required
@handle_exceptions
def delete_step_type(step_type_id):
    """Delete a step type."""
    existing = db.get_step_type(step_type_id)
    if not existing:
        raise NotFoundError(
            f'Step type not found: {step_type_id}',
            resource_type='StepType',
            resource_id=step_type_id
        )

    # Don't allow deleting built-in types
    if existing.get('is_builtin'):
        raise ValidationError('Cannot delete built-in step types')

    db.delete_step_type(step_type_id)
    return success_response()


@mop_bp.route('/api/step-types/<step_type_id>/toggle', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def toggle_step_type(step_type_id):
    """Enable or disable a step type."""
    data = request.get_json()
    enabled = data.get('enabled', True)

    existing = db.get_step_type(step_type_id)
    if not existing:
        raise NotFoundError(
            f'Step type not found: {step_type_id}',
            resource_type='StepType',
            resource_id=step_type_id
        )

    db.toggle_step_type(step_type_id, enabled)
    return success_response()
