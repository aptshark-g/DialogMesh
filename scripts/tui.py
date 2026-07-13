#!/usr/bin/env python
"""DialogMesh v4 TUI launcher."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("DialogMesh v4 TUI")
print("First launch: loading framework (~15-20s)...")
print("Subsequent launches: instant.")
print()

t0 = time.time()
from core.agent.v4.tui.app import main
elapsed = time.time() - t0
print(f"Loaded in {elapsed:.1f}s")
print()
main()
