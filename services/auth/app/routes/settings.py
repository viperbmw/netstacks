"""
System settings routes
"""

import json
import logging
import os
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status, Depends

from netstacks_core.auth import get_current_user, TokenData
from netstacks_core.db import get_session, Setting, MenuItem, APIResource
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
    # Connection timeout settings
    'default_timeout': 30,
    'default_conn_timeout': 10,
    'default_auth_timeout': 10,
    'default_banner_timeout': 15,
    'system_timezone': 'UTC',
    # AI settings
    'ai_default_provider': '',
    'ai_default_model': '',
    'ai_default_temperature': 0.1,
    'ai_default_max_tokens': 4096,
    'ai_approval_timeout_minutes': 30,
}

# Field type definitions
JSON_FIELDS = ['netbox_filters']
INT_FIELDS = [
    'cache_ttl', 'ai_default_max_tokens', 'ai_approval_timeout_minutes',
    'default_timeout', 'default_conn_timeout', 'default_auth_timeout', 'default_banner_timeout'
]
FLOAT_FIELDS = ['ai_default_temperature']
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
    elif key in FLOAT_FIELDS:
        try:
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
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


@router.get("/", response_model=SettingsResponse)
@router.get("", response_model=SettingsResponse)
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


async def _do_update_settings(
    request: SettingsUpdate,
    current_user: TokenData
) -> SettingsResponse:
    """
    Internal function to update application settings.
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


@router.put("/", response_model=SettingsResponse)
@router.put("", response_model=SettingsResponse)
async def update_settings_put(
    request: SettingsUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """Update application settings via PUT."""
    return await _do_update_settings(request, current_user)


@router.post("/", response_model=SettingsResponse)
@router.post("", response_model=SettingsResponse)
async def update_settings_post(
    request: SettingsUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """Update application settings via POST."""
    return await _do_update_settings(request, current_user)


# =============================================================================
# API Resources Routes (must be before /{category} route)
# =============================================================================

def api_resource_to_dict(resource: APIResource) -> dict:
    """Convert APIResource model to dictionary."""
    return {
        "resource_id": resource.resource_id,
        "name": resource.name,
        "description": resource.description,
        "base_url": resource.base_url,
        "auth_type": resource.auth_type,
        "auth_token": "****" if resource.auth_token else None,
        "auth_username": resource.auth_username,
        "auth_password": "****" if resource.auth_password else None,
        "custom_headers": resource.custom_headers,
        "verify_ssl": resource.verify_ssl,
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
        "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
        "created_by": resource.created_by,
    }


@router.get("/api-resources")
async def list_api_resources(current_user: TokenData = Depends(get_current_user)):
    """List all API resources."""
    session = get_session()
    try:
        resources = session.query(APIResource).order_by(APIResource.name).all()
        return {"success": True, "resources": [api_resource_to_dict(r) for r in resources]}
    finally:
        session.close()


@router.get("/api-resources/{resource_id}")
async def get_api_resource(
    resource_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get a specific API resource."""
    session = get_session()
    try:
        resource = session.query(APIResource).filter(
            APIResource.resource_id == resource_id
        ).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API resource {resource_id} not found"
            )
        return success_response(data=api_resource_to_dict(resource))
    finally:
        session.close()


@router.post("/api-resources")
async def create_api_resource(
    request: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new API resource."""
    session = get_session()
    try:
        name = request.get("name")
        base_url = request.get("base_url")
        if not name or not base_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name and base_url are required"
            )
        existing = session.query(APIResource).filter(APIResource.name == name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API resource with name '{name}' already exists"
            )
        resource = APIResource(
            resource_id=str(uuid.uuid4()),
            name=name,
            description=request.get("description"),
            base_url=base_url,
            auth_type=request.get("auth_type"),
            auth_token=request.get("auth_token"),
            auth_username=request.get("auth_username"),
            auth_password=request.get("auth_password"),
            custom_headers=request.get("custom_headers"),
            verify_ssl=request.get("verify_ssl", True),
            created_by=current_user.sub,
        )
        session.add(resource)
        session.commit()
        log.info(f"API resource '{name}' created by {current_user.sub}")
        return success_response(
            message="API resource created successfully",
            data=api_resource_to_dict(resource)
        )
    finally:
        session.close()


@router.put("/api-resources/{resource_id}")
async def update_api_resource(
    resource_id: str,
    request: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Update an existing API resource."""
    session = get_session()
    try:
        resource = session.query(APIResource).filter(
            APIResource.resource_id == resource_id
        ).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API resource {resource_id} not found"
            )
        if "name" in request:
            existing = session.query(APIResource).filter(
                APIResource.name == request["name"],
                APIResource.resource_id != resource_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"API resource with name '{request['name']}' already exists"
                )
            resource.name = request["name"]
        if "description" in request:
            resource.description = request["description"]
        if "base_url" in request:
            resource.base_url = request["base_url"]
        if "auth_type" in request:
            resource.auth_type = request["auth_type"]
        if "auth_token" in request and request["auth_token"] != "****":
            resource.auth_token = request["auth_token"]
        if "auth_username" in request:
            resource.auth_username = request["auth_username"]
        if "auth_password" in request and request["auth_password"] != "****":
            resource.auth_password = request["auth_password"]
        if "custom_headers" in request:
            resource.custom_headers = request["custom_headers"]
        if "verify_ssl" in request:
            resource.verify_ssl = request["verify_ssl"]
        session.commit()
        log.info(f"API resource '{resource.name}' updated by {current_user.sub}")
        return success_response(
            message="API resource updated successfully",
            data=api_resource_to_dict(resource)
        )
    finally:
        session.close()


@router.delete("/api-resources/{resource_id}")
async def delete_api_resource(
    resource_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete an API resource."""
    session = get_session()
    try:
        resource = session.query(APIResource).filter(
            APIResource.resource_id == resource_id
        ).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API resource {resource_id} not found"
            )
        name = resource.name
        session.delete(resource)
        session.commit()
        log.info(f"API resource '{name}' deleted by {current_user.sub}")
        return success_response(message="API resource deleted successfully")
    finally:
        session.close()


# =============================================================================
# Category route (catch-all, must be LAST)
# =============================================================================

@router.get("/{category}")
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
        'ai': ['ai_default_provider', 'ai_default_model', 'ai_default_temperature', 'ai_default_max_tokens', 'ai_approval_timeout_minutes'],
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


# =============================================================================
# Assistant Config Routes
# =============================================================================

@router.get("/credentials/default")
async def get_default_credentials(current_user: TokenData = Depends(get_current_user)):
    """
    Get default device credentials and timeout settings (unmasked).

    This endpoint returns the actual credentials and connection timeout settings
    for internal service-to-service communication (e.g., devices service testing connectivity).
    """
    session = get_session()
    try:
        default_username = ''
        default_password = ''
        default_timeout = 30
        default_conn_timeout = 10
        default_auth_timeout = 10
        default_banner_timeout = 15

        username_setting = session.query(Setting).filter(Setting.key == 'default_username').first()
        if username_setting:
            default_username = username_setting.value or ''

        password_setting = session.query(Setting).filter(Setting.key == 'default_password').first()
        if password_setting:
            default_password = password_setting.value or ''

        # Load timeout settings
        timeout_setting = session.query(Setting).filter(Setting.key == 'default_timeout').first()
        if timeout_setting:
            default_timeout = int(timeout_setting.value) if timeout_setting.value else 30

        conn_timeout_setting = session.query(Setting).filter(Setting.key == 'default_conn_timeout').first()
        if conn_timeout_setting:
            default_conn_timeout = int(conn_timeout_setting.value) if conn_timeout_setting.value else 10

        auth_timeout_setting = session.query(Setting).filter(Setting.key == 'default_auth_timeout').first()
        if auth_timeout_setting:
            default_auth_timeout = int(auth_timeout_setting.value) if auth_timeout_setting.value else 10

        banner_timeout_setting = session.query(Setting).filter(Setting.key == 'default_banner_timeout').first()
        if banner_timeout_setting:
            default_banner_timeout = int(banner_timeout_setting.value) if banner_timeout_setting.value else 15

        return success_response(data={
            'default_username': default_username,
            'default_password': default_password,
            'default_timeout': default_timeout,
            'default_conn_timeout': default_conn_timeout,
            'default_auth_timeout': default_auth_timeout,
            'default_banner_timeout': default_banner_timeout,
        })

    finally:
        session.close()


@router.get("/assistant/config")
async def get_assistant_config(current_user: TokenData = Depends(get_current_user)):
    """
    Get AI Assistant configuration.
    """
    session = get_session()
    try:
        config = {}
        assistant_keys = [
            'assistant_enabled',
            'assistant_llm_provider',
            'assistant_llm_model',
        ]

        for key in assistant_keys:
            setting = session.query(Setting).filter(Setting.key == key).first()
            if setting:
                clean_key = key.replace('assistant_', '')
                if clean_key == 'llm_provider':
                    clean_key = 'provider'
                elif clean_key == 'llm_model':
                    clean_key = 'model'

                # Parse value
                value = setting.value
                if value and value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                config[clean_key] = value

        return {"config": config}

    finally:
        session.close()


@router.post("/assistant/config")
async def save_assistant_config(
    request: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Save AI Assistant configuration.
    """
    session = get_session()
    try:
        settings_map = {
            'enabled': 'assistant_enabled',
            'provider': 'assistant_llm_provider',
            'model': 'assistant_llm_model',
        }

        for key, db_key in settings_map.items():
            if key in request:
                value = request[key]
                if isinstance(value, bool):
                    value = 'true' if value else 'false'
                elif not isinstance(value, str):
                    value = str(value)

                setting = session.query(Setting).filter(Setting.key == db_key).first()
                if setting:
                    setting.value = value
                else:
                    setting = Setting(key=db_key, value=value)
                    session.add(setting)

        session.commit()
        log.info(f"Assistant config updated by {current_user.sub}")

        return success_response(message="Assistant configuration saved")

    finally:
        session.close()
