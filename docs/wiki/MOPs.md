# MOPs (Method of Procedures)

MOPs automate complex, multi-step network procedures with conditional logic, rollback capabilities, and execution tracking.

## Overview

A MOP consists of:
- **Steps**: Individual actions (SSH commands, delays, notifications)
- **Targets**: Devices to execute on
- **Flow Control**: Success/failure paths between steps
- **Execution Tracking**: Full history and status

## Creating MOPs

### Visual Builder

1. Navigate to **MOPs**
2. Click **New MOP**
3. Click **Visual Builder** tab
4. Add target devices
5. Add steps with the **+ Step** button
6. Configure each step
7. Define transitions
8. Click **Save**

### YAML Editor

1. Navigate to **MOPs**
2. Click **New MOP**
3. Click **YAML Editor** tab
4. Write MOP definition
5. Click **Save**

## MOP Structure

### YAML Format

```yaml
name: "Maintenance Window"
description: "Router maintenance procedure"

devices:
  - router1.example.com
  - router2.example.com

steps:
  - name: "Disable BGP"
    id: disable_bgp
    type: ssh_command
    command: |
      configure terminal
      router bgp 65000
      shutdown
    on_success: wait_step
    on_failure: alert_team

  - name: "Wait for traffic drain"
    id: wait_step
    type: delay
    seconds: 300
    on_success: maintenance
    on_failure: enable_bgp

  - name: "Perform maintenance"
    id: maintenance
    type: ssh_command
    command: "show version"
    on_success: enable_bgp

  - name: "Enable BGP"
    id: enable_bgp
    type: ssh_command
    command: |
      configure terminal
      router bgp 65000
      no shutdown
    on_success: notify_success
    on_failure: alert_team

  - name: "Notify success"
    id: notify_success
    type: email
    to: "noc@example.com"
    subject: "Maintenance Complete"
    body: "BGP maintenance completed successfully"

  - name: "Alert team"
    id: alert_team
    type: email
    to: "oncall@example.com"
    subject: "Maintenance Failed"
    body: "Maintenance procedure encountered an error"
```

## Step Types

### ssh_command

Execute commands on devices via SSH.

```yaml
- name: "Show interfaces"
  id: show_int
  type: ssh_command
  command: "show ip interface brief"
  on_success: next_step
  on_failure: error_handler
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `command` | Yes | Command(s) to execute |
| `timeout` | No | Command timeout (seconds) |
| `expect` | No | Expected output pattern |

### delay

Wait for a specified duration.

```yaml
- name: "Wait 5 minutes"
  id: wait
  type: delay
  seconds: 300
  on_success: next_step
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `seconds` | Yes | Wait duration in seconds |

### email

Send email notifications.

```yaml
- name: "Notify team"
  id: notify
  type: email
  to: "team@example.com"
  subject: "Task completed"
  body: "The maintenance task has completed."
  on_success: end
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `to` | Yes | Recipient email |
| `subject` | Yes | Email subject |
| `body` | Yes | Email body |
| `cc` | No | CC recipients |

### http_request

Make HTTP/HTTPS requests.

```yaml
- name: "Trigger webhook"
  id: webhook
  type: http_request
  url: "https://api.example.com/webhook"
  method: POST
  headers:
    Content-Type: application/json
  body: '{"status": "complete"}'
  on_success: next_step
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | Target URL |
| `method` | No | HTTP method (default: GET) |
| `headers` | No | Request headers |
| `body` | No | Request body |
| `timeout` | No | Request timeout |

### log

Log messages for debugging.

```yaml
- name: "Log progress"
  id: log
  type: log
  message: "Step 3 completed successfully"
  level: info
  on_success: next_step
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `message` | Yes | Log message |
| `level` | No | Log level (debug, info, warning, error) |

### validate_python

Run custom Python validation.

```yaml
- name: "Validate output"
  id: validate
  type: validate_python
  code: |
    if 'up' in previous_output:
        return True
    return False
  on_success: next_step
  on_failure: error_handler
```

**Parameters**:
| Parameter | Required | Description |
|-----------|----------|-------------|
| `code` | Yes | Python code to execute |

**Available context**:
- `previous_output`: Output from previous step
- `device`: Current device info
- `variables`: MOP variables

## Flow Control

### Success/Failure Paths

Each step can define:
- `on_success`: Step ID to execute on success
- `on_failure`: Step ID to execute on failure

### Execution Flow

```
start → step1 → (success) → step2 → (success) → end
                ↓ (failure)
                error_handler → notify → end
```

### Terminating Steps

Steps without `on_success` or `on_failure` end that execution path.

## Variables

### MOP Variables

Define variables used across steps:

```yaml
name: "Config Update"
variables:
  snmp_community: "public"
  ntp_server: "10.0.0.1"

steps:
  - name: "Configure SNMP"
    type: ssh_command
    command: "snmp-server community {{ snmp_community }} RO"
```

### Runtime Variables

Variables can be provided at execution time:

```bash
POST /api/mops/{id}/execute
{
  "variables": {
    "snmp_community": "secure_community"
  }
}
```

## Execution

### Running a MOP

1. Navigate to **MOPs**
2. Find the MOP
3. Click **Execute**
4. (Optional) Override variables
5. Confirm execution

### Monitoring Execution

1. View progress in real-time
2. See step-by-step status
3. View command output
4. Track success/failure path

### Execution States

| State | Description |
|-------|-------------|
| `pending` | Waiting to start |
| `running` | Currently executing |
| `success` | Completed successfully |
| `failed` | Encountered error |
| `cancelled` | Manually cancelled |

## Execution History

### Viewing History

1. Navigate to **MOPs**
2. Click MOP name
3. Click **Executions** tab
4. View all past executions

### Execution Details

Each execution shows:
- Start/end time
- Total duration
- Step-by-step results
- Command outputs
- Error messages

## Example MOPs

### BGP Maintenance

```yaml
name: "BGP Maintenance Window"
description: "Gracefully disable and re-enable BGP"

devices:
  - core-router-1

steps:
  - name: "Capture pre-state"
    id: pre_check
    type: ssh_command
    command: "show ip bgp summary"
    on_success: disable_bgp

  - name: "Disable BGP"
    id: disable_bgp
    type: ssh_command
    command: |
      configure terminal
      router bgp 65000
      shutdown
      end
    on_success: wait_drain
    on_failure: rollback

  - name: "Wait for convergence"
    id: wait_drain
    type: delay
    seconds: 180
    on_success: maintenance

  - name: "Perform maintenance"
    id: maintenance
    type: ssh_command
    command: "show version"
    on_success: enable_bgp

  - name: "Enable BGP"
    id: enable_bgp
    type: ssh_command
    command: |
      configure terminal
      router bgp 65000
      no shutdown
      end
    on_success: post_check
    on_failure: alert

  - name: "Verify BGP restored"
    id: post_check
    type: ssh_command
    command: "show ip bgp summary"
    on_success: success_notify
    on_failure: alert

  - name: "Notify success"
    id: success_notify
    type: email
    to: "noc@example.com"
    subject: "BGP Maintenance Complete"
    body: "BGP maintenance completed successfully"

  - name: "Rollback"
    id: rollback
    type: ssh_command
    command: |
      configure terminal
      router bgp 65000
      no shutdown
      end
    on_success: alert

  - name: "Alert team"
    id: alert
    type: email
    to: "oncall@example.com"
    subject: "BGP Maintenance Issue"
    body: "BGP maintenance encountered a problem"
```

### Config Backup Validation

```yaml
name: "Validate and Backup Config"
description: "Check config changes and backup"

devices:
  - router1
  - router2

steps:
  - name: "Get current config"
    id: get_config
    type: ssh_command
    command: "show running-config"
    on_success: validate

  - name: "Validate config"
    id: validate
    type: validate_python
    code: |
      required = ['snmp-server', 'logging']
      for item in required:
          if item not in previous_output:
              return False
      return True
    on_success: backup
    on_failure: alert

  - name: "Trigger backup"
    id: backup
    type: http_request
    url: "http://localhost:8089/api/config-backups/run-single"
    method: POST
    headers:
      Content-Type: application/json
    on_success: notify

  - name: "Notify completion"
    id: notify
    type: log
    message: "Config validated and backed up"
    level: info

  - name: "Alert on failure"
    id: alert
    type: email
    to: "noc@example.com"
    subject: "Config validation failed"
    body: "Required configuration missing"
```

## Best Practices

### Design

- Start with simple, linear MOPs
- Add complexity gradually
- Always include error handling
- Add notifications for critical steps

### Testing

- Test on lab devices first
- Use dry-run mode when available
- Review execution history
- Document expected outcomes

### Error Handling

- Define `on_failure` for critical steps
- Include rollback procedures
- Notify appropriate teams
- Log enough detail for debugging

## API Reference

### List MOPs

```bash
GET /api/mops
```

### Get MOP

```bash
GET /api/mops/{id}
```

### Create MOP

```bash
POST /api/mops
Content-Type: application/json

{
  "name": "My MOP",
  "description": "Description",
  "yaml_content": "..."
}
```

### Execute MOP

```bash
POST /api/mops/{id}/execute
Content-Type: application/json

{
  "variables": {}
}
```

### Get Executions

```bash
GET /api/mops/{id}/executions
```

## Next Steps

- [[Configuration Backups]] - Automated backup procedures
- [[AI Agents]] - AI-assisted automation
- [[API Reference]] - Full API documentation
