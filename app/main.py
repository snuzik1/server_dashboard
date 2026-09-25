import io, json, os, shutil, socket, subprocess, time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI(title="Server Dashboard")
BASE = Path(__file__).parent
LOCAL_LIB = BASE / "library"
LIB_REPO = os.getenv("LIBRARY_REPO", "").strip()
LIB_REF = os.getenv("LIBRARY_REF", "main")
LIB_DIR = Path(os.getenv("LIBRARY_CACHE_DIR", "/var/cache/mini-server-dashboard/library"))
MAX_MB = int(os.getenv("LIBRARY_MAX_DOWNLOAD_MB", "25"))
BOOT = psutil.boot_time()


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()


def containers(runtime):
    if not shutil.which(runtime):
        return []
    try:
        lines = run(runtime, "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}").splitlines()
        return [
            {
                "name": p[0], "image": p[1],
                "status": "running" if p[2].lower().startswith("up") else "stopped",
                "runtime": runtime
            }
            for x in lines if len(p := x.split("\t", 2)) == 3
        ]
    except Exception:
        return []


def runtimes():
    return containers("docker"), containers("podman")


def uptime():
    s = int(time.time() - BOOT)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return " ".join(f"{n}{u}" for n, u in ((d, "d"), (h, "h"), (m, "m"), (s, "s")) if n or u == "s")


def metrics():
    mem, disk = psutil.virtual_memory(), psutil.disk_usage("/")
    docker, podman = runtimes()
    return {
        "hostname": socket.gethostname(),
        "cpu": round(psutil.cpu_percent(.1), 1),
        "cores": psutil.cpu_count() or 0,
        "memory": round(mem.percent, 1),
        "memory_used": round(mem.used / 1024**3, 1),
        "memory_total": round(mem.total / 1024**3, 1),
        "disk": round(disk.percent, 1),
        "disk_used": round(disk.used / 1024**3, 1),
        "disk_total": round(disk.total / 1024**3, 1),
        "load": [round(x, 2) for x in os.getloadavg()] if hasattr(os, "getloadavg") else [0, 0, 0],
        "uptime": uptime(),
        "containers": docker + podman,
        "docker": {"available": shutil.which("docker") is not None, "count": len(docker)},
        "podman": {"available": shutil.which("podman") is not None, "count": len(podman)},
    }


def library_root():
    return LIB_DIR if LIB_REPO else LOCAL_LIB


def sync():
    if not LIB_REPO:
        return
    LIB_DIR.parent.mkdir(parents=True, exist_ok=True)
    if (LIB_DIR / ".git").exists():
        run("git", "-C", str(LIB_DIR), "fetch", "--depth", "1", "origin", LIB_REF)
        run("git", "-C", str(LIB_DIR), "reset", "--hard", f"origin/{LIB_REF}")
    elif not LIB_DIR.exists():
        run("git", "clone", "--depth", "1", "--branch", LIB_REF, LIB_REPO, str(LIB_DIR))


def source():
    sync()
    commit = run("git", "-C", str(library_root()), "rev-parse", "--short", "HEAD") if (library_root() / ".git").exists() else None
    return {"type": "git" if LIB_REPO else "local", "repository": LIB_REPO or None, "ref": LIB_REF if LIB_REPO else None, "commit": commit}


def catalog():
    sync()
    p = library_root() / "catalog.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("items", [])


def item(cid):
    raw = next((x for x in catalog() if x.get("id") == cid), None)
    if not raw or not cid.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise HTTPException(404, "Configuration not found")
    root = library_root().resolve()
    folder = (root / raw.get("path", "")).resolve()
    try:
        folder.relative_to(root)
    except ValueError as e:
        raise HTTPException(400, "Invalid path") from e
    if not folder.is_dir():
        raise HTTPException(404, "Configuration directory not found")
    files = [{"path": str(p.relative_to(folder)), "size": p.stat().st_size} for p in folder.rglob("*") if p.is_file() and not p.is_symlink()]
    size = sum(x["size"] for x in files)
    return {**raw, "files": files, "size": size, "source": source()}


INDEX = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server Dashboard</title><style>
*{box-sizing:border-box}body{margin:0;background:#080b11;color:#edf1f7;font:14px system-ui,sans-serif}button,input{font:inherit}
a{color:#9db2ff}.app{display:grid;grid-template-columns:220px 1fr;min-height:100vh}.side{padding:20px 14px;border-right:1px solid #202838;background:#0a0e15}.brand{font-weight:800;font-size:15px;padding:8px}
nav{display:grid;gap:6px;margin-top:20px}.nav{padding:10px;border:1px solid transparent;background:none;color:#9aa6b9;text-align:left;border-radius:10px}.nav.active{background:#121a2a;color:#fff;border-color:#263555}
main{padding:32px;max-width:1200px;width:100%;margin:auto}.head{display:flex;justify-content:space-between;gap:20px;margin-bottom:24px}.head h1{margin:4px 0;font-size:38px}.muted{color:#8591a5}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:#10151f;border:1px solid #202a3a;border-radius:15px;padding:18px}.num{font-size:32px;font-weight:800;margin:8px 0}.bar{height:6px;background:#1d2635;border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:#8197ff;width:0}
.list{display:grid;gap:8px;margin-top:14px}.row{display:flex;justify-content:space-between;gap:12px;padding:12px;border:1px solid #202a3a;background:#0c1119;border-radius:10px}.tag{padding:4px 7px;border-radius:7px;background:#161f31;color:#aebeef;font-size:11px}.btn{border:1px solid #2a3750;background:#0c1119;color:#c7d0e0;padding:8px 11px;border-radius:9px;text-decoration:none}.primary{background:#627bf0;color:#fff}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.search{flex:1;min-width:220px;padding:10px 11px;border:1px solid #2a3548;background:#0b1018;color:#fff;border-radius:10px}.filter{padding:8px 10px;border:1px solid #29354a;background:#0b1018;color:#8e9aae;border-radius:9px}.filter.active{color:#fff;background:#16203a}.configs{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.config{display:flex;flex-direction:column;min-height:210px}.config h3{margin:12px 0 6px}.config p{color:#8b96a9;line-height:1.5}.actions{display:flex;gap:8px;margin-top:auto}.modal{position:fixed;inset:0;background:#000a;display:grid;place-items:center;padding:20px}.modal>div{position:relative;background:#0f151f;border:1px solid #29364b;border-radius:15px;padding:22px;width:min(700px,100%);max-height:85vh;overflow:auto}.close{position:absolute;right:10px;top:8px;border:0;background:none;color:#9ba7ba;font-size:24px}
@media(max-width:900px){.app{grid-template-columns:1fr}.side{border-right:0;border-bottom:1px solid #202838}.grid{grid-template-columns:repeat(2,1fr)}.configs{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){main{padding:20px}.grid,.configs{grid-template-columns:1fr}.head{flex-direction:column}}
</style></head><body><div class="app"><aside class="side"><div class="brand">SERVER DASHBOARD</div><nav>
<button class="nav active" data-v="overview">◉ Overview</button><button class="nav" data-v="containers">▣ Containers</button><button class="nav" data-v="library">◈ Configuration Library</button>
</nav></aside><main><header class="head"><div><div class="muted">LINUX SERVER</div><h1 id="title">Overview</h1><div id="host" class="muted">—</div></div><div>● Online</div></header>
<section id="overview"><div class="grid"><div class="card"><div class="muted">CPU</div><div class="num" id="cpu">—</div><div id="cores" class="muted">—</div><div class="bar"><i id="cpub"></i></div></div>
<div class="card"><div class="muted">MEMORY</div><div class="num" id="mem">—</div><div id="memd" class="muted">—</div><div class="bar"><i id="memb"></i></div></div>
<div class="card"><div class="muted">DISK /</div><div class="num" id="disk">—</div><div id="diskd" class="muted">—</div><div class="bar"><i id="diskb"></i></div></div>
<div class="card"><div class="muted">UPTIME</div><div class="num" id="up">—</div><div id="load" class="muted">—</div></div></div><div class="card" style="margin-top:12px"><div class="muted">RUNTIMES</div><div id="rt" class="list"></div></div></section>
<section id="containers" hidden><div class="card"><div class="muted">DOCKER / PODMAN</div><div id="ct" class="list"></div></div></section>
<section id="library" hidden><div class="card"><div class="muted">CONFIGURATION LIBRARY</div><p id="src" class="muted">—</p><div class="toolbar"><input id="q" class="search" placeholder="Search…"><button class="filter active" data-k="all">All</button><button class="filter" data-k="docker">Docker</button><button class="filter" data-k="podman">Podman</button><button class="filter" data-k="ansible">Ansible</button></div><div id="cfg" class="configs"></div></div></section>
<footer class="muted" style="margin-top:16px">Auto refresh 2s · <a href="/docs">API</a></footer></main></div>
<div id="modal" class="modal" hidden><div><button class="close" id="x">×</button><div id="mt" class="muted"></div><h2 id="mn">—</h2><p id="md" class="muted">—</p><div id="mf" class="list"></div><p><a id="dl" class="btn primary">Download ZIP</a></p></div></div>
<script>
const $=id=>document.getElementById(id),E=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])),L={docker:"Docker",podman:"Podman",ansible:"Ansible"};
let kind="all";
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>show(b.dataset.v));
function show(v){document.querySelectorAll("section").forEach(s=>s.hidden=true);$(v).hidden=false;document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b.dataset.v===v));$("title").textContent=v==="overview"?"Overview":v[0].toUpperCase()+v.slice(1);if(v==="library")load();}
async function refresh(){try{let d=await fetch("/api/metrics").then(r=>r.json());$("host").textContent=d.hostname;$("cpu").textContent=d.cpu+"%";$("cores").textContent=d.cores+" CPU cores";$("cpub").style.width=d.cpu+"%";$("mem").textContent=d.memory+"%";$("memd").textContent=d.memory_used+" / "+d.memory_total+" GB";$("memb").style.width=d.memory+"%";$("disk").textContent=d.disk+"%";$("diskd").textContent=d.disk_used+" / "+d.disk_total+" GB";$("diskb").style.width=d.disk+"%";$("up").textContent=d.uptime;$("load").textContent="Load "+d.load.join(" / ");$("rt").innerHTML=[["Docker",d.docker],["Podman",d.podman]].map(x=>"<div class=row><span>"+x[0]+"</span><b>"+(x[1].available?x[1].count:"—")+"</b></div>").join("");$("ct").innerHTML=d.containers.length?d.containers.map(c=>"<div class=row><div><b>"+E(c.name)+"</b><div class=muted>"+E(c.image)+"</div></div><span class=tag>"+E(c.runtime)+" · "+E(c.status)+"</span></div>").join(""):"<div class=muted>No containers</div>"}catch(e){}}
async function load(){let p=new URLSearchParams({kind,q:$("q").value});let d=await fetch("/api/library?"+p).then(r=>r.json());$("src").textContent=d.source.repository?d.source.repository+" · "+d.source.ref+" · "+(d.source.commit||"syncing"):"Local library · "+d.count+" item(s)";$("cfg").innerHTML=d.items.length?d.items.map(i=>"<article class='card config'><span class=tag>"+E(L[i.type]||i.type)+" · "+E(i.version||"")+"</span><h3>"+E(i.name)+"</h3><p>"+E(i.description||"")+"</p><div class=actions><button class=btn data-id='"+E(i.id)+"'>View</button><a class='btn primary' href='/api/library/"+encodeURIComponent(i.id)+"/download'>Download</a></div></article>").join(""):"<div class=muted>No configurations found</div>";document.querySelectorAll("[data-id]").forEach(b=>b.onclick=()=>open(b.dataset.id))}
async function open(id){let d=await fetch("/api/library/"+encodeURIComponent(id)).then(r=>r.json());$("mt").textContent=L[d.type]||d.type;$("mn").textContent=d.name;$("md").textContent=d.description||"";$("mf").innerHTML=d.files.map(f=>"<div class=row><span>"+E(f.path)+"</span><span class=muted>"+f.size+" B</span></div>").join("");$("dl").href="/api/library/"+encodeURIComponent(id)+"/download";$("modal").hidden=false}
$("x").onclick=()=>$("modal").hidden=true;document.querySelector(".modal").onclick=e=>{if(e.target.id==="modal")$("modal").hidden=true};document.querySelectorAll(".filter").forEach(b=>b.onclick=()=>{kind=b.dataset.k;document.querySelectorAll(".filter").forEach(x=>x.classList.remove("active"));b.classList.add("active");load()});$("q").oninput=()=>{clearTimeout(window.t);window.t=setTimeout(load,200)};refresh();setInterval(refresh,2000);load();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX


@app.get("/api/metrics")
def api_metrics():
    return metrics()


@app.get("/api/library")
def api_library(kind="all", q=""):
    rows = [x for x in catalog() if kind == "all" or x.get("type", "").lower() == kind.lower()]
    q = q.lower().strip()
    if q:
        rows = [x for x in rows if q in json.dumps(x, ensure_ascii=False).lower()]
    return {"source": source(), "items": rows, "count": len(rows)}


@app.get("/api/library/{cid}")
def api_library_item(cid: str):
    return item(cid)


@app.get("/api/library/{cid}/download")
def api_library_download(cid: str):
    x = item(cid)
    if x["size"] > MAX_MB * 1024 * 1024:
        raise HTTPException(413, "Configuration is too large")
    folder = (library_root() / x["path"]).resolve()
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        for f in x["files"]:
            p = (folder / f["path"]).resolve()
            try:
                p.relative_to(folder)
            except ValueError:
                continue
            z.write(p, f"{cid}/{f['path']}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{cid}.zip"'})


@app.post("/api/library/sync")
def api_library_sync():
    sync()
    return source()


@app.get("/health")
def health():
    return {"status": "ok"}
