"""
MOP (Method of Procedures) Routes
MOP management, execution, step types
Proxied to config microservice (config:8002)
"""

from flask import Blueprint, render_template
import logging

from routes.auth import login_required
from services.proxy import proxy_config_request

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
# MOP CRUD API - Proxied to Config Microservice
# ============================================================================

@mop_bp.route('/api/mops', methods=['GET'])
@login_required
def get_mops():
    """
    Get all MOPs (workflows).
    Proxied to config:8002/api/mops
    """
    return proxy_config_request('/api/mops')


@mop_bp.route('/api/mops', methods=['POST'])
@login_required
def create_mop():
    """
    Create a new MOP (workflow).
    Proxied to config:8002/api/mops
    """
    return proxy_config_request('/api/mops')


@mop_bp.route('/api/mops/<mop_id>', methods=['GET'])
@login_required
def get_mop(mop_id):
    """
    Get a specific MOP.
    Proxied to config:8002/api/mops/{mop_id}
    """
    return proxy_config_request('/api/mops/{mop_id}', mop_id=mop_id)


@mop_bp.route('/api/mops/<mop_id>', methods=['PUT'])
@login_required
def update_mop(mop_id):
    """
    Update a MOP.
    Proxied to config:8002/api/mops/{mop_id}
    """
    return proxy_config_request('/api/mops/{mop_id}', mop_id=mop_id)


@mop_bp.route('/api/mops/<mop_id>', methods=['DELETE'])
@login_required
def delete_mop(mop_id):
    """
    Delete a MOP.
    Proxied to config:8002/api/mops/{mop_id}
    """
    return proxy_config_request('/api/mops/{mop_id}', mop_id=mop_id)


# ============================================================================
# MOP Execution API - Proxied to Config Microservice
# ============================================================================

@mop_bp.route('/api/mops/<mop_id>/executions', methods=['GET'])
@login_required
def get_mop_executions(mop_id):
    """
    Get executions for a specific MOP.
    Proxied to config:8002/api/mops/{mop_id}/executions
    """
    return proxy_config_request('/api/mops/{mop_id}/executions', mop_id=mop_id)


@mop_bp.route('/api/mop-executions/<execution_id>', methods=['GET'])
@login_required
def get_mop_execution(execution_id):
    """
    Get a specific MOP execution.
    Proxied to config:8002/api/mops/executions/{execution_id}
    """
    return proxy_config_request('/api/mops/executions/{execution_id}', execution_id=execution_id)


@mop_bp.route('/api/mop-executions/running', methods=['GET'])
@login_required
def get_running_executions():
    """
    Get all running MOP executions.
    Proxied to config:8002/api/mops/executions/running/list
    """
    return proxy_config_request('/api/mops/executions/running/list')


# Note: /api/mops/<mop_id>/execute is complex and may remain in app.py
# as it requires the MOP engine and device connection infrastructure


# ============================================================================
# Step Types API - Proxied to Config Microservice
# ============================================================================

@mop_bp.route('/api/step-types', methods=['GET'])
@login_required
def get_step_types():
    """
    Get all step types.
    Proxied to config:8002/api/step-types
    """
    return proxy_config_request('/api/step-types')


@mop_bp.route('/api/step-types/<step_type_id>', methods=['GET'])
@login_required
def get_step_type(step_type_id):
    """
    Get a specific step type.
    Proxied to config:8002/api/step-types/{step_type_id}
    """
    return proxy_config_request('/api/step-types/{step_type_id}', step_type_id=step_type_id)


@mop_bp.route('/api/step-types', methods=['POST'])
@login_required
def create_step_type():
    """
    Create a new step type.
    Proxied to config:8002/api/step-types
    """
    return proxy_config_request('/api/step-types')


@mop_bp.route('/api/step-types/<step_type_id>', methods=['PUT'])
@login_required
def update_step_type(step_type_id):
    """
    Update a step type.
    Proxied to config:8002/api/step-types/{step_type_id}
    """
    return proxy_config_request('/api/step-types/{step_type_id}', step_type_id=step_type_id)


@mop_bp.route('/api/step-types/<step_type_id>', methods=['DELETE'])
@login_required
def delete_step_type(step_type_id):
    """
    Delete a step type.
    Proxied to config:8002/api/step-types/{step_type_id}
    """
    return proxy_config_request('/api/step-types/{step_type_id}', step_type_id=step_type_id)


@mop_bp.route('/api/step-types/<step_type_id>/toggle', methods=['POST'])
@login_required
def toggle_step_type(step_type_id):
    """
    Enable or disable a step type.
    Proxied to config:8002/api/step-types/{step_type_id}/toggle
    """
    return proxy_config_request('/api/step-types/{step_type_id}/toggle', step_type_id=step_type_id)
