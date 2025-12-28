"""
System settings routes
"""

import json
import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status, Depends

from netstacks_core.auth import get_current_user, TokenData
from netstacks_core.db import get_session, Setting, MenuItem
from netstacks_core.utils import success_response

from app.schemas.settings import (
    SettingsResponse,
    SettingsUpdate,
    MenuItemResponse,
    MenuItemUpdate,
    MenuOrderUpdate,
)

log = logging.getLogger(__name__)
router = APIRouter()

# Default settings
DEFAULT_SETTINGS = {
    'netbox_url': '',
    'netbox_token': '',
    'verify_ssl': False,
    'netbox_filters': [],
    'cache_ttl': 300,
    'default_username': '',
    'default_password': '',
    'system_timezone': 'UTC'
}

# Field type definitions
JSON_FIELDS = ['netbox_filters']
INT_FIELDS = ['cache_ttl']
BOOL_FIELDS = ['verify_ssl']
SENSITIVE_FIELDS = ['netbox_token', 'default_password']


def parse_setting_value(key: str, value: str) -> Any:
    """Parse a setting value to its proper type."""
    if key in JSON_FIELDS:
        try:
            return json.loads(value) if value else []
        except (json.JSONDecodeError, TypeError):
            return []
    elif key in INT_FIELDS:
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0
    elif key in BOOL_FIELDS:
        return value.lower() in ('true', '1', 'yes') if value else False
    return value


def serialize_setting_value(key: str, value: Any) -> str:
    """Serialize a setting value for storage."""
    if isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value) if value is not None else ''


def mask_sensitive(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive fields in settings dict."""
    result = settings.copy()
    for field in SENSITIVE_FIELDS:
        if field in result and result[field]:
            result[field] = '****'
    return result


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(current_user: TokenData = Depends(get_current_user)):
    """
    Get all application settings.
    """
    session = get_session()
    try:
        settings = DEFAULT_SETTINGS.copy()

        # Load settings from database
        stored = session.query(Setting).all()
        for s in stored:
            if s.key in DEFAULT_SETTINGS:
                settings[s.key] = parse_setting_value(s.key, s.value)

        # Add system timezone from environment
        settings['system_timezone'] = os.environ.get('TZ', 'UTC')

        return SettingsResponse(data=mask_sensitive(settings))

    finally:
        session.close()


@router.put("/settings", response_model=SettingsResponse)
@router.post("/settings", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update application settings.
    """
    session = get_session()
    try:
        # Get settings to update
        updates = request.model_dump(exclude_unset=True)

        for key, value in updates.items():
            if key not in DEFAULT_SETTINGS:
                continue

            # Serialize value for storage
            serialized = serialize_setting_value(key, value)

            # Upsert setting
            setting = session.query(Setting).filter(Setting.key == key).first()
            if setting:
                setting.value = serialized
            else:
                setting = Setting(key=key, value=serialized)
                session.add(setting)

        session.commit()
        log.info(f"Settings updated by {current_user.sub}")

        # Return updated settings
        settings = DEFAULT_SETTINGS.copy()
        stored = session.query(Setting).all()
        for s in stored:
            if s.key in DEFAULT_SETTINGS:
                settings[s.key] = parse_setting_value(s.key, s.value)

        settings['system_timezone'] = os.environ.get('TZ', 'UTC')

        return SettingsResponse(data=mask_sensitive(settings))

    finally:
        session.close()


@router.get("/settings/{category}")
async def get_settings_by_category(
    category: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get settings by category.
    """
    # Define category mappings
    categories = {
        'netbox': ['netbox_url', 'netbox_token', 'verify_ssl', 'netbox_filters'],
        'credentials': ['default_username', 'default_password'],
        'cache': ['cache_ttl'],
        'system': ['system_timezone'],
    }

    if category not in categories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown settings category: {category}"
        )

    session = get_session()
    try:
        settings = {}
        keys = categories[category]

        for key in keys:
            if key == 'system_timezone':
                settings[key] = os.environ.get('TZ', 'UTC')
            else:
                setting = session.query(Setting).filter(Setting.key == key).first()
                if setting:
                    settings[key] = parse_setting_value(key, setting.value)
                else:
                    settings[key] = DEFAULT_SETTINGS.get(key)

        return success_response(data=mask_sensitive(settings))

    finally:
        session.close()


@router.get("/menu", response_model=List[MenuItemResponse])
async def get_menu_items(current_user: TokenData = Depends(get_current_user)):
    """
    Get all menu items.
    """
    session = get_session()
    try:
        items = session.query(MenuItem).order_by(MenuItem.order_index).all()
        return [
            MenuItemResponse(
                item_id=item.item_id,
                label=item.label,
                icon=item.icon,
                url=item.url,
                order_index=item.order_index,
                visible=item.visible,
            )
            for item in items
        ]
    finally:
        session.close()


@router.put("/menu/order")
async def update_menu_order(
    request: MenuOrderUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update menu items order and visibility.
    """
    session = get_session()
    try:
        for item_data in request.items:
            item = session.query(MenuItem).filter(
                MenuItem.item_id == item_data.item_id
            ).first()
            if item:
                item.order_index = item_data.order_index
                if item_data.visible is not None:
                    item.visible = item_data.visible

        session.commit()
        log.info(f"Menu order updated by {current_user.sub}")

        return success_response(message="Menu order updated successfully")

    finally:
        session.close()


@router.patch("/menu/{item_id}")
async def update_menu_item(
    item_id: str,
    request: MenuItemUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update a single menu item.
    """
    session = get_session()
    try:
        item = session.query(MenuItem).filter(MenuItem.item_id == item_id).first()
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Menu item {item_id} not found"
            )

        updates = request.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(item, key, value)

        session.commit()
        log.info(f"Menu item {item_id} updated by {current_user.sub}")

        return success_response(message=f"Menu item {item_id} updated successfully")

    finally:
        session.close()
