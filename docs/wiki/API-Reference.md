# API Reference

NetStacks provides a RESTful API for all operations. This reference covers the main API endpoints.

## Authentication

### Session-Based (Web UI)

The web interface uses session cookies automatically after login.

### Token-Based (API)

For programmatic access, use JWT tokens:

```bash
# Login and get token
curl -X POST http://localhost:8089/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'

# Response
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "username": "admin",
    "roles": ["admin"]
  }
}
```

### Using the Token

Include the token in the Authorization header:

```bash
curl http://localhost:8089/api/devices \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

## Response Format

All API responses follow a consistent format:

### Success Response

```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed"
}
```

### Error Response

```json
{
  "success": false,
  "error": "Error message",
  "details": { ... }
}
```

## Devices API

### List Devices

```http
GET /api/devices
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Search by name |
| `tag` | string | Filter by tag |
| `limit` | int | Results per page |
| `offset` | int | Pagination offset |

**Response:**
```json
{
  "success": true,
  "devices": [
    {
      "id": "uuid",
      "name": "router1",
      "ip_address": "192.168.1.1",
      "device_type": "cisco_ios",
      "tags": ["production", "core"],
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 100
}
```

### Get Device

```http
GET /api/devices/{id}
```

### Create Device

```http
POST /api/devices
Content-Type: application/json

{
  "name": "router1",
  "ip_address": "192.168.1.1",
  "device_type": "cisco_ios",
  "username": "admin",
  "password": "secret",
  "port": 22,
  "tags": ["production"]
}
```

### Update Device

```http
PUT /api/devices/{id}
Content-Type: application/json

{
  "name": "router1-updated",
  "tags": ["production", "updated"]
}
```

### Delete Device

```http
DELETE /api/devices/{id}
```

### Test Device Connection

```http
POST /api/devices/{id}/test
```

**Response:**
```json
{
  "success": true,
  "connected": true,
  "output": "router1 uptime is 45 days",
  "response_time_ms": 234
}
```

## Templates API

### List Templates

```http
GET /api/v2/templates
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Search by name |
| `type` | string | Filter by type |

### Get Template

```http
GET /api/v2/templates/{id}
```

### Create Template

```http
POST /api/v2/templates
Content-Type: application/json

{
  "name": "snmp_config",
  "description": "SNMP Configuration",
  "content": "snmp-server community {{ community }} RO",
  "template_type": "service",
  "validation_template_id": null,
  "delete_template_id": null
}
```

### Update Template

```http
PUT /api/v2/templates/{id}
Content-Type: application/json

{
  "name": "snmp_config_v2",
  "content": "snmp-server community {{ community }} {{ access }}"
}
```

### Delete Template

```http
DELETE /api/v2/templates/{id}
```

### Render Template

```http
POST /api/v2/templates/{id}/render
Content-Type: application/json

{
  "variables": {
    "community": "public"
  }
}
```

**Response:**
```json
{
  "success": true,
  "rendered": "snmp-server community public RO"
}
```

## MOPs API

### List MOPs

```http
GET /api/mops
```

### Get MOP

```http
GET /api/mops/{id}
```

### Create MOP

```http
POST /api/mops
Content-Type: application/json

{
  "name": "Maintenance Procedure",
  "description": "Standard maintenance",
  "yaml_content": "name: Maintenance\ndevices:\n  - router1\nsteps:\n  - name: Check status\n    type: ssh_command\n    command: show version"
}
```

### Update MOP

```http
PUT /api/mops/{id}
Content-Type: application/json

{
  "name": "Updated Procedure",
  "yaml_content": "..."
}
```

### Delete MOP

```http
DELETE /api/mops/{id}
```

### Execute MOP

```http
POST /api/mops/{id}/execute
Content-Type: application/json

{
  "variables": {
    "custom_var": "value"
  }
}
```

**Response:**
```json
{
  "success": true,
  "execution_id": "uuid",
  "status": "running"
}
```

### Get MOP Executions

```http
GET /api/mops/{id}/executions
```

### Get Execution Status

```http
GET /api/mops/executions/{execution_id}
```

## Agents API

### List Agents

```http
GET /api/agents
```

### Get Agent

```http
GET /api/agents/{id}
```

### Create Agent

```http
POST /api/agents
Content-Type: application/json

{
  "name": "alert-handler",
  "type": "alert_handler",
  "description": "Handles network alerts",
  "llm_provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "system_prompt": "You are a network operations agent...",
  "tools": ["get_devices", "run_command"],
  "config": {
    "auto_remediate": false
  }
}
```

### Update Agent

```http
PATCH /api/agents/{id}
Content-Type: application/json

{
  "description": "Updated description"
}
```

### Delete Agent

```http
DELETE /api/agents/{id}
```

### Start Agent

```http
POST /api/agents/{id}/start
```

### Stop Agent

```http
POST /api/agents/{id}/stop
```

### Get Agent Stats

```http
GET /api/agents/{id}/stats
```

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_requests": 150,
    "successful": 145,
    "failed": 5,
    "avg_response_time_ms": 2340,
    "uptime_seconds": 86400
  }
}
```

## Config Backups API

### List Backups

```http
GET /api/config-backups
GET /api/config-backups?device=router1
GET /api/config-backups?limit=50&offset=0
```

### Get Backup

```http
GET /api/config-backups/{id}
```

### Trigger Single Backup

```http
POST /api/config-backups/run-single
Content-Type: application/json

{
  "device_name": "router1"
}
```

### Trigger All Backups

```http
POST /api/config-backups/run-all
```

### Delete Backup

```http
DELETE /api/config-backups/{id}
```

### Get Backup Schedule

```http
GET /api/backup-schedule
```

### Update Backup Schedule

```http
PUT /api/backup-schedule
Content-Type: application/json

{
  "enabled": true,
  "interval_hours": 24,
  "retention_days": 30,
  "juniper_set_format": true
}
```

## Settings API

### Get Settings

```http
GET /api/settings
```

### Save Settings

```http
POST /api/settings
Content-Type: application/json

{
  "netbox_url": "https://netbox.example.com",
  "netbox_token": "token",
  "verify_ssl": false,
  "cache_ttl": 300
}
```

### Get AI Settings

```http
GET /api/settings/ai
```

### Save AI Settings

```http
POST /api/settings/ai
Content-Type: application/json

{
  "default_provider": "anthropic",
  "default_model": "claude-3-5-sonnet-20241022",
  "default_temperature": 0.7
}
```

## LLM Providers API

### List Providers

```http
GET /api/llm/providers
```

### Configure Provider

```http
POST /api/llm/providers
Content-Type: application/json

{
  "name": "anthropic",
  "display_name": "Anthropic Claude",
  "api_key": "sk-...",
  "default_model": "claude-3-5-sonnet-20241022",
  "is_enabled": true,
  "is_default": true
}
```

### Delete Provider

```http
DELETE /api/llm/providers/{name}
```

### Test Provider Connection

```http
POST /api/llm/test
Content-Type: application/json

{
  "provider": "anthropic",
  "api_key": "sk-..."
}
```

## Tasks API

### List Tasks

```http
GET /api/tasks
GET /api/tasks?status=running
```

### Get Task Status

```http
GET /api/task/{task_id}
```

**Response:**
```json
{
  "success": true,
  "task_id": "abc123",
  "status": "SUCCESS",
  "result": { ... },
  "created_at": "2024-01-01T00:00:00Z",
  "completed_at": "2024-01-01T00:00:05Z"
}
```

### Get Task Result

```http
GET /api/task/{task_id}/result
```

## Users API

### List Users

```http
GET /api/users
```

### Create User

```http
POST /api/users
Content-Type: application/json

{
  "username": "newuser",
  "password": "password123",
  "email": "user@example.com",
  "role": "operator"
}
```

### Update User

```http
PUT /api/users/{id}
Content-Type: application/json

{
  "email": "newemail@example.com"
}
```

### Delete User

```http
DELETE /api/users/{id}
```

### Change Password

```http
POST /api/users/{id}/password
Content-Type: application/json

{
  "current_password": "oldpass",
  "new_password": "newpass"
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Authentication required |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource already exists |
| 422 | Validation Error - Invalid data |
| 500 | Server Error - Internal error |

## Rate Limiting

API requests may be rate limited:
- Default: 100 requests per minute
- Burst: 20 requests per second

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1609459200
```

## Webhooks

Configure webhooks to receive events:

```http
POST /api/webhooks
Content-Type: application/json

{
  "url": "https://your-server.com/webhook",
  "events": ["backup.completed", "agent.alert"],
  "secret": "webhook-secret"
}
```

### Webhook Payload

```json
{
  "event": "backup.completed",
  "timestamp": "2024-01-01T00:00:00Z",
  "data": {
    "device": "router1",
    "backup_id": "uuid"
  },
  "signature": "sha256=..."
}
```

## SDK Examples

### Python

```python
import requests

class NetStacksClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def get_devices(self):
        r = requests.get(f"{self.base_url}/api/devices", headers=self.headers)
        return r.json()

    def backup_device(self, device_name):
        r = requests.post(
            f"{self.base_url}/api/config-backups/run-single",
            headers=self.headers,
            json={"device_name": device_name}
        )
        return r.json()

# Usage
client = NetStacksClient("http://localhost:8089", "your-token")
devices = client.get_devices()
```

### Bash

```bash
#!/bin/bash
BASE_URL="http://localhost:8089"
TOKEN="your-token"

# Get devices
curl -s "$BASE_URL/api/devices" \
  -H "Authorization: Bearer $TOKEN" | jq

# Create device
curl -s -X POST "$BASE_URL/api/devices" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"router1","ip_address":"10.0.0.1","device_type":"cisco_ios"}' | jq
```

## Next Steps

- [[Architecture]] - System design details
- [[Developer Guide]] - Extending the API
- [[Troubleshooting]] - Common API issues
