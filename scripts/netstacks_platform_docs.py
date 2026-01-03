#!/usr/bin/env python3
"""
NetStacks Platform Documentation Seeder

Creates comprehensive documentation about the NetStacks platform
for AI agents to use when helping users navigate and use the system.

Run with: docker exec netstacks-ai python /app/scripts/netstacks_platform_docs.py
"""

import uuid
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from sqlalchemy import text
from netstacks_core.db import get_session


# =============================================================================
# NETSTACKS PLATFORM DOCUMENTATION
# =============================================================================

NETSTACKS_DOCS = [
    # =========================================================================
    # PLATFORM OVERVIEW
    # =========================================================================
    {
        "title": "NetStacks Platform Overview",
        "doc_type": "platform",
        "content": """# NetStacks Platform Overview

## What is NetStacks?

NetStacks is an AI-powered network operations platform designed for enterprise network management. It provides:

- **Device Management**: Inventory, configuration, and monitoring of network devices
- **Configuration Automation**: Template-based configuration deployment
- **AI Agents**: Intelligent automation and troubleshooting assistance
- **Alerting & Incidents**: Real-time monitoring and incident management
- **Knowledge Base**: Searchable documentation and runbooks
- **MOPs (Methods of Procedure)**: Standardized operational workflows

## Platform Architecture

NetStacks is built on a microservices architecture with these core components:

1. **Frontend Service**: Web-based UI for all platform features
2. **Auth Service**: Authentication, authorization, and user management
3. **AI Service**: AI agents, LLM integration, and chat functionality
4. **Tasks Service**: Background job processing and device automation
5. **Config Service**: Templates, MOPs, and configuration management

## Navigation Structure

The platform is organized into these main sections:

### Operations (Left Sidebar)
- **Dashboard** (`/`) - Platform overview and quick stats
- **Platform** (`/platform`) - Device inventory and management
- **Deploy** (`/deploy`) - Configuration deployment interface
- **Monitor** (`/monitor`) - Task monitoring and execution status
- **Alerts** (`/alerts`) - Active alerts from monitoring systems
- **Incidents** (`/incidents`) - Incident tracking and management

### Configuration (Left Sidebar)
- **Templates** (`/templates`) - Jinja2 configuration templates
- **MOPs** (`/mop`) - Methods of Procedure workflows
- **Step Types** (`/step-types`) - MOP step type definitions
- **Config Backups** (`/config-backups`) - Device configuration history

### AI & Automation (Left Sidebar)
- **AI Agents** (`/agents`) - Configure and manage AI agents
- **AI Settings** (`/ai-settings`) - LLM providers and AI configuration
- **Agent Chat** (`/agent-chat`) - Direct chat with AI agents
- **Knowledge** (`/knowledge`) - Knowledge base management

### Administration (Left Sidebar)
- **Users** (`/users`) - User account management
- **Authentication** (`/authentication`) - Auth providers (LDAP, SAML, etc.)
- **Settings** (`/settings`) - System-wide settings
- **Services** (`/services`) - Microservice health monitoring
- **Workers** (`/workers`) - Background worker status

## Getting Started

1. **Add Devices**: Go to Platform → Add Device to register network equipment
2. **Create Templates**: Build Jinja2 templates in Templates section
3. **Deploy Configs**: Use Deploy page to push configurations
4. **Monitor Tasks**: Track execution status in Monitor page
5. **Set Up Alerts**: Configure alerting for proactive monitoring
"""
    },
    # =========================================================================
    # DEVICE MANAGEMENT
    # =========================================================================
    {
        "title": "NetStacks Device Management Guide",
        "doc_type": "platform",
        "content": """# Device Management in NetStacks

## Overview

The Platform page (`/platform`) is the central hub for managing all network devices in your inventory.

## Accessing Device Management

Navigate to: **Platform** in the left sidebar or go directly to `/platform`

## Features

### Device Inventory
- View all registered devices with status indicators
- Filter by device type, platform, site, or status
- Search devices by name, IP, or other attributes
- Export device list to CSV

### Adding Devices

To add a new device:
1. Click the **Add Device** button
2. Fill in required fields:
   - **Name**: Unique device identifier (e.g., `PE1-NYC`)
   - **IP Address**: Management IP
   - **Platform**: Device OS (cisco_ios, cisco_xr, juniper_junos, arista_eos, etc.)
   - **Device Type**: Router, Switch, Firewall, etc.
3. Optional fields:
   - **Site**: Physical location
   - **Credentials**: Select saved credential profile
   - **Tags**: For grouping and filtering
4. Click **Save**

### Device Details

Click any device to view:
- **Configuration**: Current running config
- **Interfaces**: Interface status and details
- **Neighbors**: CDP/LLDP neighbor information
- **Health**: CPU, memory, and environmental data
- **History**: Configuration change history

### Bulk Operations

- **Bulk Import**: Upload CSV file with device information
- **Bulk Update**: Modify multiple devices at once
- **Bulk Delete**: Remove multiple devices

### Device Groups

Create logical groups for:
- Site-based organization
- Function-based grouping (Core, Distribution, Access)
- Custom groupings for deployment targets

## Device Platforms Supported

| Platform | Identifier | Description |
|----------|------------|-------------|
| Cisco IOS | `cisco_ios` | Traditional IOS devices |
| Cisco IOS-XE | `cisco_xe` | IOS-XE based devices |
| Cisco IOS-XR | `cisco_xr` | IOS-XR based routers |
| Cisco NX-OS | `cisco_nxos` | Nexus switches |
| Juniper Junos | `juniper_junos` | Juniper devices |
| Arista EOS | `arista_eos` | Arista switches |

## Best Practices

1. Use consistent naming conventions for devices
2. Always verify connectivity before bulk operations
3. Keep credential profiles updated
4. Use tags for dynamic grouping
5. Regularly validate device inventory accuracy
"""
    },
    # =========================================================================
    # CONFIGURATION DEPLOYMENT
    # =========================================================================
    {
        "title": "NetStacks Configuration Deployment Guide",
        "doc_type": "platform",
        "content": """# Configuration Deployment in NetStacks

## Overview

The Deploy page (`/deploy`) provides a streamlined interface for pushing configurations to network devices.

## Accessing Deployment

Navigate to: **Deploy** in the left sidebar or go directly to `/deploy`

## Deployment Methods

### 1. Template-Based Deployment

Use Jinja2 templates with variables:

1. Select a template from the dropdown
2. Choose target devices or device groups
3. Fill in template variables
4. Preview the rendered configuration
5. Click **Deploy**

### 2. Direct Configuration

Push raw configuration commands:

1. Select **Direct Config** mode
2. Choose target devices
3. Enter configuration commands
4. Click **Deploy**

### 3. MOP-Based Deployment

Execute a Method of Procedure:

1. Select a MOP from the library
2. Review the steps
3. Approve each step or use auto-approve
4. Monitor execution progress

## Deployment Options

### Pre-Deploy Checks
- **Syntax Validation**: Verify config syntax before pushing
- **Dry Run**: Show what would be changed without applying
- **Backup First**: Capture config before making changes

### Execution Options
- **Sequential**: Deploy to devices one at a time
- **Parallel**: Deploy to multiple devices simultaneously
- **Batch Size**: Control parallelism (e.g., 5 devices at a time)

### Post-Deploy Actions
- **Verify Config**: Run show commands to confirm changes
- **Save Config**: Write running config to startup
- **Rollback on Failure**: Revert if deployment fails

## Monitoring Deployments

After initiating a deployment:

1. Track progress on the **Monitor** page (`/monitor`)
2. View real-time logs for each device
3. Check success/failure status
4. Review output and any errors

## Template Variables

Templates support these variable types:

```jinja2
{{ device.name }}        # Device name
{{ device.ip }}          # Device IP address
{{ device.platform }}    # Device platform
{{ custom_var }}         # User-defined variable
{% for item in list %}   # Loop constructs
{% if condition %}       # Conditional logic
```

## Best Practices

1. Always preview before deploying
2. Use dry-run for critical changes
3. Deploy during maintenance windows
4. Keep deployments atomic and reversible
5. Document all changes in the deployment notes
"""
    },
    # =========================================================================
    # TEMPLATES
    # =========================================================================
    {
        "title": "NetStacks Templates Guide",
        "doc_type": "platform",
        "content": """# Configuration Templates in NetStacks

## Overview

The Templates page (`/templates`) manages Jinja2 templates for automated configuration generation.

## Accessing Templates

Navigate to: **Templates** in the left sidebar or go directly to `/templates`

## Creating Templates

### Basic Template Structure

```jinja2
! Template: {{ template_name }}
! Generated: {{ timestamp }}
! Device: {{ device.name }}

interface {{ interface_name }}
 description {{ description }}
 ip address {{ ip_address }} {{ subnet_mask }}
 no shutdown
!
```

### Template Types

1. **Full Config**: Complete device configuration
2. **Partial Config**: Specific feature configuration
3. **Snippet**: Reusable configuration blocks

## Jinja2 Syntax

### Variables
```jinja2
{{ variable_name }}
{{ device.name }}
{{ device.site.name }}
```

### Conditionals
```jinja2
{% if enable_feature %}
feature {{ feature_name }}
{% endif %}

{% if platform == 'cisco_ios' %}
  ! IOS-specific config
{% elif platform == 'juniper_junos' %}
  # Junos-specific config
{% endif %}
```

### Loops
```jinja2
{% for vlan in vlans %}
vlan {{ vlan.id }}
 name {{ vlan.name }}
{% endfor %}

{% for interface in interfaces %}
interface {{ interface.name }}
 description {{ interface.description }}
{% endfor %}
```

### Filters
```jinja2
{{ hostname | upper }}           # ROUTER1
{{ ip_address | ipaddr }}        # Validate IP
{{ list | join(', ') }}          # item1, item2, item3
{{ config | indent(2) }}         # Add indentation
```

### Macros
```jinja2
{% macro interface_config(name, ip, mask) %}
interface {{ name }}
 ip address {{ ip }} {{ mask }}
 no shutdown
{% endmacro %}

{{ interface_config('Gi0/0', '10.0.0.1', '255.255.255.0') }}
```

## Template Variables

Define variables in the template metadata:

```yaml
variables:
  - name: hostname
    type: string
    required: true
    description: Device hostname
  - name: vlans
    type: list
    required: false
    default: []
  - name: enable_bgp
    type: boolean
    default: false
```

## Template Testing

1. Click **Test Template**
2. Provide sample variable values
3. Select a test device
4. View rendered output
5. Validate syntax

## Best Practices

1. Use descriptive template names
2. Document all variables
3. Include comments in templates
4. Test thoroughly before production use
5. Version control your templates
6. Use macros for reusable blocks
"""
    },
    # =========================================================================
    # MOPs (METHODS OF PROCEDURE)
    # =========================================================================
    {
        "title": "NetStacks MOPs (Methods of Procedure) Guide",
        "doc_type": "platform",
        "content": """# Methods of Procedure (MOPs) in NetStacks

## Overview

The MOP page (`/mop`) manages standardized operational procedures for network changes.

## Accessing MOPs

Navigate to: **MOPs** in the left sidebar or go directly to `/mop`

## What is a MOP?

A Method of Procedure (MOP) is a step-by-step guide for performing network operations:

- Standardizes complex procedures
- Ensures consistency across team members
- Provides audit trail of changes
- Enables automated execution

## Creating a MOP

### 1. Define MOP Metadata
- **Name**: Descriptive title (e.g., "BGP Peer Addition")
- **Description**: Purpose and scope
- **Category**: Grouping (Maintenance, Change, Emergency)
- **Risk Level**: Low, Medium, High, Critical
- **Estimated Duration**: Expected time to complete

### 2. Add Steps

Each step includes:
- **Step Type**: Category of action
- **Title**: Brief description
- **Instructions**: Detailed guidance
- **Commands**: CLI commands to execute
- **Validation**: Expected output or success criteria
- **Rollback**: Commands to undo the step

### Step Types

| Type | Description |
|------|-------------|
| `pre_check` | Validation before changes |
| `backup` | Save current configuration |
| `configure` | Apply configuration changes |
| `verify` | Confirm changes applied |
| `post_check` | Final validation |
| `notification` | Send alerts/notifications |
| `manual` | Human intervention required |
| `approval` | Requires explicit approval |

### 3. Configure Execution Settings

- **Approval Required**: Needs approval before execution
- **Auto-Proceed**: Automatically continue on success
- **Stop on Failure**: Halt execution if step fails
- **Notification Settings**: Who to notify at each stage

## Executing a MOP

### Manual Execution

1. Select the MOP from the library
2. Choose target devices
3. Review all steps
4. Click **Execute**
5. Approve each step as needed
6. Monitor progress

### Scheduled Execution

1. Select the MOP
2. Click **Schedule**
3. Set date/time
4. Configure auto-approval settings
5. Assign approvers

## MOP Execution Flow

```
[Start] → [Pre-Checks] → [Approval] → [Backup] → [Execute Steps] → [Verify] → [Complete]
           ↓                                        ↓
        [Fail]                                   [Rollback]
           ↓                                        ↓
        [Abort]                                  [Notify]
```

## Monitoring MOP Execution

Track execution on the **Monitor** page (`/monitor`):

- Real-time step status
- Output from each step
- Approval requests
- Rollback status if needed

## Best Practices

1. Always include pre-checks
2. Capture backups before changes
3. Include verification steps
4. Document rollback procedures
5. Test MOPs in lab environments
6. Keep MOPs updated with lessons learned
"""
    },
    # =========================================================================
    # AI AGENTS
    # =========================================================================
    {
        "title": "NetStacks AI Agents Guide",
        "doc_type": "platform",
        "content": """# AI Agents in NetStacks

## Overview

The AI Agents page (`/agents`) configures intelligent automation agents for network operations.

## Accessing AI Agents

Navigate to: **AI Agents** in the left sidebar or go directly to `/agents`

## Agent Types

### Triage Agent
- First responder for alerts and incidents
- Classifies issues by severity and type
- Routes to appropriate specialist agent
- Gathers initial diagnostic information

### BGP Specialist
- Expert in BGP troubleshooting
- Analyzes BGP neighbor states
- Reviews route advertisements
- Suggests configuration fixes

### OSPF Specialist
- OSPF protocol expertise
- Adjacency troubleshooting
- LSA analysis
- Area configuration review

### IS-IS Specialist
- IS-IS protocol knowledge
- Level 1/Level 2 troubleshooting
- Metric and reachability analysis

### General Assistant
- Platform navigation help
- General network questions
- Documentation lookup
- Feature guidance

## Creating an Agent

1. Click **Create Agent**
2. Configure:
   - **Name**: Agent identifier
   - **Type**: Select agent type
   - **System Prompt**: Agent instructions
   - **LLM Provider**: AI backend (Anthropic, OpenRouter)
   - **Model**: Specific model to use
   - **Tools**: Enable/disable capabilities

## Agent Tools

Agents can use these tools:

| Tool | Description |
|------|-------------|
| `show_command` | Execute show commands on devices |
| `get_device_config` | Retrieve device configurations |
| `search_knowledge` | Query knowledge base |
| `get_platform_stats` | Get system statistics |
| `create_incident` | Create new incidents |
| `handoff_to_specialist` | Transfer to another agent |
| `escalate_to_human` | Request human intervention |

## Agent Sessions

Agents maintain conversation sessions:

- **Session ID**: Unique conversation identifier
- **History**: Complete message history
- **Actions**: All tool calls and results
- **Status**: Active, Completed, or Failed

View sessions on the **Agent Chat** page (`/agent-chat`)

## AI Settings

Configure LLM providers on the **AI Settings** page (`/ai-settings`):

### Anthropic
- Claude models (Claude 3 Opus, Sonnet, Haiku)
- Requires Anthropic API key

### OpenRouter
- Access to multiple providers
- GPT-4, Claude, Llama, Mistral, etc.
- Single API key for all models

## Best Practices

1. Use specific, detailed system prompts
2. Enable only necessary tools
3. Set appropriate temperature (0.1-0.3 for accuracy)
4. Monitor token usage
5. Review agent actions regularly
6. Update prompts based on performance
"""
    },
    # =========================================================================
    # ALERTS & INCIDENTS
    # =========================================================================
    {
        "title": "NetStacks Alerts and Incidents Guide",
        "doc_type": "platform",
        "content": """# Alerts and Incidents in NetStacks

## Overview

NetStacks provides comprehensive alerting and incident management capabilities.

## Alerts Page

Navigate to: **Alerts** in the left sidebar or go directly to `/alerts`

### Alert Features

- **Real-time Display**: Live alert feed from monitoring systems
- **Severity Levels**: Critical, Warning, Info
- **Filtering**: By device, type, severity, status
- **Bulk Actions**: Acknowledge, resolve, or escalate multiple alerts

### Alert Statuses

| Status | Description |
|--------|-------------|
| `new` | Just received, unacknowledged |
| `acknowledged` | Seen by operator |
| `investigating` | Under investigation |
| `resolved` | Issue fixed |
| `escalated` | Sent to higher tier |

### Alert Types

- **BGP Down**: BGP neighbor session failures
- **OSPF Flapping**: OSPF adjacency instability
- **IS-IS Down**: IS-IS adjacency failures
- **Interface Down**: Link failures
- **High CPU**: CPU utilization alerts
- **High Memory**: Memory utilization alerts
- **Config Change**: Unauthorized config modifications

### Auto-Triage

Enable AI auto-triage to:
- Automatically classify alerts
- Gather initial diagnostics
- Suggest remediation steps
- Route to appropriate team

## Incidents Page

Navigate to: **Incidents** in the left sidebar or go directly to `/incidents`

### Incident Features

- **Incident Creation**: Manual or automatic from correlated alerts
- **Timeline View**: Complete incident history
- **Affected Devices**: Track impacted infrastructure
- **Resolution Tracking**: Document root cause and fix

### Incident Workflow

```
[Alert] → [Triage] → [Incident Created] → [Investigation] → [Resolution] → [Post-Mortem]
```

### Incident Severity

| Level | Name | Response Time |
|-------|------|---------------|
| P1 | Critical | Immediate |
| P2 | High | 30 minutes |
| P3 | Medium | 2 hours |
| P4 | Low | Next business day |

## Best Practices

1. Set appropriate alert thresholds
2. Create correlation rules for related alerts
3. Document resolution steps for recurring issues
4. Conduct post-mortems for major incidents
5. Update runbooks based on learnings
"""
    },
    # =========================================================================
    # MONITORING
    # =========================================================================
    {
        "title": "NetStacks Monitoring Guide",
        "doc_type": "platform",
        "content": """# Task Monitoring in NetStacks

## Overview

The Monitor page (`/monitor`) provides real-time visibility into all platform operations.

## Accessing Monitor

Navigate to: **Monitor** in the left sidebar or go directly to `/monitor`

## Sections

### Active Tasks
- Currently executing tasks
- Real-time status updates
- Progress indicators
- Cancel option for stuck tasks

### Task History
- Completed task archive
- Success/failure statistics
- Execution duration
- Full output logs

### Workers
- Background worker status
- Queue depth
- Processing rate
- Worker health

### MOP Executions
- Active MOP runs
- Pending approvals
- Step-by-step progress
- Rollback status

## Task Types

| Type | Description |
|------|-------------|
| `show_command` | Execute show command on device |
| `configure` | Apply configuration |
| `backup` | Capture device config |
| `deploy` | Template deployment |
| `mop_step` | MOP step execution |
| `discovery` | Device discovery |

## Task States

```
[pending] → [started] → [success]
                    ↘ [failure]
                    ↘ [timeout]
                    ↘ [cancelled]
```

## Task Details

Click any task to view:
- **Task ID**: Unique identifier
- **Device**: Target device
- **Command**: Executed command
- **Status**: Current state
- **Duration**: Execution time
- **Result**: Output (formatted or raw JSON)
- **Errors**: Any error messages

### Raw JSON View
Toggle between formatted and raw JSON output for detailed analysis.

## Filtering

Filter tasks by:
- Status (pending, success, failure)
- Device
- Task type
- Time range
- User who initiated

## Best Practices

1. Monitor critical deployments in real-time
2. Set up alerts for failed tasks
3. Review task history for trends
4. Archive old tasks periodically
5. Use raw JSON view for debugging
"""
    },
    # =========================================================================
    # KNOWLEDGE BASE
    # =========================================================================
    {
        "title": "NetStacks Knowledge Base Guide",
        "doc_type": "platform",
        "content": """# Knowledge Base in NetStacks

## Overview

The Knowledge page (`/knowledge`) manages documentation that AI agents use for context.

## Accessing Knowledge Base

Navigate to: **Knowledge** in the left sidebar or go directly to `/knowledge`

## Features

### Collections
Organize documents into logical groups:
- **RFCs**: Protocol specifications
- **Troubleshooting Guides**: Step-by-step procedures
- **Vendor Documentation**: Platform-specific guides
- **Runbooks**: Operational procedures
- **Platform Docs**: NetStacks documentation

### Documents
Individual knowledge articles with:
- Title and description
- Rich markdown content
- Document type classification
- Searchable metadata

## Adding Knowledge

### Manual Entry
1. Click **Add Document**
2. Select or create a collection
3. Enter document content (Markdown supported)
4. Add metadata and tags
5. Click **Save**

### Document Types
- `protocol`: Protocol specifications (RFCs)
- `runbook`: Operational procedures
- `vendor`: Vendor documentation
- `troubleshooting`: Troubleshooting guides
- `platform`: Platform documentation

## AI Integration

Knowledge documents are:
- **Indexed**: Processed for semantic search
- **Vectorized**: Stored in vector database
- **Searchable**: Available to AI agents via `search_knowledge` tool

When AI agents need information:
1. User asks a question
2. Agent searches knowledge base
3. Relevant documents retrieved
4. Agent uses context to answer

## Search

Search documents by:
- Keyword matching
- Semantic similarity
- Document type
- Collection
- Tags

## Best Practices

1. Write clear, structured documents
2. Use markdown formatting
3. Include examples and commands
4. Keep documentation current
5. Tag documents appropriately
6. Organize into logical collections
"""
    },
    # =========================================================================
    # CONFIG BACKUPS
    # =========================================================================
    {
        "title": "NetStacks Config Backups Guide",
        "doc_type": "platform",
        "content": """# Configuration Backups in NetStacks

## Overview

The Config Backups page (`/config-backups`) manages device configuration history.

## Accessing Config Backups

Navigate to: **Config Backups** in the left sidebar or go directly to `/config-backups`

## Features

### Backup List
- All captured configurations
- Filter by device, date, or type
- Search within configurations
- Compare versions

### Backup Details
Click any backup to view:
- Full configuration text
- Capture timestamp
- Backup type (scheduled, manual, pre-change)
- Associated task or deployment

### Configuration Diff
Compare two configurations:
1. Select first backup
2. Select second backup
3. View side-by-side diff
4. Highlighted additions/deletions

## Backup Methods

### Manual Backup
1. Go to device details or Deploy page
2. Click **Backup Config**
3. Backup captured immediately

### Scheduled Backups
Configure automatic backups:
- Daily, weekly, or custom schedule
- All devices or specific groups
- Retention policy settings

### Pre-Change Backups
Automatically captured:
- Before any deployment
- Before MOP execution
- Before manual config changes

## Restoration

To restore a configuration:
1. Find the backup to restore
2. Click **Restore**
3. Review the configuration
4. Confirm restoration
5. Monitor deployment

## Retention Policy

Configure how long to keep backups:
- Keep last N backups per device
- Keep backups for N days
- Archive to external storage

## Best Practices

1. Enable scheduled backups
2. Always backup before changes
3. Verify backups are complete
4. Test restoration procedures
5. Archive critical configs off-platform
"""
    },
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    {
        "title": "NetStacks User Management Guide",
        "doc_type": "platform",
        "content": """# User Management in NetStacks

## Overview

The Users page (`/users`) manages user accounts and permissions.

## Accessing User Management

Navigate to: **Users** in the left sidebar or go directly to `/users`

## User Roles

### Admin
- Full platform access
- User management
- System configuration
- All operational features

### Operator
- Device operations
- Deployments and MOPs
- Alert management
- Limited configuration access

### Viewer
- Read-only access
- View devices and configs
- View alerts and incidents
- No modification rights

## Creating Users

1. Click **Add User**
2. Enter:
   - Username
   - Email
   - Password (or SSO)
   - Role assignment
   - Team/group membership
3. Click **Create**

## Authentication Methods

Configure on the **Authentication** page (`/authentication`):

### Local Authentication
- Username/password stored in NetStacks
- Password policies configurable

### LDAP/Active Directory
- Integrate with corporate directory
- Automatic group mapping
- SSO capability

### SAML
- Enterprise SSO providers
- Okta, Azure AD, etc.
- Automatic provisioning

### OAuth2
- Social login providers
- Google, GitHub, etc.

## Best Practices

1. Use SSO when available
2. Implement least-privilege access
3. Review user accounts regularly
4. Enable MFA for admins
5. Audit user actions
"""
    },
    # =========================================================================
    # SETTINGS
    # =========================================================================
    {
        "title": "NetStacks Settings Guide",
        "doc_type": "platform",
        "content": """# System Settings in NetStacks

## Overview

The Settings page (`/settings`) configures platform-wide options.

## Accessing Settings

Navigate to: **Settings** in the left sidebar or go directly to `/settings`

## Categories

### General Settings
- Platform name and branding
- Timezone configuration
- Date/time format
- Default language

### Security Settings
- Session timeout
- Password policies
- API key management
- Allowed IP ranges

### Notification Settings
- Email configuration (SMTP)
- Webhook integrations
- Notification templates
- Alert routing rules

### Integration Settings
- External system connections
- API endpoints
- Authentication tokens

### AI Settings

Accessible at `/ai-settings`:

- **LLM Providers**: Anthropic, OpenRouter configuration
- **API Keys**: Secure key storage
- **Default Models**: Platform-wide defaults
- **Assistant**: Enable/disable AI assistant
- **Agent Defaults**: Default agent settings

## API Configuration

### API Keys
Generate keys for:
- External system integration
- Automation scripts
- CI/CD pipelines

### Rate Limiting
- Requests per minute
- Burst limits
- Per-user limits

## Backup & Export

- Export platform configuration
- Backup database
- Export device inventory
- Export templates and MOPs

## Best Practices

1. Configure email notifications
2. Set appropriate session timeouts
3. Regularly rotate API keys
4. Enable audit logging
5. Backup settings regularly
"""
    },
    # =========================================================================
    # SERVICE STACKS
    # =========================================================================
    {
        "title": "NetStacks Service Stacks Guide",
        "doc_type": "platform",
        "content": """# Service Stacks in NetStacks

## Overview

The Service Stacks page (`/service-stacks`) manages logical groupings of network services.

## Accessing Service Stacks

Navigate to: **Service Stacks** in the left sidebar or go directly to `/service-stacks`

## Concept

A Service Stack represents:
- A complete network service (e.g., "Customer VPN")
- All components needed for the service
- Devices, configurations, and dependencies

## Creating a Service Stack

1. Click **Create Stack**
2. Define:
   - **Name**: Service identifier
   - **Description**: Service purpose
   - **Components**: Devices and configs included
   - **Dependencies**: Related services
3. Save the stack

## Use Cases

### Service Visibility
- Understand service composition
- Track all related devices
- Monitor service health

### Change Impact
- See what's affected by changes
- Plan maintenance windows
- Assess risk before changes

### Documentation
- Document service architecture
- Track service dependencies
- Maintain service inventory

## Best Practices

1. Define stacks for critical services
2. Keep dependencies updated
3. Include all related components
4. Document service ownership
5. Review stacks quarterly
"""
    },
    # =========================================================================
    # QUICK REFERENCE - NAVIGATION
    # =========================================================================
    {
        "title": "NetStacks Quick Reference - Page Navigation",
        "doc_type": "platform",
        "content": """# NetStacks Quick Reference - Navigation

## Page URLs

Use these URLs to navigate directly to any feature:

### Operations
| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Main platform overview |
| Platform | `/platform` | Device inventory management |
| Deploy | `/deploy` | Configuration deployment |
| Monitor | `/monitor` | Task monitoring |
| Alerts | `/alerts` | Alert management |
| Incidents | `/incidents` | Incident tracking |

### Configuration
| Page | URL | Description |
|------|-----|-------------|
| Templates | `/templates` | Jinja2 templates |
| MOPs | `/mop` | Methods of Procedure |
| Step Types | `/step-types` | MOP step definitions |
| Config Backups | `/config-backups` | Configuration history |

### AI & Automation
| Page | URL | Description |
|------|-----|-------------|
| AI Agents | `/agents` | Agent configuration |
| AI Settings | `/ai-settings` | LLM provider setup |
| Agent Chat | `/agent-chat` | Chat with agents |
| Knowledge | `/knowledge` | Knowledge base |

### Administration
| Page | URL | Description |
|------|-----|-------------|
| Users | `/users` | User management |
| Authentication | `/authentication` | Auth providers |
| Settings | `/settings` | System settings |
| Services | `/services` | Service health |
| Workers | `/workers` | Background workers |
| Service Stacks | `/service-stacks` | Service definitions |
| Admin | `/admin` | Admin functions |
| Tools | `/tools` | Utility tools |
| Approvals | `/approvals` | Pending approvals |

## Navigation Syntax for AI

When guiding users, the AI can use this syntax to create clickable navigation buttons:

```
[[Navigate: Button Text | /path]]
```

Examples:
- `[[Navigate: Go to Platform | /platform]]`
- `[[Navigate: Open Alerts | /alerts]]`
- `[[Navigate: View Templates | /templates]]`

Or use standard markdown links for inline navigation:
- `[Platform](/platform)`
- `[Deploy page](/deploy)`

## Common Tasks Quick Access

| Task | Where to Go |
|------|-------------|
| Add a device | `/platform` → Add Device |
| Deploy config | `/deploy` |
| Check task status | `/monitor` |
| View alerts | `/alerts` |
| Create template | `/templates` → Create |
| Build a MOP | `/mop` → Create MOP |
| Configure AI | `/ai-settings` |
| Manage users | `/users` |
"""
    },
]


def create_collection_if_needed(session):
    """Create NetStacks Platform collection if it doesn't exist."""
    result = session.execute(
        text("SELECT id, collection_id FROM knowledge_collections WHERE name = :name"),
        {"name": "NetStacks Platform"}
    ).fetchone()

    if result:
        return result.id, result.collection_id

    collection_id = str(uuid.uuid4())
    session.execute(
        text("""
            INSERT INTO knowledge_collections
            (collection_id, name, description, doc_type, is_enabled, document_count, created_by, created_at)
            VALUES (:collection_id, :name, :description, :doc_type, :is_enabled, :document_count, :created_by, :created_at)
        """),
        {
            "collection_id": collection_id,
            "name": "NetStacks Platform",
            "description": "Comprehensive documentation about the NetStacks platform for AI agents and users",
            "doc_type": "platform",
            "is_enabled": True,
            "document_count": 0,
            "created_by": "system",
            "created_at": datetime.utcnow()
        }
    )
    session.commit()

    # Get the auto-incremented id
    result = session.execute(
        text("SELECT id FROM knowledge_collections WHERE collection_id = :cid"),
        {"cid": collection_id}
    ).fetchone()

    print(f"  Created collection: NetStacks Platform ({collection_id})")
    return result.id, collection_id


def seed_platform_docs(session):
    """Seed NetStacks platform documentation."""
    print("Seeding NetStacks platform documentation...")

    collection_id, collection_uuid = create_collection_if_needed(session)

    import json
    created = 0
    updated = 0

    for doc in NETSTACKS_DOCS:
        # Check if document exists
        existing = session.execute(
            text("SELECT doc_id FROM knowledge_documents WHERE title = :title"),
            {"title": doc["title"]}
        ).fetchone()

        if existing:
            # Update existing document
            session.execute(
                text("""
                    UPDATE knowledge_documents
                    SET content = :content, doc_type = :doc_type, updated_at = :updated_at
                    WHERE doc_id = :doc_id
                """),
                {
                    "doc_id": existing.doc_id,
                    "content": doc["content"],
                    "doc_type": doc["doc_type"],
                    "updated_at": datetime.utcnow()
                }
            )
            updated += 1
        else:
            # Create new document
            session.execute(
                text("""
                    INSERT INTO knowledge_documents
                    (doc_id, title, content, doc_type, collection_id, is_indexed, doc_metadata, created_by, created_at, chunk_count)
                    VALUES (:doc_id, :title, :content, :doc_type, :collection_id, :is_indexed, :doc_metadata, :created_by, :created_at, :chunk_count)
                """),
                {
                    "doc_id": str(uuid.uuid4()),
                    "title": doc["title"],
                    "content": doc["content"],
                    "doc_type": doc["doc_type"],
                    "collection_id": collection_id,
                    "is_indexed": False,
                    "doc_metadata": json.dumps({"source": "platform-docs", "auto_generated": True}),
                    "created_by": "system",
                    "created_at": datetime.utcnow(),
                    "chunk_count": 0
                }
            )
            created += 1

    # Update collection document count
    session.execute(
        text("UPDATE knowledge_collections SET document_count = :count WHERE id = :id"),
        {"count": len(NETSTACKS_DOCS), "id": collection_id}
    )

    session.commit()
    print(f"  Created {created} documents, updated {updated} documents")
    print(f"  Total platform docs: {len(NETSTACKS_DOCS)}")


def main():
    print("=" * 60)
    print("NetStacks Platform Documentation Seeder")
    print("=" * 60)

    session = get_session()

    try:
        seed_platform_docs(session)

        print("=" * 60)
        print("Documentation seeding complete!")
        print("=" * 60)

        # Summary
        doc_count = session.execute(
            text("SELECT COUNT(*) FROM knowledge_documents WHERE doc_type = 'platform'")
        ).scalar()

        print(f"\nPlatform documentation: {doc_count} documents")
        print("\nNote: Run knowledge indexing to make documents searchable by AI agents.")

    except Exception as e:
        print(f"\nError during seeding: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
