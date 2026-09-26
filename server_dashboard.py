#!/usr/bin/env python3
import os
import sys
import json
import socket
import logging
import subprocess
import shutil
import zipfile
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# --- CONFIGURATION ---
CONFIG_FILE = "/etc/server-dashboard.env"

def load_config():
    config = {
        "DASHBOARD_HOST": "0.0.0.0",
        "DASHBOARD_PORT": 8000,
        "CONFIG_REPO": "",
        "CONFIG_BRANCH": "main",
        "CONFIG_CACHE": os.path.abspath(os.path.join(os.path.dirname(__file__), "library"))
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip()
    return config

CONFIG = load_config()
HOST = CONFIG["DASHBOARD_HOST"]
PORT = int(CONFIG.get("DASHBOARD_PORT", 8000))
LIBRARY_PATH = CONFIG["CONFIG_CACHE"]

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Dashboard")

# --- FRONTEND (HTML/CSS/JS) ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Server Dashboard</title>
    <style>
        :root { --bg: #1e1e2e; --surface: #282a36; --text: #f8f8f2; --primary: #bd93f9; --success: #50fa7b; --danger: #ff5555; }
        body { font-family: system-ui, -apple-system, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1, h2 { color: var(--primary); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background-color: var(--surface); padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .stat-row { display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid #444; padding-bottom: 5px; }
        .stat-row:last-child { border-bottom: none; }
        .btn { background: var(--primary); color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block;}
        .btn:hover { opacity: 0.9; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #444; }
        .badge { padding: 4px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .badge.running { background: var(--success); color: #000; }
        .badge.exited { background: var(--danger); color: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Server Dashboard</h1>
        
        <div class="grid">
            <div class="card">
                <h2>System Overview</h2>
                <div id="sys-overview">Loading...</div>
            </div>
            <div class="card">
                <h2>Resources</h2>
                <div id="sys-resources">Loading...</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Docker</h2>
                <div id="docker-status">Loading...</div>
            </div>
            <div class="card">
                <h2>Podman</h2>
                <div id="podman-status">Loading...</div>
            </div>
        </div>

        <div class="card">
            <h2>Configuration Library <button class="btn" onclick="syncLibrary()" style="float:right; font-size: 0.8em;">Sync Git</button></h2>
            <div id="library-list">Loading...</div>
        </div>
    </div>

    <script>
        async function fetchMetrics() {
            try {
                const res = await fetch('/api/metrics');
                const data = await res.json();
                
                document.getElementById('sys-overview').innerHTML = `
                    <div class="stat-row"><span>Hostname</span><span>${data.hostname}</span></div>
                    <div class="stat-row"><span>OS</span><span>${data.os}</span></div>
                    <div class="stat-row"><span>Kernel</span><span>${data.kernel}</span></div>
                    <div class="stat-row"><span>Uptime</span><span>${data.uptime}</span></div>
                    <div class="stat-row"><span>IPs</span><span>${data.ips.join(', ')}</span></div>
                `;
                
                document.getElementById('sys-resources').innerHTML = `
                    <div class="stat-row"><span>CPU Cores</span><span>${data.cpu_cores}</span></div>
                    <div class="stat-row"><span>Load Avg</span><span>${data.load_avg}</span></div>
                    <div class="stat-row"><span>RAM</span><span>${data.ram.used} / ${data.ram.total} (${data.ram.percent}%)</span></div>
                    <div class="stat-row"><span>Disk (/)</span><span>${data.disk.used} / ${data.disk.total} (${data.disk.percent}%)</span></div>
                `;

                const renderContainers = (cData) => {
                    if (cData.installed === false) return '<p>Not installed</p>';
                    if (cData.containers.length === 0) return '<p>No containers</p>';
                    let html = '<table><tr><th>Name</th><th>Status</th><th>Image</th></tr>';
                    cData.containers.forEach(c => {
                        const statusClass = c.status.toLowerCase().includes('up') ? 'running' : 'exited';
                        html += `<tr><td>${c.name}</td><td><span class="badge ${statusClass}">${c.status}</span></td><td>${c.image}</td></tr>`;
                    });
                    html += '</table>';
                    return html;
                };

                document.getElementById('docker-status').innerHTML = renderContainers(data.docker);
                document.getElementById('podman-status').innerHTML = renderContainers(data.podman);

            } catch (err) { console.error('Metrics fetch error:', err); }
        }

        async function fetchLibrary() {
            try {
                const res = await fetch('/api/library');
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                
                let html = '<table><tr><th>Name</th><th>Type</th><th>Desc</th><th>Action</th></tr>';
                data.items.forEach(item => {
                    html += `<tr>
                        <td>${item.name} <br><small>${item.tags.join(', ')}</small></td>
                        <td>${item.type}</td>
                        <td>${item.description}</td>
                        <td><a href="/api/library/${item.id}/download" class="btn">Download ZIP</a></td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('library-list').innerHTML = html;
            } catch (err) { 
                document.getElementById('library-list').innerHTML = `<p style="color:var(--danger)">Error loading library: ${err.message}</p>`; 
            }
        }

        async function syncLibrary() {
            if (!confirm('Sync library from Git?')) return;
            try {
                const res = await fetch('/api/library/sync', { method: 'POST' });
                const data = await res.json();
                alert(data.message || data.error);
                fetchLibrary();
            } catch(e) { alert('Sync error'); }
        }

        fetchMetrics();
        fetchLibrary();
        setInterval(fetchMetrics, 5000);
    </script>
</body>
</html>
"""

# --- SYSTEM METRICS FUNCTIONS ---
def get_sys_info():
    try:
        with open("/etc/os-release") as f:
            os_info = {line.split("=")[0]: line.split("=")[1].strip().strip('"') for line in f if "=" in line}
            os_name = os_info.get("PRETTY_NAME", "Unknown Linux")
    except:
        os_name = "Unknown Linux"

    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
            uptime = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"
    except:
        uptime = "N/A"

    try:
        with open("/proc/loadavg", "r") as f:
            load_avg = " ".join(f.readline().split()[:3])
    except:
        load_avg = "N/A"

    ips = []
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show"], text=True)
        for line in out.splitlines():
            if "inet " in line and "127.0.0.1" not in line:
                ips.append(line.split()[1].split("/")[0])
    except:
        pass

    ram = {"total": "0", "used": "0", "percent": "0"}
    try:
        with open("/proc/meminfo", "r") as f:
            mem = {}
            for line in f:
                parts = line.split()
                mem[parts[0].strip(":")] = int(parts[1])
            total = mem.get("MemTotal", 1)
            free = mem.get("MemAvailable", mem.get("MemFree", 0))
            used = total - free
            ram = {
                "total": f"{total // 1024} MB",
                "used": f"{used // 1024} MB",
                "percent": str(int((used / total) * 100))
            }
    except:
        pass

    disk_info = {"total": "0", "used": "0", "percent": "0"}
    try:
        du = shutil.disk_usage("/")
        disk_info = {
            "total": f"{du.total // (1024**3)} GB",
            "used": f"{du.used // (1024**3)} GB",
            "percent": str(int((du.used / du.total) * 100))
        }
    except:
        pass

    return {
        "hostname": socket.gethostname(),
        "os": os_name,
        "kernel": os.uname().release,
        "uptime": uptime,
        "cpu_cores": os.cpu_count(),
        "load_avg": load_avg,
        "ips": ips or ["N/A"],
        "ram": ram,
        "disk": disk_info
    }

def get_containers(cmd_base):
    if not shutil.which(cmd_base):
        return {"installed": False, "containers": []}
    
    try:
        out = subprocess.check_output([cmd_base, "ps", "-a", "--format", '{{.Names}}|{{.Status}}|{{.Image}}'], text=True)
        containers = []
        for line in out.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 3:
                    containers.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        return {"installed": True, "containers": containers}
    except subprocess.SubprocessError:
        return {"installed": True, "containers": []}

# --- SERVER ---
class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def do_GET(self):
        parsed_path = urlparse(self.path).path

        if parsed_path == "/":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
            
        elif parsed_path == "/health":
            self.send_json({"status": "ok"})

        elif parsed_path == "/api/metrics":
            try:
                metrics = get_sys_info()
                metrics["docker"] = get_containers("docker")
                metrics["podman"] = get_containers("podman")
                self.send_json(metrics)
            except Exception as e:
                logger.error(f"Metrics error: {e}")
                self.send_error_json("Internal Server Error", 500)

        elif parsed_path == "/api/library":
            cat_path = os.path.join(LIBRARY_PATH, "catalog.json")
            if not os.path.exists(cat_path):
                return self.send_json({"version": 1, "items": []})
            try:
                with open(cat_path, "r") as f:
                    self.send_json(json.load(f))
            except json.JSONDecodeError:
                self.send_error_json("catalog.json is corrupted", 500)
            except Exception:
                self.send_error_json("Cannot read library", 500)

        elif parsed_path.startswith("/api/library/") and parsed_path.endswith("/download"):
            item_id = parsed_path.split("/")[3]
            cat_path = os.path.join(LIBRARY_PATH, "catalog.json")
            
            if not os.path.exists(cat_path):
                return self.send_error_json("Library not found", 404)
                
            try:
                with open(cat_path, "r") as f:
                    catalog = json.load(f)
                
                item = next((i for i in catalog.get("items", []) if i.get("id") == item_id), None)
                if not item:
                    return self.send_error_json("Configuration not found", 404)

                target_dir = os.path.abspath(os.path.join(LIBRARY_PATH, item.get("path", "")))
                
                # SECURITY: Path Traversal Prevention
                if not target_dir.startswith(os.path.abspath(LIBRARY_PATH)):
                    return self.send_error_json("Access denied", 403)
                    
                if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
                    return self.send_error_json("Files not found on disk", 404)

                # Generate ZIP in memory
                memory_file = io.BytesIO()
                with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(target_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, target_dir)
                            zf.write(file_path, arcname)

                memory_file.seek(0)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{item_id}.zip"')
                self.end_headers()
                self.wfile.write(memory_file.read())

            except Exception as e:
                logger.error(f"Download error: {e}")
                self.send_error_json("Failed to create ZIP", 500)
        else:
            self.send_error_json("Not Found", 404)

    def do_POST(self):
        parsed_path = urlparse(self.path).path
        
        if parsed_path == "/api/library/sync":
            repo = CONFIG.get("CONFIG_REPO")
            branch = CONFIG.get("CONFIG_BRANCH", "main")
            
            if not repo:
                return self.send_error_json("Git repository not configured", 400)
            if not shutil.which("git"):
                return self.send_error_json("Git is not installed on the server", 500)
                
            try:
                if os.path.exists(os.path.join(LIBRARY_PATH, ".git")):
                    subprocess.run(["git", "-C", LIBRARY_PATH, "pull", "origin", branch], check=True, capture_output=True)
                    self.send_json({"message": "Library updated successfully"})
                else:
                    if os.path.exists(LIBRARY_PATH):
                        shutil.rmtree(LIBRARY_PATH)
                    subprocess.run(["git", "clone", "-b", branch, repo, LIBRARY_PATH], check=True, capture_output=True)
                    self.send_json({"message": "Library cloned successfully"})
            except subprocess.CalledProcessError as e:
                logger.error(f"Git error: {e.stderr.decode()}")
                self.send_error_json("Git sync failed. See logs for details", 500)
        else:
            self.send_error_json("Not Found", 404)

if __name__ == "__main__":
    if not os.path.exists(LIBRARY_PATH):
        try:
            os.makedirs(LIBRARY_PATH, exist_ok=True)
        except:
            pass

    server = HTTPServer((HOST, PORT), DashboardHandler)
    logger.info(f"Starting dashboard on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping dashboard...")
        server.server_close()