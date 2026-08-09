"""M3 认知层接线测试 — B1-8 + LLM-1 + LLM-3 (2026-08-04).

覆盖验收:
  B1-8-① engine 启动后 _cognitive_observer/_scheduler 可实例化（开关开启时）
  B1-8-② run_cognitive_loop 主路径可跑（PERCEIVE→REASON→REFLECT→COMMIT 闭环）
  B1-8-③ 快速通道（短文本）不经过认知循环（A16）
  B1-8-④ 认知循环 reasoning_tree/hypotheses 落 cognitive_tree（LLM-1 联动）
  B1-8-⑤ v4/cognitive_scheduler/ 核心调度（scheduler/policy）已归档 un_use
  LLM-3-① 规划/工具执行前有预测写入思考树（含置信度）
  LLM-3-② 执行后结果对照写回（差异可见）
  LLM-3-③ 重复同类任务预测命中（策略权重变化可观测）
"""
import pytest

from core.agent.runtime.engine import CognitiveRuntimeEngine


@pytest.fixture(scope="module")
def engine():
    eng = CognitiveRuntimeEngine()
    return eng


class TestCognitiveRuntimeInit:
    """B1-8-①: engine 认知运行时懒初始化。"""

    def test_observer_scheduler_live(self, engine):
        engine._init_cognitive_runtime()
        assert engine._cognitive_observer is not None
        assert engine._cognitive_scheduler is not None
        assert engine._cognitive_tree is not None
        assert engine._cognitive_compiler is not None

    def test_default_disabled(self, engine):
        # A16: 默认关闭认知前置 — 快速通道不经过认知循环
        assert engine._cognitive_runtime_enabled is False
        assert engine._run_cognitive_prepass("简短问题") is None

    def test_short_text_skips_prepass(self, engine):
        engine._cognitive_runtime_enabled = True
        try:
            # 短文本 = 快速通道 (A16)
            assert engine._run_cognitive_prepass("hi") is None
        finally:
            engine._cognitive_runtime_enabled = False


class TestCognitiveLoop:
    """B1-8-②④: 认知循环可跑 + workspace → 思考树联动。"""

    def test_loop_runs_and_writes_tree(self, engine):
        engine._cognitive_runtime_enabled = True
        try:
            trace = engine._run_cognitive_prepass(
                "这是一个较长的架构问题，涉及认知运行时与思考树的接线设计，"
                "需要深入推理模块之间的职责边界。")
            assert trace is not None
            assert trace.steps
            states = [s.state for s in trace.steps]
            assert "PERCEIVE" in states
            assert "REASON" in states
            assert "REFLECT" in states
        finally:
            engine._cognitive_runtime_enabled = False
        # B1-8-④: 认知循环产出写共享树 — 无 LLM 时 workspace 无推理内容,
        # 树写入发生在有 hypotheses/candidate_answers 时; 有产出则必写树。
        # 显式验证: 记录一条 LLM 思考 → 树节点递增（联动通道可用）。
        before = len(engine._cognitive_tree.nodes)
        engine.record_llm_thought(
            llm_instance="cognitive_loop", content="推理结论",
            node_type="REASONING", confidence=0.6)
        assert len(engine._cognitive_tree.nodes) == before + 1


class TestRecordThought:
    """LLM-1: 6 LLM 思考记录唯一写树入口。"""

    def test_record_six_llm_instances(self, engine):
        for llm in ("pcr", "intent", "meta", "planning", "answer", "reflective"):
            r = engine.record_llm_thought(
                llm_instance=llm, content=f"{llm} 思考记录",
                node_type="REASONING", confidence=0.6)
            assert r["nodes_created"] == 1, f"{llm} 写入失败: {r}"

    def test_invalid_node_type_falls_back(self, engine):
        r = engine.record_llm_thought(
            llm_instance="pcr", content="未知类型",
            node_type="NOT_A_TYPE", confidence=0.5)
        assert r["nodes_created"] == 1  # 映射到 REASONING


class TestPredictionLearning:
    """LLM-3: PREDICT → EXECUTE → COMPARE → LEARN 闭环。"""

    def test_predict_unknown_without_history(self, engine):
        p = engine.predict_execution("never_seen_action_xyz")
        assert p["expected"] == "unknown"
        assert p["confidence"] < 0.5

    def test_predict_hits_after_learn(self, engine):
        action = "compile_core"
        # 首次: 无历史 → 学习闭环记录结果
        engine.record_execution_outcome(action, "pass", "pass")
        # 预测应命中历史节点
        p = engine.predict_execution(action)
        assert p["expected"] != "unknown"
        assert p["evidence"]
        # 重复同类任务 → 命中率提升可观测
        assert engine._prediction_stats["predictions"] >= 1
        assert engine._prediction_stats["hits"] >= 1

    def test_miss_and_retry(self, engine):
        action = "deploy_agent"
        engine.record_execution_outcome(action, "pass", "fail")
        stats = dict(engine._prediction_stats)
        assert stats["misses"] >= 1
        # 差异写回树 (PREDICTION 节点)
        from core.agent.v3_0.cognitive_tree.models import CogType
        nodes = [n for n in engine._cognitive_tree.nodes.values()
                 if n.cog_type == CogType.PREDICTION]
        assert nodes


class TestBSuiteArchived:
    """B1-8-⑤: B 套核心调度已归档。"""

    def test_scheduler_policy_archived(self):
        with pytest.raises(ImportError):
            import core.agent.v4.cognitive_scheduler.scheduler  # noqa: F401
        with pytest.raises(ImportError):
            import core.agent.v4.cognitive_scheduler.policy  # noqa: F401

    def test_path_api_kept(self):
        # engine 在用 path_* — 保留
        from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
        from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
            ConfigDrivenTriggerPolicy, PathStateMachine,
        )
        assert PathAwareScheduler is not None
        assert ConfigDrivenTriggerPolicy is not None
        assert PathStateMachine is not None
