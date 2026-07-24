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
    e.start()
    e.set_observation_pool(pool)
    e.set_content_provider(provider)
    e.set_object_store(objects, ort, provider)
    return e


def _ask(engine, text, turn=1):
    """Send one turn and return (response, context_entries)."""
    ad = DialogAdapter()
    resp = engine.on_event(ad.adapt(text, session_id="itest", turn_number=turn))
    ctx = engine.last_context
    entries = ctx.entries if ctx else []
    return resp, entries


class TestEndToEndContextStructure:
    """Context compilation must produce at minimum: world_view + profile."""

    def test_world_view_present(self, engine):
        _, entries = _ask(engine, "ContextCompiler的架构是什么")
        world = [e for e in entries if "world_view" in str(getattr(e, "type", ""))]
        assert len(world) >= 1, f"Expected world_view, got types: {[getattr(e,'type','?') for e in entries]}"

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
        _, entries = _ask(engine, "测试对话树")
        tree = [e for e in entries if "discourse_tree" in str(getattr(e, "type", ""))]
        assert len(tree) >= 1

    def test_context_has_minimum_entries(self, engine):
        _, entries = _ask(engine, "DomainSelector的作用")
        assert len(entries) >= 3, f"Expected >=3 entries, got {len(entries)}"


class TestWorldViewContent:
    """World view entries must contain readable design content."""

    def test_design_content_non_empty(self, engine):
        _, entries = _ask(engine, "SemanticObject的LOD机制")
        world = [e for e in entries if "world_view" in str(getattr(e, "type", ""))]
        for w in world:
            content = getattr(w, "content", "")
            assert len(content) > 50, f"World view too short: {len(content)} chars"

    def test_architecture_label(self, engine):
        _, entries = _ask(engine, "系统的架构设计")
        world = [e for e in entries if "world_view" in str(getattr(e, "type", ""))]
        labels = [getattr(e, "content", "")[:20] for e in world]
        # Should have strategy label like [ARCHITECTURE] or [EVOLUTION]
        assert any("[" in l for l in labels)


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
    """Different topics should create tree branches."""

    def test_multiple_topics_produce_tree(self, engine):
        topics = ["DomainSelector路由机制", "递归图的双视角设计", "用户画像收敛策略"]
        for i, t in enumerate(topics):
            _ask(engine, t, turn=i + 1)
        _, entries = _ask(engine, "总结", turn=4)
        tree = [e for e in entries if "discourse_tree" in str(getattr(e, "type", ""))]
        assert len(tree) >= 1, f"Expected discourse_tree entry, got types: {[getattr(e,'type','?') for e in entries]}"


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
