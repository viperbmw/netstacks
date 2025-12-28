"""
MOP (Method of Procedures) Routes

MOP CRUD and execution history.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.mop_service import MOPService
from app.schemas.mops import MOPCreate, MOPUpdate

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_mops(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all MOPs (workflows)."""
    service = MOPService(session)
    mops = service.get_all()
    return success_response(data={
        "mops": mops,
        "count": len(mops),
    })


@router.get("/{mop_id}")
async def get_mop(
    mop_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific MOP."""
    service = MOPService(session)
    mop = service.get(mop_id)

    if not mop:
        raise HTTPException(status_code=404, detail="MOP not found")

    return success_response(data={"mop": mop})


@router.post("")
async def create_mop(
    request: MOPCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new MOP (workflow)."""
    service = MOPService(session)
    mop_id = service.create(request, created_by=current_user.sub)

    log.info(f"MOP created: {request.name} by {current_user.sub}")
    return success_response(data={"mop_id": mop_id})


@router.put("/{mop_id}")
async def update_mop(
    mop_id: str,
    request: MOPUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a MOP."""
    service = MOPService(session)
    existing = service.get(mop_id)

    if not existing:
        raise HTTPException(status_code=404, detail="MOP not found")

    service.update(mop_id, request)

    log.info(f"MOP updated: {mop_id} by {current_user.sub}")
    return success_response()


@router.delete("/{mop_id}")
async def delete_mop(
    mop_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a MOP."""
    service = MOPService(session)

    if not service.delete(mop_id):
        raise HTTPException(status_code=404, detail="MOP not found")

    log.info(f"MOP deleted: {mop_id} by {current_user.sub}")
    return success_response()


@router.patch("/{mop_id}/toggle")
async def toggle_mop(
    mop_id: str,
    enabled: bool = True,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Enable or disable a MOP."""
    service = MOPService(session)
    existing = service.get(mop_id)

    if not existing:
        raise HTTPException(status_code=404, detail="MOP not found")

    service.toggle(mop_id, enabled)

    log.info(f"MOP {'enabled' if enabled else 'disabled'}: {mop_id} by {current_user.sub}")
    return success_response()


# Execution history
@router.get("/{mop_id}/executions")
async def get_mop_executions(
    mop_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get executions for a specific MOP."""
    service = MOPService(session)
    executions = service.get_executions(mop_id)
    return success_response(data={
        "executions": executions,
        "count": len(executions),
    })


@router.get("/executions/{execution_id}")
async def get_mop_execution(
    execution_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific MOP execution."""
    service = MOPService(session)
    execution = service.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return success_response(data={"execution": execution})


@router.get("/executions/running/list")
async def get_running_executions(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all running MOP executions."""
    service = MOPService(session)
    executions = service.get_running_executions()
    return success_response(data={
        "executions": executions,
        "count": len(executions),
    })
