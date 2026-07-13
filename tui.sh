#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd $(dirname $0) && pwd)

echo "================================"
echo "DialogMesh v4 - Terminal Dashboard (TUI)"
echo "================================"
echo ""

cd $PROJECT_ROOT
python scripts/tui.py
