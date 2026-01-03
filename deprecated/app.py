"""
NetStacks - Web-based Service Stack Management for Network Automation
Uses Celery for device operations
"""
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from functools import wraps
import requests
import os
import logging
import json
import uuid
import time
import hashlib
import secrets
import bcrypt
from datetime import datetime
from netbox_client import NetboxClient
from jinja2 import Template, TemplateSyntaxError
from sqlalchemy import text
import db
import auth_ldap
import auth_oidc
from services.celery_device_service import celery_device_service

app = Flask(__name__)

# Initialize Flask-SocketIO for real-time WebSocket communication
from flask_socketio import SocketIO

def _get_socketio_cors_allowed_origins():
    """Return SocketIO CORS allowed origins.

    - If SOCKETIO_CORS_ALLOWED_ORIGINS is unset: keep legacy behaviour ("*").
    - If set: parse as comma-separated list.
    """
    raw = os.environ.get('SOCKETIO_CORS_ALLOWED_ORIGINS', '').strip()
    if not raw:
        return "*"
    origins = [o.strip() for o in raw.split(',') if o.strip()]
    return origins or "*"

socketio = SocketIO(app, cors_allowed_origins=_get_socketio_cors_allowed_origins())

# Secret key for session management - MUST be set in production
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    import warnings
    warnings.warn(
        "SECRET_KEY environment variable not set! Using an auto-generated key. "
        "Sessions will be invalidated on restart. Set SECRET_KEY in production.",
        RuntimeWarning
    )
    # Generate a random key for development - sessions won't persist across restarts
    _secret_key = secrets.token_hex(32)
app.config['SECRET_KEY'] = _secret_key

# Setup logging first (needed before blueprint registration)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Register all route blueprints
from routes import register_blueprints
register_blueprints(app)
log.info("Registered all route blueprints")

# Initialize WebSocket handlers for agent chat
try:
    from routes.agent_websocket import init_socketio
    init_socketio(socketio)
    log.info("Initialized agent WebSocket handlers")
except Exception as e:
    log.warning(f"Could not initialize WebSocket handlers: {e}")

# Register API documentation blueprint (legacy)
try:
    from api_docs import api_bp as api_docs_bp
    app.register_blueprint(api_docs_bp)
except Exception as e:
    log.warning(f"Could not register API docs: {e}")

# Configuration
NETBOX_URL = os.environ.get('NETBOX_URL', 'https://netbox.example.com')
NETBOX_TOKEN = os.environ.get('NETBOX_TOKEN', '')
VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() == 'true'
TASK_HISTORY_FILE = os.environ.get('TASK_HISTORY_FILE', '/tmp/netstacks_tasks.json')

# Note: Netbox client is now initialized dynamically via get_netbox_client()
# This allows settings to be changed via the GUI without restarting

# Initialize database (SQLite or PostgreSQL based on USE_POSTGRES env var)
db.init_db()
log.info("Database initialized")

# Load settings from database on startup
try:
    stored_settings = db.get_all_settings()
    if stored_settings:
        log.info("Loaded settings from database")
    else:
        log.warning("No settings found in database. Please configure via /settings")
except Exception as e:
    log.warning(f"Could not load settings from database: {e}")


# Authentication functions
def hash_password(password):
    """Hash a password using bcrypt with automatic salt generation"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(stored_hash, provided_password):
    """Verify a password against a stored bcrypt hash

    Also handles legacy SHA256 hashes for backward compatibility during migration.
    """
    password_bytes = provided_password.encode('utf-8')
    stored_hash_bytes = stored_hash.encode('utf-8')

    # Check if it's a bcrypt hash (starts with $2b$ or $2a$)
    if stored_hash.startswith('$2'):
        try:
            return bcrypt.checkpw(password_bytes, stored_hash_bytes)
        except ValueError:
            return False
    else:
        # Legacy SHA256 hash - verify and upgrade on next password change
        legacy_hash = hashlib.sha256(password_bytes).hexdigest()
        return stored_hash == legacy_hash


def get_user(username):
    """Get user from database"""
    return db.get_user(username)


def create_default_user():
    """Create default admin user if no users exist"""
    try:
        # Check if admin user exists
        if not get_user('admin'):
            db.create_user('admin', hash_password('admin'))
            log.info("Created default admin user (username: admin, password: admin)")
    except Exception as e:
        log.error(f"Error creating default user: {e}")


# Import login_required from routes.auth to use JWT-only authentication
from routes.auth import login_required, get_current_user


# Initialize default user on startup
create_default_user()


# Step types routes migrated to routes/mop.py
# Menu items now hardcoded in base.html (removed database-driven menu)

# Device cache is now managed by services/device_service.py
# Import the device service functions for cache operations
from services.device_service import get_devices as device_service_get_devices
from services.device_service import get_cached_devices as device_service_get_cached
from services.device_service import clear_device_cache as device_service_clear_cache

# Local cache for network connections and other transient data
# TODO: Migrate to Redis for multi-process consistency
device_cache = {
    'ttl': 300  # 5 minute cache TTL
}


# Task history management - uses database instead of JSON file
def save_task_id(task_id, device_name=None):
    """Save a task ID to the database

    Args:
        task_id: The Celery task ID
        device_name: Descriptive name for the job. For standardized format use:
                    stack:{OPERATION}:{StackName}:{ServiceName}:{DeviceName}:{JobID}
    """
    try:
        db.save_task_history(task_id, device_name)
    except Exception as e:
        log.error(f"Error saving task ID to database: {e}")


def get_task_history():
    """Get all stored task IDs from database"""
    try:
        return db.get_task_history_list(limit=500)
    except Exception as e:
        log.error(f"Error reading task history from database: {e}")
        return []


# ============================================================================
# Template Metadata Storage Functions
# ============================================================================

def save_template_metadata(template_name, metadata):
    """Save template metadata to database"""
    db.save_template_metadata(template_name, metadata)
    log.info(f"Saved template metadata: {template_name}")
    return True


def get_template_metadata(template_name):
    """Get template metadata from database"""
    return db.get_template_metadata(template_name)


def get_all_template_metadata():
    """Get all template metadata from database"""
    return db.get_all_template_metadata()


# ============================================================================
# Settings Storage Functions
# ============================================================================

def save_settings(settings):
    """Save application settings to database"""
    for key, value in settings.items():
        # Convert boolean to string for storage
        if isinstance(value, bool):
            value = str(value).lower()
        # Convert lists/dicts to JSON for storage
        elif isinstance(value, (list, dict)):
            value = json.dumps(value)
        else:
            value = str(value)
        db.set_setting(key, value)
    log.info(f"Saved settings to database")
    return True


def get_settings():
    """Get application settings from database"""
    # Default empty settings (must be configured via GUI)
    settings = {
        'netbox_url': '',
        'netbox_token': '',
        'verify_ssl': False,
        'netbox_filters': [],
        'cache_ttl': 300
    }

    # Load from database
    try:
        stored_settings = db.get_all_settings()
        if stored_settings:
            # Parse JSON fields back to lists/dicts
            for key, value in stored_settings.items():
                if key in ['netbox_filters'] and isinstance(value, str):
                    try:
                        stored_settings[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        stored_settings[key] = []
                elif key == 'cache_ttl' and isinstance(value, str):
                    try:
                        stored_settings[key] = int(value)
                    except (ValueError, TypeError):
                        stored_settings[key] = 300

            settings.update(stored_settings)
            log.info(f"Loaded settings from database")
        else:
            log.warning("No settings found in database. Please configure via /settings")
    except Exception as e:
        log.warning(f"Could not load settings from database: {e}")

    return settings


def get_netbox_client():
    """Get a Netbox client with current settings"""
    settings = get_settings()
    return NetboxClient(
        settings['netbox_url'],
        settings['netbox_token'],
        verify_ssl=settings.get('verify_ssl', False)
    )


# ============================================================================
# Service Storage Functions
# ============================================================================

def save_service_instance(service_data):
    """Save a service instance to database"""
    service_id = service_data.get('service_id', str(uuid.uuid4()))
    service_data['service_id'] = service_id
    service_data['updated_at'] = datetime.now().isoformat()

    if 'created_at' not in service_data:
        service_data['created_at'] = service_data['updated_at']

    db.save_service_instance(service_data)
    log.info(f"Saved service instance: {service_id}")
    return service_id


def get_service_instance(service_id):
    """Get a service instance from database"""
    return db.get_service_instance(service_id)


def get_all_service_instances():
    """Get all service instances from database"""
    instances = db.get_all_service_instances()
    # Sort by created_at (newest first)
    instances.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return instances


def delete_service_instance(service_id, run_delete_template=False, credential_override=None):
    """
    Delete a service instance from database and optionally run delete template

    Args:
        service_id: The service instance ID
        run_delete_template: If True, deploy the delete template to remove device config
        credential_override: Optional dict with username/password

    Returns:
        Result of deletion, or dict with task_id if delete template was deployed
    """
    if run_delete_template:
        # Get the service instance details first
        service = get_service_instance(service_id)
        if not service:
            log.warning(f"Service instance {service_id} not found")
            return {'success': False, 'error': 'Service not found'}

        delete_template = service.get('delete_template')
        device = service.get('device')
        variables = service.get('variables', {})

        log.info(f"Service {service_id}: delete_template='{delete_template}', device='{device}', variables={variables}")

        if delete_template and device:
            log.info(f"Running delete template '{delete_template}' on device '{device}' for service {service_id}")

            try:
                # Get device connection info
                from services.device_service import get_device_connection_info as get_conn_info
                device_info = get_conn_info(device, credential_override)
                if not device_info:
                    log.error(f"Could not get connection info for device {device}")
                    db.delete_service_instance(service_id)
                    return {'success': True, 'warning': 'Deleted from database but could not connect to device'}

                # Strip .j2 extension if present
                template_name_clean = delete_template[:-3] if delete_template.endswith('.j2') else delete_template

                # Render template locally
                rendered_config = render_j2_template(template_name_clean, variables)
                if not rendered_config:
                    log.error(f"Failed to render delete template: {template_name_clean}")
                    db.delete_service_instance(service_id)
                    return {'success': True, 'warning': 'Deleted from database but failed to render delete template'}

                # Deploy via Celery
                task_id = celery_device_service.set_config(
                    device_info['connection_args'],
                    rendered_config
                )

                log.info(f"Delete template deployed for service {service_id}, task_id: {task_id}")

                # Save task ID to monitor
                if task_id:
                    stack_name = "N/A"
                    if service.get('stack_id'):
                        stack = get_service_stack(service['stack_id'])
                        if stack:
                            stack_name = stack.get('name', 'N/A')

                    service_name = service.get('name', 'N/A')
                    if ' (' in service_name:
                        service_name = service_name.split(' (')[0]

                    job_name = f"stack:DELETE:{stack_name}:{service_name}:{device}:{task_id}"
                    save_task_id(task_id, device_name=job_name)

                db.delete_service_instance(service_id)
                return {'success': True, 'task_id': task_id, 'message': 'Delete template deployed successfully'}

            except Exception as e:
                log.error(f"Error deploying delete template for service {service_id}: {e}")
                db.delete_service_instance(service_id)
                return {'success': True, 'warning': f'Deleted from database but failed to deploy delete template: {str(e)}'}
        else:
            log.warning(f"No delete template or device for service {service_id}")

    # Standard database-only deletion
    result = db.delete_service_instance(service_id)
    log.info(f"Deleted service instance: {service_id}")
    return result


def update_service_state(service_id, state):
    """Update the state of a service instance"""
    service = get_service_instance(service_id)
    if service:
        service['state'] = state
        service['updated_at'] = datetime.now().isoformat()
        save_service_instance(service)
        return True
    return False


# Service Stack storage functions
def save_service_stack(stack_data):
    """Save a service stack to database"""
    stack_id = stack_data.get('stack_id', str(uuid.uuid4()))
    stack_data['stack_id'] = stack_id
    stack_data['updated_at'] = datetime.now().isoformat()

    if 'created_at' not in stack_data:
        stack_data['created_at'] = stack_data['updated_at']

    db.save_service_stack(stack_data)
    log.info(f"Saved service stack: {stack_id}")
    return stack_id


def get_service_stack(stack_id):
    """Get a service stack from database"""
    return db.get_service_stack(stack_id)


def get_all_service_stacks():
    """Get all service stacks from database"""
    stacks = db.get_all_service_stacks()
    stacks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return stacks


def delete_service_stack(stack_id):
    """Delete a service stack from database"""
    result = db.delete_service_stack(stack_id)
    log.info(f"Deleted service stack: {stack_id}")
    return result


def render_j2_template(template_name, variables):
    """Render a Jinja2 template from local database"""
    try:
        from jinja2 import Environment, BaseLoader

        # Strip .j2 extension if present
        template_lookup = template_name[:-3] if template_name.endswith('.j2') else template_name

        # Get template content from local database
        template_content = db.get_template_content(template_lookup)
        if not template_content:
            log.error(f"Template not found: {template_lookup}")
            return None

        # Render the template
        env = Environment(loader=BaseLoader(), trim_blocks=True, lstrip_blocks=True)
        template = env.from_string(template_content)
        rendered = template.render(**variables)

        return rendered

    except Exception as e:
        log.error(f"Error rendering template {template_name}: {e}", exc_info=True)
        return None




# Import the proper get_device_connection_info from device_service
from services.device_service import get_device_connection_info


def authenticate_user(username, password):
    """
    Authenticate user using all enabled authentication methods

    Args:
        username: Username to authenticate
        password: Password to verify

    Returns:
        Tuple of (success: bool, user_info: dict or None, auth_method: str)
    """
    # Get all enabled auth methods ordered by priority
    auth_configs = db.get_enabled_auth_configs()

    # Add local auth with its configured priority
    local_priority = int(db.get_setting('local_auth_priority', '999'))
    auth_configs.append({
        'auth_type': 'local',
        'priority': local_priority,
        'config_data': {}
    })

    # Sort all methods by priority
    auth_configs.sort(key=lambda x: x.get('priority', 999))

    log.info(f"Authentication order for {username}: {[(c['auth_type'], c['priority']) for c in auth_configs]}")

    for auth_config in auth_configs:
        auth_type = auth_config['auth_type']
        config_data = auth_config.get('config_data', {})

        try:
            log.info(f"Trying {auth_type} authentication for {username}")

            if auth_type == 'local':
                # Local database authentication
                user = get_user(username)
                if user and verify_password(user['password_hash'], password):
                    log.info(f"User {username} authenticated via local auth")
                    return True, {'username': username, 'auth_method': 'local'}, 'local'
                else:
                    log.info(f"Local auth failed for {username}")

            elif auth_type == 'ldap':
                # LDAP authentication
                success, user_info = auth_ldap.authenticate_ldap(username, password, config_data)
                if success:
                    log.info(f"User {username} authenticated via LDAP")
                    # Create/update local user record for LDAP user
                    if not get_user(username):
                        # Create placeholder user for LDAP
                        db.create_user(username, hash_password(secrets.token_urlsafe(32)), 'ldap')
                    return True, user_info, 'ldap'

            elif auth_type == 'oidc':
                # OIDC requires redirect flow, not direct password auth
                # This is handled separately in the OIDC routes
                pass

        except Exception as e:
            log.error(f"Error during {auth_type} authentication for user {username}: {e}")
            continue

    # All authentication methods failed
    log.warning(f"Authentication failed for user {username}")
    return False, None, None


# Authentication routes migrated to routes/auth.py





# Page routes migrated to routes/pages.py, routes/devices.py, routes/templates.py
# Settings routes migrated to routes/settings.py
# Menu items and API resources migrated to routes/api.py

@app.route('/api/platform/stats', methods=['GET'])
@login_required
def get_platform_statistics():
    """Get aggregated platform statistics for agent self-awareness."""
    from services.platform_stats_service import get_platform_stats
    return jsonify(get_platform_stats())


@app.route('/api/proxy-api-call', methods=['POST'])
@login_required
def proxy_api_call():
    """Proxy API calls to bypass CORS restrictions"""
    try:
        import requests
        import base64
        from urllib.parse import urlparse

        data = request.json
        resource_id = data.get('resource_id')
        endpoint = data.get('endpoint')
        method = data.get('method', 'GET')
        variables = data.get('variables', {})  # For variable substitution

        if not resource_id or not endpoint:
            return jsonify({'success': False, 'error': 'resource_id and endpoint are required'}), 400

        # Get the resource
        resource = db.get_api_resource(resource_id)
        if not resource:
            return jsonify({'success': False, 'error': 'Resource not found'}), 404

        # Substitute variables in endpoint (e.g., {{device}}, {{site_id}})
        substituted_endpoint = endpoint
        substituted_body = data.get('body')

        if variables:
            import re
            for var_name, var_value in variables.items():
                # Replace {{variable_name}} with actual value (double braces)
                pattern = f'{{{{{var_name}}}}}'  # {{var_name}}
                substituted_endpoint = substituted_endpoint.replace(pattern, str(var_value))

                # Also substitute in body if present
                if substituted_body:
                    substituted_body = substituted_body.replace(pattern, str(var_value))

            # Log any remaining unsubstituted variables for debugging
            remaining_vars = re.findall(r'\{\{(\w+)\}\}', substituted_endpoint)
            if remaining_vars:
                log.warning(f"Unsubstituted variables in endpoint: {remaining_vars}")

            if substituted_body:
                remaining_body_vars = re.findall(r'\{\{(\w+)\}\}', substituted_body)
                if remaining_body_vars:
                    log.warning(f"Unsubstituted variables in body: {remaining_body_vars}")

        # Build full URL
        base_url = resource['base_url'].rstrip('/')
        clean_endpoint = substituted_endpoint if substituted_endpoint.startswith('/') else '/' + substituted_endpoint
        url = base_url + clean_endpoint

        # Optional outbound allowlist (disabled by default)
        # If PROXY_API_ALLOWED_HOSTS is set, only allow proxying to these hostnames.
        allowed_hosts_raw = os.environ.get('PROXY_API_ALLOWED_HOSTS', '').strip()
        if allowed_hosts_raw:
            allowed_hosts = {h.strip().lower() for h in allowed_hosts_raw.split(',') if h.strip()}
            parsed = urlparse(url)
            host = (parsed.hostname or '').lower()
            if not host or host not in allowed_hosts:
                return jsonify({
                    'success': False,
                    'error': f"Outbound proxy blocked by allowlist (host='{host}')"
                }), 403

        # Build headers based on auth type
        headers = {}
        auth_type = resource.get('auth_type', 'none')

        if auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {resource['auth_token']}"
        elif auth_type == 'api_key':
            headers['X-API-Key'] = resource['auth_token']
        elif auth_type == 'basic':
            credentials = f"{resource['auth_username']}:{resource['auth_password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers['Authorization'] = f"Basic {encoded}"
        elif auth_type == 'custom' and resource.get('custom_headers'):
            headers = resource['custom_headers']

        # Get request body if provided (for POST/PUT) - use substituted version
        request_data = None
        if substituted_body:
            try:
                # Parse JSON body (variables already substituted)
                request_data = json.loads(substituted_body) if isinstance(substituted_body, str) else substituted_body
                headers['Content-Type'] = 'application/json'
            except json.JSONDecodeError as e:
                return jsonify({'success': False, 'error': f'Invalid JSON body: {str(e)}'}), 400

        # Make the request
        log.info(f"Proxying API call: {method} {url}")
        if request_data:
            log.info(f"Request body: {json.dumps(request_data)}")

        # Use verify_ssl setting from resource (defaults to True for security)
        verify_ssl = resource.get('verify_ssl', True)

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=request_data if request_data else None,
            timeout=30,
            verify=verify_ssl
        )

        # Return the response
        return jsonify({
            'success': True,
            'status': response.status_code,
            'statusText': response.reason,
            'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        })

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Request timeout (30s)'}), 504
    except requests.exceptions.ConnectionError as e:
        return jsonify({'success': False, 'error': f'Connection error: {str(e)}'}), 503
    except Exception as e:
        log.error(f"Error proxying API call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Device routes migrated to routes/devices.py
# Config backup CRUD routes migrated to routes/api.py

### Config Backup Execution Endpoints (Celery-dependent, stay in app.py) ###
# Config backup CRUD routes (GET, DELETE, latest) are in routes/api.py

@app.route('/api/config-backups/run-single', methods=['POST'])
@login_required
def run_single_device_backup():
    """Run a backup for a single device"""
    try:
        data = request.json
        device_name = data.get('device_name')

        if not device_name:
            return jsonify({'success': False, 'error': 'device_name is required'}), 400

        # Get device connection info
        from services.device_service import get_device_connection_info as get_conn_info
        credential_override = None
        if data.get('username') and data.get('password'):
            credential_override = {'username': data['username'], 'password': data['password']}

        device_info = get_conn_info(device_name, credential_override)
        if not device_info:
            return jsonify({'success': False, 'error': f'Device {device_name} not found'}), 404

        # Get Juniper format preference - from request or fallback to schedule settings
        if 'juniper_set_format' in data:
            juniper_set_format = data.get('juniper_set_format', True)
        else:
            schedule = db.get_backup_schedule()
            juniper_set_format = schedule.get('juniper_set_format', True) if schedule else True

        # Submit backup task
        task_id = celery_device_service.execute_backup(
            connection_args=device_info['connection_args'],
            device_name=device_name,
            device_platform=device_info['device_info'].get('platform'),
            juniper_set_format=juniper_set_format,
            snapshot_id=None,  # Single backup, not part of snapshot
            created_by=get_current_user()
        )

        if task_id:
            # Save task ID for tracking
            save_task_id(task_id, device_name=f"backup:{device_name}:{task_id}")

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Backup task submitted for {device_name}'
        })
    except Exception as e:
        log.error(f"Error running single device backup: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/run-all', methods=['POST'])
@login_required
def run_all_device_backups():
    """Run backups for all devices, creating a snapshot"""
    try:
        data = request.json or {}

        # Get all devices - try cache first, then fetch fresh if empty
        devices = device_service_get_cached()

        if not devices:
            # Cache is empty - fetch fresh devices (includes manual + Netbox)
            log.info("Device cache empty, fetching fresh device list for backup")
            from services.device_service import get_devices
            result = get_devices(force_refresh=True)
            devices = result.get('devices', [])

        if not devices:
            log.warning("No devices found for backup.")
            return jsonify({
                'success': False,
                'error': 'No devices found. Add manual devices or configure NetBox.'
            }), 400

        log.info(f"Found {len(devices)} devices for backup")

        # Get backup schedule settings
        schedule = db.get_backup_schedule()
        juniper_set_format = schedule.get('juniper_set_format', True) if schedule else True
        exclude_patterns = schedule.get('exclude_patterns', []) if schedule else []

        # Filter out excluded devices
        if exclude_patterns:
            import re
            filtered_devices = []
            for device in devices:
                device_name = device.get('name', '')
                excluded = False
                for pattern in exclude_patterns:
                    if re.search(pattern, device_name, re.IGNORECASE):
                        excluded = True
                        break
                if not excluded:
                    filtered_devices.append(device)
            devices = filtered_devices

        # Create a snapshot to group all backups
        snapshot_name = data.get('name') or f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        snapshot_id = db.create_config_snapshot({
            'name': snapshot_name,
            'description': data.get('description'),
            'snapshot_type': data.get('snapshot_type', 'manual'),
            'total_devices': len(devices),
            'created_by': get_current_user()
        })
        log.info(f"Created snapshot {snapshot_id} for {len(devices)} devices")

        # Submit backup tasks
        from services.device_service import get_device_connection_info as get_conn_info
        submitted = []
        failed = []

        created_by = get_current_user()
        for device in devices:
            device_name = device.get('name')
            try:
                device_info = get_conn_info(device_name)
                if device_info:
                    task_id = celery_device_service.execute_backup(
                        connection_args=device_info['connection_args'],
                        device_name=device_name,
                        device_platform=device_info['device_info'].get('platform'),
                        juniper_set_format=juniper_set_format,
                        snapshot_id=snapshot_id,
                        created_by=created_by
                    )
                    submitted.append({'device': device_name, 'task_id': task_id, 'snapshot_id': snapshot_id})
                    save_task_id(task_id, device_name=f"snapshot:{snapshot_id}:backup:{device_name}:{task_id}")
                else:
                    failed.append({'device': device_name, 'error': 'Could not get connection info'})
                    db.increment_snapshot_counts(snapshot_id, success=False)
            except Exception as e:
                failed.append({'device': device_name, 'error': str(e)})
                db.increment_snapshot_counts(snapshot_id, success=False)

        # Update schedule last run time
        if schedule:
            from datetime import timedelta
            last_run = datetime.utcnow()
            interval_hours = schedule.get('interval_hours', 24)
            next_run = last_run + timedelta(hours=interval_hours)
            db.update_backup_schedule_run_times(last_run, next_run)

        return jsonify({
            'success': True,
            'snapshot_id': snapshot_id,
            'submitted': len(submitted),
            'failed': len(failed),
            'tasks': submitted,
            'errors': failed
        })
    except Exception as e:
        log.error(f"Error running all device backups: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/run-selected', methods=['POST'])
@login_required
def run_selected_device_backups():
    """Run backups for selected devices"""
    try:
        data = request.json or {}
        device_names = data.get('device_names', [])

        if not device_names:
            return jsonify({'success': False, 'error': 'No devices specified'}), 400

        log.info(f"Running backup for {len(device_names)} selected devices")

        # Get backup settings
        schedule = db.get_backup_schedule()
        juniper_set_format = data.get('juniper_set_format', schedule.get('juniper_set_format', True) if schedule else True)

        # Submit backup tasks
        from services.device_service import get_device_connection_info as get_conn_info
        submitted = []
        failed = []
        created_by = get_current_user()

        for device_name in device_names:
            try:
                device_info = get_conn_info(device_name)
                if device_info:
                    task_id = celery_device_service.execute_backup(
                        connection_args=device_info['connection_args'],
                        device_name=device_name,
                        device_platform=device_info['device_info'].get('platform'),
                        juniper_set_format=juniper_set_format,
                        created_by=created_by
                    )
                    submitted.append({'device': device_name, 'task_id': task_id})
                    save_task_id(task_id, device_name=f"backup:{device_name}:{task_id}")
                else:
                    failed.append({'device': device_name, 'error': 'Could not get connection info'})
            except Exception as e:
                failed.append({'device': device_name, 'error': str(e)})

        return jsonify({
            'success': True,
            'submitted': len(submitted),
            'failed': len(failed),
            'tasks': submitted,
            'errors': failed
        })
    except Exception as e:
        log.error(f"Error running selected device backups: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/task/<task_id>', methods=['GET'])
@login_required
def get_backup_task_status(task_id):
    """Get status of a backup task.

    Note: Backups are now saved directly by the Celery task when it completes,
    so this endpoint is only for status polling by the frontend.
    """
    try:
        result = celery_device_service.get_task_result(task_id)
        log.debug(f"Task {task_id} status: {result.get('status')}")

        # Check if task result indicates it was saved
        if result.get('status') == 'success' and result.get('result'):
            task_result = result['result']
            if task_result.get('saved'):
                result['saved'] = True
            # Propagate status from inner result
            if task_result.get('status') == 'success':
                result['status'] = 'success'
            elif task_result.get('status') == 'failed':
                result['status'] = 'failed'
                result['error'] = task_result.get('error')

        return jsonify({'success': True, **result})
    except Exception as e:
        log.error(f"Error getting backup task status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Backup schedule and cleanup routes migrated to routes/api.py

@app.route('/api/config-backups/cleanup-orphans', methods=['POST'])
@login_required
def cleanup_orphaned_backups():
    """Delete backups for devices not in current cache"""
    try:
        # Get cached device names
        cached_devices = device_service_get_cached()
        if not cached_devices:
            return jsonify({
                'success': False,
                'error': 'Device cache is empty. Load devices on the Devices page first.'
            }), 400

        cached_device_names = set(d.get('name') for d in cached_devices if d.get('name'))
        log.info(f"Found {len(cached_device_names)} devices in cache")

        # Get all unique device names from backups
        summary = db.get_backup_summary()
        backup_device_names = set(summary.get('devices_with_backups', []))
        log.info(f"Found {len(backup_device_names)} unique devices with backups")

        # Find orphaned devices (in backups but not in cache)
        orphaned_devices = backup_device_names - cached_device_names
        log.info(f"Found {len(orphaned_devices)} orphaned devices")

        if not orphaned_devices:
            return jsonify({
                'success': True,
                'deleted_count': 0,
                'orphaned_devices': 0,
                'cached_device_count': len(cached_device_names),
                'message': 'No orphaned backups found'
            })

        # Delete backups for orphaned devices
        deleted_count = db.delete_backups_for_devices(list(orphaned_devices))
        log.info(f"Deleted {deleted_count} backups from {len(orphaned_devices)} orphaned devices")

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'orphaned_devices': len(orphaned_devices),
            'cached_device_count': len(cached_device_names)
        })
    except Exception as e:
        log.error(f"Error cleaning up orphaned backups: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Config Snapshot API Endpoints
# =============================================================================

@app.route('/api/config-snapshots', methods=['GET'])
@login_required
def get_config_snapshots_api():
    """Get all config snapshots"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        snapshots = db.get_config_snapshots(limit=limit, offset=offset)
        return jsonify({'success': True, 'snapshots': snapshots})
    except Exception as e:
        log.error(f"Error getting config snapshots: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/<snapshot_id>', methods=['GET'])
@login_required
def get_config_snapshot_api(snapshot_id):
    """Get a specific config snapshot with its backups"""
    try:
        snapshot = db.get_config_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({'success': False, 'error': 'Snapshot not found'}), 404

        # Get all backups for this snapshot
        backups = db.get_snapshot_backups(snapshot_id)
        snapshot['backups'] = backups

        return jsonify({'success': True, 'snapshot': snapshot})
    except Exception as e:
        log.error(f"Error getting config snapshot: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/<snapshot_id>', methods=['PUT'])
@login_required
def update_config_snapshot_api(snapshot_id):
    """Update a config snapshot (name, description)"""
    try:
        data = request.json or {}
        snapshot = db.get_config_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({'success': False, 'error': 'Snapshot not found'}), 404

        db.update_config_snapshot(snapshot_id, data)
        return jsonify({'success': True, 'message': 'Snapshot updated'})
    except Exception as e:
        log.error(f"Error updating config snapshot: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/<snapshot_id>', methods=['DELETE'])
@login_required
def delete_config_snapshot_api(snapshot_id):
    """Delete a config snapshot and all its backups"""
    try:
        snapshot = db.get_config_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({'success': False, 'error': 'Snapshot not found'}), 404

        db.delete_config_snapshot(snapshot_id)
        log.info(f"Deleted snapshot {snapshot_id} and all its backups")
        return jsonify({'success': True, 'message': 'Snapshot deleted'})
    except Exception as e:
        log.error(f"Error deleting config snapshot: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/<snapshot_id>/recalculate', methods=['POST'])
@login_required
def recalculate_snapshot_counts_api(snapshot_id):
    """Recalculate snapshot counts from actual backups in database"""
    try:
        snapshot = db.get_config_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({'success': False, 'error': 'Snapshot not found'}), 404

        result = db.recalculate_snapshot_counts(snapshot_id)
        if result:
            # Get updated snapshot
            updated = db.get_config_snapshot(snapshot_id)
            return jsonify({
                'success': True,
                'message': 'Counts recalculated',
                'snapshot': updated
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to recalculate counts'}), 500
    except Exception as e:
        log.error(f"Error recalculating snapshot counts: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/fix-stale', methods=['POST'])
@login_required
def fix_stale_snapshots_api():
    """Fix snapshots stuck in in_progress state for over 30 minutes"""
    try:
        fixed_count = db.check_and_fix_stale_snapshots()
        return jsonify({
            'success': True,
            'fixed_count': fixed_count,
            'message': f'Fixed {fixed_count} stale snapshots'
        })
    except Exception as e:
        log.error(f"Error fixing stale snapshots: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-snapshots/<snapshot_id>/compare/<other_snapshot_id>', methods=['GET'])
@login_required
def compare_config_snapshots_api(snapshot_id, other_snapshot_id):
    """Compare two snapshots across all devices"""
    try:
        snapshot1 = db.get_config_snapshot(snapshot_id)
        snapshot2 = db.get_config_snapshot(other_snapshot_id)

        if not snapshot1:
            return jsonify({'success': False, 'error': f'Snapshot {snapshot_id} not found'}), 404
        if not snapshot2:
            return jsonify({'success': False, 'error': f'Snapshot {other_snapshot_id} not found'}), 404

        # Get backups for both snapshots
        backups1 = db.get_snapshot_backups(snapshot_id)
        backups2 = db.get_snapshot_backups(other_snapshot_id)

        # Create lookup by device name
        backup_map1 = {b['device_name']: b for b in backups1}
        backup_map2 = {b['device_name']: b for b in backups2}

        # Find all devices
        all_devices = set(backup_map1.keys()) | set(backup_map2.keys())

        comparison = []
        for device in sorted(all_devices):
            b1 = backup_map1.get(device)
            b2 = backup_map2.get(device)

            comp_item = {
                'device_name': device,
                'in_snapshot1': b1 is not None,
                'in_snapshot2': b2 is not None,
                'changed': False
            }

            if b1 and b2:
                comp_item['changed'] = b1.get('config_hash') != b2.get('config_hash')
                comp_item['backup1_id'] = b1['backup_id']
                comp_item['backup2_id'] = b2['backup_id']
            elif b1:
                comp_item['backup1_id'] = b1['backup_id']
            elif b2:
                comp_item['backup2_id'] = b2['backup_id']

            comparison.append(comp_item)

        return jsonify({
            'success': True,
            'snapshot1': snapshot1,
            'snapshot2': snapshot2,
            'comparison': comparison,
            'summary': {
                'total_devices': len(all_devices),
                'changed': sum(1 for c in comparison if c['changed']),
                'only_in_snapshot1': sum(1 for c in comparison if c['in_snapshot1'] and not c['in_snapshot2']),
                'only_in_snapshot2': sum(1 for c in comparison if c['in_snapshot2'] and not c['in_snapshot1'])
            }
        })
    except Exception as e:
        log.error(f"Error comparing snapshots: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# /snapshots and /config-backups pages migrated to routes/pages.py

@app.route('/api/network-topology', methods=['GET'])
@login_required
def get_network_topology():
    """Get network topology data for visualization"""
    try:
        # Combine devices from NetBox and manual devices
        all_devices = []
        device_id = 0

        # Get settings for NetBox
        try:
            settings = get_settings()
            netbox_url = settings.get('netbox_url', '').strip()
            netbox_token = settings.get('netbox_token', '').strip()
            verify_ssl = settings.get('verify_ssl', False)
        except Exception as e:
            log.warning(f"Could not get settings: {e}")
            netbox_url = ''
            netbox_token = ''

        # Get NetBox devices if configured
        if netbox_url and netbox_token:
            try:
                netbox = get_netbox_client()
                if netbox:
                    netbox_devices = netbox.get_devices()
                    if netbox_devices:
                        for device in netbox_devices:
                            device_id += 1
                            all_devices.append({
                                'id': f'netbox-{device_id}',
                                'name': device.get('name', 'Unknown'),
                                'type': device.get('device_type', {}).get('slug', 'unknown'),
                                'source': 'netbox',
                                'ip': device.get('primary_ip4', {}).get('address', '').split('/')[0] if device.get('primary_ip4') else None,
                                'site': device.get('site', {}).get('name', 'Unknown') if device.get('site') else None
                            })
            except Exception as e:
                log.warning(f"Could not fetch NetBox devices: {e}")

        # Get manual devices
        try:
            manual_devices = db.get_all_manual_devices()
            if manual_devices:
                for device in manual_devices:
                    device_id += 1
                    all_devices.append({
                        'id': f'manual-{device_id}',
                        'name': device.get('name', 'Unknown'),
                        'type': device.get('type', 'unknown'),
                        'source': 'manual',
                        'ip': device.get('host'),
                        'port': device.get('port', 22)
                    })
        except Exception as e:
            log.warning(f"Could not fetch manual devices: {e}")

        log.info(f"Network topology loaded: {len(all_devices)} devices")

        return jsonify({
            'success': True,
            'devices': all_devices,
            'count': len(all_devices)
        })
    except Exception as e:
        log.error(f"Error getting network topology: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/network-connections', methods=['POST'])
@login_required
def get_network_connections():
    """Get network connections between devices from NetBox"""
    try:
        data = request.json
        device_names = data.get('device_names', [])

        if not device_names:
            return jsonify({'success': True, 'connections': [], 'cached': False})

        # Create cache key based on device names
        cache_key = 'connections_' + json.dumps(sorted(device_names), sort_keys=True)

        # Check cache
        now = datetime.now().timestamp()
        cache_entry = device_cache.get(cache_key, {})
        if (cache_entry.get('connections') is not None and
            cache_entry.get('timestamp') is not None and
            (now - cache_entry['timestamp']) < device_cache.get('ttl', 300)):
            log.info(f"Returning cached connections ({len(cache_entry['connections'])} connections)")
            return jsonify({'success': True, 'connections': cache_entry['connections'], 'cached': True})

        log.info(f"Fetching connections for {len(device_names)} devices")

        # Get NetBox client
        settings = get_settings()
        netbox_url = settings.get('netbox_url', '').strip()
        netbox_token = settings.get('netbox_token', '').strip()

        if not netbox_url or not netbox_token:
            log.warning("NetBox not configured")
            return jsonify({'success': True, 'connections': [], 'cached': False})

        # Fetch connections from NetBox
        netbox_client = get_netbox_client()
        connections = netbox_client.get_device_connections(device_names)

        # Update cache
        device_cache[cache_key] = {
            'connections': connections,
            'timestamp': now
        }

        log.info(f"Returning {len(connections)} connections (cached for future requests)")
        return jsonify({'success': True, 'connections': connections, 'cached': False})

    except Exception as e:
        log.error(f"Error getting network connections: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/test-netbox', methods=['POST'])
@login_required
def test_netbox_connection():
    """Test Netbox API connection with provided credentials"""
    try:
        import time
        from netbox_client import NetboxClient

        data = request.json
        netbox_url = data.get('netbox_url', '').strip()
        netbox_token = data.get('netbox_token', '').strip()
        verify_ssl = data.get('verify_ssl', False)
        filter_list = data.get('filters', [])

        if not netbox_url:
            return jsonify({'success': False, 'error': 'Netbox URL is required'}), 400

        # Keep filters as list to support multiple values for same key
        filters = []
        for f in filter_list:
            if 'key' in f and 'value' in f:
                filters.append({'key': f['key'], 'value': f['value']})

        # Build the test URL that will be called
        test_url = f"{netbox_url.rstrip('/')}/api/dcim/devices/?limit=3000"
        if filters:
            filter_params = '&'.join([f"{f['key']}={f['value']}" for f in filters])
            test_url += '&' + filter_params

        # Log the full request details
        log.info(f"Testing Netbox connection to: {test_url}")
        log.info(f"SSL Verification: {verify_ssl}")
        log.info(f"Using token: {'Yes' if netbox_token else 'No'}")
        if filters:
            log.info(f"Applying filters: {filters}")

        # Create a test client
        test_client = NetboxClient(netbox_url, netbox_token, verify_ssl)

        # Measure response time
        start_time = time.time()

        # Try to fetch devices with filters
        devices = test_client.get_devices(brief=False, limit=3000, filters=filters)

        end_time = time.time()
        response_time = f"{(end_time - start_time):.2f}s"

        if devices is not None:
            # Get total count
            device_count = len(devices)

            # Cache the devices for faster network map loading
            try:
                cache_key = json.dumps({'filters': filters}, sort_keys=True)
                now = datetime.now().timestamp()

                # Transform devices to match /api/devices format
                formatted_devices = []
                for device in devices:
                    formatted_devices.append({
                        'name': device.get('name'),
                        'device_type': device.get('device_type'),
                        'platform': device.get('platform'),
                        'manufacturer': device.get('manufacturer'),
                        'primary_ip': device.get('primary_ip'),
                        'site': device.get('site'),
                        'status': 'Active',
                        'source': 'netbox'
                    })

                device_cache[cache_key] = {
                    'devices': formatted_devices,
                    'timestamp': now
                }
                log.info(f"Pre-cached {len(formatted_devices)} devices")

                # Also fetch and cache connections
                device_names = [d.get('name') for d in devices if d.get('name')]
                if device_names:
                    log.info(f"Pre-fetching connections for {len(device_names)} devices...")
                    connections = test_client.get_device_connections(device_names)

                    # Cache connections
                    conn_cache_key = 'connections_' + json.dumps(sorted(device_names), sort_keys=True)
                    device_cache[conn_cache_key] = {
                        'connections': connections,
                        'timestamp': now
                    }
                    log.info(f"Pre-cached {len(connections)} connections")
                else:
                    connections = []

            except Exception as cache_error:
                log.warning(f"Failed to pre-cache devices/connections: {cache_error}")
                connections = []

            return jsonify({
                'success': True,
                'device_count': device_count,
                'connection_count': len(connections) if 'connections' in locals() else 0,
                'response_time': response_time,
                'message': 'Successfully connected to Netbox and pre-cached data',
                'api_url': test_url,
                'verify_ssl': verify_ssl,
                'has_token': bool(netbox_token),
                'cached': True
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch devices from Netbox',
                'api_url': test_url
            }), 500

    except requests.exceptions.SSLError as e:
        log.error(f"SSL Error testing Netbox: {e}")
        return jsonify({
            'success': False,
            'error': f'SSL certificate verification failed. Try disabling "Verify SSL certificates" if using self-signed certificates.',
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500
    except requests.exceptions.ConnectionError as e:
        log.error(f"Connection Error testing Netbox: {e}")
        return jsonify({
            'success': False,
            'error': f'Could not connect to Netbox. Check the URL and network connectivity.',
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500
    except requests.exceptions.Timeout as e:
        log.error(f"Timeout testing Netbox: {e}")
        return jsonify({
            'success': False,
            'error': 'Connection timed out after 30 seconds. Netbox may be slow or unreachable.',
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500
    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP Error testing Netbox: {e}")
        status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
        if status_code == 403:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Check your API token.',
                'api_url': test_url if 'test_url' in locals() else 'N/A',
                'status_code': status_code,
                'details': str(e)
            }), 500
        elif status_code == 404:
            return jsonify({
                'success': False,
                'error': 'API endpoint not found. Check your Netbox URL.',
                'api_url': test_url if 'test_url' in locals() else 'N/A',
                'status_code': status_code,
                'details': str(e)
            }), 500
        else:
            return jsonify({
                'success': False,
                'error': f'HTTP error {status_code}: {str(e)}',
                'api_url': test_url if 'test_url' in locals() else 'N/A',
                'status_code': status_code,
                'details': str(e)
            }), 500
    except Exception as e:
        log.error(f"Error testing Netbox connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500


@app.route('/api/device-names')
@login_required
def get_device_names():
    """Get simple list of device names"""
    try:
        netbox_client = get_netbox_client()
        names = netbox_client.get_device_names()
        return jsonify({'success': True, 'names': names})
    except Exception as e:
        log.error(f"Error fetching device names: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device/<device_name>/connection-info')
@login_required
def api_get_device_connection_info(device_name):
    """API endpoint: Get device connection information including netmiko device_type"""
    try:
        netbox_client = get_netbox_client()
        device = netbox_client.get_device_by_name(device_name)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Get platform from config_context.nornir.platform (preferred)
        nornir_platform = device.get('config_context', {}).get('nornir', {}).get('platform')

        # Fallback to netbox platform if nornir platform not set
        if not nornir_platform:
            platform = device.get('platform', {})
            device_type = device.get('device_type', {})

            # Handle device_type being either dict or string
            if isinstance(device_type, dict):
                manufacturer = device_type.get('manufacturer', {})
            else:
                manufacturer = {}

            platform_name = platform.get('name') if isinstance(platform, dict) else None
            manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None

            from netbox_client import get_netmiko_device_type
            nornir_platform = get_netmiko_device_type(platform_name, manufacturer_name)

        # Get IP address
        primary_ip = device.get('primary_ip', {}) or device.get('primary_ip4', {})
        ip_address = None
        if primary_ip:
            ip_addr_full = primary_ip.get('address', '')
            # Remove CIDR notation if present
            ip_address = ip_addr_full.split('/')[0] if ip_addr_full else None

        return jsonify({
            'success': True,
            'device_name': device_name,
            'device_type': nornir_platform,  # This is the netmiko device_type
            'ip_address': ip_address
        })
    except Exception as e:
        log.error(f"Error fetching device connection info for {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks')
@login_required
def get_tasks():
    """Get all tasks from local task history"""
    try:
        # Get task history from our local store
        history = get_task_history()

        # Build map of task_id to creation time
        task_times = {}
        all_task_ids = []
        for item in history:
            task_id = item.get('task_id')
            created = item.get('created', '1970-01-01T00:00:00')
            if task_id:
                task_times[task_id] = created
                if task_id not in all_task_ids:
                    all_task_ids.append(task_id)

        # Sort by creation time (newest first)
        sorted_tasks = sorted(
            all_task_ids,
            key=lambda tid: task_times.get(tid, '9999-99-99T99:99:99'),
            reverse=True
        )

        return jsonify({
            'status': 'success',
            'data': {
                'task_id': sorted_tasks[:100]  # Limit to 100 most recent
            }
        })
    except Exception as e:
        log.error(f"Error fetching tasks: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/metadata')
@login_required
def get_tasks_metadata():
    """Get task metadata including device names from history"""
    try:
        # Get task history from our local store
        history = get_task_history()

        # Build metadata map: task_id -> device_name
        metadata = {}
        for item in history:
            task_id = item.get('task_id')
            device_name = item.get('device_name')
            if task_id:
                metadata[task_id] = {
                    'device_name': device_name,
                    'created': item.get('created')
                }

        return jsonify({
            'success': True,
            'metadata': metadata
        })
    except Exception as e:
        log.error(f"Error fetching task metadata: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/task/<task_id>')
@login_required
def get_task(task_id):
    """Get specific task details from Celery"""
    try:
        result = celery_device_service.get_task_result(task_id)

        # Also try to get task metadata from our task_metadata store
        task_meta = {}
        try:
            from tasks import get_task_metadata
            task_meta = get_task_metadata(task_id) or {}
        except ImportError:
            pass
        except Exception as e:
            log.debug(f"Could not get task metadata: {e}")

        return jsonify({
            'status': 'success',
            'data': {
                'task_id': task_id,
                'task_status': result.get('status', 'unknown'),
                'task_result': result.get('result', {}),
                'task_queue': result.get('queue') or task_meta.get('queue', 'celery'),
                'task_meta': {
                    'assigned_worker': result.get('worker') or task_meta.get('worker'),
                    'started_at': task_meta.get('started_at') or result.get('started_at'),
                    'ended_at': result.get('ended_at') or task_meta.get('ended_at'),
                    'total_elapsed_seconds': task_meta.get('duration', 0)
                },
                'task_errors': result.get('errors', []),
                'created_on': task_meta.get('created_at') or task_meta.get('enqueued_at')
            }
        })
    except Exception as e:
        log.error(f"Error fetching task {task_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workers')
@login_required
def get_workers():
    """Get Celery worker info"""
    try:
        from tasks import celery_app

        # Get active workers from Celery
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        stats = inspect.stats() or {}

        workers = []
        for worker_name, worker_stats in stats.items():
            workers.append({
                'name': worker_name,
                'status': 'online',
                'active_tasks': len(active.get(worker_name, [])),
                'pool': worker_stats.get('pool', {}).get('max-concurrency', 'N/A'),
                'broker': worker_stats.get('broker', {}).get('hostname', 'redis')
            })

        if not workers:
            workers = [{'name': 'No workers connected', 'status': 'offline'}]

        return jsonify(workers)
    except Exception as e:
        log.error(f"Error fetching workers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workers/tasks')
@login_required
def get_registered_tasks():
    """Get list of registered Celery tasks"""
    try:
        from tasks import celery_app

        # Get registered tasks from Celery
        inspect = celery_app.control.inspect()
        registered = inspect.registered() or {}

        # Collect all unique tasks across workers
        all_tasks = set()
        for worker_name, tasks in registered.items():
            all_tasks.update(tasks)

        # Filter out celery internal tasks
        filtered_tasks = [t for t in all_tasks if not t.startswith('celery.')]

        return jsonify({
            'success': True,
            'tasks': sorted(filtered_tasks)
        })
    except Exception as e:
        log.error(f"Error fetching registered tasks: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/getconfig', methods=['POST'])
@login_required
def deploy_getconfig():
    """Deploy getconfig to device - uses Celery"""
    try:
        data = request.json
        log.info(f"Received getconfig request: {data}")

        device_name = data.get('device_name')
        payload = data.get('payload', {})
        connection_args = payload.get('connection_args', {})
        command = payload.get('command', 'show running-config')

        # Apply default credentials if not provided
        if not connection_args.get('username') or not connection_args.get('password'):
            settings = db.get_all_settings()
            if not connection_args.get('username'):
                connection_args['username'] = settings.get('default_username', '')
            if not connection_args.get('password'):
                connection_args['password'] = settings.get('default_password', '')
            log.info(f"Applied default credentials for {device_name}")

        # Extract parsing options from payload.args (where frontend sends them)
        args = payload.get('args', {})
        use_textfsm = args.get('use_textfsm', False)
        use_ttp = args.get('use_ttp', False)
        ttp_template = args.get('ttp_template', None)

        log.info(f"Parsing options: textfsm={use_textfsm}, ttp={use_ttp}")

        # Execute via Celery
        task_id = celery_device_service.execute_get_config(
            connection_args=connection_args,
            command=command,
            use_textfsm=use_textfsm,
            use_ttp=use_ttp,
            ttp_template=ttp_template
        )

        if task_id:
            save_task_id(task_id, device_name)

        return jsonify({
            'status': 'success',
            'data': {'task_id': task_id}
        })
    except Exception as e:
        log.error(f"Error deploying getconfig: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/setconfig', methods=['POST'])
@login_required
def deploy_setconfig():
    """Deploy setconfig to device - uses Celery"""
    try:
        data = request.json
        device_name = data.get('device_name')
        payload = data.get('payload', {})
        connection_args = payload.get('connection_args', {})
        config = payload.get('config', payload.get('config_set', ''))

        # Apply default credentials if not provided
        if not connection_args.get('username') or not connection_args.get('password'):
            settings = db.get_all_settings()
            if not connection_args.get('username'):
                connection_args['username'] = settings.get('default_username', '')
            if not connection_args.get('password'):
                connection_args['password'] = settings.get('default_password', '')
            log.info(f"Applied default credentials for {device_name}")

        # Handle config as string or list
        if isinstance(config, list):
            config_lines = config
        else:
            config_lines = config.split('\n') if config else []

        # Execute via Celery
        task_id = celery_device_service.execute_set_config(
            connection_args=connection_args,
            config_lines=config_lines,
            save_config=payload.get('save_config', True)
        )

        if task_id:
            save_task_id(task_id, device_name)

        return jsonify({
            'status': 'success',
            'data': {'task_id': task_id}
        })
    except Exception as e:
        log.error(f"Error deploying setconfig: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/setconfig/dry-run', methods=['POST'])
@login_required
def deploy_setconfig_dryrun():
    """Deploy setconfig dry-run - renders template without deploying"""
    try:
        data = request.json
        payload = data.get('payload', {})

        # If there's a j2config, render it locally
        j2config = payload.get('j2config', {})
        if j2config:
            template_name = j2config.get('template', '')
            variables = j2config.get('args', {})
            rendered = render_j2_template(template_name, variables)
            return jsonify({
                'status': 'success',
                'data': {'rendered_config': rendered}
            })

        # Otherwise just return the config that would be deployed
        return jsonify({
            'status': 'success',
            'data': {'rendered_config': payload.get('config', '')}
        })
    except Exception as e:
        log.error(f"Error in dry-run: {e}")
        return jsonify({'error': str(e)}), 500


# Template Management API Endpoints

@app.route('/api/templates')
@login_required
def get_templates():
    """List all J2 config templates with metadata - now uses local database"""
    try:
        templates = db.get_all_templates()

        # Format for frontend compatibility
        template_list = [{
            'name': t['name'],
            'type': t.get('type', 'deploy'),
            'validation_template': t.get('validation_template'),
            'delete_template': t.get('delete_template'),
            'description': t.get('description'),
            'has_content': bool(t.get('content'))
        } for t in templates]

        return jsonify({'success': True, 'templates': template_list})
    except Exception as e:
        log.error(f"Error fetching templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/<template_name>')
@login_required
def get_template(template_name):
    """Get specific J2 template content - now uses local database"""
    try:
        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        template = db.get_template_metadata(template_name)

        if template and template.get('content'):
            return jsonify({'success': True, 'content': template['content']})
        else:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

    except Exception as e:
        log.error(f"Error fetching template {template_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates', methods=['POST'])
@login_required
def create_template():
    """Create/update J2 template - saves to local database"""
    try:
        data = request.json
        template_name = data.get('name')
        content = data.get('content')

        # Support base64 encoded content from frontend
        if not content and data.get('base64_payload'):
            import base64
            try:
                content = base64.b64decode(data.get('base64_payload')).decode('utf-8')
            except Exception as e:
                log.error(f"Failed to decode base64 content: {e}")
                return jsonify({'success': False, 'error': 'Invalid base64 content'}), 400

        if not template_name:
            return jsonify({'success': False, 'error': 'Missing template name'}), 400

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        if not content:
            return jsonify({'success': False, 'error': 'Missing template content'}), 400

        # Build metadata
        metadata = {
            'type': data.get('type', 'deploy'),
            'vendor_types': data.get('vendor_types'),
            'description': data.get('description'),
            'validation_template': data.get('validation_template'),
            'delete_template': data.get('delete_template')
        }

        # Save to local database
        db.save_template(template_name, content, metadata)
        log.info(f"Saved template: {template_name}")

        return jsonify({
            'success': True,
            'message': f'Template {template_name} saved successfully'
        })

    except Exception as e:
        log.error(f"Error creating template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/<template_name>/metadata', methods=['PUT'])
@login_required
def update_template_metadata(template_name):
    """Update template metadata (validation and delete templates, type)"""
    try:
        data = request.json
        log.info(f"Updating template metadata for {template_name}, received data: {data}")

        # Strip .j2 extension for consistency
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        metadata = {
            'type': data.get('type', 'deploy'),  # deploy, delete, or validation
            'vendor_types': data.get('vendor_types'),
            'validation_template': data.get('validation_template'),
            'delete_template': data.get('delete_template'),
            'description': data.get('description'),
            'updated_at': datetime.now().isoformat()
        }

        log.info(f"Saving metadata: {metadata}")
        save_template_metadata(template_name, metadata)

        return jsonify({'success': True, 'message': 'Template metadata updated successfully'})
    except Exception as e:
        log.error(f"Error updating template metadata: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates', methods=['DELETE'])
@login_required
def delete_template():
    """Delete J2 template from local database"""
    try:
        data = request.json
        template_name = data.get('name')

        if not template_name:
            return jsonify({'success': False, 'error': 'Missing template name'}), 400

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        # Delete from local database
        if db.delete_template_metadata(template_name):
            log.info(f"Deleted template: {template_name}")
            return jsonify({'success': True, 'message': 'Template deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

    except Exception as e:
        log.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/templates/<template_name>/variables')
@login_required
def get_template_variables(template_name):
    """Extract variables from J2 template"""
    try:
        import re

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        # Get template content from local database
        template_content = db.get_template_content(template_name)
        if not template_content:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        # Extract variables using regex - match {{ variable_name }} patterns
        variable_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
        variables = list(set(re.findall(variable_pattern, template_content)))
        variables.sort()

        return jsonify({'success': True, 'variables': variables, 'template_content': template_content})
    except Exception as e:
        log.error(f"Error extracting template variables: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/render', methods=['POST'])
@login_required
def api_render_j2_template():
    """API endpoint: Render J2 template with provided variables"""
    try:
        data = request.json
        template_name = data.get('template_name')
        variables = data.get('variables', {})

        if not template_name:
            return jsonify({'success': False, 'error': 'Missing template name'}), 400

        # Render template locally
        rendered_config = render_j2_template(template_name, variables)

        if not rendered_config:
            return jsonify({'success': False, 'error': 'Failed to render template'}), 500

        return jsonify({'success': True, 'rendered_config': rendered_config})
    except Exception as e:
        log.error(f"Error rendering template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/generate-template', methods=['POST'])
@login_required
def generate_template_with_ai():
    """Generate a Jinja2 template using AI based on user description"""
    try:
        data = request.json
        prompt = data.get('prompt', '').strip()
        template_type = data.get('template_type', 'deploy')
        vendor_types = data.get('vendor_types', [])

        if not prompt:
            return jsonify({'success': False, 'error': 'Please provide a description of the template'}), 400

        # Import LLM client
        try:
            from ai.llm.factory import get_llm_client
        except ImportError as e:
            log.error(f"Failed to import LLM client: {e}")
            return jsonify({'success': False, 'error': 'AI features not configured. Please configure an LLM provider in Settings.'}), 500

        # Get LLM client
        try:
            llm = get_llm_client()
        except ValueError as e:
            log.warning(f"LLM not configured: {e}")
            return jsonify({'success': False, 'error': str(e)}), 400

        # Build the system prompt for template generation
        vendor_context = ""
        if vendor_types:
            vendor_names = {
                'cisco_ios': 'Cisco IOS',
                'cisco_xe': 'Cisco IOS-XE',
                'cisco_xr': 'Cisco IOS-XR',
                'cisco_nxos': 'Cisco NX-OS',
                'juniper_junos': 'Juniper JunOS',
                'arista_eos': 'Arista EOS',
                'huawei': 'Huawei VRP',
                'nokia_sros': 'Nokia SR OS',
                'paloalto_panos': 'Palo Alto PAN-OS',
                'fortinet': 'Fortinet FortiOS',
                'linux': 'Linux'
            }
            vendor_list = [vendor_names.get(v, v) for v in vendor_types]
            vendor_context = f"\n\nTarget platform(s): {', '.join(vendor_list)}"

        type_context = {
            'deploy': 'This is a DEPLOY template - it should add/configure something on the device.',
            'delete': 'This is a DELETE template - it should remove/unconfigure something from the device.',
            'validation': 'This is a VALIDATION template - it should contain commands to verify configuration.'
        }.get(template_type, '')

        system_prompt = f"""You are an expert network automation engineer. Generate a Jinja2 template for network device configuration.

IMPORTANT RULES:
1. Output ONLY the Jinja2 template content - no explanations, no markdown code blocks, no surrounding text
2. Use proper Jinja2 syntax: {{{{ variable_name }}}} for variables
3. Use descriptive variable names in snake_case
4. Include comments in the template to explain sections
5. Use Jinja2 control structures (if/for) when appropriate
6. Follow vendor-specific CLI syntax exactly
7. Start with the actual configuration commands, not show commands

{type_context}
{vendor_context}

Remember: Output ONLY the raw Jinja2 template content."""

        # Make the LLM call
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a Jinja2 template to: {prompt}"}
        ]

        response = llm.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )

        if not response.content:
            return jsonify({'success': False, 'error': 'AI returned empty response'}), 500

        # Clean up the response - remove any markdown code blocks if present
        template_content = response.content.strip()
        if template_content.startswith('```'):
            lines = template_content.split('\n')
            # Remove first line (```jinja2 or similar)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            template_content = '\n'.join(lines)

        # Try to suggest a template name based on the prompt
        suggested_name = None
        description = None

        # Simple name extraction from common patterns
        prompt_lower = prompt.lower()
        name_parts = []

        # Extract action
        for action in ['configure', 'add', 'create', 'set', 'enable', 'disable', 'remove', 'delete']:
            if action in prompt_lower:
                break

        # Extract key terms for the name
        keywords = ['snmp', 'ntp', 'vlan', 'interface', 'bgp', 'ospf', 'acl', 'route', 'dns',
                    'syslog', 'aaa', 'tacacs', 'radius', 'ssh', 'banner', 'user', 'logging']
        for kw in keywords:
            if kw in prompt_lower:
                name_parts.append(kw)

        if name_parts:
            suggested_name = '_'.join(name_parts[:2])  # Max 2 keywords
            if template_type == 'delete':
                suggested_name += '_delete'
            elif template_type == 'validation':
                suggested_name += '_validate'

        # Use first part of prompt as description
        description = prompt[:100] + ('...' if len(prompt) > 100 else '')

        return jsonify({
            'success': True,
            'template': template_content,
            'suggested_name': suggested_name,
            'description': description
        })

    except Exception as e:
        log.error(f"Error generating template with AI: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to generate template: {str(e)}'}), 500


# Services, users pages and user management API migrated to blueprints
# - /services -> routes/services.py
# - /service-stacks -> routes/stacks.py
# - /users -> routes/admin.py
# - /api/users -> routes/admin.py
# - /api/user/theme -> routes/admin.py

# Service templates and instances CRUD migrated to routes/services.py
# Service instance Celery operations stay here (create, healthcheck, redeploy, delete, validate)

@app.route('/api/services/instances/create', methods=['POST'])
@login_required
def create_template_service():
    """Create a new template-based service instance

    Expected JSON payload:
    {
        "name": "My VLAN Service",
        "template": "vlan_config.j2",
        "reverse_template": "vlan_remove.j2",  // optional
        "variables": {"vlan_id": 100, "vlan_name": "Guest"},
        "device": "switch1",  // single device for now
        "username": "admin",  // optional - from settings if not provided
        "password": "secret"  // optional - from settings if not provided
    }
    """
    try:
        data = request.json
        log.info(f"Creating template service with data: {data}")

        # Extract required fields
        service_name = data.get('name')
        template = data.get('template')
        variables = data.get('variables', {})
        device = data.get('device')

        if not all([service_name, template, device]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: name, template, device'
            }), 400

        # Get credentials
        username = data.get('username')
        password = data.get('password')

        # Get device connection info
        credential_override = None
        if username and password:
            credential_override = {'username': username, 'password': password}

        device_info = get_device_connection_info(device, credential_override)
        if not device_info:
            return jsonify({
                'success': False,
                'error': f'Could not get connection info for device: {device}'
            }), 400

        # Add credentials to connection_args if provided
        if username and password:
            device_info['connection_args']['username'] = username
            device_info['connection_args']['password'] = password

        # Get template metadata (validation and delete templates)
        template_lookup = template[:-3] if template.endswith('.j2') else template
        template_metadata = get_template_metadata(template_lookup) or {}

        # Render template
        rendered_config = render_j2_template(template, variables)
        if not rendered_config:
            return jsonify({
                'success': False,
                'error': f'Failed to render template: {template}'
            }), 500

        # Push config to device using Celery
        task_id = celery_device_service.execute_set_config(
            connection_args=device_info['connection_args'],
            config_lines=rendered_config.split('\n'),
            save_config=True
        )
        if task_id:
            save_task_id(task_id, device_name=f"service:{service_name}")

        # Create service instance
        service_data = {
            'name': service_name,
            'template': template,
            'reverse_template': data.get('reverse_template') or template_metadata.get('delete_template'),
            'validation_template': template_metadata.get('validation_template'),
            'delete_template': template_metadata.get('delete_template'),
            'variables': variables,
            'device': device,
            'state': 'deploying',
            'rendered_config': rendered_config,
            'task_id': task_id
        }

        service_id = save_service_instance(service_data)

        return jsonify({
            'success': True,
            'service_id': service_id,
            'task_id': task_id,
            'message': f'Service "{service_name}" created and deploying to {device}'
        })

    except Exception as e:
        log.error(f"Error creating template service: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/healthcheck', methods=['POST'])
@login_required
def health_check_service_instance(service_id):
    """Health check a service instance by validating config on device"""
    try:
        from services.device_service import get_device_connection_info as get_conn_info

        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        device = service.get('device')
        if not device:
            return jsonify({'success': False, 'error': 'Service has no device'}), 400

        # Get device connection info
        device_info = get_conn_info(device)
        if not device_info:
            return jsonify({'success': False, 'error': f'Could not get connection info for device: {device}'}), 400

        # Get validation patterns from rendered config
        rendered_config = service.get('rendered_config', '')
        if not rendered_config:
            return jsonify({'success': False, 'error': 'No rendered config to validate'}), 400

        # Use first few lines as validation patterns
        patterns = [line.strip() for line in rendered_config.split('\n')[:5] if line.strip()]

        # Execute validation via Celery
        task_id = celery_device_service.execute_validate(
            connection_args=device_info['connection_args'],
            expected_patterns=patterns,
            validation_command='show running-config'
        )

        if task_id:
            save_task_id(task_id, device_name=f"service_healthcheck:{service_id}")

        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        log.error(f"Error health checking service instance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/redeploy', methods=['POST'])
@login_required
def redeploy_service_instance(service_id):
    """Redeploy a service instance using stored configuration"""
    try:
        from services.device_service import get_device_connection_info as get_conn_info

        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        if not service.get('template'):
            return jsonify({'success': False, 'error': 'Service has no template to redeploy'}), 400

        # Get credentials from request if provided
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Redeploying service {service_id} to device {service.get('device')}")

        # Get device connection info
        credential_override = {'username': username, 'password': password} if username and password else None
        device_info = get_conn_info(service['device'], credential_override)
        if not device_info:
            return jsonify({'success': False, 'error': f'Could not get connection info for device: {service["device"]}'}), 400

        # Render template and deploy via Celery
        rendered_config = render_j2_template(service['template'], service.get('variables', {}))
        if not rendered_config:
            return jsonify({'success': False, 'error': 'Failed to render template'}), 500

        task_id = celery_device_service.execute_set_config(
            connection_args=device_info['connection_args'],
            config_lines=rendered_config.split('\n'),
            save_config=True
        )

        if task_id:
            save_task_id(task_id, device_name=f"service_redeploy:{service_id}:{service.get('device')}")

        # Update service state
        service['state'] = 'deploying'
        service['task_id'] = task_id
        service['rendered_config'] = rendered_config
        if 'error' in service:
            del service['error']
        save_service_instance(service)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Service redeploy submitted. Task ID: {task_id}'
        })

    except Exception as e:
        log.error(f"Error redeploying service instance: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/delete', methods=['POST'])
@login_required
def delete_template_service(service_id):
    """Delete a template-based service instance - removes config from device first"""
    try:
        from services.device_service import get_device_connection_info as get_conn_info

        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        task_id = None
        delete_template = service.get('delete_template') or service.get('reverse_template')

        # If delete template exists, use it to remove config from device
        if delete_template and service.get('device'):
            log.info(f"Using delete template '{delete_template}' to remove service from device")

            credential_override = {'username': username, 'password': password} if username and password else None
            device_info = get_conn_info(service['device'], credential_override)

            if device_info:
                # Render and deploy delete template via Celery
                template_name = delete_template[:-3] if delete_template.endswith('.j2') else delete_template
                rendered_config = render_j2_template(template_name, service.get('variables', {}))

                if rendered_config:
                    task_id = celery_device_service.execute_set_config(
                        connection_args=device_info['connection_args'],
                        config_lines=rendered_config.split('\n'),
                        save_config=True
                    )

                    if task_id:
                        stack_name = "N/A"
                        if service.get('stack_id'):
                            stack = get_service_stack(service['stack_id'])
                            if stack:
                                stack_name = stack.get('name', 'N/A')

                        service_name = service.get('name', 'N/A')
                        if ' (' in service_name:
                            service_name = service_name.split(' (')[0]

                        job_name = f"stack:DELETE:{stack_name}:{service_name}:{service.get('device', 'N/A')}:{task_id}"
                        save_task_id(task_id, device_name=job_name)

        # Remove service from any stacks that reference it
        stack_id = service.get('stack_id')
        if stack_id:
            stack = get_service_stack(stack_id)
            if stack and 'deployed_services' in stack:
                deployed_services = stack.get('deployed_services', [])
                if service_id in deployed_services:
                    deployed_services.remove(service_id)
                    stack['deployed_services'] = deployed_services
                    save_service_stack(stack)

        # Delete from database
        delete_service_instance(service_id)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Service "{service["name"]}" deleted successfully',
            'stack_id': stack_id
        })

    except Exception as e:
        log.error(f"Error deleting template service: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/check_status', methods=['POST'])
@login_required
def check_service_status(service_id):
    """Check task status and update service state"""
    try:
        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        task_id = service.get('task_id')
        if not task_id:
            return jsonify({'success': False, 'error': 'No task ID found'}), 400

        # Check task status via Celery
        task_result = celery_device_service.get_task_result(task_id)
        task_status = task_result.get('status', 'PENDING')

        # Update service state based on task status
        if task_status == 'SUCCESS':
            service['state'] = 'deployed'
        elif task_status == 'FAILURE':
            service['state'] = 'failed'
            service['error'] = str(task_result.get('error', 'Task failed'))

        save_service_instance(service)

        return jsonify({
            'success': True,
            'state': service['state'],
            'task_status': task_status
        })

    except Exception as e:
        log.error(f"Error checking service status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/validate', methods=['POST'])
@login_required
def validate_service_instance(service_id):
    """Validate that the service configuration exists on the device.

    Supports two modes:
    - use_backup=true (default): Validate against latest config backup (fast, no device connection)
    - use_backup=false: Validate live against device (slower, requires connection)
    """
    try:
        from services.device_service import get_device_connection_info as get_conn_info

        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        if service.get('state') == 'failed':
            return jsonify({'success': False, 'error': f"Cannot validate failed service: {service.get('error', 'Service deployment failed')}"}), 400

        if not service.get('template'):
            return jsonify({'success': False, 'error': 'Service has no template defined'}), 400

        data = request.json or {}
        use_backup = data.get('use_backup', True)  # Default to using backup
        username = data.get('username')
        password = data.get('password')

        # Get validation template
        validation_template = service.get('validation_template') or service.get('template')
        template_lookup = validation_template[:-3] if validation_template.endswith('.j2') else validation_template
        validation_config = render_j2_template(template_lookup, service.get('variables', {}))

        if not validation_config:
            return jsonify({'success': False, 'error': f'Template not found or failed to render: {validation_template}'}), 500

        # Extract patterns to validate
        patterns = [line.strip() for line in validation_config.split('\n') if line.strip()]

        device_name = service['device']

        if use_backup:
            # Try to get latest backup for the device
            backup = db.get_latest_backup_for_device(device_name)

            if backup and backup.get('config_content'):
                # Validate against backup (synchronous, no device connection needed)
                import re
                validations = []
                all_passed = True

                for pattern in patterns:
                    found = bool(re.search(pattern, backup['config_content'], re.MULTILINE))
                    validations.append({'pattern': pattern, 'found': found})
                    if not found:
                        all_passed = False

                # Return immediate result
                return jsonify({
                    'success': True,
                    'validation_source': 'backup',
                    'backup_id': backup.get('backup_id'),
                    'backup_time': backup.get('created_at'),
                    'status': 'success',
                    'validation_status': 'passed' if all_passed else 'failed',
                    'all_passed': all_passed,
                    'validations': validations,
                    'message': f'Validated against backup from {backup.get("created_at", "unknown")}'
                })
            else:
                # No backup available, fall back to live validation
                log.warning(f"No backup found for {device_name}, falling back to live validation")
                use_backup = False

        # Live validation (use_backup=False or no backup available)
        credential_override = {'username': username, 'password': password} if username and password else None
        device_info = get_conn_info(device_name, credential_override)
        if not device_info:
            return jsonify({'success': False, 'error': f'Could not get connection info for device: {device_name}'}), 400

        # Submit validation task via Celery
        task_id = celery_device_service.execute_validate(
            connection_args=device_info['connection_args'],
            expected_patterns=patterns,
            validation_command='show running-config'
        )

        if task_id:
            stack_name = "N/A"
            if service.get('stack_id'):
                stack = get_service_stack(service['stack_id'])
                if stack:
                    stack_name = stack.get('name', 'N/A')

            service_name = service.get('name', 'N/A')
            if ' (' in service_name:
                service_name = service_name.split(' (')[0]

            job_name = f"stack:VALIDATION:{stack_name}:{service_name}:{device_name}:{task_id}"
            save_task_id(task_id, device_name=job_name)

        # Return task_id for async polling
        return jsonify({
            'success': True,
            'validation_source': 'live',
            'task_id': task_id,
            'message': 'Live validation task submitted'
        })

    except Exception as e:
        log.error(f"Error validating service instance: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/sync-states', methods=['POST'])
@login_required
def sync_service_instance_states():
    """Sync service instance states from Celery task status"""
    try:
        updated_count = 0
        failed_count = 0

        all_services = get_all_service_instances()
        deploying_services = [s for s in all_services if s.get('state') == 'deploying']

        log.info(f"Found {len(deploying_services)} services in deploying state")

        for service in deploying_services:
            task_id = service.get('task_id')
            if not task_id:
                continue

            try:
                # Query Celery for task status
                task_result = celery_device_service.get_task_result(task_id)
                task_status = task_result.get('status', 'PENDING').upper()

                log.info(f"Service {service.get('service_id')} task {task_id} status: {task_status}")

                if task_status == 'SUCCESS':
                    service['state'] = 'deployed'
                    service['deployed_at'] = datetime.now().isoformat()
                    save_service_instance(service)
                    updated_count += 1

                elif task_status in ['FAILURE', 'FAILED']:
                    service['state'] = 'failed'
                    service['error'] = str(task_result.get('error', 'Deployment failed'))
                    save_service_instance(service)
                    failed_count += 1

            except Exception as e:
                log.error(f"Error syncing service {service.get('service_id')}: {e}")
                continue

        # Update stack states based on service states
        stacks_updated = set()
        for service in deploying_services:
            stack_id = service.get('stack_id')
            if stack_id and stack_id not in stacks_updated:
                stack_services = [s for s in all_services if s.get('stack_id') == stack_id]
                states = [s.get('state') for s in stack_services]

                if all(state == 'deployed' for state in states):
                    new_state = 'deployed'
                elif any(state == 'failed' for state in states):
                    new_state = 'partial' if any(state == 'deployed' for state in states) else 'failed'
                elif any(state == 'deploying' for state in states):
                    new_state = 'deploying'
                else:
                    new_state = 'pending'

                stack = get_service_stack(stack_id)
                if stack and stack.get('state') != new_state:
                    stack['state'] = new_state
                    db.save_service_stack(stack)
                    stacks_updated.add(stack_id)

        return jsonify({
            'success': True,
            'updated': updated_count,
            'failed': failed_count,
            'stacks_updated': len(stacks_updated),
            'still_deploying': len([s for s in deploying_services if s.get('state') == 'deploying']) - updated_count - failed_count
        })

    except Exception as e:
        log.error(f"Error syncing service states: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

### Service Stack Endpoints ###
# Basic CRUD operations migrated to routes/stacks.py
# Operations below require Celery/device operations and remain here

@app.route('/api/service-stacks/<stack_id>', methods=['DELETE'])
@login_required
def delete_stack(stack_id):
    """Delete a service stack"""
    try:
        stack = get_service_stack(stack_id)

        if not stack:
            return jsonify({'success': False, 'error': 'Service stack not found'}), 404

        # Get credentials from request body for delete templates (if provided)
        data = {}
        try:
            if request.is_json and request.data:
                data = request.json or {}
        except Exception:
            # No JSON body provided, which is fine for simple deletes
            pass

        username = data.get('username')
        password = data.get('password')

        credential_override = None
        if username and password:
            credential_override = {'username': username, 'password': password}
            log.info(f"Using provided credentials for delete operations (user: {username})")

        # Optional: Delete associated service instances and run delete templates
        delete_services = request.args.get('delete_services', 'false').lower() == 'true'
        log.info(f"Delete stack {stack_id}: delete_services={delete_services}, deployed_services={stack.get('deployed_services', [])}")

        deleted_count = 0
        task_ids = []
        if delete_services and 'deployed_services' in stack:
            log.info(f"Processing {len(stack.get('deployed_services', []))} deployed services for deletion")
            for service_id in stack.get('deployed_services', []):
                try:
                    log.info(f"Deleting service {service_id} with delete template")
                    # Run delete template to remove config from devices
                    result = delete_service_instance(service_id, run_delete_template=True, credential_override=credential_override)
                    log.info(f"Delete service result: {result}")
                    if isinstance(result, dict) and result.get('task_id'):
                        task_ids.append(result['task_id'])
                        log.info(f"Added task_id {result['task_id']} to task list")
                    deleted_count += 1
                except Exception as e:
                    log.warning(f"Failed to delete service {service_id}: {e}", exc_info=True)

        delete_service_stack(stack_id)

        return jsonify({
            'success': True,
            'message': f'Service stack "{stack["name"]}" deleted successfully',
            'deleted_services': deleted_count,
            'task_ids': task_ids
        })

    except Exception as e:
        log.error(f"Error deleting service stack: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service-stacks/<stack_id>/deploy', methods=['POST'])
@login_required
def deploy_service_stack(stack_id):
    """Deploy all services in a stack with dependency management"""
    try:
        # Get credentials from request
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Deploy request data: {data.keys() if data else 'empty'}")
        log.info(f"Username from request: {username}, Password present: {bool(password)}")

        credential_override = None
        if username and password:
            credential_override = {'username': username, 'password': password}
            log.info(f"Using provided credentials for stack deployment (user: {username})")
        else:
            log.info(f"No credential override - using device-specific credentials")

        stack = get_service_stack(stack_id)

        if not stack:
            return jsonify({'success': False, 'error': 'Service stack not found'}), 404

        if stack.get('state') == 'deploying':
            return jsonify({'success': False, 'error': 'Stack is already being deployed'}), 400

        # Update stack state
        stack['state'] = 'deploying'
        stack['deploy_started_at'] = datetime.now().isoformat()
        stack['deployed_services'] = []

        # Clear pending changes flag when starting deployment
        if 'has_pending_changes' in stack:
            del stack['has_pending_changes']
        if 'pending_since' in stack:
            del stack['pending_since']

        save_service_stack(stack)

        # Sort services by order
        services = sorted(stack['services'], key=lambda s: s.get('order', 0))

        deployed_service_ids = []
        failed_services = []

        # Deploy services sequentially
        for service_def in services:
            try:
                log.info(f"Deploying service: {service_def}")

                # Check dependencies
                depends_on = service_def.get('depends_on', [])
                if depends_on:
                    # Verify all dependencies are deployed
                    for dep_name in depends_on:
                        dep_deployed = False
                        for deployed_id in deployed_service_ids:
                            deployed_svc = get_service_instance(deployed_id)
                            if deployed_svc and deployed_svc.get('name') == dep_name:
                                if deployed_svc.get('state') != 'deployed':
                                    raise Exception(f"Dependency '{dep_name}' not in deployed state")
                                dep_deployed = True
                                break

                        if not dep_deployed:
                            raise Exception(f"Dependency '{dep_name}' not found or not deployed")

                # Merge shared variables with service-specific variables
                variables = {**stack.get('shared_variables', {}), **service_def.get('variables', {})}

                # Render template once (same config for all devices)
                template_name = service_def.get('template')
                log.info(f"Template name from service_def: '{template_name}'")

                if not template_name:
                    raise Exception(f"Service '{service_def.get('name')}' has no template specified")

                # Strip .j2 extension if present for consistency
                if template_name.endswith('.j2'):
                    template_name = template_name[:-3]

                # Get template metadata (validation and delete templates)
                template_metadata = get_template_metadata(template_name) or {}

                # Use template name without .j2 extension (templates stored without extension)
                log.info(f"Deploying template '{template_name}' with variables: {variables}")

                # Handle both single device (old format) and multiple devices (new format)
                devices = service_def.get('devices', [service_def.get('device')]) if service_def.get('devices') else [service_def.get('device')]

                # Deploy to each device (continue even if some fail)
                service_failed_devices = []
                service_succeeded_devices = []
                service_skipped_devices = []

                for device_name in devices:
                    if not device_name:
                        continue

                    try:
                        # Check if device already has this exact template+variables deployed
                        existing_service = None
                        if stack.get('deployed_services'):
                            for existing_id in stack.get('deployed_services', []):
                                existing = get_service_instance(existing_id)
                                if existing and existing.get('device') == device_name and existing.get('name', '').startswith(service_def['name']):
                                    existing_service = existing
                                    break

                        # Compare template and variables with existing service
                        # Skip if same template, same variables, and already deployed
                        if existing_service and \
                           existing_service.get('template') == template_name and \
                           existing_service.get('variables') == variables and \
                           existing_service.get('state') == 'deployed':
                            log.info(f"Skipping {device_name} - template and variables unchanged")
                            service_skipped_devices.append(device_name)
                            # Keep the existing service instance
                            deployed_service_ids.append(existing_service['service_id'])
                            service_succeeded_devices.append(device_name)
                            continue

                        # Get device connection info from Netbox
                        log.info(f"Getting connection info for device: {device_name}")
                        device_info = get_device_connection_info(device_name, credential_override)
                        if not device_info:
                            raise Exception(f"Could not get connection info for device '{device_name}'")

                        log.info(f"Deploying template to {device_name} via Celery")

                        # Render template locally and deploy via Celery
                        rendered_config = render_j2_template(template_name, variables)
                        if not rendered_config:
                            raise Exception(f"Failed to render template '{template_name}'")

                        task_id = celery_device_service.execute_set_config(
                            connection_args=device_info['connection_args'],
                            config_lines=rendered_config.split('\n'),
                            save_config=True
                        )

                        log.info(f"Got task_id: {task_id}")

                        # Save task to history for monitoring with standardized format
                        # Format: stack:DEPLOY:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                        job_name = f"stack:DEPLOY:{stack.get('name')}:{service_def['name']}:{device_name}:{task_id}"
                        save_task_id(task_id, device_name=job_name)

                        # Create service instance record in 'deploying' state
                        service_instance = {
                            'service_id': str(uuid.uuid4()),
                            'name': f"{service_def['name']} ({device_name})",
                            'template': template_name,
                            'validation_template': template_metadata.get('validation_template'),
                            'delete_template': template_metadata.get('delete_template'),
                            'device': device_name,
                            'variables': variables,
                            'rendered_config': rendered_config,
                            'pre_checks': service_def.get('pre_checks'),
                            'post_checks': service_def.get('post_checks'),
                            'state': 'deploying',
                            'task_id': task_id,
                            'stack_id': stack_id,
                            'stack_order': service_def.get('order', 0),
                            'created_at': datetime.now().isoformat()
                        }

                        save_service_instance(service_instance)
                        deployed_service_ids.append(service_instance['service_id'])
                        service_succeeded_devices.append(device_name)

                        log.info(f"Deployed service '{service_def['name']}' to device '{device_name}' in stack '{stack_id}'")

                    except Exception as device_error:
                        log.error(f"Failed to deploy service '{service_def['name']}' to device '{device_name}': {device_error}")
                        service_failed_devices.append({
                            'device': device_name,
                            'error': str(device_error)
                        })

                        # Create failed service instance record
                        failed_service_instance = {
                            'service_id': str(uuid.uuid4()),
                            'name': f"{service_def['name']} ({device_name})",
                            'template': template_name,
                            'validation_template': template_metadata.get('validation_template'),
                            'delete_template': template_metadata.get('delete_template'),
                            'device': device_name,
                            'variables': variables,
                            'state': 'failed',
                            'error': str(device_error),
                            'stack_id': stack_id,
                            'stack_order': service_def.get('order', 0),
                            'created_at': datetime.now().isoformat()
                        }

                        save_service_instance(failed_service_instance)
                        deployed_service_ids.append(failed_service_instance['service_id'])

                        # Continue to next device instead of stopping
                        continue

                # If this service had any failures, track them
                if service_failed_devices:
                    failed_services.append({
                        'name': service_def['name'],
                        'failed_devices': service_failed_devices,
                        'succeeded_devices': service_succeeded_devices,
                        'skipped_devices': service_skipped_devices,
                        'error': f"{len(service_failed_devices)} of {len(devices)} devices failed"
                    })
                # Track skipped devices even if no failures
                elif service_skipped_devices:
                    # Add to a separate tracking list for informational purposes
                    if not hasattr(stack, '_skipped_info'):
                        stack['_skipped_info'] = []
                    stack['_skipped_info'].append({
                        'name': service_def['name'],
                        'skipped_devices': service_skipped_devices
                    })

            except Exception as e:
                # This catches template-level errors (template not found, rendering errors, etc.)
                log.error(f"Failed to deploy service '{service_def['name']}': {e}")
                failed_services.append({
                    'name': service_def['name'],
                    'error': str(e),
                    'failed_devices': [],
                    'succeeded_devices': []
                })
                # Continue to next service instead of stopping
                continue

        # Update stack state
        # Since services are submitted to Celery queue and may still be deploying,
        # the stack state reflects job submission, not completion
        if failed_services:
            # Check if we have ANY successful job submissions
            has_successes = len(deployed_service_ids) > 0
            if has_successes:
                stack['state'] = 'partial'  # Some jobs submitted, some failed
            else:
                stack['state'] = 'failed'  # All jobs failed to submit
            stack['deployment_errors'] = failed_services
        else:
            # All jobs successfully submitted to Celery queue
            stack['state'] = 'deploying'  # Jobs are queued in Celery

        stack['deployed_services'] = deployed_service_ids
        stack['deploy_completed_at'] = datetime.now().isoformat()

        # Count skipped devices across all services
        total_skipped = 0
        skipped_info = stack.get('_skipped_info', [])
        for skip_data in skipped_info:
            total_skipped += len(skip_data.get('skipped_devices', []))
        # Also count skipped in failed services
        for failed in failed_services:
            total_skipped += len(failed.get('skipped_devices', []))

        # Clean up temporary tracking
        if '_skipped_info' in stack:
            del stack['_skipped_info']

        save_service_stack(stack)

        # Build detailed message
        if not failed_services:
            if total_skipped > 0:
                message = f'Stack deployment completed - {len(deployed_service_ids)} services deployed ({total_skipped} devices skipped - no changes)'
            else:
                message = f'Stack deployment completed successfully - {len(deployed_service_ids)} services deployed'
        elif len(deployed_service_ids) > 0:
            skip_msg = f', {total_skipped} devices skipped' if total_skipped > 0 else ''
            message = f'Stack deployment partially completed - {len(deployed_service_ids)} services deployed, {len(failed_services)} services had failures{skip_msg}'
        else:
            message = f'Stack deployment failed - no services deployed'

        return jsonify({
            'success': len(failed_services) == 0,
            'deployed_count': len(deployed_service_ids),
            'failed_count': len(failed_services),
            'skipped_count': total_skipped,
            'deployed_services': deployed_service_ids,
            'failed_services': failed_services,
            'message': message
        })

    except Exception as e:
        log.error(f"Error deploying service stack: {e}", exc_info=True)

        # Update stack state to failed
        try:
            stack = get_service_stack(stack_id)
            if stack:
                stack['state'] = 'failed'
                stack['deployment_errors'] = [{'error': str(e)}]
                save_service_stack(stack)
        except:
            pass

        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service-stacks/<stack_id>/validate', methods=['POST'])
@login_required
def validate_service_stack(stack_id):
    """Validate all services in a stack by calling individual service validation"""
    try:
        stack = get_service_stack(stack_id)

        if not stack:
            return jsonify({'success': False, 'error': 'Service stack not found'}), 404

        if not stack.get('deployed_services'):
            return jsonify({'success': False, 'error': 'Stack has no deployed services'}), 400

        # Get credentials from request
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Stack validation RAW request data: {data}")
        log.info(f"Stack validation credentials - username: {username}, has_password: {bool(password)}")

        validation_results = []
        all_valid = True

        log.info(f"Validating stack '{stack_id}' with {len(stack.get('deployed_services', []))} services")

        # Validate each deployed service using the service validation endpoint
        for service_id in stack.get('deployed_services', []):
            service = get_service_instance(service_id)

            if not service:
                validation_results.append({
                    'service_id': service_id,
                    'service_name': 'Unknown',
                    'valid': False,
                    'message': 'Service not found'
                })
                all_valid = False
                continue

            try:
                log.info(f"Validating service '{service.get('name')}' ({service_id}) with username={username}")

                # Build validation request context and push it
                log.info(f"Creating test request context for {service_id}")
                ctx = app.test_request_context(
                    f'/api/services/instances/{service_id}/validate',
                    method='POST',
                    json={'username': username, 'password': password},
                    content_type='application/json'
                )
                log.info(f"Pushing context for {service_id}")
                ctx.push()

                try:
                    # Set up JWT user in request context for authentication
                    from flask import request as flask_request
                    flask_request.jwt_user = get_current_user()
                    log.info(f"Set request jwt_user to: {flask_request.jwt_user}")

                    # Call the service validation function directly
                    log.info(f"Calling validate_service_instance for {service_id}")
                    response = validate_service_instance(service_id)
                    log.info(f"Got response type: {type(response)}")
                    log.info(f"Response is tuple: {isinstance(response, tuple)}")

                    # Handle None response
                    if response is None:
                        raise Exception("Validation returned None - check service instance state")

                    # Extract JSON data from response
                    response_data = None
                    if isinstance(response, tuple):
                        # Flask response with status code: (response, status_code)
                        response_obj = response[0]
                        status_code = response[1] if len(response) > 1 else 200
                        log.info(f"Tuple response: status_code={status_code}, obj_type={type(response_obj)}")
                        log.info(f"Response data: {response_obj.get_data(as_text=True)[:200] if hasattr(response_obj, 'get_data') else 'no get_data'}")
                        try:
                            response_data = response_obj.get_json(force=True) if hasattr(response_obj, 'get_json') else response_obj
                        except Exception as e:
                            log.error(f"Failed to extract JSON from tuple response: {type(response_obj)}, error: {e}")
                            raise Exception(f"Invalid response format from validation: {type(response_obj)}")
                    else:
                        # Direct Flask response object
                        log.info(f"Response status: {response.status_code if hasattr(response, 'status_code') else 'unknown'}")
                        log.info(f"Response data: {response.get_data(as_text=True)[:200] if hasattr(response, 'get_data') else 'no get_data'}")
                        if hasattr(response, 'get_json'):
                            log.info(f"Calling get_json() on response")
                            # Force processing of the response
                            response_data = response.get_json(force=True)
                            log.info(f"Got response_data: {response_data}")
                        elif hasattr(response, 'json'):
                            response_data = response.json
                        else:
                            log.error(f"Response type: {type(response)}, Response: {response}")
                            raise Exception(f"Response object has no get_json method: {type(response)}")

                    # Check if we got valid response data
                    if not response_data:
                        raise Exception("Failed to get JSON response from validation")

                    if response_data.get('success'):
                        is_valid = response_data.get('valid', False)
                        validation_results.append({
                            'service_id': service_id,
                            'service_name': service.get('name'),
                            'valid': is_valid,
                            'message': response_data.get('message', ''),
                            'missing_lines': response_data.get('missing_lines', [])
                        })
                        if not is_valid:
                            all_valid = False
                    else:
                        raise Exception(response_data.get('error', 'Validation failed'))
                finally:
                    ctx.pop()

            except Exception as e:
                import traceback
                log.error(f"Error validating service {service_id}: {e}")
                log.error(f"Traceback: {traceback.format_exc()}")
                validation_results.append({
                    'service_id': service_id,
                    'service_name': service.get('name'),
                    'valid': False,
                    'message': f'Validation error: {str(e)}'
                })
                all_valid = False

        # Update stack validation status
        stack['last_validated'] = datetime.now().isoformat()
        stack['validation_status'] = 'valid' if all_valid else 'invalid'
        save_service_stack(stack)

        log.info(f"Stack validation complete: {len(validation_results)} services validated, all_valid={all_valid}")

        return jsonify({
            'success': True,
            'all_valid': all_valid,
            'results': validation_results,
            'message': f'Stack validation {"passed" if all_valid else "failed"}'
        })

    except Exception as e:
        log.error(f"Error validating service stack: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Scheduled Stack Operations Endpoints ====================
# Basic CRUD operations migrated to routes/stacks.py
# Scheduled config operations (config_deploy) remain here as they require complex device operations

@app.route('/api/scheduled-config-operations', methods=['POST'])
@login_required
def create_scheduled_config_operation():
    """Create a scheduled config deployment operation"""
    try:
        from db import create_scheduled_operation as db_create_schedule
        import uuid
        from datetime import datetime as dt, timedelta
        import json

        data = request.json
        operation_type = data.get('operation_type')  # should be 'config_deploy'
        schedule_type = data.get('schedule_type')
        scheduled_time = data.get('scheduled_time')
        day_of_week = data.get('day_of_week')
        day_of_month = data.get('day_of_month')
        config_data = data.get('config')  # deployment configuration

        if not all([operation_type, schedule_type, scheduled_time, config_data]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        if operation_type != 'config_deploy':
            return jsonify({'success': False, 'error': 'Invalid operation_type'}), 400

        if schedule_type not in ['once', 'daily', 'weekly', 'monthly']:
            return jsonify({'success': False, 'error': 'Invalid schedule_type'}), 400

        schedule_id = str(uuid.uuid4())
        username = get_current_user()

        # Calculate next_run time
        now = dt.now()
        if schedule_type == 'once':
            # Parse ISO datetime in local timezone (no timezone conversion)
            next_run = dt.fromisoformat(scheduled_time.replace('Z', ''))
            # Reject scheduling in the past for one-time operations
            if next_run <= now:
                return jsonify({
                    'success': False,
                    'error': f'Cannot schedule operation in the past. Scheduled time: {next_run.strftime("%Y-%m-%d %H:%M")}, Current time: {now.strftime("%Y-%m-%d %H:%M")}'
                }), 400
        else:
            time_parts = scheduled_time.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])

            if schedule_type == 'daily':
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
            elif schedule_type == 'weekly':
                days_ahead = day_of_week - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
                if next_run <= now:
                    next_run += timedelta(weeks=1)
            elif schedule_type == 'monthly':
                next_run = now.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    if now.month == 12:
                        next_run = next_run.replace(year=now.year + 1, month=1)
                    else:
                        next_run = next_run.replace(month=now.month + 1)

        db_create_schedule(
            schedule_id=schedule_id,
            stack_id=None,  # No stack for config deployments
            operation_type=operation_type,
            schedule_type=schedule_type,
            scheduled_time=scheduled_time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            config_data=json.dumps(config_data),
            created_by=username
        )

        # Update next_run
        from db import update_scheduled_operation
        update_scheduled_operation(schedule_id, next_run=next_run.isoformat())

        log.info(f"Created scheduled config operation: {schedule_id}")
        return jsonify({'success': True, 'schedule_id': schedule_id})

    except Exception as e:
        log.error(f"Error creating scheduled config operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# WORKFLOW API ENDPOINTS (YAML-based MOP engine)
# ============================================================

@app.route('/api/step-types-introspect', methods=['GET'])
@login_required
def get_step_types_introspect_api():
    """Get step types from database for visual builder"""
    try:
        # Get all enabled step types from database
        step_types = db.get_all_step_types()

        # Transform to format expected by visual builder
        result = []
        for st in step_types:
            params = []
            # Convert parameters_schema to visual builder format
            schema = st.get('parameters_schema', {})
            for param_name, param_def in schema.items():
                params.append({
                    'name': param_name,
                    'type': param_def.get('type', 'string'),
                    'required': param_def.get('required', False),
                    'description': param_def.get('description', ''),
                    'default': param_def.get('default')
                })

            result.append({
                'id': st['step_type_id'],
                'name': st['name'],
                'description': st.get('description', ''),
                'icon': st.get('icon', 'cog'),
                'category': st.get('category', 'General'),
                'action_type': st.get('action_type', 'get_config'),
                'parameters': params
            })

        return jsonify({'success': True, 'step_types': result})
    except Exception as e:
        log.error(f"Error getting step types: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


### MOP Endpoints ###
# Basic CRUD operations migrated to routes/mop.py
# Execute operation requires MOP engine and device connections

@app.route('/api/mops/<mop_id>/execute', methods=['POST'])
@login_required
def execute_mop_api(mop_id):
    """Execute a workflow"""
    try:
        # Get MOP from database
        with db.get_db() as session_db:
            result = session_db.execute(text('SELECT * FROM mops WHERE mop_id = :mop_id'), {'mop_id': mop_id})
            MOP_row = result.fetchone()

            if not MOP_row:
                return jsonify({'success': False, 'error': 'MOP not found'}), 404

            MOP = dict(MOP_row._mapping)

        # Create execution record
        execution_id = str(uuid.uuid4())

        with db.get_db() as session_db:
            session_db.execute(text('''
                INSERT INTO mop_executions
                (execution_id, mop_id, status, started_at, started_by)
                VALUES (:execution_id, :mop_id, 'running', CURRENT_TIMESTAMP, :started_by)
            '''), {'execution_id': execution_id, 'mop_id': mop_id, 'started_by': get_current_user()})

        # Execute MOP asynchronously
        def run_mop():
            from mop_engine import MOPEngine

            try:
                # Build context with device information
                context = {'devices': {}}

                # Get device info from Netbox if devices specified
                # First try to get from database field (JSONB returns as list directly)
                devices_data = MOP.get('devices', [])
                # Handle both string (legacy) and list (JSONB) formats
                if isinstance(devices_data, str):
                    devices = json.loads(devices_data) if devices_data else []
                else:
                    devices = devices_data if devices_data else []

                # If no devices in database, parse from YAML
                if not devices:
                    import yaml as yaml_lib
                    try:
                        yaml_data = yaml_lib.safe_load(MOP['yaml_content'])
                        devices = yaml_data.get('devices', [])
                        log.info(f"Parsed {len(devices)} devices from YAML")
                    except Exception as e:
                        log.error(f"Could not parse YAML to extract devices: {e}")
                        devices = []

                log.info(f"MOP has {len(devices)} devices: {devices}")

                if devices:
                    for device_name in devices:
                        log.info(f"Loading device info for: {device_name}")
                        try:
                            # Get device connection info (includes IP, platform, etc.)
                            device_conn_info = get_device_connection_info(device_name)
                            log.info(f"get_device_connection_info returned: {device_conn_info is not None}")

                            if device_conn_info:
                                # Extract relevant info for MOP context
                                # Match the format expected by execute_getconfig_step
                                conn_args = device_conn_info.get('connection_args', {})
                                device_info = device_conn_info.get('device_info', {})

                                context['devices'][device_name] = {
                                    'name': device_name,
                                    'ip_address': conn_args.get('host', device_name),
                                    'primary_ip4': conn_args.get('host', device_name),
                                    'platform': conn_args.get('device_type', 'cisco_ios'),
                                    'site': device_info.get('site'),
                                    'nornir_platform': conn_args.get('device_type')
                                }
                                log.info(f"SUCCESS: Loaded device {device_name}: ip={conn_args.get('host')}, platform={conn_args.get('device_type')}")
                            else:
                                log.error(f"FAILED: get_device_connection_info returned None for {device_name}")
                                context['devices'][device_name] = {'name': device_name}

                        except Exception as e:
                            log.error(f"EXCEPTION loading device {device_name}: {e}", exc_info=True)
                            context['devices'][device_name] = {'name': device_name}

                log.info(f"MOP context devices: {list(context['devices'].keys())}")

                # Execute MOP
                engine = MOPEngine(MOP['yaml_content'], context)
                result = engine.execute()

                # Update execution record
                with db.get_db() as session_db:
                    session_db.execute(text('''
                        UPDATE mop_executions
                        SET status = :status, execution_log = :execution_log, context = :context, completed_at = CURRENT_TIMESTAMP
                        WHERE execution_id = :execution_id
                    '''), {
                        'status': result['status'],
                        'execution_log': json.dumps(result.get('execution_log', [])),
                        'context': json.dumps(result.get('context', {})),
                        'execution_id': execution_id
                    })

                log.info(f"MOP {mop_id} execution {execution_id} completed with status: {result['status']}")

            except Exception as e:
                log.error(f"Error executing MOP: {e}", exc_info=True)

                # Update execution record with error
                with db.get_db() as session_db:
                    session_db.execute(text('''
                        UPDATE mop_executions
                        SET status = 'failed', error = :error, completed_at = CURRENT_TIMESTAMP
                        WHERE execution_id = :execution_id
                    '''), {'error': str(e), 'execution_id': execution_id})

        # Start background thread
        import threading
        thread = threading.Thread(target=run_mop)
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'execution_id': execution_id})

    except Exception as e:
        log.error(f"Error starting MOP execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# MOP execution read operations migrated to routes/mop.py
# get_mop_executions, get_mop_execution_details, get_running_executions

@app.route('/api/task/<task_id>/result', methods=['GET'])
@login_required
def get_task_result_api(task_id):
    """Get task result from Celery"""
    try:
        result = celery_device_service.get_task_result(task_id)
        return jsonify({
            'status': 'success',
            'data': {
                'task_id': task_id,
                'task_status': result.get('status', 'PENDING'),
                'task_result': result.get('result', {})
            }
        })
    except Exception as e:
        log.error(f"Error getting task result: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Helper functions for executing different step types

def execute_getconfig_step(step, context=None, step_index=0):
    """Execute a getconfig step - reuses existing deploy_getconfig function

    Args:
        step: Step configuration dict
        context: Dict of previous step results for reference
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        devices = step['devices']
        command = config.get('command', 'show running-config')

        # Get default credentials
        settings = db.get_all_settings()
        default_username = settings.get('default_username', '')
        default_password = settings.get('default_password', '')

        # Use provided credentials or defaults
        username = config.get('username') or default_username
        password = config.get('password') or default_password

        if not username or not password:
            return {'status': 'error', 'error': 'No credentials provided'}

        library = config.get('library', 'netmiko')
        results = []

        # Step 1: Submit all tasks in parallel (non-blocking)
        task_submissions = []  # List of (device_name, task_id) tuples

        log.info(f"Submitting tasks for {len(devices)} devices in parallel")

        for device_name in devices:
            try:
                # Get device info from MOP context (pre-loaded and cached)
                device_info = None
                if context and 'devices' in context and device_name in context['devices']:
                    device_info = context['devices'][device_name]
                    log.info(f"Using cached device info for {device_name} from MOP context")

                if not device_info:
                    log.error(f"Device {device_name} not found in MOP context")
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'Device not found in MOP context'
                    })
                    continue

                # Get device connection parameters from cached context
                nornir_platform = device_info.get('platform')
                ip_address = device_info.get('ip_address', device_name)

                log.info(f"Using device {device_name}: ip={ip_address}, platform={nornir_platform}")

                if not ip_address:
                    log.error(f"No IP address for device {device_name}, device_info={device_info}")
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'No IP address available for device'
                    })
                    continue

                # Build payload in the format expected by deploy_getconfig
                payload = {
                    'connection_args': {
                        'device_type': nornir_platform or 'cisco_ios',
                        'host': ip_address,
                        'username': username,
                        'password': password,
                        'timeout': 10
                    },
                    'command': command,
                    'queue_strategy': 'pinned'
                }

                # Add cache if enabled
                if config.get('enable_cache'):
                    payload['cache'] = {
                        'enabled': True,
                        'ttl': 300
                    }

                # Add parsing options
                if config.get('use_textfsm') or config.get('use_ttp'):
                    payload['args'] = {}
                    if config.get('use_textfsm'):
                        payload['args']['use_textfsm'] = True
                    if config.get('use_ttp'):
                        payload['args']['use_ttp'] = True
                        if config.get('ttp_template'):
                            payload['args']['ttp_template'] = config['ttp_template']

                # Execute via Celery
                log.info(f"Sending getconfig for {device_name} via Celery")

                task_id = celery_device_service.execute_get_config(
                    connection_args=payload['connection_args'],
                    command=command,
                    use_textfsm=config.get('use_textfsm', False)
                )

                # Save task ID to history
                if task_id:
                    save_task_id(task_id, device_name=f"mop:STEP{step_index+1}-{step.get('step_name', 'unknown')}-:{device_name}")
                    task_submissions.append((device_name, task_id, device_info))
                    log.info(f"Submitted task {task_id} for {device_name}")
                else:
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'No task_id returned from Celery'
                    })

            except Exception as device_error:
                log.error(f"Error submitting task for {device_name}: {device_error}")
                results.append({
                    'device': device_name,
                    'status': 'error',
                    'error': str(device_error)
                })

        # Step 2: Poll all submitted tasks in parallel
        log.info(f"Polling {len(task_submissions)} tasks in parallel")

        import time
        import sys
        max_wait = 300  # 5 minutes max
        poll_interval = 2  # Poll every 2 seconds
        start_time = time.time()

        # Track completion status for each task
        task_states = {task_id: {'status': 'pending', 'output': None, 'device': device_name, 'info': device_info}
                      for device_name, task_id, device_info in task_submissions}

        while time.time() - start_time < max_wait:
            all_complete = True

            for task_id, state in task_states.items():
                if state['status'] in ['SUCCESS', 'FAILED', 'FAILURE', 'FINISHED', 'TIMEOUT', 'ERROR']:
                    continue  # Already in final state

                all_complete = False

                try:
                    # Poll Celery for task status
                    task_result = celery_device_service.get_task_result(task_id)
                    task_status = task_result.get('status', 'PENDING').upper()
                    task_output = task_result.get('result')

                    # Check for completion states (handle both Celery states and result statuses)
                    if task_status in ['SUCCESS', 'FAILURE', 'FAILED']:
                        log.info(f"Task {task_id} for {state['device']} completed with status: {task_status}")
                        state['status'] = task_status
                        state['output'] = task_output

                except Exception as e:
                    log.error(f"Error polling task {task_id}: {e}", exc_info=True)
                    state['status'] = 'ERROR'
                    state['error'] = str(e)

            if all_complete:
                log.info("All tasks completed")
                break

            time.sleep(poll_interval)

        # Build results from task states
        for task_id, state in task_states.items():
            if state['status'] not in ['SUCCESS', 'FAILED', 'FAILURE', 'FINISHED', 'ERROR']:
                log.error(f"Task {task_id} did not complete within {max_wait}s, final status: {state['status']}")
                state['status'] = 'TIMEOUT'

            results.append({
                'device': state['device'],
                'status': 'success' if state['status'] in ['SUCCESS', 'FINISHED'] else 'error',
                'task_id': task_id,
                'task_status': state['status'],
                'output': state.get('output'),
                'error': state.get('error')
            })

        # Return combined results
        task_ids = [r['task_id'] for r in results if r.get('task_id')]
        return {
            'status': 'success' if task_ids else 'error',
            'data': results,
            'task_id': task_ids[0] if task_ids else None  # Return first task ID for simplicity
        }

    except Exception as e:
        log.error(f"Error executing getconfig step: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_setconfig_step(step, context=None, step_index=0):
    """Execute a setconfig step - reuses existing deploy_setconfig logic

    Args:
        step: Step configuration dict
        context: Dict of previous step results for reference (MOP context)
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        devices = step['devices']
        commands_template = config.get('commands', '')

        # Get default credentials
        settings = db.get_all_settings()
        default_username = settings.get('default_username', '')
        default_password = settings.get('default_password', '')

        # Use provided credentials or defaults
        username = config.get('username') or default_username
        password = config.get('password') or default_password

        if not username or not password:
            return {'status': 'error', 'error': 'No credentials provided'}

        library = config.get('library', 'netmiko')
        save_to_variable = config.get('save_to_variable')
        results = []

        # Execute for each device
        for device_name in devices:
            try:
                # Get device info from MOP context (pre-loaded and cached)
                device_info = None
                if context and 'devices' in context and device_name in context['devices']:
                    device_info = context['devices'][device_name]
                    log.info(f"Using cached device info for {device_name} from MOP context")

                if not device_info:
                    log.error(f"Device {device_name} not found in MOP context")
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'Device not found in MOP context'
                    })
                    continue

                # Get device connection parameters from cached context
                nornir_platform = device_info.get('platform')
                ip_address = device_info.get('ip_address', device_name)

                log.info(f"Using device {device_name}: ip={ip_address}, platform={nornir_platform}")

                if not ip_address:
                    log.error(f"No IP address for device {device_name}")
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'No IP address available for device'
                    })
                    continue

                # Substitute variables in commands
                commands_str = commands_template.replace('{{device_name}}', device_name)

                # Substitute other device variables
                for key, value in device_info.items():
                    if isinstance(value, str):
                        commands_str = commands_str.replace(f'{{{{{key}}}}}', value)

                commands = commands_str.split('\n')

                # Build payload
                payload = {
                    'connection_args': {
                        'device_type': nornir_platform or 'cisco_ios',
                        'host': ip_address,
                        'username': username,
                        'password': password,
                        'timeout': 10
                    },
                    'commands': commands,
                    'queue_strategy': 'pinned',
                    'dry_run': config.get('dry_run', False)
                }

                # Add pre/post checks if provided
                if config.get('pre_check_command'):
                    payload['pre_check'] = {
                        'command': config['pre_check_command'],
                        'match': config.get('pre_check_match', '')
                    }
                if config.get('post_check_command'):
                    payload['post_check'] = {
                        'command': config['post_check_command'],
                        'match': config.get('post_check_match', '')
                    }

                # Execute via Celery
                log.info(f"Sending setconfig for {device_name} via Celery")

                task_id = celery_device_service.execute_set_config(
                    connection_args=payload['connection_args'],
                    config_lines=commands,
                    save_config=not config.get('dry_run', False)
                )

                # Save task ID to history
                if task_id:
                    save_task_id(task_id, device_name=f"mop:STEP{step_index+1}-{step.get('step_name', 'unknown')}-:{device_name}")

                results.append({
                    'device': device_name,
                    'status': 'submitted' if task_id else 'error',
                    'task_id': task_id
                })

            except Exception as device_error:
                log.error(f"Error executing setconfig for {device_name}: {device_error}")
                results.append({
                    'device': device_name,
                    'status': 'error',
                    'error': str(device_error)
                })

        # Return combined results
        task_ids = [r['task_id'] for r in results if r.get('task_id')]
        return {
            'status': 'success' if task_ids else 'error',
            'data': results,
            'task_id': task_ids[0] if task_ids else None
        }

    except Exception as e:
        log.error(f"Error executing setconfig step: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_template_step(step, context=None, step_index=0):
    """Execute a template deployment step via Celery"""
    try:
        from services.device_service import get_device_connection_info as get_conn_info

        config = step['config']
        devices = step['devices']

        template_name = config.get('template')
        if not template_name:
            return {'status': 'error', 'error': 'Template name is required'}

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        # Get template from database
        template_content = db.get_template_content(template_name)
        if not template_content:
            return {'status': 'error', 'error': f'Template not found: {template_name}'}

        variables = config.get('variables', {})
        rendered_config = render_j2_template(template_name, variables)
        if not rendered_config:
            return {'status': 'error', 'error': 'Failed to render template'}

        # Get credentials
        settings = db.get_all_settings()
        username = config.get('username') or settings.get('default_username', '')
        password = config.get('password') or settings.get('default_password', '')

        results = []
        for device_name in devices:
            try:
                credential_override = {'username': username, 'password': password} if username and password else None
                device_info = get_conn_info(device_name, credential_override)

                if not device_info:
                    results.append({'device': device_name, 'status': 'error', 'error': 'Device not found'})
                    continue

                task_id = celery_device_service.execute_set_config(
                    connection_args=device_info['connection_args'],
                    config_lines=rendered_config.split('\n'),
                    save_config=not config.get('dry_run', False)
                )

                if task_id:
                    save_task_id(task_id, device_name=f"mop:STEP{step_index+1}-{step.get('step_name', 'unknown')}-:{device_name}")

                results.append({'device': device_name, 'status': 'success', 'task_id': task_id})

            except Exception as e:
                results.append({'device': device_name, 'status': 'error', 'error': str(e)})

        task_ids = [r['task_id'] for r in results if r.get('task_id')]
        return {
            'status': 'success' if task_ids else 'error',
            'data': results,
            'task_id': task_ids[0] if task_ids else None
        }

    except Exception as e:
        log.error(f"Error executing template step: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_api_step(step, mop_context=None, step_index=0):
    """Execute an API call step

    Args:
        step: Step configuration dict (already has variables substituted)
        mop_context: Device-centric MOP context
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        resource_id = config.get('resource_id')
        endpoint_template = config.get('endpoint', '')
        method = config.get('method', 'GET')
        body_template = config.get('body', '')
        devices = step.get('devices', [])
        save_to_variable = config.get('save_to_variable')

        if not resource_id or not endpoint_template:
            return {'status': 'error', 'error': 'API resource and endpoint are required'}

        # Get the resource
        resource = db.get_api_resource(resource_id)
        if not resource:
            return {'status': 'error', 'error': 'API resource not found'}

        base_url = resource['base_url'].rstrip('/')

        # Build headers based on auth type
        headers = {}
        auth_type = resource.get('auth_type', 'none')

        if auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {resource['auth_token']}"
        elif auth_type == 'api_key':
            headers['X-API-Key'] = resource['auth_token']
        elif auth_type == 'basic':
            import base64
            credentials = f"{resource['auth_username']}:{resource['auth_password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers['Authorization'] = f"Basic {encoded}"

        results = []

        # If no devices specified, make a single API call
        if not devices or len(devices) == 0:
            # Substitute variables from context (not device-specific)
            endpoint = endpoint_template
            body = body_template

            # Build full URL
            clean_endpoint = endpoint if endpoint.startswith('/') else '/' + endpoint
            url = base_url + clean_endpoint

            # Prepare request data
            request_data = None
            if body:
                try:
                    request_data = json.loads(body)
                    headers['Content-Type'] = 'application/json'
                except json.JSONDecodeError as e:
                    return {'status': 'error', 'error': f'Invalid JSON body: {str(e)}'}

            # Make the API call
            log.info(f"Executing API step: {method} {url}")
            response = requests.request(
                method,
                url,
                headers=headers,
                json=request_data,
                timeout=30
            )

            response.raise_for_status()
            result_data = response.json() if response.content else {}

            results.append({
                'api': url,
                'status': 'success',
                'output': result_data,
                'status_code': response.status_code
            })

        # If devices are specified, make API calls for each device
        else:
            for device_name in devices:
                try:
                    # Get device info from context
                    device_info = {}
                    if mop_context and 'devices' in mop_context and device_name in mop_context['devices']:
                        device_info = mop_context['devices'][device_name]

                    # Substitute {{device_name}} and other device variables
                    endpoint = endpoint_template.replace('{{device_name}}', device_name)
                    body = body_template.replace('{{device_name}}', device_name)

                    # Substitute other device variables like {{site}}, {{platform}}, etc.
                    for key, value in device_info.items():
                        if isinstance(value, str):
                            endpoint = endpoint.replace(f'{{{{{key}}}}}', value)
                            body = body.replace(f'{{{{{key}}}}}', value)

                    # Build full URL
                    clean_endpoint = endpoint if endpoint.startswith('/') else '/' + endpoint
                    url = base_url + clean_endpoint

                    # Prepare request data
                    request_data = None
                    if body:
                        try:
                            request_data = json.loads(body)
                            headers['Content-Type'] = 'application/json'
                        except json.JSONDecodeError as e:
                            results.append({
                                'device': device_name,
                                'status': 'error',
                                'error': f'Invalid JSON body: {str(e)}'
                            })
                            continue

                    # Make the API call
                    log.info(f"Executing API step for {device_name}: {method} {url}")
                    response = requests.request(
                        method,
                        url,
                        headers=headers,
                        json=request_data,
                        timeout=30
                    )

                    response.raise_for_status()
                    result_data = response.json() if response.content else {}

                    # Store result in device context if save_to_variable is specified
                    if save_to_variable and mop_context and 'devices' in mop_context:
                        if device_name in mop_context['devices']:
                            mop_context['devices'][device_name][save_to_variable] = result_data

                    results.append({
                        'device': device_name,
                        'api': url,
                        'status': 'success',
                        'output': result_data,
                        'status_code': response.status_code
                    })

                except requests.RequestException as e:
                    log.error(f"Error executing API call for {device_name}: {e}")
                    results.append({
                        'device': device_name,
                        'api': url if 'url' in locals() else endpoint_template,
                        'status': 'error',
                        'error': str(e)
                    })
                except Exception as e:
                    log.error(f"Error processing API call for {device_name}: {e}")
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': str(e)
                    })

        return {
            'status': 'success',
            'data': results
        }

    except Exception as e:
        log.error(f"Error executing API step: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_code_step(step, mop_context=None, step_index=0):
    """Execute a code/script step for data processing in a sandboxed environment

    Args:
        step: Step configuration dict
        mop_context: Device-centric MOP context
        step_index: Index of the step in the MOP (0-based)

    Security: Code is validated and executed with restricted builtins.
              Dangerous operations (imports, file I/O, exec, eval) are blocked.
    """
    try:
        from mop_engine import execute_sandboxed_python

        config = step['config']
        script = config.get('script', '')

        if not script:
            return {'status': 'error', 'error': 'No script provided'}

        log.info(f"Executing code step with {len(script)} characters of Python code")

        # Use sandboxed execution with mop context
        result = execute_sandboxed_python(
            code=script,
            extra_globals={
                'mop': mop_context or {},
            },
            allow_requests=False  # No HTTP in code steps
        )

        # Map result format for MOP step responses
        if result.get('status') == 'success':
            return {
                'status': 'success',
                'data': [{
                    'script': 'code_execution',
                    'status': 'success',
                    'output': result.get('data', result.get('message', {}))
                }]
            }
        else:
            return {
                'status': 'error',
                'error': result.get('error', 'Unknown error')
            }

    except Exception as e:
        log.error(f"Error executing code step: {e}")
        return {'status': 'error', 'error': str(e)}


def execute_deploy_stack_step(step, mop_context=None, step_index=0):
    """Execute a deploy stack step - deploys a service stack

    Args:
        step: Step configuration dict
        mop_context: Device-centric MOP context
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        stack_id = config.get('stack_id')

        if not stack_id:
            return {'status': 'error', 'error': 'Stack ID is required'}

        # Get the stack
        stack = get_service_stack(stack_id)
        if not stack:
            return {'status': 'error', 'error': f'Service stack not found: {stack_id}'}

        log.info(f"Deploying service stack: {stack.get('name')} (ID: {stack_id})")

        # Get default credentials from settings
        settings = db.get_all_settings()
        default_username = settings.get('default_username', '')
        default_password = settings.get('default_password', '')

        if not default_username or not default_password:
            log.warning("No default credentials configured - stack deployment may fail")

        credential_override = None
        if default_username and default_password:
            credential_override = {'username': default_username, 'password': default_password}
            log.info(f"Using default credentials for stack deployment (user: {default_username})")

        if stack.get('state') == 'deploying':
            return {'status': 'error', 'error': 'Stack is already being deployed'}

        # Update stack state
        stack['state'] = 'deploying'
        stack['deploy_started_at'] = datetime.now().isoformat()
        stack['deployed_services'] = []

        # Clear pending changes flag
        if 'has_pending_changes' in stack:
            del stack['has_pending_changes']
        if 'pending_since' in stack:
            del stack['pending_since']

        save_service_stack(stack)

        # Sort services by order
        services = sorted(stack['services'], key=lambda s: s.get('order', 0))
        log.info(f"Stack has {len(services)} services to deploy: {[s.get('name') for s in services]}")

        deployed_service_ids = []
        failed_services = []

        # Deploy services sequentially
        for service_def in services:
            try:
                log.info(f"Deploying service from stack: {service_def.get('name')}")

                # Merge shared variables with service-specific variables
                variables = {**stack.get('shared_variables', {}), **service_def.get('variables', {})}

                template_name = service_def.get('template')
                if not template_name:
                    raise Exception(f"Service '{service_def.get('name')}' has no template specified")

                # Strip .j2 extension if present
                if template_name.endswith('.j2'):
                    template_name = template_name[:-3]

                # Handle both single device and multiple devices
                devices = service_def.get('devices', [service_def.get('device')]) if service_def.get('devices') else [service_def.get('device')]

                for device_name in devices:
                    if not device_name:
                        continue

                    try:
                        # Get device connection info with credentials
                        device_info = get_device_connection_info(device_name, credential_override)
                        if not device_info:
                            raise Exception(f"Could not get connection info for device '{device_name}'")

                        # Render template and deploy via Celery
                        rendered_config = render_j2_template(template_name, variables)
                        if not rendered_config:
                            raise Exception(f"Failed to render template '{template_name}'")

                        log.info(f"Deploying template '{template_name}' to {device_name} via Celery")

                        task_id = celery_device_service.execute_set_config(
                            connection_args=device_info['connection_args'],
                            config_lines=rendered_config.split('\n'),
                            save_config=True
                        )

                        log.info(f"Template deployment initiated for {device_name}: task_id={task_id}")

                        if task_id:
                            job_name = f"mop:DEPLOY_STACK:{stack.get('name')}:{service_def['name']}:{device_name}:{task_id}"
                            save_task_id(task_id, device_name=job_name)

                            # Poll Celery for task completion
                            import time
                            max_wait = 300
                            poll_interval = 2
                            elapsed = 0

                            while elapsed < max_wait:
                                try:
                                    task_result = celery_device_service.get_task_result(task_id)
                                    task_status = task_result.get('status', 'PENDING')

                                    if task_status in ['SUCCESS', 'FAILURE']:
                                        log.info(f"Deploy task {task_id} completed with status: {task_status}")
                                        break

                                except Exception as poll_error:
                                    log.error(f"Error polling deploy task {task_id}: {poll_error}")
                                    break

                                time.sleep(poll_interval)
                                elapsed += poll_interval

                    except Exception as e:
                        log.error(f"Failed to deploy to {device_name}: {e}")
                        failed_services.append(f"{service_def.get('name')} on {device_name}")
                        continue

            except Exception as e:
                log.error(f"Failed to deploy service {service_def.get('name')}: {e}")
                failed_services.append(service_def.get('name'))
                continue

        # Update stack state
        stack['state'] = 'deployed' if not failed_services else 'partial'
        stack['deploy_completed_at'] = datetime.now().isoformat()
        save_service_stack(stack)

        result_message = f"Stack '{stack.get('name')}' deployed successfully"
        if failed_services:
            result_message += f" with {len(failed_services)} failed services: {', '.join(failed_services)}"

        return {
            'status': 'success' if not failed_services else 'partial',
            'data': [{
                'stack': stack.get('name'),
                'stack_id': stack_id,
                'status': 'deployed' if not failed_services else 'partial',
                'message': result_message,
                'failed_services': failed_services
            }]
        }

    except Exception as e:
        log.error(f"Error executing deploy stack step: {e}")
        return {'status': 'error', 'error': str(e)}


# Stack Template endpoints migrated to routes/stacks.py
# Administration routes migrated to routes/admin.py

# =============================================================================
# Scheduled Operations
# =============================================================================
# Scheduled operations are handled by Celery Beat (see tasks.py)
# The old thread-based scheduler has been removed.
#
# Celery Beat tasks:
#   - tasks.check_scheduled_operations (every 60 seconds)
#   - tasks.execute_scheduled_deploy
#   - tasks.execute_scheduled_backup
#   - tasks.execute_scheduled_mop
#   - tasks.cleanup_old_backups (daily at 3 AM)
#
# To start the scheduler:
#   celery -A tasks beat -l info --schedule=/data/celerybeat-schedule
# =============================================================================


if __name__ == "__main__":
    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(app, host="0.0.0.0", port=8088, debug=True, allow_unsafe_werkzeug=True)
