#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for NetStacks

This script:
1. Connects to the existing SQLite database
2. Initializes the PostgreSQL schema
3. Migrates all data from SQLite to PostgreSQL

Usage:
    python migrate_to_postgres.py [--dry-run]

Environment variables:
    DATABASE_URL: PostgreSQL connection string
    DB_FILE: Path to SQLite database file
"""
import os
import sys
import json
import sqlite3
import argparse
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Import SQLAlchemy models
try:
    from models import (
        Base, get_engine, get_session, init_postgres_db, seed_defaults,
        Setting, User, Template, ServiceStack, ServiceInstance, Device,
        DefaultCredential, StackTemplate, APIResource, ScheduledStackOperation,
        AuthConfig, MenuItem, MOP, MOPExecution, StepType, TaskHistory
    )
except ImportError as e:
    log.error(f"Failed to import models: {e}")
    log.error("Make sure models.py is in the same directory")
    sys.exit(1)

# Configuration
SQLITE_DB = os.environ.get('DB_FILE', '/data/netstacks.db')
POSTGRES_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://netstacks:netstacks_secret_change_me@localhost:5432/netstacks'
)


def get_sqlite_connection():
    """Connect to SQLite database"""
    if not os.path.exists(SQLITE_DB):
        log.error(f"SQLite database not found: {SQLITE_DB}")
        return None

    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def parse_json_field(value):
    """Safely parse JSON field, returning default if invalid"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def migrate_settings(sqlite_conn, pg_session, dry_run=False):
    """Migrate settings table"""
    log.info("Migrating settings...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT key, value, updated_at FROM settings")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            setting = Setting(
                key=row['key'],
                value=row['value'],
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(setting)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} settings")
    return count


def migrate_users(sqlite_conn, pg_session, dry_run=False):
    """Migrate users table"""
    log.info("Migrating users...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT username, password_hash, theme, auth_source, created_at FROM users")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            user = User(
                username=row['username'],
                password_hash=row['password_hash'],
                theme=row['theme'] or 'dark',
                auth_source=row['auth_source'] or 'local',
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
            )
            pg_session.merge(user)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} users")
    return count


def migrate_templates(sqlite_conn, pg_session, dry_run=False):
    """Migrate templates metadata table"""
    log.info("Migrating templates...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM templates")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            template = Template(
                name=row['name'],
                type=row['type'] or 'deploy',
                validation_template=row['validation_template'],
                delete_template=row['delete_template'],
                description=row['description'],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(template)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} templates")
    return count


def migrate_service_stacks(sqlite_conn, pg_session, dry_run=False):
    """Migrate service_stacks table"""
    log.info("Migrating service stacks...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM service_stacks")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            stack = ServiceStack(
                stack_id=row['stack_id'],
                name=row['name'],
                description=row['description'],
                services=parse_json_field(row['services']) or [],
                shared_variables=parse_json_field(row['shared_variables']) or {},
                state=row['state'] or 'pending',
                has_pending_changes=bool(row['has_pending_changes']),
                pending_since=datetime.fromisoformat(row['pending_since']) if row['pending_since'] else None,
                deployed_services=parse_json_field(row['deployed_services']) or [],
                deployment_errors=parse_json_field(row['deployment_errors']) or [],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                deploy_started_at=datetime.fromisoformat(row['deploy_started_at']) if row['deploy_started_at'] else None,
                deploy_completed_at=datetime.fromisoformat(row['deploy_completed_at']) if row['deploy_completed_at'] else None,
                last_validated=datetime.fromisoformat(row['last_validated']) if row['last_validated'] else None,
                validation_status=row['validation_status']
            )
            pg_session.merge(stack)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} service stacks")
    return count


def migrate_service_instances(sqlite_conn, pg_session, dry_run=False):
    """Migrate service_instances table"""
    log.info("Migrating service instances...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM service_instances")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            instance = ServiceInstance(
                service_id=row['service_id'],
                name=row['name'],
                template=row['template'],
                validation_template=row['validation_template'],
                delete_template=row['delete_template'],
                device=row['device'],
                variables=parse_json_field(row['variables']) or {},
                rendered_config=row['rendered_config'],
                state=row['state'] or 'pending',
                error=row['error'],
                task_id=row['task_id'],
                stack_id=row['stack_id'],
                stack_order=row['stack_order'] or 0,
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                deployed_at=datetime.fromisoformat(row['deployed_at']) if row['deployed_at'] else None,
                last_validated=datetime.fromisoformat(row['last_validated']) if row['last_validated'] else None,
                validation_status=row['validation_status'],
                validation_errors=parse_json_field(row['validation_errors']) or []
            )
            pg_session.merge(instance)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} service instances")
    return count


def migrate_manual_devices(sqlite_conn, pg_session, dry_run=False):
    """Migrate manual_devices to unified devices table"""
    log.info("Migrating manual devices...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM manual_devices")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            device = Device(
                name=row['device_name'],
                host=row['host'],
                device_type=row['device_type'],
                port=row['port'] or 22,
                username=row['username'],
                password=row['password'],
                enable_password=row['enable_password'],
                description=row['description'],
                manufacturer=row['manufacturer'],
                model=row['model'],
                site=row['site'],
                tags=parse_json_field(row['tags']) or [],
                source='manual',
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(device)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} manual devices")
    return count


def migrate_stack_templates(sqlite_conn, pg_session, dry_run=False):
    """Migrate stack_templates table"""
    log.info("Migrating stack templates...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM stack_templates")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            template = StackTemplate(
                template_id=row['template_id'],
                name=row['name'],
                description=row['description'],
                services=parse_json_field(row['services']) or [],
                required_variables=parse_json_field(row['required_variables']) or [],
                api_variables=parse_json_field(row['api_variables']) or {},
                per_device_variables=parse_json_field(row.get('per_device_variables')) or [],
                tags=parse_json_field(row['tags']) or [],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                created_by=row['created_by']
            )
            pg_session.merge(template)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} stack templates")
    return count


def migrate_api_resources(sqlite_conn, pg_session, dry_run=False):
    """Migrate api_resources table"""
    log.info("Migrating API resources...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM api_resources")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            resource = APIResource(
                resource_id=row['resource_id'],
                name=row['name'],
                description=row['description'],
                base_url=row['base_url'],
                auth_type=row['auth_type'],
                auth_token=row['auth_token'],
                auth_username=row['auth_username'],
                auth_password=row['auth_password'],
                custom_headers=parse_json_field(row['custom_headers']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                created_by=row['created_by']
            )
            pg_session.merge(resource)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} API resources")
    return count


def migrate_scheduled_operations(sqlite_conn, pg_session, dry_run=False):
    """Migrate scheduled_stack_operations table"""
    log.info("Migrating scheduled operations...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM scheduled_stack_operations")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            operation = ScheduledStackOperation(
                schedule_id=row['schedule_id'],
                stack_id=row['stack_id'],
                operation_type=row['operation_type'],
                schedule_type=row['schedule_type'],
                scheduled_time=row['scheduled_time'],
                day_of_week=row['day_of_week'],
                day_of_month=row['day_of_month'],
                config_data=parse_json_field(row.get('config_data')),
                enabled=bool(row['enabled']),
                last_run=datetime.fromisoformat(row['last_run']) if row['last_run'] else None,
                next_run=datetime.fromisoformat(row['next_run']) if row['next_run'] else None,
                run_count=row['run_count'] or 0,
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                created_by=row['created_by']
            )
            pg_session.merge(operation)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} scheduled operations")
    return count


def migrate_auth_config(sqlite_conn, pg_session, dry_run=False):
    """Migrate auth_config table"""
    log.info("Migrating auth configurations...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM auth_config")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            config = AuthConfig(
                config_id=row['config_id'],
                auth_type=row['auth_type'],
                is_enabled=bool(row['is_enabled']),
                priority=row['priority'] or 0,
                config_data=parse_json_field(row['config_data']) or {},
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(config)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} auth configurations")
    return count


def migrate_menu_items(sqlite_conn, pg_session, dry_run=False):
    """Migrate menu_items table"""
    log.info("Migrating menu items...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM menu_items")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            item = MenuItem(
                item_id=row['item_id'],
                label=row['label'],
                icon=row['icon'],
                url=row['url'],
                order_index=row['order_index'],
                visible=bool(row['visible']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(item)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} menu items")
    return count


def migrate_mops(sqlite_conn, pg_session, dry_run=False):
    """Migrate mops table"""
    log.info("Migrating MOPs...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM mops")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            mop = MOP(
                mop_id=row['mop_id'],
                name=row['name'],
                description=row['description'],
                yaml_content=row['yaml_content'],
                devices=parse_json_field(row['devices']) or [],
                enabled=bool(row['enabled']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                created_by=row['created_by']
            )
            pg_session.merge(mop)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} MOPs")
    return count


def migrate_mop_executions(sqlite_conn, pg_session, dry_run=False):
    """Migrate mop_executions table"""
    log.info("Migrating MOP executions...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM mop_executions")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            execution = MOPExecution(
                execution_id=row['execution_id'],
                mop_id=row['mop_id'],
                status=row['status'] or 'pending',
                current_step=row['current_step'] or 0,
                execution_log=parse_json_field(row['execution_log']) or [],
                context=parse_json_field(row['context']) or {},
                error=row['error'],
                started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                started_by=row['started_by']
            )
            pg_session.merge(execution)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} MOP executions")
    return count


def migrate_step_types(sqlite_conn, pg_session, dry_run=False):
    """Migrate step_types table"""
    log.info("Migrating step types...")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM step_types")
    rows = cursor.fetchall()

    count = 0
    for row in rows:
        if not dry_run:
            step_type = StepType(
                step_type_id=row['step_type_id'],
                name=row['name'],
                description=row['description'],
                category=row['category'],
                parameters_schema=parse_json_field(row['parameters_schema']) or {},
                handler_function=row['handler_function'],
                icon=row['icon'],
                enabled=bool(row['enabled']),
                is_custom=bool(row['is_custom']),
                custom_type=row['custom_type'],
                custom_code=row['custom_code'],
                custom_webhook_url=row['custom_webhook_url'],
                custom_webhook_method=row['custom_webhook_method'] or 'POST',
                custom_webhook_headers=parse_json_field(row['custom_webhook_headers']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
            )
            pg_session.merge(step_type)
        count += 1

    log.info(f"  {'Would migrate' if dry_run else 'Migrated'} {count} step types")
    return count


def run_migration(dry_run=False):
    """Run the full migration"""
    log.info("=" * 60)
    log.info("NetStacks SQLite to PostgreSQL Migration")
    log.info("=" * 60)

    if dry_run:
        log.info("DRY RUN MODE - No changes will be made")

    log.info(f"SQLite source: {SQLITE_DB}")
    log.info(f"PostgreSQL target: {POSTGRES_URL.split('@')[1] if '@' in POSTGRES_URL else POSTGRES_URL}")
    log.info("")

    # Connect to SQLite
    sqlite_conn = get_sqlite_connection()
    if sqlite_conn is None:
        return False

    # Connect to PostgreSQL and create tables
    log.info("Initializing PostgreSQL schema...")
    try:
        engine = get_engine(POSTGRES_URL)
        if not dry_run:
            init_postgres_db(engine)
        pg_session = get_session(engine)
        log.info("  PostgreSQL connected and schema created")
    except Exception as e:
        log.error(f"Failed to connect to PostgreSQL: {e}")
        return False

    log.info("")
    log.info("Starting data migration...")
    log.info("-" * 40)

    total_count = 0

    try:
        # Migrate all tables
        total_count += migrate_settings(sqlite_conn, pg_session, dry_run)
        total_count += migrate_users(sqlite_conn, pg_session, dry_run)
        total_count += migrate_templates(sqlite_conn, pg_session, dry_run)
        total_count += migrate_service_stacks(sqlite_conn, pg_session, dry_run)
        total_count += migrate_service_instances(sqlite_conn, pg_session, dry_run)
        total_count += migrate_manual_devices(sqlite_conn, pg_session, dry_run)
        total_count += migrate_stack_templates(sqlite_conn, pg_session, dry_run)
        total_count += migrate_api_resources(sqlite_conn, pg_session, dry_run)
        total_count += migrate_scheduled_operations(sqlite_conn, pg_session, dry_run)
        total_count += migrate_auth_config(sqlite_conn, pg_session, dry_run)
        total_count += migrate_menu_items(sqlite_conn, pg_session, dry_run)
        total_count += migrate_mops(sqlite_conn, pg_session, dry_run)
        total_count += migrate_mop_executions(sqlite_conn, pg_session, dry_run)
        total_count += migrate_step_types(sqlite_conn, pg_session, dry_run)

        if not dry_run:
            pg_session.commit()
            log.info("")
            log.info("-" * 40)
            log.info(f"Migration complete! Total records migrated: {total_count}")
        else:
            log.info("")
            log.info("-" * 40)
            log.info(f"Dry run complete. Would migrate {total_count} records.")

        return True

    except Exception as e:
        log.error(f"Migration failed: {e}")
        if not dry_run:
            pg_session.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_session.close()


def main():
    global SQLITE_DB, POSTGRES_URL

    parser = argparse.ArgumentParser(
        description='Migrate NetStacks data from SQLite to PostgreSQL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without making changes'
    )
    parser.add_argument(
        '--sqlite-db',
        default=SQLITE_DB,
        help=f'Path to SQLite database (default: {SQLITE_DB})'
    )
    parser.add_argument(
        '--postgres-url',
        default=POSTGRES_URL,
        help='PostgreSQL connection URL'
    )

    args = parser.parse_args()

    # Update globals from args
    SQLITE_DB = args.sqlite_db
    POSTGRES_URL = args.postgres_url

    success = run_migration(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
