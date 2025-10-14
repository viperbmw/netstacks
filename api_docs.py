"""
NetStacks Pro API Documentation
Swagger/OpenAPI documentation for all NetStacks Pro REST APIs
"""

from flask import Blueprint
from flask_restx import Api, Resource, fields, Namespace

# Create blueprint for API docs
api_bp = Blueprint('api_docs', __name__)

# Initialize Flask-RESTX API
api = Api(
    api_bp,
    version='1.0',
    title='NetStacks Pro API',
    description='Network Automation and Configuration Management REST API',
    doc='/api-docs',
    prefix='/api'
)

# Define namespaces
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

# Devices Endpoints
@ns_devices.route('/')
class DeviceList(Resource):
    @ns_devices.doc('list_devices')
    @ns_devices.marshal_list_with(device_model)
    def post(self):
        """List all devices"""
        pass

@ns_devices.route('/<string:device_name>/connection-info')
@ns_devices.param('device_name', 'The device name')
class DeviceConnectionInfo(Resource):
    @ns_devices.doc('get_device_connection_info')
    def get(self, device_name):
        """Get device connection information"""
        pass

# Tasks Endpoints
@ns_tasks.route('/')
class TaskList(Resource):
    @ns_tasks.doc('list_tasks')
    def get(self):
        """List all task IDs"""
        pass

@ns_tasks.route('/<string:task_id>')
@ns_tasks.param('task_id', 'The task identifier')
class Task(Resource):
    @ns_tasks.doc('get_task')
    @ns_tasks.marshal_with(task_model)
    def get(self, task_id):
        """Get task details by ID"""
        pass

@ns_tasks.route('/metadata')
class TaskMetadata(Resource):
    @ns_tasks.doc('get_task_metadata')
    def get(self):
        """Get metadata for all tasks"""
        pass

# Templates Endpoints
@ns_templates.route('/')
class TemplateList(Resource):
    @ns_templates.doc('list_templates')
    @ns_templates.marshal_list_with(template_model)
    def get(self):
        """List all templates"""
        pass

    @ns_templates.doc('create_template')
    @ns_templates.expect(template_model)
    def post(self):
        """Create a new template"""
        pass

@ns_templates.route('/<string:template_id>')
@ns_templates.param('template_id', 'The template identifier')
class Template(Resource):
    @ns_templates.doc('get_template')
    @ns_templates.marshal_with(template_model)
    def get(self, template_id):
        """Get template by ID"""
        pass

    @ns_templates.doc('update_template')
    @ns_templates.expect(template_model)
    def put(self, template_id):
        """Update a template"""
        pass

    @ns_templates.doc('delete_template')
    def delete(self, template_id):
        """Delete a template"""
        pass

# Service Stacks Endpoints
@ns_stacks.route('/')
class ServiceStackList(Resource):
    @ns_stacks.doc('list_service_stacks')
    @ns_stacks.marshal_list_with(service_stack_model)
    def get(self):
        """List all service stacks"""
        pass

    @ns_stacks.doc('create_service_stack')
    @ns_stacks.expect(service_stack_model)
    def post(self):
        """Create a new service stack"""
        pass

@ns_stacks.route('/<string:stack_id>')
@ns_stacks.param('stack_id', 'The stack identifier')
class ServiceStack(Resource):
    @ns_stacks.doc('get_service_stack')
    @ns_stacks.marshal_with(service_stack_model)
    def get(self, stack_id):
        """Get service stack by ID"""
        pass

    @ns_stacks.doc('update_service_stack')
    @ns_stacks.expect(service_stack_model)
    def put(self, stack_id):
        """Update a service stack"""
        pass

    @ns_stacks.doc('delete_service_stack')
    def delete(self, stack_id):
        """Delete a service stack"""
        pass

# Scheduled Operations Endpoints
@ns_schedules.route('/')
class ScheduleList(Resource):
    @ns_schedules.doc('list_schedules')
    @ns_schedules.marshal_list_with(schedule_model)
    def get(self):
        """List all scheduled operations"""
        pass

    @ns_schedules.doc('create_schedule')
    @ns_schedules.expect(schedule_model)
    def post(self):
        """Create a new scheduled operation"""
        pass

@ns_schedules.route('/<string:schedule_id>')
@ns_schedules.param('schedule_id', 'The schedule identifier')
class Schedule(Resource):
    @ns_schedules.doc('get_schedule')
    @ns_schedules.marshal_with(schedule_model)
    def get(self, schedule_id):
        """Get schedule by ID"""
        pass

    @ns_schedules.doc('update_schedule')
    @ns_schedules.expect(schedule_model)
    def put(self, schedule_id):
        """Update a schedule"""
        pass

    @ns_schedules.doc('delete_schedule')
    def delete(self, schedule_id):
        """Delete a schedule"""
        pass

# Deploy Endpoints
@ns_deploy.route('/setconfig')
class DeploySetconfig(Resource):
    @ns_deploy.doc('deploy_setconfig')
    def post(self):
        """Deploy configuration commands to device(s)"""
        pass

@ns_deploy.route('/setconfig/dry-run')
class DeploySetconfigDryRun(Resource):
    @ns_deploy.doc('deploy_setconfig_dry_run')
    def post(self):
        """Dry-run configuration deployment (validation only)"""
        pass

@ns_deploy.route('/template')
class DeployTemplate(Resource):
    @ns_deploy.doc('deploy_template')
    def post(self):
        """Deploy using Jinja2 template"""
        pass

# Authentication Endpoints
@ns_auth.route('/login')
class Login(Resource):
    @ns_auth.doc('login')
    def post(self):
        """Authenticate user and create session"""
        pass

@ns_auth.route('/logout')
class Logout(Resource):
    @ns_auth.doc('logout')
    def post(self):
        """Logout user and destroy session"""
        pass

# Settings Endpoints
@ns_settings.route('/')
class Settings(Resource):
    @ns_settings.doc('get_settings')
    def get(self):
        """Get application settings"""
        pass

    @ns_settings.doc('update_settings')
    def post(self):
        """Update application settings"""
        pass

@ns_settings.route('/netpalm')
class NetpalmSettings(Resource):
    @ns_settings.doc('get_netpalm_settings')
    def get(self):
        """Get Netpalm API settings"""
        pass
