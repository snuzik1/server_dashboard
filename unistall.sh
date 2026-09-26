#!/bin/sh
set -e

echo "Starting Server Dashboard Uninstallation..."

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root."
    exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
    echo "Stopping and disabling systemd service..."
    systemctl stop server-dashboard.service 2>/dev/null || true
    systemctl disable server-dashboard.service 2>/dev/null || true
    rm -f /etc/systemd/system/server-dashboard.service
    systemctl daemon-reload
fi

echo "Removing application files..."
rm -rf /opt/server-dashboard

echo "Note: /etc/server-dashboard.env is kept to preserve your configurations."
echo "Note: Dependencies (Python, Docker, Podman, Git) were NOT touched."
echo "Uninstallation complete."