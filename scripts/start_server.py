"""Start DialogMesh v4 API server.

Usage:  python scripts/start_server.py
"""
import os
import sys

# Ensure the project root is importable regardless of the caller's CWD/Python.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.v4.api import serve

if __name__ == "__main__":
    serve(host="127.0.0.1", port=8000)
