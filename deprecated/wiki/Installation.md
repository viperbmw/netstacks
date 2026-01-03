# Installation

This guide covers deploying NetStacks using Docker Compose.

## Prerequisites

- **Docker**: Version 20.10 or later
- **Docker Compose**: Version 2.0 or later
- **Git**: For cloning the repository
- **Network Access**: SSH access to managed devices

## Quick Installation

### 1. Clone the Repository

```bash
git clone https://github.com/viperbmw/netstacks.git
cd netstacks
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to customize your deployment:

```bash
# Required
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here

# Database (defaults work for Docker)
DATABASE_URL=postgresql://netstacks:netstacks_secret@postgres:5432/netstacks

# Redis (defaults work for Docker)
REDIS_URL=redis://redis:6379/0

# Timezone
TZ=America/New_York
```

### 3. Start the Platform

```bash
docker-compose up -d
```

### 4. Verify Deployment

Check that all containers are running:

```bash
docker-compose ps
```

Expected output:
```
NAME                    STATUS
netstacks              Up
netstacks-workers      Up
netstacks-workers-beat Up
netstacks-postgres     Up
netstacks-redis        Up
```

### 5. Access the Platform

Open your browser to: `http://localhost:8089`

Default credentials:
- **Username**: `admin`
- **Password**: `admin`

> **Security Warning**: Change the default password immediately after first login!

## Container Architecture

| Container | Purpose | Internal Port |
|-----------|---------|---------------|
| `netstacks` | Web UI + Flask API | 8088 |
| `netstacks-workers` | Celery workers for device operations | - |
| `netstacks-workers-beat` | Celery beat scheduler | - |
| `netstacks-postgres` | PostgreSQL database | 5432 |
| `netstacks-redis` | Redis for task queue | 6379 |
| `netstacks-traefik` | Reverse proxy (optional) | 80, 8080 |

## Port Mapping

| Host Port | Container | Description |
|-----------|-----------|-------------|
| 8089 | netstacks:8088 | Main web interface |
| 80 | traefik:80 | Traefik reverse proxy |
| 8080 | traefik:8080 | Traefik dashboard |

## Data Persistence

Data is stored in Docker volumes:

| Volume | Purpose |
|--------|---------|
| `netstacks_postgres_data` | PostgreSQL database |
| `netstacks_redis_data` | Redis persistence |

### Backup Database

```bash
docker-compose exec netstacks-postgres pg_dump -U netstacks netstacks > backup.sql
```

### Restore Database

```bash
cat backup.sql | docker-compose exec -T netstacks-postgres psql -U netstacks netstacks
```

## Updating

To update NetStacks to the latest version:

```bash
cd netstacks
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Uninstalling

To completely remove NetStacks:

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker rmi $(docker images 'netstacks*' -q)
```

## Production Deployment

For production environments, consider:

### 1. Secure Secrets

Generate strong secrets:

```bash
# Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Enable HTTPS

Configure Traefik with TLS certificates or use a reverse proxy like nginx.

### 3. External Database

Use an external PostgreSQL instance:

```yaml
# docker-compose.override.yml
services:
  netstacks:
    environment:
      DATABASE_URL: postgresql://user:pass@external-db:5432/netstacks
```

### 4. Resource Limits

Add resource limits in docker-compose:

```yaml
services:
  netstacks:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## Next Steps

- [[Configuration]] - Configure environment and settings
- [[Quick Start Guide]] - Deploy your first configuration
- [[Authentication]] - Set up LDAP or OIDC
