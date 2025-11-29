"""
Device Service
Handles device connections, credential management, and Netbox synchronization

This service abstracts device operations. Currently uses Netstacker API,
but will switch to direct Celery tasks in Phase 3.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

import database as db
from netbox_client import NetboxClient, get_netmiko_device_type

log = logging.getLogger(__name__)

# In-memory device cache
device_cache = {}
cache_timestamps = {}


def get_netbox_client() -> Optional[NetboxClient]:
    """Get configured Netbox client"""
    settings = db.get_all_settings()
    netbox_url = settings.get('netbox_url')
    netbox_token = settings.get('netbox_token')

    if not netbox_url:
        return None

    verify_ssl = settings.get('verify_ssl', False)
    if isinstance(verify_ssl, str):
        verify_ssl = verify_ssl.lower() in ('true', '1', 'yes')

    return NetboxClient(netbox_url, netbox_token, verify_ssl)


def get_default_credentials() -> Dict[str, str]:
    """
    Get default credentials from settings

    Returns:
        Dict with username, password, and optional secret
    """
    settings = db.get_all_settings()
    return {
        'username': settings.get('default_username', ''),
        'password': settings.get('default_password', ''),
        'secret': settings.get('default_enable_password', '')
    }


def get_device_credentials(device_name: str, override: Dict = None) -> Dict[str, str]:
    """
    Get credentials for a device

    Priority:
    1. Override passed in request (for one-time deployments)
    2. Device-specific credentials (manual device)
    3. Default credentials from settings

    Args:
        device_name: Device hostname
        override: Optional credential override dict

    Returns:
        Dict with username, password, and optional secret
    """
    # Priority 1: Override
    if override and override.get('username'):
        creds = {
            'username': override['username'],
            'password': override.get('password', ''),
        }
        if override.get('secret'):
            creds['secret'] = override['secret']
        return creds

    # Priority 2: Device-specific (manual device)
    manual_device = db.get_manual_device(device_name)
    if manual_device and manual_device.get('username'):
        creds = {
            'username': manual_device['username'],
            'password': manual_device.get('password', ''),
        }
        if manual_device.get('enable_password'):
            creds['secret'] = manual_device['enable_password']
        return creds

    # Priority 3: Default credentials
    return get_default_credentials()


def get_device_connection_info(device_name: str, credential_override: Dict = None) -> Optional[Dict]:
    """
    Get complete connection info for a device

    Looks up device in cache (Netbox) or manual devices,
    then applies appropriate credentials.

    Args:
        device_name: Device hostname
        credential_override: Optional dict with username/password override

    Returns:
        Dict with connection_args and device_info, or None if not found
    """
    device = None

    # Try cache first (Netbox devices)
    if device_cache:
        for cache_key, cache_entry in device_cache.items():
            if cache_entry and isinstance(cache_entry, dict) and 'devices' in cache_entry:
                cached_devices = cache_entry.get('devices', [])
                device = next((d for d in cached_devices if d.get('name') == device_name), None)
                if device:
                    log.info(f"Found device {device_name} in cache (key: {cache_key})")
                    break

    # Try manual devices
    if not device:
        manual = db.get_manual_device(device_name)
        if manual:
            device = {
                'name': manual['device_name'],
                'host': manual['host'],
                'device_type': manual['device_type'],
                'port': manual.get('port', 22),
                'platform': manual.get('device_type'),
                'manufacturer': manual.get('manufacturer'),
                'site': manual.get('site'),
            }
            log.info(f"Found device {device_name} in manual devices")

    # Fallback to Netbox lookup
    if not device:
        log.info(f"Device {device_name} not in cache, fetching from Netbox")
        netbox = get_netbox_client()
        if netbox:
            device = netbox.get_device_by_name(device_name)

    if not device or not device.get('name'):
        log.error(f"Device {device_name} not found")
        return None

    # Determine device type / platform
    device_type = device.get('device_type')
    if not device_type or isinstance(device_type, dict):
        # Need to determine from platform/manufacturer
        nornir_platform = device.get('config_context', {}).get('nornir', {}).get('platform')
        if not nornir_platform:
            platform = device.get('platform', {})
            manufacturer = device.get('device_type', {}).get('manufacturer', {}) if isinstance(device.get('device_type'), dict) else {}
            platform_name = platform.get('name') if isinstance(platform, dict) else None
            manufacturer_name = manufacturer.get('name') if isinstance(manufacturer, dict) else None
            device_type = get_netmiko_device_type(platform_name, manufacturer_name)
        else:
            device_type = nornir_platform

    # Get IP/hostname
    host = device.get('host')
    if not host:
        primary_ip = device.get('primary_ip', {}) or device.get('primary_ip4', {})
        if primary_ip:
            ip_addr_full = primary_ip.get('address', '')
            host = ip_addr_full.split('/')[0] if ip_addr_full else None
        if not host:
            host = device_name

    # Build connection args
    connection_args = {
        'device_type': device_type or 'cisco_ios',
        'host': host,
        'timeout': 30,
        'port': device.get('port', 22),
    }

    # Add credentials
    creds = get_device_credentials(device_name, credential_override)
    connection_args.update(creds)

    # Get platform info for response
    platform_info = device.get('platform', {})
    platform_name = platform_info.get('name') if isinstance(platform_info, dict) else ''

    return {
        'connection_args': connection_args,
        'device_info': {
            'name': device.get('name'),
            'platform': platform_name,
            'site': device.get('site', {}).get('name') if isinstance(device.get('site'), dict) else device.get('site')
        }
    }


def sync_devices_from_netbox(filters: List[Dict] = None) -> Dict[str, Any]:
    """
    Sync device list from Netbox

    Args:
        filters: Optional list of filter dicts with 'key' and 'value'

    Returns:
        Dict with devices list and metadata
    """
    netbox = get_netbox_client()
    if not netbox:
        return {'devices': [], 'error': 'Netbox not configured'}

    try:
        devices = netbox.get_devices_with_details(filters=filters)
        cache_key = 'netbox_devices'
        device_cache[cache_key] = {
            'devices': devices,
            'synced_at': datetime.now().isoformat()
        }
        cache_timestamps[cache_key] = datetime.now()

        return {
            'devices': devices,
            'count': len(devices),
            'synced_at': datetime.now().isoformat()
        }
    except Exception as e:
        log.error(f"Error syncing from Netbox: {e}")
        return {'devices': [], 'error': str(e)}


def get_cached_devices() -> List[Dict]:
    """Get devices from cache"""
    all_devices = []

    # Add cached Netbox devices
    for cache_key, cache_entry in device_cache.items():
        if cache_entry and isinstance(cache_entry, dict) and 'devices' in cache_entry:
            all_devices.extend(cache_entry.get('devices', []))

    # Add manual devices
    manual_devices = db.get_all_manual_devices()
    for manual in manual_devices:
        all_devices.append({
            'name': manual['device_name'],
            'id': None,
            'display': manual['device_name'],
            'device_type': manual['device_type'],
            'platform': manual.get('device_type'),
            'manufacturer': manual.get('manufacturer'),
            'site': manual.get('site'),
            'source': 'manual'
        })

    # Deduplicate by name
    seen = set()
    unique_devices = []
    for device in all_devices:
        if device['name'] not in seen:
            seen.add(device['name'])
            unique_devices.append(device)

    return sorted(unique_devices, key=lambda x: x['name'])


def clear_device_cache():
    """Clear the device cache"""
    global device_cache, cache_timestamps
    device_cache = {}
    cache_timestamps = {}
    log.info("Device cache cleared")
