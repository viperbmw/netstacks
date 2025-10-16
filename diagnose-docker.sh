#!/bin/bash
# Comprehensive Docker Compose diagnosis

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}=== Docker Compose Diagnostic Tool ===${NC}"
echo ""

# 1. Check Docker installation
echo -e "${YELLOW}1. Docker Installation:${NC}"
which docker
docker --version
docker info --format '{{.ServerVersion}}' 2>&1 || echo -e "${RED}Docker daemon not accessible${NC}"
echo ""

# 2. Check Docker plugin paths
echo -e "${YELLOW}2. Docker CLI Plugin Paths:${NC}"
docker info --format '{{.ClientInfo.Plugins}}' 2>/dev/null || echo "Cannot get plugin info"
echo ""

# 3. Search for compose binary
echo -e "${YELLOW}3. Searching for compose binaries:${NC}"
echo "System-wide search (may take a moment)..."
sudo find / -name "docker-compose" -type f 2>/dev/null | grep -v snap
echo ""

# 4. Check specific locations
echo -e "${YELLOW}4. Checking known plugin locations:${NC}"
for dir in \
    /usr/libexec/docker/cli-plugins \
    /usr/lib/docker/cli-plugins \
    /usr/local/libexec/docker/cli-plugins \
    /usr/local/lib/docker/cli-plugins \
    ~/.docker/cli-plugins; do
    echo -e "${BLUE}$dir:${NC}"
    if [ -d "$dir" ]; then
        ls -lah "$dir/" 2>/dev/null || echo "  (empty or no permission)"
    else
        echo "  (does not exist)"
    fi
done
echo ""

# 5. Check Docker config
echo -e "${YELLOW}5. Docker Configuration:${NC}"
if [ -f ~/.docker/config.json ]; then
    echo "User config exists: ~/.docker/config.json"
    cat ~/.docker/config.json 2>/dev/null | head -20
else
    echo "No user Docker config"
fi
echo ""

# 6. Check environment
echo -e "${YELLOW}6. Environment Variables:${NC}"
env | grep -i docker || echo "No Docker env vars"
echo ""

# 7. Test different compose commands
echo -e "${YELLOW}7. Testing compose commands:${NC}"
echo -n "docker compose: "
docker compose version 2>&1 | head -1 || echo -e "${RED}FAILED${NC}"

echo -n "docker-compose: "
docker-compose --version 2>&1 | head -1 || echo -e "${RED}FAILED${NC}"

if [ -f /usr/libexec/docker/cli-plugins/docker-compose ]; then
    echo -n "Direct execution: "
    /usr/libexec/docker/cli-plugins/docker-compose version 2>&1 | head -1
fi
echo ""

# 8. Check Docker installation method
echo -e "${YELLOW}8. Docker Installation Method:${NC}"
if command -v snap &>/dev/null && snap list 2>/dev/null | grep -q docker; then
    echo -e "${YELLOW}Docker installed via SNAP${NC}"
    echo "This is the issue! Snap Docker has different plugin paths."
    echo ""
    echo -e "${GREEN}SOLUTION: Install Docker from official repository instead of snap${NC}"
elif dpkg -l | grep -q docker-ce; then
    echo "Docker installed via APT (official repository)"
elif which docker | grep -q snap; then
    echo -e "${YELLOW}Docker running from snap${NC}"
else
    echo "Installation method unclear"
fi
echo ""

# 9. Recommendations
echo -e "${BLUE}=== Recommendations ===${NC}"

if which docker | grep -q snap; then
    cat << 'SNAPFIX'
ISSUE FOUND: Docker is installed via Snap

Snap Docker has issues with the compose plugin. Here's how to fix it:

Option A: Use standalone docker-compose (quick fix)
  sudo curl -SL "https://github.com/docker/compose/releases/download/v2.40.0/docker-compose-linux-$(uname -m)" \
    -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  docker-compose version

Option B: Reinstall Docker from official repo (recommended)
  # Remove snap Docker
  sudo snap remove docker
  
  # Install from official Docker repo
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  
  # Add your user to docker group
  sudo usermod -aG docker $USER
  
  # Install compose plugin
  sudo apt-get install -y docker-compose-plugin
  
  # Logout and login, then test
  docker compose version

SNAPFIX
else
    echo "Checking if compose plugin executable exists..."
    if [ -f /usr/libexec/docker/cli-plugins/docker-compose ]; then
        if [ -x /usr/libexec/docker/cli-plugins/docker-compose ]; then
            echo -e "${RED}Plugin exists and is executable but Docker can't find it${NC}"
            echo "This might be a Docker CLI version mismatch or PATH issue"
            echo ""
            echo "Try: sudo apt-get update && sudo apt-get install --reinstall docker-ce docker-ce-cli"
        else
            echo "Plugin exists but is not executable"
            echo "Run: sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose"
        fi
    else
        echo "Plugin binary not found in expected location"
    fi
fi
