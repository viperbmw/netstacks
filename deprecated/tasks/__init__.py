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
