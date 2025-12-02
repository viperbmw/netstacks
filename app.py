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
from datetime import datetime
from netbox_client import NetboxClient
from jinja2 import Template, TemplateSyntaxError
from sqlalchemy import text
import db
import auth_ldap
import auth_oidc
from services.celery_device_service import celery_device_service

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'netstacks-secret-key')

# Register API documentation blueprint
try:
    from api_docs import api_bp
    app.register_blueprint(api_bp)
    log = logging.getLogger(__name__)
except Exception as e:
    log = logging.getLogger(__name__)
    log.warning(f"Could not register API docs: {e}")

# Register Celery deploy routes
try:
    from routes.deploy import deploy_bp
    app.register_blueprint(deploy_bp)
    log.info("Registered Celery deploy routes at /api/celery/*")
except Exception as e:
    log.warning(f"Could not register Celery deploy routes: {e}")

# Register v2 template routes (local database storage)
try:
    from routes.templates import templates_bp
    app.register_blueprint(templates_bp)
    log.info("Registered v2 template routes at /api/v2/templates/*")
except Exception as e:
    log.warning(f"Could not register v2 template routes: {e}")

# Configuration
NETBOX_URL = os.environ.get('NETBOX_URL', 'https://netbox.example.com')
NETBOX_TOKEN = os.environ.get('NETBOX_TOKEN', '')
VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() == 'true'
TASK_HISTORY_FILE = os.environ.get('TASK_HISTORY_FILE', '/tmp/netstacks_tasks.json')

# Setup logging first
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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
    """Hash a password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(stored_hash, provided_password):
    """Verify a password against a stored hash"""
    return stored_hash == hash_password(provided_password)


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


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Initialize default user on startup
create_default_user()


# =============================================================================
# Step Types Management Routes
# =============================================================================

@app.route('/step-types')
@login_required
def step_types_page():
    """Step types management page"""
    return render_template('step_types.html')


@app.route('/api/step-types', methods=['GET'])
@login_required
def get_step_types_api():
    """Get all step types"""
    try:
        step_types = db.get_all_step_types_full()
        return jsonify({'success': True, 'step_types': step_types})
    except Exception as e:
        log.error(f"Error getting step types: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/step-types/<step_type_id>', methods=['GET'])
@login_required
def get_step_type_api(step_type_id):
    """Get a specific step type"""
    try:
        step_type = db.get_step_type(step_type_id)
        if not step_type:
            return jsonify({'success': False, 'error': 'Step type not found'}), 404
        return jsonify({'success': True, 'step_type': step_type})
    except Exception as e:
        log.error(f"Error getting step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/step-types', methods=['POST'])
@login_required
def create_step_type_api():
    """Create a new step type"""
    try:
        data = request.json

        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        if not data.get('action_type'):
            return jsonify({'success': False, 'error': 'Action type is required'}), 400

        # Validate action type
        valid_action_types = ['get_config', 'set_config', 'api_call', 'validate', 'wait', 'manual', 'deploy_stack']
        if data.get('action_type') not in valid_action_types:
            return jsonify({'success': False, 'error': f'Invalid action type. Must be one of: {valid_action_types}'}), 400

        # For api_call types, validate URL is provided in config
        if data.get('action_type') == 'api_call':
            config = data.get('config', {})
            if not config.get('url'):
                return jsonify({'success': False, 'error': 'URL is required for API Call step types'}), 400

        step_type_id = db.save_step_type(data)
        return jsonify({'success': True, 'step_type_id': step_type_id})
    except Exception as e:
        log.error(f"Error creating step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/step-types/<step_type_id>', methods=['PUT'])
@login_required
def update_step_type_api(step_type_id):
    """Update a step type"""
    try:
        data = request.json
        data['step_type_id'] = step_type_id

        existing = db.get_step_type(step_type_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Step type not found'}), 404

        db.save_step_type(data)
        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error updating step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/step-types/<step_type_id>', methods=['DELETE'])
@login_required
def delete_step_type_api(step_type_id):
    """Delete a step type"""
    try:
        existing = db.get_step_type(step_type_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Step type not found'}), 404

        # Don't allow deleting built-in types
        if existing.get('is_builtin'):
            return jsonify({'success': False, 'error': 'Cannot delete built-in step types'}), 400

        db.delete_step_type(step_type_id)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Error deleting step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/step-types/<step_type_id>/toggle', methods=['POST'])
@login_required
def toggle_step_type_api(step_type_id):
    """Enable or disable a step type"""
    try:
        data = request.json
        enabled = data.get('enabled', True)

        existing = db.get_step_type(step_type_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Step type not found'}), 404

        db.toggle_step_type(step_type_id, enabled)
        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error toggling step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# Template context processor to inject menu items
@app.context_processor
def inject_menu_items():
    """Inject menu items into all templates"""
    try:
        if 'username' in session:  # Only load menu for logged-in users
            menu_items = db.get_menu_items()
            # Filter only visible items
            menu_items = [item for item in menu_items if item.get('visible', 1)]
            return {'menu_items': menu_items}
    except Exception as e:
        log.error(f"Error loading menu items: {e}")
    return {'menu_items': []}


# Device cache is now managed by services/device_service.py
# Import the device service functions for cache operations
from services.device_service import get_devices as device_service_get_devices
from services.device_service import get_cached_devices as device_service_get_cached
from services.device_service import clear_device_cache as device_service_clear_cache


# Task history management
def save_task_id(task_id, device_name=None):
    """Save a task ID to the history file with device name

    Args:
        task_id: The Celery task ID
        device_name: Descriptive name for the job. For standardized format use:
                    stack:{OPERATION}:{StackName}:{ServiceName}:{DeviceName}:{JobID}
    """
    try:
        tasks = []
        if os.path.exists(TASK_HISTORY_FILE):
            with open(TASK_HISTORY_FILE, 'r') as f:
                tasks = json.load(f)

        # Add new task with timestamp and device name
        tasks.append({
            'task_id': task_id,
            'device_name': device_name,
            'created': datetime.now().isoformat()
        })

        # Keep only last 500 tasks
        tasks = tasks[-500:]

        with open(TASK_HISTORY_FILE, 'w') as f:
            json.dump(tasks, f)
    except Exception as e:
        log.error(f"Error saving task ID: {e}")


def get_task_history():
    """Get all stored task IDs"""
    try:
        if os.path.exists(TASK_HISTORY_FILE):
            with open(TASK_HISTORY_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        log.error(f"Error reading task history: {e}")
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


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'GET':
        # If already logged in, redirect to dashboard
        if 'username' in session:
            return redirect(url_for('index'))

        # Check if OIDC is enabled for SSO button
        auth_configs = db.get_enabled_auth_configs()
        oidc_enabled = any(config['auth_type'] == 'oidc' for config in auth_configs)

        return render_template('login.html', oidc_enabled=oidc_enabled)

    # Handle POST - login attempt
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return render_template('login.html', error='Username and password are required')

    # Authenticate user through all enabled methods
    success, user_info, auth_method = authenticate_user(username, password)

    if not success:
        return render_template('login.html', error='Invalid username or password')

    # Login successful - create session
    session['username'] = username
    session['auth_method'] = auth_method
    session['login_time'] = datetime.now().isoformat()

    if user_info:
        session['user_info'] = user_info

    log.info(f"User {username} logged in successfully via {auth_method}")

    # Redirect to dashboard
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    """Logout and clear session"""
    username = session.get('username', 'unknown')
    session.clear()
    log.info(f"User {username} logged out")
    return redirect(url_for('login'))


@app.route('/login/oidc')
def login_oidc():
    """Initiate OIDC login flow"""
    # Get OIDC configuration
    oidc_config = db.get_auth_config('oidc')

    if not oidc_config or not oidc_config['is_enabled']:
        return render_template('login.html', error='OIDC authentication is not configured')

    try:
        # Generate authorization URL
        config_data = oidc_config['config_data']
        auth_url, state = auth_oidc.get_oidc_authorization_url(config_data)

        # Store state in session for verification
        session['oidc_state'] = state
        session['oidc_redirect'] = request.args.get('next', url_for('index'))

        # Redirect to OIDC provider
        return redirect(auth_url)

    except Exception as e:
        log.error(f"Error initiating OIDC login: {e}", exc_info=True)
        return render_template('login.html', error='Failed to initiate SSO login')


@app.route('/login/oidc/callback')
def login_oidc_callback():
    """Handle OIDC callback"""
    # Get authorization code and state from callback
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    if error:
        log.error(f"OIDC callback error: {error}")
        return render_template('login.html', error=f'SSO authentication failed: {error}')

    if not code or not state:
        return render_template('login.html', error='Invalid SSO callback')

    # Verify state
    expected_state = session.get('oidc_state')
    if not expected_state or state != expected_state:
        log.error("OIDC state mismatch")
        return render_template('login.html', error='SSO authentication failed: Invalid state')

    # Get OIDC configuration
    oidc_config = db.get_auth_config('oidc')
    if not oidc_config:
        return render_template('login.html', error='OIDC authentication is not configured')

    try:
        # Exchange code for token and get user info
        config_data = oidc_config['config_data']
        success, user_info = auth_oidc.authenticate_oidc_callback(code, state, expected_state, config_data)

        if not success or not user_info:
            return render_template('login.html', error='SSO authentication failed')

        username = user_info['username']

        # Create/update local user record for OIDC user
        if not get_user(username):
            db.create_user(username, hash_password(secrets.token_urlsafe(32)), 'oidc')

        # Login successful - create session
        session['username'] = username
        session['auth_method'] = 'oidc'
        session['login_time'] = datetime.now().isoformat()
        session['user_info'] = user_info

        # Clear OIDC state
        session.pop('oidc_state', None)

        log.info(f"User {username} logged in successfully via OIDC")

        # Redirect to original destination or dashboard
        next_url = session.pop('oidc_redirect', url_for('index'))
        return redirect(next_url)

    except Exception as e:
        log.error(f"Error processing OIDC callback: {e}", exc_info=True)
        return render_template('login.html', error='SSO authentication failed')


@app.context_processor
def inject_theme():
    """Inject user's theme preference into all templates"""
    if 'username' in session:
        theme = db.get_user_theme(session['username'])
        return {'user_theme': theme}
    return {'user_theme': 'dark'}




@app.route('/')
@login_required
def index():
    """Main dashboard"""
    return render_template('index.html')


@app.route('/deploy')
@login_required
def deploy():
    """Config deployment page"""
    return render_template('deploy.html')


@app.route('/monitor')
@login_required
def monitor():
    """Job monitoring page"""
    return render_template('monitor.html')


@app.route('/devices')
@login_required
def devices():
    """Device list page"""
    return render_template('devices.html')


@app.route('/mop')
@login_required
def mop():
    """Method of Procedures (MOP) page"""
    return render_template('mop.html')


@app.route('/mop')
@login_required
def mops():
    """MOPs page (YAML-based MOP engine)"""
    return render_template('mop.html')


@app.route('/workers')
@login_required
def workers():
    """Workers list page"""
    return render_template('workers.html')


@app.route('/templates')
@login_required
def templates_page():
    """Templates management page"""
    return render_template('templates.html')


@app.route('/settings')
@login_required
def settings_page():
    """Settings page"""
    return render_template('settings.html')


@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings_api():
    """Get current settings from database (or environment defaults)"""
    try:
        settings = get_settings()
        # Get system timezone from environment variable (set in docker-compose.yml)
        import os
        system_tz = os.environ.get('TZ', 'UTC')

        # Don't expose sensitive data in full
        safe_settings = {
            'netbox_url': settings.get('netbox_url'),
            'netbox_token': '****' if settings.get('netbox_token') else '',  # Masked
            'verify_ssl': settings.get('verify_ssl', False),
            'netbox_filters': settings.get('netbox_filters', []),
            'cache_ttl': settings.get('cache_ttl', 300),
            'system_timezone': system_tz  # Return timezone from environment
        }
        return jsonify({'success': True, 'settings': safe_settings})
    except Exception as e:
        log.error(f"Error getting settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
@login_required
def save_settings_api():
    """Save settings to database"""
    try:
        data = request.json

        log.info(f"[SETTINGS] Received settings save request")

        # Validate required fields - only netbox is required now
        if not data.get('netbox_url'):
            return jsonify({'success': False, 'error': 'netbox_url is required'}), 400

        # Prepare settings to save
        settings_to_save = {
            'netbox_url': data.get('netbox_url'),
            'netbox_token': data.get('netbox_token'),
            'verify_ssl': data.get('verify_ssl', False),
            'netbox_filters': data.get('netbox_filters', []),
            'cache_ttl': data.get('cache_ttl', 300),
            'default_username': data.get('default_username', ''),
            'default_password': data.get('default_password', ''),
            'system_timezone': data.get('system_timezone', 'UTC')
        }

        # Save to database
        save_settings(settings_to_save)

        log.info(f"Settings saved successfully")
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        log.error(f"Error saving settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api-docs')
@login_required
def api_docs():
    """API documentation - show local Celery-based API info"""
    return jsonify({
        'message': 'NetStacks API',
        'endpoints': {
            '/api/celery/getconfig': 'Execute show commands via Celery',
            '/api/celery/setconfig': 'Push configuration via Celery',
            '/api/celery/task/<task_id>': 'Get task status',
            '/api/v2/templates': 'Template management'
        }
    })


# ============================================================================
# Menu Items Endpoints
# ============================================================================

@app.route('/api/menu-items', methods=['GET'])
@login_required
def get_menu_items_api():
    """Get all menu items"""
    try:
        menu_items = db.get_menu_items()
        return jsonify({'success': True, 'menu_items': menu_items})
    except Exception as e:
        log.error(f"Error getting menu items: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/menu-items', methods=['POST'])
@login_required
def update_menu_items_api():
    """Update menu items order and visibility"""
    try:
        data = request.json
        menu_items = data.get('menu_items', [])

        if not menu_items:
            return jsonify({'success': False, 'error': 'No menu items provided'}), 400

        db.update_menu_order(menu_items)
        log.info("Menu items updated successfully")
        return jsonify({'success': True, 'message': 'Menu items updated successfully'})
    except Exception as e:
        log.error(f"Error updating menu items: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Resources Endpoints
# ============================================================================

@app.route('/api/api-resources', methods=['GET'])
@login_required
def get_api_resources():
    """Get all API resources"""
    try:
        resources = db.get_all_api_resources()
        return jsonify({'success': True, 'resources': resources})
    except Exception as e:
        log.error(f"Error getting API resources: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/api-resources', methods=['POST'])
@login_required
def create_api_resource():
    """Create a new API resource"""
    try:
        data = request.json

        # Validate required fields
        if not data.get('name') or not data.get('base_url'):
            return jsonify({'success': False, 'error': 'Name and Base URL are required'}), 400

        # Generate resource ID
        resource_id = str(uuid.uuid4())

        # Get current user
        created_by = session.get('username', 'unknown')

        # Create resource
        db.create_api_resource(
            resource_id=resource_id,
            name=data.get('name'),
            description=data.get('description', ''),
            base_url=data.get('base_url'),
            auth_type=data.get('auth_type', 'none'),
            auth_token=data.get('auth_token', ''),
            auth_username=data.get('auth_username', ''),
            auth_password=data.get('auth_password', ''),
            custom_headers=data.get('custom_headers'),
            created_by=created_by
        )

        log.info(f"API Resource created: {data.get('name')} by {created_by}")
        return jsonify({'success': True, 'resource_id': resource_id})
    except Exception as e:
        log.error(f"Error creating API resource: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/api-resources/<resource_id>', methods=['GET'])
@login_required
def get_api_resource(resource_id):
    """Get a specific API resource"""
    try:
        resource = db.get_api_resource(resource_id)
        if resource:
            return jsonify({'success': True, 'resource': resource})
        else:
            return jsonify({'success': False, 'error': 'Resource not found'}), 404
    except Exception as e:
        log.error(f"Error getting API resource {resource_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/api-resources/<resource_id>', methods=['PUT'])
@login_required
def update_api_resource(resource_id):
    """Update an existing API resource"""
    try:
        data = request.json

        # Validate required fields
        if not data.get('name') or not data.get('base_url'):
            return jsonify({'success': False, 'error': 'Name and Base URL are required'}), 400

        # Update resource
        db.update_api_resource(
            resource_id=resource_id,
            name=data.get('name'),
            description=data.get('description', ''),
            base_url=data.get('base_url'),
            auth_type=data.get('auth_type', 'none'),
            auth_token=data.get('auth_token', ''),
            auth_username=data.get('auth_username', ''),
            auth_password=data.get('auth_password', ''),
            custom_headers=data.get('custom_headers')
        )

        log.info(f"API Resource updated: {resource_id}")
        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error updating API resource {resource_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/api-resources/<resource_id>', methods=['DELETE'])
@login_required
def delete_api_resource(resource_id):
    """Delete an API resource"""
    try:
        db.delete_api_resource(resource_id)
        log.info(f"API Resource deleted: {resource_id}")
        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error deleting API resource {resource_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/proxy-api-call', methods=['POST'])
@login_required
def proxy_api_call():
    """Proxy API calls to bypass CORS restrictions"""
    try:
        import requests
        import base64

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

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=request_data if request_data else None,
            timeout=30,
            verify=False  # Allow self-signed certs
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


# API Endpoints for frontend

@app.route('/api/devices', methods=['GET', 'POST'])
@login_required
def get_devices():
    """Get device list from manual devices and Netbox (if configured).
    Uses centralized device cache from device_service.
    """
    try:
        # Get filters from request if provided (POST body or query params)
        filters = []
        if request.method == 'POST' and request.json:
            filter_list = request.json.get('filters', [])
            for f in filter_list:
                if 'key' in f and 'value' in f:
                    filters.append({'key': f['key'], 'value': f['value']})

        # Use device service to get devices (handles caching internally)
        result = device_service_get_devices(filters=filters)
        return jsonify(result)
    except Exception as e:
        log.error(f"Error fetching devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/devices/clear-cache', methods=['POST'])
@login_required
def clear_device_cache_endpoint():
    """Clear the device cache"""
    try:
        device_service_clear_cache()
        return jsonify({'success': True, 'message': 'Cache cleared successfully'})
    except Exception as e:
        log.error(f"Error clearing cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/devices/cached', methods=['GET'])
@login_required
def get_cached_devices_endpoint():
    """Get devices from cache only - does NOT call NetBox.
    Uses centralized device cache from device_service.
    """
    try:
        devices = device_service_get_cached()
        return jsonify({
            'success': True,
            'devices': devices,
            'from_cache': True,
            'count': len(devices)
        })
    except Exception as e:
        log.error(f"Error getting cached devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Manual Device Management API Routes
# ============================================================================

@app.route('/api/manual-devices', methods=['GET'])
@login_required
def get_manual_devices():
    """Get all manual devices"""
    try:
        devices = db.get_all_manual_devices()
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        log.error(f"Error fetching manual devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/manual-devices', methods=['POST'])
@login_required
def add_manual_device():
    """Add a new manual device"""
    try:
        data = request.json
        device_name = data.get('device_name', '').strip()
        device_type = data.get('device_type', '').strip()
        host = data.get('host', '').strip()
        port = data.get('port', 22)
        username = data.get('username', '').strip()
        password = data.get('password', '')

        # Validation
        if not device_name:
            return jsonify({'success': False, 'error': 'Device name is required'}), 400
        if not device_type:
            return jsonify({'success': False, 'error': 'Device type is required'}), 400
        if not host:
            return jsonify({'success': False, 'error': 'Host/IP is required'}), 400

        # Check if device already exists
        existing = db.get_manual_device(device_name)
        if existing:
            return jsonify({'success': False, 'error': 'Device with this name already exists'}), 400

        # Add device
        device_data = {
            'device_name': device_name,
            'device_type': device_type,
            'host': host,
            'port': port,
            'username': username,
            'password': password
        }
        db.save_manual_device(device_data)

        log.info(f"Manual device added: {device_name}")
        return jsonify({'success': True, 'message': f'Device {device_name} added successfully'})
    except Exception as e:
        log.error(f"Error adding manual device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/manual-devices/<device_name>', methods=['GET'])
@login_required
def get_manual_device_api(device_name):
    """Get a single manual device by name"""
    try:
        device = db.get_manual_device(device_name)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
        return jsonify({'success': True, 'device': device})
    except Exception as e:
        log.error(f"Error getting manual device {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/manual-devices/<device_name>', methods=['PUT'])
@login_required
def update_manual_device(device_name):
    """Update a manual device"""
    try:
        data = request.json

        # Get existing device
        existing = db.get_manual_device(device_name)
        if not existing:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Update fields
        device_data = {
            'device_name': device_name,
            'device_type': data.get('device_type', existing['device_type']).strip(),
            'host': data.get('host', existing['host']).strip(),
            'port': data.get('port', existing['port']),
            'username': data.get('username', existing.get('username', '')).strip(),
            'password': data.get('password', existing.get('password', ''))
        }

        # Validation
        if not device_data['device_type']:
            return jsonify({'success': False, 'error': 'Device type is required'}), 400
        if not device_data['host']:
            return jsonify({'success': False, 'error': 'Host/IP is required'}), 400

        db.save_manual_device(device_data)

        log.info(f"Manual device updated: {device_name}")
        return jsonify({'success': True, 'message': f'Device {device_name} updated successfully'})
    except Exception as e:
        log.error(f"Error updating manual device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/manual-devices/<device_name>', methods=['DELETE'])
@login_required
def delete_manual_device(device_name):
    """Delete a manual device"""
    try:
        if db.delete_manual_device(device_name):
            log.info(f"Manual device deleted: {device_name}")
            return jsonify({'success': True, 'message': f'Device {device_name} deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
    except Exception as e:
        log.error(f"Error deleting manual device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


### Device Override Endpoints ###

@app.route('/api/device-overrides', methods=['GET'])
@login_required
def get_all_device_overrides():
    """Get all device overrides"""
    try:
        overrides = db.get_all_device_overrides()
        return jsonify({'success': True, 'overrides': overrides})
    except Exception as e:
        log.error(f"Error getting device overrides: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device-overrides/<device_name>', methods=['GET'])
@login_required
def get_device_override(device_name):
    """Get device-specific overrides for a device"""
    try:
        override = db.get_device_override(device_name)
        if not override:
            return jsonify({'success': True, 'override': None, 'message': 'No override found for this device'})
        return jsonify({'success': True, 'override': override})
    except Exception as e:
        log.error(f"Error getting device override for {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device-overrides/<device_name>', methods=['PUT'])
@login_required
def save_device_override(device_name):
    """Save or update device-specific overrides"""
    try:
        data = request.json
        data['device_name'] = device_name

        # Don't store empty strings - convert to None
        for key in ['device_type', 'host', 'username', 'password', 'secret', 'notes']:
            if key in data and data[key] == '':
                data[key] = None

        # Convert numeric fields
        for key in ['port', 'timeout', 'conn_timeout', 'auth_timeout', 'banner_timeout']:
            if key in data and data[key] is not None:
                if data[key] == '' or data[key] == 0:
                    data[key] = None
                else:
                    try:
                        data[key] = int(data[key])
                    except (ValueError, TypeError):
                        data[key] = None

        if db.save_device_override(data):
            log.info(f"Device override saved for: {device_name}")
            return jsonify({'success': True, 'message': f'Override saved for {device_name}'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save override'}), 500
    except Exception as e:
        log.error(f"Error saving device override for {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device-overrides/<device_name>', methods=['DELETE'])
@login_required
def delete_device_override(device_name):
    """Delete device-specific overrides"""
    try:
        if db.delete_device_override(device_name):
            log.info(f"Device override deleted: {device_name}")
            return jsonify({'success': True, 'message': f'Override deleted for {device_name}'})
        else:
            return jsonify({'success': False, 'error': 'Override not found'}), 404
    except Exception as e:
        log.error(f"Error deleting device override for {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


### Config Backup Endpoints ###

@app.route('/api/config-backups', methods=['GET'])
@login_required
def list_config_backups():
    """List config backups with optional filters"""
    try:
        device_name = request.args.get('device')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        backups = db.get_config_backups(device_name=device_name, limit=limit, offset=offset)
        summary = db.get_backup_summary()

        return jsonify({
            'success': True,
            'backups': backups,
            'summary': summary,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        log.error(f"Error listing config backups: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/<backup_id>', methods=['GET'])
@login_required
def get_config_backup(backup_id):
    """Get a specific backup by ID"""
    try:
        backup = db.get_config_backup(backup_id)
        if not backup:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404

        return jsonify({'success': True, 'backup': backup})
    except Exception as e:
        log.error(f"Error getting backup {backup_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/<backup_id>', methods=['DELETE'])
@login_required
def delete_config_backup(backup_id):
    """Delete a specific backup"""
    try:
        if db.delete_config_backup(backup_id):
            log.info(f"Config backup deleted: {backup_id}")
            return jsonify({'success': True, 'message': 'Backup deleted'})
        else:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404
    except Exception as e:
        log.error(f"Error deleting backup {backup_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/device/<device_name>/latest', methods=['GET'])
@login_required
def get_latest_device_backup(device_name):
    """Get the latest backup for a specific device"""
    try:
        backup = db.get_latest_backup_for_device(device_name)
        if not backup:
            return jsonify({'success': False, 'error': f'No backup found for device {device_name}'}), 404

        return jsonify({'success': True, 'backup': backup})
    except Exception as e:
        log.error(f"Error getting latest backup for {device_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
            created_by=session.get('username', 'system')
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
            'created_by': session.get('username', 'system')
        })
        log.info(f"Created snapshot {snapshot_id} for {len(devices)} devices")

        # Submit backup tasks
        from services.device_service import get_device_connection_info as get_conn_info
        submitted = []
        failed = []

        created_by = session.get('username', 'system')
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


@app.route('/api/backup-schedule', methods=['GET'])
@login_required
def get_backup_schedule_api():
    """Get the backup schedule configuration"""
    try:
        schedule = db.get_backup_schedule()
        if not schedule:
            # Return defaults
            schedule = {
                'schedule_id': 'default',
                'enabled': False,
                'interval_hours': 24,
                'retention_days': 30,
                'juniper_set_format': True,
                'include_filters': [],
                'exclude_patterns': []
            }
        return jsonify({'success': True, 'schedule': schedule})
    except Exception as e:
        log.error(f"Error getting backup schedule: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backup-schedule', methods=['PUT'])
@login_required
def update_backup_schedule_api():
    """Update the backup schedule configuration"""
    try:
        data = request.json

        schedule_data = {
            'schedule_id': 'default',
            'enabled': data.get('enabled', False),
            'interval_hours': data.get('interval_hours', 24),
            'retention_days': data.get('retention_days', 30),
            'juniper_set_format': data.get('juniper_set_format', True),
            'include_filters': data.get('include_filters', []),
            'exclude_patterns': data.get('exclude_patterns', [])
        }

        db.save_backup_schedule(schedule_data)
        log.info(f"Backup schedule updated: enabled={schedule_data['enabled']}, interval={schedule_data['interval_hours']}h")

        return jsonify({'success': True, 'message': 'Backup schedule updated', 'schedule': schedule_data})
    except Exception as e:
        log.error(f"Error updating backup schedule: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config-backups/cleanup', methods=['POST'])
@login_required
def cleanup_old_backups():
    """Delete backups older than retention period"""
    try:
        data = request.json or {}
        retention_days = data.get('retention_days')

        if not retention_days:
            # Get from schedule
            schedule = db.get_backup_schedule()
            retention_days = schedule.get('retention_days', 30) if schedule else 30

        deleted_count = db.delete_old_backups(retention_days)
        log.info(f"Cleaned up {deleted_count} old backups (older than {retention_days} days)")

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'retention_days': retention_days
        })
    except Exception as e:
        log.error(f"Error cleaning up old backups: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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


@app.route('/snapshots')
@login_required
def snapshots_page():
    """Snapshots page - manage network configuration snapshots and device backups"""
    return render_template('config_backups.html')


@app.route('/config-backups')
@login_required
def config_backups_redirect():
    """Redirect old config-backups URL to snapshots"""
    return redirect(url_for('snapshots_page'))


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
        return jsonify({
            'status': 'success',
            'data': {
                'task_id': task_id,
                'task_status': result.get('status', 'unknown'),
                'task_result': result.get('result', {})
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

        # Extract parsing options from payload.args (where frontend sends them)
        args = payload.get('args', {})
        use_textfsm = args.get('use_textfsm', False)
        use_genie = args.get('use_genie', False)
        use_ttp = args.get('use_ttp', False)
        ttp_template = args.get('ttp_template', None)

        log.info(f"Parsing options: textfsm={use_textfsm}, genie={use_genie}, ttp={use_ttp}")

        # Execute via Celery
        task_id = celery_device_service.execute_get_config(
            connection_args=connection_args,
            command=command,
            use_textfsm=use_textfsm,
            use_genie=use_genie,
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


# Services routes
@app.route('/services')
@login_required
def services_page():
    """Render services management page"""
    return render_template('services.html')


@app.route('/service-stacks')
@login_required
def service_stacks_page():
    """Render service stacks management page"""
    return render_template('service-stacks.html')


@app.route('/users')
@login_required
def users_page():
    """Render user management page"""
    return render_template('users.html')


# User Management API Routes
@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    """Get list of all users"""
    try:
        all_users = db.get_all_users()
        # Don't send password hash to frontend
        users = [{'username': u['username'], 'created_at': u.get('created_at', 'Unknown')}
                 for u in all_users]
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        log.error(f"Error getting users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    """Create a new user"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400

        # Check if user already exists
        if get_user(username):
            return jsonify({'success': False, 'error': 'User already exists'}), 400

        # Create user
        db.create_user(username, hash_password(password))

        log.info(f"User {username} created by {session.get('username')}")
        return jsonify({'success': True, 'message': f'User {username} created successfully'})
    except Exception as e:
        log.error(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users/<username>/password', methods=['PUT'])
@login_required
def change_password(username):
    """Change user password"""
    try:
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        # Get current user from session
        current_user = session.get('username')

        # Users can only change their own password
        if current_user != username:
            return jsonify({'success': False, 'error': 'You can only change your own password'}), 403

        if not current_password or not new_password:
            return jsonify({'success': False, 'error': 'Current and new password are required'}), 400

        # Get user
        user = get_user(username)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Verify current password
        if not verify_password(user['password_hash'], current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

        # Update password
        db.update_user_password(username, hash_password(new_password))

        log.info(f"Password changed for user {username}")
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        log.error(f"Error changing password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users/<username>', methods=['DELETE'])
@login_required
def delete_user(username):
    """Delete a user"""
    try:
        # Can't delete yourself
        if session.get('username') == username:
            return jsonify({'success': False, 'error': 'You cannot delete your own account'}), 400

        # Can't delete admin user
        if username == 'admin':
            return jsonify({'success': False, 'error': 'Cannot delete admin user'}), 400

        # Delete user
        if db.delete_user(username):
            log.info(f"User {username} deleted by {session.get('username')}")
            return jsonify({'success': True, 'message': f'User {username} deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'User not found'}), 404
    except Exception as e:
        log.error(f"Error deleting user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/theme', methods=['GET'])
@login_required
def get_user_theme():
    """Get current user's theme preference"""
    try:
        username = session.get('username')
        theme = db.get_user_theme(username)
        return jsonify({'success': True, 'theme': theme})
    except Exception as e:
        log.error(f"Error getting user theme: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/theme', methods=['POST'])
@login_required
def set_user_theme():
    """Set current user's theme preference"""
    try:
        username = session.get('username')
        data = request.json
        theme = data.get('theme', 'dark')

        if theme not in ['dark', 'light']:
            return jsonify({'success': False, 'error': 'Invalid theme. Must be "dark" or "light"'}), 400

        if db.set_user_theme(username, theme):
            log.info(f"User {username} changed theme to {theme}")
            return jsonify({'success': True, 'message': 'Theme updated successfully', 'theme': theme})
        else:
            return jsonify({'success': False, 'error': 'Failed to update theme'}), 500
    except Exception as e:
        log.error(f"Error setting user theme: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/templates')
@login_required
def get_service_templates():
    """List all available service templates from local database"""
    try:
        # Get deploy-type templates from local database
        all_templates = db.get_all_templates()
        templates = [
            {'name': t['name'], 'description': t.get('description', '')}
            for t in all_templates
            if t.get('type', 'deploy') == 'deploy'
        ]
        return jsonify({'success': True, 'templates': templates})
    except Exception as e:
        log.error(f"Error fetching service templates: {e}")
        return jsonify({'success': True, 'templates': []})


@app.route('/api/services/templates/<template_name>/schema')
@login_required
def get_service_template_schema(template_name):
    """Get schema for a service template by extracting variables from template"""
    try:
        import re

        # Strip .j2 extension if present
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        # Get template content
        template_content = db.get_template_content(template_name)
        if not template_content:
            return jsonify({'success': True, 'schema': None})

        # Extract variables from template
        variable_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
        variables = list(set(re.findall(variable_pattern, template_content)))

        # Build a simple schema from extracted variables
        schema = {
            'properties': {var: {'type': 'string'} for var in variables},
            'required': variables
        }

        return jsonify({'success': True, 'schema': schema})
    except Exception as e:
        log.error(f"Error fetching service schema: {e}")
        return jsonify({'success': True, 'schema': None})


@app.route('/api/services/instances')
@login_required
def get_service_instances():
    """List all template-based service instances from database"""
    try:
        instances = get_all_service_instances()
        return jsonify({'success': True, 'instances': instances})
    except Exception as e:
        log.error(f"Error fetching service instances: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>')
@login_required
def get_service_instance_endpoint(service_id):
    """Get details of a specific template-based service instance"""
    try:
        instance = get_service_instance(service_id)  # Call the storage function
        if instance:
            return jsonify({'success': True, 'instance': instance})
        else:
            return jsonify({'success': False, 'error': 'Service not found'}), 404
    except Exception as e:
        log.error(f"Error fetching service instance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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

@app.route('/api/service-stacks', methods=['POST'])
@login_required
def create_service_stack():
    """Create a new service stack"""
    try:
        data = request.json

        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Stack name is required'}), 400

        if not data.get('services') or not isinstance(data['services'], list):
            return jsonify({'success': False, 'error': 'Services list is required'}), 400

        # Create stack data structure
        stack_data = {
            'stack_id': str(uuid.uuid4()),
            'name': data['name'],
            'description': data.get('description', ''),
            'services': data['services'],
            'shared_variables': data.get('shared_variables', {}),
            'state': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        # Validate service structure
        for i, service in enumerate(stack_data['services']):
            if not service.get('name'):
                return jsonify({'success': False, 'error': f'Service {i} missing name'}), 400
            if not service.get('template'):
                return jsonify({'success': False, 'error': f'Service {i} missing template'}), 400

            # Accept both 'device' (old format) and 'devices' (new format)
            if not service.get('device') and not service.get('devices'):
                return jsonify({'success': False, 'error': f'Service {i} missing device(s)'}), 400

            # Set defaults
            service.setdefault('order', i)
            service.setdefault('variables', {})
            service.setdefault('depends_on', [])

        # Save stack
        stack_id = save_service_stack(stack_data)

        return jsonify({
            'success': True,
            'stack_id': stack_id,
            'message': f'Service stack "{data["name"]}" created successfully'
        })

    except Exception as e:
        log.error(f"Error creating service stack: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service-stacks', methods=['GET'])
@login_required
def list_service_stacks():
    """Get all service stacks"""
    try:
        stacks = get_all_service_stacks()

        # Add summary information
        for stack in stacks:
            stack['service_count'] = len(stack.get('services', []))
            stack['devices'] = list(set([s.get('device') for s in stack.get('services', []) if s.get('device')]))

        return jsonify({
            'success': True,
            'stacks': stacks,
            'count': len(stacks)
        })

    except Exception as e:
        log.error(f"Error listing service stacks: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service-stacks/<stack_id>', methods=['GET'])
@login_required
def get_stack_details(stack_id):
    """Get details of a specific service stack"""
    try:
        stack = get_service_stack(stack_id)

        if not stack:
            return jsonify({'success': False, 'error': 'Service stack not found'}), 404

        # Add additional details
        stack['service_count'] = len(stack.get('services', []))
        stack['devices'] = list(set([s.get('device') for s in stack.get('services', []) if s.get('device')]))
        stack['templates'] = list(set([s.get('template') for s in stack.get('services', []) if s.get('template')]))

        return jsonify({
            'success': True,
            'stack': stack
        })

    except Exception as e:
        log.error(f"Error getting service stack details: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service-stacks/<stack_id>', methods=['PUT'])
@login_required
def update_service_stack(stack_id):
    """Update a service stack"""
    try:
        stack = get_service_stack(stack_id)

        if not stack:
            return jsonify({'success': False, 'error': 'Service stack not found'}), 404

        data = request.json

        # Track if any deployment-related fields changed
        has_changes = False

        # Update fields
        if 'name' in data:
            stack['name'] = data['name']
        if 'description' in data:
            stack['description'] = data['description']
        if 'services' in data:
            stack['services'] = data['services']
            has_changes = True  # Services changed - requires redeployment
        if 'shared_variables' in data:
            stack['shared_variables'] = data['shared_variables']
            has_changes = True  # Variables changed - requires redeployment
        if 'state' in data:
            stack['state'] = data['state']

        # If deployment-related fields changed and stack was previously deployed/partial, mark as having pending changes
        if has_changes and stack.get('state') in ['deployed', 'partial', 'failed']:
            stack['has_pending_changes'] = True
            stack['pending_since'] = datetime.now().isoformat()

        stack['updated_at'] = datetime.now().isoformat()

        save_service_stack(stack)

        return jsonify({
            'success': True,
            'message': f'Service stack "{stack["name"]}" updated successfully'
        })

    except Exception as e:
        log.error(f"Error updating service stack: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


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
                    # Set up session for authentication (bypass @login_required)
                    from flask import session as flask_session
                    flask_session['username'] = session.get('username')
                    log.info(f"Set session username to: {flask_session.get('username')}")

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

@app.route('/api/scheduled-operations', methods=['POST'])
@login_required
def create_scheduled_operation():
    """Create a new scheduled stack operation"""
    try:
        from db import create_scheduled_operation as db_create_schedule
        import uuid
        from datetime import datetime as dt, timedelta

        data = request.json
        stack_id = data.get('stack_id')
        operation_type = data.get('operation_type')
        schedule_type = data.get('schedule_type')
        scheduled_time = data.get('scheduled_time')
        day_of_week = data.get('day_of_week')
        day_of_month = data.get('day_of_month')

        if not all([stack_id, operation_type, schedule_type, scheduled_time]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        if operation_type not in ['deploy', 'validate', 'delete']:
            return jsonify({'success': False, 'error': 'Invalid operation_type'}), 400

        if schedule_type not in ['once', 'daily', 'weekly', 'monthly']:
            return jsonify({'success': False, 'error': 'Invalid schedule_type'}), 400

        schedule_id = str(uuid.uuid4())
        username = session.get('username')

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
            # For recurring schedules, calculate next occurrence
            time_parts = scheduled_time.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])

            if schedule_type == 'daily':
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
            elif schedule_type == 'weekly':
                # day_of_week: 0=Monday, 6=Sunday
                days_ahead = day_of_week - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
                if next_run <= now:
                    next_run += timedelta(weeks=1)
            elif schedule_type == 'monthly':
                next_run = now.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    # Move to next month
                    if now.month == 12:
                        next_run = next_run.replace(year=now.year + 1, month=1)
                    else:
                        next_run = next_run.replace(month=now.month + 1)

        db_create_schedule(
            schedule_id=schedule_id,
            stack_id=stack_id,
            operation_type=operation_type,
            schedule_type=schedule_type,
            scheduled_time=scheduled_time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            created_by=username
        )

        # Update next_run
        from db import update_scheduled_operation
        update_scheduled_operation(schedule_id, next_run=next_run.isoformat())

        log.info(f"Created scheduled operation: {schedule_id} for stack {stack_id}")
        return jsonify({'success': True, 'schedule_id': schedule_id})

    except Exception as e:
        log.error(f"Error creating scheduled operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-operations', methods=['GET'])
@login_required
def get_scheduled_operations():
    """Get scheduled operations, optionally filtered by stack_id"""
    try:
        from db import get_scheduled_operations as db_get_schedules

        stack_id = request.args.get('stack_id')
        schedules = db_get_schedules(stack_id=stack_id)

        return jsonify({'success': True, 'schedules': schedules})

    except Exception as e:
        log.error(f"Error getting scheduled operations: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-operations/<schedule_id>', methods=['GET'])
@login_required
def get_scheduled_operation(schedule_id):
    """Get a specific scheduled operation"""
    try:
        from db import get_scheduled_operation as db_get_schedule

        schedule = db_get_schedule(schedule_id)
        if not schedule:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404

        return jsonify({'success': True, 'schedule': schedule})

    except Exception as e:
        log.error(f"Error getting scheduled operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-operations/<schedule_id>', methods=['PATCH', 'PUT'])
@login_required
def update_scheduled_operation_endpoint(schedule_id):
    """Update a scheduled operation"""
    try:
        from db import update_scheduled_operation as db_update_schedule, get_scheduled_operation
        from datetime import datetime as dt, timedelta

        data = request.json

        # If schedule time/type changed, recalculate next_run
        if 'schedule_type' in data or 'scheduled_time' in data:
            schedule = get_scheduled_operation(schedule_id)
            if not schedule:
                return jsonify({'success': False, 'error': 'Schedule not found'}), 404

            schedule_type = data.get('schedule_type', schedule['schedule_type'])
            scheduled_time = data.get('scheduled_time', schedule['scheduled_time'])
            day_of_week = data.get('day_of_week', schedule.get('day_of_week'))
            day_of_month = data.get('day_of_month', schedule.get('day_of_month'))

            # Calculate new next_run
            now = dt.now()
            if schedule_type == 'once':
                next_run = dt.fromisoformat(scheduled_time.replace('Z', ''))
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

            data['next_run'] = next_run.isoformat()

        success = db_update_schedule(schedule_id, **data)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404

    except Exception as e:
        log.error(f"Error updating scheduled operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-operations/<schedule_id>', methods=['DELETE'])
@login_required
def delete_scheduled_operation_endpoint(schedule_id):
    """Delete a scheduled operation"""
    try:
        from db import delete_scheduled_operation as db_delete_schedule

        success = db_delete_schedule(schedule_id)

        if success:
            log.info(f"Deleted scheduled operation: {schedule_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404

    except Exception as e:
        log.error(f"Error deleting scheduled operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


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
        username = session.get('username')

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


@app.route('/api/custom-step-types', methods=['GET'])
@login_required
def get_custom_step_types_api():
    """Get all custom step types"""
    try:
        step_types = db.get_all_step_types()
        # Filter only custom types (non-builtin)
        custom_types = [st for st in step_types if not st.get('is_builtin')]
        return jsonify({'success': True, 'step_types': custom_types})
    except Exception as e:
        log.error(f"Error getting custom step types: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/custom-step-types', methods=['POST'])
@login_required
def create_custom_step_type_api():
    """Create a new custom step type"""
    try:
        data = request.json

        # Validate required fields
        required_fields = ['step_type_id', 'name', 'custom_type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        # Validate custom_type
        if data['custom_type'] not in ['python', 'webhook']:
            return jsonify({'success': False, 'error': 'custom_type must be "python" or "webhook"'}), 400

        # Validate type-specific fields
        if data['custom_type'] == 'python' and not data.get('custom_code'):
            return jsonify({'success': False, 'error': 'custom_code is required for python type'}), 400

        if data['custom_type'] == 'webhook' and not data.get('custom_webhook_url'):
            return jsonify({'success': False, 'error': 'custom_webhook_url is required for webhook type'}), 400

        # Create the step type
        step_type_id = db.create_custom_step_type(
            step_type_id=data['step_type_id'],
            name=data['name'],
            description=data.get('description', ''),
            category=data.get('category', 'Custom'),
            parameters_schema=data.get('parameters_schema', {}),
            icon=data.get('icon', 'cog'),
            custom_type=data['custom_type'],
            custom_code=data.get('custom_code'),
            custom_webhook_url=data.get('custom_webhook_url'),
            custom_webhook_method=data.get('custom_webhook_method', 'POST'),
            custom_webhook_headers=data.get('custom_webhook_headers')
        )

        return jsonify({'success': True, 'step_type_id': step_type_id})

    except Exception as e:
        log.error(f"Error creating custom step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/custom-step-types/<step_type_id>', methods=['GET'])
@login_required
def get_custom_step_type_api(step_type_id):
    """Get a specific custom step type"""
    try:
        step_type = db.get_step_type(step_type_id)
        if not step_type:
            return jsonify({'success': False, 'error': 'Step type not found'}), 404

        if not step_type.get('is_custom'):
            return jsonify({'success': False, 'error': 'Not a custom step type'}), 400

        return jsonify({'success': True, 'step_type': step_type})

    except Exception as e:
        log.error(f"Error getting custom step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/custom-step-types/<step_type_id>', methods=['PUT'])
@login_required
def update_custom_step_type_api(step_type_id):
    """Update a custom step type"""
    try:
        data = request.json

        # Validate custom_type if provided
        if 'custom_type' in data and data['custom_type'] not in ['python', 'webhook']:
            return jsonify({'success': False, 'error': 'custom_type must be "python" or "webhook"'}), 400

        success = db.update_custom_step_type(
            step_type_id=step_type_id,
            name=data.get('name'),
            description=data.get('description'),
            category=data.get('category'),
            parameters_schema=data.get('parameters_schema'),
            icon=data.get('icon'),
            custom_type=data.get('custom_type'),
            custom_code=data.get('custom_code'),
            custom_webhook_url=data.get('custom_webhook_url'),
            custom_webhook_method=data.get('custom_webhook_method'),
            custom_webhook_headers=data.get('custom_webhook_headers'),
            enabled=data.get('enabled')
        )

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update step type'}), 400

    except Exception as e:
        log.error(f"Error updating custom step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/custom-step-types/<step_type_id>', methods=['DELETE'])
@login_required
def delete_custom_step_type_api(step_type_id):
    """Delete a custom step type"""
    try:
        success = db.delete_custom_step_type(step_type_id)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete step type or not a custom type'}), 400

    except Exception as e:
        log.error(f"Error deleting custom step type: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mops', methods=['GET'])
@login_required
def get_mops_api():
    """Get all workflows"""
    try:
        with db.get_db() as session:
            result = session.execute(text('''
                SELECT mop_id, name, description, devices, enabled, created_at, updated_at
                FROM mops
                ORDER BY created_at DESC
            '''))
            MOPs = [dict(row._mapping) for row in result.fetchall()]
            return jsonify({'success': True, 'mops': MOPs})
    except Exception as e:
        log.error(f"Error getting MOPs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mops', methods=['POST'])
@login_required
def create_mop_api():
    """Create a new workflow"""
    try:
        data = request.json
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

        return jsonify({'success': True, 'mop_id': mop_id})
    except Exception as e:
        log.error(f"Error creating MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mops/<mop_id>', methods=['GET'])
@login_required
def get_mop_api(mop_id):
    """Get a specific workflow"""
    try:
        with db.get_db() as session_db:
            result = session_db.execute(text('SELECT * FROM mops WHERE mop_id = :mop_id'), {'mop_id': mop_id})
            MOP = result.fetchone()

            if not MOP:
                return jsonify({'success': False, 'error': 'MOP not found'}), 404

            return jsonify({'success': True, 'mop': dict(MOP._mapping)})
    except Exception as e:
        log.error(f"Error getting MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mops/<mop_id>', methods=['PUT'])
@login_required
def update_mop_api(mop_id):
    """Update a workflow"""
    try:
        data = request.json

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

        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error updating MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mops/<mop_id>', methods=['DELETE'])
@login_required
def delete_mop_api(mop_id):
    """Delete a workflow"""
    try:
        with db.get_db() as session_db:
            session_db.execute(text('DELETE FROM mops WHERE mop_id = :mop_id'), {'mop_id': mop_id})

        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error deleting MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


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
            '''), {'execution_id': execution_id, 'mop_id': mop_id, 'started_by': session.get('username')})

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


@app.route('/api/mops/<mop_id>/executions', methods=['GET'])
@login_required
def get_mop_executions_api(mop_id):
    """Get execution history for a workflow"""
    try:
        with db.get_db() as session_db:
            result = session_db.execute(text('''
                SELECT execution_id, status, started_at, completed_at, started_by
                FROM mop_executions
                WHERE mop_id = :mop_id
                ORDER BY started_at DESC
                LIMIT 50
            '''), {'mop_id': mop_id})
            executions = [dict(row._mapping) for row in result.fetchall()]
            return jsonify({'success': True, 'executions': executions})
    except Exception as e:
        log.error(f"Error getting MOP executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mop-executions/<execution_id>', methods=['GET'])
@login_required
def get_mop_execution_details_api(execution_id):
    """Get detailed execution information"""
    try:
        with db.get_db() as session_db:
            result = session_db.execute(text('''
                SELECT we.*, w.name as mop_name
                FROM mop_executions we
                LEFT JOIN mops w ON we.mop_id = w.mop_id
                WHERE we.execution_id = :execution_id
            '''), {'execution_id': execution_id})
            execution = result.fetchone()

            if not execution:
                return jsonify({'success': False, 'error': 'Execution not found'}), 404

            execution_dict = dict(execution._mapping)

            # Parse JSON fields if they are strings
            if execution_dict.get('execution_log'):
                if isinstance(execution_dict['execution_log'], str):
                    try:
                        execution_dict['execution_log'] = json.loads(execution_dict['execution_log'])
                    except:
                        pass  # Keep as string if not valid JSON
            if execution_dict.get('context'):
                if isinstance(execution_dict['context'], str):
                    try:
                        execution_dict['context'] = json.loads(execution_dict['context'])
                    except:
                        pass  # Keep as string if not valid JSON

            return jsonify({'success': True, 'execution': execution_dict})
    except Exception as e:
        log.error(f"Error getting MOP execution details: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mop-executions/running', methods=['GET'])
@login_required
def get_running_mop_executions_api():
    """Get recent MOP executions (last 20)"""
    try:
        with db.get_db() as session_db:
            result = session_db.execute(text('''
                SELECT we.execution_id, we.mop_id, we.status, we.current_step,
                       we.started_at, we.completed_at, we.started_by, w.name as mop_name
                FROM mop_executions we
                JOIN mops w ON we.mop_id = w.mop_id
                ORDER BY we.started_at DESC
                LIMIT 20
            '''))
            executions = [dict(row._mapping) for row in result.fetchall()]
            return jsonify({'success': True, 'executions': executions})
    except Exception as e:
        log.error(f"Error getting MOP executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


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
                    use_textfsm=config.get('use_textfsm', False),
                    use_genie=False
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
                    'status': result.get('status', 'success'),
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
    """Execute a code/script step for data processing

    Args:
        step: Step configuration dict
        mop_context: Device-centric MOP context
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        script = config.get('script', '')

        if not script:
            return {'status': 'error', 'error': 'No script provided'}

        # Create a safe execution environment
        # Pass mop_context as 'mop' for simpler access
        safe_globals = {
            'mop': mop_context or {},
            'json': json,
            're': __import__('re'),
            '__builtins__': {
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sorted': sorted,
                'sum': sum,
                'min': min,
                'max': max,
                'any': any,
                'all': all,
                'print': print,
            }
        }

        log.info(f"Executing code step with {len(script)} characters of Python code")

        # Execute the script
        exec(script, safe_globals)

        # Get the result - script should set 'result' variable or return value
        result_output = safe_globals.get('result', {})

        return {
            'status': 'success',
            'data': [{
                'script': 'code_execution',
                'status': 'success',
                'output': result_output
            }]
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


# Stack Template endpoints
@app.route('/api/stack-templates', methods=['GET'])
@login_required
def get_stack_templates():
    """Get all stack templates"""
    try:
        templates = db.get_all_stack_templates()
        return jsonify({'success': True, 'templates': templates})
    except Exception as e:
        log.error(f"Error getting stack templates: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stack-templates/<template_id>', methods=['GET'])
@login_required
def get_stack_template_details(template_id):
    """Get a specific stack template"""
    try:
        template = db.get_stack_template(template_id)
        if not template:
            return jsonify({'success': False, 'error': 'Stack template not found'}), 404
        return jsonify({'success': True, 'template': template})
    except Exception as e:
        log.error(f"Error getting stack template: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stack-templates', methods=['POST'])
@login_required
def create_stack_template():
    """Create a new stack template from an existing stack"""
    try:
        data = request.json

        # Required fields
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Template name is required'}), 400

        if not data.get('services'):
            return jsonify({'success': False, 'error': 'Services are required'}), 400

        # Extract all variables from all device templates in the stack
        required_variables = set()
        services = data['services']

        for service in services:
            template_name = service.get('template')
            if template_name:
                template_name_clean = template_name[:-3] if template_name.endswith('.j2') else template_name
                try:
                    # Get template from local database
                    template_content = db.get_template_content(template_name_clean)
                    if template_content:
                        import re
                        variable_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
                        variables = re.findall(variable_pattern, template_content)
                        required_variables.update(variables)
                except Exception as e:
                    log.warning(f"Could not extract variables from template {template_name}: {e}")

        # Check if this is an update (template_id provided) or create (new)
        existing_template_id = data.get('template_id')
        is_update = bool(existing_template_id)

        template_data = {
            'name': data['name'],
            'description': data.get('description', ''),
            'services': services,
            'required_variables': sorted(list(required_variables)),
            'api_variables': data.get('api_variables', {}),
            'per_device_variables': data.get('per_device_variables', []),
            'tags': data.get('tags', []),
            'created_by': session.get('username', 'unknown')
        }

        # Include template_id if updating existing template
        if existing_template_id:
            template_data['template_id'] = existing_template_id

        template_id = db.save_stack_template(template_data)

        action = 'updated' if is_update else 'created'
        return jsonify({
            'success': True,
            'template_id': template_id,
            'message': f'Stack template "{data["name"]}" {action} successfully'
        })

    except Exception as e:
        log.error(f"Error creating stack template: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stack-templates/<template_id>', methods=['DELETE'])
@login_required
def delete_stack_template_endpoint(template_id):
    """Delete a stack template"""
    try:
        template = db.get_stack_template(template_id)
        if not template:
            return jsonify({'success': False, 'error': 'Stack template not found'}), 404

        db.delete_stack_template(template_id)

        return jsonify({
            'success': True,
            'message': f'Stack template "{template["name"]}" deleted successfully'
        })

    except Exception as e:
        log.error(f"Error deleting stack template: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== Administration Routes =====

@app.route('/admin')
@login_required
def admin_page():
    """Combined administration page with users and authentication"""
    username = session.get('username')
    user = get_user(username) if username else None
    auth_source = user.get('auth_source', 'local') if user else 'local'
    return render_template('admin.html', user_auth_source=auth_source)

# Keep old routes for backward compatibility
@app.route('/users')
@login_required
def users_page_redirect():
    """Redirect to admin page users tab"""
    return render_template('admin.html')

@app.route('/authentication')
@login_required
def authentication_page():
    """Redirect to admin page authentication tab"""
    return render_template('admin.html')


@app.route('/api/auth/configs', methods=['GET'])
@login_required
def get_auth_configs():
    """Get all authentication configurations"""
    try:
        configs = db.get_all_auth_configs()
        return jsonify({'success': True, 'configs': configs})
    except Exception as e:
        log.error(f"Error getting auth configs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/config/<auth_type>', methods=['GET'])
@login_required
def get_auth_config_endpoint(auth_type):
    """Get specific authentication configuration"""
    try:
        config = db.get_auth_config(auth_type)
        if config:
            return jsonify(config)
        return jsonify({'error': 'Configuration not found'}), 404
    except Exception as e:
        log.error(f"Error getting auth config: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/config', methods=['POST'])
@login_required
def save_auth_config_endpoint():
    """Save authentication configuration"""
    try:
        data = request.json
        auth_type = data.get('auth_type')
        config_data = data.get('config_data', {})
        is_enabled = data.get('is_enabled', True)
        priority = data.get('priority', 0)

        if not auth_type:
            return jsonify({'success': False, 'error': 'auth_type is required'}), 400

        if auth_type not in ['local', 'ldap', 'oidc']:
            return jsonify({'success': False, 'error': 'Invalid auth_type'}), 400

        # Save configuration
        db.save_auth_config(auth_type, config_data, is_enabled, priority)

        return jsonify({
            'success': True,
            'message': f'{auth_type.upper()} configuration saved successfully'
        })

    except Exception as e:
        log.error(f"Error saving auth config: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/config/<auth_type>', methods=['DELETE'])
@login_required
def delete_auth_config_endpoint(auth_type):
    """Delete authentication configuration"""
    try:
        success = db.delete_auth_config(auth_type)
        if success:
            return jsonify({
                'success': True,
                'message': f'{auth_type.upper()} configuration deleted successfully'
            })
        return jsonify({'success': False, 'error': 'Configuration not found'}), 404
    except Exception as e:
        log.error(f"Error deleting auth config: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/config/<auth_type>/toggle', methods=['POST'])
@login_required
def toggle_auth_config_endpoint(auth_type):
    """Enable or disable authentication method"""
    try:
        data = request.json
        enabled = data.get('enabled', True)

        log.info(f"Toggling {auth_type} to {'enabled' if enabled else 'disabled'}")
        success = db.toggle_auth_config(auth_type, enabled)
        log.info(f"Toggle result: {success}")

        if success:
            status = 'enabled' if enabled else 'disabled'
            log.info(f"{auth_type.upper()} authentication {status} successfully")
            return jsonify({
                'success': True,
                'message': f'{auth_type.upper()} authentication {status} successfully'
            })
        log.warning(f"Toggle failed - configuration not found for {auth_type}")
        return jsonify({'success': False, 'error': 'Configuration not found'}), 404
    except Exception as e:
        log.error(f"Error toggling auth config: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/test/ldap', methods=['POST'])
@login_required
def test_ldap_connection_endpoint():
    """Test LDAP connection"""
    try:
        data = request.json
        config = data.get('config', {})

        log.info(f"Testing LDAP with config: server={config.get('server')}, base_dn={config.get('base_dn')}")

        success, message = auth_ldap.test_ldap_connection(config)

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        log.error(f"Error testing LDAP connection: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/test/oidc', methods=['POST'])
@login_required
def test_oidc_connection_endpoint():
    """Test OIDC configuration"""
    try:
        data = request.json
        config = data.get('config', {})

        log.info("=" * 50)
        log.info("OIDC TEST CONNECTION REQUEST")
        log.info(f"Request data keys: {list(data.keys()) if data else 'None'}")
        log.info(f"Config keys: {list(config.keys()) if config else 'None'}")
        log.info(f"Issuer: {config.get('issuer', 'MISSING')}")
        log.info(f"Client ID: {config.get('client_id', 'MISSING')[:20] + '...' if config.get('client_id') else 'MISSING'}")
        log.info(f"Client Secret: {'SET' if config.get('client_secret') else 'MISSING'}")
        log.info("=" * 50)

        success, message = auth_oidc.test_oidc_connection(config)

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        log.error(f"Error testing OIDC configuration: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/local/priority', methods=['GET', 'POST'])
@login_required
def local_auth_priority():
    """Get or set local authentication priority"""
    try:
        if request.method == 'GET':
            priority = db.get_setting('local_auth_priority', '999')
            return jsonify({'success': True, 'priority': int(priority)})
        else:
            data = request.json
            priority = data.get('priority', 999)
            db.set_setting('local_auth_priority', str(priority))
            log.info(f"Updated local auth priority to: {priority}")
            return jsonify({'success': True, 'message': 'Local auth priority updated'})
    except Exception as e:
        log.error(f"Error handling local auth priority: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Background Scheduler ====================

import threading
import time as time_module

def run_scheduled_operations():
    """Background thread to execute scheduled operations"""
    print("SCHEDULER THREAD FUNCTION CALLED!", flush=True)
    try:
        from db import get_pending_scheduled_operations, update_scheduled_operation
        from datetime import datetime as dt, timedelta

        log.info("Starting scheduled operations background thread")
        print("SCHEDULER THREAD AFTER LOG!", flush=True)
        print("About to enter while loop...", flush=True)

        while True:
            try:
                # Check for pending schedules every 60 seconds
                print("In while loop - about to log and sleep...", flush=True)
                log.info("Scheduler loop iteration - sleeping for 60 seconds...")
                time_module.sleep(60)

                log.info("Checking for pending scheduled operations...")
                pending_schedules = get_pending_scheduled_operations()
                log.info(f"Found {len(pending_schedules)} pending scheduled operations")

                for schedule in pending_schedules:
                    try:
                        schedule_id = schedule['schedule_id']
                        stack_id = schedule['stack_id']
                        operation_type = schedule['operation_type']
                        schedule_type = schedule['schedule_type']

                        log.info(f"Executing scheduled operation: {operation_type} for stack/target {stack_id}")

                        # Execute the operation
                        if operation_type == 'deploy':
                            # Deploy the stack directly (same logic as manual deployment)
                            log.info(f"Deploying stack {stack_id} via scheduled operation")
                            try:
                                stack = get_service_stack(stack_id)
                                if not stack:
                                    log.error(f"Stack {stack_id} not found for scheduled deployment")
                                    continue
    
                                if stack.get('state') == 'deploying':
                                    log.warning(f"Stack {stack_id} is already being deployed, skipping")
                                    continue
    
                                # Update stack state
                                stack['state'] = 'deploying'
                                from datetime import datetime
                                stack['deploy_started_at'] = datetime.now().isoformat()
                                stack['deployed_services'] = []
    
                                # Clear pending changes
                                if 'has_pending_changes' in stack:
                                    del stack['has_pending_changes']
                                if 'pending_since' in stack:
                                    del stack['pending_since']
    
                                save_service_stack(stack)
                                log.info(f"Stack {stack_id} state set to deploying, will deploy {len(stack.get('services', []))} services")
    
                                # Sort services by order
                                services = sorted(stack['services'], key=lambda s: s.get('order', 0))
    
                                deployed_service_ids = []
                                failed_services = []
    
                                # Deploy services sequentially
                                for service_def in services:
                                    try:
                                        log.info(f"Scheduled deployment: deploying service {service_def.get('name')}")
                                        log.info(f"Service definition: {service_def}")
    
                                        # Merge shared variables with service-specific variables
                                        variables = {**stack.get('shared_variables', {}), **service_def.get('variables', {})}
    
                                        template_name = service_def.get('template')
                                        if not template_name:
                                            raise Exception(f"Service '{service_def.get('name')}' has no template specified")
    
                                        # Strip .j2 extension if present
                                        if template_name.endswith('.j2'):
                                            template_name = template_name[:-3]
    
                                        # Get template metadata
                                        template_metadata = get_template_metadata(template_name)
    
                                        # Deploy to each device - handle both 'device' (singular) and 'devices' (plural)
                                        devices = service_def.get('devices', [])
                                        if not devices and 'device' in service_def:
                                            # Handle singular 'device' field
                                            devices = [service_def['device']]
    
                                        log.info(f"Devices for service {service_def.get('name')}: {devices} (count: {len(devices)})")
    
                                        if not devices:
                                            log.warning(f"No devices configured for service {service_def.get('name')}, skipping deployment")
                                            continue
    
                                        for device_name in devices:
                                            log.info(f"Scheduled deployment: deploying to device {device_name}")
    
                                            # Get device connection info (no credential override for scheduled jobs)
                                            device_info = get_device_connection_info(device_name, None)
                                            if not device_info:
                                                raise Exception(f"Could not get connection info for device '{device_name}'")
    
                                            # Add default credentials from settings
                                            settings = get_settings()
                                            log.info(f"[DEPLOY] Settings keys: {list(settings.keys())}")
                                            log.info(f"[DEPLOY] default_username exists: {settings.get('default_username') is not None}")
                                            log.info(f"[DEPLOY] Connection args BEFORE creds: {device_info['connection_args']}")
                                            if settings.get('default_username'):
                                                device_info['connection_args']['username'] = settings['default_username']
                                                device_info['connection_args']['password'] = settings.get('default_password', '')
                                                log.info(f"[DEPLOY] Added credentials - username: {settings['default_username']}")
                                            else:
                                                log.warning(f"[DEPLOY] No default_username found in settings!")
                                            log.info(f"[DEPLOY] Connection args AFTER creds: {device_info['connection_args']}")
    
                                            # Render template and deploy via Celery
                                            rendered_config = render_j2_template(template_name, variables)
                                            if not rendered_config:
                                                raise Exception(f"Failed to render template '{template_name}'")

                                            log.info(f"Sending deployment via Celery")

                                            task_id = celery_device_service.execute_set_config(
                                                connection_args=device_info['connection_args'],
                                                config_lines=rendered_config.split('\n'),
                                                save_config=True
                                            )

                                            if not task_id:
                                                raise Exception(f"Failed to deploy to {device_name}: no task_id returned")
    
                                            # Save task to history
                                            save_task_id(task_id, device_name=f"scheduled:{stack.get('name')}:{service_def['name']}:{device_name}")
    
                                            # Create service instance record
                                            service_instance = {
                                                'service_id': str(uuid.uuid4()),
                                                'name': f"{service_def['name']} ({device_name})",
                                                'template': template_name,
                                                'validation_template': template_metadata.get('validation_template') if template_metadata else None,
                                                'delete_template': template_metadata.get('delete_template') if template_metadata else None,
                                                'device': device_name,
                                                'variables': variables,
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
    
                                    except Exception as svc_err:
                                        log.error(f"Error deploying service {service_def.get('name')}: {svc_err}", exc_info=True)
                                        failed_services.append(service_def.get('name'))
    
                                # Update final stack state
                                stack['deployed_services'] = deployed_service_ids
                                if failed_services:
                                    stack['state'] = 'partial'
                                    stack['deployment_errors'] = failed_services
                                    log.warning(f"Stack {stack_id} deployment completed with errors: {failed_services}")
                                else:
                                    stack['state'] = 'deployed'
                                    stack['deployment_errors'] = []
                                    log.info(f"Stack {stack_id} deployment completed successfully")
    
                                stack['deploy_completed_at'] = datetime.now().isoformat()
                                save_service_stack(stack)
    
                            except Exception as deploy_err:
                                log.error(f"Error in scheduled stack deployment: {deploy_err}", exc_info=True)
    
                        elif operation_type == 'validate':
                            # Validate the stack
                            log.info(f"Validating stack {stack_id} via scheduled operation")
                            try:
                                stack = get_service_stack(stack_id)
                                if not stack:
                                    log.error(f"Stack {stack_id} not found for scheduled validation")
                                    continue
    
                                # Validate each service definition in the stack
                                services = stack.get('services', [])
                                log.info(f"Stack {stack_id} has {len(services)} services to validate")
    
                                for service_def in services:
                                    try:
                                        log.info(f"Scheduled validation: validating service {service_def.get('name')}")
    
                                        # Get devices - handle both 'device' (singular) and 'devices' (plural)
                                        devices = service_def.get('devices', [])
                                        if not devices and 'device' in service_def:
                                            devices = [service_def['device']]
    
                                        if not devices:
                                            log.warning(f"No devices configured for service {service_def.get('name')}, skipping validation")
                                            continue
    
                                        # Merge variables
                                        variables = {**stack.get('shared_variables', {}), **service_def.get('variables', {})}
                                        template_name = service_def.get('template')
    
                                        # For each device, run getconfig to validate
                                        for device_name in devices:
                                            log.info(f"Scheduled validation: validating device {device_name}")
    
                                            # Get device connection info
                                            device_info = get_device_connection_info(device_name, None)
                                            if not device_info:
                                                log.error(f"Could not get connection info for device '{device_name}'")
                                                continue
    
                                            # Add default credentials from settings
                                            settings = get_settings()
                                            if settings.get('default_username'):
                                                device_info['connection_args']['username'] = settings['default_username']
                                                device_info['connection_args']['password'] = settings.get('default_password', '')
    
                                            # Execute validation via Celery
                                            log.info(f"Sending validation via Celery for {device_name}")

                                            # Get expected patterns from template
                                            rendered_config = render_j2_template(template_name, variables) if template_name else ""
                                            patterns = [line.strip() for line in rendered_config.split('\n') if line.strip()][:10]

                                            task_id = celery_device_service.execute_validate(
                                                connection_args=device_info['connection_args'],
                                                expected_patterns=patterns,
                                                validation_command='show running-config'
                                            )

                                            if task_id:
                                                log.info(f"Validation task created for {device_name}: {task_id}")
                                                job_name = f"stack:VALIDATION:{stack.get('name')}:{service_def.get('name')}:{device_name}:{task_id}"
                                                save_task_id(task_id, device_name=job_name)
                                            else:
                                                log.error(f"Validation failed for {device_name}: no task_id returned")
    
                                    except Exception as svc_err:
                                        log.error(f"Error validating service {service_def.get('name')}: {svc_err}", exc_info=True)
    
                            except Exception as validate_err:
                                log.error(f"Error in scheduled stack validation: {validate_err}", exc_info=True)
    
                        elif operation_type == 'delete':
                            # Delete the stack
                            log.info(f"Deleting stack {stack_id} via scheduled operation")
                            try:
                                stack = get_service_stack(stack_id)
                                if not stack:
                                    log.error(f"Stack {stack_id} not found for scheduled deletion")
                                    continue
    
                                # Delete each service in reverse order (respects dependencies)
                                services = stack.get('services', [])
                                log.info(f"Stack {stack_id} has {len(services)} services to delete")
    
                                # Sort by order in reverse
                                services_sorted = sorted(services, key=lambda s: s.get('order', 0), reverse=True)
    
                                for service_def in services_sorted:
                                    try:
                                        log.info(f"Scheduled deletion: deleting service {service_def.get('name')}")
    
                                        # Get devices - handle both 'device' (singular) and 'devices' (plural)
                                        devices = service_def.get('devices', [])
                                        if not devices and 'device' in service_def:
                                            devices = [service_def['device']]
    
                                        if not devices:
                                            log.warning(f"No devices configured for service {service_def.get('name')}, skipping deletion")
                                            continue
    
                                        template_name = service_def.get('template')
                                        if not template_name:
                                            log.warning(f"Service {service_def.get('name')} has no template, skipping deletion")
                                            continue
    
                                        # Get template metadata to check for delete template
                                        template_metadata = get_template_metadata(template_name)
                                        delete_template = template_metadata.get('delete_template')
    
                                        if not delete_template:
                                            log.warning(f"No delete template configured for {template_name}, skipping deletion")
                                            continue
    
                                        # Merge variables
                                        variables = {**stack.get('shared_variables', {}), **service_def.get('variables', {})}
    
                                        # Deploy delete template to each device
                                        for device_name in devices:
                                            log.info(f"Scheduled deletion: deploying delete template to {device_name}")
    
                                            # Get device connection info
                                            device_info = get_device_connection_info(device_name, None)
                                            if not device_info:
                                                log.error(f"Could not get connection info for device '{device_name}'")
                                                continue
    
                                            # Add default credentials from settings
                                            settings = get_settings()
                                            if settings.get('default_username'):
                                                device_info['connection_args']['username'] = settings['default_username']
                                                device_info['connection_args']['password'] = settings.get('default_password', '')
    
                                            # Render delete template locally
                                            rendered_config = render_j2_template(delete_template, variables)
                                            if not rendered_config:
                                                log.error(f"Failed to render delete template '{delete_template}' for {device_name}")
                                                continue

                                            # Deploy delete template using Celery
                                            config_lines = [cmd.strip() for cmd in rendered_config.split('\n') if cmd.strip()]

                                            task_id = celery_device_service.execute_set_config(
                                                connection_args=device_info['connection_args'],
                                                config_lines=config_lines,
                                                save_config=True
                                            )

                                            if task_id:
                                                log.info(f"Delete task created for {device_name}: {task_id}")
                                                # Save task ID to history so it appears in Job Monitor with standardized format
                                                # Format: stack:DELETE:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                                                job_name = f"stack:DELETE:{stack.get('name')}:{service_def.get('name')}:{device_name}:{task_id}"
                                                save_task_id(task_id, device_name=job_name)
                                            else:
                                                log.error(f"Delete task creation failed for {device_name}")
    
                                    except Exception as svc_err:
                                        log.error(f"Error deleting service {service_def.get('name')}: {svc_err}", exc_info=True)
    
                                # After all delete templates deployed, delete the stack record
                                delete_service_stack(stack_id)
                                log.info(f"Stack {stack_id} deleted successfully")
    
                            except Exception as delete_err:
                                log.error(f"Error in scheduled stack deletion: {delete_err}", exc_info=True)
                        elif operation_type == 'config_deploy':
                            # Execute config deployment
                            import json
                            config_data_str = schedule.get('config_data')
                            if config_data_str:
                                config_data = json.loads(config_data_str)
                                deploy_type = config_data.get('type')
    
                                log.info(f"Executing scheduled {deploy_type} deployment")
    
                                # Execute the deployment
                                if deploy_type == 'setconfig':
                                    devices = config_data.get('devices', [])
                                    config_commands = config_data.get('config', '').split('\n')
                                    config_commands = [cmd.strip() for cmd in config_commands if cmd.strip()]
                                    username = config_data.get('username')
                                    password = config_data.get('password')
                                    dry_run = config_data.get('dry_run', False)
    
                                    log.info(f"Scheduled setconfig: {len(devices)} devices, {len(config_commands)} commands")
    
                                    # Deploy to each device
                                    for device_name in devices:
                                        try:
                                            # Get device connection info from Netbox
                                            netbox_client = get_netbox_client()
                                            device = netbox_client.get_device_by_name(device_name)
    
                                            if not device:
                                                log.error(f"Device {device_name} not found for scheduled deployment")
                                                continue
    
                                            # Get device type
                                            nornir_platform = device.get('config_context', {}).get('nornir', {}).get('platform')
                                            if not nornir_platform:
                                                platform = device.get('platform', {})
                                                manufacturer = device.get('device_type', {}).get('manufacturer', {})
                                                platform_name = platform.get('name') if isinstance(platform, dict) else None
                                                manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None
                                                from netbox_client import get_netmiko_device_type
                                                nornir_platform = get_netmiko_device_type(platform_name, manufacturer_name)
    
                                            # Get IP address
                                            primary_ip = device.get('primary_ip', {}) or device.get('primary_ip4', {})
                                            ip_address = None
                                            if primary_ip:
                                                ip_addr_full = primary_ip.get('address', '')
                                                ip_address = ip_addr_full.split('/')[0] if ip_addr_full else None
    
                                            if not ip_address:
                                                log.error(f"No IP address found for device {device_name}")
                                                continue
    
                                            # Build connection args
                                            connection_args = {
                                                'device_type': nornir_platform or 'cisco_ios',
                                                'host': ip_address,
                                                'username': username,
                                                'password': password,
                                                'timeout': 10
                                            }

                                            # Deploy via Celery (dry_run not supported in Celery - skip if dry_run)
                                            if dry_run:
                                                log.info(f"Dry run mode - skipping actual deployment to {device_name}")
                                                continue

                                            task_id = celery_device_service.execute_set_config(
                                                connection_args=connection_args,
                                                config_lines=config_commands,
                                                save_config=True
                                            )

                                            # Save task ID
                                            if task_id:
                                                save_task_id(task_id, device_name)
                                                log.info(f"Scheduled setconfig deployed to {device_name}, task: {task_id}")
    
                                        except Exception as e:
                                            log.error(f"Error deploying scheduled setconfig to {device_name}: {e}")
    
                                elif deploy_type == 'template':
                                    devices = config_data.get('devices', [])
                                    template_name = config_data.get('template_name')
                                    variables = config_data.get('variables', {})
                                    username = config_data.get('username')
                                    password = config_data.get('password')
                                    dry_run = config_data.get('dry_run', False)

                                    log.info(f"Scheduled template deploy: {template_name} to {len(devices)} devices")

                                    try:
                                        # Render template locally
                                        rendered_config = render_j2_template(template_name, variables)

                                        if not rendered_config:
                                            log.error(f"Failed to render template {template_name}")
                                        else:
                                            # Split into commands
                                            config_commands = [cmd.strip() for cmd in rendered_config.split('\n') if cmd.strip()]

                                            # Deploy to each device
                                            for device_name in devices:
                                                try:
                                                    # Get device connection info from Netbox
                                                    netbox_client = get_netbox_client()
                                                    device = netbox_client.get_device_by_name(device_name)

                                                    if not device:
                                                        log.error(f"Device {device_name} not found for scheduled deployment")
                                                        continue

                                                    # Get device type
                                                    nornir_platform = device.get('config_context', {}).get('nornir', {}).get('platform')
                                                    if not nornir_platform:
                                                        platform = device.get('platform', {})
                                                        manufacturer = device.get('device_type', {}).get('manufacturer', {})
                                                        platform_name = platform.get('name') if isinstance(platform, dict) else None
                                                        manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None
                                                        from netbox_client import get_netmiko_device_type
                                                        nornir_platform = get_netmiko_device_type(platform_name, manufacturer_name)

                                                    # Get IP address
                                                    primary_ip = device.get('primary_ip', {}) or device.get('primary_ip4', {})
                                                    ip_address = None
                                                    if primary_ip:
                                                        ip_addr_full = primary_ip.get('address', '')
                                                        ip_address = ip_addr_full.split('/')[0] if ip_addr_full else None

                                                    if not ip_address:
                                                        log.error(f"No IP address found for device {device_name}")
                                                        continue

                                                    # Skip if dry run mode
                                                    if dry_run:
                                                        log.info(f"Dry run mode - skipping actual deployment to {device_name}")
                                                        continue

                                                    # Build connection args
                                                    connection_args = {
                                                        'device_type': nornir_platform or 'cisco_ios',
                                                        'host': ip_address,
                                                        'username': username,
                                                        'password': password,
                                                        'timeout': 10
                                                    }

                                                    # Deploy via Celery
                                                    task_id = celery_device_service.execute_set_config(
                                                        connection_args=connection_args,
                                                        config_lines=config_commands,
                                                        save_config=True
                                                    )

                                                    # Save task ID
                                                    if task_id:
                                                        save_task_id(task_id, device_name)
                                                        log.info(f"Scheduled template deployed to {device_name}, task: {task_id}")

                                                except Exception as e:
                                                    log.error(f"Error deploying scheduled template to {device_name}: {e}")

                                    except Exception as e:
                                        log.error(f"Error rendering template {template_name}: {e}")
                            else:
                                log.warning(f"No config_data for scheduled operation {schedule_id}")
    
                        # Update last_run and run_count
                        now = dt.now()  # Use local time instead of UTC
                        run_count = schedule.get('run_count', 0) + 1
                        update_scheduled_operation(schedule_id, last_run=now.isoformat(), run_count=run_count)
    
                        # Calculate next_run for recurring schedules
                        if schedule_type != 'once':
                            time_parts = schedule['scheduled_time'].split(':')
                            hour = int(time_parts[0])
                            minute = int(time_parts[1])
    
                            if schedule_type == 'daily':
                                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                if next_run <= now:
                                    next_run += timedelta(days=1)
                            elif schedule_type == 'weekly':
                                day_of_week = schedule['day_of_week']
                                days_ahead = day_of_week - now.weekday()
                                if days_ahead <= 0:
                                    days_ahead += 7
                                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
                            elif schedule_type == 'monthly':
                                day_of_month = schedule['day_of_month']
                                next_run = now.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
                                if next_run <= now:
                                    if now.month == 12:
                                        next_run = next_run.replace(year=now.year + 1, month=1)
                                    else:
                                        next_run = next_run.replace(month=now.month + 1)
    
                            update_scheduled_operation(schedule_id, next_run=next_run.isoformat())
                        else:
                            # One-time schedule, disable it
                            update_scheduled_operation(schedule_id, enabled=0)
    
                        log.info(f"Successfully executed scheduled operation: {schedule_id}")

                    except Exception as e:
                        log.error(f"Error executing scheduled operation {schedule.get('schedule_id')}: {e}", exc_info=True)

            except Exception as e:
                log.error(f"Error in scheduled operations thread loop: {e}", exc_info=True)
                print(f"EXCEPTION IN SCHEDULER LOOP: {e}", flush=True)
                import traceback
                traceback.print_exc()
    except Exception as e:
        log.error(f"FATAL: Scheduler thread crashed before entering loop: {e}", exc_info=True)
        print(f"FATAL SCHEDULER EXCEPTION: {e}", flush=True)
        import traceback
        traceback.print_exc()
# Start scheduler thread only once (not in Flask reloader parent process)
import os

def test_thread():
    print("TEST THREAD STARTED!", flush=True)
    for i in range(5):
        print(f"Test thread iteration {i}", flush=True)
        time_module.sleep(1)

# Always start scheduler thread
print(f"App module loaded - WERKZEUG_RUN_MAIN={os.environ.get('WERKZEUG_RUN_MAIN')}", flush=True)
print("Starting scheduler thread unconditionally...", flush=True)

# Test thread first
test_thread_obj = threading.Thread(target=test_thread, daemon=True)
test_thread_obj.start()

scheduler_thread = threading.Thread(target=run_scheduled_operations, daemon=True)
scheduler_thread.start()
log.info("Scheduler thread started")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088, debug=True)
