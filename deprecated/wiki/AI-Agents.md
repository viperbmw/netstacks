# AI Agents

NetStacks includes AI-powered agents that can automate network operations, process alerts, and assist with troubleshooting.

## Overview

AI Agents use Large Language Models (LLMs) to:
- Process and respond to network alerts
- Execute automated remediation
- Assist with troubleshooting
- Manage routine operations

## LLM Providers

### Supported Providers

| Provider | Models | Description |
|----------|--------|-------------|
| **Anthropic** | Claude 3.5, Claude 3 | Recommended for complex reasoning |
| **OpenAI** | GPT-4, GPT-3.5 | General purpose |
| **OpenRouter** | Multiple | Access to many models |

### Configuring Providers

1. Navigate to **Settings → AI Settings**
2. Click **Add Provider**
3. Select provider type
4. Enter API key
5. Test connection
6. Enable provider

### Provider Settings

| Setting | Description |
|---------|-------------|
| Name | Unique identifier |
| Display Name | Friendly name |
| API Key | Provider API key |
| Base URL | API endpoint (for custom deployments) |
| Default Model | Model to use by default |
| Is Default | Use as default provider |

## Creating Agents

### Basic Agent

1. Navigate to **Agents**
2. Click **Create Agent**
3. Configure:
   - **Name**: Agent identifier
   - **Type**: Agent type (alert handler, etc.)
   - **Description**: What the agent does
   - **LLM Provider**: Which AI to use
4. Click **Save**

### Agent Types

| Type | Purpose |
|------|---------|
| **Alert Handler** | Process and respond to alerts |
| **Remediation** | Execute automated fixes |
| **Assistant** | Interactive troubleshooting |
| **Scheduler** | Time-based operations |

## Agent Configuration

### Basic Settings

```json
{
  "name": "alert-handler-1",
  "type": "alert_handler",
  "description": "Handles network alerts",
  "llm_provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "is_active": true
}
```

### Advanced Settings

| Setting | Description |
|---------|-------------|
| Temperature | Creativity (0-1, lower = more deterministic) |
| Max Tokens | Maximum response length |
| System Prompt | Agent's base instructions |
| Timeout | Maximum processing time |

## Tools

Agents can use tools to interact with NetStacks and network devices.

### Built-in Tools

| Tool | Description |
|------|-------------|
| `get_devices` | List network devices |
| `get_device_info` | Get device details |
| `run_command` | Execute device commands |
| `get_backups` | List configuration backups |
| `compare_configs` | Compare configurations |
| `create_ticket` | Create incident ticket |
| `send_notification` | Send notifications |

### Custom Tools

Create custom tools for specific use cases:

1. Navigate to **Tools → Custom**
2. Click **Create Tool**
3. Define:
   - Name and description
   - Input schema (JSON Schema)
   - Implementation (Python or HTTP)
4. Assign to agents

### MCP Servers

Connect to Model Context Protocol servers:

1. Navigate to **Tools → MCP Servers**
2. Click **Add Server**
3. Configure connection
4. Tools are automatically discovered

## Knowledge Base

Provide agents with context via the knowledge base.

### Adding Documents

1. Navigate to **Knowledge**
2. Click **Upload**
3. Add documents:
   - Network diagrams
   - Runbooks
   - Configuration standards
   - Troubleshooting guides

### Supported Formats

- PDF
- Markdown
- Text files
- JSON/YAML

### Document Organization

Use tags and categories to organize:
- `runbook`: Operational procedures
- `architecture`: Network design
- `policy`: Configuration standards

## Alert Processing

### Workflow

1. Alert received (webhook, email, etc.)
2. Agent analyzes alert context
3. Agent queries device state
4. Agent determines action
5. Agent executes or requests approval
6. Result logged and reported

### Alert Handler Configuration

```json
{
  "name": "network-alert-handler",
  "type": "alert_handler",
  "config": {
    "auto_remediate": false,
    "approval_required": true,
    "approval_timeout_minutes": 30,
    "escalation_email": "oncall@example.com"
  }
}
```

### Auto-Remediation

When enabled, agents can automatically fix issues:

```json
{
  "auto_remediate": true,
  "allowed_actions": [
    "restart_interface",
    "clear_bgp",
    "bounce_ospf"
  ],
  "excluded_devices": [
    "core-router-1"
  ]
}
```

## Approvals

For high-risk actions, agents request approval.

### Approval Workflow

1. Agent identifies required action
2. Creates approval request
3. Notification sent to approvers
4. Approver reviews and decides
5. If approved, agent executes
6. If denied, agent logs and escalates

### Configuring Approvals

```json
{
  "approval_required": true,
  "approval_timeout_minutes": 30,
  "approvers": ["admin", "noc-lead"],
  "escalation_on_timeout": "deny"
}
```

### Pending Approvals

View and manage at **Agents → Approvals**:
- See pending requests
- View agent's analysis
- Approve or deny
- Add comments

## Agent Operations

### Starting/Stopping

```bash
# Start agent
POST /api/agents/{id}/start

# Stop agent
POST /api/agents/{id}/stop
```

Or via UI:
1. Navigate to **Agents**
2. Find agent
3. Click **Start** or **Stop**

### Monitoring

View agent activity:
- Current status
- Recent actions
- Success/failure rate
- Average response time

### Logs

Agent logs show:
- Incoming requests
- LLM interactions
- Tool usage
- Actions taken
- Errors encountered

## Example Agents

### BGP Alert Handler

```json
{
  "name": "bgp-alert-handler",
  "type": "alert_handler",
  "description": "Handles BGP-related alerts",
  "system_prompt": "You are a network operations agent specializing in BGP issues. When you receive a BGP alert, analyze the situation, check neighbor status, and determine if action is needed.",
  "tools": ["get_device_info", "run_command"],
  "config": {
    "alert_filters": ["bgp", "routing"],
    "auto_remediate": false,
    "approval_required": true
  }
}
```

### Interface Monitor

```json
{
  "name": "interface-monitor",
  "type": "assistant",
  "description": "Monitors and reports on interface issues",
  "system_prompt": "You monitor network interfaces for errors, high utilization, and status changes. Report issues and suggest remediation.",
  "tools": ["get_devices", "run_command"],
  "config": {
    "check_interval_minutes": 15,
    "error_threshold": 100,
    "utilization_threshold": 80
  }
}
```

## Best Practices

### Prompt Engineering

- Be specific about agent's role
- Define clear boundaries
- Include relevant context
- Specify output format

### Tool Design

- Keep tools focused
- Provide clear descriptions
- Include input validation
- Handle errors gracefully

### Safety

- Require approvals for destructive actions
- Exclude critical devices from auto-remediation
- Set appropriate timeouts
- Monitor agent actions

### Performance

- Use appropriate model for task complexity
- Set reasonable token limits
- Cache common queries
- Monitor costs

## API Reference

### List Agents

```bash
GET /api/agents
```

### Create Agent

```bash
POST /api/agents
Content-Type: application/json

{
  "name": "my-agent",
  "type": "alert_handler",
  "llm_provider": "anthropic"
}
```

### Start Agent

```bash
POST /api/agents/{id}/start
```

### Stop Agent

```bash
POST /api/agents/{id}/stop
```

### Get Agent Stats

```bash
GET /api/agents/{id}/stats
```

## Troubleshooting

### Agent Not Responding

1. Check agent is started
2. Verify LLM provider is configured
3. Check API key is valid
4. Review agent logs

### Wrong Actions

1. Review system prompt
2. Check tool permissions
3. Add more specific instructions
4. Enable approval workflow

### High Latency

1. Use faster model
2. Reduce context size
3. Cache common operations
4. Check network connectivity

## Next Steps

- [[AI Settings]] - Configure LLM providers
- [[Knowledge]] - Build agent knowledge base
- [[Alerts]] - Set up alert processing
