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
            auth_source TEXT DEFAULT 'local',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: Add auth_source column if it doesn't exist
    try:
        cursor.execute("SELECT auth_source FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN auth_source TEXT DEFAULT 'local'")
        conn.commit()

    # Templates metadata table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            name TEXT PRIMARY KEY,
            type TEXT DEFAULT 'deploy',  -- deploy, delete, validation
            validation_template TEXT,
            delete_template TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: Add type column if it doesn't exist
    try:
        cursor.execute("SELECT type FROM templates LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE templates ADD COLUMN type TEXT DEFAULT 'deploy'")
        conn.commit()

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
            api_variables TEXT,      -- JSON object: {var_name: {url, method, headers, json_path, description}}
            tags TEXT,               -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
    ''')

    # Migration: Add api_variables column if it doesn't exist
    try:
        cursor.execute("SELECT api_variables FROM stack_templates LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE stack_templates ADD COLUMN api_variables TEXT")

    # Migration: Add per_device_variables column if it doesn't exist
    try:
        cursor.execute("SELECT per_device_variables FROM stack_templates LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE stack_templates ADD COLUMN per_device_variables TEXT")

    # API Resources table (reusable API configurations)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_resources (
            resource_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            base_url TEXT NOT NULL,
            auth_type TEXT,              -- 'none', 'bearer', 'basic', 'header', 'api_key'
            auth_token TEXT,             -- For bearer/api_key auth
            auth_username TEXT,          -- For basic auth
            auth_password TEXT,          -- For basic auth
            custom_headers TEXT,         -- JSON object with additional headers
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
    ''')

    # Scheduled stack operations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_stack_operations (
            schedule_id TEXT PRIMARY KEY,
            stack_id TEXT,                 -- NULL for config_deploy operations
            operation_type TEXT NOT NULL,  -- 'deploy', 'validate', 'delete', 'config_deploy'
            schedule_type TEXT NOT NULL,   -- 'once', 'daily', 'weekly', 'monthly'
            scheduled_time TEXT NOT NULL,  -- ISO format datetime for 'once', or time for recurring (HH:MM)
            day_of_week INTEGER,           -- 0-6 for weekly schedules (0=Monday)
            day_of_month INTEGER,          -- 1-31 for monthly schedules
            config_data TEXT,              -- JSON config for config_deploy operations
            enabled INTEGER DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            run_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            FOREIGN KEY (stack_id) REFERENCES service_stacks(stack_id) ON DELETE CASCADE
        )
    ''')

    # Migration: Add config_data column if it doesn't exist
    try:
        cursor.execute("SELECT config_data FROM scheduled_stack_operations LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE scheduled_stack_operations ADD COLUMN config_data TEXT")
        conn.commit()

    # Migration: Make stack_id nullable for config_deploy operations
    # Check if stack_id has NOT NULL constraint
    cursor.execute("PRAGMA table_info(scheduled_stack_operations)")
    columns = cursor.fetchall()
    stack_id_column = [col for col in columns if col[1] == 'stack_id']

    if stack_id_column and stack_id_column[0][3] == 1:  # notnull flag is 1
        # Need to recreate table without NOT NULL on stack_id
        log.info("Migrating scheduled_stack_operations table to make stack_id nullable")

        # Create temporary table with new schema
        cursor.execute('''
            CREATE TABLE scheduled_stack_operations_new (
                schedule_id TEXT PRIMARY KEY,
                stack_id TEXT,
                operation_type TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                day_of_week INTEGER,
                day_of_month INTEGER,
                config_data TEXT,
                enabled INTEGER DEFAULT 1,
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                run_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        ''')

        # Copy data from old table
        cursor.execute('''
            INSERT INTO scheduled_stack_operations_new
            SELECT * FROM scheduled_stack_operations
        ''')

        # Drop old table
        cursor.execute("DROP TABLE scheduled_stack_operations")

        # Rename new table
        cursor.execute("ALTER TABLE scheduled_stack_operations_new RENAME TO scheduled_stack_operations")

        conn.commit()
        log.info("Migration completed: stack_id is now nullable")

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

    # Menu items table for custom menu ordering
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu_items (
            item_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            icon TEXT NOT NULL,
            url TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            visible INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # MOP (Method of Procedures) tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mops (
            mop_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            devices TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: Add devices column to mops if it doesn't exist
    try:
        cursor.execute("SELECT devices FROM mops LIMIT 1")
    except sqlite3.OperationalError:
        log.info("Migrating mops table: adding devices column")
        cursor.execute("ALTER TABLE mops ADD COLUMN devices TEXT")
        conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mop_steps (
            step_id TEXT PRIMARY KEY,
            mop_id TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            step_type TEXT NOT NULL,
            step_name TEXT NOT NULL,
            devices TEXT,
            config TEXT,
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY (mop_id) REFERENCES mops(mop_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mop_executions (
            execution_id TEXT PRIMARY KEY,
            mop_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            current_step INTEGER DEFAULT 0,
            results TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (mop_id) REFERENCES mops(mop_id)
        )
    ''')

    # Add context and error columns if they don't exist (migration)
    try:
        cursor.execute('ALTER TABLE mop_executions ADD COLUMN context TEXT')
    except:
        pass  # Column already exists

    try:
        cursor.execute('ALTER TABLE mop_executions ADD COLUMN error TEXT')
    except:
        pass  # Column already exists

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mop_steps_mop ON mop_steps(mop_id, step_order)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mop_executions_mop ON mop_executions(mop_id)')

    # Initialize default menu items if table is empty
    cursor.execute("SELECT COUNT(*) FROM menu_items")
    if cursor.fetchone()[0] == 0:
        default_menu_items = [
            ('dashboard', 'Dashboard', 'home', '/', 0, 1),
            ('deploy', 'Deploy Config', 'rocket', '/deploy', 1, 1),
            ('monitor', 'Monitor Jobs', 'chart-line', '/monitor', 2, 1),
            ('templates', 'Config Templates', 'file-code', '/templates', 3, 1),
            ('service-stacks', 'Service Stacks', 'layer-group', '/service-stacks', 4, 1),
            ('devices', 'Devices', 'server', '/devices', 5, 1),
            ('network-map', 'Network Map', 'project-diagram', '/network-map', 6, 1),
            ('mop', 'Procedures (MOP)', 'list-check', '/mop', 7, 1),
        ]
        cursor.executemany('''
            INSERT INTO menu_items (item_id, label, icon, url, order_index, visible)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', default_menu_items)

    # Migration: Add MOP menu item if it doesn't exist
    cursor.execute("SELECT COUNT(*) FROM menu_items WHERE item_id = 'mop'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO menu_items (item_id, label, icon, url, order_index, visible)
            VALUES ('mop', 'Procedures (MOP)', 'list-check', '/mop', 7, 1)
        ''')

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

def create_user(username, password_hash, auth_source='local'):
    """Create a new user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password_hash, auth_source)
            VALUES (?, ?, ?)
        ''', (username, password_hash, auth_source))

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
            (name, type, validation_template, delete_template, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            name,
            metadata.get('type', 'deploy'),
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
def create_stack_template(template_id, name, description, services, required_variables, api_variables, tags, created_by):
    """Create a new stack template"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO stack_templates
            (template_id, name, description, services, required_variables, api_variables, tags, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            template_id,
            name,
            description,
            json.dumps(services),
            json.dumps(required_variables),
            json.dumps(api_variables),
            json.dumps(tags),
            created_by
        ))
        return template_id

def update_stack_template(template_id, name, description, services, required_variables, api_variables, tags):
    """Update an existing stack template"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE stack_templates
            SET name = ?, description = ?, services = ?, required_variables = ?, api_variables = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
            WHERE template_id = ?
        ''', (
            name,
            description,
            json.dumps(services),
            json.dumps(required_variables),
            json.dumps(api_variables),
            json.dumps(tags),
            template_id
        ))
        return cursor.rowcount > 0

def save_stack_template(template_data):
    """Save a stack template (create or update)"""
    import uuid
    with get_db() as conn:
        cursor = conn.cursor()
        template_id = template_data.get('template_id') or str(uuid.uuid4())

        cursor.execute('''
            INSERT OR REPLACE INTO stack_templates
            (template_id, name, description, services, required_variables, api_variables, per_device_variables, tags, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            template_id,
            template_data['name'],
            template_data.get('description', ''),
            json.dumps(template_data['services']),
            json.dumps(template_data.get('required_variables', [])),
            json.dumps(template_data.get('api_variables', {})),
            json.dumps(template_data.get('per_device_variables', [])),
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
            template['api_variables'] = json.loads(template['api_variables']) if template.get('api_variables') else {}
            template['per_device_variables'] = json.loads(template['per_device_variables']) if template.get('per_device_variables') else []
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
            template['api_variables'] = json.loads(template['api_variables']) if template.get('api_variables') else {}
            template['per_device_variables'] = json.loads(template['per_device_variables']) if template.get('per_device_variables') else []
            template['tags'] = json.loads(template['tags']) if template['tags'] else []
            templates.append(template)
        return templates

def delete_stack_template(template_id):
    """Delete a stack template"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM stack_templates WHERE template_id = ?', (template_id,))
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

# ==================== Scheduled Stack Operations ====================

def create_scheduled_operation(schedule_id, stack_id, operation_type, schedule_type, scheduled_time,
                                day_of_week=None, day_of_month=None, created_by=None, config_data=None):
    """Create a new scheduled stack operation"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scheduled_stack_operations
            (schedule_id, stack_id, operation_type, schedule_type, scheduled_time,
             day_of_week, day_of_month, config_data, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (schedule_id, stack_id, operation_type, schedule_type, scheduled_time,
              day_of_week, day_of_month, config_data, created_by))
        return schedule_id

def get_scheduled_operations(stack_id=None):
    """Get scheduled operations, optionally filtered by stack_id"""
    with get_db() as conn:
        cursor = conn.cursor()
        if stack_id:
            cursor.execute('''
                SELECT * FROM scheduled_stack_operations
                WHERE stack_id = ?
                ORDER BY next_run ASC
            ''', (stack_id,))
        else:
            cursor.execute('''
                SELECT * FROM scheduled_stack_operations
                ORDER BY next_run ASC
            ''')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_scheduled_operation(schedule_id):
    """Get a specific scheduled operation"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM scheduled_stack_operations WHERE schedule_id = ?', (schedule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_scheduled_operation(schedule_id, **kwargs):
    """Update a scheduled operation"""
    with get_db() as conn:
        cursor = conn.cursor()
        allowed_fields = ['operation_type', 'schedule_type', 'scheduled_time', 'day_of_week',
                         'day_of_month', 'enabled', 'last_run', 'next_run', 'run_count']

        updates = []
        values = []
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f'{field} = ?')
                values.append(value)

        if updates:
            values.append(schedule_id)
            cursor.execute(f'''
                UPDATE scheduled_stack_operations
                SET {', '.join(updates)}
                WHERE schedule_id = ?
            ''', values)
            return cursor.rowcount > 0
        return False

def delete_scheduled_operation(schedule_id):
    """Delete a scheduled operation"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM scheduled_stack_operations WHERE schedule_id = ?', (schedule_id,))
        return cursor.rowcount > 0

def get_pending_scheduled_operations():
    """Get all enabled scheduled operations that are due to run"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Note: next_run is stored in ISO format (YYYY-MM-DDTHH:MM:SS)
        # We need to convert it for SQLite comparison by:
        # 1. Replacing 'T' with space
        # 2. Removing timezone suffix if present
        # 3. Removing milliseconds if present
        # Use localtime instead of UTC for comparison
        cursor.execute('''
            SELECT * FROM scheduled_stack_operations
            WHERE enabled = 1
            AND (next_run IS NULL OR
                 REPLACE(SUBSTR(next_run, 1, 19), 'T', ' ') <= datetime('now', 'localtime'))
            ORDER BY next_run ASC
        ''')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

# API Resource operations
def create_api_resource(resource_id, name, description, base_url, auth_type, auth_token, auth_username, auth_password, custom_headers, created_by):
    """Create a new API resource"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO api_resources
            (resource_id, name, description, base_url, auth_type, auth_token, auth_username, auth_password, custom_headers, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            resource_id,
            name,
            description,
            base_url,
            auth_type,
            auth_token,
            auth_username,
            auth_password,
            json.dumps(custom_headers) if custom_headers else None,
            created_by
        ))
        return resource_id

def update_api_resource(resource_id, name, description, base_url, auth_type, auth_token, auth_username, auth_password, custom_headers):
    """Update an existing API resource"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE api_resources
            SET name = ?, description = ?, base_url = ?, auth_type = ?, auth_token = ?,
                auth_username = ?, auth_password = ?, custom_headers = ?, updated_at = CURRENT_TIMESTAMP
            WHERE resource_id = ?
        ''', (
            name,
            description,
            base_url,
            auth_type,
            auth_token,
            auth_username,
            auth_password,
            json.dumps(custom_headers) if custom_headers else None,
            resource_id
        ))
        return cursor.rowcount > 0

def get_api_resource(resource_id):
    """Get a specific API resource"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM api_resources WHERE resource_id = ?', (resource_id,))
        row = cursor.fetchone()
        if row:
            resource = dict(row)
            if resource.get('custom_headers'):
                resource['custom_headers'] = json.loads(resource['custom_headers'])
            return resource
        return None

def get_all_api_resources():
    """Get all API resources"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM api_resources ORDER BY name')
        resources = []
        for row in cursor.fetchall():
            resource = dict(row)
            if resource.get('custom_headers'):
                resource['custom_headers'] = json.loads(resource['custom_headers'])
            resources.append(resource)
        return resources

def delete_api_resource(resource_id):
    """Delete an API resource"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM api_resources WHERE resource_id = ?', (resource_id,))
        return cursor.rowcount > 0


# ============================================================================
# Menu Items Functions
# ============================================================================

def get_menu_items():
    """Get all menu items ordered by order_index"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT item_id, label, icon, url, order_index, visible
            FROM menu_items
            ORDER BY order_index ASC
        ''')
        return [dict(row) for row in cursor.fetchall()]


def update_menu_order(menu_items):
    """Update menu items order"""
    with get_db() as conn:
        cursor = conn.cursor()
        for item in menu_items:
            cursor.execute('''
                UPDATE menu_items
                SET order_index = ?, visible = ?, updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
            ''', (item['order_index'], item.get('visible', 1), item['item_id']))
        conn.commit()
        return True


def update_menu_item(item_id, label=None, icon=None, visible=None):
    """Update a menu item"""
    with get_db() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if label is not None:
            updates.append('label = ?')
            params.append(label)
        if icon is not None:
            updates.append('icon = ?')
            params.append(icon)
        if visible is not None:
            updates.append('visible = ?')
            params.append(visible)

        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            params.append(item_id)
            cursor.execute(f'''
                UPDATE menu_items
                SET {', '.join(updates)}
                WHERE item_id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
        return False


# =============================================================================
# MOP (Method of Procedures) Functions
# =============================================================================

def create_mop(mop_id, name, description="", devices=None):
    """Create a new MOP"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mops (mop_id, name, description, devices)
            VALUES (?, ?, ?, ?)
        ''', (mop_id, name, description, json.dumps(devices) if devices else None))
        conn.commit()
        return cursor.rowcount > 0

def get_all_mops():
    """Get all MOPs"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT mop_id, name, description, devices, created_at, updated_at
            FROM mops
            ORDER BY updated_at DESC
        ''')
        mops = []
        for row in cursor.fetchall():
            mop = dict(row)
            if mop.get('devices'):
                mop['devices'] = json.loads(mop['devices'])
            else:
                mop['devices'] = []
            mops.append(mop)
        return mops

def get_mop(mop_id):
    """Get a specific MOP by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT mop_id, name, description, devices, created_at, updated_at
            FROM mops
            WHERE mop_id = ?
        ''', (mop_id,))
        row = cursor.fetchone()
        if row:
            mop = dict(row)
            if mop.get('devices'):
                mop['devices'] = json.loads(mop['devices'])
            else:
                mop['devices'] = []
            return mop
        return None

def update_mop(mop_id, name=None, description=None, devices=None):
    """Update a MOP"""
    with get_db() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if name is not None:
            updates.append('name = ?')
            params.append(name)
        if description is not None:
            updates.append('description = ?')
            params.append(description)
        if devices is not None:
            updates.append('devices = ?')
            params.append(json.dumps(devices))

        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            params.append(mop_id)
            cursor.execute(f'''
                UPDATE mops
                SET {', '.join(updates)}
                WHERE mop_id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
        return False

def delete_mop(mop_id):
    """Delete a MOP and its steps"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM mops WHERE mop_id = ?', (mop_id,))
        conn.commit()
        return cursor.rowcount > 0

# MOP Steps Functions

def create_mop_step(step_id, mop_id, step_order, step_type, step_name, devices, config, enabled=1):
    """Create a new MOP step"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mop_steps (step_id, mop_id, step_order, step_type, step_name, devices, config, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (step_id, mop_id, step_order, step_type, step_name, json.dumps(devices), json.dumps(config), enabled))
        conn.commit()
        return cursor.rowcount > 0

def get_mop_steps(mop_id):
    """Get all steps for a MOP"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT step_id, mop_id, step_order, step_type, step_name, devices, config, enabled
            FROM mop_steps
            WHERE mop_id = ?
            ORDER BY step_order ASC
        ''', (mop_id,))
        steps = []
        for row in cursor.fetchall():
            step = dict(row)
            step['devices'] = json.loads(step['devices']) if step['devices'] else []
            step['config'] = json.loads(step['config']) if step['config'] else {}
            steps.append(step)
        return steps

def get_mop_step(step_id):
    """Get a specific step by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT step_id, mop_id, step_order, step_type, step_name, devices, config, enabled
            FROM mop_steps
            WHERE step_id = ?
        ''', (step_id,))
        row = cursor.fetchone()
        if row:
            step = dict(row)
            step['devices'] = json.loads(step['devices']) if step['devices'] else []
            step['config'] = json.loads(step['config']) if step['config'] else {}
            return step
        return None

def update_mop_step(step_id, step_order=None, step_type=None, step_name=None, devices=None, config=None, enabled=None):
    """Update a MOP step"""
    with get_db() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if step_order is not None:
            updates.append('step_order = ?')
            params.append(step_order)
        if step_type is not None:
            updates.append('step_type = ?')
            params.append(step_type)
        if step_name is not None:
            updates.append('step_name = ?')
            params.append(step_name)
        if devices is not None:
            updates.append('devices = ?')
            params.append(json.dumps(devices))
        if config is not None:
            updates.append('config = ?')
            params.append(json.dumps(config))
        if enabled is not None:
            updates.append('enabled = ?')
            params.append(enabled)

        if updates:
            params.append(step_id)
            cursor.execute(f'''
                UPDATE mop_steps
                SET {', '.join(updates)}
                WHERE step_id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
        return False

def delete_mop_step(step_id):
    """Delete a MOP step"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM mop_steps WHERE step_id = ?', (step_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_all_mop_steps(mop_id):
    """Delete all steps for a MOP"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM mop_steps WHERE mop_id = ?', (mop_id,))
        conn.commit()
        return cursor.rowcount

# MOP Execution Functions

def create_mop_execution(execution_id, mop_id):
    """Create a new MOP execution record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mop_executions (execution_id, mop_id, status, started_at, results)
            VALUES (?, ?, 'running', CURRENT_TIMESTAMP, '[]')
        ''', (execution_id, mop_id))
        conn.commit()
        return cursor.rowcount > 0

def get_mop_execution(execution_id):
    """Get a specific execution by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT execution_id, mop_id, status, current_step, results, context, error, started_at, completed_at
            FROM mop_executions
            WHERE execution_id = ?
        ''', (execution_id,))
        row = cursor.fetchone()
        if row:
            execution = dict(row)
            execution['results'] = json.loads(execution['results']) if execution['results'] else []
            execution['context'] = json.loads(execution['context']) if execution['context'] else {}
            return execution
        return None

def get_mop_executions(mop_id, limit=10):
    """Get execution history for a MOP"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT execution_id, mop_id, status, current_step, results, context, error, started_at, completed_at
            FROM mop_executions
            WHERE mop_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        ''', (mop_id, limit))
        executions = []
        for row in cursor.fetchall():
            execution = dict(row)
            execution['results'] = json.loads(execution['results']) if execution['results'] else []
            execution['context'] = json.loads(execution['context']) if execution['context'] else {}
            executions.append(execution)
        return executions

def update_mop_execution(execution_id, status=None, current_step=None, results=None, context=None, error=None):
    """Update a MOP execution"""
    with get_db() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if status is not None:
            updates.append('status = ?')
            params.append(status)
            if status in ['completed', 'failed']:
                updates.append('completed_at = CURRENT_TIMESTAMP')
        if current_step is not None:
            updates.append('current_step = ?')
            params.append(current_step)
        if results is not None:
            updates.append('results = ?')
            params.append(json.dumps(results))
        if context is not None:
            updates.append('context = ?')
            params.append(json.dumps(context))
        if error is not None:
            updates.append('error = ?')
            params.append(error)

        if updates:
            params.append(execution_id)
            cursor.execute(f'''
                UPDATE mop_executions
                SET {', '.join(updates)}
                WHERE execution_id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
        return False


