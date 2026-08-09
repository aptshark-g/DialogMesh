# -*- coding: utf-8 -*-
"""Probe B: bootstrap() actual module loading + who wires core chains."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.orchestrator.bootstrap_v6 import bootstrap
t0 = time.time()
orch = bootstrap()
print(f"[B1] bootstrap() ctor: {(time.time()-t0)*1000:.0f}ms")
print(f"    pcr={orch.pcr} intent={orch.intent} l4={orch.l4} behavior={orch.behavior}")
print(f"    engineering={orch.engineering} llm={'Y' if orch.llm else 'N'} discourse={orch.discourse}")
print(f"    _compass={'Y' if orch._compass else 'N'} _context_assembly={'Y' if orch._context_assembly else 'N'}")
print(f"    _event_log={'Y' if orch._event_log else 'N'} _event_bus={'Y' if orch._event_bus else 'N'}")
print(f"    _reactor={'Y' if orch._reactor else 'N'} _file_sandbox={'Y' if orch._file_sandbox else 'N'}")
print(f"    _permission_guard={'Y' if orch._permission_guard else 'N'} _semantic_diff={'Y' if orch._semantic_diff else 'N'}")

# Who wires real PCR/Intent into AgentOrchestrator? — registry path is separate runtime
print("[B2] rg evidence: only cli/registry.py:273 constructs PCRRouterV2 (CLI runtime), never passed to bootstrap()")

# Does EventLog write work? bootstrap created data/event_log.db
import os
db = os.path.join("data", "event_log.db")
print(f"[B3] event_log.db exists: {os.path.exists(db)}")

# Bootstrap warm process — how long?
t0 = time.time()
r = orch.process(text="hello")
print(f"[B4] bootstrap orch.process(warm): {(time.time()-t0)*1000:.0f}ms keys={list(r.keys())}")
