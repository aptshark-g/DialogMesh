#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd $(dirname $0) && pwd)

echo "================================"
echo "DialogMesh v4 - Terminal Dashboard (TUI)"
echo "================================"
echo "8-panel real-time dashboard. Press Ctrl+C to exit."
echo ""

cd $PROJECT_ROOT
python scripts/tui.py
