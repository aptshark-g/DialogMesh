"""One-click launcher: DialogMesh + switch Gateway.

Usage:
  python scripts/start.py              # Start both, auto-detect switch
  python scripts/start.py --no-switch  # Skip switch, direct DeepSeek
  python scripts/start.py --switch-only # Only start switch gateway

Flow:
  1. Check if switch gateway binary exists
  2. Check if switch is already running (health check :8080)
  3. If not running → start switch with provider.yaml
  4. Verify switch health
  5. Start DialogMesh API server
  6. DialogMesh auto-detects switch → uses it or falls back
"""
import subprocess, sys, os, time, urllib.request, json, signal

SWITCH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                           "gateway")
SWITCH_BIN = os.path.join(SWITCH_DIR, "gateway.exe")
SWITCH_URL = os.environ.get("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080")
SWITCH_KEY = os.environ.get("SWITCH_GATEWAY_KEY", "dm-client")

# DialogMesh paths
DM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DM_PYTHON = os.path.join(DM_DIR, ".venv-test", "Scripts", "python.exe")


def switch_health() -> bool:
    """Check if switch gateway is reachable."""
    try:
        req = urllib.request.Request(f"{SWITCH_URL}/v1/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return data.get("status") in ("healthy", "degraded")
    except Exception:
        return False


def start_switch():
    """Start switch gateway if not already running."""
    if not os.path.exists(SWITCH_BIN):
        print("⚠  switch gateway binary not found at:", SWITCH_BIN)
        return None
    
    if switch_health():
        print("✅ switch gateway already running on", SWITCH_URL)
        return None  # Already running
    
    print("Starting switch gateway...")
    proc = subprocess.Popen(
        [SWITCH_BIN],
        cwd=SWITCH_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    # Wait for health
    for i in range(15):
        time.sleep(0.5)
        if switch_health():
            print("✅ switch gateway started (pid={})".format(proc.pid))
            return proc
        if proc.poll() is not None:
            print("❌ switch gateway failed to start")
            return None
    
    print("⚠  switch gateway started but not healthy")
    return proc


def start_dialogmesh(use_switch: bool = True):
    """Start DialogMesh API server."""
    env = os.environ.copy()
    env["PYTHONHOME"] = ""
    env["PYTHONPATH"] = ""
    
    if not use_switch:
        env["SWITCH_GATEWAY_URL"] = ""
    
    print("Starting DialogMesh API...")
    print("  Switch mode:", "ON" if use_switch else "OFF (direct DeepSeek)")
    
    subprocess.run(
        [DM_PYTHON, "-c", 
         "from core.agent.v4.api import serve; serve(host='127.0.0.1', port=8000)"],
        cwd=DM_DIR, env=env,
    )


def main():
    args = set(sys.argv[1:])
    
    if "--switch-only" in args:
        proc = start_switch()
        if proc:
            print("switch running. Press Ctrl+C to stop.")
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
        return
    
    use_switch = "--no-switch" not in args
    
    if use_switch:
        switch_proc = start_switch()
        if switch_proc:
            # Register cleanup
            def cleanup(sig, frame):
                print("\nShutting down switch...")
                switch_proc.terminate()
                sys.exit(0)
            signal.signal(signal.SIGINT, cleanup)
            signal.signal(signal.SIGTERM, cleanup)
    
    start_dialogmesh(use_switch=use_switch)


if __name__ == "__main__":
    main()
