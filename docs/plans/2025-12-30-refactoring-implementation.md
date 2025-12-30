# NetStacks Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the database_postgres bug, split tasks.py into a proper package, and slim down app.py by extracting business logic.

**Architecture:** Two task systems exist: `/tasks.py` (used by Flask app) and `/workers/tasks/` (used by Celery workers). We'll fix the bug in tasks.py, then create a proper `tasks/` package to replace the monolithic file while maintaining backward compatibility.

**Tech Stack:** Python, Flask, Celery, SQLAlchemy, PostgreSQL

---

## Task 1: Fix database_postgres Import Bug

**Files:**
- Modify: `/home/cwdavis/netstacks/tasks.py` (lines 916, 964, 1070, 1123, 1175)

**Step 1: Fix all database_postgres imports**

Replace 5 instances of `import database_postgres as db` with `import database as db`:

```bash
sed -i 's/import database_postgres as db/import database as db/g' /home/cwdavis/netstacks/tasks.py
```

**Step 2: Verify the fix**

```bash
grep -n "database_postgres" /home/cwdavis/netstacks/tasks.py
# Expected: No matches found
```

**Step 3: Syntax check**

```bash
cd /home/cwdavis/netstacks && python3 -m py_compile tasks.py
# Expected: No output (success)
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks.py
git commit -m "fix: replace non-existent database_postgres with database module

The scheduled tasks were importing database_postgres which doesn't exist.
This would cause ImportError when scheduled tasks executed."
```

---

## Task 2: Create tasks/ Package Structure

**Files:**
- Create: `/home/cwdavis/netstacks/tasks/__init__.py`
- Create: `/home/cwdavis/netstacks/tasks/celery_config.py`
- Create: `/home/cwdavis/netstacks/tasks/utils.py`

**Step 1: Create tasks directory**

```bash
mkdir -p /home/cwdavis/netstacks/tasks
```

**Step 2: Create celery_config.py**

Extract Celery app initialization (lines 1-105 from tasks.py):

```python
# /home/cwdavis/netstacks/tasks/celery_config.py
"""
Celery Configuration for NetStacks
Celery app initialization and configuration
"""
import os
import logging
from typing import Dict, Optional
from celery import Celery
import redis

log = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

# Redis client for task metadata
_redis_client = None


def get_redis_client():
    """Get Redis client for task metadata"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(CELERY_RESULT_BACKEND, decode_responses=True)
        except Exception as e:
            log.warning(f"Could not connect to Redis: {e}")
            return None
    return _redis_client


def store_task_metadata(task_id: str, metadata: Dict):
    """Store task metadata in Redis"""
    client = get_redis_client()
    if client:
        try:
            import json
            key = f"task_meta:{task_id}"
            client.setex(key, 3600, json.dumps(metadata))  # 1 hour expiry
        except Exception as e:
            log.debug(f"Could not store task metadata: {e}")


def get_task_metadata(task_id: str) -> Optional[Dict]:
    """Get task metadata from Redis"""
    client = get_redis_client()
    if client:
        try:
            import json
            key = f"task_meta:{task_id}"
            data = client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            log.debug(f"Could not get task metadata: {e}")
    return None


# Create Celery app
celery_app = Celery(
    'netstacks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,  # Results expire after 1 hour
)

# Task routing configuration
celery_app.conf.task_routes = {
    'tasks.device_tasks.get_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.set_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.run_commands': {'queue': 'device_tasks'},
    'tasks.device_tasks.validate_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.test_connectivity': {'queue': 'device_tasks'},
    'tasks.backup_tasks.backup_device_config': {'queue': 'device_tasks'},
    'tasks.backup_tasks.validate_config_from_backup': {'queue': 'celery'},
    'tasks.backup_tasks.create_snapshot': {'queue': 'celery'},
    'tasks.backup_tasks.cleanup_old_backups': {'queue': 'celery'},
    'tasks.scheduled_tasks.*': {'queue': 'celery'},
}

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'check-scheduled-operations': {
        'task': 'tasks.scheduled_tasks.check_scheduled_operations',
        'schedule': 60.0,  # Every minute
    },
}
```

**Step 3: Create utils.py**

Extract utility functions (TextFSM, TTP, Jinja2 helpers):

```python
# /home/cwdavis/netstacks/tasks/utils.py
"""
Task Utilities for NetStacks
Parsing helpers (TextFSM, TTP, Jinja2)
"""
import os
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)


def get_textfsm_template_path(device_type: str, command: str) -> Optional[str]:
    """
    Find TextFSM template for a given device type and command.
    """
    try:
        from ntc_templates.parse import _get_template_dir
        template_dir = _get_template_dir()

        # Normalize command for template lookup
        command_normalized = command.strip().lower().replace(' ', '_')
        template_name = f"{device_type}_{command_normalized}.textfsm"
        template_path = os.path.join(template_dir, template_name)

        if os.path.exists(template_path):
            return template_path
    except ImportError:
        log.debug("ntc_templates not installed")
    except Exception as e:
        log.debug(f"Error finding TextFSM template: {e}")

    return None


def parse_with_textfsm(output: str, device_type: str, command: str) -> Optional[List[Dict]]:
    """
    Parse command output using TextFSM templates.
    """
    try:
        from ntc_templates.parse import parse_output
        return parse_output(platform=device_type, command=command, data=output)
    except ImportError:
        log.debug("ntc_templates not installed")
    except Exception as e:
        log.debug(f"TextFSM parsing failed: {e}")
    return None


def parse_with_ttp(output: str, template: str) -> Optional[List[Dict]]:
    """
    Parse command output using TTP template.
    """
    try:
        from ttp import ttp
        parser = ttp(data=output, template=template)
        parser.parse()
        return parser.result()
    except ImportError:
        log.debug("TTP not installed")
    except Exception as e:
        log.debug(f"TTP parsing failed: {e}")
    return None


def render_jinja2_template(template_str: str, variables: Dict) -> str:
    """
    Render a Jinja2 template string with variables.
    """
    from jinja2 import Template, Environment, BaseLoader
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(**variables)


def get_device_queue(device_name: str) -> str:
    """
    Get the queue name for a specific device.
    Used for device-level serial execution.
    """
    return f"device:{device_name}"
```

**Step 4: Create __init__.py with re-exports**

```python
# /home/cwdavis/netstacks/tasks/__init__.py
"""
NetStacks Tasks Package
Exports celery_app and utility functions for backward compatibility.
"""

from .celery_config import (
    celery_app,
    get_redis_client,
    store_task_metadata,
    get_task_metadata,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
)

from .utils import (
    get_textfsm_template_path,
    parse_with_textfsm,
    parse_with_ttp,
    render_jinja2_template,
    get_device_queue,
)

__all__ = [
    'celery_app',
    'get_redis_client',
    'store_task_metadata',
    'get_task_metadata',
    'CELERY_BROKER_URL',
    'CELERY_RESULT_BACKEND',
    'get_textfsm_template_path',
    'parse_with_textfsm',
    'parse_with_ttp',
    'render_jinja2_template',
    'get_device_queue',
]
```

**Step 5: Verify package imports work**

```bash
cd /home/cwdavis/netstacks
python3 -c "from tasks import celery_app, get_task_metadata; print('OK')"
# Expected: OK
```

**Step 6: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks/
git commit -m "refactor: create tasks/ package with celery_config and utils

Split out core Celery configuration and utility functions into a proper
Python package structure. Maintains backward compatibility via __init__.py
re-exports."
```

---

## Task 3: Create Device Tasks Module

**Files:**
- Create: `/home/cwdavis/netstacks/tasks/device_tasks.py`

**Step 1: Create device_tasks.py**

Extract device operation tasks from tasks.py (get_config, set_config, run_commands, validate_config, test_connectivity):

```python
# /home/cwdavis/netstacks/tasks/device_tasks.py
"""
Device Tasks for NetStacks
Network device operations using Netmiko
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from .celery_config import celery_app, store_task_metadata
from .utils import parse_with_textfsm, get_device_queue
from timezone_utils import utc_now

log = logging.getLogger(__name__)


@celery_app.task(bind=True, name='tasks.device_tasks.get_config')
def get_config(self, connection_args: Dict, commands: List[str],
               parse_output: bool = False, device_name: str = None) -> Dict:
    """
    Execute show commands on a network device.

    Args:
        connection_args: Netmiko connection parameters
        commands: List of commands to execute
        parse_output: Whether to parse output with TextFSM
        device_name: Optional device name for metadata

    Returns:
        Dict with command outputs and metadata
    """
    task_id = self.request.id
    device_type = connection_args.get('device_type', 'unknown')

    # Store task metadata
    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'get_config',
            'commands': commands,
            'started_at': utc_now().isoformat()
        })

    results = {}
    errors = []

    try:
        log.info(f"Task {task_id}: Connecting to {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            for command in commands:
                try:
                    output = conn.send_command(command, read_timeout=60)
                    result = {'output': output, 'success': True}

                    # Parse output if requested
                    if parse_output:
                        parsed = parse_with_textfsm(output, device_type, command)
                        if parsed:
                            result['parsed'] = parsed

                    results[command] = result

                except Exception as e:
                    log.error(f"Command '{command}' failed: {e}")
                    results[command] = {'output': str(e), 'success': False}
                    errors.append(f"Command '{command}': {str(e)}")

        return {
            'status': 'success' if not errors else 'partial',
            'results': results,
            'errors': errors,
            'device': device_name or connection_args.get('host'),
            'completed_at': utc_now().isoformat()
        }

    except NetmikoTimeoutException as e:
        log.error(f"Connection timeout: {e}")
        return {
            'status': 'error',
            'error': f"Connection timeout: {str(e)}",
            'device': device_name or connection_args.get('host')
        }
    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed: {e}")
        return {
            'status': 'error',
            'error': f"Authentication failed: {str(e)}",
            'device': device_name or connection_args.get('host')
        }
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e),
            'device': device_name or connection_args.get('host')
        }


@celery_app.task(bind=True, name='tasks.device_tasks.set_config')
def set_config(self, connection_args: Dict, config_commands: List[str],
               device_name: str = None, dry_run: bool = False) -> Dict:
    """
    Push configuration commands to a network device.

    Args:
        connection_args: Netmiko connection parameters
        config_commands: List of configuration commands
        device_name: Optional device name for metadata
        dry_run: If True, only validate without applying

    Returns:
        Dict with result status and output
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'set_config',
            'dry_run': dry_run,
            'started_at': utc_now().isoformat()
        })

    try:
        log.info(f"Task {task_id}: Connecting to {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            if dry_run:
                # For dry run, just return the commands that would be sent
                return {
                    'status': 'dry_run',
                    'commands': config_commands,
                    'device': device_name or connection_args.get('host'),
                    'message': 'Dry run - commands not applied'
                }

            # Apply configuration
            output = conn.send_config_set(config_commands)

            # Save configuration if supported
            try:
                save_output = conn.save_config()
                output += f"\n{save_output}"
            except Exception as e:
                log.warning(f"Could not save config: {e}")
                output += f"\nWarning: Could not save config: {e}"

            return {
                'status': 'success',
                'output': output,
                'device': device_name or connection_args.get('host'),
                'completed_at': utc_now().isoformat()
            }

    except NetmikoTimeoutException as e:
        return {'status': 'error', 'error': f"Connection timeout: {str(e)}"}
    except NetmikoAuthenticationException as e:
        return {'status': 'error', 'error': f"Authentication failed: {str(e)}"}
    except Exception as e:
        log.error(f"Error in set_config: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.run_commands')
def run_commands(self, connection_args: Dict, commands: List[str],
                 device_name: str = None) -> Dict:
    """
    Execute arbitrary commands on a network device.
    Similar to get_config but without parsing.
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'run_commands',
            'started_at': utc_now().isoformat()
        })

    results = {}

    try:
        with ConnectHandler(**connection_args) as conn:
            for command in commands:
                try:
                    output = conn.send_command(command, read_timeout=60)
                    results[command] = {'output': output, 'success': True}
                except Exception as e:
                    results[command] = {'output': str(e), 'success': False}

        return {
            'status': 'success',
            'results': results,
            'device': device_name or connection_args.get('host')
        }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.validate_config')
def validate_config(self, connection_args: Dict, patterns: List[str],
                    device_name: str = None) -> Dict:
    """
    Validate that specific patterns exist in device configuration.
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'validate_config',
            'started_at': utc_now().isoformat()
        })

    try:
        import re

        with ConnectHandler(**connection_args) as conn:
            # Get running config
            config = conn.send_command('show running-config', read_timeout=120)

            results = {}
            all_found = True

            for pattern in patterns:
                match = re.search(pattern, config, re.MULTILINE)
                results[pattern] = {
                    'found': bool(match),
                    'match': match.group(0) if match else None
                }
                if not match:
                    all_found = False

            return {
                'status': 'success',
                'all_patterns_found': all_found,
                'results': results,
                'device': device_name or connection_args.get('host')
            }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.test_connectivity')
def test_connectivity(self, connection_args: Dict, device_name: str = None) -> Dict:
    """
    Test connectivity to a network device.
    """
    task_id = self.request.id

    try:
        with ConnectHandler(**connection_args) as conn:
            # Try a simple command
            prompt = conn.find_prompt()
            return {
                'status': 'success',
                'reachable': True,
                'prompt': prompt,
                'device': device_name or connection_args.get('host')
            }

    except NetmikoTimeoutException:
        return {'status': 'error', 'reachable': False, 'error': 'Connection timeout'}
    except NetmikoAuthenticationException:
        return {'status': 'error', 'reachable': False, 'error': 'Authentication failed'}
    except Exception as e:
        return {'status': 'error', 'reachable': False, 'error': str(e)}
```

**Step 2: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile tasks/device_tasks.py
```

**Step 3: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks/device_tasks.py
git commit -m "refactor: extract device tasks to tasks/device_tasks.py

Move get_config, set_config, run_commands, validate_config, and
test_connectivity tasks to dedicated module."
```

---

## Task 4: Create Backup Tasks Module

**Files:**
- Create: `/home/cwdavis/netstacks/tasks/backup_tasks.py`

**Step 1: Create backup_tasks.py**

Extract backup-related tasks from tasks.py:

```python
# /home/cwdavis/netstacks/tasks/backup_tasks.py
"""
Backup Tasks for NetStacks
Device configuration backup and snapshot management
"""
import logging
import hashlib
from typing import Dict, Optional
from datetime import datetime

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from .celery_config import celery_app, store_task_metadata
from timezone_utils import utc_now

log = logging.getLogger(__name__)


def _save_backup_to_db(device_name: str, config_text: str,
                       device_type: str, snapshot_id: Optional[str] = None) -> Optional[int]:
    """
    Save device configuration backup to database.
    Returns backup_id or None on failure.
    """
    try:
        import database as db

        # Calculate config hash for change detection
        config_hash = hashlib.sha256(config_text.encode()).hexdigest()

        # Check for existing backup with same hash
        existing = db.get_latest_backup_by_device(device_name)
        if existing and existing.get('config_hash') == config_hash:
            log.debug(f"Config unchanged for {device_name}, skipping backup")
            return existing.get('backup_id')

        # Save new backup
        backup_id = db.save_config_backup(
            device_name=device_name,
            config_text=config_text,
            device_type=device_type,
            config_hash=config_hash,
            snapshot_id=snapshot_id,
            backup_time=utc_now().isoformat()
        )

        # Update snapshot counts if applicable
        if snapshot_id:
            db.increment_snapshot_counts(snapshot_id, device_name)

        log.info(f"Saved backup {backup_id} for {device_name}")
        return backup_id

    except Exception as e:
        log.error(f"Failed to save backup for {device_name}: {e}", exc_info=True)
        return None


@celery_app.task(bind=True, name='tasks.backup_tasks.backup_device_config')
def backup_device_config(self, connection_args: Dict, device_name: str,
                         snapshot_id: Optional[str] = None) -> Dict:
    """
    Backup running configuration from a network device.
    """
    task_id = self.request.id
    device_type = connection_args.get('device_type', 'unknown')

    store_task_metadata(task_id, {
        'device_name': device_name,
        'operation': 'backup_config',
        'snapshot_id': snapshot_id,
        'started_at': utc_now().isoformat()
    })

    try:
        log.info(f"Backing up config for {device_name}")

        with ConnectHandler(**connection_args) as conn:
            # Get running config
            if device_type.startswith('juniper'):
                config = conn.send_command('show configuration | display set', read_timeout=120)
            else:
                config = conn.send_command('show running-config', read_timeout=120)

            # Save to database
            backup_id = _save_backup_to_db(device_name, config, device_type, snapshot_id)

            if backup_id:
                return {
                    'status': 'success',
                    'device': device_name,
                    'backup_id': backup_id,
                    'config_length': len(config),
                    'completed_at': utc_now().isoformat()
                }
            else:
                return {
                    'status': 'error',
                    'device': device_name,
                    'error': 'Failed to save backup to database'
                }

    except NetmikoTimeoutException as e:
        return {'status': 'error', 'device': device_name, 'error': f"Timeout: {e}"}
    except NetmikoAuthenticationException as e:
        return {'status': 'error', 'device': device_name, 'error': f"Auth failed: {e}"}
    except Exception as e:
        log.error(f"Backup failed for {device_name}: {e}", exc_info=True)
        return {'status': 'error', 'device': device_name, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.backup_tasks.validate_config_from_backup')
def validate_config_from_backup(self, backup_id: int, patterns: list) -> Dict:
    """
    Validate patterns against a stored backup (without connecting to device).
    """
    try:
        import re
        import database as db

        backup = db.get_config_backup(backup_id)
        if not backup:
            return {'status': 'error', 'error': f'Backup {backup_id} not found'}

        config = backup.get('config_text', '')
        results = {}
        all_found = True

        for pattern in patterns:
            match = re.search(pattern, config, re.MULTILINE)
            results[pattern] = {
                'found': bool(match),
                'match': match.group(0) if match else None
            }
            if not match:
                all_found = False

        return {
            'status': 'success',
            'backup_id': backup_id,
            'all_patterns_found': all_found,
            'results': results
        }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.backup_tasks.cleanup_old_backups')
def cleanup_old_backups(self, retention_days: int = 30) -> Dict:
    """
    Clean up backups older than retention period.
    """
    try:
        import database as db

        schedule = db.get_backup_schedule()
        if schedule:
            retention_days = schedule.get('retention_days', retention_days)

        deleted_count = db.delete_old_backups(retention_days)

        return {
            'status': 'success',
            'deleted_count': deleted_count,
            'retention_days': retention_days
        }

    except Exception as e:
        log.error(f"Cleanup failed: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
```

**Step 2: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile tasks/backup_tasks.py
```

**Step 3: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks/backup_tasks.py
git commit -m "refactor: extract backup tasks to tasks/backup_tasks.py

Move backup_device_config, validate_config_from_backup, and
cleanup_old_backups tasks to dedicated module."
```

---

## Task 5: Create Scheduled Tasks Module

**Files:**
- Create: `/home/cwdavis/netstacks/tasks/scheduled_tasks.py`

**Step 1: Create scheduled_tasks.py**

Extract scheduled operation tasks (with the fixed database import):

```python
# /home/cwdavis/netstacks/tasks/scheduled_tasks.py
"""
Scheduled Tasks for NetStacks
Celery Beat periodic tasks for scheduled operations
"""
import logging
from typing import Dict
from datetime import datetime, timedelta

from .celery_config import celery_app
from timezone_utils import utc_now

log = logging.getLogger(__name__)


def calculate_next_run(schedule_type: str, current_time: datetime = None) -> datetime:
    """Calculate next run time based on schedule type."""
    if current_time is None:
        current_time = utc_now()

    if schedule_type == 'daily':
        return current_time + timedelta(days=1)
    elif schedule_type == 'weekly':
        return current_time + timedelta(weeks=1)
    elif schedule_type == 'monthly':
        # Approximate - add 30 days
        return current_time + timedelta(days=30)
    elif schedule_type == 'once':
        return None  # One-time schedules don't recur
    else:
        return current_time + timedelta(hours=1)


@celery_app.task(bind=True, name='tasks.scheduled_tasks.check_scheduled_operations')
def check_scheduled_operations(self):
    """
    Celery Beat periodic task to check and execute scheduled operations.
    Runs every minute to check for pending scheduled operations.
    """
    log.info("Celery Beat: Checking for pending scheduled operations...")

    try:
        import database as db

        pending_schedules = db.get_pending_scheduled_operations()
        log.info(f"Found {len(pending_schedules)} pending scheduled operations")

        for schedule in pending_schedules:
            try:
                schedule_id = schedule['schedule_id']
                stack_id = schedule['stack_id']
                operation_type = schedule['operation_type']

                log.info(f"Executing scheduled operation: {operation_type} for {stack_id}")

                # Dispatch the appropriate task
                if operation_type == 'deploy':
                    execute_scheduled_deploy.delay(schedule_id, stack_id)
                elif operation_type == 'backup':
                    execute_scheduled_backup.delay(schedule_id, stack_id)
                elif operation_type == 'mop':
                    execute_scheduled_mop.delay(schedule_id, stack_id)
                else:
                    log.warning(f"Unknown operation type: {operation_type}")
                    continue

                # Mark as in-progress
                db.update_scheduled_operation(
                    schedule_id,
                    status='in_progress',
                    last_run=utc_now().isoformat()
                )

            except Exception as e:
                log.error(f"Error queuing scheduled operation: {e}", exc_info=True)

    except Exception as e:
        log.error(f"Error in check_scheduled_operations: {e}", exc_info=True)

    return {'checked': True}


@celery_app.task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_deploy')
def execute_scheduled_deploy(self, schedule_id: str, stack_id: str):
    """Execute a scheduled stack deployment."""
    import database as db
    from jinja2 import Template

    log.info(f"Executing scheduled deploy for stack {stack_id}")

    try:
        stack = db.get_service_stack(stack_id)
        if not stack:
            raise Exception(f"Stack {stack_id} not found")

        if stack.get('state') == 'deploying':
            log.warning(f"Stack {stack_id} already deploying, skipping")
            return {'status': 'skipped', 'reason': 'already deploying'}

        # Update stack state
        stack['state'] = 'deploying'
        stack['deploy_started_at'] = utc_now().isoformat()
        db.save_service_stack(stack)

        # Deploy services
        services = sorted(stack.get('services', []), key=lambda s: s.get('order', 0))
        results = []

        for service_def in services:
            try:
                template_name = service_def.get('template')
                device_name = service_def.get('device')
                variables = service_def.get('variables', {})

                template = db.get_template_by_name(template_name)
                if not template:
                    results.append({'service': template_name, 'status': 'error', 'error': 'Template not found'})
                    continue

                device = db.get_device_by_name(device_name)
                if not device:
                    results.append({'service': template_name, 'status': 'error', 'error': 'Device not found'})
                    continue

                # Render template
                j2_template = Template(template.get('content', ''))
                config = j2_template.render(**variables)

                # Queue deploy task (would call device_tasks.set_config)
                results.append({
                    'service': template_name,
                    'device': device_name,
                    'status': 'queued',
                    'config_length': len(config)
                })

            except Exception as e:
                results.append({'service': service_def.get('template'), 'status': 'error', 'error': str(e)})

        # Update stack state
        stack['state'] = 'deployed'
        stack['deploy_completed_at'] = utc_now().isoformat()
        db.save_service_stack(stack)

        # Update schedule
        schedule = db.get_scheduled_operation(schedule_id)
        if schedule:
            schedule_type = schedule.get('schedule_type', 'once')
            next_run = calculate_next_run(schedule_type)

            db.update_scheduled_operation(
                schedule_id,
                status='completed' if schedule_type == 'once' else 'scheduled',
                last_run=utc_now().isoformat(),
                next_run=next_run.isoformat() if next_run else None
            )

        return {'status': 'success', 'stack_id': stack_id, 'results': results}

    except Exception as e:
        log.error(f"Scheduled deploy failed: {e}", exc_info=True)
        db.update_scheduled_operation(schedule_id, status='failed', error=str(e))
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_backup')
def execute_scheduled_backup(self, schedule_id: str, target_id: str):
    """Execute a scheduled backup operation."""
    import database as db
    from .backup_tasks import backup_device_config

    log.info(f"Executing scheduled backup for target {target_id}")

    try:
        # Get devices to backup
        if target_id == 'all':
            devices = db.get_all_devices()
        else:
            device = db.get_device_by_name(target_id)
            devices = [device] if device else []

        if not devices:
            return {'status': 'error', 'error': 'No devices found'}

        results = []
        for device in devices:
            device_name = device.get('name')
            connection_args = {
                'device_type': device.get('device_type', 'cisco_ios'),
                'host': device.get('host') or device.get('ip_address'),
                'username': device.get('username'),
                'password': device.get('password'),
            }

            # Queue backup task
            task = backup_device_config.delay(connection_args, device_name)
            results.append({'device': device_name, 'task_id': task.id})

        # Update schedule
        schedule = db.get_scheduled_operation(schedule_id)
        if schedule:
            schedule_type = schedule.get('schedule_type', 'once')
            next_run = calculate_next_run(schedule_type)

            db.update_scheduled_operation(
                schedule_id,
                status='completed' if schedule_type == 'once' else 'scheduled',
                last_run=utc_now().isoformat(),
                next_run=next_run.isoformat() if next_run else None
            )

        return {'status': 'success', 'backups_queued': len(results), 'results': results}

    except Exception as e:
        log.error(f"Scheduled backup failed: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_mop')
def execute_scheduled_mop(self, schedule_id: str, mop_id: str):
    """Execute a scheduled MOP (Method of Procedure)."""
    import database as db

    log.info(f"Executing scheduled MOP {mop_id}")

    try:
        from mop_engine import MOPEngine

        mop = db.get_mop(mop_id)
        if not mop:
            return {'status': 'error', 'error': f'MOP {mop_id} not found'}

        # Create execution record
        execution_id = db.create_mop_execution(
            mop_id=mop_id,
            status='running',
            started_at=utc_now().isoformat()
        )

        try:
            # Execute MOP
            engine = MOPEngine(mop.get('yaml_content', ''))
            result = engine.execute()

            # Update execution record
            db.update_mop_execution(
                execution_id,
                status='completed' if result.get('success') else 'failed',
                completed_at=utc_now().isoformat(),
                result=result
            )

        except Exception as e:
            db.update_mop_execution(
                execution_id,
                status='failed',
                completed_at=utc_now().isoformat(),
                error=str(e)
            )
            raise

        # Update schedule
        schedule = db.get_scheduled_operation(schedule_id)
        if schedule:
            schedule_type = schedule.get('schedule_type', 'once')
            next_run = calculate_next_run(schedule_type)

            db.update_scheduled_operation(
                schedule_id,
                status='completed' if schedule_type == 'once' else 'scheduled',
                last_run=utc_now().isoformat(),
                next_run=next_run.isoformat() if next_run else None
            )

        return {'status': 'success', 'mop_id': mop_id, 'execution_id': execution_id}

    except Exception as e:
        log.error(f"Scheduled MOP failed: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
```

**Step 2: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile tasks/scheduled_tasks.py
```

**Step 3: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks/scheduled_tasks.py
git commit -m "refactor: extract scheduled tasks to tasks/scheduled_tasks.py

Move check_scheduled_operations, execute_scheduled_deploy,
execute_scheduled_backup, and execute_scheduled_mop to dedicated module.
Fixed database_postgres import bug - now uses database module correctly."
```

---

## Task 6: Update __init__.py to Export All Tasks

**Files:**
- Modify: `/home/cwdavis/netstacks/tasks/__init__.py`

**Step 1: Update __init__.py**

```python
# /home/cwdavis/netstacks/tasks/__init__.py
"""
NetStacks Tasks Package
Exports celery_app and all tasks for backward compatibility.
"""

from .celery_config import (
    celery_app,
    get_redis_client,
    store_task_metadata,
    get_task_metadata,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
)

from .utils import (
    get_textfsm_template_path,
    parse_with_textfsm,
    parse_with_ttp,
    render_jinja2_template,
    get_device_queue,
)

# Import all tasks to register them with Celery
from .device_tasks import (
    get_config,
    set_config,
    run_commands,
    validate_config,
    test_connectivity,
)

from .backup_tasks import (
    backup_device_config,
    validate_config_from_backup,
    cleanup_old_backups,
)

from .scheduled_tasks import (
    check_scheduled_operations,
    execute_scheduled_deploy,
    execute_scheduled_backup,
    execute_scheduled_mop,
    calculate_next_run,
)

__all__ = [
    # Celery config
    'celery_app',
    'get_redis_client',
    'store_task_metadata',
    'get_task_metadata',
    'CELERY_BROKER_URL',
    'CELERY_RESULT_BACKEND',
    # Utils
    'get_textfsm_template_path',
    'parse_with_textfsm',
    'parse_with_ttp',
    'render_jinja2_template',
    'get_device_queue',
    # Device tasks
    'get_config',
    'set_config',
    'run_commands',
    'validate_config',
    'test_connectivity',
    # Backup tasks
    'backup_device_config',
    'validate_config_from_backup',
    'cleanup_old_backups',
    # Scheduled tasks
    'check_scheduled_operations',
    'execute_scheduled_deploy',
    'execute_scheduled_backup',
    'execute_scheduled_mop',
    'calculate_next_run',
]
```

**Step 2: Verify all imports work**

```bash
cd /home/cwdavis/netstacks
python3 -c "
from tasks import celery_app, get_task_metadata
from tasks import get_config, set_config, backup_device_config
from tasks import check_scheduled_operations
print('All imports successful!')
"
```

**Step 3: Commit**

```bash
cd /home/cwdavis/netstacks
git add tasks/__init__.py
git commit -m "refactor: update tasks/__init__.py with all task exports

Add re-exports for all device, backup, and scheduled tasks
to maintain backward compatibility with existing imports."
```

---

## Task 7: Rename Old tasks.py and Test

**Files:**
- Rename: `/home/cwdavis/netstacks/tasks.py` → `/home/cwdavis/netstacks/tasks_legacy.py`

**Step 1: Rename old file**

```bash
cd /home/cwdavis/netstacks
mv tasks.py tasks_legacy.py
```

**Step 2: Verify package import still works**

```bash
cd /home/cwdavis/netstacks
python3 -c "from tasks import celery_app; print('Package import works!')"
```

**Step 3: Syntax check all new files**

```bash
cd /home/cwdavis/netstacks
for f in tasks/*.py; do python3 -m py_compile "$f" && echo "OK: $f"; done
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add -A
git commit -m "refactor: replace monolithic tasks.py with tasks/ package

Renamed old tasks.py to tasks_legacy.py.
New tasks/ package provides same interface via __init__.py exports.

Package structure:
- tasks/celery_config.py - Celery app and configuration
- tasks/utils.py - Parsing helpers (TextFSM, TTP, Jinja2)
- tasks/device_tasks.py - Device operations
- tasks/backup_tasks.py - Backup operations
- tasks/scheduled_tasks.py - Scheduled operations
- tasks/__init__.py - Re-exports for backward compatibility"
```

---

## Task 8: Restart Services and Verify

**Step 1: Restart containers**

```bash
cd /home/cwdavis/netstacks
docker compose restart netstacks workers workers-beat
```

**Step 2: Check for import errors**

```bash
docker logs netstacks 2>&1 | grep -i "error\|import" | tail -20
docker logs netstacks-workers 2>&1 | grep -i "error\|import" | tail -20
```

**Step 3: Verify Celery tasks are registered**

```bash
docker exec netstacks-workers celery -A celery_app inspect registered | head -30
```

**Step 4: Test UI functionality**

```bash
# Run the API test script
/home/cwdavis/test_netstacks_apis.sh
```

---

## Task 9: Delete Legacy File (After Verification)

**Files:**
- Delete: `/home/cwdavis/netstacks/tasks_legacy.py`

**Step 1: Verify everything works**

Check:
- [ ] UI loads without errors
- [ ] All API endpoints respond
- [ ] Celery workers show registered tasks
- [ ] No import errors in logs

**Step 2: Delete legacy file**

```bash
cd /home/cwdavis/netstacks
rm tasks_legacy.py
git add -A
git commit -m "chore: remove legacy tasks.py after successful migration"
```

---

## Summary

After completing all tasks:

1. **Bug fixed:** `database_postgres` → `database` in scheduled_tasks.py
2. **Package created:** `tasks/` with 5 modules:
   - `celery_config.py` (config + Redis)
   - `utils.py` (parsing helpers)
   - `device_tasks.py` (5 tasks)
   - `backup_tasks.py` (3 tasks)
   - `scheduled_tasks.py` (4 tasks)
3. **Backward compatible:** All existing imports (`from tasks import X`) still work
4. **Testable:** Each module can be tested independently

**Lines reduced:** 1,235 → distributed across 5 focused modules (~200-300 lines each)

---

# Phase 2: Agent Self-Awareness System

> **Goal:** Enable AI agents to understand the NetStacks platform itself - operational state, configuration knowledge, system health, and usage patterns.

**Architecture:** Hybrid approach using Internal Tools (for dynamic queries) + Statistics API (for aggregated metrics) + Knowledge Collection (for static docs) + System Prompt Injection (for lightweight context).

---

## Task 10: Add `is_internal` Flag to Tool System

**Files:**
- Modify: `/home/cwdavis/netstacks/ai/tools/base.py`
- Modify: `/home/cwdavis/netstacks/ai/tools/registry.py`

**Step 1: Update BaseTool class**

Add `is_internal` attribute to mark tools as internal-only (hidden from UI):

```python
# In ai/tools/base.py - add to BaseTool class
class BaseTool:
    """Base class for all agent tools."""

    name: str = ""
    description: str = ""
    is_internal: bool = False  # Add this - internal tools hidden from UI

    # ... rest of class
```

**Step 2: Add get_ui_tools() method to registry**

```python
# In ai/tools/registry.py - add method to ToolRegistry class
def get_ui_tools(self) -> List[Dict]:
    """Get tools visible in UI (excludes internal tools)."""
    return [
        tool.to_dict() for tool in self._tools.values()
        if not getattr(tool, 'is_internal', False)
    ]
```

**Step 3: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile ai/tools/base.py ai/tools/registry.py
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add ai/tools/base.py ai/tools/registry.py
git commit -m "feat: add is_internal flag to tool system

Internal tools are available to agents but hidden from UI.
Adds get_ui_tools() method to registry for filtering."
```

---

## Task 11: Create Platform Statistics API

**Files:**
- Create: `/home/cwdavis/netstacks/services/platform_stats_service.py`
- Modify: `/home/cwdavis/netstacks/app.py` (add route)

**Step 1: Create PlatformStatsService**

```python
# /home/cwdavis/netstacks/services/platform_stats_service.py
"""
Platform Statistics Service
Provides aggregated platform metrics with caching.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import time

log = logging.getLogger(__name__)

# Simple TTL cache
_cache: Dict[str, Any] = {}
_cache_expiry: Dict[str, float] = {}
CACHE_TTL = 60  # seconds


def _get_cached(key: str) -> Optional[Any]:
    """Get value from cache if not expired."""
    if key in _cache and time.time() < _cache_expiry.get(key, 0):
        return _cache[key]
    return None


def _set_cached(key: str, value: Any):
    """Set value in cache with TTL."""
    _cache[key] = value
    _cache_expiry[key] = time.time() + CACHE_TTL


def get_platform_stats() -> Dict[str, Any]:
    """
    Get aggregated platform statistics.
    Cached for 60 seconds.
    """
    cached = _get_cached('platform_stats')
    if cached:
        return cached

    import database as db
    from timezone_utils import utc_now

    try:
        stats = {
            'timestamp': utc_now().isoformat(),
            'devices': _get_device_stats(db),
            'templates': _get_template_stats(db),
            'stacks': _get_stack_stats(db),
            'incidents': _get_incident_stats(db),
            'agents': _get_agent_stats(db),
            'backups': _get_backup_stats(db),
            'system': _get_system_stats(),
        }
        _set_cached('platform_stats', stats)
        return stats
    except Exception as e:
        log.error(f"Error getting platform stats: {e}", exc_info=True)
        return {'error': str(e), 'timestamp': utc_now().isoformat()}


def _get_device_stats(db) -> Dict:
    """Device statistics."""
    devices = db.get_all_devices() or []
    return {
        'total': len(devices),
        'by_type': _count_by_field(devices, 'device_type'),
        'by_status': _count_by_field(devices, 'status'),
    }


def _get_template_stats(db) -> Dict:
    """Template statistics."""
    templates = db.get_all_templates() or []
    return {
        'total': len(templates),
        'by_type': _count_by_field(templates, 'template_type'),
    }


def _get_stack_stats(db) -> Dict:
    """Service stack statistics."""
    stacks = db.get_all_service_stacks() or []
    return {
        'total': len(stacks),
        'deployed': len([s for s in stacks if s.get('state') == 'deployed']),
        'by_state': _count_by_field(stacks, 'state'),
    }


def _get_incident_stats(db) -> Dict:
    """Incident statistics."""
    incidents = db.get_all_incidents() or []
    return {
        'total': len(incidents),
        'open': len([i for i in incidents if i.get('status') == 'open']),
        'by_severity': _count_by_field(incidents, 'severity'),
        'by_status': _count_by_field(incidents, 'status'),
    }


def _get_agent_stats(db) -> Dict:
    """Agent statistics."""
    agents = db.get_all_agents() or []
    return {
        'total': len(agents),
        'active': len([a for a in agents if a.get('is_active')]),
        'by_type': _count_by_field(agents, 'agent_type'),
    }


def _get_backup_stats(db) -> Dict:
    """Backup statistics."""
    try:
        schedule = db.get_backup_schedule() or {}
        recent_backups = db.get_recent_backups(limit=100) or []
        return {
            'schedule_enabled': schedule.get('enabled', False),
            'recent_count': len(recent_backups),
        }
    except:
        return {'schedule_enabled': False, 'recent_count': 0}


def _get_system_stats() -> Dict:
    """System health statistics."""
    try:
        import redis
        import os

        redis_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)
        redis_ok = r.ping()
    except:
        redis_ok = False

    return {
        'redis_connected': redis_ok,
    }


def _count_by_field(items: list, field: str) -> Dict[str, int]:
    """Count items by field value."""
    counts = {}
    for item in items:
        value = item.get(field, 'unknown') or 'unknown'
        counts[value] = counts.get(value, 0) + 1
    return counts
```

**Step 2: Add API route to app.py**

Add near other API routes:

```python
@app.route('/api/platform/stats', methods=['GET'])
@login_required
def get_platform_statistics():
    """Get aggregated platform statistics for agent self-awareness."""
    from services.platform_stats_service import get_platform_stats
    return jsonify(get_platform_stats())
```

**Step 3: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile services/platform_stats_service.py
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add services/platform_stats_service.py app.py
git commit -m "feat: add platform statistics API for agent self-awareness

Adds /api/platform/stats endpoint with 60s caching.
Returns aggregated metrics: devices, templates, stacks, incidents, agents."
```

---

## Task 12: Create Internal Platform Tools

**Files:**
- Create: `/home/cwdavis/netstacks/ai/tools/platform_tools.py`
- Modify: `/home/cwdavis/netstacks/ai/tools/__init__.py`

**Step 1: Create platform tools module**

```python
# /home/cwdavis/netstacks/ai/tools/platform_tools.py
"""
Internal Platform Tools for Agent Self-Awareness
These tools allow agents to query NetStacks platform state.
"""
import logging
from typing import Dict, Any, Optional

from .base import BaseTool

log = logging.getLogger(__name__)


class PlatformStatusTool(BaseTool):
    """Get current platform status and statistics."""

    name = "platform_status"
    description = "Get NetStacks platform status including device counts, incident counts, and system health."
    is_internal = True

    def execute(self, **kwargs) -> Dict[str, Any]:
        from services.platform_stats_service import get_platform_stats
        return get_platform_stats()


class StackInfoTool(BaseTool):
    """Get information about service stacks."""

    name = "stack_info"
    description = "Get details about service stacks - deployed services, their states, and associated templates."
    is_internal = True

    def execute(self, stack_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        import database as db

        if stack_name:
            stack = db.get_service_stack_by_name(stack_name)
            if not stack:
                return {'error': f'Stack {stack_name} not found'}
            return {'stack': stack}

        stacks = db.get_all_service_stacks() or []
        return {
            'total': len(stacks),
            'stacks': [
                {
                    'name': s.get('stack_name'),
                    'state': s.get('state'),
                    'service_count': len(s.get('services', [])),
                }
                for s in stacks
            ]
        }


class TemplateInfoTool(BaseTool):
    """Get information about configuration templates."""

    name = "template_info"
    description = "Get details about configuration templates - types, variables, and usage."
    is_internal = True

    def execute(self, template_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        import database as db

        if template_name:
            template = db.get_template_by_name(template_name)
            if not template:
                return {'error': f'Template {template_name} not found'}
            return {'template': template}

        templates = db.get_all_templates() or []
        return {
            'total': len(templates),
            'templates': [
                {
                    'name': t.get('template_name'),
                    'type': t.get('template_type'),
                    'description': t.get('description', '')[:100],
                }
                for t in templates
            ]
        }


class IncidentStatusTool(BaseTool):
    """Get current incident status."""

    name = "incident_status"
    description = "Get current open incidents, their severity, and status."
    is_internal = True

    def execute(self, status: str = 'open', **kwargs) -> Dict[str, Any]:
        import database as db

        incidents = db.get_incidents_by_status(status) or []
        return {
            'status_filter': status,
            'count': len(incidents),
            'incidents': [
                {
                    'id': i.get('incident_id'),
                    'title': i.get('title'),
                    'severity': i.get('severity'),
                    'status': i.get('status'),
                    'created_at': i.get('created_at'),
                }
                for i in incidents[:20]  # Limit to 20
            ]
        }


class SystemHealthTool(BaseTool):
    """Check system component health."""

    name = "system_health"
    description = "Check health of system components: database, Redis, Celery workers."
    is_internal = True

    def execute(self, **kwargs) -> Dict[str, Any]:
        import os
        results = {'components': {}}

        # Check Redis
        try:
            import redis
            redis_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
            r = redis.from_url(redis_url)
            results['components']['redis'] = {'status': 'ok' if r.ping() else 'error'}
        except Exception as e:
            results['components']['redis'] = {'status': 'error', 'error': str(e)}

        # Check database
        try:
            import database as db
            db.get_all_devices()  # Simple query test
            results['components']['database'] = {'status': 'ok'}
        except Exception as e:
            results['components']['database'] = {'status': 'error', 'error': str(e)}

        # Check Celery workers
        try:
            from tasks import celery_app
            inspector = celery_app.control.inspect()
            active = inspector.active() or {}
            results['components']['celery'] = {
                'status': 'ok' if active else 'warning',
                'worker_count': len(active),
            }
        except Exception as e:
            results['components']['celery'] = {'status': 'error', 'error': str(e)}

        # Overall status
        statuses = [c.get('status') for c in results['components'].values()]
        if all(s == 'ok' for s in statuses):
            results['overall'] = 'healthy'
        elif 'error' in statuses:
            results['overall'] = 'degraded'
        else:
            results['overall'] = 'warning'

        return results


class PlatformConceptsTool(BaseTool):
    """Explain NetStacks platform concepts."""

    name = "platform_concepts"
    description = "Get explanations of NetStacks concepts: templates, stacks, MOPs, agents, etc."
    is_internal = True

    CONCEPTS = {
        'template': 'A Jinja2-based configuration template for network devices. Templates have variables that get filled in during rendering.',
        'stack': 'A Service Stack groups multiple templates together for coordinated deployment. Stacks define the order of template application.',
        'stack_template': 'Links a template to a stack with specific variable values and deployment order.',
        'mop': 'Method of Procedure - a multi-step automation workflow with approval gates and rollback capabilities.',
        'agent': 'An AI agent that can perform automated tasks, handle alerts, or assist with operations.',
        'incident': 'A tracked issue that may have correlated alerts and require remediation.',
        'backup': 'A stored copy of a device configuration, used for compliance and rollback.',
        'snapshot': 'A point-in-time backup of multiple devices, often scheduled.',
    }

    def execute(self, concept: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if concept:
            concept_lower = concept.lower()
            if concept_lower in self.CONCEPTS:
                return {'concept': concept, 'explanation': self.CONCEPTS[concept_lower]}
            return {'error': f'Unknown concept: {concept}', 'available': list(self.CONCEPTS.keys())}

        return {'concepts': self.CONCEPTS}


# Export all platform tools
PLATFORM_TOOLS = [
    PlatformStatusTool,
    StackInfoTool,
    TemplateInfoTool,
    IncidentStatusTool,
    SystemHealthTool,
    PlatformConceptsTool,
]
```

**Step 2: Register tools in __init__.py**

```python
# Add to ai/tools/__init__.py
from .platform_tools import PLATFORM_TOOLS

# In the initialization code, register platform tools:
for tool_class in PLATFORM_TOOLS:
    registry.register(tool_class())
```

**Step 3: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile ai/tools/platform_tools.py
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add ai/tools/platform_tools.py ai/tools/__init__.py
git commit -m "feat: add internal platform tools for agent self-awareness

Adds 6 internal tools (hidden from UI, available to agents):
- platform_status: Get platform statistics
- stack_info: Query service stacks
- template_info: Query templates
- incident_status: Get open incidents
- system_health: Check component health
- platform_concepts: Explain platform concepts"
```

---

## Task 13: Auto-Generate NetStacks Knowledge Collection

**Files:**
- Create: `/home/cwdavis/netstacks/ai/knowledge/platform_docs.py`
- Create: `/home/cwdavis/netstacks/ai/knowledge/netstacks_docs/` directory with markdown files

**Step 1: Create platform docs directory**

```bash
mkdir -p /home/cwdavis/netstacks/ai/knowledge/netstacks_docs
```

**Step 2: Create core documentation files**

```markdown
# /home/cwdavis/netstacks/ai/knowledge/netstacks_docs/overview.md

# NetStacks Platform Overview

NetStacks is a NOC (Network Operations Center) automation platform that manages network devices, configurations, and automated operations.

## Core Components

### Devices
Network devices (routers, switches, firewalls) managed by NetStacks. Each device has connection credentials and a device type (cisco_ios, juniper_junos, etc.).

### Templates
Jinja2-based configuration templates. Templates have variables that get populated when rendering configuration for a specific device or service.

### Service Stacks
Groups of templates deployed together as a coordinated service. Stacks define deployment order and variable mappings.

### MOPs (Method of Procedure)
Step-by-step automation workflows with approval gates. MOPs can include pre-checks, configuration changes, validation, and rollback procedures.

### Agents
AI agents that handle automated tasks:
- Alert Triage: Correlates and prioritizes incoming alerts
- Incident Response: Investigates and remediates incidents
- Config Validation: Validates configurations against policies

### Incidents & Alerts
Alerts are individual events from monitoring systems. Incidents group related alerts and track remediation progress.

### Backups & Snapshots
Device configuration backups stored for compliance and rollback. Snapshots are point-in-time backups across multiple devices.
```

```markdown
# /home/cwdavis/netstacks/ai/knowledge/netstacks_docs/workflows.md

# NetStacks Workflows

## Template to Stack Deployment Flow

1. **Create Template**: Define Jinja2 template with variables
2. **Create Stack**: Group templates with deployment order
3. **Add Stack Templates**: Link templates to stack with variable values
4. **Deploy Stack**: Render templates and push to devices
5. **Validate**: Run post-deployment validation checks

## Incident Lifecycle

1. **Alert Received**: Webhook from monitoring system
2. **Triage**: AI agent correlates with existing incidents
3. **Incident Created**: If new issue, create incident
4. **Investigation**: Agent gathers context, runs diagnostics
5. **Remediation**: Execute automated fixes or escalate
6. **Resolution**: Verify fix, close incident

## MOP Execution

1. **Create MOP**: Define steps, approvals, rollback
2. **Schedule**: Set execution time or trigger
3. **Pre-checks**: Validate device state
4. **Approval**: Get required approvals
5. **Execute**: Run configuration steps
6. **Validation**: Verify changes applied
7. **Rollback**: If validation fails, revert changes
```

**Step 3: Create knowledge loader**

```python
# /home/cwdavis/netstacks/ai/knowledge/platform_docs.py
"""
Platform Documentation Loader
Loads NetStacks documentation into knowledge base.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict

log = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / 'netstacks_docs'
COLLECTION_NAME = 'netstacks-platform'


def get_platform_docs() -> List[Dict]:
    """Load all platform documentation files."""
    docs = []

    if not DOCS_DIR.exists():
        log.warning(f"Platform docs directory not found: {DOCS_DIR}")
        return docs

    for md_file in DOCS_DIR.glob('*.md'):
        try:
            content = md_file.read_text()
            docs.append({
                'filename': md_file.name,
                'title': _extract_title(content),
                'content': content,
                'collection': COLLECTION_NAME,
            })
        except Exception as e:
            log.error(f"Error reading {md_file}: {e}")

    return docs


def _extract_title(content: str) -> str:
    """Extract title from markdown content."""
    for line in content.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return 'Untitled'


def sync_platform_docs_to_knowledge_base():
    """
    Sync platform documentation to the knowledge base.
    Called on startup or manually to update embeddings.
    """
    try:
        import database as db

        docs = get_platform_docs()
        if not docs:
            log.info("No platform docs to sync")
            return

        for doc in docs:
            # Check if doc already exists
            existing = db.get_knowledge_document_by_name(
                doc['filename'],
                collection=COLLECTION_NAME
            )

            if existing:
                # Update if content changed
                if existing.get('content') != doc['content']:
                    db.update_knowledge_document(
                        existing['doc_id'],
                        content=doc['content'],
                        title=doc['title']
                    )
                    log.info(f"Updated platform doc: {doc['filename']}")
            else:
                # Create new
                db.create_knowledge_document(
                    filename=doc['filename'],
                    title=doc['title'],
                    content=doc['content'],
                    collection=COLLECTION_NAME,
                    doc_type='platform_docs'
                )
                log.info(f"Created platform doc: {doc['filename']}")

        log.info(f"Synced {len(docs)} platform docs to knowledge base")

    except Exception as e:
        log.error(f"Error syncing platform docs: {e}", exc_info=True)
```

**Step 4: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile ai/knowledge/platform_docs.py
```

**Step 5: Commit**

```bash
cd /home/cwdavis/netstacks
git add ai/knowledge/
git commit -m "feat: add auto-generated netstacks-platform knowledge collection

Creates 'netstacks-platform' collection with platform documentation:
- overview.md: Core platform concepts
- workflows.md: Common operational workflows

Includes sync_platform_docs_to_knowledge_base() for embedding updates."
```

---

## Task 14: Inject Platform Summary into Agent System Prompts

**Files:**
- Modify: `/home/cwdavis/netstacks/ai/agents/base_agent.py`

**Step 1: Add platform context injection**

```python
# Add to ai/agents/base_agent.py

def get_platform_context_summary() -> str:
    """
    Generate a brief platform context summary for agent system prompts.
    Injected automatically so agents understand current platform state.
    """
    try:
        from services.platform_stats_service import get_platform_stats
        stats = get_platform_stats()

        summary = f"""
## Current NetStacks Platform State

- **Devices:** {stats.get('devices', {}).get('total', 0)} total
- **Templates:** {stats.get('templates', {}).get('total', 0)} available
- **Service Stacks:** {stats.get('stacks', {}).get('deployed', 0)} deployed / {stats.get('stacks', {}).get('total', 0)} total
- **Open Incidents:** {stats.get('incidents', {}).get('open', 0)}
- **Active Agents:** {stats.get('agents', {}).get('active', 0)}

You have access to internal platform tools: platform_status, stack_info, template_info, incident_status, system_health, platform_concepts.
"""
        return summary.strip()
    except Exception as e:
        return f"[Platform context unavailable: {e}]"


# In the agent's build_system_prompt() or similar method, add:
# platform_context = get_platform_context_summary()
# system_prompt = f"{base_prompt}\n\n{platform_context}"
```

**Step 2: Update agent initialization to inject context**

Modify the agent's system prompt building to include platform context:

```python
# In the agent class that builds system prompts
def build_system_prompt(self) -> str:
    """Build the complete system prompt with platform context."""
    base_prompt = self.config.get('system_prompt', self.DEFAULT_SYSTEM_PROMPT)
    platform_context = get_platform_context_summary()
    return f"{base_prompt}\n\n{platform_context}"
```

**Step 3: Verify syntax**

```bash
cd /home/cwdavis/netstacks
python3 -m py_compile ai/agents/base_agent.py
```

**Step 4: Commit**

```bash
cd /home/cwdavis/netstacks
git add ai/agents/base_agent.py
git commit -m "feat: inject platform summary into agent system prompts

Agents automatically receive current platform state in their context:
- Device/template/stack counts
- Open incident count
- Available internal tools

Lightweight approach - summary regenerated from cached stats."
```

---

## Task 15: Restart and Verify Self-Awareness Features

**Step 1: Restart services**

```bash
cd /home/cwdavis/netstacks
docker compose restart netstacks workers
```

**Step 2: Test platform stats API**

```bash
COOKIES=/tmp/ns_test.txt
curl -s -c $COOKIES -X POST http://localhost:8089/login -d "username=admin&password=admin" > /dev/null
curl -s -b $COOKIES http://localhost:8089/api/platform/stats | jq .
```

**Step 3: Verify internal tools not in UI**

```bash
# Check that platform tools are NOT returned in regular tools list
curl -s -b $COOKIES http://localhost:8089/api/tools | jq '.[] | select(.is_internal == true)'
# Expected: Empty (internal tools filtered out)
```

**Step 4: Check logs for errors**

```bash
docker logs netstacks 2>&1 | grep -i "error\|platform" | tail -20
```

---

## Phase 2 Summary

After completing all Agent Self-Awareness tasks:

1. **Internal Tools System:** `is_internal` flag hides tools from UI
2. **Platform Statistics API:** `/api/platform/stats` with 60s caching
3. **6 Internal Tools:**
   - `platform_status` - Overall platform metrics
   - `stack_info` - Service stack details
   - `template_info` - Template details
   - `incident_status` - Open incidents
   - `system_health` - Component health checks
   - `platform_concepts` - Platform concept explanations
4. **Knowledge Collection:** `netstacks-platform` with auto-generated docs
5. **System Prompt Injection:** Platform context automatically added to agent prompts

**Agents can now:**
- Query "How many service stacks are deployed?" → `platform_status` tool
- Ask "What does a MOP do?" → `platform_concepts` tool
- Check "Are there open incidents?" → `incident_status` tool
- Understand platform workflows → RAG search on `netstacks-platform` collection
