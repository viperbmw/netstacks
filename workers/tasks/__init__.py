"""
NetStacks Celery Tasks

This package contains all Celery tasks for network automation:
- device_tasks: Device configuration operations (get_config, set_config, etc.)
- backup_tasks: Configuration backup operations
- scheduled_tasks: Scheduled operation execution
"""

from .device_tasks import get_config, set_config, run_commands, validate_config, test_connectivity
from .backup_tasks import backup_device_config, create_snapshot, cleanup_old_backups
from .scheduled_tasks import check_scheduled_operations

__all__ = [
    'get_config',
    'set_config',
    'run_commands',
    'validate_config',
    'test_connectivity',
    'backup_device_config',
    'create_snapshot',
    'cleanup_old_backups',
    'check_scheduled_operations',
]
