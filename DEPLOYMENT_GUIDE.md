# NetStacks Deployment Guide

This guide explains how to deploy and configure NetStacks as a standalone network automation UI.

## 🚀 Quick Deployment

### Prerequisites

1. **Docker & Docker Compose** installed on your system
2. **Netpalm server** running somewhere (local or remote) that NetStacks can reach via HTTP/HTTPS
3. **(Optional) Netbox** server for device inventory

### Deploy in 3 Steps

```bash
# 1. Clone/download NetStacks
cd /path/to/netstacks

# 2. Start NetStacks
docker-compose up -d

# 3. Configure via GUI
# Open http://localhost:8088/settings
# Enter your Netpalm URL and API key
```

That's it! NetStacks is now running with its own Redis instance for persistent storage.

## 🌐 Architecture Overview

NetStacks is a **standalone web application** that connects to external services:

```
┌──────────────────┐
│   NetStacks      │     - Web UI (Flask)
│   Container      │     - Redis (settings & data storage)
│                  │     - Template engine
└────────┬─────────┘
         │
         │ HTTP/HTTPS API calls
         │
         ├──────────────────────────────────────┐
         │                                      │
         ▼                                      ▼
┌────────────────┐                    ┌────────────────┐
│ Netpalm Server │                    │ Netbox Server  │
│   (Required)   │                    │   (Optional)   │
└────────────────┘                    └────────────────┘
```

**Key Design Principles:**
- ✅ **Standalone**: NetStacks runs independently with its own Redis
- ✅ **GUI-First**: All configuration done via web interface at `/settings`
- ✅ **No Network Requirements**: Connects to external services via HTTP/HTTPS only
- ✅ **Persistent Settings**: All configuration stored in Redis (survives container restarts)

## 📋 Configuration

### Initial Setup via GUI

1. **Start NetStacks:**
   ```bash
   docker-compose up -d
   ```

2. **Open Settings Page:**
   Navigate to `http://localhost:8088/settings`

3. **Configure Netpalm Connection:**
   - **Netpalm URL**: Your Netpalm server (e.g., `http://192.168.1.100:9000` or `https://netpalm.example.com:9000`)
   - **Netpalm API Key**: Your Netpalm authentication key
   - Click "Test Netpalm Connection" to verify
   - Click "Save Settings"

4. **Configure Netbox (Optional):**
   - **Netbox URL**: Your Netbox server (e.g., `https://netbox.example.com`)
   - **Netbox Token**: Your Netbox API token
   - **SSL Verification**: Enable if using trusted SSL certificate
   - Click "Test Netbox Connection" to verify
   - Click "Save Settings"

All settings are saved to Redis and persist across container restarts.

### Environment Variables (Optional)

NetStacks uses minimal environment variables. Most configuration is done via GUI.

**Available Environment Variables** (`.env` file):

```bash
# Redis Configuration (NetStacks' own Redis - rarely needs changing)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=Red1zp4ww0rd_

# NetStacks Web UI Port
NETSTACKS_PORT=8088
```

**Note:** Netpalm and Netbox connections are **NOT** configured via environment variables. Use the GUI at `/settings`.

## 🐳 Docker Compose Configuration

The `docker-compose.yml` file defines two services:

### 1. NetStacks Service

```yaml
services:
  netstacks:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: netstacks
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=Red1zp4ww0rd_
      - TEMPLATE_DIR=/app/j2_templates
    ports:
      - "8088:8088"
    volumes:
      - ./j2_templates:/app/j2_templates
    depends_on:
      - redis
```

### 2. Redis Service

```yaml
  redis:
    image: redis:6-alpine
    container_name: netstacks-redis
    command: redis-server --requirepass Red1zp4ww0rd_
    volumes:
      - redis-data:/data
```

## 📁 Template Management

### Template Directory

NetStacks includes its own `j2_templates/` directory for Jinja2 templates:

```
netstacks/
└── j2_templates/
    ├── cisco_ios_add_snmp_config.j2
    ├── cisco_ios_remove_snmp_config.j2
    ├── cisco_ios_snmp_validate.j2
    └── ... (your custom templates)
```

Templates are mounted into the container at `/app/j2_templates`.

### Creating Templates

1. Add `.j2` files to the `j2_templates/` directory on your host
2. Templates are automatically detected (no restart required)
3. Use the **Templates** page in the GUI to view and manage metadata
4. Link validation and delete templates to service templates

### Example Template

```jinja2
! SNMP Configuration
snmp-server community {{ snmp_community }} {{ snmp_mode }}
snmp-server location {{ snmp_location }}
snmp-server contact {{ snmp_contact }}
```

## 🔄 Updating NetStacks

To update NetStacks to a newer version:

```bash
cd /path/to/netstacks

# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

**Your settings and data are preserved** in the `redis-data` Docker volume.

## 🐛 Troubleshooting

### Cannot Connect to Netpalm

**Symptoms:** Services fail to deploy, "Connection refused" errors

**Solutions:**
1. **Test the connection** via GUI:
   - Go to `http://localhost:8088/settings`
   - Click "Test Netpalm Connection"
   - Review the error message

2. **Common issues:**
   - Wrong protocol (http vs https)
   - Incorrect port number
   - Invalid API key
   - Firewall blocking NetStacks → Netpalm traffic
   - Netpalm server not running

3. **Verify Netpalm is accessible:**
   ```bash
   # From NetStacks container
   docker exec netstacks curl http://your-netpalm-url:9000/workers
   ```

### Cannot Connect to Netbox

**Symptoms:** Devices page empty, "Failed to fetch devices" error

**Solutions:**
1. **Test the connection** via GUI:
   - Go to `http://localhost:8088/settings`
   - Click "Test Netbox Connection"

2. **Common issues:**
   - Invalid Netbox URL
   - Incorrect API token
   - SSL certificate issues (try disabling SSL verification)

### Templates Not Loading

**Symptoms:** Deploy page shows no templates

**Solutions:**
1. **Verify templates exist:**
   ```bash
   ls -la netstacks/j2_templates/
   ```

2. **Check template mount:**
   ```bash
   docker exec netstacks ls /app/j2_templates
   ```

3. **Ensure templates have `.j2` extension**

### Settings Not Persisting

**Symptoms:** Settings reset after container restart

**Solutions:**
1. **Verify Redis is running:**
   ```bash
   docker ps | grep netstacks-redis
   ```

2. **Check Redis data volume:**
   ```bash
   docker volume ls | grep redis-data
   ```

3. **Test Redis connection:**
   ```bash
   docker exec netstacks-redis redis-cli -a Red1zp4ww0rd_ ping
   ```

### Check NetStacks Logs

```bash
# View live logs
docker logs -f netstacks

# View last 100 lines
docker logs --tail 100 netstacks

# Search logs for errors
docker logs netstacks 2>&1 | grep -i error
```

## 📊 Monitoring

### Container Health

```bash
# Check running containers
docker ps | grep netstacks

# Check resource usage
docker stats netstacks netstacks-redis

# View detailed container info
docker inspect netstacks
```

### Application Health

```bash
# Test web UI
curl http://localhost:8088/

# Test API endpoint
curl http://localhost:8088/api/templates

# Check settings endpoint
curl http://localhost:8088/api/settings
```

## 💾 Backup and Restore

### Backup Redis Data

```bash
# Create backup
docker exec netstacks-redis redis-cli -a Red1zp4ww0rd_ SAVE
docker cp netstacks-redis:/data/dump.rdb ./netstacks-backup-$(date +%Y%m%d).rdb

# Or backup the entire volume
docker run --rm -v netstacks_redis-data:/data -v $(pwd):/backup alpine tar czf /backup/netstacks-redis-$(date +%Y%m%d).tar.gz /data
```

### Restore Redis Data

```bash
# Stop containers
docker-compose down

# Restore volume
docker run --rm -v netstacks_redis-data:/data -v $(pwd):/backup alpine tar xzf /backup/netstacks-redis-YYYYMMDD.tar.gz -C /

# Restart
docker-compose up -d
```

## 🔒 Security Considerations

### 1. Change Default Redis Password

Edit `docker-compose.yml`:

```yaml
redis:
  command: redis-server --requirepass YOUR_SECURE_PASSWORD
```

Update `.env`:
```bash
REDIS_PASSWORD=YOUR_SECURE_PASSWORD
```

Rebuild:
```bash
docker-compose down
docker-compose up -d
```

### 2. Use HTTPS for External Connections

When connecting to remote Netpalm/Netbox servers, always use HTTPS:

```
✅ https://netpalm.example.com:9000
❌ http://netpalm.example.com:9000
```

### 3. Protect the Web UI

NetStacks currently has no authentication. Protect it using:

- **Reverse proxy with authentication** (nginx, Traefik)
- **VPN access only**
- **Firewall rules** (restrict to trusted IPs)

### 4. Secure API Keys

- Never commit API keys to version control
- Configure via GUI only (stored encrypted in Redis)
- Rotate keys regularly

## 🎯 Best Practices

1. **Use GUI for All Configuration** - Don't rely on environment variables for Netpalm/Netbox
2. **Keep Templates in Version Control** - Store `j2_templates/` in Git
3. **Regular Backups** - Backup Redis data weekly
4. **Monitor Logs** - Check for errors regularly
5. **Test Connections** - Use built-in test buttons after configuration changes
6. **Document Custom Templates** - Add descriptions in template metadata
7. **Use Service Stacks** - Group related configurations for easier management

## 🔗 Related Documentation

- [README.md](README.md) - Main documentation and feature overview
- [Netpalm Documentation](https://github.com/tbotnz/netpalm) - Netpalm API reference
- [Netbox Documentation](https://docs.netbox.dev/) - Netbox API reference

## 💬 Support

**For issues related to:**
- **NetStacks UI/Features**: Open an issue in this repository
- **Netpalm API**: See [Netpalm documentation](https://github.com/tbotnz/netpalm)
- **Netbox Integration**: See [Netbox API docs](https://docs.netbox.dev/en/stable/integrations/rest-api/)

---

**Built with ❤️ for network automation**
