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

1. **Netpalm Instance**: A running Netpalm installation that NetStacks can reach via HTTP/HTTPS (see [Netpalm on GitHub](https://github.com/tbotnz/netpalm))
2. **Docker & Docker Compose**: For containerized deployment
3. **(Optional) Netbox**: For automatic device inventory management

## 🔧 Quick Start

### 1. Clone or Download NetStacks

```bash
git clone <your-netstacks-repo>
cd netstacks
```

### 2. (Optional) Customize Port

By default, NetStacks runs on port 8088. To change:

```bash
cp .env.example .env
# Edit .env and set NETSTACKS_PORT if desired
```

### 3. Deploy NetStacks

```bash
docker-compose up -d
```

### 4. Configure via Web Interface

Open your browser to: `http://localhost:8088/settings`

Configure your connections:
- **Netpalm URL**: Point to your Netpalm server (e.g., `http://netpalm.example.com:9000`)
- **Netpalm API Key**: Your Netpalm authentication key
- **Netbox URL**: (Optional) Your Netbox server URL
- **Netbox Token**: (Optional) Your Netbox API token

All settings are saved to SQLite database and persist across restarts.

### 5. Start Using NetStacks

Navigate to the Dashboard: `http://localhost:8088`

## 🌐 Architecture

NetStacks is a **standalone application** that connects to external services:

```
┌─────────────┐      HTTP/HTTPS       ┌─────────────┐
│  NetStacks  │ ───────────────────> │   Netpalm   │
│  + SQLite   │                       │   Server    │
└─────────────┘                       └─────────────┘
       │
       │ HTTP/HTTPS (optional)
       │
       ▼
┌─────────────┐
│   Netbox    │
│   Server    │
└─────────────┘
```

**Key Points:**
- NetStacks runs standalone with embedded SQLite database
- Connects to Netpalm via HTTP/HTTPS API calls
- No Docker network requirements
- Configure all connections via the GUI at `/settings`

## 📁 Directory Structure

```
netstacks/
├── app.py                      # Flask application
├── database.py                 # SQLite database layer
├── netbox_client.py            # Netbox API client
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker container definition
├── docker-compose.yml          # Standalone deployment
├── .env.example                # Environment variable template
├── templates/                  # HTML templates (Flask)
│   ├── base.html
│   ├── index.html
│   ├── services.html
│   ├── service-stacks.html
│   └── ...
└── static/                     # Static assets (CSS, JS)
    ├── css/
    │   └── style.css
    └── js/
        ├── services.js
        ├── service-stacks.js
        └── ...
```

**Note**: Jinja2 configuration templates are stored in Netpalm, not in the local filesystem.

## 🛠️ Usage

### Creating Templates

1. Navigate to **Templates** page
2. Create a new Jinja2 template (e.g., `add_snmp.j2`)
3. Define template variables using `{{ variable_name }}` syntax
4. Optionally link validation and delete templates
5. Click **Save to Netpalm** - templates are stored in Netpalm

**Example Template:**
```jinja2
snmp-server community {{ snmp_community }} {{ snmp_mode }}
snmp-server location {{ snmp_location }}
snmp-server contact {{ snmp_contact }}
```

**Note**: Templates are stored in Netpalm, not locally. NetStacks uses Netpalm's template rendering engine for all deployments.

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

## 🔌 Netpalm Integration

NetStacks uses the following Netpalm API endpoints:

- `/setconfig` - Deploy configurations via Netmiko
- `/getconfig` - Retrieve device configurations
- `/j2template/config/` - List available templates
- `/task/<task_id>` - Monitor task execution

## 🐳 Docker Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_FILE` | `/data/netstacks.db` | SQLite database file path |
| `NETSTACKS_PORT` | `8088` | Port to expose NetStacks on |

**Note**: Netpalm and Netbox connections are configured via the GUI at `/settings` and stored in SQLite database. Templates are managed via GUI and stored in Netpalm.

### Volumes

- `netstacks-data:/data` - Persistent SQLite database storage for settings and service data

## 🔄 Updating

To update NetStacks:

```bash
cd netstacks
git pull
docker-compose down
docker-compose up -d --build
```

## 🐛 Troubleshooting

### Cannot connect to Netpalm

**Use the Test Connection button:**
1. Go to `http://localhost:8088/settings`
2. Enter your Netpalm URL and API key
3. Click "Test Netpalm Connection"
4. Review the error message

**Common issues:**
- Incorrect Netpalm URL (check protocol: http vs https)
- Invalid API key
- Firewall blocking NetStacks → Netpalm connection
- Netpalm server not running

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

Templates are stored in Netpalm. Check:
1. Netpalm connection is working (test via `/settings`)
2. Templates exist in Netpalm (`curl http://netpalm:9000/j2template/config/` with API key)
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

NetStacks is designed to work with the upstream Netpalm project. When contributing:

1. Ensure compatibility with Netpalm API
2. Test against multiple Netpalm versions
3. Document new features
4. Follow existing code style

## 📄 License

NetStacks is open-source software released under the MIT License. See LICENSE file for details.

## 🔗 Related Projects

- [Netpalm](https://github.com/tbotnz/netpalm) - The network automation platform NetStacks connects to
- [Netbox](https://github.com/netbox-community/netbox) - Network inventory system for device management

## 💬 Support

For issues related to:
- **NetStacks UI**: Open an issue in this repository
- **Netpalm API**: See [Netpalm documentation](https://github.com/tbotnz/netpalm)
- **Network devices**: Consult your device vendor documentation

---

**Built with ❤️ for network automation**
