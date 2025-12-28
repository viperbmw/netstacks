"""
User management schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Create user request"""
    username: str = Field(..., min_length=1, max_length=255, description="Username")
    password: str = Field(..., min_length=4, description="Password")


class UserResponse(BaseModel):
    """User response (without sensitive data)"""
    username: str
    theme: str = "dark"
    auth_source: str = "local"
    created_at: Optional[datetime] = None


class UserList(BaseModel):
    """List of users response"""
    success: bool = True
    data: List[UserResponse]
    total: int


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=4, description="New password")


class ThemeUpdate(BaseModel):
    """Theme update request"""
    theme: str = Field(..., pattern="^(dark|light)$", description="Theme name")
