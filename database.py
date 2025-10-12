"""
SQLite Database Layer for NetStacks
Replaces Redis with a persistent SQLite database
"""
import sqlite3
import json
import logging
from datetime import datetime
from contextlib import contextmanager
import os

log = logging.getLogger(__name__)

DB_FILE = os.environ.get('DB_FILE', '/data/netstacks.db')

def init_db():
    """Initialize the SQLite database with schema"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            theme TEXT DEFAULT 'dark',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Templates metadata table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            name TEXT PRIMARY KEY,
            validation_template TEXT,
            delete_template TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Service stacks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_stacks (
            stack_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            services TEXT NOT NULL,  -- JSON array
            shared_variables TEXT,   -- JSON object
            state TEXT DEFAULT 'pending',
            has_pending_changes INTEGER DEFAULT 0,
            pending_since TIMESTAMP,
            deployed_services TEXT,  -- JSON array of service IDs
            deployment_errors TEXT,  -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deploy_started_at TIMESTAMP,
            deploy_completed_at TIMESTAMP,
            last_validated TIMESTAMP,
            validation_status TEXT
        )
    ''')

    # Service instances table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_instances (
            service_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            template TEXT NOT NULL,
            validation_template TEXT,
            delete_template TEXT,
            device TEXT NOT NULL,
            variables TEXT,          -- JSON object
            rendered_config TEXT,
            state TEXT DEFAULT 'pending',
            error TEXT,
            task_id TEXT,
            stack_id TEXT,
            stack_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deployed_at TIMESTAMP,
            last_validated TIMESTAMP,
            validation_status TEXT,
            validation_errors TEXT,  -- JSON array
            FOREIGN KEY (stack_id) REFERENCES service_stacks(stack_id) ON DELETE CASCADE
        )
    ''')

    # Manual devices table (alternative to Netbox)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manual_devices (
            device_name TEXT PRIMARY KEY,
            device_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER DEFAULT 22,
            username TEXT,
            password TEXT,
            enable_password TEXT,
            description TEXT,
            manufacturer TEXT,
            model TEXT,
            site TEXT,
            tags TEXT,  -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Stack templates table (reusable stack configurations)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stack_templates (
            template_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            services TEXT NOT NULL,  -- JSON array of service definitions with device templates
            required_variables TEXT, -- JSON array of all variables needed across all device templates
            tags TEXT,               -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
    ''')

    # License table for NetStacks Pro
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            contact_email TEXT,
            license_type TEXT NOT NULL,  -- 'trial', 'standard', 'professional', 'enterprise'
            max_devices INTEGER DEFAULT -1,  -- -1 means unlimited
            max_users INTEGER DEFAULT -1,    -- -1 means unlimited
            features TEXT,                   -- JSON array of enabled features
            issued_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiration_date TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Authentication configuration table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_config (
            config_id INTEGER PRIMARY KEY AUTOINCREMENT,
            auth_type TEXT NOT NULL,  -- 'local', 'ldap', 'oidc'
            is_enabled INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0,  -- Order of authentication attempts
            config_data TEXT,  -- JSON configuration for the auth method
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_instances_stack ON service_instances(stack_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_instances_device ON service_instances(device)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_stacks_state ON service_stacks(state)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_manual_devices_type ON manual_devices(device_type)')

    # Migration: Add theme column to existing users table if it doesn't exist
    try:
        cursor.execute("SELECT theme FROM users LIMIT 1")
    except sqlite3.OperationalError:
        log.info("Migrating users table: adding theme column")
        cursor.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'dark'")

    conn.commit()
    conn.close()

    log.info(f"Database initialized at {DB_FILE}")

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# Settings operations
def get_setting(key, default=None):
    """Get a setting value"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

def set_setting(key, value):
    """Set a setting value"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, value))

def get_all_settings():
    """Get all settings as dict with proper type conversion"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        settings = {}
        for row in cursor.fetchall():
            key = row['key']
            value = row['value']
            # Convert verify_ssl to boolean
            if key == 'verify_ssl':
                settings[key] = value.lower() in ('true', '1', 'yes') if isinstance(value, str) else bool(value)
            else:
                settings[key] = value
        return settings

# User operations
def get_user(username):
    """Get user by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_user(username, password_hash):
    """Create a new user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
        ''', (username, password_hash))

def delete_user(username):
    """Delete a user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE username = ?', (username,))
        return cursor.rowcount > 0

def get_all_users():
    """Get all users"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, created_at FROM users ORDER BY username')
        return [dict(row) for row in cursor.fetchall()]

def set_user_theme(username, theme):
    """Set user's theme preference"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET theme = ? WHERE username = ?', (theme, username))
        return cursor.rowcount > 0

def get_user_theme(username):
    """Get user's theme preference"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT theme FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return row['theme'] if row else 'dark'

# Template metadata operations
def get_template_metadata(name):
    """Get template metadata"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM templates WHERE name = ?', (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

def save_template_metadata(name, metadata):
    """Save template metadata"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO templates
            (name, validation_template, delete_template, description, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            name,
            metadata.get('validation_template'),
            metadata.get('delete_template'),
            metadata.get('description')
        ))

def delete_template_metadata(name):
    """Delete template metadata"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM templates WHERE name = ?', (name,))
        return cursor.rowcount > 0

def get_all_templates():
    """Get all template metadata"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM templates ORDER BY name')
        return [dict(row) for row in cursor.fetchall()]

def get_all_template_metadata():
    """Get all template metadata as dict keyed by template name"""
    templates = get_all_templates()
    return {t['name']: t for t in templates}

# Service stack operations
def get_service_stack(stack_id):
    """Get service stack by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_stacks WHERE stack_id = ?', (stack_id,))
        row = cursor.fetchone()
        if not row:
            return None

        stack = dict(row)
        # Parse JSON fields
        stack['services'] = json.loads(stack['services']) if stack['services'] else []
        stack['shared_variables'] = json.loads(stack['shared_variables']) if stack['shared_variables'] else {}
        stack['deployed_services'] = json.loads(stack['deployed_services']) if stack['deployed_services'] else []
        stack['deployment_errors'] = json.loads(stack['deployment_errors']) if stack['deployment_errors'] else []
        stack['has_pending_changes'] = bool(stack['has_pending_changes'])
        return stack

def save_service_stack(stack):
    """Save or update service stack"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO service_stacks
            (stack_id, name, description, services, shared_variables, state,
             has_pending_changes, pending_since, deployed_services, deployment_errors,
             created_at, updated_at, deploy_started_at, deploy_completed_at,
             last_validated, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stack['stack_id'],
            stack['name'],
            stack.get('description', ''),
            json.dumps(stack.get('services', [])),
            json.dumps(stack.get('shared_variables', {})),
            stack.get('state', 'pending'),
            1 if stack.get('has_pending_changes') else 0,
            stack.get('pending_since'),
            json.dumps(stack.get('deployed_services', [])),
            json.dumps(stack.get('deployment_errors', [])),
            stack.get('created_at'),
            stack.get('updated_at'),
            stack.get('deploy_started_at'),
            stack.get('deploy_completed_at'),
            stack.get('last_validated'),
            stack.get('validation_status')
        ))

def delete_service_stack(stack_id):
    """Delete service stack"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM service_stacks WHERE stack_id = ?', (stack_id,))
        return cursor.rowcount > 0

def get_all_service_stacks():
    """Get all service stacks"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_stacks ORDER BY created_at DESC')
        stacks = []
        for row in cursor.fetchall():
            stack = dict(row)
            stack['services'] = json.loads(stack['services']) if stack['services'] else []
            stack['shared_variables'] = json.loads(stack['shared_variables']) if stack['shared_variables'] else {}
            stack['deployed_services'] = json.loads(stack['deployed_services']) if stack['deployed_services'] else []
            stack['deployment_errors'] = json.loads(stack['deployment_errors']) if stack['deployment_errors'] else []
            stack['has_pending_changes'] = bool(stack['has_pending_changes'])
            stacks.append(stack)
        return stacks

# Service instance operations
def get_service_instance(service_id):
    """Get service instance by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_instances WHERE service_id = ?', (service_id,))
        row = cursor.fetchone()
        if not row:
            return None

        service = dict(row)
        # Parse JSON fields
        service['variables'] = json.loads(service['variables']) if service['variables'] else {}
        service['validation_errors'] = json.loads(service['validation_errors']) if service['validation_errors'] else []
        return service

def save_service_instance(service):
    """Save or update service instance"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO service_instances
            (service_id, name, template, validation_template, delete_template,
             device, variables, rendered_config, state, error, task_id,
             stack_id, stack_order, created_at, deployed_at,
             last_validated, validation_status, validation_errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            service['service_id'],
            service['name'],
            service['template'],
            service.get('validation_template'),
            service.get('delete_template'),
            service['device'],
            json.dumps(service.get('variables', {})),
            service.get('rendered_config'),
            service.get('state', 'pending'),
            service.get('error'),
            service.get('task_id'),
            service.get('stack_id'),
            service.get('stack_order', 0),
            service.get('created_at'),
            service.get('deployed_at'),
            service.get('last_validated'),
            service.get('validation_status'),
            json.dumps(service.get('validation_errors', []))
        ))

def delete_service_instance(service_id):
    """Delete service instance"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM service_instances WHERE service_id = ?', (service_id,))
        return cursor.rowcount > 0

def get_all_service_instances():
    """Get all service instances"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_instances ORDER BY created_at DESC')
        services = []
        for row in cursor.fetchall():
            service = dict(row)
            service['variables'] = json.loads(service['variables']) if service['variables'] else {}
            service['validation_errors'] = json.loads(service['validation_errors']) if service['validation_errors'] else []
            services.append(service)
        return services

# Manual device operations
def get_manual_device(device_name):
    """Get manual device by name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM manual_devices WHERE device_name = ?', (device_name,))
        row = cursor.fetchone()
        if not row:
            return None

        device = dict(row)
        device['tags'] = json.loads(device['tags']) if device['tags'] else []
        return device

def save_manual_device(device):
    """Save or update manual device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO manual_devices
            (device_name, device_type, host, port, username, password, enable_password,
             description, manufacturer, model, site, tags, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            device['device_name'],
            device['device_type'],
            device['host'],
            device.get('port', 22),
            device.get('username'),
            device.get('password'),
            device.get('enable_password'),
            device.get('description', ''),
            device.get('manufacturer', ''),
            device.get('model', ''),
            device.get('site', ''),
            json.dumps(device.get('tags', []))
        ))

def delete_manual_device(device_name):
    """Delete manual device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM manual_devices WHERE device_name = ?', (device_name,))
        return cursor.rowcount > 0

def get_all_manual_devices():
    """Get all manual devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM manual_devices ORDER BY device_name')
        devices = []
        for row in cursor.fetchall():
            device = dict(row)
            device['tags'] = json.loads(device['tags']) if device['tags'] else []
            devices.append(device)
        return devices

# Stack Template operations
def save_stack_template(template_data):
    """Save a stack template"""
    import uuid
    with get_db() as conn:
        cursor = conn.cursor()
        template_id = template_data.get('template_id') or str(uuid.uuid4())

        cursor.execute('''
            INSERT OR REPLACE INTO stack_templates
            (template_id, name, description, services, required_variables, tags, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            template_id,
            template_data['name'],
            template_data.get('description', ''),
            json.dumps(template_data['services']),
            json.dumps(template_data.get('required_variables', [])),
            json.dumps(template_data.get('tags', [])),
            template_data.get('created_by', '')
        ))
        return template_id

def get_stack_template(template_id):
    """Get a stack template by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stack_templates WHERE template_id = ?', (template_id,))
        row = cursor.fetchone()
        if row:
            template = dict(row)
            template['services'] = json.loads(template['services'])
            template['required_variables'] = json.loads(template['required_variables']) if template['required_variables'] else []
            template['tags'] = json.loads(template['tags']) if template['tags'] else []
            return template
        return None

def get_all_stack_templates():
    """Get all stack templates"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stack_templates ORDER BY name')
        templates = []
        for row in cursor.fetchall():
            template = dict(row)
            template['services'] = json.loads(template['services'])
            template['required_variables'] = json.loads(template['required_variables']) if template['required_variables'] else []
            template['tags'] = json.loads(template['tags']) if template['tags'] else []
            templates.append(template)
        return templates

def delete_stack_template(template_id):
    """Delete a stack template"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM stack_templates WHERE template_id = ?', (template_id,))
        return cursor.rowcount > 0

# License operations
def save_license(license_data):
    """Save or update a license"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO licenses
            (license_key, company_name, contact_email, license_type, max_devices, max_users,
             features, issued_date, expiration_date, is_active, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            license_data['license_key'],
            license_data['company_name'],
            license_data.get('contact_email', ''),
            license_data['license_type'],
            license_data.get('max_devices', -1),
            license_data.get('max_users', -1),
            json.dumps(license_data.get('features', [])),
            license_data.get('issued_date'),
            license_data.get('expiration_date'),
            1 if license_data.get('is_active', True) else 0,
            license_data.get('notes', '')
        ))

def get_active_license():
    """Get the currently active license"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM licenses
            WHERE is_active = 1
            AND (expiration_date IS NULL OR expiration_date > datetime('now'))
            ORDER BY issued_date DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        if row:
            license_data = dict(row)
            license_data['features'] = json.loads(license_data['features']) if license_data['features'] else []
            license_data['is_active'] = bool(license_data['is_active'])
            return license_data
        return None

def get_license(license_key):
    """Get a license by key"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        row = cursor.fetchone()
        if row:
            license_data = dict(row)
            license_data['features'] = json.loads(license_data['features']) if license_data['features'] else []
            license_data['is_active'] = bool(license_data['is_active'])
            return license_data
        return None

def get_all_licenses():
    """Get all licenses"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM licenses ORDER BY issued_date DESC')
        licenses = []
        for row in cursor.fetchall():
            license_data = dict(row)
            license_data['features'] = json.loads(license_data['features']) if license_data['features'] else []
            license_data['is_active'] = bool(license_data['is_active'])
            licenses.append(license_data)
        return licenses

def deactivate_license(license_key):
    """Deactivate a license"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE licenses SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE license_key = ?', (license_key,))
        return cursor.rowcount > 0

def activate_license(license_key):
    """Activate a license"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE licenses SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE license_key = ?', (license_key,))
        return cursor.rowcount > 0

def delete_license(license_key):
    """Delete a license"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM licenses WHERE license_key = ?', (license_key,))
        return cursor.rowcount > 0

# Authentication configuration operations
def save_auth_config(auth_type, config_data, is_enabled=True, priority=0):
    """Save or update authentication configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if config exists
        cursor.execute('SELECT config_id FROM auth_config WHERE auth_type = ?', (auth_type,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('''
                UPDATE auth_config
                SET config_data = ?, is_enabled = ?, priority = ?, updated_at = CURRENT_TIMESTAMP
                WHERE auth_type = ?
            ''', (json.dumps(config_data), 1 if is_enabled else 0, priority, auth_type))
        else:
            cursor.execute('''
                INSERT INTO auth_config (auth_type, config_data, is_enabled, priority)
                VALUES (?, ?, ?, ?)
            ''', (auth_type, json.dumps(config_data), 1 if is_enabled else 0, priority))

def get_auth_config(auth_type):
    """Get authentication configuration by type"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auth_config WHERE auth_type = ?', (auth_type,))
        row = cursor.fetchone()
        if row:
            config = dict(row)
            config['config_data'] = json.loads(config['config_data']) if config['config_data'] else {}
            config['is_enabled'] = bool(config['is_enabled'])
            return config
        return None

def get_all_auth_configs():
    """Get all authentication configurations ordered by priority"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auth_config ORDER BY priority ASC')
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            config['config_data'] = json.loads(config['config_data']) if config['config_data'] else {}
            config['is_enabled'] = bool(config['is_enabled'])
            configs.append(config)
        return configs

def get_enabled_auth_configs():
    """Get all enabled authentication configurations ordered by priority"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auth_config WHERE is_enabled = 1 ORDER BY priority ASC')
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            config['config_data'] = json.loads(config['config_data']) if config['config_data'] else {}
            config['is_enabled'] = bool(config['is_enabled'])
            configs.append(config)
        return configs

def delete_auth_config(auth_type):
    """Delete an authentication configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM auth_config WHERE auth_type = ?', (auth_type,))
        return cursor.rowcount > 0

def toggle_auth_config(auth_type, enabled):
    """Enable or disable an authentication method"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE auth_config
            SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE auth_type = ?
        ''', (1 if enabled else 0, auth_type))
        return cursor.rowcount > 0
