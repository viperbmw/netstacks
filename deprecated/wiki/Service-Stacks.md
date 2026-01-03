# Service Stacks

Service Stacks group related templates for deployment as a single unit with dependency management.

## Overview

A Service Stack:
- Groups multiple templates together
- Defines deployment order via dependencies
- Applies shared variables across templates
- Enables bulk deployment and validation

## Creating Stacks

### From Templates

1. Navigate to **Stacks**
2. Click **Create Stack**
3. Enter stack details:
   - **Name**: Stack identifier
   - **Description**: What the stack configures
4. Add templates to the stack
5. Define dependencies
6. Set shared variables
7. Click **Save**

### Stack Structure

```json
{
  "name": "Basic Network Stack",
  "description": "Standard network configuration",
  "templates": [
    {"id": "template-1", "name": "ntp_config"},
    {"id": "template-2", "name": "snmp_config"},
    {"id": "template-3", "name": "logging_config"}
  ],
  "dependencies": {
    "snmp_config": ["ntp_config"],
    "logging_config": ["ntp_config"]
  },
  "variables": {
    "ntp_server": "10.0.0.1",
    "snmp_community": "public"
  }
}
```

## Dependencies

### Defining Dependencies

Dependencies determine deployment order:

```
ntp_config (no dependencies) → Deploy first
    ↓
snmp_config (depends on ntp_config) → Deploy second
    ↓
logging_config (depends on snmp_config) → Deploy third
```

### Parallel Deployment

Templates without dependencies can deploy in parallel:

```
ntp_config ──→ snmp_config ──→ syslog_config
           ──→ acl_config  ──┘
```

## Variables

### Shared Variables

Define once, use across all templates:

```json
{
  "variables": {
    "ntp_server": "10.0.0.1",
    "domain_name": "example.com",
    "admin_email": "admin@example.com"
  }
}
```

### Variable Override

Override variables per deployment:

1. Select stack
2. Click **Deploy**
3. Modify variables as needed
4. Deploy with custom values

## Deploying Stacks

### Full Stack Deployment

1. Navigate to **Stacks**
2. Select stack
3. Select target devices
4. Review/modify variables
5. Click **Deploy All**

### Selective Deployment

Deploy specific templates from a stack:

1. Select stack
2. Choose specific templates
3. Configure and deploy

### Deployment Order

Templates deploy based on dependencies:

1. Templates with no dependencies first
2. Then templates whose dependencies are met
3. Continue until all deployed

## Validation

### Validating Stack

1. Select deployed stack
2. Click **Validate**
3. Each template's validation template runs
4. View results per template

### Validation Results

```
Stack: Basic Network Stack
Device: router1

✓ ntp_config - Validated
✓ snmp_config - Validated
✗ logging_config - Missing: logging host 10.0.0.100
```

## Stack Templates

Create reusable stack templates:

### Save as Template

1. Configure a stack
2. Click **Save as Template**
3. Stack becomes reusable blueprint

### Deploy from Template

1. Select stack template
2. Click **Deploy**
3. Variables pre-filled from template
4. Modify as needed

## Example Stacks

### Basic Network Stack

```yaml
name: Basic Network Stack
templates:
  - ntp_config
  - snmp_config
  - syslog_config
  - banner_config

dependencies:
  snmp_config: []
  syslog_config: []
  banner_config: []

variables:
  ntp_server: "10.0.0.1"
  snmp_community: "public"
  syslog_server: "10.0.0.100"
  banner_text: "Authorized access only"
```

### Security Stack

```yaml
name: Security Hardening Stack
templates:
  - disable_services
  - acl_mgmt
  - ssh_config
  - aaa_config

dependencies:
  acl_mgmt: [disable_services]
  ssh_config: [acl_mgmt]
  aaa_config: [ssh_config]

variables:
  mgmt_acl_name: "MGMT-ACCESS"
  ssh_timeout: 60
  tacacs_server: "10.0.0.50"
```

## API Reference

### List Stacks

```bash
GET /api/stacks
```

### Create Stack

```bash
POST /api/stacks
Content-Type: application/json

{
  "name": "My Stack",
  "templates": ["template-id-1", "template-id-2"],
  "dependencies": {},
  "variables": {}
}
```

### Deploy Stack

```bash
POST /api/stacks/{id}/deploy
Content-Type: application/json

{
  "device_ids": ["device-1", "device-2"],
  "variables": {}
}
```

### Validate Stack

```bash
POST /api/stacks/{id}/validate
Content-Type: application/json

{
  "device_ids": ["device-1"]
}
```

## Best Practices

### Stack Design

- Group logically related configurations
- Keep stacks focused (5-10 templates max)
- Define clear dependencies
- Document variable requirements

### Variable Management

- Use descriptive variable names
- Provide sensible defaults
- Document required vs optional
- Consider device overrides

### Testing

- Test on lab devices first
- Validate after deployment
- Keep rollback procedures ready

## Next Steps

- [[Templates]] - Creating templates
- [[MOPs]] - Automated procedures
- [[Device Management]] - Managing devices
