#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/mini-server-dashboard"
SERVICE="/etc/systemd/system/mini-server-dashboard.service"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip

mkdir -p "$APP_DIR"
cp -r app "$APP_DIR/"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/app/requirements.txt"

cat > "$SERVICE" <<EOF
[Unit]
Description=Mini Server Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/app
ExecStart=$APP_DIR/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mini-server-dashboard

echo
echo "Installed."
echo "Open locally: http://127.0.0.1:8000"
echo "Status: systemctl status mini-server-dashboard"
