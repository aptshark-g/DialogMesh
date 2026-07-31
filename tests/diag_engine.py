"""Diagnose where engine creation hangs."""
import sys, time
sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")

t0 = time.time()
print(f"[0.0s] start")

import core.agent.cli.engine as eng
print(f"[{time.time()-t0:.1f}s] engine module imported")

eng._engine = None
e = eng._create_engine_instance(provider_config={'type': 'mock'})
print(f"[{time.time()-t0:.1f}s] engine instance created")
print(f"[{time.time()-t0:.1f}s] registry: {len(e._registry._defs)} defs, {sum(1 for r in e._registry._results.values() if r.loaded)} loaded")

# What's NOT loaded?
failed = [n for n, r in e._registry._results.items() if not r.loaded]
print(f"[{time.time()-t0:.1f}s] failed: {failed}")

sm = getattr(e, '_state_machine', None)
print(f"[{time.time()-t0:.1f}s] state_machine: {'YES' if sm else 'NO'}")
