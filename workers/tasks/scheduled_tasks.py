"""
Scheduled Tasks

Celery tasks for scheduled operation execution.
Handles stack deployments, backups, and MOP executions on schedule.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from celery import shared_task
from sqlalchemy.orm import Session

from netstacks_core.db import (
    get_session,
    ScheduledStackOperation,
    ServiceStack,
    MOP,
    MOPExecution,
    Device,
    Template,
)

from .device_tasks import set_config
from .backup_tasks import backup_device_config

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.utcnow()


def calculate_next_run(schedule: ScheduledStackOperation) -> Optional[datetime]:
    """Calculate the next run time for a recurring schedule."""
    schedule_type = schedule.schedule_type
    scheduled_time = schedule.scheduled_time
    now = utc_now()

    try:
        if schedule_type == 'once':
            # One-time schedules don't have a next run after execution
            return None

        # Parse time (HH:MM)
        if ':' in scheduled_time:
            parts = scheduled_time.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            hour, minute = 0, 0

        if schedule_type == 'daily':
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif schedule_type == 'weekly':
            day_of_week = schedule.day_of_week or 0
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = day_of_week - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and next_run <= now):
                days_ahead += 7
            next_run += timedelta(days=days_ahead)
            return next_run

        elif schedule_type == 'monthly':
            day_of_month = schedule.day_of_month or 1
            next_run = now.replace(
                day=min(day_of_month, 28),
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )
            if next_run <= now:
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

    except Exception as e:
        log.error(f"Error calculating next run: {e}")
        return None

    return None


@shared_task(bind=True, name='tasks.scheduled_tasks.check_scheduled_operations')
def check_scheduled_operations(self) -> Dict:
    """
    Celery Beat periodic task to check and execute scheduled operations.
    Runs every minute to check for pending scheduled operations.
    """
    session = get_session()

    try:
        now = utc_now()

        # Find schedules that are due
        pending_schedules = session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.enabled == True,
            ScheduledStackOperation.next_run <= now,
        ).all()

        log.info(f"Found {len(pending_schedules)} pending scheduled operations")

        for schedule in pending_schedules:
            try:
                schedule_id = schedule.schedule_id
                stack_id = schedule.stack_id
                operation_type = schedule.operation_type

                log.info(f"Executing scheduled operation: {operation_type} for stack {stack_id}")

                # Dispatch the appropriate task
                if operation_type == 'deploy':
                    execute_scheduled_deploy.delay(schedule_id, stack_id)
                elif operation_type == 'validate':
                    execute_scheduled_validate.delay(schedule_id, stack_id)
                elif operation_type == 'backup':
                    execute_scheduled_backup.delay(schedule_id, stack_id)
                else:
                    log.warning(f"Unknown operation type: {operation_type}")
                    continue

                # Update last run and calculate next run
                schedule.last_run = now
                schedule.run_count = (schedule.run_count or 0) + 1

                if schedule.schedule_type == 'once':
                    schedule.enabled = False
                    schedule.next_run = None
                else:
                    schedule.next_run = calculate_next_run(schedule)

                session.commit()

            except Exception as e:
                log.error(f"Error queuing scheduled operation {schedule.schedule_id}: {e}", exc_info=True)
                session.rollback()

        return {'checked': True, 'processed': len(pending_schedules)}

    except Exception as e:
        log.error(f"Error in check_scheduled_operations: {e}", exc_info=True)
        return {'checked': False, 'error': str(e)}

    finally:
        session.close()


@shared_task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_deploy')
def execute_scheduled_deploy(self, schedule_id: str, stack_id: str) -> Dict:
    """Execute a scheduled stack deployment."""
    from jinja2 import Environment, BaseLoader

    session = get_session()

    try:
        log.info(f"Executing scheduled deploy for stack {stack_id}")

        # Get stack
        stack = session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if not stack:
            return {'status': 'failed', 'error': f'Stack {stack_id} not found'}

        if stack.state == 'deploying':
            log.warning(f"Stack {stack_id} is already deploying, skipping")
            return {'status': 'skipped', 'reason': 'already deploying'}

        # Update stack state
        stack.state = 'deploying'
        stack.deploy_started_at = utc_now()
        stack.deployed_services = []
        stack.has_pending_changes = False
        stack.pending_since = None
        session.commit()

        # Deploy services
        services = sorted(stack.services or [], key=lambda s: s.get('order', 0))
        deployed_services = []
        failed_services = []

        for service_def in services:
            try:
                template_name = service_def.get('template')
                if not template_name:
                    raise Exception(f"Service '{service_def.get('name')}' has no template")

                template = session.query(Template).filter(
                    Template.name == template_name
                ).first()

                if not template:
                    raise Exception(f"Template '{template_name}' not found")

                # Merge variables
                variables = {
                    **(stack.shared_variables or {}),
                    **(service_def.get('variables') or {})
                }

                # Render template
                env = Environment(loader=BaseLoader())
                jinja_template = env.from_string(template.content or '')
                rendered_config = jinja_template.render(**variables)

                # Get device
                device_name = service_def.get('device')
                device = session.query(Device).filter(
                    Device.name == device_name
                ).first()

                if device:
                    connection_args = {
                        'device_type': device.device_type,
                        'host': device.host,
                        'username': device.username,
                        'password': device.password,
                        'port': device.port or 22,
                    }
                    if device.enable_password:
                        connection_args['secret'] = device.enable_password

                    # Queue config push
                    set_config.delay(
                        connection_args=connection_args,
                        config_lines=rendered_config.split('\n'),
                        save_config=True,
                    )

                deployed_services.append(service_def.get('name'))
                log.info(f"Queued deploy for service {service_def.get('name')}")

            except Exception as e:
                log.error(f"Failed to deploy service {service_def.get('name')}: {e}")
                failed_services.append({
                    'name': service_def.get('name'),
                    'error': str(e)
                })

        # Update stack state
        stack.state = 'deployed' if not failed_services else 'failed'
        stack.deployed_services = deployed_services
        stack.deploy_completed_at = utc_now()
        if failed_services:
            stack.deployment_errors = failed_services
        session.commit()

        return {
            'status': 'success',
            'deployed': deployed_services,
            'failed': failed_services
        }

    except Exception as e:
        log.error(f"Error in scheduled deploy: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}

    finally:
        session.close()


@shared_task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_validate')
def execute_scheduled_validate(self, schedule_id: str, stack_id: str) -> Dict:
    """Execute a scheduled stack validation."""
    session = get_session()

    try:
        log.info(f"Executing scheduled validation for stack {stack_id}")

        stack = session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if not stack:
            return {'status': 'failed', 'error': f'Stack {stack_id} not found'}

        # Update validation status
        stack.last_validated = utc_now()
        stack.validation_status = 'validating'
        session.commit()

        # TODO: Implement actual validation logic
        # For now, just mark as validated
        stack.validation_status = 'valid'
        session.commit()

        return {'status': 'success', 'validation_status': 'valid'}

    except Exception as e:
        log.error(f"Error in scheduled validate: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}

    finally:
        session.close()


@shared_task(bind=True, name='tasks.scheduled_tasks.execute_scheduled_backup')
def execute_scheduled_backup(self, schedule_id: str, target_id: str) -> Dict:
    """Execute a scheduled backup operation."""
    session = get_session()

    try:
        log.info(f"Executing scheduled backup for target {target_id}")

        # target_id could be 'all' or a specific device name
        if target_id == 'all':
            devices = session.query(Device).all()
        else:
            device = session.query(Device).filter(
                Device.name == target_id
            ).first()
            devices = [device] if device else []

        if not devices:
            return {'status': 'failed', 'error': f'No devices found for target: {target_id}'}

        backup_tasks = []
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
                created_by='scheduled',
            )
            backup_tasks.append({
                'device': device.name,
                'task_id': task.id
            })

        return {'status': 'success', 'backups': backup_tasks}

    except Exception as e:
        log.error(f"Error in scheduled backup: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}

    finally:
        session.close()
