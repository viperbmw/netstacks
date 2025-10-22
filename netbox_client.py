"""
Netbox API client for fetching device information
"""
import requests
from typing import List, Dict, Optional
import logging

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
    """
    Determine netmiko device_type from platform or manufacturer

    Args:
        platform_name: Netbox platform name (e.g., "junos", "ios")
        manufacturer_name: Netbox manufacturer name (e.g., "Juniper", "Cisco")

    Returns:
        Netmiko device_type string, defaults to 'cisco_ios' if unknown
    """
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
    log.warning(f"Unknown platform '{platform_name}' or manufacturer '{manufacturer_name}', defaulting to cisco_ios")
    return 'cisco_ios'


class NetboxClient:
    def __init__(self, base_url: str, token: str = None, verify_ssl: bool = True):
        """
        Initialize Netbox client

        Args:
            base_url: Netbox base URL (e.g., https://netbox.example.com)
            token: Optional API token for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()

        if self.token:
            self.session.headers.update({
                'Authorization': f'Token {token}',
                'Content-Type': 'application/json'
            })

    def get_devices(self, brief: bool = True, limit: int = 1000, manufacturer_ids: list = None, filters: list = None) -> List[Dict]:
        """
        Fetch all devices from Netbox

        Args:
            brief: Use brief format for faster response
            limit: Number of results per page (default 1000 for faster pagination)
            manufacturer_ids: List of manufacturer IDs to filter (optional, no default)
            filters: List of filter dicts with 'key' and 'value' (e.g., [{'key': 'tag', 'value': 'production'}])
                     Supports multiple filters with same key (e.g., multiple manufacturer_id filters)

        Returns:
            List of device dictionaries with name, id, and other metadata
        """
        try:
            # Build query string
            query_parts = []
            if brief:
                query_parts.append('brief=true')
            if limit:
                query_parts.append(f'limit={limit}')

            # Only add manufacturer_ids if explicitly provided
            if manufacturer_ids:
                for mid in manufacturer_ids:
                    query_parts.append(f'manufacturer_id={mid}')

            # Add custom filters from settings (supports multiple values for same key)
            if filters:
                for f in filters:
                    if isinstance(f, dict) and 'key' in f and 'value' in f:
                        query_parts.append(f"{f['key']}={f['value']}")
                log.info(f"Applying Netbox filters: {filters}")

            url = f"{self.base_url}/api/dcim/devices/?{'&'.join(query_parts)}"

            response = self.session.get(url, verify=self.verify_ssl, timeout=30)
            response.raise_for_status()

            data = response.json()
            devices = data.get('results', [])

            log.info(f"Fetched {len(devices)} devices from Netbox (total count: {data.get('count', 0)})")

            # Handle pagination if there are more results
            while data.get('next'):
                log.info(f"Fetching next page: {data['next']}")
                response = self.session.get(data['next'], verify=self.verify_ssl, timeout=30)
                response.raise_for_status()
                data = response.json()
                devices.extend(data.get('results', []))

            log.info(f"Total devices fetched: {len(devices)}")
            return devices

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching devices from Netbox: {e}")
            return []

    def get_device_names(self) -> List[str]:
        """
        Get a simple list of device names

        Returns:
            List of device name strings
        """
        devices = self.get_devices()
        return sorted([device.get('name', '') for device in devices if device.get('name')])

    def get_device_by_name(self, device_name: str) -> Dict:
        """
        Get full device details by name (not brief format)

        Args:
            device_name: The device hostname

        Returns:
            Device dictionary with platform, manufacturer, etc.
        """
        try:
            url = f"{self.base_url}/api/dcim/devices?name={device_name}"
            response = self.session.get(url, verify=self.verify_ssl, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if results:
                return results[0]
            else:
                log.warning(f"Device not found: {device_name}")
                return {}
        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching device {device_name}: {e}")
            return {}

    def get_devices_with_details(self, filters: list = None) -> List[Dict]:
        """
        Get devices with relevant details for the GUI
        Uses non-brief format to get platform/manufacturer info
        All filtering is now controlled via the filters parameter from settings

        Args:
            filters: Optional list of filter dicts with 'key' and 'value'

        Returns:
            List of dicts containing name, id, display, device_type, etc.
        """
        # Use non-brief format to get platform/manufacturer data
        devices = self.get_devices(brief=False, filters=filters)
        device_list = []

        for device in devices:
            device_name = device.get('name', '')

            # Extract platform information
            platform = device.get('platform')
            manufacturer = device.get('device_type', {}).get('manufacturer') if isinstance(device.get('device_type'), dict) else None

            # Determine netmiko device_type
            platform_name = platform.get('name') if isinstance(platform, dict) else None
            manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None
            device_type = get_netmiko_device_type(platform_name, manufacturer_name)

            device_list.append({
                'name': device_name,
                'id': device.get('id'),
                'display': device.get('display', device_name),
                'url': device.get('url', ''),
                'device_type': device_type,
                'platform': platform_name,
                'manufacturer': manufacturer_name
            })

        # Remove duplicates and sort by name
        seen = set()
        unique_devices = []
        for device in device_list:
            if device['name'] and device['name'] not in seen:
                seen.add(device['name'])
                unique_devices.append(device)

        return sorted(unique_devices, key=lambda x: x['name'])
