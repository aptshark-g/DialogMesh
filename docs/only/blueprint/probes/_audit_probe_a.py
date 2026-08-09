# -*- coding: utf-8 -*-
"""Probe A: AgentOrchestrator() no-arg behavior + 19s latency breakdown."""
import sys, io, time, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

t0 = time.time()
from core.agent.orchestrator.agent_native import AgentOrchestrator
print(f"[A0] import agent_native: {(time.time()-t0)*1000:.0f}ms")

t0 = time.time()
orch = AgentOrchestrator()
print(f"[A1] AgentOrchestrator() ctor: {(time.time()-t0)*1000:.0f}ms")
print(f"    pcr={orch.pcr} intent={orch.intent} l4={orch.l4} behavior={orch.behavior}")
print(f"    engineering={orch.engineering} llm={orch.llm} discourse={orch.discourse}")
print(f"    _compass={'Y' if orch._compass else 'N'} _context_assembly={'Y' if orch._context_assembly else 'N'}")
print(f"    _cognition_hub={'Y' if orch._cognition_hub else 'N'} _feedback_bridge={'Y' if orch._feedback_bridge else 'N'}")
print(f"    _plan_gate={'Y' if orch._plan_gate else 'N'} _execution_pipeline={'Y' if orch._execution_pipeline else 'N'}")
print(f"    cognitive={'Y' if orch.cognitive else 'N'} _event_log={'Y' if orch._event_log else 'N'}")

t0 = time.time()
try:
    r = orch.process(text="分析 auth.py 的安全性")
    print(f"[A2] process() returns: {(time.time()-t0)*1000:.0f}ms, keys={list(r.keys())}")
    print(f"    has route: {'route' in r} | has intents: {'intents' in r}")
    print(f"    route={r.get('route')} intents={r.get('intents')}")
    print(f"    compass keys={list(r.get('compass', {}).keys())}")
    print(f"    context keys={list(r.get('context', {}).keys())}")
    print(f"    plan={'plan' in r} latency_ms={r.get('latency_ms')}")
except Exception as e:
    print(f"[A2] process() RAISED: {type(e).__name__}: {e}")
    traceback.print_exc()

t0 = time.time()
r2 = orch.process(text="再次调用测试热路径")
print(f"[A3] 2nd process() (warm): {(time.time()-t0)*1000:.0f}ms, route={'route' in r2} intents={'intents' in r2}")
