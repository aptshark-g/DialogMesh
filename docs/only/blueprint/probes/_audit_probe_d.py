# -*- coding: utf-8 -*-
"""Probe D: cache collision + same-tick dependency skip + override add boundary."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.blueprint.engine import BlueprintEngine
from core.agent.blueprint.decider import Decider
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

# D1: cache collision — find two texts with same hash%10000
print("== D1: cache key collision ==")
base = "分析任务"
collide = None
for i in range(20000):
    t = f"{base}{i}"
    if hash(t) % 10000 == hash(base) % 10000 and t != base:
        collide = t
        break
eng = BlueprintEngine()
d1 = eng.build(base, intent="代码分析")
d2 = eng.build(collide, intent="代码分析")
print(f"    text1={base!r} text2={collide!r}")
print(f"    same hash%10000: {hash(base)%10000 == hash(collide)%10000}")
print(f"    d1 is d2 (shared obj): {d1 is d2}")
print(f"    d1.design_rationale: {d1.design_rationale[:30]}")

# D2: same-tick dependency — node B in tick 0 depends on A in tick 0
print("== D2: same-tick required dep ==")
dag = BlueprintDAG(
    nodes=[BlueprintNode("a","pcr",priority=0), BlueprintNode("b","intent",priority=0),
           BlueprintNode("c","llm_reply",priority=1)],
    edges=[BlueprintEdge("a","b","route"), BlueprintEdge("a","c","route"), BlueprintEdge("b","c","intent_context")],
    strategy="TEMPLATE")
# stub handlers to observe skip
res = Decider().execute(dag, user_text="hi")
print(f"    tick0 nodes: {res['ticks'][0]['nodes']} (b should be SKIPPED — same-tick dep on a)")
print(f"    tick1 nodes: {res['ticks'][1]['nodes']}")
print(f"    completed keys: {list(res['chain_outputs'].keys())}")

# D3: override add with deps referencing missing node — validate catches?
print("== D3: HYBRID override add boundary ==")
eng3 = BlueprintEngine()
eng3.builder._call_llm = lambda *a, **k: '{"action":"modify","add":[{"node_id":"subgraph_x","chain":"subgraph","deps":["ghost"]}],"remove":[],"reorder":{}}'
dag3 = eng3.build("帮我规划", intent="任务规划")
print(f"    after override: nodes={[n.node_id for n in dag3.nodes]}")
print(f"    edges={[(e.from_node,e.to_node,e.data_key) for e in dag3.edges]}")
ok, errs = eng3.checker.validate(dag3)
print(f"    validate: valid={ok} errs={errs[:4]}")

# D3b: was the GLOBAL template polluted? next request for 任务规划 should be clean
print("== D3b: global pollution check after bad override ==")
from core.agent.blueprint.skill_registry import BUILTIN_TEMPLATES
tpl = BUILTIN_TEMPLATES["task_planning"]
print(f"    BUILTIN task_planning now: nodes={[n.node_id for n in tpl.nodes]}")
print(f"    edges={[(e.from_node,e.to_node) for e in tpl.edges]}")
ok2, errs2 = eng3.checker.validate(tpl)
print(f"    validate global template: valid={ok2} errs={errs2[:3]}")
