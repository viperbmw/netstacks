# Multi-Architecture Support

NetStacks now supports building Docker images for multiple architectures, including AMD64 (x86_64) and ARM64 (aarch64).

## Prerequisites

**Docker Compose v2 Required**: The multi-arch configuration requires Docker Compose v2.x or later. If you see errors about unsupported `platforms` option, you need to upgrade.

### Check Your Version

```bash
# Check if you have Docker Compose v2
docker compose version

# Old v1 (not supported for multi-arch)
docker-compose --version
```

### Install/Upgrade Docker Compose v2

**Quick Install (Ubuntu/Debian):**

```bash
# Run the provided installation script
./install-docker-compose-v2.sh
```

**Manual Install:**

```bash
# Update package index
sudo apt-get update

# Install Docker Compose v2 plugin
sudo apt-get install -y docker-compose-plugin

# Verify installation
docker compose version
```

**Important**: Docker Compose v2 uses `docker compose` (with a space), not `docker-compose` (with a hyphen).

## Supported Platforms

- `linux/amd64` - Intel/AMD 64-bit processors
- `linux/arm64` - ARM 64-bit processors (Apple Silicon, Raspberry Pi 4+, AWS Graviton, etc.)

## Quick Start

### Building for Your Current Platform

When using standard `docker compose` commands, images will build for your current architecture automatically:

```bash
docker compose build
docker compose up -d
```

### Building for a Specific Platform

Set the `DOCKER_DEFAULT_PLATFORM` environment variable:

```bash
# For AMD64
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker compose build

# For ARM64
export DOCKER_DEFAULT_PLATFORM=linux/arm64
docker compose build
```

Or use the `.env` file:

```bash
# Copy and edit .env.example
cp .env.example .env

# Edit .env and uncomment the desired platform
# DOCKER_DEFAULT_PLATFORM=linux/arm64
```

### Building Multi-Architecture Images

Use the provided build script to build images for multiple architectures:

```bash
# Build for both AMD64 and ARM64 (local build - current platform only)
./build-multiarch.sh

# Build and push to Docker Hub
./build-multiarch.sh --push --registry docker.io/yourusername --tag v1.0.0

# Build only for ARM64
./build-multiarch.sh --platforms linux/arm64

# Show help
./build-multiarch.sh --help
```

## Docker Compose Configuration

The `docker-compose.yml` file has been configured with:

1. **Build platforms**: Each service specifies `platforms: [linux/amd64, linux/arm64]`
2. **Runtime platform**: Each service uses `platform: ${DOCKER_DEFAULT_PLATFORM:-linux/amd64}`
3. **Default behavior**: If `DOCKER_DEFAULT_PLATFORM` is not set, it defaults to `linux/amd64`

## Building for Registry/Distribution

To build and distribute multi-arch images:

### 1. Ensure buildx is configured

```bash
# Check buildx version
docker buildx version

# Create a multiarch builder (if not exists)
docker buildx create --name multiarch --use

# Verify platforms are available
docker buildx inspect --bootstrap
```

### 2. Build and push to registry

```bash
# Using the build script
./build-multiarch.sh \
  --push \
  --registry docker.io/yourusername \
  --tag v1.0.0

# Or manually with docker buildx
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag yourusername/netstacks:v1.0.0 \
  --push \
  .
```

### 3. Update docker-compose.yml to use registry images

```yaml
services:
  netstacks:
    image: yourusername/netstacks:v1.0.0
    # Remove or comment out the 'build' section
```

## Platform-Specific Considerations

### ARM64 Notes

- All base images (Python 3.9, Python 3.8, Redis 6.0.7) support ARM64
- Build times may be slower when cross-compiling on AMD64 hosts
- Native ARM64 builds (on ARM64 hardware) are significantly faster

### Apple Silicon (M1/M2/M3)

Apple Silicon Macs use ARM64 architecture. To build and run natively:

```bash
# Option 1: Use the default setting (will build for your platform)
docker compose build

# Option 2: Explicitly set ARM64
export DOCKER_DEFAULT_PLATFORM=linux/arm64
docker compose build
```

### Cross-Platform Building

When building on one platform for another (e.g., building ARM64 images on AMD64):

1. QEMU emulation is automatically used by Docker buildx
2. First build may take longer as QEMU registers are set up
3. Subsequent builds use caching

## Troubleshooting

### "unsupported option: 'platforms'" Error

**Problem**: You see this error when running `docker-compose up`:
```
ERROR: services.netstacks.build contains unsupported option: 'platforms'
```

**Solution**: You're using Docker Compose v1, which doesn't support the `platforms` option. Upgrade to v2:

```bash
# Install Docker Compose v2
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Use the new command (note the space instead of hyphen)
docker compose up -d
```

### "exec user process caused: exec format error"

This means you're trying to run an image built for a different architecture. Rebuild with:

```bash
docker compose build --no-cache
```

### Buildx not available

Install buildx:

```bash
# On most systems, buildx comes with Docker Desktop
# For Linux, install docker-buildx-plugin
sudo apt-get install docker-buildx-plugin
```

### Slow cross-platform builds

This is expected when building for a different architecture. To speed up:

1. Use `--push` to build on Docker Hub's multi-arch builders
2. Build natively on target architecture
3. Use layer caching effectively

## Testing Multi-Arch Images

To test if an image supports multiple architectures:

```bash
# Inspect manifest
docker buildx imagetools inspect yourusername/netstacks:v1.0.0

# You should see multiple platforms listed
```

## References

- [Docker Buildx Documentation](https://docs.docker.com/buildx/working-with-buildx/)
- [Multi-platform images](https://docs.docker.com/build/building/multi-platform/)
- [Docker Compose Build Documentation](https://docs.docker.com/compose/compose-file/build/)
