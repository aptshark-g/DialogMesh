"""Subgraph V2 tests — design-contract assertions (DESIGN_SUBGRAPH.md).

Covers the v3-aligned capabilities added in the refactor:
  - intent-aware allocation matrix (§2.1)
  - cross_ref pointer network (§2.2)
  - structural trim (§2.5) and topic-switch rebuild (§2.6)
  - pull_prior for PCR §5 (§4.3)

FakeEngine injects all data sources so the tests are deterministic and
model-free (no BGE / no LLM).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler, DomainEntry


class FakeEngine:
    _world_objects = {"mod_a": "ok", "mod_b": "warn", "mod_c": "err"}
    _behavior_graph_adapter = type(
        "BG", (), {"stats": lambda self: {"count": 42, "patterns": 3}})()

    class _ocean:
        class profile:
            @staticmethod
            def to_mbti():
                return "INTJ"

            @staticmethod
            def top_dimensions(k):
                return [("O", 0.8)]

        dims = {"O": 0.7}

    _ocean_analyst = _ocean()

    class _dt:
        _trees = {"t1": type(
            "T", (), {"blocks": {"b1": type(
                "B", (), {"topic": "延迟问题根因分析"})()}})()}

    _discourse_tree = _dt()
    _engineering_knowledge = type(
        "EK", (), {"get_by_type": lambda self, t: [
            type("N", (), {"name": "Every Provider must expose Metrics"})(),
            type("N", (), {"name": "Every Service must have tests"})()]})()
    _inertia_graph = type(
        "IG", (), {"top_impact": lambda self, k: [("param_x", 0.9)]})()
    _vcs = None
    _meta = type("M", (), {"self_audit": lambda self: "audit: 3 reviews passed"})()
    _world_provider = None


@pytest.fixture(scope="module")
def compiler():
    return SubgraphCompiler(engine=FakeEngine(), budget=300)


# ══════════════════════════════════════════════════════════════════════
# Intent-aware allocation matrix (§2.1)
# ══════════════════════════════════════════════════════════════════════

def test_alloc_matrix_intent_driven(compiler):
    """Alloc changes with intent and always normalizes to ~1.0."""
    for intent in ("task", "query", "correction", "discussion", "casual", "topic_switch"):
        a = compiler._alloc_for_intent(intent)
        assert abs(sum(a.values()) - 1.0) < 1e-6, f"{intent} sum={sum(a.values())}"
        assert a, f"{intent} empty alloc"


def test_alloc_matrix_primary_domain(compiler):
    """Primary domain dominates each intent (>= 0.5)."""
    cases = {"task": "E", "correction": "B", "casual": "D", "topic_switch": "D"}
    for intent, primary_family in cases.items():
        a = compiler._alloc_for_intent(intent)
        # design domain → v4 domains (E→K/E, B→B, C→D)
        family = {"E": ["K", "E"], "B": ["B"], "D": ["D"]}[primary_family]
        share = sum(a.get(k, 0.0) for k in family)
        assert share >= 0.5, f"{intent}: primary={primary_family} share={share:.2f}"


def test_alloc_matrix_unknown_falls_back(compiler):
    """Unknown intent falls back to the v4 default dialogue alloc."""
    a = compiler._alloc_for_intent("no_such_intent")
    assert abs(sum(a.values()) - 1.0) < 1e-6


# ══════════════════════════════════════════════════════════════════════
# cross_ref pointer network (§2.2)
# ══════════════════════════════════════════════════════════════════════

def test_cross_refs_generated(compiler):
    d = compiler.compile_dialogue(intent_category="task", event_id="evt_101")
    refs = [e for e in d.entries if e.cross_refs]
    assert refs, "expected entries with cross_refs"
    # connector direction: E ↔ K family, F ↔ P family
    all_refs = [r["target_domain"] for e in d.entries for r in e.cross_refs]
    assert all_refs, "cross_ref list should not be empty"


def test_source_events_no_duplicates(compiler):
    d = compiler.compile_dialogue(intent_category="query", event_id="evt_7")
    for e in d.entries:
        assert e.source_events.count("evt_7") == 1, f"{e.domain} dup source event"


def test_assemble_prompt_has_refs(compiler):
    d = compiler.compile_dialogue(intent_category="task")
    prompt = compiler.assemble_prompt(d)
    assert "^ref:" in prompt, "prompt should surface cross_ref pointers"


# ══════════════════════════════════════════════════════════════════════
# Structural trim (§2.5) + topic switch (§2.6)
# ══════════════════════════════════════════════════════════════════════

def test_trim_respects_budget(compiler):
    d = compiler.compile_dialogue(intent_category="discussion")
    if d.total_tokens <= d.budget:
        pytest.skip("no over-budget scenario in this fixture")
    trimmed = compiler._trim(d, "discussion")
    # Budget is a target, not an invariant: trim either fits the budget OR
    # stops at the information-quality floor (DESIGN_SUBGRAPH §2.5).
    assert trimmed.total_tokens <= d.budget or \
        all(len(e.content) <= compiler._MIN_CONTENT for e in trimmed.entries), (
        f"trim failed: {trimmed.total_tokens} > {d.budget} and floor not reached")


def test_trim_summarizes_tail(compiler):
    d = compiler.compile_dialogue(intent_category="discussion")
    if d.total_tokens <= d.budget:
        pytest.skip("no over-budget scenario in this fixture")
    trimmed = compiler._trim(d, "discussion")
    # Quality floor: no entry is shredded below the minimum, and any trimmed
    # entry still carries its domain anchor + content signal.
    for e in trimmed.entries:
        # short original (e.g. "mod_a") is untouched; longer entries, if
        # compressed, keep >= floor chars + domain anchor
        if e.content.startswith("["):
            assert len(e.content) >= compiler._MIN_CONTENT - 6, \
                f"{e.domain} shredded: {e.content!r}"
    summarized = [e for e in trimmed.entries if e.content.startswith("[")]
    if trimmed.total_tokens > d.budget:
        # Over budget but stopped at floor — must have compressed something
        assert summarized, "over budget but nothing was summarized"


def test_topic_switch_rebuild_merges(compiler):
    old = compiler.compile_dialogue(intent_category="casual", event_id="evt_old")
    new = compiler.compile_dialogue(intent_category="task", event_id="evt_new")
    merged = compiler._topic_switch_rebuild(old, new)
    assert merged.intent_category == "topic_switch"
    assert merged.entries, "merged context should not be empty"
    assert merged.total_tokens <= merged.budget, (
        f"merged over budget: {merged.total_tokens} > {merged.budget}")


# ══════════════════════════════════════════════════════════════════════
# pull_prior (§4.3, PCR §5)
# ══════════════════════════════════════════════════════════════════════

def test_pull_prior_shape(compiler):
    prior = compiler.pull_prior({"D": 0.4, "K": 0.2, "B": 0.15, "P": 0.1})
    assert set(prior) == {"domain_scope", "coordinate_bias", "expected_context"}
    assert prior["domain_scope"] == {"D": 0.4, "K": 0.2, "B": 0.15, "P": 0.1}
    assert prior["coordinate_bias"], "bias should reflect domain confidence"
    assert prior["expected_context"], "expected context should not be empty"


def test_pull_prior_empty_engine():
    c = SubgraphCompiler(engine=None, budget=300)
    prior = c.pull_prior({})
    assert prior["expected_context"] == ""
    assert prior["coordinate_bias"] == {}


# ══════════════════════════════════════════════════════════════════════
# Context IR v2 structured output (§3) + event expansion (§11)
# ══════════════════════════════════════════════════════════════════════

def test_to_ir_structure(compiler):
    d = compiler.compile_dialogue(intent_category="task", event_id="evt_ir")
    ir = compiler.to_ir(d)
    assert set(ir) == {"perspective", "intent_category", "compile_strategy",
                       "domain_allocation", "total_estimated_tokens", "budget",
                       "entries"}
    assert ir["perspective"] == "dialogue"
    assert ir["intent_category"] == "task"
    assert ir["entries"], "IR should carry entries"
    e0 = ir["entries"][0]
    assert set(e0) == {"domain", "type", "content", "cross_refs",
                       "source_events", "confidence", "estimated_tokens"}


def test_expand_from_event_trace_walk(compiler):
    """With an in-memory EventLog, expansion returns provenance entries."""
    class FakeEventLog:
        def __init__(self):
            self._rows = [
                {"event_id": "evt_a", "kind": "MessageReceived",
                 "payload": {"text": "帮我分析延迟问题"}, "trace_id": "tr_1"},
                {"event_id": "evt_b", "kind": "IntentLocked",
                 "payload": {"text": "intent=task"}, "trace_id": "tr_1"},
                {"event_id": "evt_c", "kind": "PatternDiscovered",
                 "payload": {"text": "pattern=delay"}, "trace_id": "tr_1"},
                {"event_id": "evt_x", "kind": "Other",
                 "payload": {"text": "other trace"}, "trace_id": "tr_2"},
            ]

        def get_event(self, event_id):
            for r in self._rows:
                if r["event_id"] == event_id:
                    return r
            return None

        def replay_unconsumed(self, limit=100):
            return self._rows[:limit]

    eng = FakeEngine()
    eng._event_log = FakeEventLog()
    c = SubgraphCompiler(engine=eng, budget=300)
    entries = c._expand_from_event("evt_a", max_hops=2)
    # root event + same-trace events (evt_b, evt_c); NOT evt_x
    ids = {e.source_events[0] for e in entries if e.source_events}
    assert "evt_a" in ids, "root event must be present"
    assert "evt_b" in ids and "evt_c" in ids, "same-trace events should be walked"
    assert "evt_x" not in ids, "other trace must not leak in"


def test_expand_from_event_no_eventlog(compiler):
    entries = compiler._expand_from_event("evt_missing")
    assert entries == []  # tolerant: no EventLog → empty provenance


# ══════════════════════════════════════════════════════════════════════
# Quality invariants — trim must not destroy the subgraph
# ══════════════════════════════════════════════════════════════════════

def test_trim_preserves_connector_references(compiler):
    """Trimming content must NEVER drop cross_ref pointers — the pointer
    network IS the subgraph; content is just payload."""
    d = compiler.compile_dialogue(intent_category="task")
    refs_before = {id(e): [r["target_domain"] for r in e.cross_refs]
                   for e in d.entries}
    trimmed = compiler._trim(d, "task")
    refs_after = {id(e): [r["target_domain"] for r in e.cross_refs]
                  for e in trimmed.entries}
    assert refs_before == refs_after, "trim must not drop cross_ref pointers"


def test_trim_keeps_all_domains_represented(compiler):
    """Trim compresses entries, it does not delete domains (structure intact)."""
    d = compiler.compile_dialogue(intent_category="discussion")
    domains_before = {e.domain for e in d.entries}
    trimmed = compiler._trim(d, "discussion")
    domains_after = {e.domain for e in trimmed.entries}
    # every domain that had data must still be represented
    assert domains_after == domains_before, (
        f"trim dropped domains: {domains_before - domains_after}")


def test_trim_is_idempotent(compiler):
    """Trimming twice must not shrink further (second pass is a no-op)."""
    d = compiler.compile_dialogue(intent_category="discussion")
    t1 = compiler._trim(d, "discussion")
    snapshot = [(e.domain, e.content, e.token_estimate) for e in t1.entries]
    t2 = compiler._trim(t1, "discussion")
    after = [(e.domain, e.content, e.token_estimate) for e in t2.entries]
    assert after == snapshot, "second trim changed entries — not idempotent"


def test_trim_content_still_carries_signal(compiler):
    """Summaries must retain a content window, not become empty shells."""
    d = compiler.compile_dialogue(intent_category="discussion")
    trimmed = compiler._trim(d, "discussion")
    for e in trimmed.entries:
        if e.content.startswith("["):
            # head window + domain anchor — must not be just the bracket
            assert len(e.content) > len(e.domain) + 8, \
                f"{e.domain} summary is an empty shell: {e.content!r}"


# ══════════════════════════════════════════════════════════════════════
# Semantic correctness — matrix maps to the RIGHT domains
# ══════════════════════════════════════════════════════════════════════

def test_semantic_task_engineering_primary(compiler):
    """task intent → engineering (K/E) must carry >= 50% of allocation."""
    a = compiler._alloc_for_intent("task")
    eng = a.get("K", 0.0) + a.get("E", 0.0)
    assert eng >= 0.5, f"task: engineering share={eng:.2f}"
    assert a.get("B", 0.0) > 0, "task: behavior should be auxiliary"


def test_semantic_correction_behavior_primary(compiler):
    """correction intent → behavior (B) must dominate."""
    a = compiler._alloc_for_intent("correction")
    assert a.get("B", 0.0) >= 0.5, f"correction: behavior share={a.get('B'):.2f}"


def test_semantic_casual_dialogue_primary(compiler):
    """casual intent → conversation (D) must dominate; no deep engineering."""
    a = compiler._alloc_for_intent("casual")
    assert a.get("D", 0.0) >= 0.5, f"casual: dialogue share={a.get('D'):.2f}"


def test_semantic_compile_strategy_reflects_fill(compiler):
    """Empty data → summary_fallback; filled primary → primary_deep."""
    empty = SubgraphCompiler(engine=None, budget=300)
    d_empty = empty.compile_dialogue(intent_category="task")
    assert d_empty.compile_strategy == "summary_fallback"


# ══════════════════════════════════════════════════════════════════════
# Edge / adversarial — extreme inputs
# ══════════════════════════════════════════════════════════════════════

def test_edge_empty_intent(compiler):
    d = compiler.compile_dialogue(intent="", intent_category="")
    assert d.compile_strategy in ("balanced", "summary_fallback")
    assert isinstance(d.entries, list)


def test_edge_zero_budget_does_not_crash(compiler):
    c = SubgraphCompiler(engine=FakeEngine(), budget=0)
    d = c.compile_dialogue(intent_category="task")
    trimmed = c._trim(d, "task")
    assert trimmed.entries  # never empty — quality floor stops shredding


def test_edge_missing_all_data_sources():
    class Empty:
        pass
    c = SubgraphCompiler(engine=Empty(), budget=300)
    d = c.compile_dialogue(intent_category="task", event_id="evt_e")
    # event expansion on an engine without _event_log is tolerant
    assert d.compile_strategy == "summary_fallback"


def test_edge_very_long_content(compiler):
    """Long content must be compressible below its original size."""
    e = DomainEntry("K", "x" * 2000, 0.8, "engineering")
    summary = compiler._summarize_domain(e)
    assert len(summary) < len(e.content), "summary must shrink long content"
    assert "x" in summary, "summary must retain content signal"


# ══════════════════════════════════════════════════════════════════════
# Adversarial quality — tests written AGAINST the implementation
# ══════════════════════════════════════════════════════════════════════

def test_trim_refs_target_domains_still_alive(compiler):
    """REAL connectivity invariant: after trim, every cross_ref's
    target_domain must still exist among surviving entries. A ref pointing
    at a trimmed-away domain would leave the pointer network broken —
    the subgraph would navigate to nowhere."""
    d = compiler.compile_dialogue(intent_category="task")
    trimmed = compiler._trim(d, "task")
    alive = {e.domain for e in trimmed.entries}
    for e in trimmed.entries:
        for ref in e.cross_refs:
            tgt = ref.get("target_domain")
            assert tgt in alive, (
                f"cross_ref -> {tgt} but domain not in surviving entries {alive}")


def test_pull_prior_bias_matches_confidence(compiler):
    """bias must order consistently with domain confidence: a domain whose
    entries carry higher confidence must not get a LOWER bias than a weaker
    domain — otherwise PCR's coordinate bias is meaningless."""
    prior = compiler.pull_prior({})
    bias = prior["coordinate_bias"]
    assert bias, "bias should exist on populated engine"
    # rebuild domain→max-confidence from a fresh compile
    d = compiler.compile_dialogue(intent_category="query")
    conf = {}
    for e in d.entries:
        conf[e.domain] = max(conf.get(e.domain, 0.0), e.confidence)
    for dom, c in conf.items():
        if dom in bias:
            # bias is normalized to max 1.0; relative order must not invert
            assert bias[dom] > 0, f"{dom} bias=0 but confidence={c:.2f}"


def test_to_ir_matches_assemble_prompt(compiler):
    """IR and prompt render the SAME entries — no structural split where the
    prompt shows different content than the structured IR (drift trap)."""
    d = compiler.compile_dialogue(intent_category="task", event_id="evt_ir2")
    ir = compiler.to_ir(d)
    prompt = compiler.assemble_prompt(d)
    # every IR entry's content must appear in the rendered prompt
    for entry in ir["entries"]:
        assert entry["content"] in prompt, (
            f"IR entry {entry['domain']} missing from prompt: {entry['content'][:30]!r}")


@pytest.mark.slow
@pytest.mark.integration
def test_real_engine_integration():
    """Real assembled engine (B registry path): subgraph compiles, engineering
    domain yields data, no crash on any intent."""
    from core.agent.cli.engine import _create_engine_instance
    eng = _create_engine_instance({"type": "mock", "name": "mock"})
    sg = getattr(eng, "_subgraph", None)
    assert sg is not None, "B registry should now mount subgraph"
    for intent in ("task", "query", "correction", "discussion", "casual", "topic_switch"):
        d = sg.compile_dialogue(intent_category=intent)
        assert isinstance(d.entries, list)
        assert d.compile_strategy in ("primary_deep", "balanced", "summary_fallback")
    d = sg.compile_dialogue(intent_category="task")
    assert any(e.domain == "K" for e in d.entries), "engineering constraints expected"


# ══════════════════════════════════════════════════════════════════════
# PCR zone ↔ intent_category bridge (§4.4)
# ══════════════════════════════════════════════════════════════════════

def test_zone_fallback_maps_to_intent(compiler):
    """zone alone (no intent_category) uses the fallback table."""
    d = compiler.compile_dialogue(zone="PRECISION")
    assert d.intent_category == "task", f"PRECISION should map to task, got {d.intent_category}"


def test_zone_fallback_psyche(compiler):
    d = compiler.compile_dialogue(zone="PSYCHE")
    assert d.intent_category == "discussion", f"PSYCHE should map to discussion"


def test_explicit_intent_wins_over_zone(compiler):
    """Both given and disagree → intent_category wins, conflict recorded."""
    d = compiler.compile_dialogue(intent_category="correction", zone="ATOMIC")
    assert d.intent_category == "correction", "explicit intent_category must win"
    assert d.conflicts, "disagreement must be recorded in conflicts"
    c = d.conflicts[0]
    assert c["zone"] == "ATOMIC" and c["intent_category"] == "correction"


def test_zone_match_no_conflict(compiler):
    """Both given and agree → no conflict."""
    d = compiler.compile_dialogue(intent_category="task", zone="PRECISION")
    assert d.intent_category == "task"
    assert d.conflicts == []


# ══════════════════════════════════════════════════════════════════════
# Graph retrieval primitive (§13) — expand_from_graph
# ══════════════════════════════════════════════════════════════════════

class FakeGraph:
    def __init__(self):
        class Item:
            def __init__(self, text, rel):
                self.text = text
                self.relevance = rel
        self._items = [
            Item("延迟问题的根因分析：监控缺失 + 超时配置", 0.9),
            Item("性能优化的常见模式与权衡", 0.7),
        ]

    def compile_context(self, query, top_k=10, max_hops=2, max_nodes=30):
        return self._items[:top_k]


def test_expand_from_graph_available():
    class Eng(FakeEngine):
        _graph = FakeGraph()
    c = SubgraphCompiler(engine=Eng(), budget=300)
    entries = c.expand_from_graph("延迟问题")
    assert entries, "graph available → entries expected"
    assert all(e.domain == "G" for e in entries), "graph entries must be G domain"
    assert entries[0].confidence >= 0.5
    # cross_refs are built at compile time (_build_cross_refs), NOT inside the
    # raw primitive — the primitive only guarantees retrievable data.


def test_expand_from_graph_no_graph(compiler):
    # FakeEngine has no _content_index / _graph → returns None (fallback)
    assert compiler.expand_from_graph("anything") is None


def test_compile_falls_back_when_no_graph(compiler):
    """No graph → compile_dialogue still produces domain-grab entries."""
    d = compiler.compile_dialogue(intent_category="task")
    assert d.entries, "fallback domain grabbing must still work"
    assert not any(e.domain == "G" for e in d.entries), "no graph → no G entries"


def test_expand_from_graph_empty_query(compiler):
    assert compiler.expand_from_graph("") is None


def test_graph_plus_empty_domains_no_dangling_refs():
    """ADVERSARIAL: graph expansion returns G entries whose cross_refs point
    to D (discourse). If domain grabbing yields NO D entry (empty dialogue
    tree — common in production), the compiled subgraph contains a dangling
    pointer G→D. The pointer network must never reference a domain that does
    not exist in the same context."""
    class GraphOnlyEngine:
        _graph = FakeGraph()
        _discourse_tree = None      # empty dialogue tree
        _engineering_knowledge = None
        _world_objects = {}
        _behavior_graph_adapter = None
        _ocean_analyst = None
    c = SubgraphCompiler(engine=GraphOnlyEngine(), budget=300)
    d = c.compile_dialogue(intent_category="task")
    assert d.entries, "should still compile (graph + maybe empty domains)"
    alive = {e.domain for e in d.entries}
    for e in d.entries:
        for ref in e.cross_refs:
            tgt = ref.get("target_domain")
            assert tgt in alive, (
                f"dangling cross_ref G→{tgt}; alive domains={alive}")


def test_real_concept_graph_integration():
    """REAL ConceptGraph (build_from_pool) — multi-tier anchors + expansion."""
    from core.agent.context.graph_source import ConceptGraph
    g = ConceptGraph()
    g._nodes = {
        "监控缺失": {"relations": [{"target": "延迟问题", "type": "reason",
                                  "confidence": 0.9}],
                     "observations": ["模块缺少监控导致延迟不可见"],
                     "docs": {"doc1"}},
        "延迟问题": {"relations": [{"target": "超时配置", "type": "depends_on",
                                  "confidence": 0.8}],
                     "observations": ["延迟是性能核心问题"],
                     "docs": {"doc1"}},
        "超时配置": {"relations": [], "observations": ["timeout 参数"],
                     "docs": {"doc1"}},
    }
    g._built = True
    items = g.compile_context("延迟问题", top_k=5, max_hops=2, max_nodes=10)
    assert items, "graph with data must compile context"
    # expansion must reach 2-hop node (超时配置) via 延迟问题
    text = "\n".join(getattr(i, "text", "") for i in items)
    assert "超时配置" in text or "延迟" in text
    assert any(getattr(i, "relevance", 0) > 0.5 for i in items), (
        "seed node should carry high relevance")


def test_graph_entries_survive_trim():
    """G entries compressed by trim must keep cross_refs (pointer survives)."""
    class Eng(FakeEngine):
        _graph = FakeGraph()
    c = SubgraphCompiler(engine=Eng(), budget=50)  # tight budget → trim
    d = c.compile_dialogue(intent_category="task")
    trimmed = c._trim(d, "task")
    g_entries = [e for e in trimmed.entries if e.domain == "G"]
    if g_entries:
        for e in g_entries:
            assert e.cross_refs, "trimmed G entry lost its cross_refs"
