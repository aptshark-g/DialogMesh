# -*- coding: utf-8 -*-
"""Probe C2: converge float('high') crash via engine.build (two-stage mock)."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.blueprint.engine import BlueprintEngine

calls = {"n": 0}
def fake_llm(system, user, **kw):
    calls["n"] += 1
    if calls["n"] == 1:
        # diverge stage — must return a LIST of paths
        return '[{"path":[{"chain":"pcr","reason":"r"},{"chain":"intent","reason":"r"},{"chain":"llm_reply","reason":"r"}],"confidence":0.9,"rationale":"r"}]'
    # converge stage — malformed confidence
    return '{"nodes":[{"node_id":"pcr_0","chain":"pcr"},{"node_id":"llm_1","chain":"llm_reply"}],"edges":[{"from_node":"pcr_0","to_node":"llm_1","data_key":"route"}],"confidence":"high","design_rationale":"x"}'

eng = BlueprintEngine()
eng.builder._call_llm = fake_llm
try:
    dag = eng.build("测试因果推理", intent="因果推理")
    print(f"[C2a] NO crash; strategy={dag.strategy} nodes={dag.node_count} confidence={dag.confidence}")
except Exception as e:
    print(f"[C2a] CRASH: {type(e).__name__}: {e}  ← P1-9 confirmed if this is ValueError")

# C2b: also test bool("false") required
from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder, Hypothesis
from core.agent.blueprint.llm_dag_builder import LearningResult
b2 = LLMDAGBuilder()
calls2 = {"n": 0}
def fake2(system, user, **kw):
    calls2["n"] += 1
    if calls2["n"] == 1:
        return '[{"path":[{"chain":"pcr","reason":"r"},{"chain":"llm_reply","reason":"r"}],"confidence":0.9,"rationale":"r"}]'
    return '{"nodes":[{"node_id":"pcr_0","chain":"pcr"},{"node_id":"llm_1","chain":"llm_reply"}],"edges":[{"from_node":"pcr_0","to_node":"llm_1","data_key":"route","required":"false"}],"confidence":0.8,"design_rationale":"x"}'
b2._call_llm = fake2
dag2 = b2.build_llm_driven("t", "通用对话")
print(f"[C2b] required='false' string → edge.required={dag2.edges[0].required} (should be False, is bool('false')={bool('false')})")
