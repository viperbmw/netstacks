"""
Device Service

Business logic for device management.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import Device

from app.schemas.devices import DeviceCreate, DeviceUpdate

log = logging.getLogger(__name__)

# In-memory device cache
_device_cache = {
    'devices': [],
    'timestamp': None,
    'ttl': 300,  # 5 minutes default
    'sources': []
}


class DeviceService:
    """Service for device management."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(
        self,
        source: Optional[str] = None,
        device_type: Optional[str] = None,
        site: Optional[str] = None,
        refresh: bool = False,
    ) -> List[Dict]:
        """
        Get all devices with optional filtering.

        Args:
            source: Filter by source (manual, netbox)
            device_type: Filter by device type
            site: Filter by site
            refresh: Force refresh from database

        Returns:
            List of device dicts
        """
        query = self.session.query(Device)

        if source:
            query = query.filter(Device.source == source)
        if device_type:
            query = query.filter(Device.device_type == device_type)
        if site:
            query = query.filter(Device.site == site)

        devices = query.order_by(Device.name).all()

        return [self._to_dict(d) for d in devices]

    def get_cached(self) -> List[Dict]:
        """Get devices from cache only."""
        global _device_cache
        if not _device_cache.get('devices'):
            return []
        return _device_cache['devices']

    def clear_cache(self):
        """Clear the device cache."""
        global _device_cache
        _device_cache = {
            'devices': [],
            'timestamp': None,
            'ttl': 300,
            'sources': []
        }
        log.info("Device cache cleared")

    def get(self, device_name: str) -> Optional[Dict]:
        """Get a single device by name."""
        device = self.session.query(Device).filter(
            Device.name == device_name
        ).first()

        if device:
            return self._to_dict(device)
        return None

    def create(self, device: DeviceCreate) -> Dict:
        """Create a new device."""
        db_device = Device(
            name=device.name,
            host=device.host,
            device_type=device.device_type,
            port=device.port,
            username=device.username,
            password=device.password,
            enable_password=device.enable_password,
            description=device.description,
            manufacturer=device.manufacturer,
            model=device.model,
            platform=device.platform,
            site=device.site,
            tags=device.tags,
            source='manual',
        )
        self.session.add(db_device)
        self.session.commit()

        log.info(f"Device {device.name} created")
        return self._to_dict(db_device)

    def update(self, device_name: str, device: DeviceUpdate) -> Dict:
        """Update a device."""
        db_device = self.session.query(Device).filter(
            Device.name == device_name
        ).first()

        if not db_device:
            raise ValueError(f"Device not found: {device_name}")

        # Update only provided fields
        update_data = device.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(db_device, field):
                setattr(db_device, field, value)

        db_device.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"Device {device_name} updated")
        return self._to_dict(db_device)

    def delete(self, device_name: str) -> bool:
        """Delete a device."""
        db_device = self.session.query(Device).filter(
            Device.name == device_name
        ).first()

        if not db_device:
            return False

        self.session.delete(db_device)
        self.session.commit()

        log.info(f"Device {device_name} deleted")
        return True

    def _to_dict(self, device: Device) -> Dict:
        """Convert device model to dict."""
        return {
            'id': device.id,
            'name': device.name,
            'host': device.host,
            'device_type': device.device_type,
            'port': device.port,
            'description': device.description,
            'manufacturer': device.manufacturer,
            'model': device.model,
            'platform': device.platform,
            'site': device.site,
            'tags': device.tags or [],
            'source': device.source,
            'netbox_id': device.netbox_id,
            'last_synced_at': device.last_synced_at.isoformat() if device.last_synced_at else None,
            'created_at': device.created_at.isoformat() if device.created_at else None,
            'updated_at': device.updated_at.isoformat() if device.updated_at else None,
        }
