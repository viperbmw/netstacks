"""
NetBox Routes

NetBox integration and sync operations.
"""

import logging
import time
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.services.netbox_service import NetBoxService
from app.schemas.netbox import NetBoxSyncRequest, NetBoxSyncResponse

log = logging.getLogger(__name__)

router = APIRouter()


class NetBoxFilter(BaseModel):
    key: str
    value: str


class TestNetBoxRequest(BaseModel):
    netbox_url: str
    netbox_token: Optional[str] = None
    verify_ssl: bool = False
    filters: Optional[List[NetBoxFilter]] = None


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


# This endpoint is at /api/test-netbox (separate from /api/netbox prefix)
test_router = APIRouter()


@test_router.post("/test-netbox")
async def test_netbox_connection(
    request: TestNetBoxRequest,
    current_user = Depends(get_current_user),
):
    """Test NetBox API connection with provided credentials."""
    netbox_url = request.netbox_url.strip()
    netbox_token = request.netbox_token.strip() if request.netbox_token else None
    verify_ssl = request.verify_ssl
    filters = request.filters or []

    if not netbox_url:
        raise HTTPException(status_code=400, detail="NetBox URL is required")

    # Build the test URL
    test_url = f"{netbox_url.rstrip('/')}/api/dcim/devices/?limit=3000"
    if filters:
        filter_params = '&'.join([f"{f.key}={f.value}" for f in filters])
        test_url += '&' + filter_params

    log.info(f"Testing NetBox connection to: {test_url}")
    log.info(f"SSL Verification: {verify_ssl}")
    log.info(f"Using token: {'Yes' if netbox_token else 'No'}")

    try:
        headers = {"Accept": "application/json"}
        if netbox_token:
            headers["Authorization"] = f"Token {netbox_token}"

        start_time = time.time()
        response = requests.get(
            test_url,
            headers=headers,
            verify=verify_ssl,
            timeout=30
        )
        end_time = time.time()
        response_time = f"{(end_time - start_time):.2f}s"

        if response.status_code == 200:
            data = response.json()
            devices = data.get("results", [])
            device_count = len(devices)

            return {
                "success": True,
                "device_count": device_count,
                "connection_count": 0,
                "response_time": response_time,
                "message": "Successfully connected to NetBox",
                "api_url": test_url,
                "verify_ssl": verify_ssl,
                "has_token": bool(netbox_token),
                "cached": False
            }
        else:
            return {
                "success": False,
                "error": f"NetBox returned HTTP {response.status_code}: {response.text[:200]}",
                "api_url": test_url,
                "verify_ssl": verify_ssl,
                "has_token": bool(netbox_token)
            }

    except requests.exceptions.SSLError as e:
        return {
            "success": False,
            "error": f"SSL Error: {str(e)}. Try disabling SSL verification.",
            "api_url": test_url,
            "verify_ssl": verify_ssl,
            "has_token": bool(netbox_token)
        }
    except requests.exceptions.ConnectionError as e:
        return {
            "success": False,
            "error": f"Connection Error: Unable to connect to {netbox_url}",
            "api_url": test_url,
            "verify_ssl": verify_ssl,
            "has_token": bool(netbox_token)
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out after 30 seconds",
            "api_url": test_url,
            "verify_ssl": verify_ssl,
            "has_token": bool(netbox_token)
        }
    except Exception as e:
        log.error(f"NetBox test error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "api_url": test_url,
            "verify_ssl": verify_ssl,
            "has_token": bool(netbox_token)
        }
