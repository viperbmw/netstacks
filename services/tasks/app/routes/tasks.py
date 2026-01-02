"""
Task management routes.

Provides endpoints for querying task history from the database.
All task data is stored in DB by Celery signal handlers - no direct Celery queries.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from netstacks_core.db import get_db, TaskHistory

from app.services.celery_client import cancel_task

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/metadata")
async def get_task_metadata(
    session: Session = Depends(get_db),
):
    """
    Get metadata about tasks including device name mappings.

    Returns:
        Dict containing task metadata with device_name for each task_id.
    """
    try:
        history = session.query(TaskHistory).order_by(
            TaskHistory.created_at.desc()
        ).limit(200).all()

        metadata = {}
        for entry in history:
            metadata[entry.task_id] = {
                "device_name": entry.device_name,
                "task_name": entry.task_name,
                "status": entry.status,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "started_at": entry.started_at.isoformat() if entry.started_at else None,
                "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
            }

        return {"metadata": metadata}
    except Exception as e:
        log.error(f"Error getting task metadata: {e}")
        return {"metadata": {}, "error": str(e)}


@router.get("")
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    session: Session = Depends(get_db),
):
    """
    List recent tasks from task history.

    All data comes from the database - no Celery queries.
    """
    try:
        query = session.query(TaskHistory)

        # Filter by status if provided
        if status:
            query = query.filter(TaskHistory.status == status.lower())

        tasks = query.order_by(TaskHistory.created_at.desc()).limit(limit).all()

        return {
            "status": "success",
            "data": {
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "task_name": t.task_name,
                        "device_name": t.device_name,
                        "status": t.status,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "started_at": t.started_at.isoformat() if t.started_at else None,
                        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    }
                    for t in tasks
                ]
            }
        }
    except Exception as e:
        log.error(f"Error listing tasks: {e}")
        return {
            "status": "error",
            "data": {"tasks": []},
            "error": str(e)
        }


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    session: Session = Depends(get_db),
):
    """
    Get status and details of a specific task from the database.

    Args:
        task_id: The task ID

    Returns:
        Task status information including state, result, and any errors
    """
    task = session.query(TaskHistory).filter(TaskHistory.task_id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return {
        "task_id": task.task_id,
        "task_name": task.task_name,
        "device_name": task.device_name,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "traceback": task.traceback,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/{task_id}/result")
async def get_task_result_endpoint(
    task_id: str,
    session: Session = Depends(get_db),
):
    """
    Get the result of a task from the database.

    Args:
        task_id: The task ID

    Returns:
        The task result if available
    """
    task = session.query(TaskHistory).filter(TaskHistory.task_id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status == 'pending':
        return {
            "task_id": task_id,
            "status": "pending",
            "result": None,
            "message": "Task is pending"
        }

    if task.status == 'started':
        return {
            "task_id": task_id,
            "status": "started",
            "result": None,
            "message": "Task is still running"
        }

    if task.status == 'failure':
        return {
            "task_id": task_id,
            "status": "failure",
            "result": task.result,
            "error": task.error,
            "traceback": task.traceback,
        }

    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result
    }


@router.post("/{task_id}/cancel")
async def cancel_task_endpoint(
    task_id: str,
    terminate: bool = Query(False, description="Forcefully terminate if running"),
    session: Session = Depends(get_db),
):
    """
    Cancel a pending or running task.

    Args:
        task_id: The task ID
        terminate: If True, forcefully terminate even if currently running

    Returns:
        Cancellation result
    """
    # Update DB status
    task = session.query(TaskHistory).filter(TaskHistory.task_id == task_id).first()
    if task and task.status in ('pending', 'started'):
        task.status = 'cancelled'
        session.commit()

    # Also tell Celery to cancel (best effort)
    result = cancel_task(task_id, terminate=terminate)

    return {"cancelled": True, "task_id": task_id}
