"""
Service Stack Routes

Stack CRUD and deployment operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.stack_service import StackService
from app.schemas.stacks import StackCreate, StackUpdate

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_stacks(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List all service stacks."""
    service = StackService(session)
    stacks = service.get_all()
    return success_response(data={
        "stacks": stacks,
        "count": len(stacks),
    })


@router.get("/{stack_id}")
async def get_stack(
    stack_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific service stack."""
    service = StackService(session)
    stack = service.get(stack_id)

    if not stack:
        raise HTTPException(status_code=404, detail="Service stack not found")

    return success_response(data={"stack": stack})


@router.post("")
async def create_stack(
    request: StackCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new service stack."""
    service = StackService(session)
    stack_id = service.create(request)

    log.info(f"Stack created: {request.name} by {current_user.sub}")
    return success_response(
        data={"stack_id": stack_id},
        message=f'Service stack "{request.name}" created successfully',
    )


@router.put("/{stack_id}")
async def update_stack(
    stack_id: str,
    request: StackUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a service stack."""
    service = StackService(session)
    existing = service.get(stack_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Service stack not found")

    service.update(stack_id, request)

    log.info(f"Stack updated: {stack_id} by {current_user.sub}")
    return success_response(message=f'Service stack "{existing["name"]}" updated successfully')


@router.delete("/{stack_id}")
async def delete_stack(
    stack_id: str,
    delete_services: bool = Query(False, description="Also delete deployed service instances"),
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a service stack."""
    service = StackService(session)
    stack = service.get(stack_id)

    if not stack:
        raise HTTPException(status_code=404, detail="Service stack not found")

    stack_name = stack["name"]

    if delete_services and stack.get("deployed_services"):
        log.warning(
            f"Delete with services requested for stack {stack_id} - "
            "using basic delete only (deployment cleanup deferred)"
        )

    service.delete(stack_id)

    log.info(f"Stack deleted: {stack_id} by {current_user.sub}")
    return success_response(message=f'Service stack "{stack_name}" deleted successfully')


# Stack Templates (reusable stack definitions)
@router.get("/templates/list")
async def list_stack_templates(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all stack templates."""
    service = StackService(session)
    templates = service.get_all_templates()
    return success_response(data={"templates": templates})


@router.get("/templates/{template_id}")
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


@router.delete("/templates/{template_id}")
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
