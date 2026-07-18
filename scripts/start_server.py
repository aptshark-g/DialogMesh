"""Start DialogMesh v4 API server.

Usage:  python scripts/start_server.py
"""
from core.agent.v4.api import serve

if __name__ == "__main__":
    serve(host="127.0.0.1", port=8000)
