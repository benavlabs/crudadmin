#!/bin/bash
#
# CRUDAdmin Service Deployment Script
# Deploys a CRUDAdmin application as a systemd service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  CRUDAdmin Service Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run this script with sudo or as root${NC}"
    exit 1
fi

# Get the actual user if running with sudo
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    read -p "Enter the user to run the service as: " ACTUAL_USER
fi

# Get app directory
read -p "Enter the full path to your application directory: " APP_DIR

if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}Error: Directory '$APP_DIR' does not exist${NC}"
    exit 1
fi

if [ ! -f "$APP_DIR/main.py" ]; then
    echo -e "${RED}Error: main.py not found in '$APP_DIR'${NC}"
    exit 1
fi

if [ ! -d "$APP_DIR/venv" ]; then
    echo -e "${RED}Error: Virtual environment not found in '$APP_DIR/venv'${NC}"
    exit 1
fi

# Get service name
DEFAULT_SERVICE_NAME=$(basename "$APP_DIR")
read -p "Enter service name [${DEFAULT_SERVICE_NAME}]: " SERVICE_NAME
SERVICE_NAME=${SERVICE_NAME:-$DEFAULT_SERVICE_NAME}

# Get host and port
read -p "Enter host to bind to [0.0.0.0]: " HOST
HOST=${HOST:-0.0.0.0}

read -p "Enter port to listen on [8000]: " PORT
PORT=${PORT:-8000}

# Get number of workers
read -p "Enter number of workers [1]: " WORKERS
WORKERS=${WORKERS:-1}

echo
echo -e "${YELLOW}Configuration:${NC}"
echo "  Service Name: ${SERVICE_NAME}"
echo "  App Directory: ${APP_DIR}"
echo "  User: ${ACTUAL_USER}"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  Workers: ${WORKERS}"
echo

read -p "Continue with deployment? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Create systemd service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${YELLOW}Creating systemd service...${NC}"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=${SERVICE_NAME} CRUDAdmin Service
After=network.target

[Service]
Type=simple
User=${ACTUAL_USER}
Group=${ACTUAL_USER}
WorkingDirectory=${APP_DIR}

# Environment
Environment="PATH=${APP_DIR}/venv/bin"
EnvironmentFile=-${APP_DIR}/.env

# Start command
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host ${HOST} --port ${PORT} --workers ${WORKERS}

# Restart configuration
Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}Service file created: ${SERVICE_FILE}${NC}"

# Set correct ownership of app directory
echo -e "${YELLOW}Setting directory permissions...${NC}"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "$APP_DIR"

# Reload systemd
echo -e "${YELLOW}Reloading systemd...${NC}"
systemctl daemon-reload

# Enable and start the service
echo -e "${YELLOW}Enabling service...${NC}"
systemctl enable "${SERVICE_NAME}"

echo -e "${YELLOW}Starting service...${NC}"
systemctl start "${SERVICE_NAME}"

# Wait a moment for the service to start
sleep 2

# Check service status
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Deployment Successful!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo
    echo -e "Service ${BLUE}${SERVICE_NAME}${NC} is running."
    echo
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "  Status:   sudo systemctl status ${SERVICE_NAME}"
    echo "  Logs:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  Stop:     sudo systemctl stop ${SERVICE_NAME}"
    echo "  Start:    sudo systemctl start ${SERVICE_NAME}"
    echo "  Restart:  sudo systemctl restart ${SERVICE_NAME}"
    echo "  Disable:  sudo systemctl disable ${SERVICE_NAME}"
    echo
    echo -e "${YELLOW}Application URL:${NC}"
    echo "  http://${HOST}:${PORT}"
    echo "  Admin Panel: http://${HOST}:${PORT}/admin"
    echo
else
    echo -e "${RED}Service failed to start. Check logs:${NC}"
    echo "  sudo journalctl -u ${SERVICE_NAME} -n 50"
    systemctl status "${SERVICE_NAME}" --no-pager || true
    exit 1
fi

# Optional: Configure firewall
echo
read -p "Open port ${PORT} in firewall? [y/N]: " OPEN_FIREWALL
if [[ "$OPEN_FIREWALL" =~ ^[Yy]$ ]]; then
    if command -v ufw &> /dev/null; then
        ufw allow "${PORT}/tcp"
        echo -e "${GREEN}UFW rule added for port ${PORT}${NC}"
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port="${PORT}/tcp"
        firewall-cmd --reload
        echo -e "${GREEN}Firewalld rule added for port ${PORT}${NC}"
    else
        echo -e "${YELLOW}No supported firewall found. Please configure manually.${NC}"
    fi
fi

# Optional: Setup nginx reverse proxy
echo
read -p "Setup nginx reverse proxy? [y/N]: " SETUP_NGINX
if [[ "$SETUP_NGINX" =~ ^[Yy]$ ]]; then
    if ! command -v nginx &> /dev/null; then
        echo -e "${YELLOW}Installing nginx...${NC}"
        if command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y nginx
        elif command -v dnf &> /dev/null; then
            dnf install -y nginx
        elif command -v yum &> /dev/null; then
            yum install -y nginx
        else
            echo -e "${RED}Could not install nginx automatically${NC}"
        fi
    fi

    if command -v nginx &> /dev/null; then
        read -p "Enter domain name (e.g., app.example.com): " DOMAIN_NAME

        NGINX_CONF="/etc/nginx/sites-available/${SERVICE_NAME}"
        cat > "$NGINX_CONF" << EOF
server {
    listen 80;
    server_name ${DOMAIN_NAME};

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

        # Enable site
        if [ -d /etc/nginx/sites-enabled ]; then
            ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
        fi

        # Test and reload nginx
        nginx -t && systemctl reload nginx
        echo -e "${GREEN}Nginx configured for ${DOMAIN_NAME}${NC}"
        echo
        echo -e "${YELLOW}For HTTPS, run:${NC}"
        echo "  sudo certbot --nginx -d ${DOMAIN_NAME}"
    fi
fi

echo
echo -e "${GREEN}Deployment complete!${NC}"
