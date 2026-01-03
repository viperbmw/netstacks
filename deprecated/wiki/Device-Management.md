# Device Management

NetStacks provides comprehensive device inventory management with support for multiple vendors and connection types.

## Adding Devices

### Manual Entry

1. Navigate to **Devices**
2. Click **Add Device**
3. Fill in device information:

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Unique device identifier |
| IP Address | Yes | Device management IP |
| Device Type | Yes | Netmiko device type |
| Username | No | SSH username (uses default if empty) |
| Password | No | SSH password (uses default if empty) |
| Port | No | SSH port (default: 22) |
| Tags | No | Labels for filtering |

### Supported Device Types

NetStacks uses Netmiko for device connections. Common device types:

| Vendor | Device Type | Description |
|--------|-------------|-------------|
| Cisco | `cisco_ios` | IOS devices |
| Cisco | `cisco_xe` | IOS-XE devices |
| Cisco | `cisco_xr` | IOS-XR devices |
| Cisco | `cisco_nxos` | NX-OS devices |
| Juniper | `juniper_junos` | Junos devices |
| Arista | `arista_eos` | EOS devices |
| Palo Alto | `paloalto_panos` | PAN-OS devices |
| Fortinet | `fortinet` | FortiOS devices |

[Full list of supported platforms](https://github.com/ktbyers/netmiko#supported-platforms)

### Netbox Integration

Sync devices automatically from Netbox:

1. Go to **Settings**
2. Configure Netbox connection:
   - **URL**: Your Netbox instance
   - **Token**: API token with read access
3. Click **Test Connection**
4. Navigate to **Devices**
5. Click **Sync from Netbox**

#### Netbox Filters

Filter which devices to sync:

```json
{
  "site": "datacenter1",
  "role": "router",
  "status": "active"
}
```

## Device Credentials

### Credential Priority

1. Device-specific credentials (highest priority)
2. Default credentials from Settings
3. Error if no credentials available

### Setting Default Credentials

1. Go to **Settings**
2. Enter default username and password
3. Click **Save**

These credentials are used when device-specific credentials are not set.

### Encrypted Storage

All credentials are encrypted at rest using Fernet symmetric encryption.

## Testing Connectivity

### Single Device Test

1. Find the device in the list
2. Click **Test**
3. View connection status and output

### Bulk Test

1. Select multiple devices
2. Click **Test Selected**
3. View results for all devices

### Test Output

Successful test shows:
- Connection status
- Device hostname
- Platform info
- Uptime (if available)

## Device Operations

### View Device

- **Info**: Device details and metadata
- **Configs**: Deployed configurations
- **Backups**: Configuration history

### Edit Device

1. Click the device name
2. Modify fields
3. Click **Save**

### Delete Device

1. Select device(s)
2. Click **Delete**
3. Confirm deletion

> **Warning**: Deleting a device removes associated backups and deployment history.

## Device Tags

Tags help organize and filter devices.

### Adding Tags

1. Edit device
2. Add comma-separated tags
3. Save

### Filtering by Tags

1. Use the search/filter bar
2. Enter tag name
3. View matching devices

### Common Tag Patterns

- Location: `dc1`, `dc2`, `remote`
- Role: `core`, `edge`, `access`
- Environment: `prod`, `dev`, `test`
- Vendor: `cisco`, `juniper`, `arista`

## Bulk Operations

### Import from CSV

Create a CSV file:

```csv
name,ip_address,device_type,username,password,tags
router1,192.168.1.1,cisco_ios,admin,secret123,dc1,core
router2,192.168.1.2,cisco_ios,admin,secret123,dc1,edge
```

Import via API:
```bash
curl -X POST http://localhost:8089/api/devices/import \
  -H "Content-Type: multipart/form-data" \
  -F "file=@devices.csv"
```

### Export Devices

```bash
curl http://localhost:8089/api/devices?format=csv > devices.csv
```

## Device Override

Override device-specific settings for template variables:

1. Navigate to **Device Overrides**
2. Select device
3. Add variable overrides:
   ```json
   {
     "snmp_community": "custom_community",
     "ntp_server": "10.0.0.1"
   }
   ```
4. These values override template defaults during deployment

## Troubleshooting

### Connection Timeout

```
Error: Connection timed out
```

- Verify device is reachable: `ping device-ip`
- Check SSH port is open: `nc -zv device-ip 22`
- Verify firewall rules allow access

### Authentication Failed

```
Error: Authentication failed
```

- Verify username and password
- Check if account is locked
- Verify SSH is enabled on device

### Device Type Mismatch

```
Error: Pattern not detected
```

- Verify correct device type selected
- Try alternative device type (e.g., `cisco_xe` instead of `cisco_ios`)
- Check device SSH configuration

### SSH Key Authentication

For SSH key authentication:

1. Mount SSH keys into container
2. Configure device with key path
3. Leave password empty

## API Reference

### List Devices

```bash
GET /api/devices
```

### Create Device

```bash
POST /api/devices
Content-Type: application/json

{
  "name": "router1",
  "ip_address": "192.168.1.1",
  "device_type": "cisco_ios",
  "username": "admin",
  "password": "secret"
}
```

### Update Device

```bash
PUT /api/devices/{id}
Content-Type: application/json

{
  "name": "router1-updated"
}
```

### Delete Device

```bash
DELETE /api/devices/{id}
```

### Test Device

```bash
POST /api/devices/{id}/test
```

## Next Steps

- [[Templates]] - Create configuration templates
- [[Configuration Backups]] - Set up automated backups
- [[MOPs]] - Automate device procedures
