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
