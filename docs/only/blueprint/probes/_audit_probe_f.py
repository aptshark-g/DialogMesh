# -*- coding: utf-8 -*-
"""Probe F: strategy overwrite after fallback + unknown chain + v3_session intent chain."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.blueprint.engine import BlueprintEngine
from core.agent.blueprint.decider import Decider
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

# F1: constraint-fail fallback → dag.strategy overwritten (misleading)
print("== F1: RECOVERY dag strategy overwrite ==")
eng = BlueprintEngine()
eng.builder._call_llm = lambda *a, **k: '{"action":"modify","add":[{"node_id":"subgraph_x","chain":"subgraph","deps":["ghost"]}],"remove":[],"reorder":{}}'
dag = eng.build("帮我规划项目", intent="任务规划")
print(f"    returned dag: nodes={[n.node_id for n in dag.nodes]} strategy={dag.strategy}")
print(f"    rationale={dag.design_rationale}")
print(f"    -> strategy claims {dag.strategy} but actual structure is {'RECOVERY' if len(dag.nodes)==2 and dag.nodes[0].chain=='pcr' else '?'}")

# F2: unknown chain — BlueprintNode.__post_init__ rejects at construction?
print("== F2: unknown chain node ==")
try:
    BlueprintNode("u1", "unknown_chain_xyz")
    print("    constructed OK (no validation)")
except ValueError as e:
    print(f"    REJECTED at construction: {str(e)[:80]}")
    print("    -> decider L100-102 'unknown chain fallback to llm_reply' is DEAD CODE (unreachable)")

# F3: v3_session_api intent chain — cognitive_ctx has no intents → intent="通用对话" → general_chat
print("== F3: production intent chain ==")
cognitive_ctx = {"intents": {}, "route": {}, "compass": {}, "context": {}}
intent = cognitive_ctx.get("intents", {}).get("primary", "")
if not intent:
    segments = cognitive_ctx.get("intents", {}).get("segments", [])
    intent = segments[0] if segments else "通用对话"
eng3 = BlueprintEngine()
dag3 = eng3.build("帮我分析 auth.py 的安全性", intent=intent)
print(f"    intent resolved to: {intent}")
print(f"    blueprint: strategy={dag3.strategy} nodes={dag3.node_count} rationale={dag3.design_rationale[:24]}")
print(f"    -> production ALWAYS builds general_chat (4 nodes) because orchestrator never sets intents")

# F4: same tick reversed order — b defined BEFORE a but a is dep
print("== F4: same-tick reversed definition order ==")
dag4 = BlueprintDAG(
    nodes=[BlueprintNode("b","intent",priority=0), BlueprintNode("a","pcr",priority=0),
           BlueprintNode("c","llm_reply",priority=1)],
    edges=[BlueprintEdge("a","b","route"), BlueprintEdge("a","c","route"), BlueprintEdge("b","c","intent_context")],
    strategy="TEMPLATE")
res4 = Decider().execute(dag4, user_text="hi")
print(f"    tick0 nodes: {res4['ticks'][0]['nodes']} (b first, depends on a later in same tick)")
print(f"    completed: {list(res4['chain_outputs'].keys())}")
print(f"    -> b SKIPPED if dep not completed at its turn: {'b not in res4[\"chain_outputs\"]' if 'b' not in res4['chain_outputs'] else 'b executed'}")
