"""
Template Routes

Template CRUD and rendering operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.template_service import TemplateService
from app.schemas.templates import (
    TemplateCreate,
    TemplateUpdate,
    TemplateRenderRequest,
)

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_templates(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List all templates."""
    service = TemplateService(session)
    templates = service.get_all()
    return success_response(data={
        "templates": templates,
        "count": len(templates),
    })


@router.get("/{template_name}")
async def get_template(
    template_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get template by name."""
    # Strip .j2 extension if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    service = TemplateService(session)
    template = service.get(template_name)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return success_response(data=template)


@router.post("")
async def create_template(
    request: TemplateCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new template."""
    service = TemplateService(session)

    # Strip .j2 extension if present
    name = request.name
    if name.endswith('.j2'):
        name = name[:-3]

    template = service.create(
        name=name,
        content=request.content,
        template_type=request.type,
        description=request.description,
        validation_template=request.validation_template,
        delete_template=request.delete_template,
    )

    log.info(f"Template created: {name} by {current_user.sub}")
    return success_response(
        data={"name": name},
        message=f"Template {name} saved",
    )


@router.put("/{template_name}")
async def update_template(
    template_name: str,
    request: TemplateUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update an existing template."""
    # Strip .j2 extension if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    service = TemplateService(session)
    existing = service.get(template_name)

    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    service.update(template_name, request)

    log.info(f"Template updated: {template_name} by {current_user.sub}")
    return success_response(message=f"Template {template_name} updated")


@router.delete("/{template_name}")
async def delete_template(
    template_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a template."""
    # Strip .j2 extension if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    service = TemplateService(session)

    if not service.delete(template_name):
        raise HTTPException(status_code=404, detail="Template not found")

    log.info(f"Template deleted: {template_name} by {current_user.sub}")
    return success_response(message=f"Template {template_name} deleted")


@router.post("/{template_name}/render")
async def render_template(
    template_name: str,
    request: Optional[TemplateRenderRequest] = None,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Render a template with variables (dry run)."""
    # Strip .j2 extension if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    service = TemplateService(session)
    variables = request.variables if request else {}

    result = service.render(template_name, variables)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return success_response(data={"rendered": result["rendered"]})
