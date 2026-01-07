"""
Backup Tasks

Celery tasks for device configuration backup operations.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from celery import shared_task
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from sqlalchemy.orm import Session

from netstacks_core.db import (
    get_session,
    ConfigBackup,
    ConfigSnapshot,
    BackupSchedule,
    Device,
)

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.utcnow()


@shared_task(bind=True, name='tasks.backup_tasks.backup_device_config')
def backup_device_config(self, connection_args: Dict, device_name: str,
                         device_platform: str = None, juniper_set_format: bool = True,
                         snapshot_id: str = None, created_by: str = None) -> Dict:
    """
    Backup device running configuration and save to database.

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        device_name: Name of the device (for metadata)
        device_platform: Platform name (for identifying Juniper)
        juniper_set_format: If True, get Juniper config in set format
        snapshot_id: Optional snapshot ID to link backup to a snapshot
        created_by: Username who initiated the backup

    Returns:
        Dict with config content and metadata
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'device_name': device_name,
        'config_format': 'native',
    }

    try:
        log.info(f"Starting config backup for {device_name} ({connection_args.get('host')})")

        device_type = connection_args.get('device_type', '').lower()
        is_juniper = 'juniper' in device_type or (device_platform and 'junos' in device_platform.lower())

        with ConnectHandler(**connection_args) as conn:
            # Enter enable mode if needed (for Cisco/Arista devices)
            if not is_juniper and hasattr(conn, 'enable'):
                try:
                    conn.enable()
                except Exception as e:
                    log.debug(f"Enable mode not required or failed for {device_name}: {e}")

            if is_juniper and juniper_set_format:
                config_output = conn.send_command('show configuration | display set')
                result['config_format'] = 'set'
            elif is_juniper:
                config_output = conn.send_command('show configuration')
            elif 'cisco' in device_type or 'ios' in device_type:
                config_output = conn.send_command('show running-config')
            elif 'arista' in device_type or 'eos' in device_type:
                config_output = conn.send_command('show running-config')
            elif 'nokia' in device_type or 'sros' in device_type:
                config_output = conn.send_command('admin display-config')
            else:
                config_output = conn.send_command('show running-config')

            result['config_content'] = config_output
            result['config_size'] = len(config_output)
            result['status'] = 'success'

            # Save backup to database
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content=config_output,
                config_format=result['config_format'],
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='success'
            )
            result['saved'] = True

    except NetmikoTimeoutException as e:
        log.error(f"Timeout backing up {device_name}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Connection timeout: {str(e)}"
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed backing up {device_name}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Authentication failed: {str(e)}"
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    except Exception as e:
        log.error(f"Error backing up {device_name}: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    return result


def _save_backup_to_db(device_name: str, device_ip: str, platform: str,
                       config_content: str, config_format: str,
                       snapshot_id: str = None, created_by: str = None,
                       status: str = 'success', error_message: str = None):
    """Save backup to database and update snapshot counts."""
    session = get_session()
    backup_saved = False
    backup_id = f"backup_{utc_now().strftime('%Y%m%d_%H%M%S%f')}_{device_name}"

    try:
        # Calculate config hash
        config_hash = hashlib.sha256(config_content.encode()).hexdigest() if config_content else None

        backup = ConfigBackup(
            backup_id=backup_id,
            device_name=device_name,
            device_ip=device_ip,
            platform=platform,
            config_content=config_content,
            config_format=config_format,
            config_hash=config_hash,
            backup_type='snapshot' if snapshot_id else 'manual',
            status=status,
            error_message=error_message,
            file_size=len(config_content) if config_content else 0,
            snapshot_id=snapshot_id,
            created_by=created_by,
        )

        session.add(backup)
        session.commit()
        backup_saved = True
        log.info(f"Saved backup {backup_id} for device {device_name}")

    except Exception as e:
        log.error(f"Failed to save backup for {device_name}: {e}", exc_info=True)
        session.rollback()
        status = 'failed'

    # Update snapshot counts if applicable
    if snapshot_id:
        try:
            snapshot = session.query(ConfigSnapshot).filter(
                ConfigSnapshot.snapshot_id == snapshot_id
            ).first()

            if snapshot:
                final_status = status if backup_saved else 'failed'
                if final_status == 'success':
                    snapshot.success_count = (snapshot.success_count or 0) + 1
                else:
                    snapshot.failed_count = (snapshot.failed_count or 0) + 1

                # Check if snapshot is complete (include skipped devices)
                total = (snapshot.success_count or 0) + (snapshot.failed_count or 0) + (snapshot.skipped_count or 0)
                if total >= snapshot.total_devices:
                    # Status is 'complete' only if no failures/skips, otherwise 'partial'
                    if (snapshot.failed_count or 0) == 0 and (snapshot.skipped_count or 0) == 0:
                        snapshot.status = 'complete'
                    else:
                        snapshot.status = 'partial'
                    snapshot.completed_at = utc_now()

                session.commit()
                log.info(f"Updated snapshot {snapshot_id} counts")

        except Exception as e:
            log.error(f"Failed to update snapshot counts: {e}")
            session.rollback()

    session.close()


@shared_task(bind=True, name='tasks.backup_tasks.create_snapshot')
def create_snapshot(self, device_names: List[str] = None,
                    snapshot_name: str = None, created_by: str = None,
                    juniper_set_format: bool = True) -> Dict:
    """
    Create a configuration snapshot for multiple devices.

    Args:
        device_names: List of device names to backup (None = all devices)
        snapshot_name: Optional name for the snapshot
        created_by: Username who initiated the snapshot
        juniper_set_format: Use set format for Juniper devices

    Returns:
        Dict with snapshot_id and queued task info
    """
    session = get_session()
    snapshot_id = str(uuid.uuid4())

    try:
        # Get devices to backup
        if device_names:
            devices = session.query(Device).filter(
                Device.name.in_(device_names)
            ).all()
        else:
            devices = session.query(Device).all()

        if not devices:
            return {'status': 'failed', 'error': 'No devices found'}

        # Create snapshot record
        snapshot = ConfigSnapshot(
            snapshot_id=snapshot_id,
            name=snapshot_name or f"Snapshot {utc_now().strftime('%Y-%m-%d %H:%M')}",
            snapshot_type='manual',
            status='in_progress',
            total_devices=len(devices),
            success_count=0,
            failed_count=0,
            created_by=created_by,
        )
        session.add(snapshot)
        session.commit()

        # Queue backup tasks for each device
        queued_tasks = []
        for device in devices:
            connection_args = {
                'device_type': device.device_type,
                'host': device.host,
                'username': device.username,
                'password': device.password,
                'port': device.port or 22,
            }
            if device.enable_password:
                connection_args['secret'] = device.enable_password

            task = backup_device_config.delay(
                connection_args=connection_args,
                device_name=device.name,
                device_platform=device.platform,
                juniper_set_format=juniper_set_format,
                snapshot_id=snapshot_id,
                created_by=created_by,
            )
            queued_tasks.append({
                'device': device.name,
                'task_id': task.id,
            })

        log.info(f"Created snapshot {snapshot_id} with {len(devices)} devices")

        return {
            'status': 'success',
            'snapshot_id': snapshot_id,
            'total_devices': len(devices),
            'tasks': queued_tasks,
        }

    except Exception as e:
        log.error(f"Error creating snapshot: {e}", exc_info=True)
        session.rollback()
        return {'status': 'failed', 'error': str(e)}

    finally:
        session.close()


@shared_task(bind=True, name='tasks.backup_tasks.cleanup_old_backups')
def cleanup_old_backups(self) -> Dict:
    """
    Clean up old backup files based on retention policy.
    Runs daily via Celery Beat.
    """
    session = get_session()

    try:
        # Get backup schedule for retention setting
        schedule = session.query(BackupSchedule).filter(
            BackupSchedule.schedule_id == 'default'
        ).first()

        retention_days = schedule.retention_days if schedule else 30
        cutoff_date = utc_now() - timedelta(days=retention_days)

        # Delete old backups
        deleted = session.query(ConfigBackup).filter(
            ConfigBackup.created_at < cutoff_date
        ).delete()

        session.commit()
        log.info(f"Cleaned up {deleted} old backups (retention: {retention_days} days)")

        return {'status': 'success', 'deleted': deleted}

    except Exception as e:
        log.error(f"Error in cleanup_old_backups: {e}", exc_info=True)
        session.rollback()
        return {'status': 'failed', 'error': str(e)}

    finally:
        session.close()
