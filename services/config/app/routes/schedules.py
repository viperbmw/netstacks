"""
Scheduled Operations Routes

Scheduled stack operations management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.schedule_service import ScheduleService
from app.schemas.schedules import ScheduleCreate, ScheduleUpdate

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_scheduled_operations(
    stack_id: Optional[str] = Query(None, description="Filter by stack ID"),
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get scheduled operations."""
    service = ScheduleService(session)
    schedules = service.get_all(stack_id=stack_id)
    return success_response(data={
        "schedules": schedules,
        "count": len(schedules),
    })


@router.get("/{schedule_id}")
async def get_scheduled_operation(
    schedule_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific scheduled operation."""
    service = ScheduleService(session)
    schedule = service.get(schedule_id)

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return success_response(data={"schedule": schedule})


@router.post("")
async def create_scheduled_operation(
    request: ScheduleCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new scheduled stack operation."""
    service = ScheduleService(session)
    schedule_id = service.create(request, created_by=current_user.sub)

    log.info(f"Schedule created: {schedule_id} by {current_user.sub}")
    return success_response(data={"schedule_id": schedule_id})


@router.put("/{schedule_id}")
@router.patch("/{schedule_id}")
async def update_scheduled_operation(
    schedule_id: str,
    request: ScheduleUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a scheduled operation."""
    service = ScheduleService(session)
    existing = service.get(schedule_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")

    service.update(schedule_id, request)

    log.info(f"Schedule updated: {schedule_id} by {current_user.sub}")
    return success_response()


@router.delete("/{schedule_id}")
async def delete_scheduled_operation(
    schedule_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a scheduled operation."""
    service = ScheduleService(session)

    if not service.delete(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")

    log.info(f"Schedule deleted: {schedule_id} by {current_user.sub}")
    return success_response()


@router.patch("/{schedule_id}/toggle")
async def toggle_scheduled_operation(
    schedule_id: str,
    enabled: bool = True,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Enable or disable a scheduled operation."""
    service = ScheduleService(session)
    existing = service.get(schedule_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")

    service.toggle(schedule_id, enabled)

    log.info(f"Schedule {'enabled' if enabled else 'disabled'}: {schedule_id} by {current_user.sub}")
    return success_response()
