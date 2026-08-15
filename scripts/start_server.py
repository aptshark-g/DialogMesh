"""Start DialogMesh v6 — minimal FastAPI server with v6 chat endpoint.

Bypasses heavy legacy imports. Only loads v6-specific modules.
"""

import os, sys, time, subprocess
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-08-15 排查: app logger 无 handler → 错误静默吞掉; 补 stdout 日志
# + HF 离线（模型已缓存, 消灭每次请求 10013 联网重试 ~6s 噪音）。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_EXE = os.path.join(PROJECT_ROOT, "gateway", "gateway.exe")


def start_gateway():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.connect(("127.0.0.1", 8080)); s.close()
        print("[Gateway] Already running on :8080 (reusing)"); return None
    except Exception:
        s.close()
    if not os.path.exists(GATEWAY_EXE):
        print("[Gateway] Not found, skipping"); return None
    print("[Gateway] Starting...")
    p = subprocess.Popen([GATEWAY_EXE], cwd=os.path.dirname(GATEWAY_EXE),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2); return p


def _check_port(port: int) -> bool:
    """Check if port is already in use."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port)); s.close(); return False
    except OSError:
        return True


if __name__ == "__main__":
    no_gw = "--no-gateway" in sys.argv
    gw = None if no_gw else start_gateway()
    if no_gw:
        print("[Gateway] Skipped (--no-gateway)")

    # Check if already running — reuse instead of error
    if _check_port(8000):
        print("[API] Port 8000 in use — server may already be running")
        print("[API] Stop existing process first or use different port")
        if gw: gw.terminate(); gw.wait()
        sys.exit(0)

    try:
        from core.agent.api.v6_app import app
        import uvicorn
        print("[v6] Starting on :8000")
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    finally:
        if gw:
            gw.terminate(); gw.wait()
