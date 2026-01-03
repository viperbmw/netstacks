# Configuration

This guide covers all configuration options for NetStacks.

## Environment Variables

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | Auto-generated | Flask session encryption key |
| `JWT_SECRET_KEY` | Auto-generated | JWT token signing key |
| `TZ` | `America/New_York` | Timezone for scheduled operations |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://netstacks:...@postgres:5432/netstacks` | PostgreSQL connection string |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection for Celery |
| `CELERY_BROKER_URL` | Same as REDIS_URL | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Same as REDIS_URL | Celery result backend |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Application Settings

Access settings in the web UI at **Settings** or via API.

### Netbox Integration

| Setting | Description |
|---------|-------------|
| `netbox_url` | Netbox server URL (e.g., `https://netbox.example.com`) |
| `netbox_token` | Netbox API token |
| `verify_ssl` | Verify SSL certificates (default: false) |
| `netbox_filters` | Device filters for sync |
| `cache_ttl` | Cache duration in seconds (default: 300) |

### Default Credentials

| Setting | Description |
|---------|-------------|
| `default_username` | Default SSH username for devices |
| `default_password` | Default SSH password for devices |

> **Note**: Device-specific credentials override defaults.

## Timezone Configuration

NetStacks uses the container's timezone for all scheduled operations.

### Setting Timezone

1. Edit `docker-compose.yml`:

```yaml
services:
  netstacks:
    environment:
      - TZ=America/Los_Angeles
```

2. Restart the container:

```bash
docker-compose restart netstacks
```

### Common Timezones

| Region | Timezone |
|--------|----------|
| US Eastern | `America/New_York` |
| US Central | `America/Chicago` |
| US Mountain | `America/Denver` |
| US Pacific | `America/Los_Angeles` |
| UTC | `UTC` |
| UK | `Europe/London` |
| Central Europe | `Europe/Paris` |
| Japan | `Asia/Tokyo` |

### Verify Timezone

```bash
docker-compose exec netstacks date
```

## Celery Configuration

Celery handles background tasks like device operations.

### Worker Settings

In `docker-compose.yml`:

```yaml
netstacks-workers:
  command: celery -A tasks worker -l info --concurrency=4
```

| Option | Default | Description |
|--------|---------|-------------|
| `--concurrency` | 4 | Number of worker processes |
| `-l` | info | Log level |

### Beat Scheduler

The beat scheduler runs periodic tasks:

```yaml
netstacks-workers-beat:
  command: celery -A tasks beat -l info --schedule=/data/celerybeat-schedule
```

### Scheduled Tasks

| Task | Interval | Description |
|------|----------|-------------|
| `check_scheduled_operations` | 60s | Check for pending scheduled operations |
| `cleanup_old_backups` | Daily 3 AM | Remove backups older than retention period |

## SSL/TLS Configuration

### Netbox SSL

If Netbox uses a self-signed certificate:

```python
# In settings
verify_ssl: false
```

### Device SSH

NetStacks uses Netmiko for device connections. SSH settings are configured per-device.

## Docker Compose Overrides

Create `docker-compose.override.yml` for local customizations:

```yaml
version: '3.8'

services:
  netstacks:
    environment:
      - TZ=America/Los_Angeles
      - LOG_LEVEL=DEBUG
    ports:
      - "8089:8088"
      - "5000:5000"  # Debug port
```

## Configuration Files

### Main Configuration

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container orchestration |
| `.env` | Environment variables |
| `config.py` | Flask configuration |

### Database Models

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy ORM models |
| `database.py` | Database operations |

## Backup Configuration

### Backup Schedule Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | false | Enable scheduled backups |
| `interval_hours` | 24 | Backup frequency |
| `retention_days` | 30 | Days to keep backups |
| `juniper_set_format` | true | Use set format for Juniper |

Configure via UI at **Backups → Schedule** or API.

## Next Steps

- [[Authentication]] - Set up authentication methods
- [[Device Management]] - Add network devices
- [[AI Settings]] - Configure LLM providers
