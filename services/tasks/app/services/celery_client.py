"""
Celery Client for Tasks Service

Provides Celery app connection and task management functions.
"""

import logging
from typing import Optional, Dict, Any, List

from celery import Celery
from celery.result import AsyncResult

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Create Celery app (for inspection only, not for running workers)
celery_app = Celery(
    'netstacks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configure to match worker configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a Celery task.

    Returns:
        Dict with task status information
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        status_info = {
            'task_id': task_id,
            'status': result.status,
            'ready': result.ready(),
            'successful': result.successful() if result.ready() else None,
            'failed': result.failed() if result.ready() else None,
        }

        # Get result if successful
        if result.successful():
            try:
                status_info['result'] = result.result
            except Exception as e:
                log.warning(f"Could not get result for task {task_id}: {e}")
                status_info['result'] = None

        # Get error info if failed
        if result.failed():
            try:
                status_info['error'] = str(result.result)
                status_info['traceback'] = result.traceback
            except Exception as e:
                log.warning(f"Could not get error for task {task_id}: {e}")
                status_info['error'] = 'Unknown error'

        # Get progress info if available
        if result.status == 'PROGRESS':
            try:
                status_info['progress'] = result.info
            except Exception:
                pass

        return status_info

    except Exception as e:
        log.error(f"Error getting task status for {task_id}: {e}")
        return {
            'task_id': task_id,
            'status': 'UNKNOWN',
            'error': str(e)
        }


def get_task_result(task_id: str) -> Optional[Any]:
    """
    Get the result of a completed Celery task.

    Returns:
        The task result, or None if not ready/failed
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        if result.successful():
            return result.result
        return None

    except Exception as e:
        log.error(f"Error getting task result for {task_id}: {e}")
        return None


def cancel_task(task_id: str, terminate: bool = False) -> Dict[str, Any]:
    """
    Cancel a Celery task.

    Args:
        task_id: The task ID to cancel
        terminate: If True, terminate the task even if running

    Returns:
        Dict with cancellation result
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        # Revoke the task
        celery_app.control.revoke(task_id, terminate=terminate)

        return {
            'task_id': task_id,
            'cancelled': True,
            'terminated': terminate,
            'previous_status': result.status
        }

    except Exception as e:
        log.error(f"Error cancelling task {task_id}: {e}")
        return {
            'task_id': task_id,
            'cancelled': False,
            'error': str(e)
        }


def get_active_workers() -> Dict[str, Any]:
    """
    Get information about active Celery workers.

    Returns:
        Dict with worker information
    """
    try:
        # Use short timeout (1 second) to avoid blocking
        inspect = celery_app.control.inspect(timeout=1.0)

        # Only get active tasks - skip the slow calls
        active = inspect.active() or {}

        workers = {}
        for worker_name in active.keys():
            workers[worker_name] = {
                'active_tasks': active.get(worker_name, []),
                'active_count': len(active.get(worker_name, [])),
            }

        return {
            'workers': workers,
            'worker_count': len(workers),
            'total_active_tasks': sum(w['active_count'] for w in workers.values())
        }

    except Exception as e:
        log.error(f"Error getting worker info: {e}")
        return {
            'workers': {},
            'worker_count': 0,
            'total_active_tasks': 0,
            'error': str(e)
        }


def get_worker_stats() -> Dict[str, Any]:
    """
    Get aggregate statistics for all workers.

    Returns:
        Dict with aggregate stats
    """
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats() or {}

        total_tasks_completed = 0
        total_tasks_failed = 0

        for worker_name, worker_stats in stats.items():
            total = worker_stats.get('total', {})
            for task_name, task_stats in total.items():
                # task_stats is typically a count
                if isinstance(task_stats, (int, float)):
                    total_tasks_completed += int(task_stats)

        return {
            'worker_count': len(stats),
            'workers': list(stats.keys()),
            'total_tasks_completed': total_tasks_completed,
            'raw_stats': stats
        }

    except Exception as e:
        log.error(f"Error getting worker stats: {e}")
        return {
            'worker_count': 0,
            'workers': [],
            'total_tasks_completed': 0,
            'error': str(e)
        }


def get_registered_tasks() -> Dict[str, Any]:
    """
    Get list of registered Celery tasks.

    Returns:
        Dict with registered task names
    """
    try:
        inspect = celery_app.control.inspect()
        registered = inspect.registered() or {}

        # Collect unique task names from all workers
        all_tasks = set()
        for worker_tasks in registered.values():
            all_tasks.update(worker_tasks)

        return {
            'tasks': sorted(list(all_tasks)),
            'task_count': len(all_tasks),
            'per_worker': registered
        }

    except Exception as e:
        log.error(f"Error getting registered tasks: {e}")
        return {
            'tasks': [],
            'task_count': 0,
            'error': str(e)
        }


def get_queues() -> Dict[str, Any]:
    """
    Get information about Celery queues.

    Returns:
        Dict with queue information
    """
    try:
        inspect = celery_app.control.inspect()
        active_queues = inspect.active_queues() or {}

        queues = {}
        for worker_name, worker_queues in active_queues.items():
            for queue in worker_queues:
                queue_name = queue.get('name', 'unknown')
                if queue_name not in queues:
                    queues[queue_name] = {
                        'name': queue_name,
                        'workers': [],
                        'routing_key': queue.get('routing_key'),
                    }
                queues[queue_name]['workers'].append(worker_name)

        return {
            'queues': list(queues.values()),
            'queue_count': len(queues)
        }

    except Exception as e:
        log.error(f"Error getting queue info: {e}")
        return {
            'queues': [],
            'queue_count': 0,
            'error': str(e)
        }
