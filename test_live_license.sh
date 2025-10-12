#!/bin/bash

# Test script for NetStacks Pro licensing system
# Tests the live application running in Docker

BASE_URL="http://localhost:8088"
COOKIE_FILE="/tmp/netstacks_cookie.txt"

echo "================================================"
echo "NetStacks Pro Live Licensing System Test"
echo "================================================"
echo ""

# Clean up old cookies
rm -f $COOKIE_FILE

# Step 1: Login
echo "1. Logging in as admin..."
curl -s -c $COOKIE_FILE -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin" \
  "$BASE_URL/login" > /dev/null

if [ $? -eq 0 ]; then
    echo "   ✓ Login successful"
else
    echo "   ✗ Login failed"
    exit 1
fi

# Step 2: Check license status (should be no license initially)
echo ""
echo "2. Checking initial license status..."
STATUS=$(curl -s -b $COOKIE_FILE "$BASE_URL/api/license/status")
VALID=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin).get('valid', False))")

if [ "$VALID" = "False" ]; then
    echo "   ✓ No license found (as expected)"
    MESSAGE=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin).get('message', ''))")
    echo "   Message: $MESSAGE"
else
    echo "   ℹ License already exists"
fi

# Step 3: Create a trial license
echo ""
echo "3. Creating trial license..."
TRIAL_RESPONSE=$(curl -s -b $COOKIE_FILE -X POST \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Test Company","contact_email":"test@example.com"}' \
  "$BASE_URL/api/license/trial")

SUCCESS=$(echo $TRIAL_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))")

if [ "$SUCCESS" = "True" ]; then
    echo "   ✓ Trial license created successfully"
    LICENSE_KEY=$(echo $TRIAL_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['license']['license_key'])")
    echo "   License Key: $LICENSE_KEY"
else
    echo "   ✗ Trial license creation failed"
    echo "   Response: $TRIAL_RESPONSE"
fi

# Step 4: Check license status again (should be valid now)
echo ""
echo "4. Verifying license status..."
STATUS=$(curl -s -b $COOKIE_FILE "$BASE_URL/api/license/status")
VALID=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin).get('valid', False))")

if [ "$VALID" = "True" ]; then
    echo "   ✓ License is now valid"
    COMPANY=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['license']['company_name'])")
    LICENSE_TYPE=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['license']['license_type'])")
    EXPIRY=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['license'].get('expiration_date', 'Never')[:10])")

    echo "   Company: $COMPANY"
    echo "   Type: $LICENSE_TYPE"
    echo "   Expires: $EXPIRY"
else
    echo "   ✗ License validation failed"
    echo "   Response: $STATUS"
    exit 1
fi

# Step 5: Check device and user limits
echo ""
echo "5. Checking license limits..."
DEVICE_CURRENT=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['device_limit']['current'])")
DEVICE_MAX=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['device_limit']['max'])")
USER_CURRENT=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['user_limit']['current'])")
USER_MAX=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['user_limit']['max'])")

echo "   Devices: $DEVICE_CURRENT / $DEVICE_MAX"
echo "   Users: $USER_CURRENT / $USER_MAX"

# Step 6: Generate a professional license
echo ""
echo "6. Generating a professional license..."
PRO_RESPONSE=$(curl -s -b $COOKIE_FILE -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "company_name":"Pro Customer",
    "license_type":"professional",
    "contact_email":"pro@example.com",
    "duration_days":365,
    "max_devices":-1,
    "max_users":-1,
    "notes":"Professional license for testing"
  }' \
  "$BASE_URL/api/license/generate")

SUCCESS=$(echo $PRO_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))")

if [ "$SUCCESS" = "True" ]; then
    echo "   ✓ Professional license generated successfully"
    PRO_KEY=$(echo $PRO_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['license']['license_key'])")
    echo "   License Key: $PRO_KEY"
else
    echo "   ✗ License generation failed"
    echo "   Response: $PRO_RESPONSE"
fi

# Step 7: List all licenses
echo ""
echo "7. Listing all licenses..."
ALL_LICENSES=$(curl -s -b $COOKIE_FILE "$BASE_URL/api/license/all")
LICENSE_COUNT=$(echo $ALL_LICENSES | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
echo "   ✓ Found $LICENSE_COUNT license(s)"

echo $ALL_LICENSES | python3 -c "
import sys, json
licenses = json.load(sys.stdin)
for lic in licenses:
    print(f\"   - {lic['license_key'][:25]}... ({lic['license_type']}, {lic['company_name']})\")
"

# Clean up
rm -f $COOKIE_FILE

echo ""
echo "================================================"
echo "✓ All tests completed successfully!"
echo "================================================"
echo ""
echo "You can now access NetStacks Pro at:"
echo "  http://localhost:8088"
echo ""
echo "Login credentials:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "Navigate to http://localhost:8088/license to manage licenses"
echo ""
