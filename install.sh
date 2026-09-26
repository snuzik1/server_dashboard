#!/bin/sh
set -e

echo "Starting Server Dashboard Installation..."

# 1. Check root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root."
    exit 1
fi

# 2. Check and Find Python 3
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    if python --version 2>&1 | grep -q "Python 3"; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "Python 3 not found. Attempting to install..."
    if command -v dnf >/dev/null 2>&1; then dnf install -y python3
    elif command -v apt-get >/dev/null 2>&1; then apt-get update && apt-get install -y python3
    elif command -v yum >/dev/null 2>&1; then yum install -y python3
    elif command -v zypper >/dev/null 2>&1; then zypper install -y python3
    elif command -v apk >/dev/null 2>&1; then apk add python3
    else
        echo "Error: Cannot detect package manager to install Python 3. Please install manually."
        exit 1
    fi
    PYTHON_CMD="python3"
fi

# 3. Check Python version (>= 3.8)
$PYTHON_CMD -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' || {
    echo "Error: Python 3.8+ is required."
    exit 1
}

# 4. Check Port 8000 availability
if command -v ss >/dev/null 2>&1; then
    if ss -tuln | grep -q ":8000 "; then
        echo "Warning: Port 8000 is already in use."
        echo "Please configure a different port in /etc/server-dashboard.env (e.g. DASHBOARD_PORT=8080)"
    fi
fi

# 5. Setup directories and copy files
INSTALL_DIR="/opt/server-dashboard"
mkdir -p "$INSTALL_DIR"
cp server_dashboard.py "$INSTALL_DIR/"
cp -r library "$INSTALL_DIR/" 2>/dev/null || true
chmod +x "$INSTALL_DIR/server_dashboard.py"

ENV_FILE="/etc/server-dashboard.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating default configuration at $ENV_FILE"
    cat <<EOF > "$ENV_FILE"
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000
CONFIG_CACHE=/opt/server-dashboard/library
# CONFIG_REPO=https://github.com/user/server-config-library.git
# CONFIG_BRANCH=main
EOF
fi

# 6. Systemd setup
if command -v systemctl >/dev/null 2>&1; then
    echo "Systemd detected. Configuring service..."
    cat <<EOF > /etc/systemd/system/server-dashboard.service
[Unit]
Description=Server Dashboard
After=network.target

[Service]
Type=simple
User=root
ExecStart=$(command -v $PYTHON_CMD) $INSTALL_DIR/server_dashboard.py
Restart=always
RestartSec=5
EnvironmentFile=-/etc/server-dashboard.env

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now server-dashboard.service
    
    if systemctl is-active --quiet server-dashboard.service; then
        echo "Service is running successfully."
    else
        echo "Warning: Service failed to start. Check 'journalctl -u server-dashboard'."
    fi
else
    echo "Systemd not found. Skipping service creation."
    echo "Run manually: $PYTHON_CMD $INSTALL_DIR/server_dashboard.py"
fi

echo "Installation complete!"
echo "Dashboard URL: http://127.0.0.1:8000"
echo "Health check: curl http://127.0.0.1:8000/health"