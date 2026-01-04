"""
Step Types Routes

MOP step type management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.step_type_service import StepTypeService
from app.schemas.step_types import StepTypeCreate, StepTypeUpdate

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_step_types(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all step types."""
    service = StepTypeService(session)
    step_types = service.get_all()
    return success_response(data={
        "step_types": step_types,
        "count": len(step_types),
    })


@router.get("/{step_type_id}")
async def get_step_type(
    step_type_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific step type."""
    service = StepTypeService(session)
    step_type = service.get(step_type_id)

    if not step_type:
        raise HTTPException(status_code=404, detail="Step type not found")

    return success_response(data={"step_type": step_type})


@router.post("")
async def create_step_type(
    request: StepTypeCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new step type."""
    # Validate action type
    valid_action_types = [
        'get_config', 'set_config', 'api_call', 'validate',
        'wait', 'manual', 'deploy_stack', 'agent'
    ]
    if request.action_type not in valid_action_types:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid action type. Must be one of: {valid_action_types}'
        )

    # For api_call types, validate URL is provided
    if request.action_type == 'api_call':
        config = request.config or {}
        if not config.get('url'):
            raise HTTPException(
                status_code=400,
                detail='URL is required for API Call step types'
            )

    # For agent types, validate prompt is provided
    if request.action_type == 'agent':
        config = request.config or {}
        if not config.get('prompt'):
            raise HTTPException(
                status_code=400,
                detail='Prompt is required for AI Agent step types'
            )

    service = StepTypeService(session)
    step_type_id = service.create(request)

    log.info(f"Step type created: {request.name} by {current_user.sub}")
    return success_response(data={"step_type_id": step_type_id})


@router.put("/{step_type_id}")
async def update_step_type(
    step_type_id: str,
    request: StepTypeUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a step type."""
    service = StepTypeService(session)
    existing = service.get(step_type_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Step type not found")

    service.update(step_type_id, request)

    log.info(f"Step type updated: {step_type_id} by {current_user.sub}")
    return success_response()


@router.delete("/{step_type_id}")
async def delete_step_type(
    step_type_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a step type."""
    service = StepTypeService(session)
    existing = service.get(step_type_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Step type not found")

    # Don't allow deleting built-in types
    if existing.get('is_builtin'):
        raise HTTPException(
            status_code=400,
            detail='Cannot delete built-in step types'
        )

    service.delete(step_type_id)

    log.info(f"Step type deleted: {step_type_id} by {current_user.sub}")
    return success_response()


@router.post("/{step_type_id}/toggle")
async def toggle_step_type(
    step_type_id: str,
    enabled: bool = True,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Enable or disable a step type."""
    service = StepTypeService(session)
    existing = service.get(step_type_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Step type not found")

    service.toggle(step_type_id, enabled)

    log.info(f"Step type {'enabled' if enabled else 'disabled'}: {step_type_id} by {current_user.sub}")
    return success_response()
