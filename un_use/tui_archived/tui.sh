#!/usr/bin/env bash
# DialogMesh v4 TUI launcher — Unix/Linux/macOS

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================"
echo "   DialogMesh v4 - Terminal Dashboard (TUI)"
echo "================================================================"
echo ""
echo "  Dual-mode: API (localhost:8000) | Offline (direct engine)"
echo "  Mode auto-detected on startup."
echo ""
echo "  First launch may take 5-10 seconds for Python imports."
echo ""

python scripts/tui.py
