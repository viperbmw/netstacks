"""
Pydantic schemas for Auth Service
"""

from .auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
    UserInfo,
)

from .users import (
    UserCreate,
    UserResponse,
    UserList,
    PasswordChange,
    ThemeUpdate,
)

from .settings import (
    SettingsResponse,
    SettingsUpdate,
    MenuItemResponse,
    MenuItemUpdate,
    MenuOrderUpdate,
)

__all__ = [
    # Auth
    "LoginRequest",
    "LoginResponse",
    "RefreshRequest",
    "RefreshResponse",
    "TokenResponse",
    "UserInfo",
    # Users
    "UserCreate",
    "UserResponse",
    "UserList",
    "PasswordChange",
    "ThemeUpdate",
    # Settings
    "SettingsResponse",
    "SettingsUpdate",
    "MenuItemResponse",
    "MenuItemUpdate",
    "MenuOrderUpdate",
]
