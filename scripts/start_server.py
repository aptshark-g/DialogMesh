"""Start DialogMesh v6 — API + optional Gateway.

Usage:  python scripts/start_server.py
        python scripts/start_server.py --no-gateway
"""
import os
import sys
import subprocess
import time

# Ensure the project root is importable regardless of the caller's CWD/Python.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_EXE = os.path.join(PROJECT_ROOT, "gateway", "gateway.exe")


def start_gateway() -> Optional[subprocess.Popen]:
    """Launch switch gateway as a subprocess if it's not already running."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("127.0.0.1", 8080))
        sock.close()
        print("[Gateway] Already running on :8080")
        return None
    except Exception:
        sock.close()

    if not os.path.exists(GATEWAY_EXE):
        print("[Gateway] Binary not found, skipping (use --no-gateway to suppress)")
        return None

    print(f"[Gateway] Starting {GATEWAY_EXE}...")
    proc = subprocess.Popen(
        [GATEWAY_EXE],
        cwd=os.path.dirname(GATEWAY_EXE),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # wait for startup
    return proc


if __name__ == "__main__":
    no_gateway = "--no-gateway" in sys.argv

    if not no_gateway:
        gw_proc = start_gateway()
    else:
        gw_proc = None
        print("[Gateway] Skipped (--no-gateway)")

    try:
        from core.agent.v4.api import serve
        serve(host="127.0.0.1", port=8000)
    finally:
        if gw_proc:
            gw_proc.terminate()
            gw_proc.wait()
