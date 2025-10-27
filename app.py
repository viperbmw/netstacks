"""
NetStacks - Web-based Service Stack Management for Network Automation
Connects to Netstacker API for network device automation
"""
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from functools import wraps
import requests
import os
import logging
import json
import base64
import uuid
import time
import hashlib
import secrets
from datetime import datetime
from netbox_client import NetboxClient
from jinja2 import Template, TemplateSyntaxError
import database as db
import auth_ldap
import auth_oidc

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'netstacks-secret-key')

# Register API documentation blueprint
try:
    from api_docs import api_bp
    app.register_blueprint(api_bp)
    log = logging.getLogger(__name__)
    log.info("API documentation blueprint registered at /api/docs")
except Exception as e:
    logging.error(f"Failed to register API docs blueprint: {e}")

# Configuration
NETSTACKER_API_URL = os.environ.get('NETSTACKER_API_URL', 'http://netstacker-controller:9000')
NETSTACKER_API_KEY = os.environ.get('NETSTACKER_API_KEY', '2a84465a-cf38-46b2-9d86-b84Q7d57f288')
NETBOX_URL = os.environ.get('NETBOX_URL', 'https://netbox.example.com')
NETBOX_TOKEN = os.environ.get('NETBOX_TOKEN', '')
VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() == 'true'
TASK_HISTORY_FILE = os.environ.get('TASK_HISTORY_FILE', '/tmp/netstacks_tasks.json')
# Database initialized in database.py
# Templates are stored in Netstacker - no local template directory needed

# Setup logging first
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Headers for netstacker API calls
NETSTACKER_HEADERS = {
    'x-api-key': NETSTACKER_API_KEY,
    'Content-Type': 'application/json'
}

# Note: Netbox client is now initialized dynamically via get_netbox_client()
# This allows settings to be changed via the GUI without restarting

# Initialize SQLite database
db.init_db()
log.info("SQLite database initialized")

# Load settings from database and update globals on startup
try:
    stored_settings = db.get_all_settings()
    if stored_settings:
        NETSTACKER_API_URL = stored_settings.get('netstacker_url', NETSTACKER_API_URL).rstrip('/')
        NETSTACKER_API_KEY = stored_settings.get('netstacker_api_key', NETSTACKER_API_KEY)
        NETSTACKER_HEADERS = {
            'x-api-key': NETSTACKER_API_KEY,
            'Content-Type': 'application/json'
        }
        log.info("Loaded Netstacker settings from database")
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


# Device list cache
device_cache = {
    'devices': None,
    'timestamp': None,
    'ttl': 300  # 5 minutes
}


# Task history management
def save_task_id(task_id, device_name=None):
    """Save a task ID to the history file with device name

    Args:
        task_id: The Netstacker task ID
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
        'netstacker_url': '',
        'netstacker_api_key': '',
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
                device_info = get_device_connection_info(device, credential_override)
                if not device_info:
                    log.error(f"Could not get connection info for device {device}")
                    # Still delete from database
                    result = db.delete_service_instance(service_id)
                    return {'success': True, 'warning': 'Deleted from database but could not connect to device'}

                # Strip .j2 extension if present - Netstacker stores templates without extension
                template_name_clean = delete_template[:-3] if delete_template.endswith('.j2') else delete_template
                log.info(f"Deploying delete template '{template_name_clean}' via Netstacker with variables: {variables}")

                # Use Netstacker's setconfig with j2config at top level
                # This tells Netstacker to render the J2 template and deploy it in one operation
                payload = {
                    'library': 'netmiko',
                    'connection_args': device_info['connection_args'],
                    'j2config': {
                        'template': template_name_clean,
                        'args': variables
                    },
                    'queue_strategy': 'fifo'
                }

                log.info(f"Payload: {payload}")
                response = requests.post(
                    f'{NETSTACKER_API_URL}/setconfig',
                    json=payload,
                    headers=NETSTACKER_HEADERS,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()

                task_id = result.get('data', {}).get('task_id')
                log.info(f"Delete template deployed for service {service_id}, task_id: {task_id}")

                # Save task ID to monitor with standardized format
                if task_id:
                    # Get stack name for standardized format
                    stack_name = "N/A"
                    if service.get('stack_id'):
                        stack = get_service_stack(service['stack_id'])
                        if stack:
                            stack_name = stack.get('name', 'N/A')

                    # Extract service name (remove device suffix if present)
                    service_name = service.get('name', 'N/A')
                    if ' (' in service_name:
                        service_name = service_name.split(' (')[0]

                    # Format: stack:DELETE:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                    job_name = f"stack:DELETE:{stack_name}:{service_name}:{device}:{task_id}"
                    save_task_id(task_id, device_name=job_name)
                    log.info(f"Saved delete task {task_id} to task history")

                # Delete from database after successful job submission to Netstacker
                db.delete_service_instance(service_id)

                return {'success': True, 'task_id': task_id, 'message': 'Delete template deployed successfully'}

            except Exception as e:
                log.error(f"Error deploying delete template for service {service_id}: {e}")
                # Still delete from database
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
    """Render a Jinja2 template using Netstacker's template system"""
    try:
        # Call Netstacker's j2template render endpoint
        response = requests.post(
            f'{NETSTACKER_API_URL}/j2template/render/config/{template_name}',
            json=variables,
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Extract rendered config from response
        task_result = result.get('data', {}).get('task_result', {})
        rendered = task_result.get('template_render_result', '') if isinstance(task_result, dict) else task_result

        return rendered

    except Exception as e:
        log.error(f"Error rendering template {template_name}: {e}")
        return None


def render_local_j2_template(template_name, variables):
    """Render a Jinja2 template locally using template content from Netstacker

    This is used for validation templates. We fetch the template content from Netstacker
    and render it locally in NetStacks so we can compare against device config.
    """
    try:
        from jinja2 import Environment, BaseLoader

        # Fetch template content from Netstacker
        # Template names in Netstacker are stored without .j2 extension
        template_lookup = template_name[:-3] if template_name.endswith('.j2') else template_name

        log.info(f"Fetching template content from Netstacker: {template_lookup}")
        response = requests.get(
            f'{NETSTACKER_API_URL}/j2template/config/{template_lookup}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Extract template content from response
        # Netstacker returns templates as base64 encoded
        template_data = result.get('data', {}).get('task_result', {})
        base64_payload = template_data.get('base64_payload', '')

        if not base64_payload:
            log.error(f"No template content found for: {template_lookup}")
            log.error(f"Response data: {template_data}")
            return None

        # Decode base64 template
        import base64
        template_content = base64.b64decode(base64_payload).decode('utf-8')
        log.info(f"Retrieved and decoded template content: {len(template_content)} bytes")
        log.info(f"Rendering locally with variables: {variables}")

        # Render the template locally using Jinja2
        env = Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            lstrip_blocks=True
        )

        template = env.from_string(template_content)
        rendered = template.render(**variables)

        log.info(f"Successfully rendered template locally")
        return rendered

    except Exception as e:
        log.error(f"Error rendering local template {template_name}: {e}", exc_info=True)
        return None




def get_device_connection_info(device_name, credential_override=None):
    """Get device connection info from Netbox or cache"""
    try:
        device = None

        # Try to get device from cache first (faster and more reliable)
        # device_cache is a dict, iterate through all cache entries
        if device_cache:
            for cache_key, cache_entry in device_cache.items():
                if cache_entry and isinstance(cache_entry, dict) and 'devices' in cache_entry:
                    cached_devices = cache_entry.get('devices', [])
                    if cached_devices:
                        device = next((d for d in cached_devices if d.get('name') == device_name), None)
                        if device:
                            log.info(f"Found device {device_name} in cache (key: {cache_key})")
                            break

        # Fallback to Netbox if not in cache
        if not device:
            log.info(f"Device {device_name} not in cache, fetching from Netbox")
            netbox = get_netbox_client()
            device = netbox.get_device_by_name(device_name)

        if not device or not device.get('name'):
            log.error(f"Device {device_name} not found in Netbox or cache")
            return None

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
        host = None
        if primary_ip:
            ip_addr_full = primary_ip.get('address', '')
            # Remove CIDR notation if present
            host = ip_addr_full.split('/')[0] if ip_addr_full else None

        # Fallback to device name if no IP
        if not host:
            host = device_name

        # Build connection args
        connection_args = {
            'device_type': nornir_platform or 'cisco_ios',  # Default to cisco_ios
            'host': host,
            'timeout': 30
        }

        # Add credentials from override if provided
        if credential_override:
            connection_args['username'] = credential_override.get('username')
            connection_args['password'] = credential_override.get('password')
            log.info(f"Applied credential override for device {device_name} (username: {credential_override.get('username')})")

        platform_info = device.get('platform', {})
        platform_name = platform_info.get('name') if isinstance(platform_info, dict) else ''

        return {
            'connection_args': connection_args,
            'device_info': {
                'name': device.get('name'),
                'platform': platform_name,
                'site': device.get('site', {}).get('name') if device.get('site') else None
            }
        }

    except Exception as e:
        log.error(f"Error getting device connection info for {device_name}: {e}", exc_info=True)
        return None


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


@app.context_processor
def inject_netstacker_url():
    """Inject Netstacker URL from settings into all templates"""
    try:
        settings = db.get_all_settings()
        netstacker_url = settings.get('netstacker_url', 'http://localhost:9000')
        return {'netstacker_url': netstacker_url}
    except Exception as e:
        log.error(f"Error loading Netstacker URL: {e}")
        return {'netstacker_url': 'http://localhost:9000'}


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


@app.route('/network-map')
@login_required
def network_map():
    """Network map visualization page"""
    return render_template('network-map.html')


@app.route('/mop')
@login_required
def mop():
    """Method of Procedures (MOP) page"""
    return render_template('mop.html')


@app.route('/workflows')
@login_required
def workflows():
    """Workflows page (YAML-based workflow engine)"""
    return render_template('workflows.html')


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
            'netstacker_url': settings.get('netstacker_url'),
            'netstacker_api_key': '****' if settings.get('netstacker_api_key') else '',  # Masked
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
    """Save settings to database and update global variables"""
    try:
        global NETSTACKER_API_URL, NETSTACKER_API_KEY, NETSTACKER_HEADERS

        data = request.json

        log.info(f"[SETTINGS] Received settings save request")
        log.info(f"[SETTINGS] default_username in request: {data.get('default_username', 'NOT PRESENT')}")
        log.info(f"[SETTINGS] default_password in request: {'***' if data.get('default_password') else 'NOT PRESENT/EMPTY'}")

        # Validate required fields
        required_fields = ['netstacker_url', 'netbox_url']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400

        # Prepare settings to save
        settings_to_save = {
            'netstacker_url': data.get('netstacker_url'),
            'netstacker_api_key': data.get('netstacker_api_key'),
            'netbox_url': data.get('netbox_url'),
            'netbox_token': data.get('netbox_token'),
            'verify_ssl': data.get('verify_ssl', False),
            'netbox_filters': data.get('netbox_filters', []),
            'cache_ttl': data.get('cache_ttl', 300),
            'default_username': data.get('default_username', ''),
            'default_password': data.get('default_password', ''),
            'system_timezone': data.get('system_timezone', 'UTC')
        }

        log.info(f"[SETTINGS] Saving default_username: {settings_to_save['default_username']}")
        log.info(f"[SETTINGS] Saving netbox_filters: {settings_to_save['netbox_filters']}")

        # Save to database
        save_settings(settings_to_save)

        # Update global variables so all endpoints use new settings immediately
        NETSTACKER_API_URL = settings_to_save['netstacker_url'].rstrip('/')
        NETSTACKER_API_KEY = settings_to_save['netstacker_api_key']
        NETSTACKER_HEADERS = {
            'x-api-key': NETSTACKER_API_KEY,
            'Content-Type': 'application/json'
        }

        log.info(f"Settings saved successfully and globals updated")
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        log.error(f"Error saving settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api-docs')
@login_required
def api_docs():
    """Redirect to Netstacker API documentation using configured Netstacker URL"""
    # Use the Netstacker URL from settings (configured via GUI) exactly as entered
    if NETSTACKER_API_URL:
        return redirect(f'{NETSTACKER_API_URL}/', code=302)
    else:
        return jsonify({'error': 'Netstacker URL not configured. Please configure via /settings'}), 400


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
    """Get device list from manual devices and Netbox (if configured)"""
    try:
        # Get filters from request if provided (POST body or query params)
        filters = []
        if request.method == 'POST' and request.json:
            filter_list = request.json.get('filters', [])
            # Keep as list to support multiple values for same key
            for f in filter_list:
                if 'key' in f and 'value' in f:
                    filters.append({'key': f['key'], 'value': f['value']})

        # Create cache key based on filters
        cache_key = json.dumps({'filters': filters}, sort_keys=True)

        # Check cache (with filter-specific key)
        now = datetime.now().timestamp()
        cache_entry = device_cache.get(cache_key, {})
        if (cache_entry.get('devices') is not None and
            cache_entry.get('timestamp') is not None and
            (now - cache_entry['timestamp']) < device_cache.get('ttl', 300)):
            log.info(f"Returning cached device list ({len(cache_entry['devices'])} devices)")
            return jsonify({'success': True, 'devices': cache_entry['devices'], 'cached': True})

        # Fetch devices from all available sources
        all_devices = []
        sources_used = []

        # Always fetch manual devices
        log.info(f"Fetching manual devices...")
        manual_devices = db.get_all_manual_devices()
        # Format manual devices to match Netbox device structure
        for device in manual_devices:
            all_devices.append({
                'name': device['device_name'],
                'device_type': device['device_type'],
                'primary_ip': device['host'],
                'site': 'Manual',
                'status': 'Active',
                'source': 'manual'
            })
        log.info(f"Found {len(manual_devices)} manual devices")
        if len(manual_devices) > 0:
            sources_used.append('manual')

        # Try to fetch Netbox devices if configured
        settings = get_settings()
        netbox_url = settings.get('netbox_url', '').strip()
        netbox_token = settings.get('netbox_token', '').strip()

        if netbox_url and netbox_token:
            try:
                log.info(f"Fetching device list from Netbox with filters: {filters}...")
                netbox_client = get_netbox_client()
                netbox_devices = netbox_client.get_devices_with_details(filters=filters)
                # Mark Netbox devices with source
                for device in netbox_devices:
                    device['source'] = 'netbox'
                all_devices.extend(netbox_devices)
                log.info(f"Found {len(netbox_devices)} Netbox devices")
                if len(netbox_devices) > 0:
                    sources_used.append('netbox')
            except Exception as netbox_error:
                log.warning(f"Could not fetch devices from Netbox: {netbox_error}")
                # Continue with manual devices only
        else:
            log.info("Netbox not configured, using manual devices only")

        # Update cache with filter-specific key
        device_cache[cache_key] = {
            'devices': all_devices,
            'timestamp': now
        }

        sources_str = ', '.join(sources_used) if sources_used else 'none'
        log.info(f"Cached {len(all_devices)} total devices from sources: {sources_str}")
        return jsonify({'success': True, 'devices': all_devices, 'cached': False, 'sources': sources_used})
    except Exception as e:
        log.error(f"Error fetching devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/devices/clear-cache', methods=['POST'])
@login_required
def clear_device_cache():
    """Clear the device cache"""
    try:
        global device_cache
        device_cache.clear()
        device_cache['ttl'] = 300  # Restore TTL
        log.info("Device cache cleared")
        return jsonify({'success': True, 'message': 'Cache cleared successfully'})
    except Exception as e:
        log.error(f"Error clearing cache: {e}")
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


@app.route('/api/test-netstacker', methods=['POST'])
@login_required
def test_netstacker_connection():
    """Test Netstacker API connection with provided credentials"""
    try:
        import time

        data = request.json
        netstacker_url = data.get('netstacker_url', '').strip()
        netstacker_api_key = data.get('netstacker_api_key', '').strip()

        if not netstacker_url:
            return jsonify({'success': False, 'error': 'Netstacker URL is required'}), 400

        if not netstacker_api_key:
            return jsonify({'success': False, 'error': 'Netstacker API key is required'}), 400

        # Build the test URL (check workers endpoint as a simple test)
        test_url = f"{netstacker_url.rstrip('/')}/workers"

        log.info(f"Testing Netstacker connection to: {test_url}")

        # Prepare headers
        test_headers = {
            'x-api-key': netstacker_api_key,
            'Content-Type': 'application/json'
        }

        # Measure response time
        start_time = time.time()

        # Try to fetch workers (simple read-only endpoint)
        response = requests.get(
            test_url,
            headers=test_headers,
            timeout=10
        )

        response_time = round((time.time() - start_time) * 1000, 2)  # Convert to ms

        if response.status_code == 200:
            result = response.json()

            # Try to extract workers from different possible response structures
            workers = None
            if isinstance(result, dict):
                # Try nested structure: data.task_result
                workers = result.get('data', {})
                if isinstance(workers, dict):
                    workers = workers.get('task_result', [])
                # If data itself is a list, use it directly
                elif isinstance(result.get('data'), list):
                    workers = result.get('data')
            elif isinstance(result, list):
                # Response is a list directly
                workers = result

            # Count workers
            worker_count = len(workers) if isinstance(workers, list) else 0

            log.info(f"Netstacker test successful: {worker_count} workers found")

            return jsonify({
                'success': True,
                'worker_count': worker_count,
                'response_time': response_time,
                'message': 'Successfully connected to Netstacker API',
                'api_url': test_url,
                'has_api_key': bool(netstacker_api_key)
            })
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Check your Netstacker API key.',
                'api_url': test_url,
                'status_code': response.status_code
            }), 401
        else:
            return jsonify({
                'success': False,
                'error': f'Netstacker API returned status code {response.status_code}',
                'api_url': test_url,
                'status_code': response.status_code,
                'details': response.text[:200]
            }), 500

    except requests.exceptions.ConnectionError as e:
        log.error(f"Connection Error testing Netstacker: {e}")
        return jsonify({
            'success': False,
            'error': 'Could not connect to Netstacker. Check the URL and network connectivity.',
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500
    except requests.exceptions.Timeout as e:
        log.error(f"Timeout testing Netstacker: {e}")
        return jsonify({
            'success': False,
            'error': 'Connection to Netstacker timed out after 10 seconds.',
            'api_url': test_url if 'test_url' in locals() else 'N/A'
        }), 500
    except Exception as e:
        log.error(f"Error testing Netstacker connection: {e}")
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
    """Get all tasks - combines queue and history, sorted by creation time (newest first)"""
    try:
        # Get currently queued tasks from netstacker
        response = requests.get(f'{NETSTACKER_API_URL}/taskqueue/', headers=NETSTACKER_HEADERS, timeout=5)
        response.raise_for_status()
        queued_data = response.json()

        # Get task history from our local store
        history = get_task_history()

        # Build map of task_id to creation time
        task_times = {}
        for item in history:
            task_id = item.get('task_id')
            created = item.get('created', '1970-01-01T00:00:00')
            if task_id:
                task_times[task_id] = created

        # Get all unique task IDs
        all_task_ids = list(set(queued_data.get('data', {}).get('task_id', [])))

        # Add historical tasks not in queue
        for item in history:
            task_id = item['task_id']
            if task_id not in all_task_ids:
                all_task_ids.append(task_id)

        # Sort by creation time (newest first)
        sorted_tasks = sorted(
            all_task_ids,
            key=lambda tid: task_times.get(tid, '9999-99-99T99:99:99'),
            reverse=True
        )

        # Return in same format as netstacker
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
    """Get specific task details"""
    try:
        response = requests.get(f'{NETSTACKER_API_URL}/task/{task_id}', headers=NETSTACKER_HEADERS, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        log.error(f"Error fetching task {task_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workers')
@login_required
def get_workers():
    """Get all workers from netstacker"""
    try:
        response = requests.get(f'{NETSTACKER_API_URL}/workers', headers=NETSTACKER_HEADERS, timeout=5)
        response.raise_for_status()

        # Return the data in a consistent format
        result = response.json()
        if isinstance(result, list):
            return jsonify(result)
        elif isinstance(result, dict) and 'data' in result:
            data = result['data']
            if isinstance(data, dict) and 'task_result' in data:
                return jsonify(data['task_result'])
            return jsonify(data)
        return jsonify(result)
    except Exception as e:
        log.error(f"Error fetching workers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/getconfig', methods=['POST'])
@login_required
def deploy_getconfig():
    """Deploy getconfig to device"""
    try:
        data = request.json
        log.info(f"Received getconfig request: {data}")

        # Extract device name if provided
        device_name = data.get('device_name')

        # Forward request to netstacker
        library = data.get('library', 'netmiko')
        endpoint = f'/getconfig/{library}' if library != 'auto' else '/getconfig'

        payload = data.get('payload')
        log.info(f"Sending to netstacker {NETSTACKER_API_URL}{endpoint}: {payload}")

        response = requests.post(
            f'{NETSTACKER_API_URL}{endpoint}',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=30
        )

        log.info(f"Netstacker response status: {response.status_code}")
        log.info(f"Netstacker response body: {response.text}")

        response.raise_for_status()
        result = response.json()

        # Save task ID to history with device name
        if result.get('status') == 'success' and result.get('data', {}).get('task_id'):
            save_task_id(result['data']['task_id'], device_name)

        return jsonify(result)
    except Exception as e:
        log.error(f"Error deploying getconfig: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/setconfig', methods=['POST'])
@login_required
def deploy_setconfig():
    """Deploy setconfig to device"""
    try:
        data = request.json

        # Extract device name if provided
        device_name = data.get('device_name')

        # Forward request to netstacker
        library = data.get('library', 'netmiko')
        endpoint = f'/setconfig/{library}' if library != 'auto' else '/setconfig'

        response = requests.post(
            f'{NETSTACKER_API_URL}{endpoint}',
            json=data.get('payload'),
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        # Save task ID to history with device name
        if result.get('status') == 'success' and result.get('data', {}).get('task_id'):
            save_task_id(result['data']['task_id'], device_name)

        return jsonify(result)
    except Exception as e:
        log.error(f"Error deploying setconfig: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/deploy/setconfig/dry-run', methods=['POST'])
@login_required
def deploy_setconfig_dryrun():
    """Deploy setconfig dry-run to device"""
    try:
        data = request.json

        response = requests.post(
            f'{NETSTACKER_API_URL}/setconfig/dry-run',
            json=data.get('payload'),
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        log.error(f"Error deploying dry-run: {e}")
        return jsonify({'error': str(e)}), 500


# Template Management API Endpoints

@app.route('/api/templates')
@login_required
def get_templates():
    """List all J2 config templates with metadata"""
    try:
        response = requests.get(
            f'{NETSTACKER_API_URL}/j2template/config/',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Extract template list from response
        templates = result.get('data', {}).get('task_result', {}).get('templates', [])

        # Get all template metadata
        all_metadata = get_all_template_metadata()

        # Enhance template list with metadata
        enhanced_templates = []
        for template_name in templates:
            # Strip .j2 extension for lookup
            lookup_name = template_name[:-3] if template_name.endswith('.j2') else template_name

            metadata = all_metadata.get(lookup_name, {})
            enhanced_templates.append({
                'name': template_name,
                'type': metadata.get('type', 'deploy'),  # Default to deploy if not set
                'validation_template': metadata.get('validation_template'),
                'delete_template': metadata.get('delete_template'),
                'description': metadata.get('description')
            })

        return jsonify({'success': True, 'templates': enhanced_templates})
    except Exception as e:
        log.error(f"Error fetching templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/<template_name>')
@login_required
def get_template(template_name):
    """Get specific J2 template content"""
    try:
        # Strip .j2 extension if present (Netstacker adds it automatically)
        if template_name.endswith('.j2'):
            template_name_without_ext = template_name[:-3]
        else:
            template_name_without_ext = template_name

        response = requests.get(
            f'{NETSTACKER_API_URL}/j2template/config/{template_name_without_ext}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Extract base64 template content and decode
        template_data = result.get('data', {}).get('task_result', {})
        base64_content = template_data.get('base64_payload') or template_data.get('template')

        if base64_content:
            # Decode from base64
            decoded_content = base64.b64decode(base64_content).decode('utf-8')
            return jsonify({'success': True, 'content': decoded_content})
        else:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

    except Exception as e:
        log.error(f"Error fetching template {template_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates', methods=['POST'])
@login_required
def create_template():
    """Create/update J2 template - saves to Netstacker only"""
    try:
        data = request.json
        template_name = data.get('name')
        base64_payload = data.get('base64_payload')

        if not template_name or not base64_payload:
            return jsonify({'success': False, 'error': 'Missing name or base64_payload'}), 400

        # Strip .j2 extension if present (Netstacker handles this)
        if template_name.endswith('.j2'):
            template_name_no_ext = template_name[:-3]
        else:
            template_name_no_ext = template_name

        # Push to Netstacker (primary storage)
        payload = {
            'name': template_name_no_ext,
            'base64_payload': base64_payload
        }

        response = requests.post(
            f'{NETSTACKER_API_URL}/j2template/config/',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Check if netstacker returned success
        if result.get('status') == 'success':
            log.info(f"Saved template to Netstacker: {template_name_no_ext}")
            return jsonify({
                'success': True,
                'message': f'Template saved to Netstacker successfully'
            })
        else:
            error_msg = result.get('data', {}).get('task_result', {}).get('error', 'Unknown error')
            log.error(f"Netstacker save failed: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'Failed to save template: {error_msg}'
            }), 500

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
    """Delete J2 template"""
    try:
        data = request.json
        template_name = data.get('name')

        if not template_name:
            return jsonify({'success': False, 'error': 'Missing template name'}), 400

        payload = {'name': template_name}

        # Delete from Netstacker
        response = requests.delete(
            f'{NETSTACKER_API_URL}/j2template/config/',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()

        # Delete metadata from local database
        try:
            delete_template_metadata(template_name)
        except Exception as db_error:
            log.warning(f"Failed to delete template metadata for {template_name}: {db_error}")

        return jsonify({'success': True, 'message': 'Template deleted successfully'})
    except Exception as e:
        log.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/templates/<template_name>/variables')
@login_required
def get_template_variables(template_name):
    """Extract variables from J2 template"""
    try:
        # Strip .j2 extension if present (Netstacker adds it automatically)
        if template_name.endswith('.j2'):
            template_name_without_ext = template_name[:-3]
        else:
            template_name_without_ext = template_name

        # Get template content
        response = requests.get(
            f'{NETSTACKER_API_URL}/j2template/config/{template_name_without_ext}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        template_data = result.get('data', {}).get('task_result', {})
        base64_content = template_data.get('base64_payload') or template_data.get('template')

        if not base64_content:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        # Decode template
        template_content = base64.b64decode(base64_content).decode('utf-8')

        # Extract variables using regex
        import re
        # Match {{ variable_name }} patterns
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

        # Call netstacker's template render API
        payload = {
            'template_name': template_name,
            'args': variables
        }

        response = requests.post(
            f'{NETSTACKER_API_URL}/j2template/render/config/{template_name}',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Extract rendered configuration from response
        task_result = result.get('data', {}).get('task_result', {})
        rendered_config = task_result.get('template_render_result', '') or task_result.get('rendered_config', '')

        if not rendered_config:
            return jsonify({'success': False, 'error': 'No rendered configuration returned from template'}), 500

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
    """List all available service templates using helper script"""
    try:
        # Use custom script to list service templates
        payload = {
            "script": "list_service_templates",
            "args": {}
        }

        response = requests.post(
            f'{NETSTACKER_API_URL}/script',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Get the task_id and retrieve the result
        task_id = result.get('data', {}).get('task_id')
        if task_id:
            import time
            time.sleep(0.5)  # Brief wait for task to complete

            task_response = requests.get(
                f'{NETSTACKER_API_URL}/task/{task_id}',
                headers=NETSTACKER_HEADERS,
                timeout=10
            )
            task_response.raise_for_status()
            task_result = task_response.json()

            script_result = task_result.get('data', {}).get('task_result', {})
            templates = script_result.get('templates', [])

            return jsonify({'success': True, 'templates': templates})

        # Fallback to empty list
        return jsonify({'success': True, 'templates': []})
    except Exception as e:
        log.error(f"Error fetching service templates: {e}")
        # Return empty list as fallback
        return jsonify({'success': True, 'templates': []})


@app.route('/api/services/templates/<template_name>/schema')
@login_required
def get_service_template_schema(template_name):
    """Get the Pydantic model schema for a service template

    Note: This endpoint is maintained for backward compatibility.
    The template-based system now uses dynamic template variable extraction
    instead of hardcoded schemas.
    """

    # Empty schemas dictionary - using template-based system now
    service_schemas = {}

    # Check if we have a hardcoded schema (none currently)
    if template_name in service_schemas:
        return jsonify({'success': True, 'schema': service_schemas[template_name]})

    try:
        # Try to get the schema from netstacker (if it provides one)
        response = requests.get(
            f'{NETSTACKER_API_URL}/service/schema/{template_name}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            schema = result.get('data', {}).get('task_result', {})
            return jsonify({'success': True, 'schema': schema})
        else:
            # Return empty schema if not available
            return jsonify({'success': True, 'schema': None})
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

        # Push config to device using setconfig
        setconfig_payload = {
            'library': 'netmiko',
            'connection_args': device_info['connection_args'],
            'config': rendered_config.split('\n'),
            'queue_strategy': 'fifo'
        }

        response = requests.post(
            f'{NETSTACKER_API_URL}/setconfig',
            json=setconfig_payload,
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        task_id = result.get('data', {}).get('task_id')
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
    """Health check a service instance"""
    try:
        response = requests.post(
            f'{NETSTACKER_API_URL}/service/instance/healthcheck/{service_id}',
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        task_id = result.get('data', {}).get('task_id')
        if task_id:
            save_task_id(task_id, device_name=f"service_healthcheck:{service_id}")

        return jsonify({'success': True, 'task_id': task_id, 'result': result.get('data', {})})
    except Exception as e:
        log.error(f"Error health checking service instance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/redeploy', methods=['POST'])
@login_required
def redeploy_service_instance(service_id):
    """Redeploy a service instance using stored configuration"""
    try:
        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        # Check if service has template and variables
        if not service.get('template'):
            return jsonify({
                'success': False,
                'error': 'Service has no template to redeploy'
            }), 400

        # Get credentials from request if provided
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Redeploying service {service_id} to device {service.get('device')} with template {service.get('template')}")

        # Get device connection info
        credential_override = None
        if username and password:
            credential_override = {'username': username, 'password': password}

        device_info = get_device_connection_info(service['device'], credential_override)
        if not device_info:
            return jsonify({
                'success': False,
                'error': f'Could not get connection info for device: {service["device"]}'
            }), 400

        # Deploy using j2config - let Netstacker render and deploy
        deploy_response = requests.post(
            f'{NETSTACKER_API_URL}/setconfig',
            headers=NETSTACKER_HEADERS,
            json={
                'library': 'netmiko',
                'connection_args': device_info['connection_args'],
                'j2config': {
                    'template': service['template'],
                    'args': service.get('variables', {})
                },
                'queue_strategy': 'fifo'
            },
            timeout=60
        )

        if deploy_response.status_code != 201:
            raise Exception(f"Failed to deploy configuration: {deploy_response.text}")

        deploy_result = deploy_response.json()
        task_id = deploy_result.get('data', {}).get('task_id')

        if task_id:
            save_task_id(task_id, device_name=f"service_redeploy:{service_id}:{service.get('device')}")

        # Update service state to deploying (non-blocking - let Netstacker queue handle it)
        service['state'] = 'deploying'
        service['task_id'] = task_id
        if 'error' in service:
            del service['error']
        save_service_instance(service)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Service redeploy job submitted to Netstacker. Task ID: {task_id}'
        })

    except Exception as e:
        log.error(f"Error redeploying service instance: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/<service_id>/delete', methods=['POST'])
@login_required
def delete_template_service(service_id):
    """Delete a template-based service instance - removes config from device first"""
    try:
        # Get service instance
        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        # Get credentials from request if provided
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        task_id = None
        delete_template = service.get('delete_template') or service.get('reverse_template')

        # If delete template exists, use it to remove config from device
        if delete_template:
            log.info(f"Using delete template '{delete_template}' to remove service from device")

            # Get device connection info
            credential_override = None
            if username and password:
                credential_override = {'username': username, 'password': password}

            device_info = get_device_connection_info(service['device'], credential_override)
            if not device_info:
                return jsonify({
                    'success': False,
                    'error': f'Could not get connection info for device: {service["device"]}'
                }), 400

            # Add credentials
            if username and password:
                device_info['connection_args']['username'] = username
                device_info['connection_args']['password'] = password

            # Use j2config to let Netstacker render and deploy the delete template
            # Strip .j2 extension - Netstacker stores templates without extension
            template_name = delete_template[:-3] if delete_template.endswith('.j2') else delete_template

            log.info(f"Deploying delete template '{template_name}' via Netstacker with j2config")

            # Push delete config to device using j2config
            setconfig_payload = {
                'library': 'netmiko',
                'connection_args': device_info['connection_args'],
                'j2config': {
                    'template': template_name,
                    'args': service.get('variables', {})
                },
                'queue_strategy': 'fifo'
            }

            response = requests.post(
                f'{NETSTACKER_API_URL}/setconfig',
                json=setconfig_payload,
                headers=NETSTACKER_HEADERS,
                timeout=60
            )

            if response.status_code != 201:
                return jsonify({
                    'success': False,
                    'error': f'Failed to submit delete job to Netstacker: {response.text}'
                }), 500

            result = response.json()
            task_id = result.get('data', {}).get('task_id')

            if task_id:
                # Get stack name for standardized format
                stack_name = "N/A"
                if service.get('stack_id'):
                    stack = get_service_stack(service['stack_id'])
                    if stack:
                        stack_name = stack.get('name', 'N/A')

                # Extract service name (remove device suffix if present)
                service_name = service.get('name', 'N/A')
                if ' (' in service_name:
                    service_name = service_name.split(' (')[0]

                # Format: stack:DELETE:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                job_name = f"stack:DELETE:{stack_name}:{service_name}:{service.get('device', 'N/A')}:{task_id}"
                save_task_id(task_id, device_name=job_name)
                log.info(f"Delete job submitted to Netstacker, task_id: {task_id}")

            # Non-blocking: job submitted to Netstacker queue, don't wait for completion

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
                    log.info(f"Removed service {service_id} from stack {stack_id}")

        # Only delete from database after successful device cleanup
        delete_service_instance(service_id)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Service "{service["name"]}" deleted successfully',
            'stack_id': stack_id  # Return stack_id so UI can refresh stack
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

        # Check task status
        response = requests.get(
            f'{NETSTACKER_API_URL}/task/{task_id}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        task_data = response.json()

        task_status = task_data.get('data', {}).get('task_status')
        task_errors = task_data.get('data', {}).get('task_errors', [])

        # Update service state based on task status
        if task_status == 'finished' and not task_errors:
            service['state'] = 'deployed'
        elif task_status == 'failed' or task_errors:
            service['state'] = 'failed'
            service['error'] = str(task_errors) if task_errors else 'Task failed'

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
    """Validate that the service configuration exists on the device"""
    try:
        service = get_service_instance(service_id)
        if not service:
            return jsonify({'success': False, 'error': 'Service not found'}), 404

        # Check if service is in failed state
        if service.get('state') == 'failed':
            return jsonify({
                'success': False,
                'error': f"Cannot validate failed service: {service.get('error', 'Service deployment failed')}"
            }), 400

        # Check if service has template and variables (needed for validation)
        if not service.get('template'):
            return jsonify({
                'success': False,
                'error': 'Service has no template defined'
            }), 400

        # Get credentials from request if provided
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Service validation RAW request data: {data}")
        log.info(f"Validation credentials - username: {username}, has_password: {bool(password)}")

        # Get device connection info
        credential_override = None
        if username and password:
            credential_override = {'username': username, 'password': password}
            log.info(f"Using credential override for validation")

        device_info = get_device_connection_info(service['device'], credential_override)
        if not device_info:
            return jsonify({
                'success': False,
                'error': f'Could not get connection info for device: {service["device"]}'
            }), 400

        # Add credentials
        if username and password:
            device_info['connection_args']['username'] = username
            device_info['connection_args']['password'] = password
        else:
            # Use default credentials from settings
            settings = {}
            try:
                # Try to load from environment or config
                settings = {
                    'username': os.environ.get('DEFAULT_USERNAME'),
                    'password': os.environ.get('DEFAULT_PASSWORD')
                }
            except:
                pass

            if settings.get('username'):
                device_info['connection_args']['username'] = settings['username']
                device_info['connection_args']['password'] = settings['password']

        # Determine appropriate show command based on device type
        device_type = device_info['connection_args'].get('device_type', 'cisco_ios')

        if 'juniper' in device_type.lower() or 'junos' in device_type.lower():
            # For Juniper devices, use "show configuration | display set" for set format
            show_command = 'show configuration | display set'
        else:
            # For Cisco and other vendors, use standard running-config
            show_command = 'show running-config'

        # Get running config from device
        getconfig_payload = {
            'library': 'netmiko',
            'connection_args': device_info['connection_args'],
            'command': show_command,
            'queue_strategy': 'fifo'
        }

        response = requests.post(
            f'{NETSTACKER_API_URL}/getconfig',
            json=getconfig_payload,
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        task_id = result.get('data', {}).get('task_id')
        if task_id:
            # Get stack name for standardized format
            stack_name = "N/A"
            if service.get('stack_id'):
                stack = get_service_stack(service['stack_id'])
                if stack:
                    stack_name = stack.get('name', 'N/A')

            # Extract service name (remove device suffix if present)
            service_name = service.get('name', 'N/A')
            if ' (' in service_name:
                service_name = service_name.split(' (')[0]

            # Format: stack:VALIDATION:{StackName}:{ServiceName}:{DeviceName}:{JobID}
            job_name = f"stack:VALIDATION:{stack_name}:{service_name}:{service['device']}:{task_id}"
            save_task_id(task_id, device_name=job_name)

        # Poll for task completion (simple approach for now)
        import time
        max_wait = 30
        waited = 0
        running_config = None

        while waited < max_wait:
            time.sleep(2)
            waited += 2

            task_response = requests.get(
                f'{NETSTACKER_API_URL}/task/{task_id}',
                headers=NETSTACKER_HEADERS,
                timeout=10
            )
            task_response.raise_for_status()
            task_data = task_response.json()

            task_status = task_data.get('data', {}).get('task_status')
            if task_status == 'finished':
                running_config = task_data.get('data', {}).get('task_result', {})
                break
            elif task_status == 'failed':
                return jsonify({
                    'success': False,
                    'error': 'Failed to retrieve running config',
                    'task_errors': task_data.get('data', {}).get('task_errors', [])
                }), 500

        if not running_config:
            return jsonify({
                'success': False,
                'error': 'Timeout waiting for config retrieval'
            }), 500

        # Extract config - handle both dict and list formats
        running_config_lines = []

        if isinstance(running_config, dict):
            # Extract from dict (command key)
            config_text = running_config.get(show_command, '') or running_config.get('show running-config', '')
            if isinstance(config_text, list):
                running_config_lines = [line.strip() for line in config_text if line.strip()]
            else:
                running_config_lines = [line.strip() for line in config_text.split('\n') if line.strip()]
        elif isinstance(running_config, list):
            # Already a list
            running_config_lines = [line.strip() for line in running_config if isinstance(line, str) and line.strip()]
        else:
            # String format
            running_config_lines = [line.strip() for line in str(running_config).split('\n') if line.strip()]

        # Get validation config - use validation template if specified, otherwise use deployment template
        validation_template = service.get('validation_template')
        template_to_use = validation_template if validation_template else service.get('template')

        if not template_to_use:
            log.error(f"Service {service_id} has no template for validation")
            return jsonify({
                'success': False,
                'error': 'Service has no template defined for validation'
            }), 400

        # Render template LOCALLY with service variables
        # Fetch template content from Netstacker and render locally
        log.info(f"Using template for validation: {template_to_use}")
        template_lookup = template_to_use[:-3] if template_to_use.endswith('.j2') else template_to_use
        validation_config = render_local_j2_template(template_lookup, service.get('variables', {}))

        if not validation_config:
            log.error(f"Failed to render validation template: {template_lookup}")
            return jsonify({
                'success': False,
                'error': f'Template not found or failed to render: {template_to_use}'
            }), 500

        rendered_lines = [line.strip() for line in validation_config.split('\n') if line.strip()]

        # Normalize config lines for comparison - handle abbreviations and whitespace
        def normalize_config_line(line):
            """Normalize a config line for comparison"""
            # Strip all whitespace
            line = line.strip()

            # Handle common Cisco abbreviations
            line = line.replace('int ', 'interface ')
            line = line.replace('Int ', 'Interface ')

            # Normalize IP address format (remove /32 if present for comparison)
            # This helps with cases where running config shows it differently

            return line

        # Normalize both lists for comparison
        normalized_running = [normalize_config_line(line) for line in running_config_lines]
        normalized_rendered = [normalize_config_line(line) for line in rendered_lines]

        # Validate line by line - each rendered line should exist as a substring in running config
        missing_lines = []
        for i, line in enumerate(normalized_rendered):
            # Check if this line appears as a substring in any running config line
            found = False
            for running_line in normalized_running:
                if line in running_line:
                    found = True
                    break

            if not found:
                # Store the original line, not normalized
                missing_lines.append(rendered_lines[i])

        is_valid = len(missing_lines) == 0

        # Update service validation status
        service['last_validated'] = datetime.now().isoformat()
        service['validation_status'] = 'valid' if is_valid else 'invalid'
        if not is_valid:
            service['validation_errors'] = missing_lines

        save_service_instance(service)

        return jsonify({
            'success': True,
            'valid': is_valid,
            'missing_lines': missing_lines,
            'task_id': task_id,
            'message': 'Configuration is present on device' if is_valid else 'Configuration drift detected'
        })

    except Exception as e:
        log.error(f"Error validating service instance: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/instances/sync-states', methods=['POST'])
@login_required
def sync_service_instance_states():
    """Sync service instance states from Netstacker task status"""
    try:
        updated_count = 0
        failed_count = 0

        # Get all service instances in 'deploying' state
        all_services = get_all_service_instances()
        deploying_services = [s for s in all_services if s.get('state') == 'deploying']

        log.info(f"Found {len(deploying_services)} services in deploying state")

        for service in deploying_services:
            task_id = service.get('task_id')
            if not task_id:
                continue

            try:
                # Query Netstacker for task status
                response = requests.get(
                    f'{NETSTACKER_API_URL}/task/{task_id}',
                    headers=NETSTACKER_HEADERS,
                    timeout=10
                )

                if response.status_code == 200:
                    task_data = response.json().get('data', {})
                    task_status = task_data.get('task_status')

                    if task_status == 'finished':
                        # Update to deployed
                        service['state'] = 'deployed'
                        service['deployed_at'] = datetime.now().isoformat()
                        save_service_instance(service)
                        updated_count += 1
                        log.info(f"Updated service {service.get('service_id')} to deployed")

                    elif task_status == 'failed':
                        # Update to failed
                        service['state'] = 'failed'
                        service['error'] = task_data.get('task_errors', 'Deployment failed')
                        save_service_instance(service)
                        failed_count += 1
                        log.info(f"Updated service {service.get('service_id')} to failed")

            except Exception as e:
                log.error(f"Error syncing service {service.get('service_id')}: {e}")
                continue

        # Update stack states based on service states
        stacks_updated = set()
        for service in deploying_services:
            stack_id = service.get('stack_id')
            if stack_id and stack_id not in stacks_updated:
                # Get all services for this stack
                stack_services = [s for s in all_services if s.get('stack_id') == stack_id]

                # Calculate stack state based on service states
                states = [s.get('state') for s in stack_services]

                if all(state == 'deployed' for state in states):
                    new_state = 'deployed'
                elif any(state == 'failed' for state in states):
                    new_state = 'partial' if any(state == 'deployed' for state in states) else 'failed'
                elif any(state == 'deploying' for state in states):
                    new_state = 'deploying'
                else:
                    new_state = 'pending'

                # Update stack state
                stack = get_service_stack(stack_id)
                if stack and stack.get('state') != new_state:
                    stack['state'] = new_state
                    db.save_service_stack(stack)
                    log.info(f"Updated stack {stack_id} state to {new_state}")
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
            log.warning(f"No credentials provided in deployment request!")

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

                # Use template name without .j2 extension (Netstacker stores templates without extension)
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

                        log.info(f"Deploying template to {device_name} via Netstacker (template or variables changed)")

                        # Log the exact payload being sent
                        payload = {
                            'library': 'netmiko',
                            'connection_args': device_info['connection_args'],
                            'j2config': {
                                'template': template_name,
                                'args': variables
                            },
                            'queue_strategy': 'fifo'
                        }

                        # Add pre/post checks if defined in service
                        if service_def.get('pre_checks'):
                            payload['pre_checks'] = service_def['pre_checks']
                            log.info(f"Adding pre-checks: {service_def['pre_checks']}")

                        if service_def.get('post_checks'):
                            payload['post_checks'] = service_def['post_checks']
                            log.info(f"Adding post-checks: {service_def['post_checks']}")

                        log.info(f"Sending payload to Netstacker: j2config.template='{template_name}', args={variables}")

                        # Deploy using Netstacker's j2config - Netstacker renders and deploys in one call
                        deploy_response = requests.post(
                            f'{NETSTACKER_API_URL}/setconfig',
                            headers=NETSTACKER_HEADERS,
                            json=payload,
                            timeout=60
                        )

                        log.info(f"Deploy response status: {deploy_response.status_code}")
                        if deploy_response.status_code != 201:
                            raise Exception(f"Failed to deploy configuration to {device_name}: {deploy_response.text}")

                        deploy_result = deploy_response.json()
                        task_id = deploy_result.get('data', {}).get('task_id')
                        log.info(f"Got task_id: {task_id}")

                        # Save task to history for monitoring with standardized format
                        # Format: stack:DEPLOY:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                        job_name = f"stack:DEPLOY:{stack.get('name')}:{service_def['name']}:{device_name}:{task_id}"
                        save_task_id(task_id, device_name=job_name)

                        # Create service instance record immediately in 'deploying' state
                        # Let Netstacker queue handle the deployment - don't wait here
                        # Note: rendered_config is not stored since Netstacker does the rendering
                        service_instance = {
                            'service_id': str(uuid.uuid4()),
                            'name': f"{service_def['name']} ({device_name})",
                            'template': template_name,
                            'validation_template': template_metadata.get('validation_template'),
                            'delete_template': template_metadata.get('delete_template'),
                            'device': device_name,
                            'variables': variables,
                            'pre_checks': service_def.get('pre_checks'),
                            'post_checks': service_def.get('post_checks'),
                            'state': 'deploying',  # Jobs submitted to Netstacker queue
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
        # Since services are submitted to Netstacker queue and may still be deploying,
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
            # All jobs successfully submitted to Netstacker queue
            stack['state'] = 'deploying'  # Changed from 'deployed' - jobs are queued in Netstacker

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
        from database import create_scheduled_operation as db_create_schedule
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
        from database import update_scheduled_operation
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
        from database import get_scheduled_operations as db_get_schedules

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
        from database import get_scheduled_operation as db_get_schedule

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
        from database import update_scheduled_operation as db_update_schedule, get_scheduled_operation
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
        from database import delete_scheduled_operation as db_delete_schedule

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
        from database import create_scheduled_operation as db_create_schedule
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
        from database import update_scheduled_operation
        update_scheduled_operation(schedule_id, next_run=next_run.isoformat())

        log.info(f"Created scheduled config operation: {schedule_id}")
        return jsonify({'success': True, 'schedule_id': schedule_id})

    except Exception as e:
        log.error(f"Error creating scheduled config operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== MOP (Method of Procedures) Endpoints ====================

@app.route('/api/mop', methods=['GET'])
@login_required
def get_all_mops_api():
    """Get all MOPs"""
    try:
        mops = db.get_all_mops()
        return jsonify({'success': True, 'mops': mops})
    except Exception as e:
        log.error(f"Error getting MOPs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop', methods=['POST'])
@login_required
def create_mop_api():
    """Create a new MOP"""
    try:
        data = request.json
        mop_id = str(uuid.uuid4())
        name = data.get('name')
        description = data.get('description', '')
        devices = data.get('devices', [])

        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        db.create_mop(mop_id, name, description, devices)
        log.info(f"Created MOP: {mop_id} with devices: {devices}")
        return jsonify({'success': True, 'mop_id': mop_id})

    except Exception as e:
        log.error(f"Error creating MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>', methods=['GET'])
@login_required
def get_mop_api(mop_id):
    """Get a specific MOP with its steps"""
    try:
        mop = db.get_mop(mop_id)
        if not mop:
            return jsonify({'success': False, 'error': 'MOP not found'}), 404

        steps = db.get_mop_steps(mop_id)
        mop['steps'] = steps

        return jsonify({'success': True, 'mop': mop})
    except Exception as e:
        log.error(f"Error getting MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>', methods=['PUT'])
@login_required
def update_mop_api(mop_id):
    """Update a MOP"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')
        devices = data.get('devices')

        db.update_mop(mop_id, name=name, description=description, devices=devices)
        log.info(f"Updated MOP: {mop_id}")
        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error updating MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>', methods=['DELETE'])
@login_required
def delete_mop_api(mop_id):
    """Delete a MOP"""
    try:
        db.delete_mop(mop_id)
        log.info(f"Deleted MOP: {mop_id}")
        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error deleting MOP: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/steps', methods=['GET'])
@login_required
def get_mop_steps_api(mop_id):
    """Get all steps for a MOP"""
    try:
        steps = db.get_mop_steps(mop_id)
        return jsonify({'success': True, 'steps': steps})
    except Exception as e:
        log.error(f"Error getting MOP steps: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/steps', methods=['POST'])
@login_required
def create_mop_step_api(mop_id):
    """Create a new step for a MOP"""
    try:
        data = request.json
        step_id = str(uuid.uuid4())
        step_order = data.get('step_order', 0)
        step_type = data.get('step_type')  # 'getconfig', 'setconfig', 'template'
        step_name = data.get('step_name')
        devices = data.get('devices', [])
        config = data.get('config', {})
        enabled = data.get('enabled', 1)

        if not step_type or not step_name:
            return jsonify({'success': False, 'error': 'step_type and step_name are required'}), 400

        db.create_mop_step(step_id, mop_id, step_order, step_type, step_name, devices, config, enabled)
        log.info(f"Created MOP step: {step_id} for MOP: {mop_id}")
        return jsonify({'success': True, 'step_id': step_id})

    except Exception as e:
        log.error(f"Error creating MOP step: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/steps/<step_id>', methods=['PUT'])
@login_required
def update_mop_step_api(mop_id, step_id):
    """Update a MOP step"""
    try:
        data = request.json
        step_order = data.get('step_order')
        step_type = data.get('step_type')
        step_name = data.get('step_name')
        devices = data.get('devices')
        config = data.get('config')
        enabled = data.get('enabled')

        db.update_mop_step(step_id, step_order=step_order, step_type=step_type,
                          step_name=step_name, devices=devices, config=config, enabled=enabled)
        log.info(f"Updated MOP step: {step_id}")
        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error updating MOP step: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/steps/<step_id>', methods=['DELETE'])
@login_required
def delete_mop_step_api(mop_id, step_id):
    """Delete a MOP step"""
    try:
        db.delete_mop_step(step_id)
        log.info(f"Deleted MOP step: {step_id}")
        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error deleting MOP step: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def substitute_step_variables(step, variables, mop_context):
    """Substitute {{variable}} patterns in step with runtime values

    Supports dot notation for device-centric access:
    - {{mop.devices.router01.site}}
    - {{mop.devices.router01.step0.output}}
    - {{device_name}} (runtime variables)
    """
    import re
    import copy

    # Create a deep copy to avoid modifying original
    step = copy.deepcopy(step)

    # Function to replace variables in a string
    def replace_vars(text):
        if not isinstance(text, str):
            return text

        # Pattern to match {{anything}}
        pattern = r'\{\{([^}]+)\}\}'

        def replacer(match):
            var_path = match.group(1).strip()

            # Handle mop.devices.XXX.YYY paths
            if var_path.startswith('mop.devices.'):
                parts = var_path.split('.')
                # parts = ['mop', 'devices', 'router01', 'site'] or ['mop', 'devices', 'router01', 'step0', 'output']
                if len(parts) >= 3:
                    device_name = parts[2]  # router01
                    if device_name in mop_context['devices']:
                        device_data = mop_context['devices'][device_name]

                        if len(parts) == 3:
                            # Just device name: {{mop.devices.router01}}
                            return device_name
                        elif len(parts) == 4:
                            # Device attribute: {{mop.devices.router01.site}}
                            attr = parts[3]
                            return str(device_data.get(attr, ''))
                        elif len(parts) == 5:
                            # Step result: {{mop.devices.router01.step0.output}}
                            step_ref = parts[3]  # step0
                            attr = parts[4]      # output
                            return str(device_data.get(step_ref, {}).get(attr, ''))

            # Handle simple runtime variables
            elif var_path in variables:
                var_value = variables[var_path]
                if isinstance(var_value, list):
                    return var_value  # Will be handled by caller
                return str(var_value)

            # Variable not found, return original
            return match.group(0)

        result = re.sub(pattern, replacer, text)
        return result

    # Substitute in devices array
    if step.get('devices') and isinstance(step['devices'], list):
        new_devices = []
        for device in step['devices']:
            replaced = replace_vars(device)
            if isinstance(replaced, list):
                # Device variable expanded to list of devices
                new_devices.extend(replaced)
            else:
                new_devices.append(replaced)
        step['devices'] = new_devices

    # Substitute in config fields recursively
    if step.get('config'):
        def substitute_dict(obj):
            if isinstance(obj, dict):
                return {k: substitute_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_dict(item) for item in obj]
            elif isinstance(obj, str):
                return replace_vars(obj)
            else:
                return obj

        step['config'] = substitute_dict(step['config'])

    return step

@app.route('/api/mop/<mop_id>/execute', methods=['POST'])
@login_required
def execute_mop_api(mop_id):
    """Execute a MOP - run all steps sequentially in background"""
    try:
        # Get variables from request body
        request_data = request.get_json() or {}
        variables = request_data.get('variables', {})

        log.info(f"Executing MOP {mop_id} with variables: {variables}")

        # Get MOP and steps
        mop = db.get_mop(mop_id)
        if not mop:
            return jsonify({'success': False, 'error': 'MOP not found'}), 404

        steps = db.get_mop_steps(mop_id)
        if not steps:
            return jsonify({'success': False, 'error': 'No steps found for this MOP'}), 400

        # Create execution record
        execution_id = str(uuid.uuid4())
        db.create_mop_execution(execution_id, mop_id)

        # Start execution in background thread
        import threading
        thread = threading.Thread(
            target=execute_mop_background,
            args=(execution_id, mop_id, mop, steps, variables)
        )
        thread.daemon = True
        thread.start()

        # Return execution_id immediately so client can poll for progress
        return jsonify({
            'success': True,
            'execution_id': execution_id,
            'message': 'MOP execution started'
        })

    except Exception as e:
        log.error(f"Error starting MOP execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def execute_mop_background(execution_id, mop_id, mop, steps, variables):
    """Background worker to execute MOP steps"""
    log.info(f"=== MOP BACKGROUND THREAD STARTED: {execution_id} ===")
    try:
        log.info(f"Background execution started for {execution_id}")

        # Build device-centric MOP context
        mop_context = {
            'devices': {}
        }

        # Get device metadata for all MOP devices from cache
        all_devices_list = []

        # Collect all devices from all cache entries
        for cache_key, cache_entry in device_cache.items():
            if cache_key == 'ttl':
                continue
            if cache_entry and isinstance(cache_entry, dict) and 'devices' in cache_entry:
                cached_devices = cache_entry.get('devices', [])
                if cached_devices:
                    all_devices_list.extend(cached_devices)

        # If cache is empty, only use manual devices
        if not all_devices_list:
            manual_devices = db.get_all_manual_devices()
            for device in manual_devices:
                all_devices_list.append({
                    'name': device['device_name'],
                    'device_type': device['device_type'],
                    'primary_ip': device['host'],
                    'site': 'Manual',
                    'status': 'Active',
                    'device_role': '',
                    'platform': '',
                    'source': 'manual'
                })

        # Build context for each MOP device
        for device_name in mop.get('devices', []):
            device_info = next((dev for dev in all_devices_list if dev['name'] == device_name), None)

            if device_info:
                # Extract IP address (remove subnet mask if present)
                primary_ip = device_info.get('primary_ip', '')
                if primary_ip and '/' in primary_ip:
                    ip_address = primary_ip.split('/')[0]
                else:
                    ip_address = primary_ip or device_name

                mop_context['devices'][device_name] = {
                    'name': device_name,
                    'site': device_info.get('site', ''),
                    'device_type': device_info.get('device_type', ''),
                    'device_role': device_info.get('device_role', ''),
                    'ip_address': ip_address,
                    'platform': device_info.get('platform', ''),
                    'status': device_info.get('status', ''),
                }
                log.info(f"Built MOP context for {device_name}: ip={ip_address}, platform={device_info.get('platform')}")
            else:
                # Device not found in inventory, use device name as IP
                log.warning(f"Device {device_name} not found in inventory, will use device name as IP")
                mop_context['devices'][device_name] = {
                    'name': device_name,
                    'ip_address': device_name,  # Fallback to using device name as IP
                }

        # Execute steps sequentially
        results = []

        for step_index, step in enumerate(steps):
            # Substitute variables in step before execution
            step = substitute_step_variables(step, variables, mop_context)

            if not step['enabled']:
                results.append({
                    'step_id': step['step_id'],
                    'step_name': step['step_name'],
                    'status': 'skipped',
                    'message': 'Step is disabled'
                })
                continue

            log.info(f"Executing MOP step {step_index} (order {step['step_order']}): {step['step_name']}")

            # Update execution status - use step_index not step_order
            db.update_mop_execution(execution_id, current_step=step_index)

            try:
                # Execute the step based on its type - pass MOP context
                if step['step_type'] == 'getconfig':
                    result = execute_getconfig_step(step, mop_context, step_index)
                elif step['step_type'] == 'setconfig':
                    result = execute_setconfig_step(step, mop_context, step_index)
                elif step['step_type'] == 'template':
                    result = execute_template_step(step, mop_context, step_index)
                elif step['step_type'] == 'deploy_stack':
                    result = execute_deploy_stack_step(step, mop_context, step_index)
                elif step['step_type'] == 'api':
                    result = execute_api_step(step, mop_context, step_index)
                elif step['step_type'] == 'code':
                    result = execute_code_step(step, mop_context, step_index)
                else:
                    result = {
                        'status': 'error',
                        'message': f"Unknown step type: {step['step_type']}"
                    }

                # Build step result object
                step_result = {
                    'step_id': step['step_id'],
                    'step_name': step['step_name'],
                    'step_type': step['step_type'],
                    'step_order': step['step_order'],
                    'status': result.get('status', 'unknown'),
                    'data': result.get('data'),
                    'task_id': result.get('task_id'),
                    'error': result.get('error')
                }

                results.append(step_result)

                # Store results in device-centric structure: mop.devices[device_name].step0.output
                step_ref = f"step{step['step_order']}"
                if result.get('data') and isinstance(result.get('data'), list):
                    for device_result in result.get('data'):
                        device_name = device_result.get('device')
                        if device_name and device_name in mop_context['devices']:
                            # Add step results to device
                            if step_ref not in mop_context['devices'][device_name]:
                                mop_context['devices'][device_name][step_ref] = {}

                            mop_context['devices'][device_name][step_ref] = {
                                'output': device_result.get('output'),
                                'status': device_result.get('task_status'),
                                'task_id': device_result.get('task_id')
                            }

                log.info(f"Stored step {step_ref} results for devices")

            except Exception as step_error:
                log.error(f"Error executing step {step['step_id']}: {step_error}")
                results.append({
                    'step_id': step['step_id'],
                    'step_name': step['step_name'],
                    'status': 'error',
                    'error': str(step_error)
                })
                # Continue with next step even if this one fails
                continue

        # Update execution status to completed with results and context
        db.update_mop_execution(
            execution_id,
            status='completed',
            results=results,
            context=mop_context  # Store device-centric context
        )

        log.info(f"Completed MOP execution: {execution_id}")

    except Exception as e:
        log.error(f"Error in background MOP execution: {e}", exc_info=True)
        # Update execution status to failed
        db.update_mop_execution(execution_id, status='failed', error=str(e))

@app.route('/api/mop/executions/running', methods=['GET'])
@login_required
def get_all_running_mop_executions_api():
    """Get all currently running MOP executions across all MOPs"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.execution_id, e.mop_id, e.status, e.current_step, e.started_at, m.name as mop_name
                FROM mop_executions e
                JOIN mops m ON e.mop_id = m.mop_id
                WHERE e.status = 'running'
                ORDER BY e.started_at DESC
            """)
            executions = cursor.fetchall()
            # Convert Row objects to dictionaries
            executions_list = [dict(row) for row in executions]
            return jsonify({'success': True, 'executions': executions_list})
    except Exception as e:
        log.error(f"Error getting running MOP executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/executions/<execution_id>/cancel', methods=['POST'])
@login_required
def cancel_mop_execution_api(execution_id):
    """Cancel a running MOP execution"""
    try:
        from datetime import datetime
        db.update_mop_execution(
            execution_id,
            status='cancelled',
            error='Cancelled by user',
            completed_at=datetime.utcnow()
        )
        log.info(f"MOP execution {execution_id} cancelled by user")
        return jsonify({'success': True, 'message': 'MOP execution cancelled'})
    except Exception as e:
        log.error(f"Error cancelling MOP execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/executions', methods=['GET'])
@login_required
def get_mop_executions_api(mop_id):
    """Get execution history for a MOP"""
    try:
        limit = request.args.get('limit', 10, type=int)
        executions = db.get_mop_executions(mop_id, limit=limit)
        return jsonify({'success': True, 'executions': executions})
    except Exception as e:
        log.error(f"Error getting MOP executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/executions/<execution_id>', methods=['GET'])
@login_required
def get_mop_execution_api(execution_id):
    """Get a specific execution"""
    try:
        execution = db.get_mop_execution(execution_id)
        if not execution:
            return jsonify({'success': False, 'error': 'Execution not found'}), 404
        return jsonify({'success': True, 'execution': execution})
    except Exception as e:
        log.error(f"Error getting MOP execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mop/<mop_id>/current-execution', methods=['GET'])
@login_required
def get_current_mop_execution_api(mop_id):
    """Get the current running execution for a MOP (if any)"""
    try:
        # Get recent executions for this MOP
        executions = db.get_mop_executions(mop_id, limit=5)

        # Find the first one that's still running
        running_execution = next((e for e in executions if e.get('status') == 'running'), None)

        if running_execution:
            return jsonify({'success': True, 'execution': running_execution, 'has_running': True})
        else:
            return jsonify({'success': True, 'has_running': False})
    except Exception as e:
        log.error(f"Error getting current MOP execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# WORKFLOW API ENDPOINTS (YAML-based workflow engine)
# ============================================================

@app.route('/api/workflows', methods=['GET'])
@login_required
def get_workflows_api():
    """Get all workflows"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT workflow_id, name, description, devices, enabled, created_at, updated_at
                FROM workflows
                ORDER BY created_at DESC
            ''')
            workflows = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'workflows': workflows})
    except Exception as e:
        log.error(f"Error getting workflows: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows', methods=['POST'])
@login_required
def create_workflow_api():
    """Create a new workflow"""
    try:
        data = request.json
        workflow_id = str(uuid.uuid4())

        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workflows (workflow_id, name, description, yaml_content, devices, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                workflow_id,
                data.get('name'),
                data.get('description'),
                data.get('yaml_content'),
                json.dumps(data.get('devices', [])),
                session.get('username')
            ))
            conn.commit()

        return jsonify({'success': True, 'workflow_id': workflow_id})
    except Exception as e:
        log.error(f"Error creating workflow: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows/<workflow_id>', methods=['GET'])
@login_required
def get_workflow_api(workflow_id):
    """Get a specific workflow"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM workflows WHERE workflow_id = ?', (workflow_id,))
            workflow = cursor.fetchone()

            if not workflow:
                return jsonify({'success': False, 'error': 'Workflow not found'}), 404

            return jsonify({'success': True, 'workflow': dict(workflow)})
    except Exception as e:
        log.error(f"Error getting workflow: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows/<workflow_id>', methods=['PUT'])
@login_required
def update_workflow_api(workflow_id):
    """Update a workflow"""
    try:
        data = request.json

        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE workflows
                SET name = ?, description = ?, yaml_content = ?, devices = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
            ''', (
                data.get('name'),
                data.get('description'),
                data.get('yaml_content'),
                json.dumps(data.get('devices', [])),
                workflow_id
            ))
            conn.commit()

        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error updating workflow: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows/<workflow_id>', methods=['DELETE'])
@login_required
def delete_workflow_api(workflow_id):
    """Delete a workflow"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM workflows WHERE workflow_id = ?', (workflow_id,))
            conn.commit()

        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Error deleting workflow: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows/<workflow_id>/execute', methods=['POST'])
@login_required
def execute_workflow_api(workflow_id):
    """Execute a workflow"""
    try:
        # Get workflow from database
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM workflows WHERE workflow_id = ?', (workflow_id,))
            workflow_row = cursor.fetchone()

            if not workflow_row:
                return jsonify({'success': False, 'error': 'Workflow not found'}), 404

            workflow = dict(workflow_row)

        # Create execution record
        execution_id = str(uuid.uuid4())

        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workflow_executions
                (execution_id, workflow_id, status, started_at, started_by)
                VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?)
            ''', (execution_id, workflow_id, session.get('username')))
            conn.commit()

        # Execute workflow asynchronously
        def run_workflow():
            from workflow_engine import WorkflowEngine

            try:
                # Build context with device information
                context = {'devices': {}}

                # Get device info from Netbox if devices specified
                # First try to get from database field
                devices = json.loads(workflow.get('devices', '[]'))

                # If no devices in database, parse from YAML
                if not devices:
                    import yaml as yaml_lib
                    try:
                        yaml_data = yaml_lib.safe_load(workflow['yaml_content'])
                        devices = yaml_data.get('devices', [])
                        log.info(f"Parsed {len(devices)} devices from YAML")
                    except Exception as e:
                        log.error(f"Could not parse YAML to extract devices: {e}")
                        devices = []

                log.info(f"Workflow has {len(devices)} devices: {devices}")

                if devices:
                    for device_name in devices:
                        log.info(f"Loading device info for: {device_name}")
                        try:
                            # Get device connection info (includes IP, platform, etc.)
                            device_conn_info = get_device_connection_info(device_name)
                            log.info(f"get_device_connection_info returned: {device_conn_info is not None}")

                            if device_conn_info:
                                # Extract relevant info for workflow context
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

                log.info(f"Workflow context devices: {list(context['devices'].keys())}")

                # Execute workflow
                engine = WorkflowEngine(workflow['yaml_content'], context)
                result = engine.execute()

                # Update execution record
                with db.get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE workflow_executions
                        SET status = ?, execution_log = ?, context = ?, completed_at = CURRENT_TIMESTAMP
                        WHERE execution_id = ?
                    ''', (
                        result['status'],
                        json.dumps(result.get('execution_log', [])),
                        json.dumps(result.get('context', {})),
                        execution_id
                    ))
                    conn.commit()

                log.info(f"Workflow {workflow_id} execution {execution_id} completed with status: {result['status']}")

            except Exception as e:
                log.error(f"Error executing workflow: {e}", exc_info=True)

                # Update execution record with error
                with db.get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE workflow_executions
                        SET status = 'failed', error = ?, completed_at = CURRENT_TIMESTAMP
                        WHERE execution_id = ?
                    ''', (str(e), execution_id))
                    conn.commit()

        # Start background thread
        import threading
        thread = threading.Thread(target=run_workflow)
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'execution_id': execution_id})

    except Exception as e:
        log.error(f"Error starting workflow execution: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflows/<workflow_id>/executions', methods=['GET'])
@login_required
def get_workflow_executions_api(workflow_id):
    """Get execution history for a workflow"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT execution_id, status, started_at, completed_at, started_by
                FROM workflow_executions
                WHERE workflow_id = ?
                ORDER BY started_at DESC
                LIMIT 50
            ''', (workflow_id,))
            executions = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'executions': executions})
    except Exception as e:
        log.error(f"Error getting workflow executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflow-executions/<execution_id>', methods=['GET'])
@login_required
def get_workflow_execution_details_api(execution_id):
    """Get detailed execution information"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM workflow_executions WHERE execution_id = ?
            ''', (execution_id,))
            execution = cursor.fetchone()

            if not execution:
                return jsonify({'success': False, 'error': 'Execution not found'}), 404

            execution_dict = dict(execution)

            # Parse JSON fields
            if execution_dict.get('execution_log'):
                execution_dict['execution_log'] = json.loads(execution_dict['execution_log'])
            if execution_dict.get('context'):
                execution_dict['context'] = json.loads(execution_dict['context'])

            return jsonify({'success': True, 'execution': execution_dict})
    except Exception as e:
        log.error(f"Error getting workflow execution details: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflow-executions/running', methods=['GET'])
@login_required
def get_running_workflow_executions_api():
    """Get all currently running workflow executions"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT we.execution_id, we.workflow_id, we.status, we.current_step,
                       we.started_at, we.started_by, w.name as workflow_name
                FROM workflow_executions we
                JOIN workflows w ON we.workflow_id = w.workflow_id
                WHERE we.status = 'running'
                ORDER BY we.started_at DESC
            ''')
            executions = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'executions': executions})
    except Exception as e:
        log.error(f"Error getting running workflow executions: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/<task_id>/result', methods=['GET'])
@login_required
def get_task_result_api(task_id):
    """Get task result from netstacker"""
    try:
        response = requests.get(
            f'{NETSTACKER_API_URL}/task/{task_id}',
            headers=NETSTACKER_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        return jsonify(response.json())
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

                # Call the existing deploy_getconfig endpoint logic
                endpoint = f'/getconfig/{library}' if library != 'auto' else '/getconfig'
                log.info(f"Sending getconfig for {device_name} to {NETSTACKER_API_URL}{endpoint}")

                response = requests.post(
                    f'{NETSTACKER_API_URL}{endpoint}',
                    json=payload,
                    headers=NETSTACKER_HEADERS,
                    timeout=30
                )

                response.raise_for_status()
                result = response.json()

                task_id = result.get('data', {}).get('task_id')

                # Save task ID to history
                if task_id:
                    save_task_id(task_id, device_name=f"mop:STEP{step_index+1}-{step.get('step_name', 'unknown')}-:{device_name}")
                    task_submissions.append((device_name, task_id, device_info))
                    log.info(f"Submitted task {task_id} for {device_name}")
                else:
                    results.append({
                        'device': device_name,
                        'status': 'error',
                        'error': 'No task_id returned from Netstacker'
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
                    print(f"[MOP] Polling {task_id} for {state['device']}", file=sys.stderr, flush=True)
                    task_response = requests.get(
                        f'{NETSTACKER_API_URL}/task/{task_id}',
                        headers=NETSTACKER_HEADERS,
                        timeout=10
                    )
                    print(f"[MOP] Got HTTP {task_response.status_code}", file=sys.stderr, flush=True)

                    if task_response.status_code == 200:
                        task_data = task_response.json().get('data', {})
                        task_output = task_data.get('task_result')
                        task_status = task_data.get('task_status', 'pending')
                        print(f"[MOP] {state['device']} task_status={task_status}", file=sys.stderr, flush=True)

                        # Check for final states (case-insensitive to handle 'failed', 'FAILED', 'finished', 'FINISHED', etc.)
                        task_status_upper = task_status.upper() if task_status else 'PENDING'
                        if task_status_upper in ['SUCCESS', 'FAILED', 'FAILURE', 'FINISHED']:
                            log.info(f"Task {task_id} for {state['device']} completed with status: {task_status}")
                            print(f"[MOP] {state['device']} COMPLETE: {task_status}", file=sys.stderr, flush=True)
                            state['status'] = task_status_upper
                            state['output'] = task_output
                    else:
                        log.warning(f"Failed to get task {task_id} status: HTTP {task_response.status_code}")

                except Exception as e:
                    print(f"[MOP] EXCEPTION polling {task_id}: {e}", file=sys.stderr, flush=True)
                    log.error(f"Error polling task {task_id}: {e}", exc_info=True)
                    state['status'] = 'ERROR'
                    state['error'] = str(e)

            if all_complete:
                log.info("All tasks completed")
                break

            print(f"[MOP] Sleeping {poll_interval}s...", file=sys.stderr, flush=True)
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

                # Call netstacker
                endpoint = f'/setconfig/{library}' if library != 'auto' else '/setconfig'
                log.info(f"Sending setconfig for {device_name} to {NETSTACKER_API_URL}{endpoint}")

                response = requests.post(
                    f'{NETSTACKER_API_URL}{endpoint}',
                    json=payload,
                    headers=NETSTACKER_HEADERS,
                    timeout=30
                )

                response.raise_for_status()
                result = response.json()

                task_id = result.get('data', {}).get('task_id')

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
    """Execute a template deployment step

    Args:
        step: Step configuration dict
        context: Dict of previous step results for reference
        step_index: Index of the step in the MOP (0-based)
    """
    try:
        config = step['config']
        devices = step['devices']

        # Get template content
        template_name = config.get('template')
        if not template_name:
            return {'status': 'error', 'error': 'Template name is required'}

        # Read template file
        template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.j2")
        if not os.path.exists(template_path):
            return {'status': 'error', 'error': f'Template not found: {template_name}'}

        with open(template_path, 'r') as f:
            template_content = f.read()

        payload = {
            'hosts': devices,
            'template': template_content,
            'variables': config.get('variables', {}),
            'dry_run': config.get('dry_run', False)
        }

        # Add credentials if provided
        if config.get('username'):
            payload['username'] = config['username']
        if config.get('password'):
            payload['password'] = config['password']

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

        library = config.get('library', 'netmiko')
        endpoint = f'/setconfig/{library}' if library != 'auto' else '/setconfig'

        log.info(f"Sending template deployment request to {NETSTACKER_API_URL}{endpoint}")
        response = requests.post(
            f'{NETSTACKER_API_URL}{endpoint}',
            json=payload,
            headers=NETSTACKER_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        task_id = result.get('data', {}).get('task_id')

        # Save task ID to history
        if task_id:
            save_task_id(task_id, device_name=f"mop:STEP{step_index+1}-{step.get('step_name', 'unknown')}-:template")

        return {
            'status': result.get('status', 'success'),
            'data': result.get('data'),
            'task_id': task_id
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

                        # Deploy template to device
                        payload = {
                            'library': 'netmiko',
                            'connection_args': device_info['connection_args'],
                            'j2config': {
                                'template': template_name,
                                'args': variables
                            },
                            'queue_strategy': 'fifo'
                        }

                        log.info(f"Deploying template '{template_name}' to {device_name}")

                        response = requests.post(
                            f'{NETSTACKER_API_URL}/setconfig',
                            json=payload,
                            headers=NETSTACKER_HEADERS,
                            timeout=300
                        )
                        response.raise_for_status()

                        task_data = response.json()
                        log.info(f"Deploy response data: {task_data}")
                        task_id = task_data.get('data', {}).get('task_id') or task_data.get('task_id')
                        log.info(f"Template deployment initiated for {device_name}: task_id={task_id}")

                        # Save task to history for job monitoring
                        # Format: mop:DEPLOY_STACK:{StackName}:{ServiceName}:{DeviceName}:{TaskID}
                        if task_id:
                            job_name = f"mop:DEPLOY_STACK:{stack.get('name')}:{service_def['name']}:{device_name}:{task_id}"
                            save_task_id(task_id, device_name=job_name)

                            # Poll and wait for task completion
                            import time
                            max_wait = 300  # 5 minutes max
                            poll_interval = 2  # Poll every 2 seconds
                            elapsed = 0
                            task_status = 'pending'

                            while elapsed < max_wait:
                                try:
                                    task_response = requests.get(
                                        f'{NETSTACKER_API_URL}/task/{task_id}',
                                        headers=NETSTACKER_HEADERS,
                                        timeout=10
                                    )
                                    if task_response.status_code == 200:
                                        task_result = task_response.json().get('data', {})
                                        task_status = task_result.get('task_status', 'pending')

                                        # Check if task is in final state
                                        if task_status in ['SUCCESS', 'FAILED', 'FAILURE', 'finished']:
                                            log.info(f"Deploy task {task_id} completed with status: {task_status}")
                                            break
                                    else:
                                        log.warning(f"Failed to get deploy task {task_id} status: HTTP {task_response.status_code}")

                                except Exception as poll_error:
                                    log.error(f"Error polling deploy task {task_id}: {poll_error}", exc_info=True)
                                    task_status = 'FAILED'
                                    break

                                time.sleep(poll_interval)
                                elapsed += poll_interval

                            if task_status not in ['SUCCESS', 'FAILED', 'FAILURE', 'finished']:
                                log.error(f"Deploy task {task_id} did not complete within {max_wait}s, final status: {task_status}")
                                task_status = 'TIMEOUT'

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
                # Get variables from the device template
                template_name_clean = template_name[:-3] if template_name.endswith('.j2') else template_name
                try:
                    # Call the existing API endpoint to get template variables
                    response = requests.get(
                        f'{NETSTACKER_API_URL}/j2template/config/{template_name_clean}',
                        headers=NETSTACKER_HEADERS,
                        timeout=10
                    )
                    if response.status_code == 200:
                        result = response.json()
                        template_data = result.get('data', {}).get('task_result', {})
                        base64_content = template_data.get('base64_payload') or template_data.get('template')

                        if base64_content:
                            # Decode and extract variables
                            template_content = base64.b64decode(base64_content).decode('utf-8')
                            import re
                            variable_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
                            variables = re.findall(variable_pattern, template_content)
                            required_variables.update(variables)
                except Exception as e:
                    log.warning(f"Could not extract variables from template {template_name}: {e}")

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

        template_id = db.save_stack_template(template_data)

        return jsonify({
            'success': True,
            'template_id': template_id,
            'message': f'Stack template "{data["name"]}" created successfully'
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
        from database import get_pending_scheduled_operations, update_scheduled_operation
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
    
                                            # Prepare payload for netstacker
                                            payload = {
                                                'library': 'netmiko',
                                                'connection_args': device_info['connection_args'],
                                                'j2config': {
                                                    'template': template_name,
                                                    'args': variables
                                                },
                                                'queue_strategy': 'fifo'
                                            }
    
                                            # Add pre/post checks if defined
                                            if service_def.get('pre_checks'):
                                                payload['pre_checks'] = service_def['pre_checks']
    
                                            if service_def.get('post_checks'):
                                                payload['post_checks'] = service_def['post_checks']
    
                                            log.info(f"Sending deployment to netstacker: {NETSTACKER_API_URL}/setconfig")
    
                                            # Deploy using Netstacker
                                            import requests
                                            deploy_response = requests.post(
                                                f'{NETSTACKER_API_URL}/setconfig',
                                                headers=NETSTACKER_HEADERS,
                                                json=payload,
                                                timeout=60
                                            )
    
                                            if deploy_response.status_code != 201:
                                                raise Exception(f"Failed to deploy to {device_name}: {deploy_response.text}")
    
                                            deploy_result = deploy_response.json()
                                            task_id = deploy_result.get('data', {}).get('task_id')
    
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
    
                                            # Prepare payload for netstacker getconfig
                                            payload = {
                                                'library': 'netmiko',
                                                'connection_args': device_info['connection_args'],
                                                'command': 'show running-config',
                                                'args': {},
                                                'queue_strategy': 'fifo'
                                            }
    
                                            # Get config using Netstacker
                                            import requests
                                            log.info(f"Sending validation payload to {NETSTACKER_API_URL}/getconfig/netmiko: {payload}")
                                            validate_response = requests.post(
                                                f'{NETSTACKER_API_URL}/getconfig/netmiko',
                                                headers=NETSTACKER_HEADERS,
                                                json=payload,
                                                timeout=60
                                            )
    
                                            if validate_response.status_code == 200 or validate_response.status_code == 201:
                                                result = validate_response.json()
                                                task_id = result.get('data', {}).get('task_id')
                                                log.info(f"Validation task created for {device_name}: {task_id}")
                                                # Save task ID to history so it appears in Job Monitor with standardized format
                                                # Format: stack:VALIDATION:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                                                if task_id:
                                                    job_name = f"stack:VALIDATION:{stack.get('name')}:{service_def.get('name')}:{device_name}:{task_id}"
                                                    save_task_id(task_id, device_name=job_name)
                                            else:
                                                log.error(f"Validation failed for {device_name}: {validate_response.status_code}")
                                                log.error(f"Response: {validate_response.text}")
    
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
    
                                            # Prepare payload for netstacker
                                            payload = {
                                                'library': 'netmiko',
                                                'connection_args': device_info['connection_args'],
                                                'j2config': {
                                                    'template': delete_template,
                                                    'args': variables
                                                },
                                                'queue_strategy': 'fifo'
                                            }
    
                                            # Deploy delete template using Netstacker
                                            import requests
                                            delete_response = requests.post(
                                                f'{NETSTACKER_API_URL}/setconfig',
                                                headers=NETSTACKER_HEADERS,
                                                json=payload,
                                                timeout=60
                                            )
    
                                            if delete_response.status_code == 201:
                                                result = delete_response.json()
                                                task_id = result.get('data', {}).get('task_id')
                                                log.info(f"Delete task created for {device_name}: {task_id}")
                                                # Save task ID to history so it appears in Job Monitor with standardized format
                                                # Format: stack:DELETE:{StackName}:{ServiceName}:{DeviceName}:{JobID}
                                                if task_id:
                                                    job_name = f"stack:DELETE:{stack.get('name')}:{service_def.get('name')}:{device_name}:{task_id}"
                                                    save_task_id(task_id, device_name=job_name)
                                            else:
                                                log.error(f"Delete failed for {device_name}: {delete_response.status_code}")
    
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
    
                                            # Build netstacker payload
                                            payload = {
                                                'connection_args': {
                                                    'device_type': nornir_platform or 'cisco_ios',
                                                    'host': ip_address,
                                                    'username': username,
                                                    'password': password,
                                                    'timeout': 10
                                                },
                                                'config': config_commands,
                                                'queue_strategy': 'pinned'
                                            }
    
                                            # Send to Netstacker
                                            endpoint = '/setconfig/dry-run' if dry_run else '/setconfig/netmiko'
                                            response = requests.post(
                                                f'{NETSTACKER_API_URL}{endpoint}',
                                                json=payload,
                                                headers=NETSTACKER_HEADERS,
                                                timeout=30
                                            )
                                            response.raise_for_status()
                                            result = response.json()
    
                                            # Save task ID
                                            if result.get('status') == 'success' and result.get('data', {}).get('task_id'):
                                                task_id = result['data']['task_id']
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
                                        # Render template first
                                        render_response = requests.post(
                                            f'{NETSTACKER_API_URL}/j2template/render',
                                            json={
                                                'template_name': template_name.replace('.j2', ''),
                                                'args': variables
                                            },
                                            headers=NETSTACKER_HEADERS,
                                            timeout=10
                                        )
                                        render_response.raise_for_status()
                                        render_result = render_response.json()
    
                                        rendered_config = render_result.get('data', {}).get('task_result', {}).get('template_render_result', '')
    
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
    
                                                    # Build netstacker payload
                                                    payload = {
                                                        'connection_args': {
                                                            'device_type': nornir_platform or 'cisco_ios',
                                                            'host': ip_address,
                                                            'username': username,
                                                            'password': password,
                                                            'timeout': 10
                                                        },
                                                        'config': config_commands,
                                                        'queue_strategy': 'pinned'
                                                    }
    
                                                    # Send to Netstacker
                                                    endpoint = '/setconfig/dry-run' if dry_run else '/setconfig/netmiko'
                                                    response = requests.post(
                                                        f'{NETSTACKER_API_URL}{endpoint}',
                                                        json=payload,
                                                        headers=NETSTACKER_HEADERS,
                                                        timeout=30
                                                    )
                                                    response.raise_for_status()
                                                    result = response.json()
    
                                                    # Save task ID
                                                    if result.get('status') == 'success' and result.get('data', {}).get('task_id'):
                                                        task_id = result['data']['task_id']
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
