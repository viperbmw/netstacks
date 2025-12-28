"""
Settings Service

Business logic for application settings and menu configuration.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import Setting, MenuItem

log = logging.getLogger(__name__)


class SettingsService:
    """
    Service for managing application settings.

    Handles:
    - NetBox integration settings
    - Default credentials
    - Cache configuration
    - Menu item customization
    """

    # Default settings structure
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

    # Fields that should be parsed as JSON
    JSON_FIELDS = ['netbox_filters']

    # Fields that should be parsed as integers
    INT_FIELDS = ['cache_ttl']

    # Fields that should be parsed as booleans
    BOOL_FIELDS = ['verify_ssl']

    # Sensitive fields that should be masked in responses
    SENSITIVE_FIELDS = ['netbox_token', 'default_password']

    def __init__(self, session: Session):
        self.session = session

    def get_all(self, mask_sensitive: bool = True) -> Dict[str, Any]:
        """
        Get all application settings.

        Args:
            mask_sensitive: If True, mask sensitive values like tokens/passwords

        Returns:
            Dict of all settings with proper type conversion
        """
        settings = self.DEFAULT_SETTINGS.copy()

        stored_settings = self.session.query(Setting).all()
        for s in stored_settings:
            if s.key in self.DEFAULT_SETTINGS:
                settings[s.key] = self._parse_value(s.key, s.value)

        # Add system timezone from environment
        settings['system_timezone'] = os.environ.get('TZ', 'UTC')

        if mask_sensitive:
            settings = self._mask_sensitive_fields(settings)

        return settings

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a single setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value with proper type conversion
        """
        setting = self.session.query(Setting).filter(Setting.key == key).first()

        if setting is None:
            return default

        return self._parse_value(key, setting.value)

    def save(self, settings: Dict[str, Any]) -> bool:
        """
        Save application settings.

        Args:
            settings: Dict of settings to save

        Returns:
            True if successful
        """
        for key, value in settings.items():
            if key not in self.DEFAULT_SETTINGS:
                continue

            # Convert types for storage
            serialized = self._serialize_value(key, value)

            # Upsert setting
            setting = self.session.query(Setting).filter(Setting.key == key).first()
            if setting:
                setting.value = serialized
            else:
                setting = Setting(key=key, value=serialized)
                self.session.add(setting)

        self.session.commit()
        log.info("Settings saved successfully")
        return True

    def update(self, key: str, value: Any) -> bool:
        """
        Update a single setting.

        Args:
            key: Setting key
            value: New value

        Returns:
            True if successful

        Raises:
            ValueError: If key is unknown
        """
        if key not in self.DEFAULT_SETTINGS:
            raise ValueError(f"Unknown setting: {key}")

        serialized = self._serialize_value(key, value)

        setting = self.session.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = serialized
        else:
            setting = Setting(key=key, value=serialized)
            self.session.add(setting)

        self.session.commit()
        log.info(f"Setting '{key}' updated")
        return True

    def _parse_value(self, key: str, value: str) -> Any:
        """Parse a stored setting value to its proper type."""
        if key in self.JSON_FIELDS and isinstance(value, str):
            try:
                return json.loads(value) if value else []
            except (json.JSONDecodeError, TypeError):
                return []

        if key in self.INT_FIELDS and isinstance(value, str):
            try:
                return int(value) if value else 0
            except (ValueError, TypeError):
                return 0

        if key in self.BOOL_FIELDS and isinstance(value, str):
            return value.lower() in ('true', '1', 'yes') if value else False

        return value

    def _serialize_value(self, key: str, value: Any) -> str:
        """Serialize a setting value for storage."""
        if isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value) if value is not None else ''

    def _mask_sensitive_fields(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in settings dict."""
        masked = settings.copy()
        for field in self.SENSITIVE_FIELDS:
            if field in masked and masked[field]:
                masked[field] = '****'
        return masked


class MenuService:
    """
    Service for managing navigation menu items.

    Handles:
    - Retrieving menu configuration
    - Updating menu order
    - Toggling menu item visibility
    """

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """
        Get all menu items ordered by position.

        Returns:
            List of menu item dicts
        """
        items = self.session.query(MenuItem).order_by(MenuItem.order_index).all()
        return [
            {
                'item_id': item.item_id,
                'label': item.label,
                'icon': item.icon,
                'url': item.url,
                'order_index': item.order_index,
                'visible': item.visible,
            }
            for item in items
        ]

    def update_order(self, menu_items: List[Dict]) -> bool:
        """
        Update menu items order and visibility.

        Args:
            menu_items: List of menu item dicts with item_id, order_index, visible

        Returns:
            True if successful

        Raises:
            ValueError: If menu_items is empty
        """
        if not menu_items:
            raise ValueError('No menu items provided')

        for item_data in menu_items:
            item = self.session.query(MenuItem).filter(
                MenuItem.item_id == item_data['item_id']
            ).first()
            if item:
                item.order_index = item_data.get('order_index', item.order_index)
                if 'visible' in item_data:
                    item.visible = item_data['visible']

        self.session.commit()
        log.info("Menu items updated successfully")
        return True

    def update_item(
        self,
        item_id: str,
        label: Optional[str] = None,
        icon: Optional[str] = None,
        visible: Optional[bool] = None
    ) -> bool:
        """
        Update a single menu item.

        Args:
            item_id: Menu item ID
            label: New label (optional)
            icon: New icon (optional)
            visible: New visibility (optional)

        Returns:
            True if successful

        Raises:
            ValueError: If menu item not found
        """
        item = self.session.query(MenuItem).filter(MenuItem.item_id == item_id).first()
        if not item:
            raise ValueError(f"Menu item not found: {item_id}")

        if label is not None:
            item.label = label
        if icon is not None:
            item.icon = icon
        if visible is not None:
            item.visible = visible

        self.session.commit()
        log.info(f"Menu item '{item_id}' updated")
        return True
