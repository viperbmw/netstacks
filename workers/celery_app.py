"""
Celery Application Configuration for NetStacks Workers

This is the main Celery application that orchestrates all background tasks
for network automation, backups, and scheduled operations.
"""

import os
import logging
from celery import Celery
from celery.schedules import crontab

log = logging.getLogger(__name__)

# Celery configuration from environment
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

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


if __name__ == '__main__':
    celery_app.start()
