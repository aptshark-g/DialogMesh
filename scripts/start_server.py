"""Start DialogMesh v6 — minimal FastAPI server with v6 chat endpoint.

Bypasses heavy legacy imports. Only loads v6-specific modules.
"""

import os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_EXE = os.path.join(PROJECT_ROOT, "gateway", "gateway.exe")


def start_gateway():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", 8080)); s.close()
        print("[Gateway] Already running on :8080"); return None
    except Exception:
        s.close()
    if not os.path.exists(GATEWAY_EXE):
        print("[Gateway] Not found, skipping"); return None
    print("[Gateway] Starting...")
    p = subprocess.Popen([GATEWAY_EXE], cwd=os.path.dirname(GATEWAY_EXE),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2); return p


if __name__ == "__main__":
    no_gw = "--no-gateway" in sys.argv
    gw = None if no_gw else start_gateway()
    if no_gw:
        print("[Gateway] Skipped (--no-gateway)")

    try:
        from core.agent.api.v6_app import app
        import uvicorn
        print("[v6] Starting on :8000")
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    finally:
        if gw:
            gw.terminate(); gw.wait()
