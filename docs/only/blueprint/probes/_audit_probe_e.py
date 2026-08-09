# -*- coding: utf-8 -*-
"""Probe E: match/update_weight/MetaFeedback/learn/tracer edge behavior."""
import sys, io, os, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.agent.blueprint.skill_registry import SkillRegistry, BUILTIN_TEMPLATES

# E1: partial match boundaries
print("== E1: match() partial-match boundaries ==")
r = SkillRegistry()
for intent in ["代码分析", "做代码分析", "帮我分析代码", "分析", "代码", "任务", "规划项目", "数据", "天气", ""]:
    s, bp = r.match(intent)
    print(f"    match({intent!r:10}) -> strategy={s:10} template={bp.design_rationale[:18]}")

# E2: update_weight evolution — repeated low scores then recovery
print("== E2: update_weight evolution ==")
r2 = SkillRegistry()
w0 = [(w.strategy, round(w.weight,2), w.total_count) for w in r2._strategy_weights["代码分析"]]
for i in range(3):
    r2.update_weight("代码分析", "LLM_DRIVEN", 0.2)   # 3 low
w_low = [(w.strategy, round(w.weight,2), w.total_count, w.success_count) for w in r2._strategy_weights["代码分析"]]
for i in range(2):
    r2.update_weight("代码分析", "LLM_DRIVEN", 0.95)  # 2 high
w_hi = [(w.strategy, round(w.weight,2), w.total_count, w.success_count) for w in r2._strategy_weights["代码分析"]]
print(f"    initial: {w0}")
print(f"    after 3x low:  {w_low}")
print(f"    after 2x high: {w_hi}")
s, bp = r2.match("代码分析")
print(f"    match after evolution -> {s}")

# E3: MetaFeedback triggers
print("== E3: MetaFeedback degrade/promote behavior ==")
from core.agent.blueprint.meta_feedback import MetaFeedback
from core.agent.blueprint.models import ExecutionAudit
fb = MetaFeedback(r2)
for i in range(3):
    fb.consume(ExecutionAudit(request_id=str(i), blueprint_id="x", strategy="LLM_DRIVEN", dag_quality_score=0.2))
actions = fb.check_degradations()
print(f"    after 3 low audits: actions={actions}")
print(f"    registry weights after degrade-action: {[(w.strategy, round(w.weight,2)) for w in r2._strategy_weights['代码分析']]}")
print(f"    (registry unchanged? -> {'Y' if w_hi == [(w.strategy, round(w.weight,2), w.total_count, w.success_count) for w in r2._strategy_weights['代码分析']] else 'N'})")

# E4: learn() offline behavior
print("== E4: learn() with no hypotheses / offline ==")
from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder, Hypothesis
b = LLMDAGBuilder()
lr = b.learn([], "代码分析")
print(f"    empty hypotheses -> LearningResult(arxiv={len(lr.arxiv_matches)}, refs={len(lr.reference_matches)})")
lr2 = b.learn([Hypothesis(nodes=[{"chain":"pcr"}], confidence=0.9, rationale="r")], "代码分析")
print(f"    with hypotheses (offline): arxiv={len(lr2.arxiv_matches)} eventlog={len(lr2.eventlog_matches)} refs={lr2.reference_matches}")

# E5: tracer file path + record
print("== E5: PipelineTracer CWD-dependent path ==")
from core.agent.blueprint.tracer import PipelineTracer, TRACE_FILE
print(f"    TRACE_FILE = {TRACE_FILE} (resolve: {TRACE_FILE.resolve()})")
cwd = os.getcwd()
print(f"    cwd = {cwd}")
PipelineTracer.record("req1", "sess12345678", {"intent":"x","strategy":"T","blueprint_nodes":2,"chain_summary":{"pcr":"ok"},"ticks":1,"llm_reply":"hello world","errors":[],"latency_ms":5})
print(f"    file exists: {TRACE_FILE.exists()} -> {TRACE_FILE.resolve()}")
last = PipelineTracer.read_last(1)
print(f"    read_last(1): {len(last)} trace(s), keys={list(last[0].keys()) if last else 'N/A'}")
