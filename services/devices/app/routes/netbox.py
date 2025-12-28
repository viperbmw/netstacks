"""
NetBox Routes

NetBox integration and sync operations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.netbox_service import NetBoxService
from app.schemas.netbox import NetBoxSyncRequest, NetBoxSyncResponse

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def netbox_status(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Check NetBox connectivity and configuration status."""
    service = NetBoxService(session)
    status = service.get_status()
    return success_response(data=status)


@router.post("/sync")
async def sync_from_netbox(
    request: Optional[NetBoxSyncRequest] = None,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Sync devices from NetBox.

    Optionally provide filters to limit which devices are synced.
    """
    service = NetBoxService(session)
    filters = request.filters if request else None

    result = service.sync_devices(filters=filters)
    log.info(f"NetBox sync triggered by {current_user.sub}: {result}")
    return success_response(data=result)


@router.get("/devices")
async def list_netbox_devices(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List devices directly from NetBox (without caching).

    This is useful for previewing what would be synced.
    """
    service = NetBoxService(session)
    devices = service.fetch_devices()
    return success_response(data={
        "devices": devices,
        "count": len(devices),
    })


@router.get("/connections")
async def get_device_connections(
    device_names: str = Query(..., description="Comma-separated list of device names"),
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get network connections between devices from NetBox.

    Useful for topology visualization.
    """
    service = NetBoxService(session)
    names = [n.strip() for n in device_names.split(",") if n.strip()]

    if not names:
        raise HTTPException(status_code=400, detail="No device names provided")

    connections = service.get_connections(names)
    return success_response(data={
        "connections": connections,
        "count": len(connections),
    })
