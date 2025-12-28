"""
Stack Templates Routes

Reusable stack template definitions - separate from service stacks.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.stack_service import StackService

log = logging.getLogger(__name__)

router = APIRouter()


class StackTemplateServiceDef(BaseModel):
    """Service definition within a stack template."""
    template_id: str
    template_name: Optional[str] = None
    order: int = 0


class StackTemplateCreate(BaseModel):
    """Schema for creating a stack template."""
    name: str
    description: Optional[str] = None
    services: List[Dict[str, Any]] = []
    api_variables: Dict[str, Any] = {}
    per_device_variables: List[str] = []


class StackTemplateUpdate(BaseModel):
    """Schema for updating a stack template."""
    name: Optional[str] = None
    description: Optional[str] = None
    services: Optional[List[Dict[str, Any]]] = None
    api_variables: Optional[Dict[str, Any]] = None
    per_device_variables: Optional[List[str]] = None


@router.get("")
async def list_stack_templates(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all stack templates."""
    service = StackService(session)
    templates = service.get_all_templates()
    return success_response(data={"templates": templates, "count": len(templates)})


@router.get("/{template_id}")
async def get_stack_template(
    template_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific stack template."""
    service = StackService(session)
    template = service.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Stack template not found")

    return success_response(data={"template": template})


@router.post("")
async def create_stack_template(
    request: StackTemplateCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new stack template."""
    service = StackService(session)

    # Check for duplicate name
    existing = service.get_template_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f'Stack template "{request.name}" already exists')

    template_id = service.create_template(
        name=request.name,
        description=request.description,
        services=request.services,
        api_variables=request.api_variables,
        per_device_variables=request.per_device_variables,
    )

    log.info(f"Stack template created: {request.name} by {current_user.sub}")
    return success_response(
        data={"template_id": template_id},
        message=f'Stack template "{request.name}" created successfully',
    )


@router.put("/{template_id}")
async def update_stack_template(
    template_id: str,
    request: StackTemplateUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a stack template."""
    service = StackService(session)
    existing = service.get_template(template_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Stack template not found")

    service.update_template(template_id, request.model_dump(exclude_none=True))

    log.info(f"Stack template updated: {template_id} by {current_user.sub}")
    return success_response(message=f'Stack template "{existing["name"]}" updated successfully')


@router.delete("/{template_id}")
async def delete_stack_template(
    template_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a stack template."""
    service = StackService(session)
    template = service.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Stack template not found")

    service.delete_template(template_id)

    log.info(f"Stack template deleted: {template_id} by {current_user.sub}")
    return success_response(message=f'Stack template "{template["name"]}" deleted successfully')
