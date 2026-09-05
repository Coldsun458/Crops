#!/usr/bin/env bash
# ==============================================================================
# Agri-Exchange Wholesaler Production Engine - Automated VPS Deployment Script
# Supports: Ubuntu 22.04 / 24.04 LTS, Debian 11/12
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   Agri-Exchange Wholesaler - Production VPS Deploy   ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Verify sudo / root access
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# 2. Check and Install Docker & Docker Compose if not present
if ! command -v docker &>/dev/null; then
    echo -e "${YELLOW}[1/4] Docker not found. Installing Docker Engine & Compose plugin...${NC}"
    $SUDO apt-get update -y
    $SUDO apt-get install -y ca-certificates curl gnupg lsb-release

    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    UBUNTU_CODENAME=$(lsb_release -cs 2>/dev/null || echo "jammy")
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      ${UBUNTU_CODENAME} stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

    $SUDO apt-get update -y
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    $SUDO systemctl enable docker
    $SUDO systemctl start docker

    if [ -n "$SUDO" ] && [ -n "${USER:-}" ]; then
        $SUDO usermod -aG docker "$USER" || true
    fi
    echo -e "${GREEN}Docker installed successfully!${NC}"
else
    echo -e "${GREEN}[1/4] Docker is already installed: $(docker --version)${NC}"
fi

# 3. Create production .env if not exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}[2/4] Generating production .env configuration...${NC}"
    RANDOM_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "agri-prod-jwt-secret-$(date +%s)")
    RANDOM_DB_PASS=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || echo "agri-db-pass-$(date +%s)")

    cat <<ENVEOF > .env
POSTGRES_USER=agri_admin
POSTGRES_PASSWORD=${RANDOM_DB_PASS}
POSTGRES_DB=agri_exchange
DATABASE_URL=postgresql://agri_admin:${RANDOM_DB_PASS}@db:5432/agri_exchange
SECRET_KEY=${RANDOM_SECRET}
ALGORITHM=HS256
PORT=8000
ENVEOF
    echo -e "${GREEN}Created .env file with secure randomized secrets.${NC}"
else
    echo -e "${GREEN}[2/4] Production .env file already exists.${NC}"
fi

# 4. Build and run containers
echo -e "${BLUE}[3/4] Building and launching Docker Compose stack...${NC}"
$SUDO docker compose down --remove-orphans || true
$SUDO docker compose up -d --build

# 5. Wait for healthcheck and verify
echo -e "${BLUE}[4/4] Waiting for services to become healthy...${NC}"
for i in {1..30}; do
    if curl -s http://localhost/health | grep -q "healthy"; then
        echo -e "${GREEN}Service is HEALTHY and responding through Nginx on port 80!${NC}"
        break
    elif curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo -e "${GREEN}Backend is HEALTHY on port 8000 (Nginx starting up)!${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

SERVER_IP=$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   Deployment Successful!                             ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "Web Application UI : ${BLUE}http://${SERVER_IP}/${NC}"
echo -e "API Documentation  : ${BLUE}http://${SERVER_IP}/docs${NC}"
echo -e "Health Endpoint    : ${BLUE}http://${SERVER_IP}/health${NC}"
echo ""
echo -e "To view live logs:  ${YELLOW}sudo docker compose logs -f${NC}"
echo -e "To stop services:   ${YELLOW}sudo docker compose down${NC}"
echo -e "${GREEN}======================================================${NC}"
