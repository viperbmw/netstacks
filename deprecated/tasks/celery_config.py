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
