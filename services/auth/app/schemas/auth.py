"""
Authentication schemas
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token expiration in seconds")


class LoginResponse(BaseModel):
    """Login response"""
    success: bool = True
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserInfo"


class RefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str = Field(..., description="Refresh token")


class RefreshResponse(BaseModel):
    """Token refresh response"""
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    """User information returned after login"""
    username: str
    auth_method: Optional[str] = "local"
    roles: List[str] = []
    theme: str = "dark"


# Update forward references
LoginResponse.model_rebuild()
