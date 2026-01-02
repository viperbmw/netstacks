"""
Celery Application Configuration for NetStacks Workers

This is the main Celery application that orchestrates all background tasks
for network automation, backups, and scheduled operations.
"""

import os
import logging
from datetime import datetime
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure
from celery.schedules import crontab

log = logging.getLogger(__name__)

# Celery configuration from environment
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://netstacks:netstacks@db:5432/netstacks')

# Create Celery app
celery_app = Celery(
    'netstacks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        'tasks.device_tasks',
        'tasks.backup_tasks',
        'tasks.scheduled_tasks',
    ]
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,

    # Task tracking
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Results
    result_expires=3600,  # Results expire after 1 hour
)

# Task routing - device operations go to device_tasks queue
celery_app.conf.task_routes = {
    'tasks.device_tasks.get_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.set_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.run_commands': {'queue': 'device_tasks'},
    'tasks.device_tasks.validate_config': {'queue': 'device_tasks'},
    'tasks.device_tasks.test_connectivity': {'queue': 'device_tasks'},
    'tasks.backup_tasks.backup_device_config': {'queue': 'device_tasks'},
    'tasks.backup_tasks.create_snapshot': {'queue': 'celery'},
    'tasks.scheduled_tasks.*': {'queue': 'celery'},
}

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'check-scheduled-operations': {
        'task': 'tasks.scheduled_tasks.check_scheduled_operations',
        'schedule': 60.0,  # Every 60 seconds
    },
    'cleanup-old-backups': {
        'task': 'tasks.backup_tasks.cleanup_old_backups',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
}

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ============================================================================
# Database persistence for task history
# ============================================================================

def get_db_session():
    """Create a database session for task persistence."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()


def update_task_status(task_id: str, **kwargs):
    """Update task status in database."""
    try:
        from netstacks_core.db import TaskHistory
        session = get_db_session()
        task = session.query(TaskHistory).filter(TaskHistory.task_id == task_id).first()
        if task:
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            session.commit()
            log.debug(f"Updated task {task_id}: {kwargs.get('status', 'unknown')}")
        else:
            log.warning(f"Task {task_id} not found in database for update")
        session.close()
    except Exception as e:
        log.error(f"Error updating task {task_id}: {e}")


@task_prerun.connect
def task_started_handler(task_id=None, task=None, **kwargs):
    """Called when a task starts executing."""
    update_task_status(
        task_id,
        status='started',
        task_name=task.name if task else None,
        started_at=datetime.utcnow()
    )


@task_postrun.connect
def task_completed_handler(task_id=None, task=None, retval=None, state=None, **kwargs):
    """Called when a task completes (success or failure)."""
    status = 'success' if state == 'SUCCESS' else state.lower() if state else 'unknown'

    # Determine status from result if available
    if isinstance(retval, dict) and retval.get('status') == 'failed':
        status = 'failure'

    update_task_status(
        task_id,
        status=status,
        result=retval,
        completed_at=datetime.utcnow()
    )


@task_failure.connect
def task_failed_handler(task_id=None, exception=None, traceback=None, **kwargs):
    """Called when a task fails with an exception."""
    import traceback as tb
    error_msg = str(exception) if exception else 'Unknown error'
    tb_str = ''.join(tb.format_tb(traceback)) if traceback else None

    update_task_status(
        task_id,
        status='failure',
        error=error_msg,
        traceback=tb_str,
        completed_at=datetime.utcnow()
    )


if __name__ == '__main__':
    celery_app.start()
