"""
License Management Module for NetStacks Pro
Handles license key generation, validation, and enforcement
"""
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
import json
import logging
import database as db

log = logging.getLogger(__name__)

# Available feature flags
AVAILABLE_FEATURES = [
    'basic_deployment',       # Basic service deployment
    'service_stacks',         # Service stack management
    'advanced_validation',    # Advanced validation features
    'scheduled_deployments',  # Schedule deployments for later
    'audit_logging',          # Detailed audit trail
    'backup_restore',         # Config backup before changes
    'change_management',      # Approval workflows
    'advanced_reporting',     # Analytics and reports
    'api_access',             # REST API access
    'webhooks',               # Custom webhooks
    'rbac',                   # Role-based access control
    'multi_tenancy',          # Multiple organizations
]

# License type to feature mappings
LICENSE_FEATURES = {
    'trial': [
        'basic_deployment',
        'service_stacks',
    ],
    'standard': [
        'basic_deployment',
        'service_stacks',
        'advanced_validation',
        'api_access',
    ],
    'professional': [
        'basic_deployment',
        'service_stacks',
        'advanced_validation',
        'scheduled_deployments',
        'audit_logging',
        'backup_restore',
        'api_access',
        'webhooks',
    ],
    'enterprise': AVAILABLE_FEATURES,  # All features
}


def generate_license_key(company_name, license_type='standard'):
    """
    Generate a unique license key
    Format: NSPRO-XXXXX-XXXXX-XXXXX-XXXXX
    """
    # Create a unique identifier
    unique_string = f"{company_name}{datetime.now().isoformat()}{secrets.token_hex(8)}"
    hash_obj = hashlib.sha256(unique_string.encode())
    hash_hex = hash_obj.hexdigest()

    # Convert to base32 for readability (no ambiguous characters)
    key_bytes = bytes.fromhex(hash_hex[:40])  # Use first 40 chars of hash
    key_b32 = base64.b32encode(key_bytes).decode('utf-8')

    # Format as NSPRO-XXXXX-XXXXX-XXXXX-XXXXX
    key_parts = [key_b32[i:i+5] for i in range(0, 20, 5)]
    license_key = f"NSPRO-{'-'.join(key_parts)}"

    return license_key


def create_license(company_name, license_type='standard', contact_email='',
                   duration_days=365, max_devices=-1, max_users=-1, notes=''):
    """
    Create a new license

    Args:
        company_name: Name of the company
        license_type: Type of license (trial, standard, professional, enterprise)
        contact_email: Contact email for the license
        duration_days: Number of days until expiration (None for perpetual)
        max_devices: Maximum number of devices (-1 for unlimited)
        max_users: Maximum number of users (-1 for unlimited)
        notes: Additional notes about the license

    Returns:
        dict: License data including the generated key
    """
    license_key = generate_license_key(company_name, license_type)

    # Calculate expiration date
    expiration_date = None
    if duration_days:
        expiration_date = (datetime.now() + timedelta(days=duration_days)).isoformat()

    # Get features for this license type
    features = LICENSE_FEATURES.get(license_type, LICENSE_FEATURES['standard'])

    license_data = {
        'license_key': license_key,
        'company_name': company_name,
        'contact_email': contact_email,
        'license_type': license_type,
        'max_devices': max_devices,
        'max_users': max_users,
        'features': features,
        'issued_date': datetime.now().isoformat(),
        'expiration_date': expiration_date,
        'is_active': True,
        'notes': notes
    }

    # Save to database
    db.save_license(license_data)
    log.info(f"Created new {license_type} license for {company_name}: {license_key}")

    return license_data


def validate_license(license_key=None):
    """
    Validate a license

    Args:
        license_key: Specific license key to validate, or None to check active license

    Returns:
        dict: Validation result with 'valid', 'license', 'message', 'warnings'
    """
    if license_key:
        license_data = db.get_license(license_key)
    else:
        license_data = db.get_active_license()

    if not license_data:
        return {
            'valid': False,
            'license': None,
            'message': 'No valid license found. Please contact support to obtain a license.',
            'warnings': []
        }

    warnings = []

    # Check if license is active
    if not license_data['is_active']:
        return {
            'valid': False,
            'license': license_data,
            'message': 'License is deactivated.',
            'warnings': warnings
        }

    # Check expiration
    if license_data['expiration_date']:
        expiration = datetime.fromisoformat(license_data['expiration_date'])
        now = datetime.now()

        if now > expiration:
            return {
                'valid': False,
                'license': license_data,
                'message': f"License expired on {expiration.strftime('%Y-%m-%d')}.",
                'warnings': warnings
            }

        # Warn if expiring soon (within 30 days)
        days_until_expiration = (expiration - now).days
        if days_until_expiration <= 30:
            warnings.append(f"License expires in {days_until_expiration} days on {expiration.strftime('%Y-%m-%d')}.")

    return {
        'valid': True,
        'license': license_data,
        'message': 'License is valid.',
        'warnings': warnings
    }


def check_feature_enabled(feature_name):
    """
    Check if a specific feature is enabled in the active license

    Args:
        feature_name: Name of the feature to check

    Returns:
        bool: True if feature is enabled, False otherwise
    """
    validation = validate_license()

    if not validation['valid']:
        return False

    license_data = validation['license']
    return feature_name in license_data.get('features', [])


def check_device_limit():
    """
    Check if the device limit has been reached

    Returns:
        dict: {'allowed': bool, 'current': int, 'max': int, 'unlimited': bool}
    """
    validation = validate_license()

    if not validation['valid']:
        return {'allowed': False, 'current': 0, 'max': 0, 'unlimited': False}

    license_data = validation['license']
    max_devices = license_data.get('max_devices', -1)

    # Count devices from both manual devices and deployed services
    manual_devices = db.get_all_manual_devices()
    service_instances = db.get_all_service_instances()

    # Get unique devices from service instances
    service_devices = set(s['device'] for s in service_instances)
    manual_device_names = set(d['device_name'] for d in manual_devices)

    # Combine both sets
    all_devices = service_devices.union(manual_device_names)
    current_devices = len(all_devices)

    if max_devices == -1:
        # Unlimited
        return {'allowed': True, 'current': current_devices, 'max': -1, 'unlimited': True}

    return {
        'allowed': current_devices < max_devices,
        'current': current_devices,
        'max': max_devices,
        'unlimited': False
    }


def check_user_limit():
    """
    Check if the user limit has been reached

    Returns:
        dict: {'allowed': bool, 'current': int, 'max': int, 'unlimited': bool}
    """
    validation = validate_license()

    if not validation['valid']:
        return {'allowed': False, 'current': 0, 'max': 0, 'unlimited': False}

    license_data = validation['license']
    max_users = license_data.get('max_users', -1)

    users = db.get_all_users()
    current_users = len(users)

    if max_users == -1:
        # Unlimited
        return {'allowed': True, 'current': current_users, 'max': -1, 'unlimited': True}

    return {
        'allowed': current_users < max_users,
        'current': current_users,
        'max': max_users,
        'unlimited': False
    }


def get_license_status():
    """
    Get comprehensive license status information

    Returns:
        dict: Complete license status including validation, limits, features
    """
    validation = validate_license()

    status = {
        'valid': validation['valid'],
        'message': validation['message'],
        'warnings': validation['warnings'],
        'license': None,
        'device_limit': check_device_limit(),
        'user_limit': check_user_limit(),
        'features': {}
    }

    if validation['license']:
        license_data = validation['license']
        status['license'] = {
            'company_name': license_data['company_name'],
            'license_type': license_data['license_type'],
            'expiration_date': license_data['expiration_date'],
            'features': license_data['features']
        }

        # Check each available feature
        for feature in AVAILABLE_FEATURES:
            status['features'][feature] = feature in license_data['features']

    return status


def install_trial_license(company_name='Trial Company', contact_email=''):
    """
    Install a 30-day trial license

    Returns:
        dict: License data
    """
    return create_license(
        company_name=company_name,
        license_type='trial',
        contact_email=contact_email,
        duration_days=30,
        max_devices=10,
        max_users=3,
        notes='30-day trial license with limited features'
    )
