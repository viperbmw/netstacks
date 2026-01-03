"""
Service Stack Routes

Stack CRUD and deployment operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    request: Request,
    delete_services: bool = Query(False, description="Also delete deployed service instances"),
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a service stack and optionally run delete templates on deployed services."""
    import httpx

    service = StackService(session)
    stack = service.get(stack_id)

    if not stack:
        raise HTTPException(status_code=404, detail="Service stack not found")

    stack_name = stack["name"]
    deployed_services = stack.get("deployed_services", [])
    deleted_count = 0
    delete_errors = []

    # If delete_services is true, call the service delete endpoint for each deployed service
    if delete_services and deployed_services:
        auth_header = request.headers.get("Authorization")
        tasks_url = "http://tasks:8006"

        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        log.info(f"Deleting {len(deployed_services)} services from stack {stack_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            for service_id in deployed_services:
                try:
                    response = await client.post(
                        f"{tasks_url}/api/services/instances/{service_id}/delete",
                        headers=headers,
                        json={}  # Empty body for ServiceOperationRequest
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success"):
                            deleted_count += 1
                            log.info(f"Deleted service instance {service_id}")
                        else:
                            error_msg = result.get("message", "Unknown error")
                            delete_errors.append({"service_id": service_id, "error": error_msg})
                            log.warning(f"Failed to delete service {service_id}: {error_msg}")
                    elif response.status_code == 404:
                        # Service already deleted, just count it as successful
                        deleted_count += 1
                        log.info(f"Service instance {service_id} already deleted")
                    else:
                        try:
                            error_detail = response.json().get("detail", response.text)
                        except Exception:
                            error_detail = response.text
                        delete_errors.append({"service_id": service_id, "error": error_detail})
                        log.warning(f"Failed to delete service {service_id}: {error_detail}")

                except Exception as e:
                    delete_errors.append({"service_id": service_id, "error": str(e)})
                    log.error(f"Error deleting service {service_id}: {e}")

    # Delete the stack itself
    service.delete(stack_id)

    log.info(f"Stack deleted: {stack_id} by {current_user.sub}")

    # Build response message
    if delete_services and deployed_services:
        if delete_errors:
            message = f'Service stack "{stack_name}" deleted. {deleted_count}/{len(deployed_services)} services removed. {len(delete_errors)} errors.'
        else:
            message = f'Service stack "{stack_name}" and all {deleted_count} services deleted successfully'
    else:
        message = f'Service stack "{stack_name}" deleted successfully'

    return success_response(
        message=message,
        data={
            "deleted_services": deleted_count,
            "errors": delete_errors if delete_errors else None
        }
    )


@router.post("/{stack_id}/validate")
async def validate_stack(
    stack_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Validate all services in a stack."""
    from datetime import datetime

    service = StackService(session)
    stack = service.get(stack_id)

    if not stack:
        raise HTTPException(status_code=404, detail="Service stack not found")

    deployed_services = stack.get("deployed_services", [])
    if not deployed_services:
        raise HTTPException(status_code=400, detail="Stack has no deployed services to validate")

    # Update stack validation status
    service.update_validation_status(stack_id, "validating")

    validation_results = []
    all_valid = True

    log.info(f"Validating stack '{stack_id}' with {len(deployed_services)} services")

    # For now, mark validation as pending - actual validation happens via Celery tasks
    # The frontend will call individual service validate endpoints
    service.update_validation_status(stack_id, "pending", datetime.utcnow())

    return success_response(
        data={
            "stack_id": stack_id,
            "status": "pending",
            "services_to_validate": len(deployed_services),
            "message": "Stack validation initiated. Individual services will be validated.",
        }
    )


@router.post("/{stack_id}/deploy")
async def deploy_stack(
    stack_id: str,
    request: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Deploy all services in a stack by creating ServiceInstance records."""
    import httpx
    from datetime import datetime

    service = StackService(session)
    stack = service.get(stack_id)

    if not stack:
        raise HTTPException(status_code=404, detail="Service stack not found")

    if stack.get("state") == "deploying":
        raise HTTPException(status_code=400, detail="Stack is already being deployed")

    # Update stack to deploying state
    service.update_state(stack_id, "deploying", datetime.utcnow())

    services = sorted(stack.get("services", []), key=lambda s: s.get("order", 0))
    shared_variables = stack.get("shared_variables", {})

    log.info(f"Deploying stack '{stack_id}' with {len(services)} services")

    # Get auth header to forward to tasks service
    auth_header = request.headers.get("Authorization")

    deployed_services = []
    failed_services = []

    # Deploy each service by calling the services API (which creates ServiceInstance records)
    for idx, service_def in enumerate(services):
        try:
            template_name = service_def.get("template")
            device_name = service_def.get("device")
            service_name = service_def.get("name")

            if not template_name or not device_name:
                failed_services.append({
                    "name": service_name,
                    "error": "Missing template or device"
                })
                continue

            # Strip .j2 extension if present
            if template_name.endswith('.j2'):
                template_name = template_name[:-3]

            # Merge shared variables with service-specific variables
            variables = {**shared_variables, **service_def.get("variables", {})}

            # Call tasks service to create service instance (this creates proper ServiceInstance records)
            tasks_url = "http://tasks:8006/api/services/instances/create"
            headers = {"Content-Type": "application/json"}
            if auth_header:
                headers["Authorization"] = auth_header

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    tasks_url,
                    headers=headers,
                    json={
                        "name": service_name,
                        "template": template_name,
                        "device": device_name,
                        "variables": variables,
                        "stack_id": stack_id,
                        "stack_order": idx
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        service_id = result.get("data", {}).get("service_id")
                        task_id = result.get("data", {}).get("task_id")
                        deployed_services.append({
                            "service_id": service_id,
                            "service_name": service_name,
                            "device": device_name,
                            "template": template_name,
                            "task_id": task_id
                        })
                        log.info(f"Created service instance '{service_name}' ({service_id}) for device {device_name}")
                    else:
                        error_detail = result.get("message", "Unknown error")
                        failed_services.append({
                            "name": service_name,
                            "error": f"Deploy failed: {error_detail}"
                        })
                else:
                    try:
                        error_detail = response.json().get("detail", response.text)
                    except Exception:
                        error_detail = response.text
                    failed_services.append({
                        "name": service_name,
                        "error": f"Deploy failed: {error_detail}"
                    })

        except Exception as e:
            log.error(f"Error deploying service {service_def.get('name')}: {e}")
            failed_services.append({
                "name": service_def.get("name"),
                "error": str(e)
            })

    # Update stack state based on results
    if failed_services and not deployed_services:
        service.update_state(stack_id, "failed")
    elif failed_services:
        service.update_state(stack_id, "partial")
    else:
        service.update_state(stack_id, "deployed")

    # Store deployed service instance IDs in the stack (not task IDs!)
    if deployed_services:
        service.update_deployed_services(stack_id, [s["service_id"] for s in deployed_services])

    # Also store any deployment errors for display
    if failed_services:
        service.update_deployment_errors(stack_id, failed_services)

    return success_response(
        data={
            "stack_id": stack_id,
            "status": "deployed" if not failed_services else ("partial" if deployed_services else "failed"),
            "deployed_services": deployed_services,
            "failed_services": failed_services,
            "message": f"Deployed {len(deployed_services)} services, {len(failed_services)} failed.",
        }
    )


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
