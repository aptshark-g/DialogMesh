"""L2 Summary - topic-level structured aggregation engine (v3.2)
Design doc §4.4: topic-level structured aggregation with full behavior DAG.
"""
from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


# ── Data Models ──

@dataclass
class BehaviorDAG:
    """Complete behavior推演图 for a topic."""
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class KeyDecision:
    """A decision point detected in the conversation."""
    turn_id: str = ""
    description: str = ""
    alternatives: List[str] = field(default_factory=list)
    chosen: Optional[str] = None


@dataclass
class DivergencePoint:
    """A point where multiple branches were predicted."""
    turn_id: str = ""
    description: str = ""
    branches: List[str] = field(default_factory=list)


@dataclass
class Level2Summary:
    """Topic-level structured aggregation (design doc §4.4)."""
    summary_id: str = ""
    topic_node_id: str = ""
    topic_description: str = ""
    behavior_dag: Dict[str, Any] = field(default_factory=dict)
    causal_chain_full: List[Dict[str, Any]] = field(default_factory=list)
    association_map: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    key_decisions: List[KeyDecision] = field(default_factory=list)
    divergence_points: List[DivergencePoint] = field(default_factory=list)
    unresolved_issues: List[str] = field(default_factory=list)
    l1_summary_ids: List[str] = field(default_factory=list)
    raw_turn_ids: List[str] = field(default_factory=list)
    total_turns: int = 0
    correction_rate: float = 0.0
    prediction_accuracy: float = 0.0


# ── Backward Compatibility ──

@dataclass
class L2SummaryEntry:
    """Deprecated: session-level summary entry with v1-v4 summary state.
    Use Level2Summary + L2SummaryAggregator instead.
    """
    session_id: str = ""
    turn_count: int = 0
    topics: list = field(default_factory=list)
    key_actions: list = field(default_factory=list)
    total_latency_ms: float = 0.0
    avg_stability: float = 0.0
    summary_v1: str = ""      # raw concatenated
    summary_v2: str = ""      # entity-extracted
    summary_v3: str = ""      # milestone-extracted
    summary_v4: str = ""      # LLM-compressed
    summary_version: int = 1

    def __post_init__(self):
        warnings.warn(
            "L2SummaryEntry is deprecated; use Level2Summary + L2SummaryAggregator",
            DeprecationWarning,
            stacklevel=2,
        )


class L2Summary:
    """Deprecated compatibility shim. Use L2SummaryAggregator."""

    def __init__(self, max_turns=100, llm_provider=None):
        warnings.warn(
            "L2Summary is deprecated; use L2SummaryAggregator",
            DeprecationWarning,
            stacklevel=2,
        )
        self.max_turns = max_turns
        self.turns = []
        self.llm = llm_provider

    def add_turn(self, l1_data: dict):
        self.turns.append(l1_data)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def summarize(self, session_id="", llm_callback=None) -> L2SummaryEntry:
        if not self.turns:
            return L2SummaryEntry(session_id=session_id)
        recent = self.turns[-20:]
        topics = list({str(t) for t in [x.get("topic", "") for x in recent] if str(t)})
        actions = list({str(a) for a in [x.get("action", "") for x in recent] if str(a)})
        stabs = [float(t.get("stability", 0)) for t in self.turns if t.get("stability")]
        avg_s = sum(stabs) / len(stabs) if stabs else 0.0
        last_q = str(recent[-1].get("query", ""))[:50] if recent else ""
        v1 = f"{len(self.turns)} turns, {len(topics)} topics, last: {last_q}"
        entities = [str(e) for t in recent for e in (t.get("entities", []) or []) if e]
        v2 = f"[{', '.join(topics[:5])}] key_actions: {', '.join(actions[:5])}"
        if entities:
            v2 += f" | entities: {', '.join(set(entities[:5]))}"
        errors = sum(1 for t in recent if t.get("error"))
        corrections = sum(1 for t in recent if t.get("correction"))
        v3 = v2
        if errors or corrections:
            v3 += f" | {errors} errors, {corrections} corrections"
        v4 = ""
        callback = llm_callback or self.llm
        if callback and len(self.turns) >= 5:
            try:
                text = v3 if len(v3) > len(v1) else v1
                prompt = f"Compress this conversation summary into <=80 chars. Keep topics and actions.\n{text}"
                if callable(callback):
                    result = callback(prompt)
                    if result and len(str(result)) > 10:
                        v4 = str(result)[:120]
                elif hasattr(callback, "generate"):
                    import asyncio
                    result = asyncio.run(callback.generate(prompt, max_tokens=100))
                    if result and len(str(result)) > 10:
                        v4 = str(result)[:120]
            except Exception:
                v4 = ""
        ver = 4 if v4 else 3 if corrections else 2 if entities else 1
        return L2SummaryEntry(
            session_id=session_id, turn_count=len(self.turns),
            topics=topics[:10], key_actions=actions[:10],
            avg_stability=avg_s, summary_v1=v1, summary_v2=v2,
            summary_v3=v3, summary_v4=v4, summary_version=ver,
        )


# ── New Aggregator ──

class L2SummaryAggregator:
    """Topic-level structured aggregation engine (design doc §4.4)."""

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def aggregate(self, topic_id: str, l1_entries: list) -> Level2Summary:
        """Main aggregation: build Level2Summary from L1 entries."""
        if not l1_entries:
            return Level2Summary(summary_id=str(uuid.uuid4()), topic_node_id=topic_id)

        l1_ids = [getattr(e, "summary_id", str(i)) for i, e in enumerate(l1_entries)]
        turn_ids = [getattr(e, "turn_id", "") for e in l1_entries]
        meta_list = [getattr(e, "meta_info", {}) or {} for e in l1_entries]

        topic_desc = self._build_topic_description(l1_entries)
        behavior_dag = self._build_behavior_dag(meta_list)
        causal_chain = self._extract_causal_chain(meta_list)
        assoc_map = self._extract_associations(meta_list)
        decisions = self._extract_key_decisions(l1_entries, meta_list)
        divergences = self._extract_divergence_points(meta_list)
        unresolved = self._extract_unresolved_issues(l1_entries, meta_list)
        metrics = self._compute_metrics(l1_entries, meta_list)

        return Level2Summary(
            summary_id=str(uuid.uuid4()),
            topic_node_id=topic_id,
            topic_description=topic_desc,
            behavior_dag=behavior_dag,
            causal_chain_full=causal_chain,
            association_map=assoc_map,
            key_decisions=decisions,
            divergence_points=divergences,
            unresolved_issues=unresolved,
            l1_summary_ids=l1_ids,
            raw_turn_ids=turn_ids,
            total_turns=len(l1_entries),
            correction_rate=metrics["correction_rate"],
            prediction_accuracy=metrics["prediction_accuracy"],
        )

    # ── internal builders ──

    def _build_topic_description(self, l1_entries: list) -> str:
        intents = []
        for e in l1_entries:
            mi = getattr(e, "meta_info", {}) or {}
            intent = mi.get("intent_category") if isinstance(mi, dict) else None
            if intent:
                intents.append(str(intent))
        if intents:
            return f"Topic: {', '.join(list(dict.fromkeys(intents))[:3])}"
        return "Topic: (no intent data)"

    def _build_behavior_dag(self, meta_list: list) -> Dict[str, Any]:
        nodes: Dict[str, Any] = {}
        edges: List[Dict[str, Any]] = []
        for i, meta in enumerate(meta_list):
            if not isinstance(meta, dict):
                continue
            prev = meta.get("prev_action")
            curr = meta.get("current_action")
            pred = meta.get("predicted_next", [])
            tid = meta.get("turn_id", f"turn_{i}")
            if curr:
                nodes[str(curr)] = {"turn_id": tid, "type": "action"}
            if prev and curr:
                edges.append({"from": str(prev), "to": str(curr), "weight": 1.0, "type": "observed"})
            for p in pred:
                act = p.get("action") if isinstance(p, dict) else str(p)
                if act and curr:
                    edges.append({"from": str(curr), "to": str(act), "weight": 0.5, "type": "predicted"})
        return asdict(BehaviorDAG(nodes=nodes, edges=edges))

    def _extract_causal_chain(self, meta_list: list) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = []
        for meta in meta_list:
            if not isinstance(meta, dict):
                continue
            events = meta.get("causal_events", [])
            for ev in events:
                if isinstance(ev, dict):
                    chain.append(ev)
                elif hasattr(ev, "__dict__"):
                    chain.append(ev.__dict__)
        return chain

    def _extract_associations(self, meta_list: list) -> Dict[str, List[Dict[str, Any]]]:
        assoc: Dict[str, List[Dict[str, Any]]] = {}
        for meta in meta_list:
            if not isinstance(meta, dict):
                continue
            for ref in meta.get("associations", []):
                if isinstance(ref, dict):
                    target = str(ref.get("target", "unknown"))
                    assoc.setdefault(target, []).append(ref)
                elif hasattr(ref, "__dict__"):
                    target = str(getattr(ref, "target", "unknown"))
                    assoc.setdefault(target, []).append(ref.__dict__)
        return assoc

    def _extract_key_decisions(self, l1_entries: list, meta_list: list) -> List[KeyDecision]:
        decisions: List[KeyDecision] = []
        for e, meta in zip(l1_entries, meta_list):
            if not isinstance(meta, dict):
                continue
            turn_id = getattr(e, "turn_id", "") or meta.get("turn_id", "")
            if meta.get("correction_detected"):
                decisions.append(KeyDecision(
                    turn_id=str(turn_id),
                    description="User correction detected",
                    alternatives=[meta.get("correction_detail", "")] if meta.get("correction_detail") else [],
                    chosen=meta.get("current_action", ""),
                ))
            if meta.get("is_topic_switch"):
                decisions.append(KeyDecision(
                    turn_id=str(turn_id),
                    description="Topic switch",
                    alternatives=[],
                    chosen=meta.get("current_action", ""),
                ))
        return decisions

    def _extract_divergence_points(self, meta_list: list) -> List[DivergencePoint]:
        divergences: List[DivergencePoint] = []
        for i, meta in enumerate(meta_list):
            if not isinstance(meta, dict):
                continue
            preds = meta.get("predicted_next", [])
            branches = [p.get("action") if isinstance(p, dict) else str(p) for p in preds]
            branches = [b for b in branches if b]
            if len(branches) > 1:
                divergences.append(DivergencePoint(
                    turn_id=meta.get("turn_id", f"turn_{i}"),
                    description="Multiple predicted_next branches",
                    branches=branches,
                ))
        return divergences

    def _extract_unresolved_issues(self, l1_entries: list, meta_list: list) -> List[str]:
        issues: List[str] = []
        for e, meta in zip(l1_entries, meta_list):
            stab = getattr(e, "stability", None)
            if stab is None and isinstance(meta, dict):
                stab = meta.get("stability")
            if stab is not None and float(stab) < 0.5:
                issues.append(f"Low stability turn: {getattr(e, 'turn_id', '')}")
            unc = meta.get("uncertainty") if isinstance(meta, dict) else None
            if unc and float(unc) > 0.7:
                issues.append(f"High uncertainty turn: {getattr(e, 'turn_id', '')}")
        return issues

    def _compute_metrics(self, l1_entries: list, meta_list: list) -> Dict[str, float]:
        total = len(l1_entries)
        if total == 0:
            return {"correction_rate": 0.0, "prediction_accuracy": 0.0}
        corrections = sum(1 for m in meta_list if isinstance(m, dict) and m.get("correction_detected"))
        # prediction accuracy: count entries where predicted_next matched current_action of next turn
        hits = 0
        pred_total = 0
        for i, meta in enumerate(meta_list[:-1]):
            if not isinstance(meta, dict):
                continue
            preds = meta.get("predicted_next", [])
            next_meta = meta_list[i + 1]
            next_act = next_meta.get("current_action") if isinstance(next_meta, dict) else None
            if preds and next_act:
                pred_total += 1
                pred_actions = [p.get("action") if isinstance(p, dict) else str(p) for p in preds]
                if next_act in pred_actions:
                    hits += 1
        correction_rate = corrections / total
        prediction_accuracy = hits / pred_total if pred_total > 0 else 0.0
        return {"correction_rate": correction_rate, "prediction_accuracy": prediction_accuracy}

    # ── serialization ──

    @staticmethod
    def to_dict(summary: Level2Summary) -> Dict[str, Any]:
        return asdict(summary)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Level2Summary:
        # Rehydrate nested dataclasses
        data = dict(data)
        data["behavior_dag"] = BehaviorDAG(**data.get("behavior_dag", {}))
        data["key_decisions"] = [KeyDecision(**d) for d in data.get("key_decisions", [])]
        data["divergence_points"] = [DivergencePoint(**d) for d in data.get("divergence_points", [])]
        return Level2Summary(**data)


# ── Backward compatibility function ──

def build_daily_report(sessions):
    """Build multi-session report from list of L2SummaryEntry."""
    if not sessions:
        return "No sessions"
    all_topics = set()
    total_turns = 0
    for s_obj in sessions:
        s = s_obj if isinstance(s_obj, dict) else s_obj.__dict__
        top = s.get("topics", []) if isinstance(s, dict) else (getattr(s_obj, "topics", []) or [])
        all_topics.update(top[:5])
        total_turns += s.get("turn_count", 0) if isinstance(s, dict) else getattr(s_obj, "turn_count", 0)
    return f"{len(sessions)} sessions | {total_turns} turns | {len(all_topics)} unique topics: {', '.join(list(all_topics)[:8])}"
