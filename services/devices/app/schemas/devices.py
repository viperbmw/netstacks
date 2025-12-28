"""
Device Schemas

Pydantic models for device requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeviceBase(BaseModel):
    """Base device schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Device hostname")
    host: str = Field(..., min_length=1, max_length=255, description="IP address or hostname")
    device_type: str = Field(..., min_length=1, max_length=100, description="Netmiko device type")
    port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    description: Optional[str] = Field(None, max_length=1000)
    manufacturer: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    platform: Optional[str] = Field(None, max_length=100)
    site: Optional[str] = Field(None, max_length=255)
    tags: List[str] = Field(default_factory=list)


class DeviceCreate(DeviceBase):
    """Schema for creating a device"""
    username: Optional[str] = Field(None, max_length=255, description="Device username (optional)")
    password: Optional[str] = Field(None, max_length=255, description="Device password (optional)")
    enable_password: Optional[str] = Field(None, max_length=255, description="Enable password (optional)")


class DeviceUpdate(BaseModel):
    """Schema for updating a device"""
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    device_type: Optional[str] = Field(None, min_length=1, max_length=100)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    enable_password: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    manufacturer: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    platform: Optional[str] = Field(None, max_length=100)
    site: Optional[str] = Field(None, max_length=255)
    tags: Optional[List[str]] = None


class DeviceOut(DeviceBase):
    """Device output schema (no sensitive data)"""
    id: int
    source: str = Field(default="manual", description="Device source (manual or netbox)")
    netbox_id: Optional[int] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceResponse(BaseModel):
    """Standard device response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DeviceListResponse(BaseModel):
    """List devices response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
