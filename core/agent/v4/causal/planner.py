"""CausalRetrievalPlanner: v4 adapter for v3_2 BehaviorGraph + CausalSubstrate.

Design: Adapter pattern — v4 code never imports v3_2 directly.
The planner exposes two faces:
  1. CausalContextSource  → plugged into ContextAssembler (retrieve)
  2. CausalPlanner        → invoked by Slow Path / engine checkpoint

Data flow:
  Async Path  → ObservationPool → BehaviorStep (via EventIR→BehaviorStep mapper)
  Slow Path   → CausalPlanner.process_chain() → CausalSubstrate → updated priors
  ContextAsm  → CausalContextSource.retrieve() → BehaviorChain IR entries
"""
from __future__ import annotations
import time
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.event_ir import EventIR

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# v4-native dataclasses (mirror v3_2 models, no import)
# ═══════════════════════════════════════════════════════════════

@dataclass
class BehaviorStepIR:
    """v4 IR for a behavior step. Decoupled from v3_2 BehaviorStep."""
    step_id: str
    action_summary: str
    action_type: str
    entities: dict = field(default_factory=dict)
    result: str = ""
    timestamp: float = 0.0
    event_id: str = ""

    @classmethod
    def from_event(cls, event: EventIR) -> "BehaviorStepIR":
        """Map an EventIR to a BehaviorStepIR."""
        payload = event.payload if hasattr(event, "payload") else {}
        kind = event.kind if hasattr(event, "kind") else "unknown"
        # Derive action_type from EventIR.kind
        action_type = _kind_to_action_type(kind)
        # Build action_summary from payload
        summary = _build_summary(kind, payload)
        return cls(
            step_id=f"step_{event.id}",
            action_summary=summary,
            action_type=action_type,
            entities=payload.get("entities", {}),
            result=payload.get("result", ""),
            timestamp=event.timestamp if hasattr(event, "timestamp") else time.time(),
            event_id=event.id,
        )


@dataclass
class BehaviorEdgeIR:
    """v4 IR for a behavior edge. Decoupled from v3_2 BehaviorEdge."""
    edge_id: str
    from_step_id: str
    to_step_id: str
    weight: float = 0.5
    llm_causal_prob: float = 0.0
    freq_ratio: float = 0.0
    profile_boost: float = 0.0
    structural_prior: float = 0.0
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    correction_count: int = 0
    importance: float = 0.5
    is_stable: bool = True
    is_deprecated: bool = False


@dataclass
class CausalChainResult:
    """Result of processing a behavior chain through CausalSubstrate."""
    chain: List[BehaviorStepIR]
    edge_updates: List[Dict[str, Any]] = field(default_factory=list)
    structural_priors: Dict[str, float] = field(default_factory=dict)
    triggered: bool = False
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def _kind_to_action_type(kind: str) -> str:
    mapping = {
        "dialog.message": "dialog",
        "ui.click": "ui_interact",
        "ui.drag": "ui_interact",
        "ui.drop": "ui_interact",
        "config.change": "config",
        "api.call": "api",
        "document.upload": "document",
        "tool.call": "tool",
    }
    return mapping.get(kind, "unknown")


def _build_summary(kind: str, payload: dict) -> str:
    text = payload.get("text", payload.get("content", ""))
    if text:
        return text[:200]
    desc = payload.get("description", "")
    if desc:
        return desc[:200]
    return f"{kind}:{list(payload.keys())[:3]}"


# ═══════════════════════════════════════════════════════════════
# CausalPlanner: core logic wrapper
# ═══════════════════════════════════════════════════════════════

class CausalPlanner:
    """Wraps v3_2 BehaviorGraph + CausalSubstrate for v4 runtime.

    Lifecycle:
        1. engine.start() -> planner = CausalPlanner()
        2. on_event()     -> planner.record_step(event)
        3. Slow Path      -> planner.process_chain() -> updates priors
        4. ContextAsm     -> source.retrieve() -> behavior chains as IR entries

    Thread-safety: All public methods acquire ``_lock``.
    """

    MIN_CHAIN_LEN: int = 10  # mirrors CausalSubstrate.MIN_CHAIN

    def __init__(
        self,
        graph_path: Optional[str] = None,
        behavior_graph=None,
        causal_substrate=None,
    ):
        self._lock = __import__("threading").Lock()
        self._step_buffer: List[BehaviorStepIR] = []
        self._chain_results: List[CausalChainResult] = []
        self._last_processed_idx: int = 0

        # Lazy-loaded v3_2 instances (created on first use)
        self._graph_path = graph_path
        self._graph = behavior_graph
        self._substrate = causal_substrate
        self._v3_2_loaded: bool = behavior_graph is not None

    # ---- v3_2 bridge (lazy init) ----

    def _ensure_v3_2(self) -> bool:
        """Lazy-import and initialize v3_2 components. Returns True if ready."""
        if self._v3_2_loaded:
            return True
        try:
            from core.agent.v3_2.behavior_graph.graph_store import BehaviorGraph
            from core.agent.v3_2.causal_substrate.causal_substrate import CausalSubstrate

            if self._graph_path:
                self._graph = BehaviorGraph.load(self._graph_path)
                logger.info("BehaviorGraph loaded from %s", self._graph_path)
            else:
                self._graph = BehaviorGraph()
                logger.info("BehaviorGraph created (cold start)")

            self._substrate = CausalSubstrate(self._graph)
            self._v3_2_loaded = True
            return True
        except Exception as exc:
            logger.warning("CausalPlanner: v3_2 components unavailable: %s", exc)
            return False

    # ---- Async Path: record steps ----

    def record_step(self, event: EventIR, success: bool = True, correction: bool = False) -> Optional[str]:
        """Record an EventIR as a BehaviorStep and (if previous exists) an Edge.

        Called from engine.on_event() after observation compilation.

        Returns:
            edge_id if an edge was recorded, else None.
        """
        step_ir = BehaviorStepIR.from_event(event)
        with self._lock:
            self._step_buffer.append(step_ir)

            if not self._ensure_v3_2():
                return None

            # Map IR -> v3_2 step
            from core.agent.v3_2.behavior_graph.models import BehaviorStep as V3Step
            v3_step = V3Step(
                step_id=step_ir.step_id,
                action_summary=step_ir.action_summary,
                action_type=step_ir.action_type,
                entities=step_ir.entities,
                result=step_ir.result,
                timestamp=step_ir.timestamp,
            )
            self._graph.add_step(v3_step)

            # Record edge from previous step
            edge_id = None
            if len(self._step_buffer) >= 2:
                prev = self._step_buffer[-2]
                from core.agent.v3_2.behavior_graph.models import BehaviorStep as V3Step
                prev_v3 = V3Step(
                    step_id=prev.step_id,
                    action_summary=prev.action_summary,
                    action_type=prev.action_type,
                    entities=prev.entities,
                    result=prev.result,
                    timestamp=prev.timestamp,
                )
                edge_id = self._graph.record_edge(
                    prev_v3, v3_step, success=success, correction=correction
                )
                logger.debug(
                    "BehaviorEdge recorded: %s (%s -> %s)",
                    edge_id, prev.step_id, step_ir.step_id,
                )
            return edge_id

    # ---- Slow Path: causal processing ----

    def process_chain(self, max_depth: int = 5) -> CausalChainResult:
        """Process buffered steps as a chain through CausalSubstrate.

        Called from engine._run_path("slow") or trigger_checkpoint().

        Returns:
            CausalChainResult with edge_updates and structural_priors.
        """
        with self._lock:
            chain = list(self._step_buffer[self._last_processed_idx :])
            if not chain:
                return CausalChainResult(chain=[], triggered=False)

            triggered = len(chain) > self.MIN_CHAIN_LEN
            result = CausalChainResult(chain=chain, triggered=triggered)

            if not triggered:
                logger.debug("Chain too short (%d < %d), skipping causal processing", len(chain), self.MIN_CHAIN_LEN)
                return result

            if not self._ensure_v3_2():
                return result

            # Build v3_2 step chain for substrate
            from core.agent.v3_2.behavior_graph.models import BehaviorStep as V3Step
            v3_chain = []
            for s in chain:
                v3_chain.append(V3Step(
                    step_id=s.step_id,
                    action_summary=s.action_summary,
                    action_type=s.action_type,
                    entities=s.entities,
                    result=s.result,
                    timestamp=s.timestamp,
                ))

            try:
                # CausalSubstrate.process_chain returns list of {"edge_key": ..., "structural_prior": ...}
                updates = self._substrate.process_chain(v3_chain)
                for upd in updates:
                    ek = upd.get("edge_key")
                    prior = upd.get("structural_prior", 0.0)
                    if ek:
                        self._substrate.update_edge_prior(ek, prior)
                        result.edge_updates.append({"edge_key": ek, "structural_prior": prior})
                        result.structural_priors[ek] = prior
                self._last_processed_idx = len(self._step_buffer)
                logger.info(
                    "CausalChain processed: %d steps, %d edge updates",
                    len(chain), len(result.edge_updates),
                )
            except Exception as exc:
                logger.warning("CausalSubstrate process_chain failed: %s", exc)

            self._chain_results.append(result)
            return result

    # ---- Retrieval API ----

    def get_chain(self, start_event_id: str, max_depth: int = 5) -> List[Tuple[BehaviorStepIR, BehaviorEdgeIR]]:
        """Retrieve behavior chain from graph starting at a given event's step.

        Returns:
            List of (BehaviorStepIR, BehaviorEdgeIR) tuples.
        """
        step_id = f"step_{start_event_id}"
        with self._lock:
            if not self._ensure_v3_2():
                return []

            try:
                v3_chain = self._graph.get_chain(step_id, max_depth=max_depth)
            except Exception as exc:
                logger.warning("get_chain failed: %s", exc)
                return []

            results: List[Tuple[BehaviorStepIR, BehaviorEdgeIR]] = []
            for v3_step, v3_edge in v3_chain:
                step_ir = BehaviorStepIR(
                    step_id=v3_step.step_id,
                    action_summary=v3_step.action_summary,
                    action_type=v3_step.action_type,
                    entities=getattr(v3_step, "entities", {}),
                    result=getattr(v3_step, "result", ""),
                    timestamp=getattr(v3_step, "timestamp", 0.0),
                )
                edge_ir = BehaviorEdgeIR(
                    edge_id=v3_edge.edge_id,
                    from_step_id=v3_edge.from_step_id,
                    to_step_id=v3_edge.to_step_id,
                    weight=v3_edge.weight,
                    llm_causal_prob=v3_edge.llm_causal_prob,
                    freq_ratio=v3_edge.freq_ratio,
                    profile_boost=v3_edge.profile_boost,
                    structural_prior=v3_edge.structural_prior,
                    sample_count=v3_edge.sample_count,
                    success_count=v3_edge.success_count,
                    failure_count=v3_edge.failure_count,
                    correction_count=v3_edge.correction_count,
                    importance=v3_edge.importance,
                    is_stable=v3_edge.is_stable,
                    is_deprecated=v3_edge.is_deprecated,
                )
                results.append((step_ir, edge_ir))
            return results

    def get_recent_chain(self, max_steps: int = 10) -> List[BehaviorStepIR]:
        """Return the most recent N steps from the buffer."""
        with self._lock:
            return list(self._step_buffer[-max_steps:])

    # ---- Persistence ----

    def save(self, path: str) -> bool:
        """Persist underlying BehaviorGraph to disk."""
        with self._lock:
            if not self._ensure_v3_2():
                return False
            try:
                self._graph.save(path)
                logger.info("BehaviorGraph saved to %s", path)
                return True
            except Exception as exc:
                logger.warning("Save failed: %s", exc)
                return False

    def load(self, path: str) -> bool:
        """Load BehaviorGraph from disk."""
        with self._lock:
            try:
                from core.agent.v3_2.behavior_graph.graph_store import BehaviorGraph
                self._graph = BehaviorGraph.load(path)
                self._graph_path = path
                self._v3_2_loaded = True
                logger.info("BehaviorGraph loaded from %s", path)
                return True
            except Exception as exc:
                logger.warning("Load failed: %s", exc)
                return False

    # ---- Stats ----

    @property
    def stats(self) -> dict:
        with self._lock:
            graph_stats = {}
            if self._v3_2_loaded and self._graph is not None:
                try:
                    gs = self._graph.get_statistics()
                    graph_stats = {
                        "node_count": getattr(gs, "node_count", 0),
                        "edge_count": getattr(gs, "edge_count", 0),
                        "total_samples": getattr(gs, "total_samples", 0),
                    }
                except Exception:
                    pass
            return {
                "buffered_steps": len(self._step_buffer),
                "last_processed_idx": self._last_processed_idx,
                "chain_results": len(self._chain_results),
                "v3_2_loaded": self._v3_2_loaded,
                **graph_stats,
            }


# ═══════════════════════════════════════════════════════════════
# CausalContextSource: ContextSource implementation
# ═══════════════════════════════════════════════════════════════

class CausalContextSource(ContextSource):
    """Retrieves behavior chains and causal priors for ContextAssembler.

    Usage:
        planner = CausalPlanner()
        source = CausalContextSource(planner)
        assembler = ContextAssembler(sources=[..., source])
    """

    def __init__(self, planner: CausalPlanner):
        self._planner = planner

    @property
    def name(self) -> str:
        return "causal"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        """Retrieve causal context: recent behavior chain + edge priors.

        Relevance scoring:
          - Recency: newer steps score higher
          - Causal strength: edges with higher structural_prior score higher
          - Query match: action_summary contains query keywords
        """
        items: List[ContextItem] = []
        keywords = query.lower().split()

        # 1. Recent chain (as context narrative)
        recent = self._planner.get_recent_chain(max_steps=top_k * 2)
        for i, step in enumerate(recent):
            recency_score = (i + 1) / max(1, len(recent))  # 0..1, higher = newer
            keyword_score = sum(1 for kw in keywords if kw in step.action_summary.lower())
            relevance = 0.3 * recency_score + 0.1 * min(1.0, keyword_score)
            items.append(ContextItem(
                source=self.name,
                content=f"[{step.action_type}] {step.action_summary}",
                relevance=relevance,
                metadata={
                    "step_id": step.step_id,
                    "event_id": step.event_id,
                    "timestamp": step.timestamp,
                    "type": "behavior_step",
                },
            ))

        # 2. Causal edges with high structural_prior (if query hints at causality)
        causal_keywords = {"why", "because", "cause", "lead", "result", "trigger", "then", "after"}
        if any(kw in causal_keywords for kw in keywords):
            # Get chain from most recent step to include edge data
            if recent:
                chain = self._planner.get_chain(recent[-1].event_id, max_depth=top_k)
                for step_ir, edge_ir in chain:
                    causal_strength = edge_ir.structural_prior * 0.5 + edge_ir.weight * 0.3
                    items.append(ContextItem(
                        source=self.name,
                        content=(
                            f"Causal: {edge_ir.from_step_id} -> {edge_ir.to_step_id} "
                            f"(prior={edge_ir.structural_prior:.2f}, weight={edge_ir.weight:.2f})"
                        ),
                        relevance=causal_strength,
                        metadata={
                            "edge_id": edge_ir.edge_id,
                            "structural_prior": edge_ir.structural_prior,
                            "weight": edge_ir.weight,
                            "success_rate": edge_ir.success_count / max(1, edge_ir.success_count + edge_ir.failure_count),
                            "type": "causal_edge",
                        },
                    ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]
