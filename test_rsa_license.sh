#!/bin/bash
#
# Test RSA License Installation
#

LICENSE_KEY="NSPRO-v2-eyJkYXRhIjogeyJjb21wYW55X25hbWUiOiAiVGVzdCBDb21wYW55IiwgImxpY2Vuc2VfdHlwZSI6ICJlbnRlcnByaXNlIiwgInRpZXJfbmFtZSI6ICJFbnRlcnByaXNlIiwgImlzc3VlZF9kYXRlIjogIjIwMjUtMTAtMTIiLCAiZXhwaXJhdGlvbl9kYXRlIjogIjIwMjYtMTAtMTIiLCAiZHVyYXRpb25fZGF5cyI6IDM2NSwgIm1heF9kZXZpY2VzIjogLTEsICJtYXhfdXNlcnMiOiAtMSwgImZlYXR1cmVzIjogWyJiYXNpY19hdXRvbWF0aW9uIiwgImNvbmZpZ190ZW1wbGF0ZXMiLCAiYXBpX2FjY2VzcyIsICJzZXJ2aWNlX3N0YWNrcyIsICJhZHZhbmNlZF9tb25pdG9yaW5nIiwgImN1c3RvbV9pbnRlZ3JhdGlvbnMiLCAibGRhcF9hdXRoIiwgIm9pZGNfYXV0aCIsICJoYV9zdXBwb3J0IiwgInByaW9yaXR5X3N1cHBvcnQiLCAiY3VzdG9tX2JyYW5kaW5nIl0sICJ2ZXJzaW9uIjogMn0sICJzaWduYXR1cmUiOiAiaVdMZGZudnVjcSs2QkZjdVpQNGZFRnMwOWFRM0luWTFZOC9hektYL1E0bUcyVTVQa3o3VXBXVWlmMWZVWFI3ek5kd2hnU2tnYTVaWndjek54TXJZZ0Q2TzhFS0gyRW9YakhJbFR3aldKZ3lsL2ZNZXFlckVxd1FJejJ0eGpKaWJlVFpKSHJleDJzUWZtMkxEZ3hwWVRFdzhVQkxVV3hvY2hjRDZ6UHl5SHN4VWhwVDF6QkJnM2ZvVEFEQ2cvSnYvNFlzUWw4djBWUFoxNHZjWHgyVVh4bkIwcTRnbXNIb0k4V2l3aVFpYnhVY3ZxMEttREtreSsydm5oRy90c0lzZ1F3R2FWWW9BdGVJdFkxaXorcEVRTGVCOHQ4eDU1RDVyMTVVeUhVdTBNR3ZkdXB6TVlGQnJ4UGhGQVBtVkJiSEJDdkJQa3JObGY3bndmVnNTZzUxSElBPT0ifQ=="

echo "Testing RSA License Installation..."
echo ""

# Login first
echo "1. Logging in as admin..."
curl -s -c /tmp/cookies.txt -X POST http://localhost:8088/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin" > /dev/null

if [ $? -ne 0 ]; then
    echo "❌ Login failed"
    exit 1
fi
echo "✓ Logged in"
echo ""

# Install license
echo "2. Installing RSA license..."
RESPONSE=$(curl -s -b /tmp/cookies.txt -X POST http://localhost:8088/api/license/install \
  -H "Content-Type: application/json" \
  -d "{\"license_key\": \"$LICENSE_KEY\"}")

echo "$RESPONSE" | python3 -m json.tool
echo ""

# Check if successful
if echo "$RESPONSE" | grep -q '"success": true'; then
    echo "✅ License installed successfully!"
else
    echo "❌ License installation failed"
    exit 1
fi
echo ""

# Get license status
echo "3. Checking license status..."
curl -s -b /tmp/cookies.txt http://localhost:8088/api/license/status | python3 -m json.tool
echo ""

echo "✅ Test complete!"
