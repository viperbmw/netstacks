#!/bin/bash
# Multi-Architecture Build Script for NetStacks
# This script builds and optionally pushes multi-arch images to a registry

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
PUSH=false
REGISTRY=""
TAG="latest"
PLATFORMS="linux/amd64,linux/arm64"

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Build multi-architecture Docker images for NetStacks"
    echo ""
    echo "Options:"
    echo "  -p, --push              Push images to registry after building"
    echo "  -r, --registry REGISTRY Registry URL (e.g., docker.io/username)"
    echo "  -t, --tag TAG          Image tag (default: latest)"
    echo "  --platforms PLATFORMS  Comma-separated platforms (default: linux/amd64,linux/arm64)"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Build locally for both AMD64 and ARM64"
    echo "  $0"
    echo ""
    echo "  # Build and push to Docker Hub"
    echo "  $0 --push --registry docker.io/myuser --tag v1.0.0"
    echo ""
    echo "  # Build only for ARM64"
    echo "  $0 --platforms linux/arm64"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--push)
            PUSH=true
            shift
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        --platforms)
            PLATFORMS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            usage
            ;;
    esac
done

# Validate push requirements
if [ "$PUSH" = true ] && [ -z "$REGISTRY" ]; then
    echo -e "${RED}Error: --registry is required when using --push${NC}"
    exit 1
fi

# Create or use existing buildx builder
echo -e "${GREEN}Setting up buildx builder...${NC}"
if ! docker buildx inspect multiarch &>/dev/null; then
    docker buildx create --name multiarch --use
else
    docker buildx use multiarch
fi

# Build function
build_image() {
    local service=$1
    local context=$2
    local dockerfile=$3
    local image_name="${service}"
    
    if [ -n "$REGISTRY" ]; then
        image_name="${REGISTRY}/${service}"
    fi
    
    echo -e "${YELLOW}Building ${service} for platforms: ${PLATFORMS}${NC}"
    
    if [ "$PUSH" = true ]; then
        docker buildx build \
            --platform "${PLATFORMS}" \
            --tag "${image_name}:${TAG}" \
            --tag "${image_name}:latest" \
            --file "${dockerfile}" \
            --push \
            "${context}"
    else
        docker buildx build \
            --platform "${PLATFORMS}" \
            --tag "${image_name}:${TAG}" \
            --file "${dockerfile}" \
            --load \
            "${context}"
    fi
    
    echo -e "${GREEN}✓ Built ${service}${NC}"
}

# Build all images
echo -e "${GREEN}Starting multi-architecture build...${NC}"
echo -e "${YELLOW}Platforms: ${PLATFORMS}${NC}"
echo -e "${YELLOW}Tag: ${TAG}${NC}"
if [ "$PUSH" = true ]; then
    echo -e "${YELLOW}Registry: ${REGISTRY}${NC}"
    echo -e "${YELLOW}Push: Enabled${NC}"
fi
echo ""

# Note: --load only works with single platform, so for local builds we'll build for current platform
if [ "$PUSH" = false ]; then
    echo -e "${YELLOW}Note: Local builds (without --push) will only build for the current platform${NC}"
    CURRENT_ARCH=$(docker version --format '{{.Server.Arch}}')
    PLATFORMS="linux/${CURRENT_ARCH}"
    echo -e "${YELLOW}Building for: ${PLATFORMS}${NC}"
    echo ""
fi

# Build each service
build_image "netstacks" "." "Dockerfile"
build_image "netstacker-controller" "./netstacker" "./netstacker/dockerfiles/netstacker_controller_dockerfile"
build_image "netstacker-worker-pinned" "./netstacker" "./netstacker/dockerfiles/netstacker_pinned_worker_dockerfile"
build_image "netstacker-worker-fifo" "./netstacker" "./netstacker/dockerfiles/netstacker_fifo_worker_dockerfile"
build_image "netstacker-redis" "./netstacker" "./netstacker/dockerfiles/netstacker_redis_dockerfile"

echo ""
echo -e "${GREEN}✓ All images built successfully!${NC}"

if [ "$PUSH" = true ]; then
    echo -e "${GREEN}✓ Images pushed to ${REGISTRY}${NC}"
else
    echo -e "${YELLOW}To push images to a registry, run with --push --registry <registry-url>${NC}"
fi
