# NetStacks

**Web-based Service Stack Management for Network Automation**

NetStacks is an open-source web application that provides a modern interface for managing network device configurations using template-based service stacks. It simplifies network automation with an intuitive UI for deploying, validating, and managing configuration services across your network infrastructure.

This application connects to [Netpalm](https://github.com/tbotnz/netpalm) for network automation and provides powerful features for enterprise network management.

## 🚀 Features

- **Template-Based Services**: Deploy configurations using Jinja2 templates with variable substitution
- **Service Stacks**: Group related services and deploy them as a stack with dependency management
- **Validation**: Automatically validate deployed configurations against device running configs
- **Delete Operations**: Clean removal of configurations using delete templates
- **Multi-Device Support**: Deploy services to multiple devices simultaneously
- **Netbox Integration**: Automatically fetch device inventory from Netbox
- **Real-time Monitoring**: Track deployment progress and job status
- **Template Metadata**: Link validation and delete templates to service templates
- **🔐 Enterprise Authentication**: Multiple authentication methods
  - Local database authentication
  - LDAP / Active Directory integration
  - OAuth2 / OpenID Connect (OIDC) support
  - Auto-provisioning for external users
- **🌐 Offline Operation**: Fully functional without internet connectivity

## 📋 Prerequisites

1. **Docker & Docker Compose**: For containerized deployment
2. **(Optional) Netbox**: For automatic device inventory management

## 🚀 Quick Start

**NetStacks now includes the complete platform!** The unified docker-compose deploys both:
- **NetStacks Web UI** (port 8089) - Frontend interface
- **Netstacker Backend** (port 9000) - API automation engine

### 1. Clone the Repository

```bash
git clone https://github.com/viperbmw/netstacks.git
cd netstacks
```

### 2. (Optional) Customize Configuration

```bash
cp .env.example .env
# Edit .env to customize API keys and ports if needed
```

### 3. Deploy the Complete Platform

```bash
docker-compose up -d
```

This will start 5 containers:
- `netstacks` - Web UI
- `netstacker-controller` - API server
- `netstacker-worker-pinned` - Task worker (pinned queue)
- `netstacker-worker-fifo` - Task worker (FIFO queue)
- `netstacker-redis` - Queue and cache

### 4. Access the Platform

- **NetStacks Web UI**: `http://localhost:8089`
- **Netstacker API**: `http://localhost:9000`
- **Netstacker Swagger UI**: `http://localhost:9000`

The Web UI is pre-configured to connect to the backend API automatically!

### 5. (Optional) Configure Netbox Integration

1. Go to `http://localhost:8089/settings`
2. Add your Netbox connection details:
   - **Netbox URL**: Your Netbox server URL
   - **Netbox Token**: Your Netbox API token

## 🌐 Architecture

NetStacks is a **complete network automation platform** with integrated frontend and backend:

```
┌─────────────────────────────────────────────────────────┐
│                    NetStacks Platform                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌──────────────────────────┐ │
│  │  NetStacks   │  REST   │  Netstacker Backend      │ │
│  │   Web UI     │ ◄─────► │  ┌────────────────────┐  │ │
│  │  (Flask)     │   API   │  │ FastAPI Controller │  │ │
│  │  + SQLite    │         │  ├────────────────────┤  │ │
│  └──────────────┘         │  │ Pinned Worker      │  │ │
│       Port 8089           │  ├────────────────────┤  │ │
│                           │  │ FIFO Worker        │  │ │
│                           │  ├────────────────────┤  │ │
│                           │  │ Redis Queue/Cache  │  │ │
│                           │  └────────────────────┘  │ │
│                           │       Port 9000          │ │
│                           └──────────────────────────┘ │
│                                       │                 │
└───────────────────────────────────────┼─────────────────┘
                                        │ SSH/Telnet
                                        ▼
                              Network Devices

                 Optional: Netbox Integration ◄────────┘
```

**Key Points:**
- **Unified Platform**: Both frontend and backend deploy together
- **Pre-integrated**: Web UI automatically connects to backend API
- **Microservices**: Scalable worker architecture for task processing
- **Persistent Storage**: SQLite for UI data, Redis for task queuing
- **Network Automation**: Direct device access via Netmiko (SSH/Telnet)

## 📁 Directory Structure

```
netstacks/
├── app.py                      # Flask application (Web UI)
├── database.py                 # SQLite database layer
├── netbox_client.py            # Netbox API client
├── requirements.txt            # Python dependencies
├── Dockerfile                  # NetStacks Web UI container
├── docker-compose.yml          # Complete platform deployment
├── .env.example                # Environment variable template
├── templates/                  # HTML templates (Flask)
│   ├── base.html
│   ├── index.html
│   ├── services.html
│   ├── service-stacks.html
│   └── ...
├── static/                     # Static assets (CSS, JS)
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── services.js
│       ├── service-stacks.js
│       └── ...
└── netstacker/                 # Backend API platform
    ├── docker-compose.yml      # Backend-only deployment (optional)
    ├── netstacker/             # Backend Python code
    │   ├── netstacker_controller.py
    │   ├── backend/
    │   │   ├── core/
    │   │   └── plugins/
    │   └── routers/
    ├── dockerfiles/            # Backend Dockerfiles
    ├── config/                 # Backend configuration
    └── tests/                  # Backend tests
```

**Note**: Jinja2 configuration templates are stored in the Netstacker backend under `netstacker/netstacker/backend/plugins/extensibles/j2_config_templates/`

## 🛠️ Usage

### Creating Templates

1. Navigate to **Templates** page
2. Create a new Jinja2 template (e.g., `add_snmp.j2`)
3. Define template variables using `{{ variable_name }}` syntax
4. Optionally link validation and delete templates
5. Click **Save to Netstacker** - templates are stored in Netstacker

**Example Template:**
```jinja2
snmp-server community {{ snmp_community }} {{ snmp_mode }}
snmp-server location {{ snmp_location }}
snmp-server contact {{ snmp_contact }}
```

**Note**: Templates are stored in Netstacker, not locally. NetStacks uses Netstacker's template rendering engine for all deployments.

### Deploying Services

1. Go to **Services** page
2. Click **Deploy New Service**
3. Select a template
4. Fill in template variables
5. Select target device(s)
6. Click **Deploy**

### Creating Service Stacks

1. Navigate to **Service Stacks** page
2. Click **Create Stack**
3. Add services to the stack
4. Define dependencies between services
5. Save and deploy the stack

### Validating Configurations

1. Find a deployed service or stack
2. Click **Validate**
3. NetStacks will check if the configuration exists on the device
4. View validation results

### Deleting Services

1. Find a deployed service
2. Click **Delete**
3. NetStacks will:
   - Render the delete template (if configured)
   - Execute delete commands on the device
   - Remove the service from tracking

## 🔌 Netstacker Integration

NetStacks uses the following Netstacker API endpoints:

- `/setconfig` - Deploy configurations via Netmiko
- `/getconfig` - Retrieve device configurations
- `/j2template/config/` - List available templates
- `/task/<task_id>` - Monitor task execution

## 🐳 Docker Configuration

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `NETSTACKER_API_KEY` | `2a84465a-cf38-46b2-9d86-b84Q7d57f288` | API key for backend authentication |
| `DB_FILE` | `/data/netstacks.db` | SQLite database file path |

**Note**: The Web UI is pre-configured to connect to the backend API at `http://netstacker-controller:9000`. Netbox connections are configured via the GUI at `/settings`.

### Ports

| Service | Port | Description |
|---------|------|-------------|
| NetStacks Web UI | 8089 | Main web interface |
| Netstacker API | 9000 | Backend REST API / Swagger UI |

### Volumes

- `netstacks-data:/data` - Persistent SQLite database storage for settings and service data

### Services

The unified docker-compose deploys 5 services:

1. **netstacks** - Flask web UI for managing configurations
2. **netstacker-controller** - FastAPI backend server
3. **netstacker-worker-pinned** - RQ worker for pinned tasks
4. **netstacker-worker-fifo** - RQ worker for FIFO tasks
5. **redis** - Task queue and caching layer

## 🔄 Updating

To update NetStacks:

```bash
cd netstacks
git pull
docker-compose down
docker-compose up -d --build
```

## 🐛 Troubleshooting

### Cannot connect to Netstacker

**Use the Test Connection button:**
1. Go to `http://localhost:8088/settings`
2. Enter your Netstacker URL and API key
3. Click "Test Netstacker Connection"
4. Review the error message

**Common issues:**
- Incorrect Netstacker URL (check protocol: http vs https)
- Invalid API key
- Firewall blocking NetStacks → Netstacker connection
- Netstacker server not running

**Check NetStacks logs:**
```bash
docker logs netstacks
```

### Cannot connect to Netbox

**Use the Test Connection button:**
1. Go to `http://localhost:8088/settings`
2. Enter your Netbox URL and token
3. Click "Test Netbox Connection"

### Templates not loading

Templates are stored in Netstacker. Check:
1. Netstacker connection is working (test via `/settings`)
2. Templates exist in Netstacker (`curl http://netstacker:9000/j2template/config/` with API key)
3. Check NetStacks logs: `docker logs netstacks`

### Settings not persisting

Verify the SQLite database volume exists:
```bash
docker volume ls | grep netstacks-data
docker exec netstacks ls -la /data
```

## 📝 Template Metadata

NetStacks stores template metadata in SQLite database:

- **Description**: Human-readable template description
- **Validation Template**: Template used to validate deployments
- **Delete Template**: Template used to remove configurations

This metadata enhances the template system by linking related templates together.

## 🤝 Contributing

When contributing:

1. Ensure compatibility with Netstacker API
2. Test against multiple configurations
3. Document new features
4. Follow existing code style

## 📄 License

NetStacks is open-source software released under the MIT License. See LICENSE file for details.

## 🔗 Related Projects

- [Netbox](https://github.com/netbox-community/netbox) - Network inventory system for device management

## 💬 Support

For issues related to:
- **NetStacks UI**: Open an issue in this repository
- **Netstacker API**: See Netstacker documentation
- **Network devices**: Consult your device vendor documentation

---

**Built with ❤️ for network automation**
