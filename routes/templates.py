"""
Template Routes
Template management using local database storage
"""
from flask import Blueprint, jsonify, request, render_template

import logging

import db
from routes.auth import login_required

log = logging.getLogger(__name__)

templates_bp = Blueprint('templates', __name__)


# ============================================================================
# Template Pages
# ============================================================================

@templates_bp.route('/templates')
@login_required
def templates_page():
    """Templates management page."""
    return render_template('templates.html')


# ============================================================================
# Template API
# ============================================================================

@templates_bp.route('/api/v2/templates', methods=['GET'])
def list_templates():
    """
    List all templates

    Returns:
        {
            "success": true,
            "templates": [
                {
                    "name": "template-name",
                    "type": "deploy",
                    "description": "...",
                    "has_content": true
                }
            ]
        }
    """
    try:
        templates = db.get_all_templates()

        # Format response (don't include full content in list)
        template_list = [{
            'name': t['name'],
            'type': t.get('type', 'deploy'),
            'description': t.get('description'),
            'validation_template': t.get('validation_template'),
            'delete_template': t.get('delete_template'),
            'has_content': bool(t.get('content')),
            'created_at': t.get('created_at'),
            'updated_at': t.get('updated_at')
        } for t in templates]

        return jsonify({'success': True, 'templates': template_list})

    except Exception as e:
        log.error(f"Error listing templates: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@templates_bp.route('/api/v2/templates/<template_name>', methods=['GET'])
def get_template(template_name):
    """
    Get template content and metadata

    Returns:
        {
            "success": true,
            "content": "template content...",
            "type": "deploy",
            "description": "..."
        }
    """
    try:
        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        template = db.get_template_metadata(template_name)

        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        return jsonify({
            'success': True,
            'name': template['name'],
            'content': template.get('content', ''),
            'type': template.get('type', 'deploy'),
            'description': template.get('description'),
            'validation_template': template.get('validation_template'),
            'delete_template': template.get('delete_template'),
            'created_at': template.get('created_at'),
            'updated_at': template.get('updated_at')
        })

    except Exception as e:
        log.error(f"Error getting template {template_name}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@templates_bp.route('/api/v2/templates', methods=['POST'])
def create_template():
    """
    Create or update a template

    Request body:
    {
        "name": "template-name",
        "content": "template content as plain text",
        "type": "deploy",
        "description": "optional description",
        "validation_template": "optional validation template name",
        "delete_template": "optional delete template name"
    }
    """
    try:
        data = request.json

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        name = data.get('name')
        if not name:
            return jsonify({'success': False, 'error': 'Template name required'}), 400

        # Strip .j2 extension if present
        if name.endswith('.j2'):
            name = name[:-3]

        content = data.get('content')
        if not content:
            return jsonify({'success': False, 'error': 'Template content required'}), 400

        # Build metadata
        metadata = {
            'type': data.get('type', 'deploy'),
            'description': data.get('description'),
            'validation_template': data.get('validation_template'),
            'delete_template': data.get('delete_template')
        }

        # Save template
        db.save_template(name, content, metadata)

        log.info(f"Saved template: {name}")

        return jsonify({
            'success': True,
            'message': f'Template {name} saved',
            'name': name
        })

    except Exception as e:
        log.error(f"Error creating template: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@templates_bp.route('/api/v2/templates/<template_name>', methods=['PUT'])
def update_template(template_name):
    """Update an existing template"""
    try:
        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Check if template exists
        existing = db.get_template_metadata(template_name)
        if not existing:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        # Get content if provided, otherwise keep existing
        content = data.get('content', existing.get('content', ''))

        # Build metadata (use existing values as defaults)
        metadata = {
            'type': data.get('type', existing.get('type', 'deploy')),
            'description': data.get('description', existing.get('description')),
            'validation_template': data.get('validation_template', existing.get('validation_template')),
            'delete_template': data.get('delete_template', existing.get('delete_template'))
        }

        db.save_template(template_name, content, metadata)

        log.info(f"Updated template: {template_name}")

        return jsonify({
            'success': True,
            'message': f'Template {template_name} updated'
        })

    except Exception as e:
        log.error(f"Error updating template {template_name}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@templates_bp.route('/api/v2/templates/<template_name>', methods=['DELETE'])
def delete_template(template_name):
    """Delete a template"""
    try:
        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        if db.delete_template_metadata(template_name):
            log.info(f"Deleted template: {template_name}")
            return jsonify({'success': True, 'message': f'Template {template_name} deleted'})
        else:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

    except Exception as e:
        log.error(f"Error deleting template {template_name}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@templates_bp.route('/api/v2/templates/<template_name>/render', methods=['POST'])
def render_template(template_name):
    """
    Render a template with variables (dry run)

    Request body:
    {
        "variables": {"key": "value", ...}
    }

    Returns:
        {
            "success": true,
            "rendered": "rendered config..."
        }
    """
    try:
        from jinja2 import Template as J2Template, TemplateSyntaxError

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        # Get template content
        content = db.get_template_content(template_name)
        if not content:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        data = request.json or {}
        variables = data.get('variables', {})

        try:
            template = J2Template(content)
            rendered = template.render(**variables)

            return jsonify({
                'success': True,
                'rendered': rendered
            })

        except TemplateSyntaxError as e:
            return jsonify({
                'success': False,
                'error': f'Template syntax error: {e}'
            }), 400

    except Exception as e:
        log.error(f"Error rendering template {template_name}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
