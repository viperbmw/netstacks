# Templates

Templates are the core of NetStacks configuration management. They use Jinja2 syntax to create reusable, parameterized configurations.

## Creating Templates

### Basic Template

1. Navigate to **Templates**
2. Click **New Template**
3. Enter:
   - **Name**: Unique identifier
   - **Description**: What the template does
   - **Content**: Jinja2 template code

### Template Syntax

NetStacks uses Jinja2 templating:

```jinja2
{# This is a comment #}

{# Variables #}
hostname {{ hostname }}
ip address {{ ip_address }} {{ subnet_mask }}

{# Conditionals #}
{% if enable_snmp %}
snmp-server community {{ snmp_community }} RO
{% endif %}

{# Loops #}
{% for server in ntp_servers %}
ntp server {{ server }}
{% endfor %}
```

## Variable Types

### Simple Variables

```jinja2
interface {{ interface_name }}
  description {{ description }}
  ip address {{ ip_address }} {{ mask }}
```

Variables: `interface_name`, `description`, `ip_address`, `mask`

### Boolean Variables

```jinja2
{% if enable_logging %}
logging buffered 16384
logging console
{% endif %}
```

Variable: `enable_logging` (true/false)

### List Variables

```jinja2
{% for vlan in vlans %}
vlan {{ vlan.id }}
  name {{ vlan.name }}
{% endfor %}
```

Variable: `vlans` (list of objects with `id` and `name`)

### Default Values

```jinja2
hostname {{ hostname | default('router') }}
```

Uses "router" if `hostname` is not provided.

## Template Types

### Service Template

The main configuration template:

```jinja2
{# SNMP Configuration #}
snmp-server community {{ community }} {{ access }}
snmp-server location {{ location }}
snmp-server contact {{ contact }}
```

### Validation Template

Verifies configuration exists on device:

```jinja2
snmp-server community {{ community }}
```

Returns success if all lines are found in running config.

### Delete Template

Removes configuration from device:

```jinja2
no snmp-server community {{ community }}
no snmp-server location
no snmp-server contact
```

## Linking Templates

### Create Template Family

1. Create the service template
2. Create a validation template
3. Create a delete template
4. Edit service template
5. Link validation and delete templates

### Benefits

- **Validation**: Verify deployments succeeded
- **Rollback**: Clean removal of configurations
- **Audit**: Track what's deployed where

## Template Variables

### Auto-Detection

NetStacks automatically detects variables in templates:

```jinja2
interface {{ interface }}
  description {{ desc }}
```

Detected: `interface`, `desc`

### Variable Metadata

Add descriptions for better UX:

```yaml
# Template metadata (in description or separate field)
variables:
  interface:
    description: Interface name (e.g., GigabitEthernet0/1)
    required: true
  desc:
    description: Interface description
    default: ""
```

## Advanced Features

### Filters

Jinja2 filters transform values:

```jinja2
{# Convert to uppercase #}
hostname {{ hostname | upper }}

{# Default value #}
description {{ desc | default('No description') }}

{# Join list #}
logging trap {{ log_levels | join(' ') }}
```

### Macros

Reusable template blocks:

```jinja2
{% macro interface_config(name, ip, mask) %}
interface {{ name }}
  ip address {{ ip }} {{ mask }}
  no shutdown
{% endmacro %}

{{ interface_config('Gi0/1', '10.0.0.1', '255.255.255.0') }}
{{ interface_config('Gi0/2', '10.0.1.1', '255.255.255.0') }}
```

### Includes

Include other templates:

```jinja2
{% include 'common/header.j2' %}

{# Main configuration #}
hostname {{ hostname }}

{% include 'common/footer.j2' %}
```

## Example Templates

### SNMP Configuration

```jinja2
{# SNMP v2c Configuration #}
snmp-server community {{ community_ro }} RO
snmp-server community {{ community_rw }} RW
snmp-server location {{ location }}
snmp-server contact {{ contact }}

{% for host in trap_hosts %}
snmp-server host {{ host }} {{ community_ro }}
{% endfor %}
```

### NTP Configuration

```jinja2
{# NTP Configuration #}
{% for server in ntp_servers %}
ntp server {{ server }}{% if loop.first %} prefer{% endif %}

{% endfor %}

ntp source {{ source_interface }}
```

### ACL Configuration

```jinja2
{# Access Control List #}
ip access-list extended {{ acl_name }}
{% for rule in rules %}
  {{ rule.action }} {{ rule.protocol }} {{ rule.source }} {{ rule.destination }}{% if rule.port %} eq {{ rule.port }}{% endif %}

{% endfor %}
```

### Interface Configuration

```jinja2
interface {{ interface }}
  description {{ description }}
{% if ip_address %}
  ip address {{ ip_address }} {{ subnet_mask }}
{% else %}
  no ip address
{% endif %}
{% if vlan %}
  switchport access vlan {{ vlan }}
  switchport mode access
{% endif %}
{% if shutdown %}
  shutdown
{% else %}
  no shutdown
{% endif %}
```

## Template Testing

### Preview Rendering

1. Open template
2. Click **Preview**
3. Enter test variables
4. View rendered output

### Dry Run

1. Select template and device
2. Enable **Dry Run** mode
3. View what would be deployed
4. No changes made to device

## Best Practices

### Naming Conventions

- Use descriptive names: `snmp_v2c_config` not `snmp`
- Include vendor if specific: `cisco_ios_ntp`
- Use underscores, not spaces

### Documentation

- Add description to every template
- Document required variables
- Include example usage

### Modularity

- Create small, focused templates
- Use includes for common patterns
- Build template libraries

### Version Control

- Templates are stored in database
- Export templates for backup
- Consider external version control for critical templates

## API Reference

### List Templates

```bash
GET /api/v2/templates
```

### Get Template

```bash
GET /api/v2/templates/{id}
```

### Create Template

```bash
POST /api/v2/templates
Content-Type: application/json

{
  "name": "snmp_config",
  "description": "SNMP Configuration",
  "content": "snmp-server community {{ community }} RO"
}
```

### Render Template

```bash
POST /api/v2/templates/{id}/render
Content-Type: application/json

{
  "variables": {
    "community": "public"
  }
}
```

### Delete Template

```bash
DELETE /api/v2/templates/{id}
```

## Next Steps

- [[Service Stacks]] - Group related templates
- [[MOPs]] - Use templates in procedures
- [[Configuration Backups]] - Track configuration changes
