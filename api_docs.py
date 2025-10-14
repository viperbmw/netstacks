"""
NetStacks Pro API Documentation
Swagger/OpenAPI documentation for all NetStacks Pro REST APIs
"""

from flask import Blueprint
from flask_restx import Api, Resource, fields, Namespace

# Create blueprint for API docs
api_bp = Blueprint('api_docs', __name__)

# Initialize Flask-RESTX API
# Note: add_api_spec_resource=False prevents Flask-RESTX from creating actual API endpoints
# We only want the Swagger documentation UI, not duplicate API routes
api = Api(
    api_bp,
    version='1.0',
    title='NetStacks Pro API',
    description='Network Automation and Configuration Management REST API',
    doc='/api-docs',
    add_api_spec_resource=False
)

# Define namespaces for documentation only
# NOTE: These namespaces are for documentation purposes only
# They do NOT create actual API endpoints (add_api_spec_resource=False)
# The actual API endpoints are defined in app.py
ns_devices = api.namespace('devices', description='Device management operations')
ns_tasks = api.namespace('tasks', description='Task and job monitoring')
ns_templates = api.namespace('templates', description='Configuration templates')
ns_stacks = api.namespace('stacks', description='Service stack operations')
ns_schedules = api.namespace('schedules', description='Scheduled operations')
ns_deploy = api.namespace('deploy', description='Configuration deployment')
ns_auth = api.namespace('auth', description='Authentication')
ns_settings = api.namespace('settings', description='Settings management')

# Define models
device_model = api.model('Device', {
    'name': fields.String(required=True, description='Device name'),
    'ip_address': fields.String(description='IP address'),
    'device_type': fields.String(description='Device type (e.g., cisco_ios)'),
    'manufacturer': fields.String(description='Manufacturer'),
    'platform': fields.String(description='Platform'),
    'site': fields.String(description='Site location'),
    'status': fields.String(description='Device status'),
})

task_model = api.model('Task', {
    'task_id': fields.String(description='Unique task identifier'),
    'task_status': fields.String(description='Task status (queued, running, finished, failed)'),
    'created_on': fields.DateTime(description='Task creation timestamp'),
    'task_result': fields.Raw(description='Task execution result'),
    'task_errors': fields.Raw(description='Task errors if any'),
})

template_model = api.model('Template', {
    'template_id': fields.String(description='Unique template identifier'),
    'template_name': fields.String(required=True, description='Template name'),
    'template_type': fields.String(required=True, description='Template type (deploy, delete, validate)'),
    'template_content': fields.String(required=True, description='Jinja2 template content'),
    'variables': fields.Raw(description='Template variables schema'),
    'created_at': fields.DateTime(description='Creation timestamp'),
})

schedule_model = api.model('Schedule', {
    'schedule_id': fields.String(description='Unique schedule identifier'),
    'operation_type': fields.String(required=True, description='Operation type (deploy, validate, delete, config_deploy)'),
    'schedule_type': fields.String(required=True, description='Schedule type (once, daily, weekly, monthly)'),
    'scheduled_time': fields.String(required=True, description='Schedule time (ISO 8601 format)'),
    'enabled': fields.Boolean(description='Schedule enabled status'),
    'next_run': fields.DateTime(description='Next execution time'),
    'last_run': fields.DateTime(description='Last execution time'),
    'run_count': fields.Integer(description='Number of times executed'),
})

service_stack_model = api.model('ServiceStack', {
    'stack_id': fields.String(description='Unique stack identifier'),
    'stack_name': fields.String(required=True, description='Stack name'),
    'description': fields.String(description='Stack description'),
    'deploy_template_id': fields.String(description='Deploy template ID'),
    'delete_template_id': fields.String(description='Delete template ID'),
    'validation_template_id': fields.String(description='Validation template ID'),
    'target_devices': fields.List(fields.String, description='Target device list'),
    'service_variables': fields.Raw(description='Service-specific variables'),
    'created_at': fields.DateTime(description='Creation timestamp'),
})

# NOTE: Resource classes have been removed to prevent route conflicts
# Flask-RESTX creates actual routes when Resource classes are defined
# Since we only want documentation (Swagger UI), not duplicate endpoints,
# we've removed all Resource class definitions.
#
# The actual API endpoints are implemented in app.py
# This file only provides the Swagger UI for documentation purposes
