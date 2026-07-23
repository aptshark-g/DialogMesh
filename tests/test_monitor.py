"""E2E Test Monitor — API + Frontend + Gateway full trace.

Usage:
  .venv-test\Scripts\python tests\test_monitor.py
  .venv-test\Scripts\python tests\test_monitor.py --no-frontend
"""
import os, sys, time, json, subprocess, socket, logging, threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "tests" / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Logger ────────────────────────────────────────────────
def setup_logger(name: str) -> logging.Logger:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_DIR / f"{name}_{ts}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(ch)
    return logger

log = setup_logger("monitor")

# ── Port check ────────────────────────────────────────────
def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


# ── Service launchers ─────────────────────────────────────
def _start_process(cmd: list, cwd: Path, name: str, env: dict = None):
    """Start a process with full stdout/stderr to log file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = open(LOG_DIR / f"{name}_{ts}.stdout", "w", encoding="utf-8", buffering=1)
    merged = env or {}
    merged.update(os.environ)
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=logfile, stderr=subprocess.STDOUT, env=merged)
    log.info("%s started (PID=%d)", name, proc.pid)
    return proc


def start_gateway():
    exe = PROJECT_ROOT / "gateway" / "gateway.exe"
    if not exe.exists():
        log.error("Gateway binary not found: %s", exe)
        return None
    if port_open("127.0.0.1", 8080):
        log.info("Gateway already on :8080")
        return None
    log.info("Starting Gateway...")
    proc = _start_process([str(exe)], exe.parent, "gateway")
    for _ in range(10):
        if port_open("127.0.0.1", 8080):
            log.info("Gateway ready")
            return proc
        time.sleep(0.5)
    log.error("Gateway did not start in 5s")
    return proc


def start_api():
    if port_open("127.0.0.1", 8000):
        log.info("API already on :8000")
        return None
    log.info("Starting API...")
    proc = _start_process(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "start_server.py"), "--no-gateway"],
        PROJECT_ROOT, "api"
    )
    for _ in range(15):
        if port_open("127.0.0.1", 8000):
            log.info("API ready")
            return proc
        time.sleep(0.5)
    log.error("API did not start in 8s")
    return proc


def start_frontend():
    if port_open("127.0.0.1", 4173):
        log.info("Frontend already on :4173")
        return None
    fe_dir = PROJECT_ROOT / "frontend"
    if not (fe_dir / "package.json").exists():
        log.warning("Frontend dir not found, skipping")
        return None
    log.info("Starting Frontend (vite dev)...")
    proc = _start_process(
        ["npx", "vite", "--port", "4173"],
        fe_dir, "frontend",
        env={"VITE_API_BASE_URL": "http://localhost:8000"}
    )
    for _ in range(20):
        if port_open("127.0.0.1", 4173):
            log.info("Frontend ready")
            return proc
        time.sleep(0.5)
    log.error("Frontend did not start")
    return proc


# ── HTTP probe with full response logging ─────────────────
def api_call(base: str, path: str, method: str = "GET", headers: dict = None, body: str = None) -> dict:
    import urllib.request, urllib.error
    url = f"{base}{path}"
    h = headers or {}
    data = body.encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode()
            return {"ok": True, "status": resp.status, "body": raw[:3000]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read().decode()[:1000]}
    except Exception as e:
        return {"ok": False, "status": 0, "body": str(e)[:500]}


# ── Full probe suite ──────────────────────────────────────
def probe_all():
    token = {"Authorization": "Bearer dev-token"}
    results = []

    # Gateway
    for path in ["/v1/health", "/v1/diagnostics", "/v1/providers", "/v1/stats"]:
        r = api_call("http://127.0.0.1:8080", path)
        icon = "✅" if r["ok"] else "❌"
        log.info("%s Gateway %s → %s", icon, path, r["status"])
        results.append(("gateway", path, r))

    # API core
    api_paths = [
        "/v4/health", "/v3/health", "/v6/profile", "/v6/trace", "/v6/abc", "/v6/mind",
        "/v6/sessions", "/v6/persistence", "/v6/recursive-map", "/v6/engineering/modules",
        "/v6/engineering", "/v6/gateway/providers", "/v6/gateway/config",
        "/v6/gateway/health", "/v6/gateway/stats", "/v6/gateway/usage",
        "/v6/router/modes", "/v6/providers", "/v6/providers/tokens", "/v6/metrics",
        "/v6/degradation", "/v6/causal", "/v6/ttl", "/v6/subgraph/cache",
        "/v6/audit", "/v6/causal-chain", "/v6/sync",
    ]
    for path in api_paths:
        r = api_call("http://127.0.0.1:8000", path, token)
        icon = "✅" if r["ok"] else "❌"
        log.info("%s API %s → %s", icon, path, r["status"])
        results.append(("api", path, r))

    return results


# ── Frontend proxy probe ──────────────────────────────────
def probe_frontend_proxy():
    """Check if frontend can reach API through its proxy."""
    # Vite dev server proxies /api → http://localhost:8000 if configured
    # Otherwise check frontend HTML to see if it loads
    r = api_call("http://127.0.0.1:4173", "/")
    if r["ok"]:
        log.info("✅ Frontend responds (HTML %d bytes)", len(r["body"]))
        # Check if API calls in frontend HTML reference correct URL
        if "localhost:8000" in r["body"] or "VITE_API" in r["body"]:
            log.info("  Frontend HTML references API correctly")
    else:
        log.error("❌ Frontend not responding: %s", r["body"][:200])


# ── Continuous watch ──────────────────────────────────────
def watch_loop(interval: int = 5):
    """Poll both services + frontend, log state changes and errors."""
    log.info("═══ Watch mode: %ds interval ═══", interval)
    states = {"gw": None, "api": None, "fe": None}
    errors = {"gw": 0, "api": 0, "fe": 0}

    while True:
        try:
            # Gateway
            gw = api_call("http://127.0.0.1:8080", "/v1/health")
            gw_state = "UP" if gw["ok"] else f"DOWN({gw['status']})"
            if gw_state != states["gw"]:
                icon = "✅" if gw["ok"] else "❌"
                log.info("%s Gateway: %s", icon, gw_state)
                if not gw["ok"]:
                    log.warning("  Gateway error: %s", gw["body"][:200])
                    errors["gw"] += 1
                states["gw"] = gw_state

            # API
            api = api_call("http://127.0.0.1:8000", "/v4/health", {"Authorization": "Bearer dev-token"})
            api_state = "UP" if api["ok"] else f"DOWN({api['status']})"
            if api_state != states["api"]:
                icon = "✅" if api["ok"] else "❌"
                log.info("%s API: %s", icon, api_state)
                if not api["ok"]:
                    log.warning("  API error: %s", api["body"][:200])
                    errors["api"] += 1
                states["api"] = api_state

            # Frontend
            fe = api_call("http://127.0.0.1:4173", "/")
            fe_state = "UP" if fe["ok"] else f"DOWN({fe['status']})"
            if fe_state != states["fe"]:
                icon = "✅" if fe["ok"] else "❌"
                log.info("%s Frontend: %s", icon, fe_state)
                if not fe["ok"]:
                    errors["fe"] += 1
                states["fe"] = fe_state

            # Summary every 30s
            if sum(errors.values()) > 0 and int(time.time()) % 30 < interval:
                log.info("  Errors so far: gw=%d api=%d fe=%d", errors["gw"], errors["api"], errors["fe"])

            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Watch stopped (errors: gw=%d api=%d fe=%d)", errors["gw"], errors["api"], errors["fe"])
            break


# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("═══ DialogMesh E2E Monitor ═══")
    log.info("Log dir: %s", LOG_DIR)

    no_fe = "--no-frontend" in sys.argv

    gw = start_gateway()
    api = start_api()
    fe = start_frontend() if not no_fe else None

    # Initial probe
    log.info("═══ Initial probe ═══")
    results = probe_all()
    ok_count = sum(1 for _, _, r in results if r["ok"])
    log.info("  Total: %d/%d OK", ok_count, len(results))

    if fe:
        probe_frontend_proxy()

    # API↔frontend trace: capture a full request round-trip
    log.info("═══ Frontend→API round-trip ═══")
    for path in ["/v6/profile", "/v6/gateway/providers", "/v6/metrics"]:
        r = api_call("http://127.0.0.1:8000", path, {"Authorization": "Bearer dev-token"})
        icon = "✅" if r["ok"] else "❌"
        log.info("%s FE→API %s → %s", icon, path, r["status"])
        if r["ok"]:
            # Log the actual data shapes
            try:
                data = json.loads(r["body"])
                if isinstance(data, dict):
                    log.info("  Response keys: %s", list(data.keys())[:10])
                elif isinstance(data, list):
                    log.info("  Response: list of %d items", len(data))
            except Exception:
                log.info("  Response: %s", r["body"][:200])

    log.info("═══ Live watch ═══")
    watch_loop(interval=5)

    # Cleanup
    for proc in [gw, api, fe]:
        if proc:
            proc.terminate()
    log.info("Done. Logs: %s", LOG_DIR)
