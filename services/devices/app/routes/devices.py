"""
Device Routes

CRUD operations for devices (manual and synced).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response, error_response

from app.schemas.devices import (
    DeviceCreate,
    DeviceUpdate,
    DeviceResponse,
    DeviceListResponse,
    DeviceFilterRequest,
    DeviceCreateOrFilter,
)
from app.services.device_service import DeviceService

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=DeviceListResponse)
async def list_devices(
    source: Optional[str] = Query(None, description="Filter by source (manual, netbox)"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    site: Optional[str] = Query(None, description="Filter by site"),
    refresh: bool = Query(False, description="Force refresh from sources"),
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get all devices from database and optionally NetBox.

    - Use `refresh=true` to force a fresh fetch from NetBox
    - Filter by source, device_type, or site
    """
    service = DeviceService(session)
    devices = service.get_all(
        source=source,
        device_type=device_type,
        site=site,
        refresh=refresh,
    )
    return success_response(data={
        "devices": devices,
        "count": len(devices),
    })


@router.post("/list", response_model=DeviceListResponse)
async def list_devices_with_filters(
    request: DeviceFilterRequest,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List devices with optional NetBox filters.

    This endpoint accepts a POST body with filters for compatibility with
    the legacy frontend that sends filters via POST.
    """
    service = DeviceService(session)
    devices = service.get_all_with_filters(filters=request.filters)
    return success_response(data={
        "devices": devices,
        "count": len(devices),
    })


@router.get("/cached")
async def get_cached_devices(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get devices from cache only - does NOT call NetBox."""
    service = DeviceService(session)
    devices = service.get_cached()
    return success_response(data={
        "devices": devices,
        "from_cache": True,
        "count": len(devices),
    })


@router.post("/clear-cache")
async def clear_device_cache(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Clear the device cache."""
    service = DeviceService(session)
    service.clear_cache()
    return success_response(message="Cache cleared successfully")


@router.post("/sync")
async def sync_devices_from_netbox(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Sync devices from NetBox to the database.

    This is the same as POST /api/netbox/sync but available at /api/devices/sync
    for convenience (e.g., from the devices page "Reload" button).
    """
    from app.services.netbox_service import NetBoxService

    service = NetBoxService(session)
    result = service.sync_devices()

    if result.get('success'):
        return success_response(
            data=result,
            message=f"Synced {result.get('synced', 0)} devices from NetBox"
        )
    else:
        return success_response(data=result)


@router.get("/{device_name}", response_model=DeviceResponse)
async def get_device(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a single device by name."""
    service = DeviceService(session)
    device = service.get(device_name)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_name}")
    return success_response(data={"device": device})


@router.post("")
async def create_or_list_devices(
    request: DeviceCreateOrFilter,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Handle POST to /api/devices.

    If request body contains 'filters', return filtered device list.
    Otherwise, create a new manual device.
    """
    service = DeviceService(session)

    # Check if this is a filter request (from dashboard)
    if request.filters is not None:
        devices = service.get_all_with_filters(filters=request.filters)
        return success_response(data={
            "devices": devices,
            "count": len(devices),
        })

    # Otherwise, it's a device creation request
    # Validate required fields for device creation
    if not request.name or not request.host or not request.device_type:
        raise HTTPException(
            status_code=422,
            detail="Device creation requires name, host, and device_type fields"
        )

    # Check if device already exists
    existing = service.get(request.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Device {request.name} already exists"
        )

    # Convert to DeviceCreate for service
    device_data = DeviceCreate(
        name=request.name,
        host=request.host,
        device_type=request.device_type,
        port=request.port,
        description=request.description,
        manufacturer=request.manufacturer,
        model=request.model,
        platform=request.platform,
        site=request.site,
        tags=request.tags,
        username=request.username,
        password=request.password,
        enable_password=request.enable_password,
    )

    created = service.create(device_data)
    log.info(f"Device {request.name} created by {current_user.sub}")
    return success_response(
        data={"device": created},
        message=f"Device {request.name} created successfully"
    )


@router.put("/{device_name}", response_model=DeviceResponse)
async def update_device(
    device_name: str,
    device: DeviceUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a device."""
    service = DeviceService(session)

    existing = service.get(device_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_name}")

    updated = service.update(device_name, device)
    log.info(f"Device {device_name} updated by {current_user.sub}")
    return success_response(
        data={"device": updated},
        message=f"Device {device_name} updated successfully"
    )


@router.delete("/{device_name}")
async def delete_device(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a device."""
    service = DeviceService(session)

    existing = service.get(device_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_name}")

    service.delete(device_name)
    log.info(f"Device {device_name} deleted by {current_user.sub}")
    return success_response(message=f"Device {device_name} deleted successfully")


@router.post("/{device_name}/test")
async def test_device_connectivity(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Test connectivity to a device.

    Returns connection status and basic device info.
    """
    service = DeviceService(session)

    device = service.get(device_name)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_name}")

    # TODO: Implement actual connectivity test via Netmiko
    # For now, return a placeholder response
    return success_response(
        data={
            "device": device_name,
            "status": "not_implemented",
            "message": "Connectivity testing requires Celery worker integration"
        }
    )
