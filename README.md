# Mini Server Dashboard

A tiny Linux server dashboard built with FastAPI + psutil.

## Features

- CPU usage
- RAM usage
- Disk usage for `/`
- Uptime
- Load average
- Docker container status (when Docker socket is accessible)
- JSON API at `/api/metrics`
- Health endpoint at `/health`
- Runs as a systemd service

## Requirements

- Linux
- Python 3.10+
- Optional: Docker

## Quick start

```bash
git clone <your-repo>
cd mini-server-dashboard

python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt

cd app
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Install as a systemd service

```bash
sudo ./install.sh
```

Then:

```bash
systemctl status mini-server-dashboard
journalctl -u mini-server-dashboard -f
```

## Remote access

Keep the app on `127.0.0.1` by default. For a VPS, put it behind Nginx/Caddy and HTTPS rather than exposing port 8000 directly.

## API

```bash
curl http://127.0.0.1:8000/api/metrics
curl http://127.0.0.1:8000/health
```

## Docker permissions

When running as a non-root service user, that user needs permission to access the Docker socket, commonly by being a member of the `docker` group. That group grants broad control over Docker on many Linux setups, so treat membership as privileged access.
