# -*- coding: utf-8 -*-
"""Probe C: converge crash path (P1-9) + constraint boundaries."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.blueprint.engine import BlueprintEngine, ConstraintChecker
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder

# C1: converge with non-numeric confidence → ValueError propagates?
print("== C1: converge malformed confidence ==")
b = LLMDAGBuilder()
b._call_llm = lambda *a, **k: '{"nodes":[{"node_id":"pcr_0","chain":"pcr"}],"edges":[],"confidence":"high","design_rationale":"x"}'
from core.agent.blueprint.llm_dag_builder import Hypothesis
h = [Hypothesis(nodes=[{"chain":"pcr"},{"chain":"llm_reply"}], confidence=0.9, rationale="r")]
try:
    dag = b.converge("test", "通用对话", h, None)
    print("    no crash; dag=", dag)
except Exception as e:
    print(f"    CRASH: {type(e).__name__}: {e}")

# C1b: through engine.build LLM_DRIVEN
print("== C1b: engine.build LLM_DRIVEN with malformed confidence ==")
eng = BlueprintEngine()
eng.builder._call_llm = lambda *a, **k: '{"nodes":[{"node_id":"pcr_0","chain":"pcr"}],"edges":[],"confidence":"high","design_rationale":"x"}'
try:
    dag = eng.build("test", intent="因果推理")
    print("    no crash; strategy=", dag.strategy, "nodes=", dag.node_count)
except Exception as e:
    print(f"    CRASH: {type(e).__name__}: {e}")

# C2: constraint boundaries
print("== C2: ConstraintChecker boundaries ==")
ck = ConstraintChecker()
# 8 nodes (over MAX_NODES=7)
dag8 = BlueprintDAG(nodes=[BlueprintNode(f"n{i}", "intent") for i in range(8)] + [BlueprintNode("p", "pcr", priority=0), BlueprintNode("l", "llm_reply", priority=1)], strategy="TEMPLATE")
ok, errs = ck.validate(dag8)
print(f"    8 intent nodes + pcr + llm: valid={ok} errs={errs[:3]}")
# cycle
dag_cyc = BlueprintDAG(nodes=[BlueprintNode("a","pcr"), BlueprintNode("b","intent"), BlueprintNode("c","llm_reply")],
                       edges=[BlueprintEdge("a","b","route"), BlueprintEdge("b","c","x"), BlueprintEdge("c","b","y")], strategy="TEMPLATE")
ok, errs = ck.validate(dag_cyc)
print(f"    cycle a->b->c->b: valid={ok} errs={errs}")
# no llm_reply
dag_nol = BlueprintDAG(nodes=[BlueprintNode("a","pcr")], strategy="TEMPLATE")
ok, errs = ck.validate(dag_nol)
print(f"    no llm_reply: valid={ok} errs={errs}")
# data_key whitelist
dag_badkey = BlueprintDAG(nodes=[BlueprintNode("a","pcr"), BlueprintNode("b","llm_reply")],
                          edges=[BlueprintEdge("a","b","custom_key")], strategy="TEMPLATE")
ok, errs = ck.validate(dag_badkey)
print(f"    unknown data_key: valid={ok} errs={errs}")
