"""
Bulk device operations routes.

Provides endpoints for executing operations on multiple devices via Celery.
"""

import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Header, Depends
from sqlalchemy.orm import Session
import httpx

from netstacks_core.db import get_db, TaskHistory

from app.config import get_settings
from app.services.celery_client import celery_app

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/devices/bulk", tags=["bulk"])


# Pydantic models for request validation
class BulkTestRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names to test")


class BulkGetConfigRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names")
    command: str = Field(default="show running-config", description="Command to execute")
    use_textfsm: bool = Field(default=False, description="Parse with TextFSM")
    username: Optional[str] = Field(default=None, description="Override username")
    password: Optional[str] = Field(default=None, description="Override password")


class BulkSetConfigRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names")
    config: Optional[str] = Field(default=None, description="Configuration to push")
    template_name: Optional[str] = Field(default=None, description="Template name to use")
    template_vars: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Template variables")
    dry_run: bool = Field(default=False, description="Dry run mode")
    username: Optional[str] = Field(default=None, description="Override username")
    password: Optional[str] = Field(default=None, description="Override password")


class BulkBackupRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names to backup")


class BulkDeleteRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names to delete")


async def get_device_with_credentials(
    device_name: str,
    auth_header: Optional[str] = None,
    custom_username: Optional[str] = None,
    custom_password: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get device info and credentials from Devices and Auth services.
    """
    devices_url = settings.DEVICES_SERVICE_URL
    auth_url = settings.AUTH_SERVICE_URL

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Get device info
            device_resp = await client.get(
                f"{devices_url}/api/devices/{device_name}",
                headers=headers
            )
            if device_resp.status_code != 200:
                return None

            device_data = device_resp.json().get("data", {}).get("device", {})
            if not device_data:
                return None

            # Get device overrides with unmasked credentials
            override_resp = await client.get(
                f"{devices_url}/api/device-overrides/{device_name}/connection-args",
                headers=headers
            )
            override = {}
            if override_resp.status_code == 200:
                resp_data = override_resp.json().get("data", {})
                override = resp_data.get("connection_args") or {}

            # Get default credentials (unmasked)
            settings_resp = await client.get(
                f"{auth_url}/api/settings/credentials/default",
                headers=headers
            )
            default_settings = {}
            if settings_resp.status_code == 200:
                default_settings = settings_resp.json().get("data", {})

            # Build connection args with credential precedence:
            # 1. Custom credentials passed in request
            # 2. Device-specific overrides
            # 3. Default settings
            connection_args = {
                "device_type": override.get("device_type") or device_data.get("device_type", "cisco_ios"),
                "host": override.get("host") or device_data.get("host"),
                "port": override.get("port") or device_data.get("port") or 22,
                "username": (
                    custom_username or
                    override.get("username") or
                    default_settings.get("default_username", "")
                ),
                "password": (
                    custom_password or
                    override.get("password") or
                    default_settings.get("default_password", "")
                ),
                # Disable SSH keys/agent to force password/keyboard-interactive auth
                "use_keys": False,
                "allow_agent": False,
                # Timeout settings from device overrides or global defaults
                "timeout": override.get("timeout") or default_settings.get("default_timeout", 30),
                "conn_timeout": override.get("conn_timeout") or default_settings.get("default_conn_timeout", 10),
                "auth_timeout": override.get("auth_timeout") or default_settings.get("default_auth_timeout", 10),
                "banner_timeout": override.get("banner_timeout") or default_settings.get("default_banner_timeout", 15),
            }

            # Add enable secret if available
            if override.get("enable_password"):
                connection_args["secret"] = override["enable_password"]
            elif override.get("secret"):
                connection_args["secret"] = override["secret"]

            return {
                "device": device_data,
                "connection_args": connection_args
            }

        except httpx.RequestError as e:
            log.error(f"Error connecting to services: {e}")
            return None


def submit_celery_task(task_name: str, **kwargs) -> str:
    """Submit a task to Celery."""
    task = celery_app.send_task(task_name, kwargs=kwargs)
    return task.id


def record_task(session: Session, task_id: str, device_name: str, task_name: str = None, action_type: str = None):
    """Record a task to the database for history tracking."""
    try:
        entry = TaskHistory(
            task_id=task_id,
            device_name=device_name,
            task_name=task_name,
            action_type=action_type,
            status='pending'
        )
        session.add(entry)
        session.commit()
        log.debug(f"Recorded task {task_id} for device {device_name} (action: {action_type})")
    except Exception as e:
        log.error(f"Failed to record task history: {e}")
        session.rollback()


@router.post("/test")
async def bulk_test_devices(
    request: BulkTestRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Test connectivity to multiple devices.
    Returns task IDs for polling results.
    """
    if not request.devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    task_ids = []

    for device_name in request.devices:
        device_info = await get_device_with_credentials(device_name, authorization)

        if not device_info:
            continue

        connection_args = device_info["connection_args"]

        # Skip if no credentials
        if not connection_args.get("username") or not connection_args.get("password"):
            continue

        # Clean None values
        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task_id = submit_celery_task(
            "tasks.device_tasks.test_connectivity",
            connection_args=clean_args
        )
        task_ids.append(task_id)
        log.info(f"Dispatched test_connectivity task {task_id} for {device_name}")

    return {"task_ids": task_ids}


@router.post("/get-config")
async def bulk_get_config(
    request: BulkGetConfigRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Get configuration from multiple devices.
    Returns task IDs for polling results.
    """
    if not request.devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    task_ids = []

    for device_name in request.devices:
        device_info = await get_device_with_credentials(
            device_name,
            authorization,
            request.username,
            request.password
        )

        if not device_info:
            continue

        connection_args = device_info["connection_args"]

        # Skip if no credentials
        if not connection_args.get("username") or not connection_args.get("password"):
            continue

        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task_id = submit_celery_task(
            "tasks.device_tasks.get_config",
            connection_args=clean_args,
            command=request.command,
            use_textfsm=request.use_textfsm
        )
        task_ids.append(task_id)
        log.info(f"Dispatched get_config task {task_id} for {device_name}")

    return {"task_ids": task_ids}


@router.post("/set-config")
async def bulk_set_config(
    request: BulkSetConfigRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Set configuration on multiple devices.
    Returns task IDs for polling results.
    """
    if not request.devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    if not request.config and not request.template_name:
        raise HTTPException(status_code=400, detail="No config or template specified")

    # If using template, fetch and render it
    final_config = request.config
    if request.template_name:
        config_url = settings.CONFIG_SERVICE_URL if hasattr(settings, 'CONFIG_SERVICE_URL') else 'http://config:8002'
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization

        async with httpx.AsyncClient(timeout=10.0) as client:
            template_resp = await client.get(
                f"{config_url}/api/templates/{request.template_name}",
                headers=headers
            )
            if template_resp.status_code != 200:
                raise HTTPException(
                    status_code=404,
                    detail=f"Template not found: {request.template_name}"
                )

            template_data = template_resp.json().get("data", {}).get("template", {})
            template_content = template_data.get("content", "")

            # Render with Jinja2
            from jinja2 import Template
            try:
                jinja_template = Template(template_content)
                final_config = jinja_template.render(**(request.template_vars or {}))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Template rendering error: {str(e)}"
                )

    task_ids = []

    for device_name in request.devices:
        device_info = await get_device_with_credentials(
            device_name,
            authorization,
            request.username,
            request.password
        )

        if not device_info:
            continue

        connection_args = device_info["connection_args"]

        # Skip if no credentials
        if not connection_args.get("username") or not connection_args.get("password"):
            continue

        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        # Convert config string to lines
        config_lines = final_config.split("\n") if final_config else []

        task_id = submit_celery_task(
            "tasks.device_tasks.set_config",
            connection_args=clean_args,
            config_lines=config_lines,
            save_config=not request.dry_run
        )
        task_ids.append(task_id)
        log.info(f"Dispatched set_config task {task_id} for {device_name}")

    return {"task_ids": task_ids}


@router.post("/backup")
async def bulk_backup_devices(
    request: BulkBackupRequest,
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_db)
):
    """
    Backup configuration from multiple devices.
    Returns task IDs for polling results.
    """
    if not request.devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    # Extract username from JWT if available
    username = None
    if authorization and authorization.startswith("Bearer "):
        try:
            import jwt
            token = authorization[7:]
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            username = payload.get("sub")
        except Exception:
            pass

    task_ids = []

    for device_name in request.devices:
        device_info = await get_device_with_credentials(device_name, authorization)

        if not device_info:
            continue

        connection_args = device_info["connection_args"]
        device_data = device_info["device"]

        # Skip if no credentials
        if not connection_args.get("username") or not connection_args.get("password"):
            continue

        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task_name = "tasks.backup_tasks.backup_device_config"
        task_id = submit_celery_task(
            task_name,
            connection_args=clean_args,
            device_name=device_name,
            device_platform=device_data.get("platform"),
            created_by=username
        )

        # Record task to database for monitoring
        record_task(session, task_id, f"backup:{device_name}", task_name, action_type="backup")

        task_ids.append(task_id)
        log.info(f"Dispatched backup task {task_id} for {device_name}")

    return {"task_ids": task_ids, "success": True}


@router.post("/delete")
async def bulk_delete_devices(
    request: BulkDeleteRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Delete multiple manual devices.
    Proxies delete requests to the Devices microservice.
    """
    if not request.devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    devices_url = settings.DEVICES_SERVICE_URL
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    deleted = 0
    errors = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for device_name in request.devices:
            try:
                response = await client.delete(
                    f"{devices_url}/api/devices/{device_name}",
                    headers=headers
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        deleted += 1
                    else:
                        errors.append(f"{device_name}: {result.get('error', 'Unknown error')}")
                else:
                    errors.append(f"{device_name}: HTTP {response.status_code}")

            except Exception as e:
                errors.append(f"{device_name}: {str(e)}")

    return {
        "deleted": deleted,
        "errors": errors if errors else None
    }
