"""
License Verification Module for NetStacks Pro (RSA-signed licenses)
Verifies licenses using embedded public key - NO private key needed
"""

import json
import base64
from datetime import datetime
import logging
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

log = logging.getLogger(__name__)

# PUBLIC KEY - Embedded in application (safe to be public)
# This is used to VERIFY licenses only, cannot create licenses
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoRTZvswqeVC8EnjM0wIw
lmOM8neiwb9wIPzaGbOez/YgJsMCgPxLZ8KS4UNbZfV1+R6aBLZM1pbGiHUuqYS5
gNSFYYxsc/dMJfm/Cs0GAUq+pzfzDhqxhb6Yc6tBgzhaqYDj1qowI4OCS5hq9CVI
qU/qwt+SHLGEJZa9qGp86d+gPt4e1/Zipfh4NUgefI36Vs4O+y3rg+iL1NHImhib
tz1NhvLIB61SM+kkG0gap4L+HC0jxK8o9z+L1toFXfRFYps+F6uDem2frABKz7F2
At5pcNZjSXSA7AEva5yIYHBCj/dsB++ssGGHsyJXnDKZd3vn4ZWkgkejagDkvW2r
vwIDAQAB
-----END PUBLIC KEY-----"""


def load_public_key():
    """Load the embedded RSA public key"""
    try:
        public_key = serialization.load_pem_public_key(
            PUBLIC_KEY_PEM.encode('utf-8')
        )
        return public_key
    except Exception as e:
        log.error(f"Failed to load public key: {e}")
        return None


def verify_rsa_license(license_key):
    """
    Verify an RSA-signed license (v2 format)

    Args:
        license_key: License key in format NSPRO-v2-{base64}

    Returns:
        dict: Validation result with 'valid', 'license_data', 'message', 'warnings'
    """
    try:
        # Check format
        if not license_key.startswith('NSPRO-v2-'):
            return {
                'valid': False,
                'license_data': None,
                'message': 'Invalid license key format. This key is not a valid RSA-signed license.',
                'warnings': []
            }

        # Extract base64 data
        b64_data = license_key[9:]  # Remove 'NSPRO-v2-' prefix

        # Decode base64
        try:
            package_json = base64.b64decode(b64_data).decode('utf-8')
            license_package = json.loads(package_json)
        except Exception as e:
            log.error(f"Failed to decode license: {e}")
            return {
                'valid': False,
                'license_data': None,
                'message': 'Invalid license key. Unable to decode license data.',
                'warnings': []
            }

        # Extract data and signature
        license_data = license_package.get('data', {})
        signature_b64 = license_package.get('signature', '')

        if not license_data or not signature_b64:
            return {
                'valid': False,
                'license_data': None,
                'message': 'Invalid license key. Missing required data or signature.',
                'warnings': []
            }

        # Decode signature
        try:
            signature = base64.b64decode(signature_b64)
        except Exception as e:
            log.error(f"Failed to decode signature: {e}")
            return {
                'valid': False,
                'license_data': None,
                'message': 'Invalid license key. Corrupted signature.',
                'warnings': []
            }

        # Load public key
        public_key = load_public_key()
        if not public_key:
            return {
                'valid': False,
                'license_data': None,
                'message': 'System error: Unable to load verification key.',
                'warnings': []
            }

        # Verify signature
        try:
            # Re-create the exact JSON that was signed
            license_json = json.dumps(license_data, sort_keys=True)
            license_bytes = license_json.encode('utf-8')

            # Verify RSA signature
            public_key.verify(
                signature,
                license_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            # Signature is valid! License is authentic
            log.info(f"License signature verified successfully for {license_data.get('company_name')}")

        except InvalidSignature:
            log.warning("License signature verification failed - invalid signature")
            return {
                'valid': False,
                'license_data': None,
                'message': 'Invalid license key. This license has been tampered with or is counterfeit.',
                'warnings': []
            }
        except Exception as e:
            log.error(f"Signature verification error: {e}")
            return {
                'valid': False,
                'license_data': None,
                'message': f'License verification failed: {str(e)}',
                'warnings': []
            }

        # License signature is valid - now check expiration and other constraints
        warnings = []

        # Check expiration date
        expiration_date_str = license_data.get('expiration_date')
        if expiration_date_str:
            try:
                expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d')
                now = datetime.now()

                if now > expiration_date:
                    return {
                        'valid': False,
                        'license_data': license_data,
                        'message': f"License expired on {expiration_date.strftime('%Y-%m-%d')}.",
                        'warnings': warnings
                    }

                # Warn if expiring soon (within 30 days)
                days_until_expiration = (expiration_date - now).days
                if 0 < days_until_expiration <= 30:
                    warnings.append(f"License expires in {days_until_expiration} days")
                elif 0 < days_until_expiration <= 7:
                    warnings.append(f"⚠️ License expires in {days_until_expiration} days - renewal required soon!")

            except Exception as e:
                log.error(f"Error parsing expiration date: {e}")
                warnings.append("Unable to parse license expiration date")

        # License is valid and not expired
        return {
            'valid': True,
            'license_data': license_data,
            'message': f"License valid for {license_data.get('company_name')} ({license_data.get('tier_name', license_data.get('license_type')).title()})",
            'warnings': warnings
        }

    except Exception as e:
        log.error(f"Unexpected error verifying license: {e}", exc_info=True)
        return {
            'valid': False,
            'license_data': None,
            'message': f'License verification error: {str(e)}',
            'warnings': []
        }


def get_license_features(license_data):
    """
    Extract features from verified license data

    Args:
        license_data: Decrypted and verified license data dict

    Returns:
        list: List of enabled features
    """
    return license_data.get('features', [])


def get_license_limits(license_data):
    """
    Extract limits from verified license data

    Args:
        license_data: Decrypted and verified license data dict

    Returns:
        dict: Limits (max_devices, max_users)
    """
    return {
        'max_devices': license_data.get('max_devices', -1),
        'max_users': license_data.get('max_users', -1)
    }
