#!/bin/bash
# Install Docker Compose v2 on Ubuntu
# This script installs the latest Docker Compose v2 plugin

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Docker Compose v2 Installation Script${NC}"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}Error: This script is for Linux systems only${NC}"
    exit 1
fi

# Check current Docker Compose version
echo -e "${YELLOW}Checking current Docker Compose version...${NC}"
if command -v docker-compose &> /dev/null; then
    CURRENT_VERSION=$(docker-compose --version 2>/dev/null || echo "Unknown")
    echo -e "Current: ${CURRENT_VERSION}"
fi

if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    CURRENT_V2=$(docker compose version 2>/dev/null || echo "Unknown")
    echo -e "Current v2: ${CURRENT_V2}"
fi

echo ""
echo -e "${YELLOW}Installing Docker Compose v2...${NC}"

# Update package index
echo -e "${YELLOW}Updating package index...${NC}"
sudo apt-get update

# Install Docker Compose v2 plugin
echo -e "${YELLOW}Installing docker-compose-plugin...${NC}"
sudo apt-get install -y docker-compose-plugin

# Verify installation
echo ""
echo -e "${GREEN}Verifying installation...${NC}"
if docker compose version &> /dev/null; then
    NEW_VERSION=$(docker compose version)
    echo -e "${GREEN}✓ Docker Compose v2 installed successfully!${NC}"
    echo -e "Version: ${NEW_VERSION}"
    echo ""
    echo -e "${GREEN}Usage:${NC}"
    echo -e "  Use: ${YELLOW}docker compose${NC} (with a space, NOT docker-compose)"
    echo -e "  Example: ${YELLOW}docker compose up -d${NC}"
else
    echo -e "${RED}✗ Installation failed${NC}"
    exit 1
fi

# Check if old docker-compose exists
if command -v docker-compose &> /dev/null; then
    echo ""
    echo -e "${YELLOW}Note: Old 'docker-compose' (v1) is still installed${NC}"
    echo -e "To remove it: ${YELLOW}sudo apt-get remove docker-compose${NC}"
    echo -e "Or keep both versions (recommended during transition)"
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
