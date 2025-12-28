"""
NetBox Service

Business logic for NetBox integration and device sync.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from netstacks_core.db import Device, Setting

log = logging.getLogger(__name__)

# Platform/Manufacturer to Netmiko device_type mapping
PLATFORM_TO_NETMIKO = {
    # Juniper
    'juniper_junos': 'juniper_junos',
    'junos': 'juniper_junos',
    'juniper': 'juniper_junos',
    # Cisco IOS/IOS-XE
    'cisco_ios': 'cisco_ios',
    'ios': 'cisco_ios',
    'cisco': 'cisco_ios',
    'catalyst': 'cisco_ios',
    # Cisco IOS-XR
    'cisco_xr': 'cisco_xr',
    'iosxr': 'cisco_xr',
    'ios-xr': 'cisco_xr',
    # Cisco NX-OS
    'cisco_nxos': 'cisco_nxos',
    'nxos': 'cisco_nxos',
    'nexus': 'cisco_nxos',
    # Arista
    'arista_eos': 'arista_eos',
    'eos': 'arista_eos',
    'arista': 'arista_eos',
    # HP/HPE
    'hp_comware': 'hp_comware',
    'hp_procurve': 'hp_procurve',
    'hpe': 'hp_comware',
    # Dell
    'dell_os10': 'dell_os10',
    'dell_force10': 'dell_force10',
    'dell': 'dell_os10',
}


def get_netmiko_device_type(platform_name: Optional[str], manufacturer_name: Optional[str]) -> str:
    """Determine netmiko device_type from platform or manufacturer."""
    # Try platform first
    if platform_name:
        platform_lower = platform_name.lower().strip()
        if platform_lower in PLATFORM_TO_NETMIKO:
            return PLATFORM_TO_NETMIKO[platform_lower]

    # Try manufacturer as fallback
    if manufacturer_name:
        manufacturer_lower = manufacturer_name.lower().strip()
        if manufacturer_lower in PLATFORM_TO_NETMIKO:
            return PLATFORM_TO_NETMIKO[manufacturer_lower]

    # Default to cisco_ios
    log.warning(
        f"Unknown platform '{platform_name}' or manufacturer '{manufacturer_name}', "
        "defaulting to cisco_ios"
    )
    return 'cisco_ios'


class NetBoxService:
    """Service for NetBox integration."""

    def __init__(self, session: Session):
        self.session = session
        self._client = None

    def get_status(self) -> Dict:
        """Get NetBox configuration and connectivity status."""
        config = self._get_config()

        status = {
            'configured': bool(config.get('url') and config.get('token')),
            'url': config.get('url'),
            'verify_ssl': config.get('verify_ssl', False),
            'connected': False,
            'error': None,
        }

        if status['configured']:
            try:
                # Test connectivity
                headers = {'Authorization': f"Token {config['token']}"}
                response = requests.get(
                    f"{config['url'].rstrip('/')}/api/status/",
                    headers=headers,
                    verify=config.get('verify_ssl', False),
                    timeout=10
                )
                response.raise_for_status()
                status['connected'] = True
                status['version'] = response.json().get('netbox-version')
            except requests.RequestException as e:
                status['error'] = str(e)
                log.error(f"NetBox connectivity test failed: {e}")

        return status

    def sync_devices(self, filters: Optional[List[Dict]] = None) -> Dict:
        """
        Sync devices from NetBox to the database.

        Args:
            filters: Optional list of filter dicts with 'key' and 'value'

        Returns:
            Dict with sync results
        """
        config = self._get_config()
        if not config.get('url') or not config.get('token'):
            return {
                'success': False,
                'error': 'NetBox not configured',
                'synced': 0,
                'created': 0,
                'updated': 0,
            }

        # Fetch devices from NetBox
        netbox_devices = self._fetch_from_netbox(config, filters)

        created = 0
        updated = 0

        for nb_device in netbox_devices:
            device_name = nb_device.get('name')
            if not device_name:
                continue

            # Check if device exists
            existing = self.session.query(Device).filter(
                Device.name == device_name
            ).first()

            # Extract platform/manufacturer for device type
            platform = nb_device.get('platform')
            manufacturer = nb_device.get('device_type', {}).get('manufacturer') if isinstance(
                nb_device.get('device_type'), dict
            ) else None

            platform_name = platform.get('name') if isinstance(platform, dict) else None
            manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None
            device_type = get_netmiko_device_type(platform_name, manufacturer_name)

            # Get primary IP
            primary_ip = nb_device.get('primary_ip') or nb_device.get('primary_ip4')
            host = None
            if primary_ip:
                if isinstance(primary_ip, str):
                    host = primary_ip.split('/')[0]
                elif isinstance(primary_ip, dict):
                    host = primary_ip.get('address', '').split('/')[0]

            if not host:
                host = device_name

            # Get site
            site = nb_device.get('site', {})
            site_name = site.get('name') if isinstance(site, dict) else None

            if existing:
                # Update existing device
                existing.host = host
                existing.device_type = device_type
                existing.platform = platform_name
                existing.manufacturer = manufacturer_name
                existing.site = site_name
                existing.netbox_id = nb_device.get('id')
                existing.last_synced_at = datetime.utcnow()
                existing.source = 'netbox'
                updated += 1
            else:
                # Create new device
                new_device = Device(
                    name=device_name,
                    host=host,
                    device_type=device_type,
                    port=22,
                    platform=platform_name,
                    manufacturer=manufacturer_name,
                    site=site_name,
                    source='netbox',
                    netbox_id=nb_device.get('id'),
                    last_synced_at=datetime.utcnow(),
                )
                self.session.add(new_device)
                created += 1

        self.session.commit()

        log.info(f"NetBox sync complete: {created} created, {updated} updated")
        return {
            'success': True,
            'synced': len(netbox_devices),
            'created': created,
            'updated': updated,
        }

    def fetch_devices(self, filters: Optional[List[Dict]] = None) -> List[Dict]:
        """Fetch devices directly from NetBox without syncing."""
        config = self._get_config()
        if not config.get('url') or not config.get('token'):
            return []

        return self._fetch_from_netbox(config, filters)

    def get_connections(self, device_names: List[str]) -> List[Dict]:
        """Get network connections between devices from NetBox."""
        config = self._get_config()
        if not config.get('url') or not config.get('token'):
            return []

        connections = []
        device_name_set = set(device_names)
        headers = {'Authorization': f"Token {config['token']}"}
        base_url = config['url'].rstrip('/')
        verify_ssl = config.get('verify_ssl', False)

        try:
            all_interfaces = []

            for device_name in device_names:
                response = requests.get(
                    f"{base_url}/api/dcim/interfaces/",
                    headers=headers,
                    params={'device': device_name, 'limit': 1000},
                    verify=verify_ssl,
                    timeout=30
                )
                response.raise_for_status()
                interfaces = response.json().get('results', [])
                all_interfaces.extend(interfaces)

            log.info(f"Fetched {len(all_interfaces)} interfaces for {len(device_names)} devices")

            # Process connections
            seen_connections = set()

            for interface in all_interfaces:
                device = interface.get('device', {})
                device_name = device.get('name')

                link_peers = interface.get('link_peers') or interface.get('connected_endpoints') or []

                for peer in link_peers:
                    peer_device = peer.get('device', {})
                    peer_device_name = peer_device.get('name')

                    if peer_device_name and peer_device_name in device_name_set:
                        conn_key = tuple(sorted([device_name, peer_device_name]))

                        if conn_key not in seen_connections:
                            seen_connections.add(conn_key)
                            connections.append({
                                'source': device_name,
                                'target': peer_device_name,
                                'source_interface': interface.get('name'),
                                'target_interface': peer.get('name'),
                                'cable_id': interface.get('cable', {}).get('id') if isinstance(
                                    interface.get('cable'), dict
                                ) else None
                            })

            log.info(f"Found {len(connections)} connections")

        except Exception as e:
            log.error(f"Error fetching connections: {e}")

        return connections

    def _get_config(self) -> Dict:
        """Get NetBox configuration from settings."""
        settings = {}

        stored = self.session.query(Setting).filter(
            Setting.key.in_(['netbox_url', 'netbox_token', 'verify_ssl', 'netbox_filters'])
        ).all()

        for s in stored:
            if s.key == 'verify_ssl':
                settings[s.key] = s.value.lower() in ('true', '1', 'yes') if s.value else False
            elif s.key == 'netbox_filters':
                try:
                    import json
                    settings[s.key] = json.loads(s.value) if s.value else []
                except:
                    settings[s.key] = []
            else:
                settings[s.key] = s.value

        return {
            'url': settings.get('netbox_url', ''),
            'token': settings.get('netbox_token', ''),
            'verify_ssl': settings.get('verify_ssl', False),
            'filters': settings.get('netbox_filters', []),
        }

    def _fetch_from_netbox(self, config: Dict, filters: Optional[List[Dict]] = None) -> List[Dict]:
        """Fetch devices from NetBox API."""
        headers = {'Authorization': f"Token {config['token']}"}
        base_url = config['url'].rstrip('/')
        verify_ssl = config.get('verify_ssl', False)

        # Build query params
        params = {'limit': 1000}

        # Apply filters
        if filters:
            for f in filters:
                if isinstance(f, dict) and 'key' in f and 'value' in f:
                    params[f['key']] = f['value']

        try:
            devices = []
            url = f"{base_url}/api/dcim/devices/"

            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=verify_ssl,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            devices = data.get('results', [])

            # Handle pagination
            while data.get('next'):
                response = requests.get(
                    data['next'],
                    headers=headers,
                    verify=verify_ssl,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                devices.extend(data.get('results', []))

            log.info(f"Fetched {len(devices)} devices from NetBox")
            return devices

        except requests.RequestException as e:
            log.error(f"Error fetching devices from NetBox: {e}")
            return []
