"""
Override Service

Business logic for device-specific connection overrides.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import DeviceOverride

from app.schemas.overrides import DeviceOverrideUpdate

log = logging.getLogger(__name__)


class OverrideService:
    """Service for managing device overrides."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all device overrides."""
        overrides = self.session.query(DeviceOverride).order_by(
            DeviceOverride.device_name
        ).all()

        return [self._to_dict(o) for o in overrides]

    def get(self, device_name: str) -> Optional[Dict]:
        """Get override for a specific device."""
        override = self.session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).first()

        if override:
            return self._to_dict(override)
        return None

    def save(self, device_name: str, override: DeviceOverrideUpdate) -> Dict:
        """Save or update device override."""
        db_override = self.session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).first()

        if db_override:
            # Update existing
            update_data = override.model_dump(exclude_unset=True)

            # Handle empty strings - convert to None
            for key in ['device_type', 'host', 'username', 'password', 'secret', 'notes']:
                if key in update_data and update_data[key] == '':
                    update_data[key] = None

            # Handle numeric fields
            for key in ['port', 'timeout', 'conn_timeout', 'auth_timeout', 'banner_timeout']:
                if key in update_data:
                    if update_data[key] == '' or update_data[key] == 0:
                        update_data[key] = None

            for field, value in update_data.items():
                if hasattr(db_override, field):
                    setattr(db_override, field, value)

            db_override.updated_at = datetime.utcnow()
        else:
            # Create new
            db_override = DeviceOverride(
                device_name=device_name,
                device_type=override.device_type,
                host=override.host,
                port=override.port,
                username=override.username,
                password=override.password,
                secret=override.secret,
                timeout=override.timeout,
                conn_timeout=override.conn_timeout,
                auth_timeout=override.auth_timeout,
                banner_timeout=override.banner_timeout,
                notes=override.notes,
                disabled=override.disabled,
            )
            self.session.add(db_override)

        self.session.commit()
        log.info(f"Device override saved for {device_name}")
        return self._to_dict(db_override)

    def delete(self, device_name: str) -> bool:
        """Delete device override."""
        db_override = self.session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).first()

        if not db_override:
            return False

        self.session.delete(db_override)
        self.session.commit()

        log.info(f"Device override deleted for {device_name}")
        return True

    def _to_dict(self, override: DeviceOverride) -> Dict:
        """Convert override model to dict."""
        return {
            'device_name': override.device_name,
            'device_type': override.device_type,
            'host': override.host,
            'port': override.port,
            'username': override.username,
            'password': '****' if override.password else None,
            'secret': '****' if override.secret else None,
            'timeout': override.timeout,
            'conn_timeout': override.conn_timeout,
            'auth_timeout': override.auth_timeout,
            'banner_timeout': override.banner_timeout,
            'notes': override.notes,
            'disabled': override.disabled,
            'created_at': override.created_at.isoformat() if override.created_at else None,
            'updated_at': override.updated_at.isoformat() if override.updated_at else None,
        }
