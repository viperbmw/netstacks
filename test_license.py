#!/usr/bin/env python3
"""
Test script for NetStacks Pro licensing system
"""
import os
import sys
import tempfile

# Create a temporary database for testing
test_db = tempfile.mktemp(suffix='.db')
os.environ['DB_FILE'] = test_db

import database as db
import license_manager

def test_database_init():
    """Test database initialization"""
    print("Testing database initialization...")
    db.init_db()
    print("✓ Database initialized successfully")

def test_license_generation():
    """Test license key generation"""
    print("\nTesting license generation...")

    # Generate trial license
    trial_license = license_manager.create_license(
        company_name="Test Company",
        license_type="trial",
        contact_email="test@example.com",
        duration_days=30,
        max_devices=10,
        max_users=3
    )

    print(f"✓ Trial license generated: {trial_license['license_key']}")
    print(f"  Company: {trial_license['company_name']}")
    print(f"  Type: {trial_license['license_type']}")
    print(f"  Features: {', '.join(trial_license['features'])}")

    # Generate professional license
    pro_license = license_manager.create_license(
        company_name="Pro Company",
        license_type="professional",
        contact_email="pro@example.com",
        duration_days=365,
        max_devices=-1,
        max_users=-1
    )

    print(f"✓ Professional license generated: {pro_license['license_key']}")
    print(f"  Company: {pro_license['company_name']}")
    print(f"  Type: {pro_license['license_type']}")
    print(f"  Features: {len(pro_license['features'])} features")

    return trial_license, pro_license

def test_license_validation(trial_license, pro_license):
    """Test license validation"""
    print("\nTesting license validation...")

    # Validate trial license
    validation = license_manager.validate_license(trial_license['license_key'])
    assert validation['valid'], "Trial license should be valid"
    print(f"✓ Trial license validation passed")
    print(f"  Message: {validation['message']}")

    # Validate professional license
    validation = license_manager.validate_license(pro_license['license_key'])
    assert validation['valid'], "Professional license should be valid"
    print(f"✓ Professional license validation passed")

    return True

def test_feature_checks(pro_license):
    """Test feature availability checks"""
    print("\nTesting feature checks...")

    # Activate the professional license
    db.activate_license(pro_license['license_key'])

    # Test feature checks
    features_to_test = [
        'basic_deployment',
        'service_stacks',
        'advanced_validation',
        'webhooks',
        'api_access'
    ]

    for feature in features_to_test:
        enabled = license_manager.check_feature_enabled(feature)
        status = "✓" if enabled else "✗"
        print(f"  {status} {feature}: {'enabled' if enabled else 'disabled'}")

    print("✓ Feature checks completed")

def test_license_limits():
    """Test device and user limits"""
    print("\nTesting license limits...")

    device_limit = license_manager.check_device_limit()
    print(f"✓ Device limit check:")
    print(f"  Current: {device_limit['current']}")
    print(f"  Max: {'Unlimited' if device_limit['unlimited'] else device_limit['max']}")
    print(f"  Allowed: {device_limit['allowed']}")

    user_limit = license_manager.check_user_limit()
    print(f"✓ User limit check:")
    print(f"  Current: {user_limit['current']}")
    print(f"  Max: {'Unlimited' if user_limit['unlimited'] else user_limit['max']}")
    print(f"  Allowed: {user_limit['allowed']}")

def test_license_status():
    """Test getting comprehensive license status"""
    print("\nTesting license status...")

    status = license_manager.get_license_status()
    print(f"✓ License status retrieved:")
    print(f"  Valid: {status['valid']}")
    print(f"  Message: {status['message']}")
    if status['license']:
        print(f"  Company: {status['license']['company_name']}")
        print(f"  Type: {status['license']['license_type']}")
        print(f"  Features enabled: {len([f for f in status['features'].values() if f])}")

def test_license_deactivation(license_key):
    """Test license deactivation"""
    print("\nTesting license deactivation...")

    success = db.deactivate_license(license_key)
    assert success, "License deactivation should succeed"
    print("✓ License deactivated")

    validation = license_manager.validate_license(license_key)
    assert not validation['valid'], "Deactivated license should be invalid"
    print("✓ Deactivated license validation correctly fails")

    # Reactivate for cleanup
    db.activate_license(license_key)
    print("✓ License reactivated")

def test_all_licenses():
    """Test retrieving all licenses"""
    print("\nTesting license listing...")

    all_licenses = db.get_all_licenses()
    print(f"✓ Retrieved {len(all_licenses)} licenses")

    for lic in all_licenses:
        print(f"  - {lic['license_key'][:20]}... ({lic['license_type']}, {lic['company_name']})")

def cleanup():
    """Clean up test database"""
    print("\nCleaning up...")
    if os.path.exists(test_db):
        os.remove(test_db)
        print(f"✓ Removed test database: {test_db}")

def main():
    """Run all tests"""
    print("="*60)
    print("NetStacks Pro Licensing System Test Suite")
    print("="*60)

    try:
        test_database_init()
        trial_license, pro_license = test_license_generation()
        test_license_validation(trial_license, pro_license)
        test_feature_checks(pro_license)
        test_license_limits()
        test_license_status()
        test_license_deactivation(trial_license['license_key'])
        test_all_licenses()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        cleanup()

if __name__ == '__main__':
    main()
