"""
Device Override Schemas

Pydantic models for device override requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeviceOverrideBase(BaseModel):
    """Base device override schema"""
    device_type: Optional[str] = Field(None, max_length=50, description="Override device type")
    host: Optional[str] = Field(None, max_length=255, description="Override host/IP")
    port: Optional[int] = Field(None, ge=1, le=65535, description="Override port")
    timeout: Optional[int] = Field(None, ge=1, le=600, description="Connection timeout")
    conn_timeout: Optional[int] = Field(None, ge=1, le=600, description="Connection timeout")
    auth_timeout: Optional[int] = Field(None, ge=1, le=600, description="Auth timeout")
    banner_timeout: Optional[int] = Field(None, ge=1, le=600, description="Banner timeout")
    notes: Optional[str] = Field(None, max_length=1000, description="Notes about this override")
    disabled: bool = Field(default=False, description="Disable device from operations")


class DeviceOverrideCreate(DeviceOverrideBase):
    """Schema for creating a device override"""
    device_name: str = Field(..., min_length=1, max_length=255)
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    secret: Optional[str] = Field(None, max_length=255, description="Enable secret")


class DeviceOverrideUpdate(DeviceOverrideBase):
    """Schema for updating a device override"""
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    secret: Optional[str] = Field(None, max_length=255)


class DeviceOverrideOut(DeviceOverrideBase):
    """Device override output schema (credentials masked)"""
    device_name: str
    username: Optional[str] = None
    password: str = "****"  # Masked
    secret: Optional[str] = None  # Masked if present
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceOverrideResponse(BaseModel):
    """Standard override response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DeviceOverrideListResponse(BaseModel):
    """List overrides response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
