#!/usr/bin/env bash
# DialogMesh v3.0 — Stop Script
# Usage: ./stop.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$PROJECT_ROOT/.pids"

if [ -f "$PID_FILE" ]; then
    source "$PID_FILE"
    
    if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[Stop] Killing backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    
    if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "[Stop] Killing frontend (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    
    rm -f "$PID_FILE"
    echo "[OK] DialogMesh stopped."
else
    echo "[WARN] No PID file found. Trying to find processes..."
    
    # Try to find and kill by process name
    if command -v pkill &>/dev/null; then
        pkill -f "main_v3.py" 2>/dev/null || true
        pkill -f "vite preview" 2>/dev/null || true
        echo "[OK] Processes terminated."
    else
        echo "[ERROR] Cannot find processes to stop. Please stop manually."
    fi
fi
