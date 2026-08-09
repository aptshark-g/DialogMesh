# -*- coding: utf-8 -*-
"""Probe A2: breakdown of 12.9s cold process() — which stage is slow?"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.orchestrator.agent_native import AgentOrchestrator
orch = AgentOrchestrator()

text = "分析 auth.py 的安全性"

# Stage: Compass
t0 = time.time()
try:
    cr = orch._compass.measure(text)
    print(f"[C1] compass.measure: {(time.time()-t0)*1000:.0f}ms -> lenses={len(cr.selected_lenses) if cr.selected_lenses else 0}")
except Exception as e:
    print(f"[C1] compass.measure FAILED: {type(e).__name__} {str(e)[:100]} ({(time.time()-t0)*1000:.0f}ms)")

# Stage: Context assembly (needs a result dict with text)
t0 = time.time()
try:
    ctx = orch._context_assembly.assemble({"text": text})
    print(f"[C2] context_assembly.assemble: {(time.time()-t0)*1000:.0f}ms -> keys={list(ctx.keys())[:6]}")
except Exception as e:
    print(f"[C2] context_assembly FAILED: {type(e).__name__} {str(e)[:100]} ({(time.time()-t0)*1000:.0f}ms)")

# Stage: Cognition hub converge
t0 = time.time()
try:
    cog = orch._cognition_hub.converge()
    print(f"[C3] cognition_hub.converge: {(time.time()-t0)*1000:.0f}ms")
except Exception as e:
    print(f"[C3] cognition_hub.converge FAILED: {type(e).__name__} {str(e)[:100]} ({(time.time()-t0)*1000:.0f}ms)")

# Full process() again (now warm) — confirm
t0 = time.time()
r = orch.process(text=text)
print(f"[C4] warm process(): {(time.time()-t0)*1000:.0f}ms keys={list(r.keys())}")
