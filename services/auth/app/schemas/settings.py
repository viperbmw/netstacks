"""
Settings schemas
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Settings response"""
    success: bool = True
    data: Dict[str, Any]


class SettingsUpdate(BaseModel):
    """Settings update request"""
    netbox_url: Optional[str] = None
    netbox_token: Optional[str] = None
    verify_ssl: Optional[bool] = None
    netbox_filters: Optional[List[str]] = None
    cache_ttl: Optional[int] = Field(None, ge=0, le=86400)
    default_username: Optional[str] = None
    default_password: Optional[str] = None
    # AI settings
    ai_default_provider: Optional[str] = None
    ai_default_model: Optional[str] = None
    ai_default_temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    ai_default_max_tokens: Optional[int] = Field(None, ge=256, le=128000)
    ai_approval_timeout_minutes: Optional[int] = Field(None, ge=1, le=1440)


class MenuItemResponse(BaseModel):
    """Menu item response"""
    item_id: str
    label: str
    icon: str
    url: str
    order_index: int
    visible: bool


class MenuItemUpdate(BaseModel):
    """Menu item update request"""
    label: Optional[str] = None
    icon: Optional[str] = None
    visible: Optional[bool] = None


class MenuOrderItem(BaseModel):
    """Single menu item for order update"""
    item_id: str
    order_index: int
    visible: Optional[bool] = None


class MenuOrderUpdate(BaseModel):
    """Menu order update request"""
    items: List[MenuOrderItem]
