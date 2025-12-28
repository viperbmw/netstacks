"""
Template Routes
Template management - proxied to config microservice (config:8002)
"""
from flask import Blueprint, render_template as flask_render_template
import logging

from routes.auth import login_required
from services.proxy import proxy_config_request

log = logging.getLogger(__name__)

templates_bp = Blueprint('templates', __name__)


# ============================================================================
# Template Pages
# ============================================================================

@templates_bp.route('/templates')
@login_required
def templates_page():
    """Templates management page."""
    return flask_render_template('templates.html')


# ============================================================================
# Template API - Proxied to Config Microservice
# ============================================================================

@templates_bp.route('/api/v2/templates', methods=['GET'])
@login_required
def list_templates():
    """
    List all templates.
    Proxied to config:8002/api/templates
    """
    return proxy_config_request('/api/templates')


@templates_bp.route('/api/v2/templates/<template_name>', methods=['GET'])
@login_required
def get_template(template_name):
    """
    Get template content and metadata.
    Proxied to config:8002/api/templates/{template_name}
    """
    return proxy_config_request('/api/templates/{template_name}', template_name=template_name)


@templates_bp.route('/api/v2/templates', methods=['POST'])
@login_required
def create_template():
    """
    Create a new template.
    Proxied to config:8002/api/templates
    """
    return proxy_config_request('/api/templates')


@templates_bp.route('/api/v2/templates/<template_name>', methods=['PUT'])
@login_required
def update_template(template_name):
    """
    Update an existing template.
    Proxied to config:8002/api/templates/{template_name}
    """
    return proxy_config_request('/api/templates/{template_name}', template_name=template_name)


@templates_bp.route('/api/v2/templates/<template_name>', methods=['DELETE'])
@login_required
def delete_template(template_name):
    """
    Delete a template.
    Proxied to config:8002/api/templates/{template_name}
    """
    return proxy_config_request('/api/templates/{template_name}', template_name=template_name)


@templates_bp.route('/api/v2/templates/<template_name>/render', methods=['POST'])
@login_required
def render_template(template_name):
    """
    Render a template with variables (dry run).
    Proxied to config:8002/api/templates/{template_name}/render
    """
    return proxy_config_request('/api/templates/{template_name}/render', template_name=template_name)
