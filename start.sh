#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh v3.0 — One-Click Startup (Git Bash / WSL / Linux / macOS)
# ═══════════════════════════════════════════════════════════════════════════════
# Usage: ./start.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    DialogMesh v3.0 — Startup Script                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# ── Detect environment ────────────────────────────────────────────────────────

# Node.js
if command -v node &>/dev/null; then
    NODE_CMD="node"
    NPM_CMD="npm"
elif [ -f "/c/Program Files/nodejs/npm.cmd" ]; then
    NODE_CMD="/c/Program Files/nodejs/node.exe"
    NPM_CMD="cmd //c '/c/Program Files/nodejs/npm.cmd'"
else
    echo "[ERROR] Node.js not found. Please install Node.js 18+."
    exit 1
fi

# Python
if command -v py &>/dev/null; then
    PYTHON_CMD="py"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python not found. Please install Python 3.9+."
    exit 1
fi

# Fix Anaconda sqlite3 on Windows
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    if [ -d "/c/Users/APTShark/anaconda3/Library/bin" ]; then
        export PATH="/c/Users/APTShark/anaconda3/Library/bin:$PATH"
        echo "[Fix] Added Anaconda Library/bin to PATH for sqlite3"
    fi
fi

# ── Check prerequisites ───────────────────────────────────────────────────────

echo "[Check] Node.js ..."
$NODE_CMD --version
echo "[OK] Node.js ready."

echo "[Check] Python ..."
$PYTHON_CMD --version
echo "[OK] Python ready."

echo "[Check] sqlite3 ..."
if ! $PYTHON_CMD -c "import sqlite3; print('sqlite3:', sqlite3.sqlite_version)" 2>/dev/null; then
    echo "[ERROR] sqlite3 not working. If using Anaconda, ensure Library/bin is in PATH."
    exit 1
fi
echo "[OK] sqlite3 ready."

echo "[Check] Frontend build ..."
if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    echo "[WARN] Frontend dist not found. Building..."
    cd "$FRONTEND_DIR"
    $NPM_CMD run build
fi
echo "[OK] Frontend build ready."

echo ""
echo "[INFO] Starting DialogMesh services..."
echo "  - Backend:  http://localhost:8000"
echo "  - Frontend: http://localhost:5173"
echo "  - API Docs: http://localhost:8000/docs"
echo ""

# ── Start Backend ─────────────────────────────────────────────────────────────

echo "[1/2] Starting Backend (FastAPI) in background..."
cd "$PROJECT_ROOT"
nohup $PYTHON_CMD main_v3.py --host 0.0.0.0 --port 8000 --log-level info > backend.log 2>&1 &
BACKEND_PID=$!
echo "[PID] Backend started: $BACKEND_PID"

# Wait for backend health check
echo "[Wait] Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo "[OK] Backend is ready."
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "[WARN] Backend health check timed out. Check backend.log"
    fi
done

# ── Start Frontend ────────────────────────────────────────────────────────────

echo "[2/2] Starting Frontend (Vite Preview) in background..."
cd "$FRONTEND_DIR"
nohup $NODE_CMD ./node_modules/.bin/vite preview --port 5173 --host > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "[PID] Frontend started: $FRONTEND_PID"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  DialogMesh is running!                                                      ║"
echo "║                                                                              ║"
echo "║  • Frontend: http://localhost:5173                                           ║"
echo "║  • Backend:  http://localhost:8000                                           ║"
echo "║  • API Docs: http://localhost:8000/docs                                      ║"
echo "║                                                                              ║"
echo "║  Stop commands:                                                              ║"
echo "║    kill $BACKEND_PID   # stop backend                                       ║"
echo "║    kill $FRONTEND_PID  # stop frontend                                      ║"
echo "║    ./stop.sh           # stop both (if available)                           ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Save PIDs for stop script
cat > .pids <<EOF
BACKEND_PID=$BACKEND_PID
FRONTEND_PID=$FRONTEND_PID
EOF
