"""Subgraph Compiler — cross-chain context assembly with dual perspectives.

Design: BUSINESS_CHAIN_10
Two perspectives sharing one compiler:
  dialogue_subgraph: for LLM response generation (narrow+deep)
  meta_subgraph:     for meta-cognition review (wide+shallow)

Data sources: discourse tree, behavior chain, association chain, 
              engineering chain, profile/inertia, version control.
"""
from __future__ import annotations
import json, os, time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DomainEntry:
    domain: str
    content: str
    confidence: float
    source: str
    token_estimate: int = 0
    cross_refs: List[Dict[str, Any]] = field(default_factory=list)
    source_events: List[str] = field(default_factory=list)


@dataclass
class SubgraphContext:
    perspective: str          # "dialogue" | "meta"
    entries: List[DomainEntry]
    total_tokens: int
    budget: int
    domains: Dict[str, float]  # domain → budget allocation
    compile_strategy: str = "balanced"   # primary_deep | balanced | summary_fallback
    intent_category: str = "query"
    conflicts: List[Dict[str, Any]] = field(default_factory=list)  # zone vs intent disagreements


class SubgraphCompiler:
    """Compiles cross-domain context for two perspectives.
    
    Perspective 1 — dialogue_subgraph:
      Purpose: provide context for LLM response generation
      Style: narrow+deep — focuses on current topic with high-quality detail
      Domains: D(35%) + K(20%) + E(5%) + B(15%) + R(10%) + P(10%) + F(5%)
    
    Perspective 2 — meta_subgraph:
      Purpose: provide context for meta-cognition review/retrospection
      Style: wide+shallow — covers multiple chains, summary-level evidence
      Domains: V(25%) + E(30%) + M(15%) + I(15%) + P(10%) + Q(5%)
    """

    def __init__(self, engine=None, budget: int = 2000):
        self._engine = engine
        self._budget = budget
        self._config: Dict[str, Any] = {}
        self._format = "json"   # B5-3-P3: 层2 给 LLM 的形态（json/xml/markdown/natural）
        self._load_config()

    # ── Config (DESIGN_SUBGRAPH §6) ──

    def _load_config(self):
        """Lazy-load config/subgraph_dimensions.yaml (intent matrix, trim)."""
        from pathlib import Path
        try:
            cfg_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "subgraph_dimensions.yaml"
            import yaml
            with open(cfg_path, "r", encoding="utf-8") as fh:
                self._config = (yaml.safe_load(fh) or {}).get("subgraph", {})
        except Exception as exc:
            logger.debug("subgraph_dimensions.yaml not loaded: %s", exc)
            self._config = {}

    def _alloc_for_intent(self, intent_category: str) -> Dict[str, float]:
        """Design-domain alloc from intent matrix → v4 grab-domain weights.

        Matrix rows: {primary, aux1, aux2} (design domains C/E/B/P/K). Weights
        default 60/25/15. Returns v4-domain alloc normalized to sum 1.0.
        """
        matrix = self._config.get("intent_matrix", {})
        row = matrix.get(intent_category)
        weights = self._config.get("alloc_weights", {"primary": 0.60, "aux1": 0.25, "aux2": 0.15})
        domain_map = self._config.get("domain_map", {})
        if not row:
            # fallback: v4 default dialogue alloc (query-like)
            return {"D": 0.35, "K": 0.20, "E": 0.05, "B": 0.15, "R": 0.10, "P": 0.10, "F": 0.05}

        alloc: Dict[str, float] = {}
        for role, dname in (("primary", row.get("primary")),
                            ("aux1", row.get("aux1")),
                            ("aux2", row.get("aux2"))):
            if not dname:
                continue
            w = weights.get(role, 0.0)
            targets = domain_map.get(dname, [dname])
            share = w / max(1, len(targets))
            for t in targets:
                alloc[t] = alloc.get(t, 0.0) + share
        # normalize
        total = sum(alloc.values()) or 1.0
        return {k: v / total for k, v in alloc.items()}

    def _compile_strategy(self, alloc: Dict[str, float], entries: List[DomainEntry],
                          budget: int) -> str:
        """Choose strategy by actual fill: primary_deep | balanced | summary_fallback."""
        filled = sum(e.token_estimate or len(e.content) // 2 for e in entries)
        if filled <= 0:
            return "summary_fallback"
        primary_share = max(alloc.values()) if alloc else 0
        if primary_share >= 0.5 and filled <= budget:
            return "primary_deep"
        return "balanced"

    # ── Perspective 1: Dialogue Subgraph ──

    def _resolve_intent_category(self, intent_category: str = None,
                                 zone: str = None) -> str:
        """Bridge PCR zone → intent_category (§4.4). Primary: explicit
        intent_category. Fallback: zone_fallback table from YAML. When both
        are given and disagree, the explicit category wins and the conflict
        is surfaced to the caller (recorded by compile_dialogue)."""
        fallback = self._config.get("zone_fallback", {})
        mapped = fallback.get(zone) if zone else None
        if intent_category and zone and mapped and mapped != intent_category:
            return intent_category, {"zone": zone, "intent_category": intent_category,
                                     "mapped": mapped, "resolved": intent_category}
        resolved = intent_category or mapped or "query"
        return resolved, None

    def compile_dialogue(self, intent: str = "general_query",
                         intent_category: str = None,
                         zone: str = None,
                         extra_budget: int = 0,
                         event_id: str = None) -> SubgraphContext:
        """Compile context for LLM response generation.

        intent_category drives the intent-aware domain matrix (DESIGN_SUBGRAPH
        §2.1); alloc is computed from config, not hardcoded. event_id, when
        provided, seeds cross_refs (DESIGN_SUBGRAPH §2.2).

        zone (PCR output, optional): used ONLY as fallback for
        intent_category via the zone_fallback table (§4.4). When both are
        given and disagree, intent_category wins and the conflict is recorded.
        """
        resolved, conflict = self._resolve_intent_category(intent_category, zone)
        intent_category = resolved
        budget = self._budget + extra_budget
        alloc = self._alloc_for_intent(intent_category)
        entries: List[DomainEntry] = []

        eng = self._engine
        if not eng:
            return SubgraphContext("dialogue", entries, 0, budget, alloc,
                                   "summary_fallback", intent_category,
                                   [conflict] if conflict else [])

        # Event-driven provenance (DESIGN_SUBGRAPH §11): when an event_id is
        # provided, attach trace entries BEFORE domain grabbing so the final
        # context carries the chain-of-origin alongside domain data.
        if event_id:
            entries = self._expand_from_event(event_id)

        # Graph retrieval primitive (§13): when a ConceptGraph is available,
        # expand from it FIRST (multi-tier anchors + edge expansion). If the
        # graph is unavailable, this returns None and we fall through to
        # domain grabbing below.
        if not entries:
            graph_entries = self.expand_from_graph(intent)
            if graph_entries:
                entries = graph_entries

        # D: Discourse tree (current topic + related blocks)
        dt = getattr(eng, '_discourse_tree', None)
        if dt:
            trees = getattr(dt, '_trees', {})
            for tree_id, tree in list(trees.items())[:1]:
                blocks = getattr(tree, 'blocks', {})
                for bid, block in list(blocks.items())[:5]:
                    topic = getattr(block, 'topic', '')[:200]
                    if topic:
                        entries.append(DomainEntry("D", topic, 0.8, "discourse_tree",
                                                   len(topic)//2,
                                                   source_events=[event_id] if event_id else []))

        # K: Engineering constraints
        ek = getattr(eng, '_engineering_knowledge', None)
        if ek and hasattr(ek, 'get_by_type'):
            try:
                from core.agent.engineering.models import KnowledgeType
                for n in ek.get_by_type(KnowledgeType.CONSTRAINT)[:3]:
                    entries.append(DomainEntry("K", str(getattr(n, 'name', '?'))[:200], 0.8, "engineering", 50))
            except Exception: pass

        # E: Engineering module status
        objects = getattr(eng, '_world_objects', {})
        for name in list(objects.keys())[:3]:
            entries.append(DomainEntry("E", name[:100], 0.6, "world_objects", 30))

        # B: Behavior signals
        bg = getattr(eng, '_behavior_graph_adapter', None)
        if bg and hasattr(bg, 'stats'):
            try:
                stats = bg.stats() if callable(bg.stats) else {}
                s = str(stats)[:200]
                if s: entries.append(DomainEntry("B", s, 0.5, "behavior_graph", len(s)//2))
            except Exception: pass

        # P: Profile summary
        ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
        if ocean:
            top = ocean.top_dimensions(3) if hasattr(ocean, 'top_dimensions') else []
            mbti = ocean.to_mbti() if hasattr(ocean, 'to_mbti') else "?"
            entries.append(DomainEntry("P", f"MBTI≈{mbti} | top={top}", 0.7, "ocean_profile", 40))

        # F: OCEAN feedback
        if ocean:
            dims = getattr(ocean, 'dims', {})
            entries.append(DomainEntry("F", str(dict(list(dims.items())[:5]))[:200], 0.6, "ocean_dims", 60))

        entries = self._build_cross_refs(entries, event_id)
        strategy = self._compile_strategy(alloc, entries, budget)
        return SubgraphContext("dialogue", entries, self._count_tokens(entries), budget, alloc,
                               strategy, intent_category,
                               [conflict] if conflict else [])

    # ── Perspective 2: Meta Subgraph ──

    def compile_meta(self, review_target: str = "", extra_budget: int = 0) -> SubgraphContext:
        """Compile context for meta-cognition review."""
        budget = self._budget + extra_budget
        alloc = {"V": 0.25, "E": 0.30, "M": 0.15, "I": 0.15, "P": 0.10, "Q": 0.05}
        entries: List[DomainEntry] = []

        eng = self._engine
        if not eng:
            return SubgraphContext("meta", entries, 0, budget, alloc,
                                   "summary_fallback", "review")

        # V: Version diff
        vcs = getattr(eng, '_vcs', None)
        if vcs and review_target:
            try:
                for cat in ["parameters", "rules", "profile"]:
                    store = vcs.store(cat)
                    latest = store.latest(review_target)
                    if latest:
                        entries.append(DomainEntry("V", str(latest.diff_summary)[:200], 0.9,
                                                   "version_control", 80))
            except Exception as exc:
                logger.debug("V-domain fetch failed: %s", exc)
        elif review_target:
            entries.append(DomainEntry("V", f"vcs unavailable; target={review_target[:80]}",
                                       0.3, "version_control", 30))

        # E: Multi-chain evidence
        # Association chain
        rs = getattr(getattr(eng, '_world_provider', None), 'relation_substrate', None)
        if rs and hasattr(rs, 'query'):
            edges = rs.query()[:3] if callable(getattr(rs, 'query', None)) else []
            for e in edges:
                s = f"{getattr(e,'source','?')}→{getattr(e,'target','?')} strength={getattr(e,'semantic_strength','?')}"
                entries.append(DomainEntry("E", s[:150], 0.6, "relation_substrate", 40))

        # M: Meta operation history
        meta = getattr(eng, '_meta', None)
        if meta:
            audit = meta.self_audit()
            entries.append(DomainEntry("M", str(audit)[:200], 0.8, "meta_self_audit", 60))

        # I: Inertia impact (real data when available)
        inertia = getattr(eng, '_inertia_graph', None)
        if inertia and hasattr(inertia, 'top_impact'):
            try:
                top = inertia.top_impact(3)
                entries.append(DomainEntry("I", str(top)[:200], 0.7, "inertia_graph", 40))
            except Exception as exc:
                logger.debug("I-domain fetch failed: %s", exc)
                entries.append(DomainEntry("I", "inertia: unavailable", 0.3, "inertia_graph", 20))
        else:
            entries.append(DomainEntry("I", "inertia: unavailable", 0.3, "inertia_graph", 20))

        # P: Profile summary
        ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
        if ocean:
            mbti = ocean.to_mbti() if hasattr(ocean, 'to_mbti') else "?"
            entries.append(DomainEntry("P", f"MBTI≈{mbti}", 0.7, "ocean_profile", 20))

        # Q: Review target detail
        if review_target:
            entries.append(DomainEntry("Q", review_target[:200], 0.9, "review_target", 40))

        entries = self._build_cross_refs(entries)
        strategy = self._compile_strategy(alloc, entries, budget)
        return SubgraphContext("meta", entries, self._count_tokens(entries), budget, alloc,
                               strategy, "review")

    # ── Helpers ──

    def _count_tokens(self, entries: List[DomainEntry]) -> int:
        return sum(e.token_estimate or len(e.content) // 2 for e in entries)

    def assemble_prompt(self, ctx: SubgraphContext) -> str:
        """Convert subgraph context to LLM prompt format."""
        lines = [f"[Context — {ctx.perspective} perspective]"]
        for e in ctx.entries:
            lines.append(f"  [{e.domain}] {e.content}")
            for ref in e.cross_refs:
                lines.append(f"    ^ref: {ref.get('target_domain','?')}.{ref.get('target_event_id','')} = {ref.get('note','')}")
        return "\n".join(lines)

    def to_ir(self, ctx: SubgraphContext) -> Dict[str, Any]:
        """Context IR v2 structured output (v3 §7, DESIGN_SUBGRAPH §3).

        Language-neutral structure: perspective, intent_category,
        compile_strategy, domain_allocation, and entries with cross_refs /
        source_events / confidence / estimated_tokens. Serializers render
        this to provider-specific prompt formats.
        """
        return {
            "perspective": ctx.perspective,
            "intent_category": ctx.intent_category,
            "compile_strategy": ctx.compile_strategy,
            "domain_allocation": ctx.domains,
            "total_estimated_tokens": ctx.total_tokens,
            "budget": ctx.budget,
            "entries": [
                {
                    "domain": e.domain,
                    "type": e.source,
                    "content": e.content,
                    "cross_refs": e.cross_refs,
                    "source_events": e.source_events,
                    "confidence": e.confidence,
                    "estimated_tokens": e.token_estimate,
                }
                for e in ctx.entries
            ],
        }

    # ── B5-3-P3 serializer 家族（层2 给 LLM 的形态）──────────── #

    def set_format(self, fmt: str) -> Dict[str, Any]:
        """选择层2 序列化形态（json/xml/markdown/natural）。"""
        from core.agent.v4.cognitive.serializers import normalize_format
        self._format = normalize_format(fmt)
        return {"format": self._format,
                "available": ["json", "xml", "markdown", "natural"]}

    def get_format(self) -> Dict[str, Any]:
        return {"format": self._format,
                "available": ["json", "xml", "markdown", "natural"]}

    def serialize(self, ctx_or_ir, fmt: str = None) -> Dict[str, Any]:
        """统一渲染入口: 接受 SubgraphContext 或 IR dict。

        B5-3 验收②: 用户编辑后 LLM 消费的是编辑后的形态（层2 = 层1 投影）。
        """
        from core.agent.v4.cognitive.serializers import serialize as _ser
        if isinstance(ctx_or_ir, SubgraphContext):
            ir = self.to_ir(ctx_or_ir)
        elif isinstance(ctx_or_ir, dict):
            ir = ctx_or_ir
        else:
            return {"format": "json", "text": "", "tokens": 0, "error": "unsupported"}
        return _ser(ir, fmt or self._format)

    # ── Cross-domain references (DESIGN_SUBGRAPH §2.2) ──

    def _build_cross_refs(self, entries: List[DomainEntry],
                          event_id: str = None) -> List[DomainEntry]:
        """Attach cross_ref pointers between entries that share a source or
        a domain family (conversation/behavior/profile/engineering). When
        event_id is provided, every entry links back to it as source event.
        """
        if len(entries) < 2:
            if event_id and entries and event_id not in entries[0].source_events:
                entries[0].source_events.append(event_id)
            return entries

        family = {"D": "conversation", "C": "conversation",
                  "B": "behavior", "R": "association",
                  "K": "engineering", "E": "engineering",
                  "P": "profile", "F": "profile",
                  "G": "graph", "Q": "review",
                  "V": "version", "M": "meta", "I": "inertia", "Q": "review"}
        seen: Dict[str, str] = {}
        graph_refs = False
        for e in entries:
            fam = family.get(e.domain, e.domain)
            if fam in seen and seen[fam] != e.domain:
                e.cross_refs.append({
                    "target_domain": seen[fam],
                    "target_event_id": event_id or "ctx",
                    "note": f"related to {seen[fam]} domain",
                })
            else:
                seen[fam] = e.domain
            if e.domain == "G":
                graph_refs = True
            if event_id and event_id not in e.source_events:
                e.source_events.append(event_id)
        # Graph knowledge (G) serves every domain: link it to the FIRST
        # surviving non-G domain so the pointer always targets something that
        # exists in this context (no dangling refs, §13).
        if graph_refs:
            targets = [e for e in entries if e.domain != "G"]
            if targets:
                anchor = targets[0].domain
                for e in entries:
                    if e.domain == "G" and not e.cross_refs:
                        e.cross_refs.append({
                            "target_domain": anchor,
                            "target_event_id": event_id or "graph",
                            "note": "graph knowledge relevant across domains",
                        })
        return entries

    # ── Structural trim (DESIGN_SUBGRAPH §2.5, v3 §11.3) ──

    # Minimum content length a trimmed entry may keep — below this we stop
    # compressing: further shrinking destroys the information the subgraph
    # exists to carry (quality floor, not budget obsession).
    _MIN_CONTENT = 24

    def _trim(self, ctx: SubgraphContext, intent_category: str = "query") -> SubgraphContext:
        """Four-round trim when over budget. Keeps subgraph connectivity and
        an information-quality floor:
        1) capacitance sort (low-confidence tail) → 2) structure protect
        (connectors de-prioritized, not excluded — compressing content keeps
        the cross_ref pointer, so connectivity is preserved) → 3) recency fix
        (new nodes spared) → 4) summary compression per domain.

        Rounds repeat until within budget OR every entry has reached the
        quality floor (_MIN_CONTENT). If the floor is hit while still over
        budget, we STOP — the budget is mis-configured for the intent, and
        shredding entries further would lose the semantics (v3 §10: budget is
        a user-tunable variable, not an invariant).
        """
        if ctx.total_tokens <= ctx.budget:
            return ctx

        cfg = self._config.get("trim", {})
        candidate_ratio = cfg.get("candidate_ratio", 0.3)
        between_threshold = cfg.get("betweenness_threshold", 0.6)

        entries = list(ctx.entries)
        # Re-estimate tokens from content before trimming: several domains
        # carry hardcoded token_estimate (e.g. F=60 with content "{}") that
        # disagrees with content length.
        for e in entries:
            if e.token_estimate > 0:
                est = max(2, len(e.content) // 2)
                if abs(e.token_estimate - est) > 8:
                    e.token_estimate = est
        ctx.total_tokens = self._count_tokens(entries)

        ratio = candidate_ratio
        while (ctx.total_tokens > ctx.budget and ratio < 1.0 and len(entries) > 1
               and any(len(e.content) > self._MIN_CONTENT for e in entries)):
            # Round 1: capacitance — low-confidence tail are candidates
            ranked = sorted(entries, key=lambda e: (e.confidence, len(e.content)))
            n_candidates = max(1, int(len(ranked) * ratio))
            candidates = ranked[:n_candidates]

            # Round 2: structure protect — connectors are de-prioritized
            # (compressed LAST), but never excluded: content shrinks while
            # cross_refs stay attached, so the pointer network survives.
            max_refs = max((len(e.cross_refs) for e in entries), default=0)
            connectors = [e for e in candidates
                          if max_refs > 0 and len(e.cross_refs) / max_refs >= between_threshold]
            candidates = [e for e in candidates if e not in connectors]
            ordered = candidates + connectors

            # Round 3: recency fix — entries with source_events are spared
            ordered = [e for e in ordered if not e.source_events] + \
                      [e for e in ordered if e.source_events]

            # Round 4: summary compression (only shrink; skip already-tiny)
            compressed = False
            for e in ordered:
                if len(e.content) <= self._MIN_CONTENT:
                    continue  # quality floor reached — keep the semantics
                new_content = self._summarize_domain(e)
                if len(new_content) >= len(e.content):
                    continue  # summary must shrink; keep original
                e.content = new_content
                e.token_estimate = len(e.content) // 2
                e.confidence = max(0.1, e.confidence * 0.7)
                compressed = True
                if (self._count_tokens(entries) <= ctx.budget
                        or all(len(x.content) <= self._MIN_CONTENT for x in entries)):
                    break

            ctx.total_tokens = self._count_tokens(entries)
            if not compressed:
                break  # nothing more to shrink
            ratio = min(1.0, ratio * 1.6)

        ctx.entries = entries
        return ctx

    def _summarize_domain(self, e: DomainEntry) -> str:
        """Domain-specific summary (v3 §11.3 round 4) — semantic, not truncation.

        Keeps the domain anchor plus a meaningful window (head + tail) so the
        summary still carries signal, not just a prefix.
        """
        if len(e.content) <= self._MIN_CONTENT:
            return e.content  # already small enough — don't shred
        head = e.content[:self._MIN_CONTENT].replace("\n", " ")
        tail = e.content[-20:].replace("\n", " ") if len(e.content) > self._MIN_CONTENT + 20 else ""
        mid = f"...{tail}" if tail else "..."
        if e.domain == "D":
            return f"[D:话题] {head}{mid}"
        if e.domain in ("K", "E"):
            return f"[{e.domain}:工程] {head}{mid}"
        if e.domain in ("P", "F"):
            return f"[{e.domain}:画像] {head}{mid}"
        if e.domain == "B":
            return f"[B:行为] {head}{mid}"
        return f"[{e.domain}] {head}{mid}"

    # ── Topic-switch rebuild (DESIGN_SUBGRAPH §2.6, v3 §11.4) ──

    def _topic_switch_rebuild(self, old_ctx: SubgraphContext,
                              new_ctx: SubgraphContext) -> SubgraphContext:
        """Three-step landing on topic switch:
        1) old topic → L2-style summary (anchor + cross_ref preserved)
        2) structure keep-alive (connectors not compressed)
        3) new topic expanded under budget
        """
        # Step 1+2: summarize old, keep connectors intact
        for e in old_ctx.entries:
            is_connector = len(e.cross_refs) > 0
            if not is_connector:
                e.content = self._summarize_domain(e)
                e.token_estimate = len(e.content) // 2
                e.confidence = max(0.1, e.confidence * 0.7)

        # Step 3: merge under budget — trim combined if over
        merged = SubgraphContext(
            perspective=new_ctx.perspective,
            entries=old_ctx.entries + new_ctx.entries,
            total_tokens=self._count_tokens(old_ctx.entries + new_ctx.entries),
            budget=new_ctx.budget,
            domains=new_ctx.domains,
            compile_strategy="balanced",
            intent_category="topic_switch",
        )
        return self._trim(merged, "topic_switch")

    # ── SubgraphPrior pull (DESIGN_SUBGRAPH §4.3 / PCR §5) ──

    def pull_prior(self, domain_scope: Dict[str, float]) -> Dict[str, Any]:
        """Return expected-context prior for PCR coordinate bias.

        domain_scope: PCR-decided domain→budget map. Compiles dialogue context
        and aggregates confidence per domain into a coordinate_bias hint the
        PCR X-axis can use as a real reference (1 - cos(query, prior)).
        """
        ctx = self.compile_dialogue(intent_category="query")
        if not ctx.entries:
            return {"domain_scope": domain_scope, "coordinate_bias": {},
                    "expected_context": ""}

        # Aggregate per-domain confidence → bias (normalized 0..1)
        bias: Dict[str, float] = {}
        for e in ctx.entries:
            bias[e.domain] = max(bias.get(e.domain, 0.0), e.confidence)
        max_b = max(bias.values()) or 1.0
        coordinate_bias = {k: round(v / max_b, 3) for k, v in bias.items()}

        expected = " | ".join(f"{e.domain}:{e.content[:40]}" for e in ctx.entries[:5])
        return {
            "domain_scope": domain_scope,
            "coordinate_bias": coordinate_bias,
            "expected_context": expected[:300],
        }

    # ── Event-driven expansion (DESIGN_SUBGRAPH §11, v3 §3) ──

    def _expand_from_event(self, event_id: str, max_hops: int = 2) -> List[DomainEntry]:
        """Subgraph-side consumer: resolve an event and walk its trace.

        Reads the engine EventLog by event_id (payload + trace_id), then walks
        same-trace events to attach provenance entries. Deliberately tolerant:
        if EventLog is missing/closed or the event is unknown, returns [] —
        the caller decides whether to fall back to plain domain grabbing.
        Cross-module trace_id propagation (EventBus + chain writers) is a
        separate shared-layer task (DESIGN_SUBGRAPH §11.2).
        """
        if not event_id:
            return []
        el = getattr(self._engine, '_event_log', None) if self._engine else None
        if el is None:
            return []

        events: List[DomainEntry] = []
        try:
            row = el.get_event(event_id) if hasattr(el, 'get_event') else None
            if row is None:
                # fallback: scan recent unconsumed for the id
                for r in el.replay_unconsumed(limit=200) if hasattr(el, 'replay_unconsumed') else []:
                    if r.get("event_id") == event_id:
                        row = r
                        break
            if row is None:
                return []

            trace_id = row.get("trace_id")
            kind = row.get("kind", "unknown")
            payload = row.get("payload") or {}
            content = str(payload.get("text") or payload.get("content") or json.dumps(
                payload, ensure_ascii=False))[:200]
            events.append(DomainEntry("Q", f"event[{kind}] {content}", 0.9,
                                      "event_log", 40,
                                      source_events=[event_id]))

            if trace_id:
                hops = 0
                frontier = [event_id]
                seen = {event_id}
                while frontier and hops < max_hops:
                    nxt = []
                    for r in (el.replay_unconsumed(limit=500)
                              if hasattr(el, 'replay_unconsumed') else []):
                        rid = r.get("event_id")
                        if r.get("trace_id") == trace_id and rid not in seen:
                            seen.add(rid)
                            p = r.get("payload") or {}
                            c = str(p.get("text") or p.get("content") or
                                    json.dumps(p, ensure_ascii=False))[:150]
                            events.append(DomainEntry(
                                "E", f"trace[{r.get('kind','?')}] {c}", 0.7,
                                "event_log", 30, source_events=[rid]))
                            nxt.append(rid)
                        if len(seen) >= 8:
                            break
                    frontier = nxt
                    hops += 1
        except Exception as exc:
            logger.debug("event expansion failed for %s: %s", event_id, exc)
        return events

    # ── Graph retrieval primitive (DESIGN_SUBGRAPH §13) ──

    def expand_from_graph(self, query: str, max_nodes: int = 8) -> Optional[List[DomainEntry]]:
        """Graph-based retrieval: delegate to ConceptGraph.compile_context
        (multi-tier anchor + edge-priority expansion, §13.1). Returns entries
        in domain "G" (graph knowledge), or None when no graph is available —
        the caller then falls back to domain grabbing (§12.4/§13.3 ②).
        """
        if not query or not query.strip() or not self._engine:
            return None
        graph = None
        ci = getattr(self._engine, "_content_index", None)
        if ci is not None and hasattr(ci, "_graph"):
            graph = ci._graph
        if graph is None:
            graph = getattr(self._engine, "_graph", None)
        if graph is None:
            return None
        try:
            items = graph.compile_context(query, top_k=max_nodes,
                                          max_hops=2, max_nodes=max_nodes)
            if not items:
                return None
            entries = []
            for item in items:
                text = getattr(item, "text", "") or ""
                if not text:
                    continue
                entries.append(DomainEntry(
                    "G", text[:300], min(1.0, 0.5 + item.relevance / 2),
                    "concept_graph", len(text) // 2,
                ))
            return entries
        except Exception as exc:
            logger.debug("graph expansion failed: %s", exc)
            return None
