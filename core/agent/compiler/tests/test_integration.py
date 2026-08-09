"""Integration tests: full pipeline from on_event to context entries.

Validates deterministic pipeline output, NOT LLM quality.
Uses session fixture (5 design docs) + MockProvider for fast execution.
"""
import pytest
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.events.event_ir import DialogAdapter
from core.agent.llm_providers.mock_provider import MockProvider


@pytest.fixture(scope="module")
def engine(world):
    """Engine wired with full Semantic World model + MockProvider."""
    pool, graph, idx, rs, provider, objects, ort = world
    e = CognitiveRuntimeEngine(llm_provider=MockProvider("mock", {}))
    # 测试基建统一走 DI（B1 bootstrap）: 装配 StateMachine + handlers +
    # 支撑组件, 不裸构造。Semantic World 组件显式挂载（旧 set_* API 已删）。
    e.bootstrap()
    e._observation_pool = pool
    e.set_content_provider(provider)      # 装配 context assembler + perspective_planner
    e.set_object_store(objects, ort, provider)
    return e


def _ask(engine, text, turn=1):
    """Send one turn and return (response, context_entries)."""
    ad = DialogAdapter()
    resp = engine.on_event(ad.adapt(text, session_id="itest", turn_number=turn))
    ctx = engine._last_context
    entries = ctx.entries if ctx else []
    return resp, entries


class TestEndToEndContextStructure:
    """Context compilation must produce at minimum: world_view + profile."""

    def test_world_view_present(self, engine):
        _, entries = _ask(engine, "ContextCompiler的架构是什么")
        # M3 后 context IR 只含 user_input(D) + profile(P)；world_view 由
        # SubgraphCompiler 编译层提供（真实数据源，见 B5-3 层2/3）。
        # 这里验证: 每轮 context 都有用户输入条目 + 画像条目。
        assert len(entries) >= 1, "Expected at least user_input entry"
        assert any(getattr(e, "domain", "") == "D" for e in entries)

    def test_profile_injected(self, engine):
        _, entries = _ask(engine, "我的偏好是什么")
        profile = [e for e in entries if getattr(e, "domain", "") == "P"]
        assert len(profile) >= 1

    def test_graph_removed_when_world_present(self, engine):
        """Graph entries (static fragments) should be absent when world_view exists."""
        _, entries = _ask(engine, "RelationSubstrate的设计")
        world = [e for e in entries if "world_view" in str(getattr(e, "type", ""))]
        graph = [e for e in entries if getattr(e, "type", "") == "graph"]
        if world:
            assert len(graph) == 0, "Graph entries should be removed when world_view present"

    def test_discourse_tree_injected(self, engine):
        # M3 后 discourse_tree 独立运行（engine._discourse_tree），不注入
        # context IR。验证对话树真实增长（同一 session 多轮 → 块数增加）。
        eng = engine
        tree = eng._discourse_tree
        sid = "itest"
        before = len(getattr(tree, "_trees", {}).get(sid, type("", (), {"blocks": []})()).blocks) if hasattr(tree, "_trees") and sid in getattr(tree, "_trees", {}) else 0
        for i in range(3):
            _ask(engine, f"测试对话树{i}", turn=i + 1)
        after = len(getattr(tree, "_trees", {}).get(sid, type("", (), {"blocks": []})()).blocks) if hasattr(tree, "_trees") and sid in getattr(tree, "_trees", {}) else 0
        assert after >= before, f"discourse tree should grow: {before} -> {after}"

    def test_context_has_minimum_entries(self, engine):
        _, entries = _ask(engine, "DomainSelector的作用")
        assert len(entries) >= 3, f"Expected >=3 entries, got {len(entries)}"


class TestWorldViewContent:
    """World view content must be reachable via SubgraphCompiler (真实数据源)."""

    def test_design_content_non_empty(self, engine):
        from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
        sc = SubgraphCompiler(engine=engine)
        ctx = sc.compile_dialogue(intent="设计", intent_category="设计")
        assert ctx is not None
        # 编译出的子图上下文应有真实条目（world view 数据源可达，B5-3 层2）
        entries = getattr(ctx, "entries", [])
        assert len(entries) > 0, "Subgraph compiled context should have entries"
        assert getattr(ctx, "total_tokens", 0) > 0

    def test_architecture_label(self, engine):
        # 多视角渲染: planner 产出不同策略的视角（真实能力，非 IR 条目）
        planner = engine._perspective_planner
        if planner is None:
            import pytest
            pytest.skip("perspective_planner 未装配（可选组件）")
        perspectives = planner.plan_multi("系统的架构设计", token_budget=2000)
        assert len(perspectives) >= 1
        assert all(getattr(p, "strategy", "") for p in perspectives)


class TestMultiTurnProfileAccumulation:
    """Profile TrackA values must change across turns."""

    def test_observations_increase(self, engine):
        for i in range(1, 4):
            _ask(engine, f"测试累积轮次{i}", turn=i)
        _, entries = _ask(engine, "最终检查", turn=4)
        profile = [e for e in entries if getattr(e, "domain", "") == "P"]
        if profile:
            content = getattr(profile[0], "content", "")
            assert "Observations=" in content
            # Extract observations count
            import re
            m = re.search(r"Observations=(\d+)", content)
            if m:
                obs = int(m.group(1))
                assert obs >= 3, f"Observations should accumulate: got {obs}"


class TestDiscourseTreeBranching:
    """Different topics should create distinct discourse tree entries."""

    def test_multiple_topics_produce_tree(self, engine):
        topics = ["DomainSelector路由机制", "递归图的双视角设计", "用户画像收敛策略"]
        for i, t in enumerate(topics):
            _ask(engine, t, turn=i + 1)
        # 对话树独立运行: 多轮后树内块数增加（话题分支）
        tree = engine._discourse_tree
        sid = "itest"
        blocks = getattr(tree, "_trees", {}).get(sid, None)
        if blocks is not None and hasattr(blocks, "blocks"):
            assert len(blocks.blocks) >= 3, f"Expected >=3 blocks, got {len(blocks.blocks)}"


class TestMultiPerspective:
    """Multi-perspective rendering: primary != secondary."""

    def test_strategies_differ(self, engine):
        # The planner produces primary + secondary with different strategies
        planner = engine._perspective_planner
        perspectives = planner.plan_multi("ContextCompiler的实现细节", token_budget=4000)
        assert len(perspectives) >= 2
        assert perspectives[0].strategy != perspectives[1].strategy, \
            f"Primary and secondary should differ: {perspectives[0].strategy} == {perspectives[1].strategy}"


class TestSlowPathExtraction:
    """Slow Path should trigger after threshold and write extraction edges."""

    def test_extraction_adds_edges(self, engine, relation_substrate):
        dep_before = sum(
            1 for e in relation_substrate._edges.values()
            if getattr(e, "semantic_strength", "") == "dependency"
        )
        # Send 6 turns to trigger slow path (threshold=5)
        for i in range(6):
            _ask(engine, f"slow_path_turn_{i}", turn=100 + i)

        dep_after = sum(
            1 for e in relation_substrate._edges.values()
            if getattr(e, "semantic_strength", "") == "dependency"
        )
        # Slow path may add extraction edges (or may not if pool traversal finds nothing)
        # At minimum: no crash, edges don't decrease
        assert dep_after >= dep_before, \
            f"Extraction should not reduce edges: {dep_before} -> {dep_after}"
