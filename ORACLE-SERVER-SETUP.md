# Setup Guide for Oracle ARM64 Server

## Issue
You're seeing this error on your Oracle server:
```
ERROR: services.netstacks.build contains unsupported option: 'platforms'
```

This happens because your server has Docker Compose v1, which doesn't support multi-arch builds.

## Solution: Upgrade to Docker Compose v2

### Option 1: Use the Installation Script

1. Copy the installation script to your Oracle server:
```bash
# On your Oracle server
scp install-docker-compose-v2.sh ubuntu@oracle-hopper:~/netstacks/
```

2. Run the script:
```bash
# SSH to your Oracle server
ssh ubuntu@oracle-hopper

# Navigate to netstacks directory
cd ~/netstacks

# Run installation script
chmod +x install-docker-compose-v2.sh
./install-docker-compose-v2.sh
```

### Option 2: Manual Installation

Run these commands on your Oracle server:

```bash
# Update package index
sudo apt-get update

# Install Docker Compose v2 plugin
sudo apt-get install -y docker-compose-plugin

# Verify installation
docker compose version
```

### If "docker: 'compose' is not a docker command" Error

If the plugin is installed but Docker can't find it, run this fix:

```bash
# Download and run the fix script
curl -O https://raw.githubusercontent.com/yourusername/netstacks/main/fix-docker-compose.sh
chmod +x fix-docker-compose.sh
./fix-docker-compose.sh
```

**Or manually fix it:**

```bash
# Create CLI plugins directory
sudo mkdir -p /usr/libexec/docker/cli-plugins

# Download compose binary directly
COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
  -o /usr/libexec/docker/cli-plugins/docker-compose

# Make it executable
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose

# Test
docker compose version
```

## After Installation

**Important**: Use `docker compose` (with a space), NOT `docker-compose` (with a hyphen)

```bash
# Old command (v1) - DON'T USE
docker-compose up -d

# New command (v2) - USE THIS
docker compose up -d
```

## Building and Running NetStacks on ARM64

Your Oracle server is ARM64 (aarch64), so:

```bash
# Set platform to ARM64 (optional, auto-detected)
export DOCKER_DEFAULT_PLATFORM=linux/arm64

# Build for ARM64
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps
```

## Quick Commands

```bash
# Stop services
docker compose down

# View logs
docker compose logs -f

# Rebuild specific service
docker compose build netstacks

# Restart a service
docker compose restart netstacker-controller
```

## Verifying Architecture

After building, verify your images are ARM64:

```bash
docker image inspect netstacks-netstacks:latest --format '{{.Architecture}}'
# Should output: arm64
```

## Performance Notes

- ARM64 builds on ARM64 hardware are **much faster** than cross-compilation
- Your Oracle ARM server will build images natively for ARM64
- Build times should be reasonable (similar to AMD64 on equivalent hardware)
