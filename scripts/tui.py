#!/usr/bin/env python
"""DialogMesh v4 TUI launcher — Dual-mode (API + Offline)."""
import sys, os, time

# Setup paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

print("DialogMesh v4 TUI")
print("=" * 50)
print("Mode detection: API (localhost:8000) -> Offline (direct engine)")
print()

t0 = time.time()
from tools.tui.app import main
elapsed = time.time() - t0
print(f"Loaded in {elapsed:.1f}s")
print()

main()
