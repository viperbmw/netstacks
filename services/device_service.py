"""
Device Service
Handles device connections, credential management, and Netbox synchronization

This service abstracts device operations using Celery tasks for network automation.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

import db
from netbox_client import NetboxClient, get_netmiko_device_type

log = logging.getLogger(__name__)

# In-memory device cache (single source of truth)
device_cache = {
    'devices': [],
    'timestamp': None,
    'ttl': 300,  # 5 minutes default TTL
    'sources': []
}


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
    2. Device override from database (edited via UI)
    3. Device-specific credentials (manual device)
    4. Default credentials from settings

    Args:
        device_name: Device hostname
        override: Optional credential override dict

    Returns:
        Dict with username, password, and optional secret
    """
    # Priority 1: Override passed in request
    if override and override.get('username'):
        creds = {
            'username': override['username'],
            'password': override.get('password', ''),
        }
        if override.get('secret'):
            creds['secret'] = override['secret']
        return creds

    # Priority 2: Device override from database (edited via UI)
    device_override = db.get_device_override(device_name)
    if device_override and device_override.get('username'):
        creds = {
            'username': device_override['username'],
            'password': device_override.get('password', ''),
        }
        if device_override.get('secret'):
            creds['secret'] = device_override['secret']
        log.debug(f"Using device override credentials for {device_name}")
        return creds

    # Priority 3: Device-specific (manual device)
    manual_device = db.get_manual_device(device_name)
    if manual_device and manual_device.get('username'):
        creds = {
            'username': manual_device['username'],
            'password': manual_device.get('password', ''),
        }
        if manual_device.get('enable_password'):
            creds['secret'] = manual_device['enable_password']
        return creds

    # Priority 4: Default credentials
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
    if device_cache.get('devices'):
        cached_devices = device_cache['devices']
        device = next((d for d in cached_devices if d.get('name') == device_name), None)
        if device:
            log.debug(f"Found device {device_name} in cache")

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

    # Get IP/hostname - prefer IP address from primary_ip4 over hostname
    host = device.get('host')  # Already set from ip_address if available
    host_source = 'cached host' if host else None

    if not host:
        primary_ip = device.get('primary_ip') or device.get('primary_ip4') or device.get('ip_address')
        if primary_ip:
            # Handle both string (manual devices) and dict (NetBox) formats
            if isinstance(primary_ip, str):
                host = primary_ip.split('/')[0] if primary_ip else None
                host_source = 'primary_ip (string)'
            elif isinstance(primary_ip, dict):
                ip_addr_full = primary_ip.get('address', '')
                host = ip_addr_full.split('/')[0] if ip_addr_full else None
                host_source = 'primary_ip (dict)'
        if not host:
            host = device_name
            host_source = 'hostname fallback'

    # Build connection args
    connection_args = {
        'device_type': device_type or 'cisco_ios',
        'host': host,
        'timeout': 30,
        'port': device.get('port', 22),
    }
    log.info(f"Built connection_args for {device_name}: device_type={connection_args['device_type']}, host={connection_args['host']} ({host_source}), port={connection_args['port']}")

    # Apply device overrides from database (edited via UI)
    device_override = db.get_device_override(device_name)
    if device_override:
        log.debug(f"Applying device override for {device_name}")
        # Apply connection setting overrides
        if device_override.get('device_type'):
            connection_args['device_type'] = device_override['device_type']
        if device_override.get('host'):
            connection_args['host'] = device_override['host']
        if device_override.get('port'):
            connection_args['port'] = device_override['port']
        # Apply timeout overrides
        if device_override.get('timeout'):
            connection_args['timeout'] = device_override['timeout']
        if device_override.get('conn_timeout'):
            connection_args['conn_timeout'] = device_override['conn_timeout']
        if device_override.get('auth_timeout'):
            connection_args['auth_timeout'] = device_override['auth_timeout']
        if device_override.get('banner_timeout'):
            connection_args['banner_timeout'] = device_override['banner_timeout']

    # Add credentials (this also checks device overrides)
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


def is_cache_valid() -> bool:
    """Check if device cache is still valid"""
    if not device_cache.get('timestamp'):
        return False
    now = datetime.now().timestamp()
    return (now - device_cache['timestamp']) < device_cache.get('ttl', 300)


def get_devices(filters: List[Dict] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Get devices from cache or fetch fresh data.
    This is the main entry point for getting devices.

    Args:
        filters: Optional list of filter dicts with 'key' and 'value'
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Dict with devices list, cached flag, and sources
    """
    global device_cache

    # Return cached data if valid and not forcing refresh
    if not force_refresh and is_cache_valid() and device_cache.get('devices'):
        log.info(f"Returning cached device list ({len(device_cache['devices'])} devices)")
        return {
            'success': True,
            'devices': device_cache['devices'],
            'cached': True,
            'sources': device_cache.get('sources', [])
        }

    # Fetch fresh data
    all_devices = []
    sources_used = []

    # Always fetch manual devices from database
    log.info("Fetching manual devices...")
    manual_devices = db.get_all_manual_devices()
    for manual in manual_devices:
        all_devices.append({
            'name': manual['device_name'],
            'id': None,
            'display': manual['device_name'],
            'device_type': manual['device_type'],
            'host': manual.get('host'),
            'primary_ip': manual.get('host'),
            'port': manual.get('port', 22),
            'platform': manual.get('device_type'),
            'site': 'Manual',
            'status': 'Active',
            'source': 'manual'
        })
    log.info(f"Found {len(manual_devices)} manual devices")
    if len(manual_devices) > 0:
        sources_used.append('manual')

    # Fetch from Netbox if configured
    settings = db.get_all_settings()
    netbox_url = settings.get('netbox_url', '').strip()
    netbox_token = settings.get('netbox_token', '').strip()

    if netbox_url and netbox_token:
        try:
            log.info(f"Fetching device list from Netbox with filters: {filters}...")
            netbox = get_netbox_client()
            if netbox:
                netbox_devices = netbox.get_devices_with_details(filters=filters)
                for device in netbox_devices:
                    device['source'] = 'netbox'
                    # Use primary_ip4 as host for connectivity (not hostname)
                    if device.get('ip_address'):
                        device['host'] = device['ip_address']
                        log.debug(f"Device {device.get('name')} using IP {device['host']} for connectivity")
                all_devices.extend(netbox_devices)
                log.info(f"Found {len(netbox_devices)} Netbox devices")
                if len(netbox_devices) > 0:
                    sources_used.append('netbox')
        except Exception as e:
            log.warning(f"Could not fetch devices from Netbox: {e}")
    else:
        log.info("Netbox not configured, using manual devices only")

    # Update cache
    device_cache['devices'] = all_devices
    device_cache['timestamp'] = datetime.now().timestamp()
    device_cache['sources'] = sources_used

    log.info(f"Cached {len(all_devices)} total devices from sources: {', '.join(sources_used) if sources_used else 'none'}")

    return {
        'success': True,
        'devices': all_devices,
        'cached': False,
        'sources': sources_used
    }


def get_cached_devices() -> List[Dict]:
    """
    Get devices from cache only (does NOT fetch fresh data).
    Used by backup-all and other operations that should only work with cached devices.

    Returns:
        List of cached devices, empty if cache is empty/invalid
    """
    if not device_cache.get('devices'):
        return []
    return device_cache['devices']


def clear_device_cache():
    """Clear the device cache"""
    global device_cache
    device_cache = {
        'devices': [],
        'timestamp': None,
        'ttl': 300,
        'sources': []
    }
    log.info("Device cache cleared")
