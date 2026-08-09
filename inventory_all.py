#!/usr/bin/env python3
"""Inventory all modules across v3_0, v4/cognitive, and current v6."""
import os, re

def inventory(base_path, label):
    for root, dirs, files in os.walk(base_path):
        for f in sorted(files):
            if not f.endswith('.py') or "__pycache__" in root or f == "__init__.py":
                continue
            path = os.path.join(root, f)
            text = open(path, encoding="utf-8").read()
            m = re.search(r'\"\"\"(.*?)\"\"\"', text, re.DOTALL)
            purpose = m.group(1).strip() if m else "no docstring"
            purpose = " ".join(purpose.split()[:15])
            lines = len(text.splitlines())
            rel = os.path.relpath(path, base_path)
            print(f"  {label}/{rel:45s} {lines:>5}L  {purpose[:75]}")

print("=== v3_0 (legacy cognitive architecture) ===")
inventory("core/agent/v3_0", "v3_0")

print("\n=== v4/cognitive (cognitive modules) ===")
inventory("core/agent/v4/cognitive", "v4_cog")

print("\n=== Current v6 (core modules) ===")
for d in ["core/agent/persistence", "core/agent/memory", "core/agent/compiler", 
          "core/agent/orchestrator", "core/agent/observability"]:
    print(f"\n  --- {d} ---")
    inventory(d, "v6")
