#!/bin/bash

# NetStacks Quick Start Script
# This script helps you get NetStacks up and running quickly

set -e

echo "=================================="
echo "   NetStacks Quick Start"
echo "=================================="
echo ""

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and configure your settings:"
    echo "   - NETBOX_TOKEN"
    echo "   - NETPALM_API_URL (if different)"
    echo "   - Other credentials as needed"
    echo ""
    read -p "Press Enter after you've edited .env, or Ctrl+C to exit..."
fi

echo "✅ Environment file exists"

# Check if netpalm-network exists
if ! docker network ls | grep -q netpalm-network; then
    echo "⚠️  Docker network 'netpalm-network' not found"
    read -p "Do you want to create it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker network create netpalm-network
        echo "✅ Created netpalm-network"
    else
        echo "⚠️  Warning: NetStacks may not be able to connect to Netpalm without this network"
    fi
else
    echo "✅ Docker network 'netpalm-network' exists"
fi

# Build and start NetStacks
echo ""
echo "🚀 Building and starting NetStacks..."
docker-compose up -d --build

# Wait for container to start
echo "⏳ Waiting for NetStacks to start..."
sleep 5

# Check if container is running
if docker ps | grep -q netstacks; then
    echo ""
    echo "=================================="
    echo "   ✅ NetStacks is running!"
    echo "=================================="
    echo ""
    echo "📊 Access NetStacks at: http://localhost:8088"
    echo ""
    echo "📝 Useful commands:"
    echo "   docker logs -f netstacks        # View logs"
    echo "   docker-compose down             # Stop NetStacks"
    echo "   docker-compose restart          # Restart NetStacks"
    echo ""
    echo "📚 Documentation:"
    echo "   README.md                       # Full documentation"
    echo "   DEPLOYMENT_GUIDE.md             # Deployment options"
    echo ""
else
    echo ""
    echo "❌ Error: NetStacks container failed to start"
    echo "Check logs with: docker logs netstacks"
    exit 1
fi
