"""
Config backup operation routes.

Provides endpoints for running config backups via Celery tasks.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
import httpx

from app.config import get_settings
from app.services.celery_client import celery_app

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/config-backups", tags=["config-backups"])


class RunAllBackupsRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    snapshot_type: str = Field(default="manual")


class RunSelectedBackupsRequest(BaseModel):
    devices: List[str] = Field(..., description="List of device names to backup")
    name: Optional[str] = None
    description: Optional[str] = None
    snapshot_type: str = Field(default="manual")


class RunSingleBackupRequest(BaseModel):
    device_name: str = Field(..., description="Device name to backup")


async def get_all_devices(auth_header: Optional[str] = None) -> List[dict]:
    """Get all devices from the devices service."""
    devices_url = settings.DEVICES_SERVICE_URL
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{devices_url}/api/devices", headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("devices", [])
        except Exception as e:
            log.error(f"Error fetching devices: {e}")
    return []


async def get_backup_schedule(auth_header: Optional[str] = None) -> dict:
    """Get backup schedule settings from devices service."""
    devices_url = settings.DEVICES_SERVICE_URL
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{devices_url}/api/backup-schedule", headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            log.error(f"Error fetching backup schedule: {e}")
    return {}


async def get_device_connection_info(
    device_name: str,
    auth_header: Optional[str] = None
) -> Optional[dict]:
    """Get device connection info including credentials.

    Returns:
        Dict with device_info and connection_args, or dict with 'error' key if device is disabled, or None if not found.
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
            device_disabled = False
            if override_resp.status_code == 200:
                resp_data = override_resp.json().get("data", {})
                override = resp_data.get("connection_args") or {}
                device_disabled = resp_data.get("disabled", False)

            # If device is disabled, return error dict to block all operations
            if device_disabled:
                log.info(f"Device {device_name} is disabled, skipping operation")
                return {"error": "disabled", "message": f"Device {device_name} is disabled"}

            # Get default credentials (unmasked)
            settings_resp = await client.get(
                f"{auth_url}/api/settings/credentials/default",
                headers=headers
            )
            default_settings = {}
            if settings_resp.status_code == 200:
                default_settings = settings_resp.json().get("data", {})

            # Build connection args
            connection_args = {
                "device_type": override.get("device_type") or device_data.get("device_type", "cisco_ios"),
                "host": override.get("host") or device_data.get("host"),
                "port": override.get("port") or device_data.get("port") or 22,
                # Disable SSH keys/agent to force password/keyboard-interactive auth
                "use_keys": False,
                "allow_agent": False,
            }

            # Apply credentials - override takes precedence over defaults
            if override.get("username"):
                connection_args["username"] = override["username"]
                connection_args["password"] = override.get("password", "")
            else:
                connection_args["username"] = default_settings.get("default_username", "")
                connection_args["password"] = default_settings.get("default_password", "")

            # Apply timeout settings - device override takes precedence, then global defaults
            connection_args["timeout"] = (
                override.get("timeout") or
                default_settings.get("default_timeout", 30)
            )
            connection_args["conn_timeout"] = (
                override.get("conn_timeout") or
                default_settings.get("default_conn_timeout", 10)
            )
            connection_args["auth_timeout"] = (
                override.get("auth_timeout") or
                default_settings.get("default_auth_timeout", 10)
            )
            connection_args["banner_timeout"] = (
                override.get("banner_timeout") or
                default_settings.get("default_banner_timeout", 15)
            )

            if override.get("secret"):
                connection_args["secret"] = override["secret"]

            return {
                "device_info": device_data,
                "connection_args": connection_args
            }

        except httpx.RequestError as e:
            log.error(f"Error getting device connection info: {e}")
            return None


async def create_config_snapshot(
    name: str,
    description: Optional[str],
    snapshot_type: str,
    total_devices: int,
    created_by: Optional[str],
    auth_header: Optional[str] = None
) -> Optional[str]:
    """Create a config snapshot in the config service."""
    config_url = getattr(settings, 'CONFIG_SERVICE_URL', 'http://config:8002')
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    snapshot_id = str(uuid.uuid4())

    # Direct DB insert since we have access to shared models
    try:
        from netstacks_core.db import get_session, ConfigSnapshot as ConfigSnapshotModel

        session = get_session()
        snapshot = ConfigSnapshotModel(
            snapshot_id=snapshot_id,
            name=name,
            description=description,
            snapshot_type=snapshot_type,
            status='in_progress',
            total_devices=total_devices,
            success_count=0,
            failed_count=0,
            skipped_count=0,
            created_by=created_by
        )
        session.add(snapshot)
        session.commit()
        session.close()
        return snapshot_id
    except Exception as e:
        log.error(f"Error creating snapshot: {e}")
        return None


async def save_task_history(
    task_id: str,
    device_name: str,
    auth_header: Optional[str] = None
):
    """Save task to task_history table."""
    try:
        from netstacks_core.db import get_session, TaskHistory

        session = get_session()
        task = TaskHistory(
            task_id=task_id,
            device_name=device_name,
            status='pending'
        )
        session.add(task)
        session.commit()
        session.close()
    except Exception as e:
        log.error(f"Error saving task history: {e}")


def get_username_from_token(auth_header: Optional[str]) -> Optional[str]:
    """Extract username from JWT token."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        import jwt
        token = auth_header[7:]
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload.get("sub")
    except Exception:
        return None


async def update_snapshot_for_skipped_devices(snapshot_id: str, skipped: int):
    """
    Update snapshot to account for devices that were skipped (disabled, no credentials, etc).
    Uses the skipped_count column and checks if the snapshot is now complete.
    """
    try:
        from netstacks_core.db import get_session, ConfigSnapshot as ConfigSnapshotModel

        session = get_session()
        snapshot = session.query(ConfigSnapshotModel).filter(
            ConfigSnapshotModel.snapshot_id == snapshot_id
        ).first()

        if snapshot:
            # Update skipped count
            snapshot.skipped_count = (snapshot.skipped_count or 0) + skipped

            # Check if snapshot is now complete (success + failed + skipped = total)
            total_processed = (snapshot.success_count or 0) + (snapshot.failed_count or 0) + (snapshot.skipped_count or 0)
            if total_processed >= snapshot.total_devices:
                # Status is 'complete' only if all succeeded, 'partial' if any failed or skipped
                if snapshot.failed_count == 0 and snapshot.skipped_count == 0:
                    snapshot.status = 'complete'
                else:
                    snapshot.status = 'partial'
                snapshot.completed_at = datetime.utcnow()
                log.info(f"Snapshot {snapshot_id} marked as {snapshot.status} (skipped {skipped} devices)")

            session.commit()
        session.close()
    except Exception as e:
        log.error(f"Error updating snapshot for skipped devices: {e}")


@router.post("/run-all")
async def run_all_device_backups(
    request: RunAllBackupsRequest = None,
    authorization: Optional[str] = Header(None)
):
    """
    Run backups for all devices, creating a snapshot.
    """
    try:
        request = request or RunAllBackupsRequest()

        # Get all devices
        devices = await get_all_devices(authorization)

        if not devices:
            raise HTTPException(
                status_code=400,
                detail="No devices found. Add manual devices or configure NetBox."
            )

        log.info(f"Found {len(devices)} devices for backup")

        # Get backup schedule settings
        schedule = await get_backup_schedule(authorization)
        juniper_set_format = schedule.get("juniper_set_format", True)
        exclude_patterns = schedule.get("exclude_patterns", []) or []

        # Filter out excluded devices
        if exclude_patterns:
            filtered_devices = []
            for device in devices:
                device_name = device.get("name", "")
                excluded = False
                for pattern in exclude_patterns:
                    if re.search(pattern, device_name, re.IGNORECASE):
                        excluded = True
                        break
                if not excluded:
                    filtered_devices.append(device)
            devices = filtered_devices

        # Create snapshot
        created_by = get_username_from_token(authorization)
        snapshot_name = request.name or f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        snapshot_id = await create_config_snapshot(
            name=snapshot_name,
            description=request.description,
            snapshot_type=request.snapshot_type,
            total_devices=len(devices),
            created_by=created_by,
            auth_header=authorization
        )

        if not snapshot_id:
            raise HTTPException(status_code=500, detail="Failed to create snapshot")

        log.info(f"Created snapshot {snapshot_id} for {len(devices)} devices")

        # Submit backup tasks
        submitted = []
        failed = []

        for device in devices:
            device_name = device.get("name")
            try:
                device_info = await get_device_connection_info(device_name, authorization)

                if not device_info:
                    failed.append({"device": device_name, "error": "Could not get connection info"})
                    continue

                # Check if device is disabled
                if device_info.get("error") == "disabled":
                    failed.append({"device": device_name, "error": "Device is disabled"})
                    continue

                connection_args = device_info["connection_args"]

                # Skip if no credentials
                if not connection_args.get("username") or not connection_args.get("password"):
                    failed.append({"device": device_name, "error": "No credentials configured"})
                    continue

                # Clean None values
                clean_args = {k: v for k, v in connection_args.items() if v is not None}

                # Submit Celery task
                task = celery_app.send_task(
                    "tasks.backup_tasks.backup_device_config",
                    kwargs={
                        "connection_args": clean_args,
                        "device_name": device_name,
                        "device_platform": device_info["device_info"].get("platform"),
                        "juniper_set_format": juniper_set_format,
                        "snapshot_id": snapshot_id,
                        "created_by": created_by
                    }
                )
                task_id = task.id

                # Save task history
                await save_task_history(
                    task_id=task_id,
                    device_name=f"snapshot:{snapshot_id}:backup:{device_name}",
                    auth_header=authorization
                )

                submitted.append({
                    "device": device_name,
                    "task_id": task_id,
                    "snapshot_id": snapshot_id
                })

            except Exception as e:
                failed.append({"device": device_name, "error": str(e)})

        # Update snapshot with actual counts (adjusting for skipped devices)
        if failed:
            await update_snapshot_for_skipped_devices(snapshot_id, len(failed))

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "submitted": len(submitted),
            "failed": len(failed),
            "tasks": submitted,
            "errors": failed
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error running all device backups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-selected")
async def run_selected_device_backups(
    request: RunSelectedBackupsRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Run backups for selected devices.
    """
    try:
        if not request.devices:
            raise HTTPException(status_code=400, detail="No devices specified")

        # Get backup schedule settings
        schedule = await get_backup_schedule(authorization)
        juniper_set_format = schedule.get("juniper_set_format", True)

        # Create snapshot
        created_by = get_username_from_token(authorization)
        snapshot_name = request.name or f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        snapshot_id = await create_config_snapshot(
            name=snapshot_name,
            description=request.description,
            snapshot_type=request.snapshot_type,
            total_devices=len(request.devices),
            created_by=created_by,
            auth_header=authorization
        )

        if not snapshot_id:
            raise HTTPException(status_code=500, detail="Failed to create snapshot")

        log.info(f"Created snapshot {snapshot_id} for {len(request.devices)} selected devices")

        # Submit backup tasks
        submitted = []
        failed = []

        for device_name in request.devices:
            try:
                device_info = await get_device_connection_info(device_name, authorization)

                if not device_info:
                    failed.append({"device": device_name, "error": "Could not get connection info"})
                    continue

                # Check if device is disabled
                if device_info.get("error") == "disabled":
                    failed.append({"device": device_name, "error": "Device is disabled"})
                    continue

                connection_args = device_info["connection_args"]

                if not connection_args.get("username") or not connection_args.get("password"):
                    failed.append({"device": device_name, "error": "No credentials configured"})
                    continue

                clean_args = {k: v for k, v in connection_args.items() if v is not None}

                task = celery_app.send_task(
                    "tasks.backup_tasks.backup_device_config",
                    kwargs={
                        "connection_args": clean_args,
                        "device_name": device_name,
                        "device_platform": device_info["device_info"].get("platform"),
                        "juniper_set_format": juniper_set_format,
                        "snapshot_id": snapshot_id,
                        "created_by": created_by
                    }
                )
                task_id = task.id

                await save_task_history(
                    task_id=task_id,
                    device_name=f"snapshot:{snapshot_id}:backup:{device_name}",
                    auth_header=authorization
                )

                submitted.append({
                    "device": device_name,
                    "task_id": task_id,
                    "snapshot_id": snapshot_id
                })

            except Exception as e:
                failed.append({"device": device_name, "error": str(e)})

        # Update snapshot with actual counts (adjusting for skipped devices)
        if failed:
            await update_snapshot_for_skipped_devices(snapshot_id, len(failed))

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "submitted": len(submitted),
            "failed": len(failed),
            "tasks": submitted,
            "errors": failed
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error running selected device backups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-single")
async def run_single_device_backup(
    request: RunSingleBackupRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Run backup for a single device.
    """
    try:
        device_name = request.device_name

        # Get backup schedule settings
        schedule = await get_backup_schedule(authorization)
        juniper_set_format = schedule.get("juniper_set_format", True)

        created_by = get_username_from_token(authorization)

        device_info = await get_device_connection_info(device_name, authorization)

        if not device_info:
            raise HTTPException(
                status_code=404,
                detail=f"Device not found: {device_name}"
            )

        # Check if device is disabled
        if device_info.get("error") == "disabled":
            raise HTTPException(
                status_code=403,
                detail=device_info.get("message", f"Device {device_name} is disabled")
            )

        connection_args = device_info["connection_args"]

        if not connection_args.get("username") or not connection_args.get("password"):
            raise HTTPException(
                status_code=400,
                detail="No credentials configured for device"
            )

        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task = celery_app.send_task(
            "tasks.backup_tasks.backup_device_config",
            kwargs={
                "connection_args": clean_args,
                "device_name": device_name,
                "device_platform": device_info["device_info"].get("platform"),
                "juniper_set_format": juniper_set_format,
                "created_by": created_by
            }
        )
        task_id = task.id

        await save_task_history(
            task_id=task_id,
            device_name=f"backup:{device_name}",
            auth_header=authorization
        )

        log.info(f"Started backup task {task_id} for device {device_name}")

        return {
            "success": True,
            "task_id": task_id,
            "device": device_name
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error running single device backup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
