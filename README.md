# NetStacks

**Web-based Network Automation Platform**

NetStacks is an open-source platform for network device management, configuration automation, and AI-assisted operations. It provides a modern web interface for deploying configurations, managing devices, running automated procedures, and leveraging AI agents for network operations.

## Features

### Network Configuration Management
- **Template-Based Services**: Deploy configurations using Jinja2 templates with variable substitution
- **Service Stacks**: Group related services and deploy them as a stack with dependency management
- **Configuration Backups**: Automated and on-demand device configuration backups with diff comparison
- **Validation**: Automatically validate deployed configurations against device running configs
- **Multi-Device Support**: Deploy services to multiple devices simultaneously
- **Netbox Integration**: Automatically fetch device inventory from Netbox

### MOP (Method of Procedures) Engine
- **Visual MOP Builder**: Drag-and-drop interface for creating complex procedures
- **Intelligent Step Types**: Auto-discovered from Python code - extensible by adding functions
- **Conditional Logic**: Define success/failure paths for each step
- **Execution Tracking**: Complete history and status tracking for all MOP executions
- **Multiple Step Types**: SSH commands, delays, email notifications, HTTP requests, Python validation

### AI Agents & Automation
- **AI-Powered Agents**: Configurable AI agents for network operations
- **Multiple LLM Providers**: Support for Anthropic, OpenAI, and OpenRouter
- **Tool Integration**: Built-in tools, custom tools, and MCP server support
- **Knowledge Base**: Document storage for agent context
- **Alert Processing**: AI-assisted incident management and remediation

### Authentication & Security
- **Multi-Method Authentication**:
  - Local database authentication
  - LDAP / Active Directory with STARTTLS
  - OAuth2 / OpenID Connect (Google, Azure AD, Okta, etc.)
- **Priority-Based Auth**: Configure authentication order
- **Credential Encryption**: Secure storage of device credentials
- **User Management**: Role-based access control

## Architecture

NetStacks uses a modular Flask architecture with Blueprint-based routing and a service layer pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                    NetStacks Platform                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Flask Application (app.py)               │   │
│  │  - Blueprint Registration                             │   │
│  │  - Celery Task Endpoints                              │   │
│  │  - Device Operations (SSH/Netmiko)                    │   │
│  └──────────────────────────────────────────────────────┘   │
│           │                                                  │
│  ┌────────┴─────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │    Blueprints    │  │   Services    │  │    Utils    │  │
│  │  routes/*.py     │  │ services/*.py │  │  utils/*.py │  │
│  │  - pages         │  │  - auth       │  │  - decorators│ │
│  │  - auth          │  │  - settings   │  │  - exceptions│ │
│  │  - devices       │  │  - stack      │  │  - responses │ │
│  │  - templates     │  │  - user       │  │              │  │
│  │  - stacks        │  │  - device     │  └─────────────┘  │
│  │  - mop           │  │  - platform   │                    │
│  │  - agents        │  └───────────────┘                    │
│  │  - settings      │                                        │
│  │  - api           │                                        │
│  └──────────────────┘                                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  Background Workers                   │   │
│  │  Celery + Redis + PostgreSQL                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
└──────────────────────────────┼───────────────────────────────┘
                               │ SSH/Netmiko
                               ▼
                      Network Devices
```

### Directory Structure

```
netstacks/
├── app.py                      # Flask application + Celery endpoints
├── database.py                 # PostgreSQL database layer (SQLAlchemy)
├── models.py                   # SQLAlchemy ORM models
├── mop_engine.py               # MOP execution engine
├── auth_ldap.py                # LDAP authentication
├── auth_oidc.py                # OIDC/OAuth2 authentication
├── netbox_client.py            # Netbox API client
├── credential_encryption.py    # Credential encryption utilities
├── timezone_utils.py           # Timezone handling
├── docker-compose.yml          # Platform deployment
│
├── routes/                     # Flask Blueprints
│   ├── __init__.py             # Blueprint registration
│   ├── pages.py                # Dashboard, deploy, monitor pages
│   ├── auth.py                 # Login, logout, password management
│   ├── admin.py                # User CRUD, auth config
│   ├── devices.py              # Device CRUD operations
│   ├── templates.py            # Template management
│   ├── stacks.py               # Stack templates and stacks
│   ├── mop.py                  # MOP CRUD and execution
│   ├── agents.py               # AI agent management
│   ├── settings.py             # Application settings, LLM providers
│   ├── api.py                  # API resources, config backups
│   ├── alerts.py               # Alert and incident management
│   └── knowledge.py            # Knowledge base documents
│
├── services/                   # Business Logic Layer
│   ├── auth_service.py         # Authentication logic
│   ├── user_service.py         # User management
│   ├── settings_service.py     # Settings management
│   ├── stack_service.py        # Stack operations
│   ├── device_service.py       # Device operations
│   ├── platform_stats_service.py  # Platform statistics
│   └── microservice_client.py  # Service health checks
│
├── utils/                      # Shared Utilities
│   ├── decorators.py           # @handle_exceptions, @require_json
│   ├── exceptions.py           # ValidationError, NotFoundError, etc.
│   └── responses.py            # success_response, error_response
│
├── templates/                  # Jinja2 HTML templates
├── static/                     # CSS, JavaScript, images
├── tasks/                      # Celery task definitions
├── ai/                         # AI agent implementations
└── docs/                       # Documentation and plans
```

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/viperbmw/netstacks.git
cd netstacks
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env to customize settings
```

### 3. Deploy the Platform

```bash
docker-compose up -d
```

This starts the following containers:
- `netstacks` - Web UI + API (Flask)
- `netstacks-workers` - Celery workers for device operations
- `netstacks-workers-beat` - Celery beat scheduler
- `netstacks-postgres` - PostgreSQL database
- `netstacks-redis` - Redis for task queue
- `netstacks-traefik` - Reverse proxy (optional)

### 4. Access the Platform

- **Web UI**: `http://localhost:8089`
- **Default Login**: `admin` / `admin`

**Important**: Change the default password after first login!

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | PostgreSQL connection | Database connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection for Celery |
| `TZ` | `America/New_York` | Timezone for scheduled operations |
| `SECRET_KEY` | Auto-generated | Flask session secret |
| `JWT_SECRET_KEY` | Auto-generated | JWT token secret |

### Authentication Setup

#### Local Authentication (Default)
- Database-backed username/password
- Change password via user settings

#### LDAP / Active Directory
1. Navigate to **Settings → Authentication**
2. Configure LDAP settings:
   - Server hostname/IP
   - Port (389/636)
   - Base DN
   - User filter
   - SSL/TLS options
3. Test connection and enable

#### OAuth2 / OIDC
1. Configure your identity provider (Google, Azure AD, Okta)
2. Navigate to **Settings → Authentication → OIDC**
3. Enter Client ID, Client Secret, Issuer URL
4. Set redirect URI: `http://your-server:8089/login/oidc/callback`
5. Test and enable

### Netbox Integration

1. Go to **Settings**
2. Enter Netbox URL and API token
3. Configure device filters (optional)
4. Click **Sync Devices** to import inventory

### AI/LLM Configuration

1. Navigate to **Settings → AI Settings**
2. Add LLM providers (Anthropic, OpenAI, OpenRouter)
3. Enter API keys and configure defaults
4. Test connection to verify

## Usage

### Managing Devices

1. Navigate to **Devices**
2. Add devices manually or sync from Netbox
3. Configure credentials (stored encrypted)
4. Test connectivity

### Creating Templates

1. Go to **Templates**
2. Create Jinja2 templates with `{{ variable }}` syntax
3. Link validation and delete templates
4. Save template

Example template:
```jinja2
snmp-server community {{ snmp_community }} {{ snmp_mode }}
snmp-server location {{ snmp_location }}
snmp-server contact {{ snmp_contact }}
```

### Deploying Configurations

1. Navigate to **Deploy**
2. Select template and target devices
3. Fill in template variables
4. Execute deployment
5. Monitor progress in real-time

### Creating MOPs (Method of Procedures)

1. Go to **MOPs**
2. Create new MOP with Visual Builder or YAML editor
3. Add steps with conditional logic
4. Save and execute

Example MOP:
```yaml
name: "BGP Maintenance"
description: "Graceful BGP shutdown and restore"
devices:
  - router1.example.com

steps:
  - name: "Disable BGP"
    id: disable_bgp
    type: ssh_command
    command: "configure terminal\nrouter bgp 65000\nshutdown"
    on_success: wait_step
    on_failure: send_alert

  - name: "Wait 5 minutes"
    id: wait_step
    type: delay
    seconds: 300
    on_success: enable_bgp

  - name: "Re-enable BGP"
    id: enable_bgp
    type: ssh_command
    command: "configure terminal\nrouter bgp 65000\nno shutdown"
```

### Configuration Backups

1. Navigate to **Backups**
2. Configure backup schedule (interval, retention)
3. Run on-demand backups
4. Compare configurations with diff view

### AI Agents

1. Go to **Agents**
2. Create agent with specific capabilities
3. Assign tools and knowledge base
4. Configure LLM provider
5. Start agent for automated operations

## API Reference

### Authentication
- `POST /login` - Authenticate user
- `POST /logout` - End session
- `GET /api/auth/me` - Current user info

### Devices
- `GET /api/devices` - List devices
- `POST /api/devices` - Create device
- `GET /api/devices/<id>` - Get device
- `PUT /api/devices/<id>` - Update device
- `DELETE /api/devices/<id>` - Delete device
- `POST /api/devices/<id>/test` - Test connectivity

### Templates
- `GET /api/v2/templates` - List templates
- `POST /api/v2/templates` - Create template
- `GET /api/v2/templates/<id>` - Get template
- `PUT /api/v2/templates/<id>` - Update template
- `DELETE /api/v2/templates/<id>` - Delete template

### MOPs
- `GET /api/mops` - List MOPs
- `POST /api/mops` - Create MOP
- `GET /api/mops/<id>` - Get MOP
- `PUT /api/mops/<id>` - Update MOP
- `DELETE /api/mops/<id>` - Delete MOP
- `POST /api/mops/<id>/execute` - Execute MOP

### Agents
- `GET /api/agents` - List agents
- `POST /api/agents` - Create agent
- `PATCH /api/agents/<id>` - Update agent
- `POST /api/agents/<id>/start` - Start agent
- `POST /api/agents/<id>/stop` - Stop agent

### Settings
- `GET /api/settings` - Get settings
- `POST /api/settings` - Save settings
- `GET /api/llm/providers` - List LLM providers
- `POST /api/llm/providers` - Configure provider

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/netstacks"
export REDIS_URL="redis://localhost:6379/0"

# Run Flask
python app.py

# Run Celery worker (separate terminal)
celery -A tasks worker -l info

# Run Celery beat (separate terminal)
celery -A tasks beat -l info
```

### Adding New Routes

1. Create blueprint in `routes/`
2. Register in `routes/__init__.py`
3. Use decorators from `utils/decorators.py`
4. Use responses from `utils/responses.py`

### Adding New Services

1. Create service class in `services/`
2. Import and use in blueprints
3. Keep business logic in services, not routes

## Troubleshooting

### Container Logs

```bash
docker-compose logs -f netstacks
docker-compose logs -f netstacks-workers
```

### Database Issues

```bash
# Connect to PostgreSQL
docker-compose exec netstacks-postgres psql -U netstacks

# Check tables
\dt
```

### Celery Issues

```bash
# Check worker status
docker-compose exec netstacks celery -A tasks inspect active

# Check scheduled tasks
docker-compose exec netstacks celery -A tasks inspect scheduled
```

### Timezone Issues

Verify timezone configuration:
```bash
docker-compose exec netstacks printenv TZ
docker-compose exec netstacks date
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow existing code patterns
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Related Projects

- [Netbox](https://github.com/netbox-community/netbox) - Network inventory management
- [NAPALM](https://github.com/napalm-automation/napalm) - Network automation library
- [Netmiko](https://github.com/ktbyers/netmiko) - SSH library for network devices

---

**Built for network automation**