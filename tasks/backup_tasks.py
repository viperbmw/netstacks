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
                         device_platform: str = None, juniper_set_format: bool = True,
                         snapshot_id: Optional[str] = None, created_by: str = None) -> Dict:
    """
    Backup running configuration from a network device.

    Args:
        connection_args: Device connection parameters
        device_name: Name of the device
        device_platform: Platform name (to identify Juniper)
        juniper_set_format: Get Juniper configs in set format (default True)
        snapshot_id: Optional snapshot ID to link backup to
        created_by: Username who initiated the backup
    """
    task_id = self.request.id
    device_type = connection_args.get('device_type', 'unknown')

    store_task_metadata(task_id, {
        'device_name': device_name,
        'operation': 'backup_config',
        'snapshot_id': snapshot_id,
        'created_by': created_by,
        'started_at': utc_now().isoformat()
    })

    try:
        log.info(f"Backing up config for {device_name} (created_by: {created_by})")

        with ConnectHandler(**connection_args) as conn:
            # Get running config - handle Juniper specially
            is_juniper = device_type.startswith('juniper') or (device_platform and 'juniper' in device_platform.lower())
            if is_juniper:
                if juniper_set_format:
                    config = conn.send_command('show configuration | display set', read_timeout=120)
                else:
                    config = conn.send_command('show configuration', read_timeout=120)
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
