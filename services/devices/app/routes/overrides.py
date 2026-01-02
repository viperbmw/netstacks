"""
Device Override Routes

Device-specific connection setting overrides.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.schemas.overrides import (
    DeviceOverrideCreate,
    DeviceOverrideUpdate,
    DeviceOverrideResponse,
    DeviceOverrideListResponse,
)
from app.services.override_service import OverrideService

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=DeviceOverrideListResponse)
async def list_overrides(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all device overrides."""
    service = OverrideService(session)
    overrides = service.get_all()
    return success_response(data={
        "overrides": overrides,
        "count": len(overrides),
    })


@router.get("/{device_name}", response_model=DeviceOverrideResponse)
async def get_override(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get device-specific overrides for a device."""
    service = OverrideService(session)
    override = service.get(device_name)
    if not override:
        return success_response(
            data={"override": None},
            message="No override found for this device"
        )
    return success_response(data={"override": override})


@router.put("/{device_name}", response_model=DeviceOverrideResponse)
async def save_override(
    device_name: str,
    override: DeviceOverrideUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Save or update device-specific overrides."""
    service = OverrideService(session)
    saved = service.save(device_name, override)
    log.info(f"Device override saved for {device_name} by {current_user.sub}")
    return success_response(
        data={"override": saved},
        message=f"Override saved for {device_name}"
    )


@router.delete("/{device_name}")
async def delete_override(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete device-specific overrides."""
    service = OverrideService(session)

    existing = service.get(device_name)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Override not found for: {device_name}"
        )

    service.delete(device_name)
    log.info(f"Device override deleted for {device_name} by {current_user.sub}")
    return success_response(message=f"Override deleted for {device_name}")


@router.get("/{device_name}/connection-args")
async def get_override_connection_args(
    device_name: str,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get device override connection args with unmasked credentials.

    This endpoint returns the actual credentials for internal service-to-service
    communication (e.g., tasks service connecting to devices).
    """
    from netstacks_core.db import DeviceOverride

    override = session.query(DeviceOverride).filter(
        DeviceOverride.device_name == device_name
    ).first()

    if not override:
        return success_response(data={"connection_args": None})

    # Return connection args with actual credentials (not masked)
    connection_args = {}

    if override.device_type:
        connection_args["device_type"] = override.device_type
    if override.host:
        connection_args["host"] = override.host
    if override.port:
        connection_args["port"] = override.port
    if override.username:
        connection_args["username"] = override.username
    if override.password:
        connection_args["password"] = override.password
    if override.secret:
        connection_args["secret"] = override.secret
    if override.timeout:
        connection_args["timeout"] = override.timeout
    if override.conn_timeout:
        connection_args["conn_timeout"] = override.conn_timeout
    if override.auth_timeout:
        connection_args["auth_timeout"] = override.auth_timeout
    if override.banner_timeout:
        connection_args["banner_timeout"] = override.banner_timeout

    return success_response(data={"connection_args": connection_args})
