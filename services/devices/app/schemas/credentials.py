"""
Credential Schemas

Pydantic models for credential requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CredentialBase(BaseModel):
    """Base credential schema"""
    name: str = Field(..., min_length=1, max_length=100, description="Credential set name")
    username: str = Field(..., min_length=1, max_length=255, description="Username")


class CredentialCreate(CredentialBase):
    """Schema for creating a credential"""
    password: str = Field(..., min_length=1, max_length=255, description="Password")
    enable_password: Optional[str] = Field(None, max_length=255, description="Enable password")
    is_default: bool = Field(default=False, description="Set as default credential")


class CredentialUpdate(BaseModel):
    """Schema for updating a credential"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1, max_length=255)
    enable_password: Optional[str] = Field(None, max_length=255)
    is_default: Optional[bool] = None


class CredentialOut(CredentialBase):
    """Credential output schema (password masked)"""
    id: int
    password: str = "****"  # Always masked
    enable_password: Optional[str] = None  # Masked if present
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CredentialResponse(BaseModel):
    """Standard credential response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CredentialListResponse(BaseModel):
    """List credentials response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
