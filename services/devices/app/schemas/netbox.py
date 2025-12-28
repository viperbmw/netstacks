"""
NetBox Schemas

Pydantic models for NetBox sync requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NetBoxFilter(BaseModel):
    """NetBox filter key-value pair"""
    key: str = Field(..., description="Filter key (e.g., 'tag', 'site', 'manufacturer_id')")
    value: str = Field(..., description="Filter value")


class NetBoxSyncRequest(BaseModel):
    """Request to sync devices from NetBox"""
    filters: Optional[List[NetBoxFilter]] = Field(
        None,
        description="Optional filters to apply when syncing"
    )


class NetBoxSyncResponse(BaseModel):
    """NetBox sync result"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class NetBoxDeviceOut(BaseModel):
    """NetBox device info"""
    name: str
    id: Optional[int] = None
    display: Optional[str] = None
    device_type: str
    platform: Optional[str] = None
    manufacturer: Optional[str] = None
    site: Optional[str] = None
    primary_ip: Optional[str] = None
    url: Optional[str] = None


class NetBoxConnectionOut(BaseModel):
    """NetBox device connection info"""
    source: str
    target: str
    source_interface: Optional[str] = None
    target_interface: Optional[str] = None
    cable_id: Optional[int] = None
