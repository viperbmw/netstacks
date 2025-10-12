"""
NetStacks - Web-based Service Stack Management for Network Automation
Connects to Netpalm API for network device automation
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
from datetime import datetime
from netbox_client import NetboxClient
from jinja2 import Template, TemplateSyntaxError
import database as db
import license_manager

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'netstacks-secret-key')

# Configuration
NETPALM_API_URL = os.environ.get('NETPALM_API_URL', 'http://netpalm-controller:9000')
NETPALM_API_KEY = os.environ.get('NETPALM_API_KEY', '2a84465a-cf38-46b2-9d86-b84Q7d57f288')
NETBOX_URL = os.environ.get('NETBOX_URL', 'https://netbox-prprd.gi-nw.viasat.io')
NETBOX_TOKEN = os.environ.get('NETBOX_TOKEN', '')
VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() == 'true'
TASK_HISTORY_FILE = os.environ.get('TASK_HISTORY_FILE', '/tmp/netstacks_tasks.json')
# Database initialized in database.py
# Templates are stored in Netpalm - no local template directory needed

# Setup logging first
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Headers for netpalm API calls
NETPALM_HEADERS = {
    'x-api-key': NETPALM_API_KEY,
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
        NETPALM_API_URL = stored_settings.get('netpalm_url', NETPALM_API_URL).rstrip('/')
        NETPALM_API_KEY = stored_settings.get('netpalm_api_key', NETPALM_API_KEY)
        NETPALM_HEADERS = {
            'x-api-key': NETPALM_API_KEY,
            'Content-Type': 'application/json'
        }
        log.info("Loaded Netpalm settings from database")
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


# License management
@app.context_processor
def inject_license_status():
    """Inject license status into all templates"""
    return {'license_status': license_manager.get_license_status()}


def license_required(feature=None):
    """Decorator to require valid license for routes"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            validation = license_manager.validate_license()
            if not validation['valid']:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'Invalid or expired license',
                        'message': validation['message']
                    }), 403
                return render_template('license_error.html',
                                      message=validation['message'],
                                      license_status=license_manager.get_license_status()), 403

            # Check specific feature if required
            if feature and not license_manager.check_feature_enabled(feature):
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'Feature not available',
                        'message': f'Your license does not include the "{feature}" feature. Please upgrade your license.'
                    }), 403
                return render_template('license_error.html',
                                      message=f'Your license does not include the "{feature}" feature.',
                                      license_status=license_manager.get_license_status()), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Device list cache
device_cache = {
    'devices': None,
    'timestamp': None,
    'ttl': 300  # 5 minutes
}


# Task history management
def save_task_id(task_id, device_name=None):
    """Save a task ID to the history file with device name"""
    try:
        tasks = []
        if os.path.exists(TASK_HISTORY_FILE):
            with open(TASK_HISTORY_FILE, 'r') as f:
                tasks = json.load(f)

        # Add new task with timestamp and device name
        tasks.append({
            'task_id': task_id,
            'device_name': device_name,
            'created': datetime.utcnow().isoformat()
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
        db.set_setting(key, str(value))
    log.info(f"Saved settings to database")
    return True


def get_settings():
    """Get application settings from database"""
    # Default empty settings (must be configured via GUI)
    settings = {
        'netpalm_url': '',
        'netpalm_api_key': '',
        'netbox_url': '',
        'netbox_token': '',
        'verify_ssl': False
    }

    # Load from database
    try:
        stored_settings = db.get_all_settings()
        if stored_settings:
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
    service_data['updated_at'] = datetime.utcnow().isoformat()

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


def delete_service_instance(service_id):
    """Delete a service instance from database"""
    result = db.delete_service_instance(service_id)
    log.info(f"Deleted service instance: {service_id}")
    return result


def update_service_state(service_id, state):
    """Update the state of a service instance"""
    service = get_service_instance(service_id)
    if service:
        service['state'] = state
        service['updated_at'] = datetime.utcnow().isoformat()
        save_service_instance(service)
        return True
    return False


# Service Stack storage functions
def save_service_stack(stack_data):
    """Save a service stack to database"""
    stack_id = stack_data.get('stack_id', str(uuid.uuid4()))
    stack_data['stack_id'] = stack_id
    stack_data['updated_at'] = datetime.utcnow().isoformat()

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
    """Render a Jinja2 template using Netpalm's template system"""
    try:
        # Call Netpalm's j2template render endpoint
        response = requests.post(
            f'{NETPALM_API_URL}/j2template/render/config/{template_name}',
            json=variables,
            headers=NETPALM_HEADERS,
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




def get_device_connection_info(device_name, credential_override=None):
    """Get device connection info from Netbox"""
    try:
        # Get Netbox client with current settings
        netbox = get_netbox_client()

        # Get device from Netbox
        device = netbox.get_device_by_name(device_name)
        if not device or not device.get('name'):
            log.error(f"Device {device_name} not found in Netbox")
            return None

        # Get platform from config_context.nornir.platform (preferred)
        nornir_platform = device.get('config_context', {}).get('nornir', {}).get('platform')

        # Fallback to netbox platform if nornir platform not set
        if not nornir_platform:
            platform = device.get('platform', {})
            manufacturer = device.get('device_type', {}).get('manufacturer', {})
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


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'GET':
        # If already logged in, redirect to dashboard
        if 'username' in session:
            return redirect(url_for('index'))
        return render_template('login.html')

    # Handle POST - login attempt
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return render_template('login.html', error='Username and password are required')

    # Get user from database
    user = get_user(username)
    if not user:
        return render_template('login.html', error='Invalid username or password')

    # Verify password
    if not verify_password(user['password_hash'], password):
        return render_template('login.html', error='Invalid username or password')

    # Login successful - create session
    session['username'] = username
    session['login_time'] = datetime.now().isoformat()

    log.info(f"User {username} logged in successfully")

    # Redirect to dashboard
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    """Logout and clear session"""
    username = session.get('username', 'unknown')
    session.clear()
    log.info(f"User {username} logged out")
    return redirect(url_for('login'))


@app.context_processor
def inject_theme():
    """Inject user's theme preference into all templates"""
    if 'username' in session:
        theme = db.get_user_theme(session['username'])
        return {'user_theme': theme}
    return {'user_theme': 'dark'}


@app.route('/')
@login_required
@login_required
def index():
    """Main dashboard"""
    return render_template('index.html')


@app.route('/deploy')
@login_required
@login_required
def deploy():
    """Config deployment page"""
    return render_template('deploy.html')


@app.route('/monitor')
@login_required
@login_required
def monitor():
    """Job monitoring page"""
    return render_template('monitor.html')


@app.route('/devices')
@login_required
@login_required
def devices():
    """Device list page"""
    return render_template('devices.html')


@app.route('/workers')
@login_required
@login_required
def workers():
    """Workers list page"""
    return render_template('workers.html')


@app.route('/templates')
@login_required
@login_required
def templates_page():
    """Templates management page"""
    return render_template('templates.html')


@app.route('/settings')
@login_required
@login_required
def settings_page():
    """Settings page"""
    return render_template('settings.html')


@app.route('/api/settings', methods=['GET'])
@login_required
@login_required
def get_settings_api():
    """Get current settings from database (or environment defaults)"""
    try:
        settings = get_settings()
        # Don't expose sensitive data in full
        safe_settings = {
            'netpalm_url': settings.get('netpalm_url'),
            'netpalm_api_key': '****' if settings.get('netpalm_api_key') else '',  # Masked
            'netbox_url': settings.get('netbox_url'),
            'netbox_token': '****' if settings.get('netbox_token') else '',  # Masked
            'verify_ssl': settings.get('verify_ssl', False)
        }
        return jsonify({'success': True, 'settings': safe_settings})
    except Exception as e:
        log.error(f"Error getting settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
@login_required
@login_required
def save_settings_api():
    """Save settings to database and update global variables"""
    try:
        global NETPALM_API_URL, NETPALM_API_KEY, NETPALM_HEADERS

        data = request.json

        # Validate required fields
        required_fields = ['netpalm_url', 'netbox_url']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400

        # Prepare settings to save
        settings_to_save = {
            'netpalm_url': data.get('netpalm_url'),
            'netpalm_api_key': data.get('netpalm_api_key'),
            'netbox_url': data.get('netbox_url'),
            'netbox_token': data.get('netbox_token'),
            'verify_ssl': data.get('verify_ssl', False)
        }

        # Save to database
        save_settings(settings_to_save)

        # Update global variables so all endpoints use new settings immediately
        NETPALM_API_URL = settings_to_save['netpalm_url'].rstrip('/')
        NETPALM_API_KEY = settings_to_save['netpalm_api_key']
        NETPALM_HEADERS = {
            'x-api-key': NETPALM_API_KEY,
            'Content-Type': 'application/json'
        }

        log.info(f"Settings saved successfully and globals updated")
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        log.error(f"Error saving settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api-docs')
@login_required
@login_required
def api_docs():
    """Redirect to Netpalm API documentation using configured Netpalm URL"""
    # Use the Netpalm URL from settings (configured via GUI) exactly as entered
    if NETPALM_API_URL:
        return redirect(f'{NETPALM_API_URL}/', code=302)
    else:
        return jsonify({'error': 'Netpalm URL not configured. Please configure via /settings'}), 400


# API Endpoints for frontend

@app.route('/api/devices', methods=['GET', 'POST'])
@login_required
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
        now = datetime.utcnow().timestamp()
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


@app.route('/api/test-netbox', methods=['POST'])
@login_required
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

            return jsonify({
                'success': True,
                'device_count': device_count,
                'response_time': response_time,
                'message': 'Successfully connected to Netbox',
                'api_url': test_url,
                'verify_ssl': verify_ssl,
                'has_token': bool(netbox_token)
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


@app.route('/api/test-netpalm', methods=['POST'])
@login_required
def test_netpalm_connection():
    """Test Netpalm API connection with provided credentials"""
    try:
        import time

        data = request.json
        netpalm_url = data.get('netpalm_url', '').strip()
        netpalm_api_key = data.get('netpalm_api_key', '').strip()

        if not netpalm_url:
            return jsonify({'success': False, 'error': 'Netpalm URL is required'}), 400

        if not netpalm_api_key:
            return jsonify({'success': False, 'error': 'Netpalm API key is required'}), 400

        # Build the test URL (check workers endpoint as a simple test)
        test_url = f"{netpalm_url.rstrip('/')}/workers"

        log.info(f"Testing Netpalm connection to: {test_url}")

        # Prepare headers
        test_headers = {
            'x-api-key': netpalm_api_key,
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

            log.info(f"Netpalm test successful: {worker_count} workers found")

            return jsonify({
                'success': True,
                'worker_count': worker_count,
                'response_time': response_time,
                'message': 'Successfully connected to Netpalm API',
                'api_url': test_url,
                'has_api_key': bool(netpalm_api_key)
            })
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Check your Netpalm API key.',
                'api_url': test_url,
                'status_code': response.status_code
            }), 401
        else:
            return jsonify({
                'success': False,
                'error': f'Netpalm API returned status code {response.status_code}',
                'api_url': test_url,
                'status_code': response.status_code,
                'details': response.text[:200]
            }), 500

    except requests.exceptions.ConnectionError as e:
        log.error(f"Connection Error testing Netpalm: {e}")
        return jsonify({
            'success': False,
            'error': 'Could not connect to Netpalm. Check the URL and network connectivity.',
            'api_url': test_url if 'test_url' in locals() else 'N/A',
            'details': str(e)
        }), 500
    except requests.exceptions.Timeout as e:
        log.error(f"Timeout testing Netpalm: {e}")
        return jsonify({
            'success': False,
            'error': 'Connection to Netpalm timed out after 10 seconds.',
            'api_url': test_url if 'test_url' in locals() else 'N/A'
        }), 500
    except Exception as e:
        log.error(f"Error testing Netpalm connection: {e}")
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
        # Get currently queued tasks from netpalm
        response = requests.get(f'{NETPALM_API_URL}/taskqueue/', headers=NETPALM_HEADERS, timeout=5)
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

        # Return in same format as netpalm
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
        response = requests.get(f'{NETPALM_API_URL}/task/{task_id}', headers=NETPALM_HEADERS, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        log.error(f"Error fetching task {task_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workers')
@login_required
def get_workers():
    """Get all workers from netpalm"""
    try:
        response = requests.get(f'{NETPALM_API_URL}/workers', headers=NETPALM_HEADERS, timeout=5)
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

        # Extract device name if provided
        device_name = data.get('device_name')

        # Forward request to netpalm
        library = data.get('library', 'netmiko')
        endpoint = f'/getconfig/{library}' if library != 'auto' else '/getconfig'

        response = requests.post(
            f'{NETPALM_API_URL}{endpoint}',
            json=data.get('payload'),
            headers=NETPALM_HEADERS,
            timeout=30
        )
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

        # Forward request to netpalm
        library = data.get('library', 'netmiko')
        endpoint = f'/setconfig/{library}' if library != 'auto' else '/setconfig'

        response = requests.post(
            f'{NETPALM_API_URL}{endpoint}',
            json=data.get('payload'),
            headers=NETPALM_HEADERS,
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
            f'{NETPALM_API_URL}/setconfig/dry-run',
            json=data.get('payload'),
            headers=NETPALM_HEADERS,
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
            f'{NETPALM_API_URL}/j2template/config/',
            headers=NETPALM_HEADERS,
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
        # Strip .j2 extension if present (Netpalm adds it automatically)
        if template_name.endswith('.j2'):
            template_name_without_ext = template_name[:-3]
        else:
            template_name_without_ext = template_name

        response = requests.get(
            f'{NETPALM_API_URL}/j2template/config/{template_name_without_ext}',
            headers=NETPALM_HEADERS,
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
    """Create/update J2 template - saves to Netpalm only"""
    try:
        data = request.json
        template_name = data.get('name')
        base64_payload = data.get('base64_payload')

        if not template_name or not base64_payload:
            return jsonify({'success': False, 'error': 'Missing name or base64_payload'}), 400

        # Strip .j2 extension if present (Netpalm handles this)
        if template_name.endswith('.j2'):
            template_name_no_ext = template_name[:-3]
        else:
            template_name_no_ext = template_name

        # Push to Netpalm (primary storage)
        payload = {
            'name': template_name_no_ext,
            'base64_payload': base64_payload
        }

        response = requests.post(
            f'{NETPALM_API_URL}/j2template/config/',
            json=payload,
            headers=NETPALM_HEADERS,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        # Check if netpalm returned success
        if result.get('status') == 'success':
            log.info(f"Saved template to Netpalm: {template_name_no_ext}")
            return jsonify({
                'success': True,
                'message': f'Template saved to Netpalm successfully'
            })
        else:
            error_msg = result.get('data', {}).get('task_result', {}).get('error', 'Unknown error')
            log.error(f"Netpalm save failed: {error_msg}")
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
    """Update template metadata (validation and delete templates)"""
    try:
        data = request.json

        # Strip .j2 extension for consistency
        if template_name.endswith('.j2'):
            template_name = template_name[:-3]

        metadata = {
            'validation_template': data.get('validation_template'),
            'delete_template': data.get('delete_template'),
            'description': data.get('description'),
            'updated_at': datetime.utcnow().isoformat()
        }

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

        response = requests.delete(
            f'{NETPALM_API_URL}/j2template/config/',
            json=payload,
            headers=NETPALM_HEADERS,
            timeout=10
        )
        response.raise_for_status()

        return jsonify({'success': True, 'message': 'Template deleted successfully'})
    except Exception as e:
        log.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/templates/<template_name>/variables')
@login_required
def get_template_variables(template_name):
    """Extract variables from J2 template"""
    try:
        # Strip .j2 extension if present (Netpalm adds it automatically)
        if template_name.endswith('.j2'):
            template_name_without_ext = template_name[:-3]
        else:
            template_name_without_ext = template_name

        # Get template content
        response = requests.get(
            f'{NETPALM_API_URL}/j2template/config/{template_name_without_ext}',
            headers=NETPALM_HEADERS,
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

        # Call netpalm's template render API
        payload = {
            'template_name': template_name,
            'args': variables
        }

        response = requests.post(
            f'{NETPALM_API_URL}/j2template/render/config/{template_name}',
            json=payload,
            headers=NETPALM_HEADERS,
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
            f'{NETPALM_API_URL}/script',
            json=payload,
            headers=NETPALM_HEADERS,
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
                f'{NETPALM_API_URL}/task/{task_id}',
                headers=NETPALM_HEADERS,
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
        # Try to get the schema from netpalm (if it provides one)
        response = requests.get(
            f'{NETPALM_API_URL}/service/schema/{template_name}',
            headers=NETPALM_HEADERS,
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
            f'{NETPALM_API_URL}/setconfig',
            json=setconfig_payload,
            headers=NETPALM_HEADERS,
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
            f'{NETPALM_API_URL}/service/instance/healthcheck/{service_id}',
            headers=NETPALM_HEADERS,
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

        # Check if service has rendered config
        if not service.get('rendered_config'):
            return jsonify({
                'success': False,
                'error': 'Service has no rendered configuration to redeploy'
            }), 400

        # Get credentials from request if provided
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')

        log.info(f"Redeploying service {service_id} to device {service.get('device')}")

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

        # Deploy configuration
        deploy_response = requests.post(
            f'{NETPALM_API_URL}/setconfig',
            headers=NETPALM_HEADERS,
            json={
                'library': 'netmiko',
                'connection_args': device_info['connection_args'],
                'config': service['rendered_config'].split('\n')
            },
            timeout=60
        )

        if deploy_response.status_code != 201:
            raise Exception(f"Failed to deploy configuration: {deploy_response.text}")

        deploy_result = deploy_response.json()
        task_id = deploy_result.get('data', {}).get('task_id')

        if task_id:
            save_task_id(task_id, device_name=f"service_redeploy:{service_id}:{service.get('device')}")

        # Wait for deployment to complete
        max_wait = 60
        waited = 0

        while waited < max_wait:
            time.sleep(2)
            waited += 2

            status_response = requests.get(
                f'{NETPALM_API_URL}/task/{task_id}',
                headers=NETPALM_HEADERS,
                timeout=10
            )

            if status_response.status_code == 200:
                task_status = status_response.json()
                task_data = task_status.get('data', {})

                if task_data.get('task_status') == 'finished':
                    # Update service instance to deployed state
                    service['state'] = 'deployed'
                    service['task_id'] = task_id
                    service['deployed_at'] = datetime.utcnow().isoformat()
                    if 'error' in service:
                        del service['error']
                    save_service_instance(service)

                    return jsonify({
                        'success': True,
                        'task_id': task_id,
                        'message': f'Service redeployed successfully to {service["device"]}'
                    })
                elif task_data.get('task_status') == 'failed':
                    error_msg = task_data.get('task_errors', 'Deployment failed')
                    # Update service to failed state
                    service['state'] = 'failed'
                    service['error'] = str(error_msg)
                    service['task_id'] = task_id
                    save_service_instance(service)

                    return jsonify({
                        'success': False,
                        'error': f'Deployment failed: {error_msg}'
                    }), 500

        return jsonify({
            'success': False,
            'error': 'Timeout waiting for deployment to complete'
        }), 500

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

            # Render delete template using Netpalm
            template_name = delete_template[:-3] if delete_template.endswith('.j2') else delete_template
            rendered_config = render_j2_template(template_name, service.get('variables', {}))

            if not rendered_config:
                return jsonify({
                    'success': False,
                    'error': f'Failed to render delete template: {delete_template}'
                }), 500

            log.info(f"Rendered delete config: {rendered_config[:200]}...")

            # Push delete config to device
            setconfig_payload = {
                'library': 'netmiko',
                'connection_args': device_info['connection_args'],
                'config': rendered_config.split('\n'),
                'queue_strategy': 'fifo'
            }

            response = requests.post(
                f'{NETPALM_API_URL}/setconfig',
                json=setconfig_payload,
                headers=NETPALM_HEADERS,
                timeout=60
            )

            if response.status_code != 201:
                return jsonify({
                    'success': False,
                    'error': f'Failed to execute delete on device: {response.text}'
                }), 500

            result = response.json()
            task_id = result.get('data', {}).get('task_id')

            if task_id:
                save_task_id(task_id, device_name=f"service_delete:{service_id}")

            # Wait for deletion task to complete
            log.info(f"Waiting for deletion task {task_id} to complete...")
            max_wait = 60
            waited = 0
            while waited < max_wait:
                time.sleep(2)
                waited += 2

                task_response = requests.get(
                    f'{NETPALM_API_URL}/task/{task_id}',
                    headers=NETPALM_HEADERS,
                    timeout=10
                )
                task_data = task_response.json()
                task_status = task_data.get('data', {}).get('task_status')

                if task_status == 'finished':
                    log.info(f"Delete task completed successfully")
                    break
                elif task_status == 'failed':
                    task_errors = task_data.get('data', {}).get('task_errors', [])
                    return jsonify({
                        'success': False,
                        'error': f'Delete task failed: {task_errors}',
                        'task_id': task_id
                    }), 500

            if waited >= max_wait:
                return jsonify({
                    'success': False,
                    'error': 'Timeout waiting for delete task to complete',
                    'task_id': task_id
                }), 500

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
            f'{NETPALM_API_URL}/task/{task_id}',
            headers=NETPALM_HEADERS,
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

        # Check if service has rendered config
        if not service.get('rendered_config'):
            return jsonify({
                'success': False,
                'error': 'Service has no rendered configuration to validate'
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
            f'{NETPALM_API_URL}/getconfig',
            json=getconfig_payload,
            headers=NETPALM_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        task_id = result.get('data', {}).get('task_id')
        if task_id:
            save_task_id(task_id, device_name=f"validate:{service_id}")

        # Poll for task completion (simple approach for now)
        import time
        max_wait = 30
        waited = 0
        running_config = None

        while waited < max_wait:
            time.sleep(2)
            waited += 2

            task_response = requests.get(
                f'{NETPALM_API_URL}/task/{task_id}',
                headers=NETPALM_HEADERS,
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

        # Get validation config - use validation template if specified, otherwise use deployed config
        validation_template = service.get('validation_template')
        if validation_template:
            # Render validation template with service variables
            log.info(f"Using validation template: {validation_template}")
            template_lookup = validation_template[:-3] if validation_template.endswith('.j2') else validation_template
            validation_config = render_j2_template(template_lookup, service.get('variables', {}))

            if not validation_config:
                log.warning(f"Failed to render validation template, falling back to deployed config")
                validation_config = service['rendered_config']

            rendered_lines = [line.strip() for line in validation_config.split('\n') if line.strip()]
        else:
            # Use deployed config for validation
            rendered_lines = [line.strip() for line in service['rendered_config'].split('\n') if line.strip()]

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
        service['last_validated'] = datetime.utcnow().isoformat()
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
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
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
            stack['pending_since'] = datetime.utcnow().isoformat()

        stack['updated_at'] = datetime.utcnow().isoformat()

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

        # Optional: Delete associated service instances
        delete_services = request.args.get('delete_services', 'false').lower() == 'true'

        if delete_services and 'deployed_services' in stack:
            for service_id in stack.get('deployed_services', []):
                try:
                    delete_service_instance(service_id)
                except Exception as e:
                    log.warning(f"Failed to delete service {service_id}: {e}")

        delete_service_stack(stack_id)

        return jsonify({
            'success': True,
            'message': f'Service stack "{stack["name"]}" deleted successfully'
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
        stack['deploy_started_at'] = datetime.utcnow().isoformat()
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

                log.info(f"Rendering template: '{template_name}' with variables: {variables}")

                # Render template using Netpalm
                rendered_config = render_j2_template(template_name, variables)

                if not rendered_config:
                    raise Exception(f"Failed to render template: {template_name}")

                log.info(f"Rendered config preview: {rendered_config[:200]}...")

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
                        # Check if device already has this exact config deployed
                        existing_service = None
                        if stack.get('deployed_services'):
                            for existing_id in stack.get('deployed_services', []):
                                existing = get_service_instance(existing_id)
                                if existing and existing.get('device') == device_name and existing.get('name', '').startswith(service_def['name']):
                                    existing_service = existing
                                    break

                        # Compare rendered config with existing service
                        if existing_service and existing_service.get('rendered_config') == rendered_config and existing_service.get('state') == 'deployed':
                            log.info(f"Skipping {device_name} - configuration unchanged")
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

                        log.info(f"Deploying configuration to {device_name} (config changed or new)")
                        # Deploy configuration
                        deploy_response = requests.post(
                            f'{NETPALM_API_URL}/setconfig',
                            headers=NETPALM_HEADERS,
                            json={
                                'library': 'netmiko',
                                'connection_args': device_info['connection_args'],
                                'config': rendered_config.split('\n')
                            },
                            timeout=60
                        )

                        log.info(f"Deploy response status: {deploy_response.status_code}")
                        if deploy_response.status_code != 201:
                            raise Exception(f"Failed to deploy configuration to {device_name}: {deploy_response.text}")

                        deploy_result = deploy_response.json()
                        task_id = deploy_result.get('data', {}).get('task_id')
                        log.info(f"Got task_id: {task_id}")

                        # Save task to history for monitoring
                        save_task_id(task_id, device_name=f"stack:{stack.get('name')}:{service_def['name']}:{device_name}")

                        # Wait for deployment to complete (with timeout)
                        max_wait = 60
                        waited = 0
                        task_error = None

                        while waited < max_wait:
                            time.sleep(2)
                            waited += 2

                            status_response = requests.get(
                                f'{NETPALM_API_URL}/task/{task_id}',
                                headers=NETPALM_HEADERS,
                                timeout=10
                            )

                            if status_response.status_code == 200:
                                task_status = status_response.json()
                                task_data = task_status.get('data', {})

                                if task_data.get('task_status') == 'finished':
                                    break
                                elif task_data.get('task_status') == 'failed':
                                    task_error = task_data.get('task_errors')
                                    raise Exception(f"Deployment task failed on {device_name}: {task_error}")

                        # Create service instance record for this device
                        service_instance = {
                            'service_id': str(uuid.uuid4()),
                            'name': f"{service_def['name']} ({device_name})",
                            'template': service_def['template'],
                            'validation_template': template_metadata.get('validation_template'),
                            'delete_template': template_metadata.get('delete_template'),
                            'device': device_name,
                            'variables': variables,
                            'rendered_config': rendered_config,
                            'state': 'deployed',
                            'task_id': task_id,
                            'stack_id': stack_id,
                            'stack_order': service_def.get('order', 0),
                            'created_at': datetime.utcnow().isoformat()
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
                            'template': service_def['template'],
                            'validation_template': template_metadata.get('validation_template'),
                            'delete_template': template_metadata.get('delete_template'),
                            'device': device_name,
                            'variables': variables,
                            'rendered_config': rendered_config,
                            'state': 'failed',
                            'error': str(device_error),
                            'stack_id': stack_id,
                            'stack_order': service_def.get('order', 0),
                            'created_at': datetime.utcnow().isoformat()
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
        if failed_services:
            # Check if we have ANY successful deployments
            has_successes = len(deployed_service_ids) > 0
            if has_successes:
                stack['state'] = 'partial'  # Some succeeded, some failed
            else:
                stack['state'] = 'failed'  # Everything failed
            stack['deployment_errors'] = failed_services
        else:
            stack['state'] = 'deployed'

        stack['deployed_services'] = deployed_service_ids
        stack['deploy_completed_at'] = datetime.utcnow().isoformat()

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
                ctx = app.test_request_context(
                    f'/api/services/instances/{service_id}/validate',
                    method='POST',
                    json={'username': username, 'password': password},
                    content_type='application/json'
                )
                ctx.push()

                try:
                    # Call the service validation function directly
                    response = validate_service_instance(service_id)

                    # Handle None response
                    if response is None:
                        raise Exception("Validation returned None - check service instance state")

                    # Extract JSON data from response
                    if isinstance(response, tuple):
                        response_obj = response[0]
                        response_data = response_obj.get_json() if response_obj else None
                    else:
                        response_data = response.get_json() if response else None

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
                log.error(f"Error validating service {service_id}: {e}")
                validation_results.append({
                    'service_id': service_id,
                    'service_name': service.get('name'),
                    'valid': False,
                    'message': f'Validation error: {str(e)}'
                })
                all_valid = False

        # Update stack validation status
        stack['last_validated'] = datetime.utcnow().isoformat()
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
                        f'{NETPALM_API_URL}/j2template/config/{template_name_clean}',
                        headers=NETPALM_HEADERS,
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


# ===== License Management Routes =====

@app.route('/license')
@login_required
def license_page():
    """License management page"""
    return render_template('license.html')


@app.route('/api/license/status', methods=['GET'])
@login_required
def get_license_status_endpoint():
    """Get current license status"""
    try:
        status = license_manager.get_license_status()
        return jsonify(status)
    except Exception as e:
        log.error(f"Error getting license status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/license/install', methods=['POST'])
@login_required
def install_license_endpoint():
    """Install a license key"""
    try:
        data = request.json
        license_key = data.get('license_key', '').strip()

        if not license_key:
            return jsonify({'success': False, 'error': 'License key is required'}), 400

        # Check if license exists in database
        license_data = db.get_license(license_key)
        if not license_data:
            return jsonify({
                'success': False,
                'error': 'Invalid license key. Please contact support.'
            }), 400

        # Activate the license
        db.activate_license(license_key)

        validation = license_manager.validate_license(license_key)

        return jsonify({
            'success': True,
            'message': 'License installed successfully',
            'license': validation.get('license'),
            'status': license_manager.get_license_status()
        })

    except Exception as e:
        log.error(f"Error installing license: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/trial', methods=['POST'])
@login_required
def install_trial_license_endpoint():
    """Install a trial license"""
    try:
        data = request.json or {}
        company_name = data.get('company_name', 'Trial Company')
        contact_email = data.get('contact_email', '')

        license_data = license_manager.install_trial_license(company_name, contact_email)

        return jsonify({
            'success': True,
            'message': '30-day trial license created successfully',
            'license': license_data,
            'status': license_manager.get_license_status()
        })

    except Exception as e:
        log.error(f"Error creating trial license: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/generate', methods=['POST'])
@login_required
def generate_license_endpoint():
    """Generate a new license (admin only)"""
    try:
        data = request.json

        required_fields = ['company_name', 'license_type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400

        license_data = license_manager.create_license(
            company_name=data['company_name'],
            license_type=data.get('license_type', 'standard'),
            contact_email=data.get('contact_email', ''),
            duration_days=data.get('duration_days', 365),
            max_devices=data.get('max_devices', -1),
            max_users=data.get('max_users', -1),
            notes=data.get('notes', '')
        )

        return jsonify({
            'success': True,
            'message': 'License generated successfully',
            'license': license_data
        })

    except Exception as e:
        log.error(f"Error generating license: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/all', methods=['GET'])
@login_required
def get_all_licenses_endpoint():
    """Get all licenses (admin only)"""
    try:
        licenses = db.get_all_licenses()
        return jsonify(licenses)
    except Exception as e:
        log.error(f"Error getting licenses: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/license/<license_key>/deactivate', methods=['POST'])
@login_required
def deactivate_license_endpoint(license_key):
    """Deactivate a license"""
    try:
        success = db.deactivate_license(license_key)
        if success:
            return jsonify({
                'success': True,
                'message': 'License deactivated successfully',
                'status': license_manager.get_license_status()
            })
        return jsonify({'success': False, 'error': 'License not found'}), 404
    except Exception as e:
        log.error(f"Error deactivating license: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/<license_key>/activate', methods=['POST'])
@login_required
def activate_license_endpoint(license_key):
    """Activate a license"""
    try:
        success = db.activate_license(license_key)
        if success:
            return jsonify({
                'success': True,
                'message': 'License activated successfully',
                'status': license_manager.get_license_status()
            })
        return jsonify({'success': False, 'error': 'License not found'}), 404
    except Exception as e:
        log.error(f"Error activating license: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088, debug=True)
