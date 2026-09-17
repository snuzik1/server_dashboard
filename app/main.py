from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

try:
    import docker
    from docker.errors import DockerException
except ImportError:  # pragma: no cover
    docker = None
    DockerException = Exception


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Mini Server Dashboard")
boot_time = psutil.boot_time()


def format_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def docker_containers():
    if docker is None:
        return {"available": False, "containers": []}

    try:
        client = docker.from_env()
        containers = []
        for c in client.containers.list(all=True):
            containers.append({
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
            })
        client.close()
        return {"available": True, "containers": containers}
    except DockerException:
        return {"available": False, "containers": []}
    except Exception:
        return {"available": False, "containers": []}


def metrics():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)

    return {
        "hostname": socket.gethostname(),
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "cpu_count": psutil.cpu_count(logical=True) or 0,
        "memory_percent": memory.percent,
        "memory_used_gb": round(memory.used / (1024**3), 2),
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "load_15m": round(load[2], 2),
        "uptime": format_uptime(time.time() - boot_time),
        "boot_time": int(boot_time),
        "docker": docker_containers(),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"hostname": socket.gethostname()},
    )


@app.get("/api/metrics")
async def api_metrics():
    return metrics()


@app.get("/health")
async def health():
    return {"status": "ok"}
