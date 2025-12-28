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
