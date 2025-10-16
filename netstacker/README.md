# Netstacker

**Network Automation Platform for Netstacks**

Netstacker is a streamlined network automation API platform designed specifically for use with Netstacks. It provides a modern REST API interface for network device configuration and state management using Netmiko.

## About

Netstacker is a focused fork of [netpalm](https://github.com/tbotnz/netpalm), optimized for Netstacks deployments. We've removed unnecessary drivers and features to create a lean, efficient platform centered on Netmiko-based network automation.

### What's Different from Netpalm?

- **Netmiko-Only**: Removed NAPALM, ncclient, and RESTCONF drivers
- **Simplified**: Removed service orchestration framework and GUI
- **Streamlined**: Focused on core getconfig/setconfig operations
- **Lightweight**: Reduced dependencies and complexity

## Features

- **REST API**: Modern OpenAPI 3.0 REST interface with interactive Swagger UI
- **Netmiko Support**: Full support for SSH/Telnet network device automation
- **PureSNMP Support**: SNMP operations for monitoring and configuration
- **Parser Integration**: Built-in support for TextFSM, TTP, and Genie parsers
- **Asynchronous Processing**: Redis-based task queue with RQ workers
- **Webhook Support**: Post-task webhook notifications
- **Jinja2 Templates**: Template-based configuration management
- **Custom Scripts**: Execute Python scripts via REST API
- **Pre/Post Checks**: Validate configurations before and after deployment
- **Caching**: Redis-based result caching for improved performance
- **Scalable Architecture**: Container-based microservices design

## Architecture

Netstacker consists of four main components:

```
┌─────────────────┐
│  Controller     │  FastAPI web server (port 9000)
│  (REST API)     │  Swagger UI at http://localhost:9000
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
┌────────▼────────┐  ┌────▼──────────┐
│  Redis          │  │  RQ Workers   │
│  (Queue/Cache)  │  │  - Pinned     │
└─────────────────┘  │  - FIFO       │
                     └───────────────┘
```

### Components

- **netstacker-controller**: FastAPI application serving REST API and Swagger UI
- **netstacker-worker-pinned**: Dedicated worker queues for device-specific tasks
- **netstacker-worker-fifo**: Shared worker pool for general tasks
- **redis**: Message broker and cache

## Installation

### Prerequisites

- Docker and Docker Compose
- Network access to target devices

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd netstacker
   ```

2. **Configure settings** (optional)
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start the services**
   ```bash
   docker compose up -d --build
   ```

4. **Access the API**
   - Swagger UI: http://localhost:9000
   - API Base: http://localhost:9000

## Configuration

### Environment Variables

Key environment variables (set in `.env`):

- `NETSTACKER_CONFIG`: Path to config.json
- `NETSTACKER_LOG_CONFIG_FILENAME`: Path to log configuration
- `NETSTACKER_REDIS_CACHE_ENABLED`: Enable/disable caching

### Configuration Files

- `config/config.json`: Main application configuration
- `config/defaults.json`: Default configuration values
- `config/log-config.yml`: Logging configuration

## API Usage

### Authentication

All API requests require an API key passed in the header:

```bash
curl -X GET "http://localhost:9000/task/task_id" \
  -H "x-api-key: your-api-key-here"
```

### Get Configuration (Netmiko)

Retrieve device configuration via SSH:

```bash
curl -X POST "http://localhost:9000/getconfig" \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "library": "netmiko",
    "connection_args": {
      "device_type": "cisco_ios",
      "host": "192.168.1.1",
      "username": "admin",
      "password": "password"
    },
    "command": "show running-config"
  }'
```

### Set Configuration (Netmiko)

Push configuration to a device:

```bash
curl -X POST "http://localhost:9000/setconfig" \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "library": "netmiko",
    "connection_args": {
      "device_type": "cisco_ios",
      "host": "192.168.1.1",
      "username": "admin",
      "password": "password"
    },
    "config": "interface GigabitEthernet0/1\n description Configured by Netstacker"
  }'
```

### Using TextFSM Parsers

Parse CLI output into structured data:

```bash
curl -X POST "http://localhost:9000/getconfig" \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "library": "netmiko",
    "connection_args": {
      "device_type": "cisco_ios",
      "host": "192.168.1.1",
      "username": "admin",
      "password": "password"
    },
    "command": "show ip interface brief",
    "args": {
      "use_textfsm": true
    }
  }'
```

### Check Task Status

```bash
curl -X GET "http://localhost:9000/task/{task_id}" \
  -H "x-api-key: your-api-key"
```

## Advanced Features

### Jinja2 Templates

Store and use Jinja2 templates for configuration:

1. Upload template via `/template/add/`
2. Reference in setconfig with `j2config` parameter

### Custom Scripts

Execute custom Python scripts:

```bash
curl -X POST "http://localhost:9000/script" \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "hello_world",
    "args": {
      "name": "Netstacker"
    }
  }'
```

### Pre/Post Checks

Validate configuration changes:

```json
{
  "library": "netmiko",
  "connection_args": {...},
  "config": "hostname new-hostname",
  "post_checks": [
    {
      "match_type": "include",
      "get_config_args": {
        "command": "show running-config | include hostname"
      },
      "match_str": ["hostname new-hostname"]
    }
  ]
}
```

### Queue Strategies

- **FIFO** (default): Tasks processed by shared worker pool
- **Pinned**: Dedicated queue per device for serial execution

```json
{
  "library": "netmiko",
  "connection_args": {...},
  "command": "show version",
  "queue_strategy": "pinned"
}
```

## Scaling

Scale workers horizontally:

```bash
docker compose up -d --scale netstacker-worker-fifo=5 --scale netstacker-worker-pinned=3
```

## Development

### Project Structure

```
netstacker/
├── netstacker/              # Main application code
│   ├── backend/
│   │   ├── core/           # Core functionality
│   │   │   ├── calls/      # API operation handlers
│   │   │   ├── driver/     # Driver base classes
│   │   │   ├── manager/    # Netstacker manager
│   │   │   └── models/     # Pydantic models
│   │   └── plugins/
│   │       ├── drivers/    # Netmiko and PureSNMP
│   │       └── extensibles/
│   ├── routers/            # FastAPI routers
│   ├── static/             # Swagger UI assets
│   └── templates/          # HTML templates
├── config/                 # Configuration files
├── tests/                  # Test suites
└── docker-compose.yml      # Container orchestration
```

### Running Tests

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires test devices)
pytest tests/integration/
```

## Supported Devices

Netstacker supports any device that Netmiko supports, including:

- Cisco IOS/IOS-XE/NX-OS/ASA
- Arista EOS
- Juniper Junos
- HP/Aruba
- Dell
- Palo Alto
- And 90+ more device types

See [Netmiko's supported platforms](https://github.com/ktbyers/netmiko#supported-platforms) for the full list.

## Troubleshooting

### Check Container Logs

```bash
docker compose logs netstacker-controller
docker compose logs netstacker-worker-fifo
```

### Verify Redis Connection

```bash
docker compose exec redis redis-cli ping
```

### Test API Connectivity

```bash
curl -X GET "http://localhost:9000/ping"
```

## API Documentation

Full API documentation is available via the interactive Swagger UI at:

**http://localhost:9000**

## Integration with Netstacks

Netstacker is designed to integrate seamlessly with Netstacks:

1. **Configuration Management**: Push/pull configs to Netstacks devices
2. **State Validation**: Pre/post checks ensure desired state
3. **Automation**: REST API enables programmatic network operations
4. **Monitoring**: SNMP support for device monitoring

## Contributing

This is a focused fork maintained for Netstacks use cases. For the upstream project:
- Original Project: [netpalm](https://github.com/tbotnz/netpalm)

## License

GNU Lesser General Public License v3.0 (LGPL-3.0)

See [LICENSE](LICENSE) for details.

## Credits

Netstacker is based on [netpalm](https://github.com/tbotnz/netpalm) by [tbotnz](https://github.com/tbotnz).

Built with:
- [Netmiko](https://github.com/ktbyers/netmiko) - Multi-vendor SSH library
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Redis](https://redis.io/) & [RQ](https://python-rq.org/) - Task queue
- [TextFSM](https://github.com/google/textfsm) - CLI parsing
- [TTP](https://ttp.readthedocs.io/) - Template Text Parser
- [Jinja2](https://jinja.palletsprojects.com/) - Template engine

## Support

For issues and questions related to Netstacker usage with Netstacks, please open an issue in this repository.

For general netpalm questions, see the [upstream project](https://github.com/tbotnz/netpalm).
