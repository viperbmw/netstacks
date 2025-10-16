#!/bin/bash
# Fix Docker Compose v2 detection issue

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Diagnosing Docker Compose issue...${NC}"
echo ""

# Check Docker version
echo -e "${YELLOW}Docker version:${NC}"
docker --version || echo -e "${RED}Docker not found${NC}"
echo ""

# Check where compose plugin is installed
echo -e "${YELLOW}Looking for compose plugin:${NC}"
find /usr/lib* -name "*compose*" 2>/dev/null | grep -i docker || echo "Not found in /usr/lib"
find /usr/local/lib* -name "*compose*" 2>/dev/null | grep -i docker || echo "Not found in /usr/local/lib"
echo ""

# Check Docker CLI plugins directory
echo -e "${YELLOW}Checking Docker CLI plugins:${NC}"
ls -la /usr/libexec/docker/cli-plugins/ 2>/dev/null || echo "Directory not found"
ls -la ~/.docker/cli-plugins/ 2>/dev/null || echo "User plugins directory not found"
echo ""

# Check if compose plugin package is installed
echo -e "${YELLOW}Checking installed packages:${NC}"
dpkg -l | grep compose || echo "No compose packages found"
echo ""

echo -e "${YELLOW}Attempting fixes...${NC}"
echo ""

# Fix 1: Create symlink if plugin exists but not in right location
if [ -f /usr/lib/docker/cli-plugins/docker-compose ]; then
    echo -e "${GREEN}Found plugin at /usr/lib/docker/cli-plugins/docker-compose${NC}"
    if [ ! -d /usr/libexec/docker/cli-plugins ]; then
        echo -e "${YELLOW}Creating /usr/libexec/docker/cli-plugins directory${NC}"
        sudo mkdir -p /usr/libexec/docker/cli-plugins
    fi
    echo -e "${YELLOW}Creating symlink${NC}"
    sudo ln -sf /usr/lib/docker/cli-plugins/docker-compose /usr/libexec/docker/cli-plugins/docker-compose
fi

# Fix 2: Reinstall plugin
echo -e "${YELLOW}Reinstalling docker-compose-plugin...${NC}"
sudo apt-get remove -y docker-compose-plugin 2>/dev/null || true
sudo apt-get install -y docker-compose-plugin

echo ""
echo -e "${YELLOW}Testing docker compose...${NC}"
if docker compose version &>/dev/null; then
    echo -e "${GREEN}✓ docker compose is now working!${NC}"
    docker compose version
else
    echo -e "${RED}Still not working. Trying alternative installation...${NC}"
    
    # Alternative: Download compose binary directly
    echo -e "${YELLOW}Downloading latest Docker Compose binary...${NC}"
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    echo -e "Latest version: ${COMPOSE_VERSION}"
    
    sudo mkdir -p /usr/libexec/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
        -o /usr/libexec/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    
    echo ""
    if docker compose version &>/dev/null; then
        echo -e "${GREEN}✓ docker compose installed successfully!${NC}"
        docker compose version
    else
        echo -e "${RED}Installation failed. Manual intervention required.${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
