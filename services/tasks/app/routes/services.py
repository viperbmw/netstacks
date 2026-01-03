"""
Services Routes

Service instance operations - deployment, validation, state management.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from celery.result import AsyncResult
import httpx

from netstacks_core.db import get_db, ServiceInstance, ServiceStack, TaskHistory
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.config import get_settings
from app.services.celery_client import celery_app
from .deploy import get_device_connection_info, submit_celery_task, record_task

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/services")


# Pydantic models
class ServiceCreateRequest(BaseModel):
    name: str
    template: str
    device: str
    variables: Dict[str, Any] = {}
    reverse_template: Optional[str] = None
    validation_template: Optional[str] = None
    delete_template: Optional[str] = None
    stack_id: Optional[str] = None
    stack_order: int = 0
    username: Optional[str] = None
    password: Optional[str] = None


class ServiceOperationRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    use_backup: bool = True


# Helper functions
async def get_template_content(
    template_name: str,
    variables: Dict[str, Any],
    auth_header: Optional[str] = None
) -> Optional[str]:
    """Fetch and render a template from the config service."""
    config_url = settings.CONFIG_SERVICE_URL

    # Strip .j2 if present
    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Render template
            response = await client.post(
                f"{config_url}/api/templates/{template_name}/render",
                headers=headers,
                json={"variables": variables}
            )

            if response.status_code != 200:
                log.error(f"Failed to render template {template_name}: {response.status_code}")
                return None

            data = response.json()
            if data.get("success"):
                return data.get("data", {}).get("rendered")
            return None

        except httpx.RequestError as e:
            log.error(f"Error connecting to config service: {e}")
            return None


async def get_template_metadata(
    template_name: str,
    auth_header: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch template metadata from the config service."""
    config_url = settings.CONFIG_SERVICE_URL

    if template_name.endswith('.j2'):
        template_name = template_name[:-3]

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{config_url}/api/templates/{template_name}",
                headers=headers
            )

            if response.status_code != 200:
                return {}

            data = response.json()
            if data.get("success"):
                return data.get("data", {})
            return {}

        except httpx.RequestError as e:
            log.error(f"Error fetching template metadata: {e}")
            return {}


async def get_device_backup(
    device_name: str,
    auth_header: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get latest backup for a device from the devices service."""
    devices_url = settings.DEVICES_SERVICE_URL

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{devices_url}/api/backups/{device_name}/latest",
                headers=headers
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if data.get("success"):
                return data.get("data", {}).get("backup")
            return None

        except httpx.RequestError as e:
            log.error(f"Error fetching device backup: {e}")
            return None


def service_to_dict(service: ServiceInstance) -> Dict[str, Any]:
    """Convert ServiceInstance model to dict."""
    return {
        'service_id': service.service_id,
        'name': service.name,
        'template': service.template,
        'validation_template': service.validation_template,
        'delete_template': service.delete_template,
        'device': service.device,
        'variables': service.variables or {},
        'rendered_config': service.rendered_config,
        'state': service.state,
        'error': service.error,
        'task_id': service.task_id,
        'stack_id': service.stack_id,
        'stack_order': service.stack_order,
        'created_at': service.created_at.isoformat() if service.created_at else None,
        'deployed_at': service.deployed_at.isoformat() if service.deployed_at else None,
        'last_validated': service.last_validated.isoformat() if service.last_validated else None,
        'validation_status': service.validation_status,
        'validation_errors': service.validation_errors or [],
    }


# Routes
@router.get("/instances")
async def list_service_instances(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List all service instances."""
    instances = session.query(ServiceInstance).order_by(
        ServiceInstance.created_at.desc()
    ).all()

    return success_response(data={
        "instances": [service_to_dict(s) for s in instances],
        "count": len(instances)
    })


@router.get("/instances/{service_id}")
async def get_service_instance(
    service_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific service instance."""
    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service instance not found")

    return success_response(data={"instance": service_to_dict(service)})


@router.post("/instances/create")
async def create_service_instance(
    request: ServiceCreateRequest,
    req: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new service instance and deploy to device."""
    auth_header = req.headers.get("Authorization")

    # Get template metadata
    template_metadata = await get_template_metadata(request.template, auth_header)

    # Render the template
    rendered_config = await get_template_content(
        request.template,
        request.variables,
        auth_header
    )

    if not rendered_config:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to render template: {request.template}"
        )

    # Get device connection info
    credential_override = None
    if request.username and request.password:
        credential_override = {
            "username": request.username,
            "password": request.password
        }

    device_info = await get_device_connection_info(
        request.device,
        credential_override,
        auth_header
    )

    if not device_info:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get connection info for device: {request.device}"
        )

    # Submit Celery task to push config
    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    task_id = submit_celery_task(
        "tasks.device_tasks.set_config",
        connection_args=clean_args,
        config_lines=rendered_config.split('\n'),
        save_config=True
    )

    # Record task
    record_task(session, task_id, request.device, "service_deploy", action_type="deploy")

    # Create service instance
    service_id = str(uuid.uuid4())
    service = ServiceInstance(
        service_id=service_id,
        name=request.name,
        template=request.template,
        validation_template=request.validation_template or template_metadata.get('validation_template'),
        delete_template=request.delete_template or request.reverse_template or template_metadata.get('delete_template'),
        device=request.device,
        variables=request.variables,
        rendered_config=rendered_config,
        state='deploying',
        task_id=task_id,
        stack_id=request.stack_id,
        stack_order=request.stack_order,
    )

    session.add(service)
    session.commit()

    log.info(f"Service instance created: {request.name} ({service_id})")

    return success_response(
        data={
            "service_id": service_id,
            "task_id": task_id
        },
        message=f'Service "{request.name}" created and deploying to {request.device}'
    )


@router.post("/instances/{service_id}/healthcheck")
async def healthcheck_service(
    service_id: str,
    request_body: ServiceOperationRequest,
    req: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Health check a service instance by validating config on device."""
    auth_header = req.headers.get("Authorization")

    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if not service.rendered_config:
        raise HTTPException(status_code=400, detail="No rendered config to validate")

    # Get device connection info
    credential_override = None
    if request_body.username and request_body.password:
        credential_override = {
            "username": request_body.username,
            "password": request_body.password
        }

    device_info = await get_device_connection_info(
        service.device,
        credential_override,
        auth_header
    )

    if not device_info:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get connection info for device: {service.device}"
        )

    # Extract patterns from rendered config
    patterns = [line.strip() for line in service.rendered_config.split('\n')[:5] if line.strip()]

    # Submit validation task
    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    task_id = submit_celery_task(
        "tasks.device_tasks.validate_config",
        connection_args=clean_args,
        expected_patterns=patterns,
        validation_command='show running-config'
    )

    record_task(session, task_id, service.device, "service_healthcheck", action_type="healthcheck")

    return success_response(data={"task_id": task_id})


@router.post("/instances/{service_id}/redeploy")
async def redeploy_service(
    service_id: str,
    request_body: ServiceOperationRequest,
    req: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Redeploy a service instance using stored configuration."""
    auth_header = req.headers.get("Authorization")

    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if not service.template:
        raise HTTPException(status_code=400, detail="Service has no template to redeploy")

    # Re-render template
    rendered_config = await get_template_content(
        service.template,
        service.variables or {},
        auth_header
    )

    if not rendered_config:
        raise HTTPException(status_code=500, detail="Failed to render template")

    # Get device connection info
    credential_override = None
    if request_body.username and request_body.password:
        credential_override = {
            "username": request_body.username,
            "password": request_body.password
        }

    device_info = await get_device_connection_info(
        service.device,
        credential_override,
        auth_header
    )

    if not device_info:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get connection info for device: {service.device}"
        )

    # Submit Celery task
    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    task_id = submit_celery_task(
        "tasks.device_tasks.set_config",
        connection_args=clean_args,
        config_lines=rendered_config.split('\n'),
        save_config=True
    )

    record_task(session, task_id, service.device, "service_redeploy", action_type="deploy")

    # Update service state
    service.state = 'deploying'
    service.task_id = task_id
    service.rendered_config = rendered_config
    service.error = None
    session.commit()

    log.info(f"Service {service_id} redeploy submitted: {task_id}")

    return success_response(
        data={"task_id": task_id},
        message=f'Service redeploy submitted. Task ID: {task_id}'
    )


@router.post("/instances/{service_id}/delete")
async def delete_service(
    service_id: str,
    request_body: ServiceOperationRequest,
    req: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a service instance - removes config from device first if delete template exists."""
    auth_header = req.headers.get("Authorization")

    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    task_id = None
    delete_template = service.delete_template

    # If delete template exists, use it to remove config from device
    if delete_template and service.device:
        log.info(f"Using delete template '{delete_template}' to remove service from device")

        credential_override = None
        if request_body.username and request_body.password:
            credential_override = {
                "username": request_body.username,
                "password": request_body.password
            }

        device_info = await get_device_connection_info(
            service.device,
            credential_override,
            auth_header
        )

        if device_info:
            # Render delete template
            rendered_config = await get_template_content(
                delete_template,
                service.variables or {},
                auth_header
            )

            if rendered_config:
                connection_args = device_info["connection_args"]
                clean_args = {k: v for k, v in connection_args.items() if v is not None}

                task_id = submit_celery_task(
                    "tasks.device_tasks.set_config",
                    connection_args=clean_args,
                    config_lines=rendered_config.split('\n'),
                    save_config=True
                )

                record_task(session, task_id, service.device, "service_delete", action_type="delete")

    # Remove service from stack if applicable
    stack_id = service.stack_id
    if stack_id:
        stack = session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if stack and stack.deployed_services:
            deployed_services = list(stack.deployed_services)
            if service_id in deployed_services:
                deployed_services.remove(service_id)
                stack.deployed_services = deployed_services

    service_name = service.name

    # Delete the service instance
    session.delete(service)
    session.commit()

    log.info(f"Service {service_id} deleted")

    return success_response(
        data={
            "task_id": task_id,
            "stack_id": stack_id
        },
        message=f'Service "{service_name}" deleted successfully'
    )


@router.post("/instances/{service_id}/check_status")
async def check_service_status(
    service_id: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Check task status and update service state."""
    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if not service.task_id:
        raise HTTPException(status_code=400, detail="No task ID found")

    # Check task status via Celery
    result = AsyncResult(service.task_id, app=celery_app)
    task_status = result.status

    # Update service state based on task status
    if result.successful():
        service.state = 'deployed'
        service.deployed_at = datetime.utcnow()
    elif result.failed():
        service.state = 'failed'
        service.error = str(result.result) if result.result else 'Task failed'

    session.commit()

    return success_response(data={
        "state": service.state,
        "task_status": task_status
    })


@router.post("/instances/{service_id}/validate")
async def validate_service(
    service_id: str,
    request_body: ServiceOperationRequest,
    req: Request,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Validate that the service configuration exists on the device."""
    auth_header = req.headers.get("Authorization")

    service = session.query(ServiceInstance).filter(
        ServiceInstance.service_id == service_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if service.state == 'failed':
        raise HTTPException(
            status_code=400,
            detail=f"Cannot validate failed service: {service.error or 'Service deployment failed'}"
        )

    if not service.template:
        raise HTTPException(status_code=400, detail="Service has no template defined")

    # Get validation template
    validation_template = service.validation_template or service.template
    validation_config = await get_template_content(
        validation_template,
        service.variables or {},
        auth_header
    )

    if not validation_config:
        raise HTTPException(
            status_code=500,
            detail=f"Template not found or failed to render: {validation_template}"
        )

    # Extract patterns to validate
    patterns = [line.strip() for line in validation_config.split('\n') if line.strip()]

    if request_body.use_backup:
        # Try to get latest backup for the device
        backup = await get_device_backup(service.device, auth_header)

        if backup and backup.get('config_content'):
            # Validate against backup (synchronous, no device connection needed)
            validations = []
            all_passed = True

            for pattern in patterns:
                found = bool(re.search(re.escape(pattern), backup['config_content'], re.MULTILINE))
                validations.append({'pattern': pattern, 'found': found})
                if not found:
                    all_passed = False

            # Update service validation status
            service.last_validated = datetime.utcnow()
            service.validation_status = 'passed' if all_passed else 'failed'
            service.validation_errors = [v['pattern'] for v in validations if not v['found']]
            session.commit()

            return success_response(data={
                'validation_source': 'backup',
                'backup_id': backup.get('backup_id'),
                'backup_time': backup.get('created_at'),
                'status': 'success',
                'validation_status': 'passed' if all_passed else 'failed',
                'all_passed': all_passed,
                'validations': validations,
                'message': f'Validated against backup from {backup.get("created_at", "unknown")}'
            })

    # Live validation (use_backup=False or no backup available)
    credential_override = None
    if request_body.username and request_body.password:
        credential_override = {
            "username": request_body.username,
            "password": request_body.password
        }

    device_info = await get_device_connection_info(
        service.device,
        credential_override,
        auth_header
    )

    if not device_info:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get connection info for device: {service.device}"
        )

    # Submit validation task
    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    task_id = submit_celery_task(
        "tasks.device_tasks.validate_config",
        connection_args=clean_args,
        expected_patterns=patterns,
        validation_command='show running-config'
    )

    record_task(session, task_id, service.device, "service_validate", action_type="validate")

    return success_response(data={
        'validation_source': 'live',
        'task_id': task_id,
        'message': 'Live validation task submitted'
    })


@router.post("/instances/sync-states")
async def sync_service_states(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Sync service instance states from Celery task status."""
    updated_count = 0
    failed_count = 0

    # Get all services in deploying state
    deploying_services = session.query(ServiceInstance).filter(
        ServiceInstance.state == 'deploying'
    ).all()

    log.info(f"Found {len(deploying_services)} services in deploying state")

    for service in deploying_services:
        if not service.task_id:
            continue

        try:
            # Query Celery for task status
            result = AsyncResult(service.task_id, app=celery_app)
            task_status = result.status.upper()

            log.info(f"Service {service.service_id} task {service.task_id} status: {task_status}")

            if task_status == 'SUCCESS':
                service.state = 'deployed'
                service.deployed_at = datetime.utcnow()
                updated_count += 1
            elif task_status in ['FAILURE', 'FAILED']:
                service.state = 'failed'
                service.error = str(result.result) if result.result else 'Deployment failed'
                failed_count += 1

        except Exception as e:
            log.error(f"Error syncing service {service.service_id}: {e}")
            continue

    # Update stack states based on service states
    stacks_updated = set()
    for service in deploying_services:
        stack_id = service.stack_id
        if stack_id and stack_id not in stacks_updated:
            # Get all services for this stack
            stack_services = session.query(ServiceInstance).filter(
                ServiceInstance.stack_id == stack_id
            ).all()

            states = [s.state for s in stack_services]

            if all(state == 'deployed' for state in states):
                new_state = 'deployed'
            elif any(state == 'failed' for state in states):
                new_state = 'partial' if any(state == 'deployed' for state in states) else 'failed'
            elif any(state == 'deploying' for state in states):
                new_state = 'deploying'
            else:
                new_state = 'pending'

            stack = session.query(ServiceStack).filter(
                ServiceStack.stack_id == stack_id
            ).first()

            if stack and stack.state != new_state:
                stack.state = new_state
                stacks_updated.add(stack_id)

    session.commit()

    # Count still deploying
    still_deploying = sum(1 for s in deploying_services if s.state == 'deploying')

    return success_response(data={
        'updated': updated_count,
        'failed': failed_count,
        'stacks_updated': len(stacks_updated),
        'still_deploying': still_deploying
    })
