"""
Worker management routes.

Provides endpoints for monitoring Celery workers and queues.
"""

from fastapi import APIRouter, HTTPException

from app.services.celery_client import (
    get_active_workers,
    get_worker_stats,
    get_queues,
    get_registered_tasks,
)

router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("")
async def list_workers():
    """
    Get information about active Celery workers.

    Returns:
        Dict containing worker information including:
        - workers: Dict of worker details keyed by worker name
        - worker_count: Total number of active workers
        - total_active_tasks: Sum of tasks currently being processed
    """
    workers_info = get_active_workers()

    if 'error' in workers_info and workers_info.get('worker_count', 0) == 0:
        # No workers and there's an error - likely connection issue
        raise HTTPException(
            status_code=503,
            detail=f"Unable to connect to workers: {workers_info['error']}"
        )

    return workers_info


@router.get("/stats")
async def get_workers_stats():
    """
    Get aggregate statistics for all workers.

    Returns:
        Dict containing:
        - worker_count: Number of active workers
        - workers: List of worker names
        - total_tasks_completed: Total tasks completed across all workers
        - raw_stats: Detailed statistics per worker
    """
    stats = get_worker_stats()

    if 'error' in stats and stats.get('worker_count', 0) == 0:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to get worker stats: {stats['error']}"
        )

    return stats


@router.get("/tasks")
async def get_worker_tasks():
    """
    Get list of tasks registered with Celery workers.

    Returns:
        Dict containing registered task names and their metadata
    """
    tasks_info = get_registered_tasks()

    if 'error' in tasks_info and tasks_info.get('task_count', 0) == 0:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to get registered tasks: {tasks_info['error']}"
        )

    return tasks_info


@router.get("/queues")
async def list_queues():
    """
    Get information about Celery queues.

    Returns:
        Dict containing:
        - queues: List of queue information including workers consuming each queue
        - queue_count: Total number of active queues
    """
    queues_info = get_queues()

    if 'error' in queues_info and queues_info.get('queue_count', 0) == 0:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to get queue info: {queues_info['error']}"
        )

    return queues_info


@router.get("/{worker_name}")
async def get_worker_detail(worker_name: str):
    """
    Get detailed information about a specific worker.

    Args:
        worker_name: The worker name (e.g., 'celery@worker1')

    Returns:
        Worker details including active tasks, registered tasks, and stats
    """
    workers_info = get_active_workers()

    if 'error' in workers_info:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to connect to workers: {workers_info['error']}"
        )

    workers = workers_info.get('workers', {})

    if worker_name not in workers:
        raise HTTPException(
            status_code=404,
            detail=f"Worker '{worker_name}' not found"
        )

    return {
        "name": worker_name,
        **workers[worker_name]
    }
