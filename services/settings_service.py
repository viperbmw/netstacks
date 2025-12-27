"""
Settings Service for NetStacks

Business logic for application settings and menu configuration.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import database as db
from utils.exceptions import ValidationError, NotFoundError

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

    def get_all(self, mask_sensitive: bool = True) -> Dict[str, Any]:
        """
        Get all application settings.

        Args:
            mask_sensitive: If True, mask sensitive values like tokens/passwords

        Returns:
            Dict of all settings with proper type conversion
        """
        settings = self.DEFAULT_SETTINGS.copy()

        try:
            stored_settings = db.get_all_settings()
            if stored_settings:
                settings = self._parse_stored_settings(stored_settings, settings)
                log.debug("Loaded settings from database")
            else:
                log.warning("No settings found in database")
        except Exception as e:
            log.warning(f"Could not load settings from database: {e}")

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
        value = db.get_setting(key, default)

        if value is None:
            return default

        # Type conversion
        if key in self.JSON_FIELDS and isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default if default is not None else []

        if key in self.INT_FIELDS and isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default if default is not None else 0

        if key in self.BOOL_FIELDS and isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')

        return value

    def save(self, settings: Dict[str, Any]) -> bool:
        """
        Save application settings.

        Args:
            settings: Dict of settings to save

        Returns:
            True if successful

        Raises:
            ValidationError: If required fields are missing
        """
        # Validate required fields
        if not settings.get('netbox_url'):
            raise ValidationError(
                'NetBox URL is required',
                field_errors={'netbox_url': ['netbox_url is required']}
            )

        # Prepare settings for storage
        settings_to_save = {}

        for key, value in settings.items():
            if key not in self.DEFAULT_SETTINGS:
                continue  # Skip unknown keys

            # Convert types for storage
            if isinstance(value, bool):
                settings_to_save[key] = str(value).lower()
            elif isinstance(value, (list, dict)):
                settings_to_save[key] = json.dumps(value)
            else:
                settings_to_save[key] = str(value) if value is not None else ''

        # Save each setting to database
        for key, value in settings_to_save.items():
            db.set_setting(key, value)

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
        """
        if key not in self.DEFAULT_SETTINGS:
            raise ValidationError(f"Unknown setting: {key}")

        # Convert type for storage
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, (list, dict)):
            value = json.dumps(value)
        else:
            value = str(value) if value is not None else ''

        db.set_setting(key, value)
        log.info(f"Setting '{key}' updated")
        return True

    def _parse_stored_settings(
        self,
        stored: Dict[str, Any],
        defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse stored settings with proper type conversion."""
        result = defaults.copy()

        for key, value in stored.items():
            if key in self.JSON_FIELDS and isinstance(value, str):
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = defaults.get(key, [])
            elif key in self.INT_FIELDS and isinstance(value, str):
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = defaults.get(key, 0)
            elif key in self.BOOL_FIELDS and isinstance(value, str):
                result[key] = value.lower() in ('true', '1', 'yes')
            else:
                result[key] = value

        return result

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

    def get_all(self) -> List[Dict]:
        """
        Get all menu items ordered by position.

        Returns:
            List of menu item dicts
        """
        try:
            return db.get_menu_items()
        except Exception as e:
            log.error(f"Error getting menu items: {e}")
            raise

    def update_order(self, menu_items: List[Dict]) -> bool:
        """
        Update menu items order and visibility.

        Args:
            menu_items: List of menu item dicts with item_id, order_index, visible

        Returns:
            True if successful

        Raises:
            ValidationError: If menu_items is empty
        """
        if not menu_items:
            raise ValidationError('No menu items provided')

        try:
            db.update_menu_order(menu_items)
            log.info("Menu items updated successfully")
            return True
        except Exception as e:
            log.error(f"Error updating menu items: {e}")
            raise

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
            NotFoundError: If menu item not found
        """
        success = db.update_menu_item(item_id, label, icon, visible)
        if not success:
            raise NotFoundError(
                f"Menu item not found: {item_id}",
                resource_type='MenuItem',
                resource_id=item_id
            )
        log.info(f"Menu item '{item_id}' updated")
        return True
