"""
Device deployment routes.

Provides endpoints for executing device operations via Celery tasks.
"""

import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
import httpx

from netstacks_core.db import get_db, TaskHistory

from app.config import get_settings
from app.services.celery_client import celery_app

log = logging.getLogger(__name__)
settings = get_settings()


def record_task(session: Session, task_id: str, device_name: str, task_name: str = None):
    """Record a task to the database for history tracking."""
    try:
        entry = TaskHistory(
            task_id=task_id,
            device_name=device_name,
            task_name=task_name,
            status='pending'
        )
        session.add(entry)
        session.commit()
        log.debug(f"Recorded task {task_id} for device {device_name}")
    except Exception as e:
        log.error(f"Failed to record task history: {e}")
        session.rollback()

router = APIRouter(prefix="/api/celery", tags=["deploy"])


# Pydantic models for request validation
class GetConfigRequest(BaseModel):
    device: str = Field(..., description="Device name")
    command: str = Field(..., description="CLI command to execute")
    use_textfsm: bool = Field(default=False, description="Parse output with TextFSM")
    use_ttp: bool = Field(default=False, description="Parse output with TTP")
    username: Optional[str] = Field(default=None, description="Override username")
    password: Optional[str] = Field(default=None, description="Override password")


class SetConfigRequest(BaseModel):
    device: str = Field(..., description="Device name")
    config_lines: Optional[List[str]] = Field(default=None, description="Configuration lines")
    template_content: Optional[str] = Field(default=None, description="Jinja2 template content")
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Template variables")
    save_config: bool = Field(default=True, description="Save config after push")
    username: Optional[str] = Field(default=None, description="Override username")
    password: Optional[str] = Field(default=None, description="Override password")


class ValidateRequest(BaseModel):
    device: str = Field(..., description="Device name")
    patterns: List[str] = Field(..., description="Regex patterns to validate")
    command: str = Field(default="show running-config", description="Command to run for validation")


class TaskHistoryEntry(BaseModel):
    task_id: str
    device_name: Optional[str] = None


async def get_device_connection_info(
    device_name: str,
    credential_override: Optional[Dict[str, str]] = None,
    auth_header: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get device connection info from the Devices microservice.

    Args:
        device_name: Name of the device
        credential_override: Optional credential override
        auth_header: Authorization header to forward

    Returns:
        Dict with connection_args or None if not found
    """
    devices_url = settings.DEVICES_SERVICE_URL

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Get device info
            response = await client.get(
                f"{devices_url}/api/devices/{device_name}",
                headers=headers
            )

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                log.error(f"Error getting device {device_name}: {response.status_code}")
                return None

            response_data = response.json()
            # Unwrap the response: {"success": true, "data": {"device": {...}}}
            device = response_data.get("data", {}).get("device", response_data)

            # Get device overrides with unmasked credentials
            overrides = {}
            override_response = await client.get(
                f"{devices_url}/api/device-overrides/{device_name}/connection-args",
                headers=headers
            )
            if override_response.status_code == 200:
                override_data = override_response.json()
                if override_data.get("success"):
                    overrides = override_data.get("data", {}).get("connection_args", {}) or {}
                else:
                    overrides = override_data.get("connection_args", {}) or {}

            # Build connection args starting with device defaults
            connection_args = {
                "device_type": device.get("device_type") or device.get("platform", "cisco_ios"),
                "host": device.get("host") or device.get("primary_ip") or device.get("hostname") or device_name,
                "port": device.get("port", 22),
                # Disable SSH keys/agent to force password/keyboard-interactive auth
                "use_keys": False,
                "allow_agent": False,
            }

            # Apply overrides (from device-overrides endpoint)
            if overrides.get("device_type"):
                connection_args["device_type"] = overrides["device_type"]
            if overrides.get("host"):
                connection_args["host"] = overrides["host"]
            if overrides.get("port"):
                connection_args["port"] = overrides["port"]

            # Apply timeout settings from overrides
            if overrides.get("timeout"):
                connection_args["timeout"] = overrides["timeout"]
            if overrides.get("conn_timeout"):
                connection_args["conn_timeout"] = overrides["conn_timeout"]
            if overrides.get("auth_timeout"):
                connection_args["auth_timeout"] = overrides["auth_timeout"]
            if overrides.get("banner_timeout"):
                connection_args["banner_timeout"] = overrides["banner_timeout"]

            # Apply credentials (inline override takes highest precedence, then device overrides)
            if credential_override:
                connection_args["username"] = credential_override.get("username")
                connection_args["password"] = credential_override.get("password")
            elif overrides.get("username"):
                connection_args["username"] = overrides.get("username")
                # Password is masked in response, need to get from auth service or device
                # For now, use the masked value as a flag that credentials exist
                if overrides.get("password"):
                    connection_args["password"] = overrides.get("password")
                if overrides.get("secret"):
                    connection_args["secret"] = overrides.get("secret")
            else:
                # Fallback to device's stored credentials
                connection_args["username"] = device.get("username")
                connection_args["password"] = device.get("password")
                if device.get("enable_password"):
                    connection_args["secret"] = device["enable_password"]

            return {
                "device": device,
                "connection_args": connection_args
            }

        except httpx.RequestError as e:
            log.error(f"Error connecting to devices service: {e}")
            return None


def submit_celery_task(task_name: str, **kwargs) -> str:
    """
    Submit a task to Celery.

    Args:
        task_name: Full task name (e.g., 'tasks.device_tasks.get_config')
        **kwargs: Task arguments

    Returns:
        Task ID
    """
    task = celery_app.send_task(task_name, kwargs=kwargs)
    return task.id


@router.post("/getconfig")
async def celery_getconfig(
    request: GetConfigRequest,
    req: Request,
    session: Session = Depends(get_db),
):
    """
    Execute a show command on a device via Celery.

    Returns the task ID for polling results.
    """
    # Build credential override if provided
    credential_override = None
    if request.username:
        credential_override = {
            "username": request.username,
            "password": request.password or ""
        }

    # Get auth header from the incoming request
    auth_header = req.headers.get("Authorization")

    # Get device connection info from Devices service
    device_info = await get_device_connection_info(
        request.device,
        credential_override,
        auth_header=auth_header
    )

    if not device_info:
        raise HTTPException(status_code=404, detail=f"Device {request.device} not found")

    connection_args = device_info["connection_args"]

    # Clean None values
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    # Submit Celery task
    task_name = "tasks.device_tasks.get_config"
    task_id = submit_celery_task(
        task_name,
        connection_args=clean_args,
        command=request.command,
        use_textfsm=request.use_textfsm,
        use_ttp=request.use_ttp
    )

    # Record task in database for history
    record_task(session, task_id, request.device, task_name)

    log.info(f"Dispatched get_config task {task_id} to {clean_args.get('host')}")

    return {
        "task_id": task_id,
        "device": request.device,
        "command": request.command,
        "message": "Task submitted successfully"
    }


@router.post("/setconfig")
async def celery_setconfig(
    request: SetConfigRequest,
    req: Request,
    session: Session = Depends(get_db),
):
    """
    Push configuration to a device via Celery.

    Returns the task ID for polling results.
    """
    if not request.config_lines and not request.template_content:
        raise HTTPException(
            status_code=400,
            detail="Either config_lines or template_content is required"
        )

    # Build credential override if provided
    credential_override = None
    if request.username:
        credential_override = {
            "username": request.username,
            "password": request.password or ""
        }

    # Get auth header from the incoming request
    auth_header = req.headers.get("Authorization")

    # Get device connection info
    device_info = await get_device_connection_info(
        request.device,
        credential_override,
        auth_header=auth_header
    )

    if not device_info:
        raise HTTPException(status_code=404, detail=f"Device {request.device} not found")

    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    # Submit Celery task
    task_name = "tasks.device_tasks.set_config"
    task_id = submit_celery_task(
        task_name,
        connection_args=clean_args,
        config_lines=request.config_lines,
        template_content=request.template_content,
        variables=request.variables or {},
        save_config=request.save_config
    )

    # Record task in database for history
    record_task(session, task_id, request.device, task_name)

    log.info(f"Dispatched set_config task {task_id} to {clean_args.get('host')}")

    return {
        "task_id": task_id,
        "device": request.device,
        "message": "Task submitted successfully"
    }


@router.get("/task/{task_id}")
async def celery_task_status(task_id: str):
    """
    Get Celery task status and result.
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": result.status,
    }

    # Add metadata
    try:
        if hasattr(result, "date_done") and result.date_done:
            response["ended_at"] = result.date_done.isoformat()
    except Exception:
        pass

    if result.ready():
        if result.successful():
            response["result"] = result.result
            if isinstance(result.result, dict):
                response["status"] = result.result.get("status", "success")
            else:
                response["status"] = "success"
        else:
            response["status"] = "failed"
            response["error"] = str(result.result)
            if result.traceback:
                response["traceback"] = result.traceback
    else:
        response["status"] = result.status.lower()

    return response


@router.post("/validate")
async def celery_validate(
    request: ValidateRequest,
    req: Request,
    session: Session = Depends(get_db),
):
    """
    Validate configuration patterns on a device via Celery.
    """
    # Get auth header from the incoming request
    auth_header = req.headers.get("Authorization")

    # Get device connection info
    device_info = await get_device_connection_info(request.device, auth_header=auth_header)

    if not device_info:
        raise HTTPException(status_code=404, detail=f"Device {request.device} not found")

    connection_args = device_info["connection_args"]
    clean_args = {k: v for k, v in connection_args.items() if v is not None}

    # Submit Celery task
    task_name = "tasks.device_tasks.validate_config"
    task_id = submit_celery_task(
        task_name,
        connection_args=clean_args,
        expected_patterns=request.patterns,
        validation_command=request.command
    )

    # Record task in database for history
    record_task(session, task_id, request.device, task_name)

    log.info(f"Dispatched validate_config task {task_id} to {clean_args.get('host')}")

    return {
        "task_id": task_id,
        "device": request.device,
        "message": "Validation task submitted"
    }
