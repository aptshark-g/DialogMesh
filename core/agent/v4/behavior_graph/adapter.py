"""v4 BehaviorGraph adapter: bridges v3_2 BehaviorGraph into v4 runtime.

Architecture:
    EventIR → BehaviorGraphAdapter.record(event) → BehaviorStep
    Async Path writes steps; Slow Path reads chains for causal analysis.

The adapter is a ContextSource (for ContextAssembler integration) and
produces BehaviorContextItems that feed into CrossDomainContextIR.
"""
from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v4.event_ir import EventIR
from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.observation_compiler.models import ObservationBundle

# v3_2 imports (read-only, no modifications)
from core.agent.v3_2.behavior_graph.graph_store import BehaviorGraph as V3BehaviorGraph
from core.agent.v3_2.behavior_graph.models import BehaviorStep, BehaviorEdge

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# v4-native dataclasses (typed, documented)
# ═══════════════════════════════════════════════════════════════

@dataclass
class BehaviorGraphState:
    """Serializable snapshot of BehaviorGraph for v4 diagnostics."""
    node_count: int = 0
    edge_count: int = 0
    total_samples: int = 0
    last_step_id: Optional[str] = None
    chain_depth: int = 0


@dataclass
class BehaviorContextItem:
    """Normalized behavior data for v4 ContextAssembler."""
    step_id: str
    action_summary: str
    action_type: str
    entities: dict = field(default_factory=dict)
    result: str = ""
    timestamp: float = 0.0
    edge_weight: float = 0.5
    success_rate: float = 0.5
    chain_depth: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class BehaviorChainResult:
    """Result of chain extraction from BehaviorGraph."""
    chain_id: str
    steps: List[BehaviorContextItem]
    edges: List[Dict[str, Any]]
    total_weight: float = 0.0
    avg_success_rate: float = 0.0
    is_stable: bool = True


# ═══════════════════════════════════════════════════════════════
# Adapter
# ═══════════════════════════════════════════════════════════════

class BehaviorGraphAdapter(ContextSource):
    """v4 adapter for v3_2 BehaviorGraph.

    Responsibilities:
        1. Convert EventIR / ObservationBundle → BehaviorStep → write to graph
        2. Extract behavior chains for ContextAssembler (ContextSource interface)
        3. Provide chain query API for HypothesisEngine / CausalSubstrate
        4. Persist graph via v3_2's save/load (path configurable)

    Integration points:
        - Async Path: ``on_event()`` → ``record_step()``
        - Slow Path: ``retrieve()`` → ContextItem list for ContextAssembler
        - CausalSubstrate: ``get_chain_for_causal()`` → BehaviorChainResult
    """

    def __init__(
        self,
        graph: Optional[V3BehaviorGraph] = None,
        graph_path: Optional[str] = None,
        auto_save: bool = True,
    ):
        self._graph = graph or V3BehaviorGraph()
        self._graph_path = graph_path
        self._auto_save = auto_save
        self._session_step_ids: List[str] = []  # track current session chain
        self._last_step_id: Optional[str] = None
        logger.info(
            "BehaviorGraphAdapter initialized: nodes=%d edges=%d",
            len(self._graph.nodes),
            len(self._graph.edges),
        )

    # ── Properties ──

    @property
    def name(self) -> str:
        return "behavior"

    @property
    def graph(self) -> V3BehaviorGraph:
        """Access underlying v3_2 graph (for CausalSubstrate, etc.)."""
        return self._graph

    @property
    def node_count(self) -> int:
        return len(self._graph.nodes)

    @property
    def edge_count(self) -> int:
        return len(self._graph.edges)

    # ── Write API (Async Path) ──

    def record_step(
        self,
        action_summary: str,
        action_type: str = "dialog",
        entities: Optional[dict] = None,
        result: str = "",
        success: bool = True,
        correction: bool = False,
    ) -> str:
        """Record a single behavior step and link to previous step.

        Returns:
            step_id of the newly created step.
        """
        step_id = f"bs_{uuid.uuid4().hex[:12]}"
        step = BehaviorStep(
            step_id=step_id,
            action_summary=action_summary,
            action_type=action_type,
            entities=entities or {},
            result=result,
            timestamp=time.time(),
        )
        self._graph.add_step(step)
        self._session_step_ids.append(step_id)

        # Link to previous step in session
        if self._last_step_id is not None:
            self._graph.record_edge(
                self._graph.get_step(self._last_step_id),
                step,
                success=success,
                correction=correction,
            )
            logger.debug(
                "Behavior edge recorded: %s -> %s (success=%s correction=%s)",
                self._last_step_id, step_id, success, correction,
            )

        self._last_step_id = step_id

        if self._auto_save and self._graph_path:
            try:
                self._graph.save(self._graph_path)
            except Exception as e:
                logger.warning("BehaviorGraph auto-save failed: %s", e)

        return step_id

    def record_event(self, event: EventIR, success: bool = True) -> str:
        """Convert EventIR to BehaviorStep and record.

        Maps EventIR.kind → action_type:
            dialog.message → dialog
            ui.*           → ui
            config.change  → config
            api.call       → api
            document.upload → document
        """
        kind = event.kind if hasattr(event, "kind") else "unknown"
        payload = event.payload if hasattr(event, "payload") else {}

        # Map kind to action_type
        action_type = "unknown"
        if kind.startswith("dialog."):
            action_type = "dialog"
        elif kind.startswith("ui."):
            action_type = "ui"
        elif kind.startswith("config."):
            action_type = "config"
        elif kind.startswith("api."):
            action_type = "api"
        elif kind.startswith("document."):
            action_type = "document"
        elif kind.startswith("tool."):
            action_type = "tool"

        summary = payload.get("text", payload.get("content", payload.get("action", kind)))
        entities = {
            "event_id": event.id,
            "kind": kind,
            **{k: v for k, v in payload.items() if k not in ("text", "content", "action")},
        }

        return self.record_step(
            action_summary=str(summary)[:200],
            action_type=action_type,
            entities=entities,
            result=payload.get("result", ""),
            success=success,
        )

    def record_observation_bundle(self, bundle: ObservationBundle, success: bool = True) -> List[str]:
        """Record all domain observations from an ObservationBundle as steps.

        Returns:
            List of recorded step_ids.
        """
        step_ids = []
        for domain, obs in bundle.domain_observations.items():
            sid = self.record_step(
                action_summary=obs.summary or f"obs:{domain}",
                action_type=domain,
                entities={
                    "bundle_id": bundle.bundle_id,
                    "event_id": bundle.event_id,
                    "domain": domain,
                    "actions": obs.actions,
                    "objects": obs.objects,
                },
                result=obs.status,
                success=success,
            )
            step_ids.append(sid)
        return step_ids

    def mark_correction(self, step_id: str) -> bool:
        """Mark a step as corrected (updates edge metadata)."""
        step = self._graph.get_step(step_id)
        if step is None:
            return False
        # Find incoming edge and mark correction
        for ek, edge in self._graph.edges.items():
            if edge.to_step_id == step_id:
                edge.correction_count += 1
                edge.is_stable = False
                logger.debug("Correction marked on edge %s", ek)
                return True
        return False

    def reset_session_chain(self) -> None:
        """Reset session chain tracking (e.g., on new conversation)."""
        self._session_step_ids.clear()
        self._last_step_id = None

    # ── Read API (ContextSource interface) ──

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        """Retrieve behavior context items for ContextAssembler.

        Strategy:
            1. Find recent steps matching query keywords
            2. Extract short chains around matched steps
            3. Return as ContextItem with relevance score
        """
        keywords = query.lower().split()
        items: List[ContextItem] = []

        # Score nodes by keyword match
        scored_steps: List[Tuple[BehaviorStep, float]] = []
        for step in self._graph.nodes.values():
            text = f"{step.action_summary} {step.action_type}".lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored_steps.append((step, score / max(1, len(keywords))))

        scored_steps.sort(key=lambda x: x[1], reverse=True)

        for step, relevance in scored_steps[:top_k]:
            # Extract mini-chain around this step
            chain = self._graph.get_chain(step.step_id, max_depth=2)
            chain_items = [
                BehaviorContextItem(
                    step_id=s.step_id,
                    action_summary=s.action_summary,
                    action_type=s.action_type,
                    entities=s.entities,
                    result=s.result,
                    timestamp=s.timestamp,
                    edge_weight=e.weight if e else 0.5,
                    success_rate=e.success_rate if e else 0.5,
                    chain_depth=i,
                )
                for i, (s, e) in enumerate(chain)
            ]

            items.append(ContextItem(
                source=self.name,
                content=chain_items,
                relevance=relevance,
                metadata={
                    "step_id": step.step_id,
                    "action_type": step.action_type,
                    "chain_length": len(chain),
                    "timestamp": step.timestamp,
                },
            ))

        return items

    # ── Chain API (for CausalSubstrate / HypothesisEngine) ──

    def get_chain_for_causal(
        self,
        start_step_id: Optional[str] = None,
        max_depth: int = 5,
    ) -> BehaviorChainResult:
        """Extract a behavior chain for CausalSubstrate analysis.

        If start_step_id is None, uses the first step of the current session.
        """
        sid = start_step_id or (self._session_step_ids[0] if self._session_step_ids else None)
        if sid is None:
            return BehaviorChainResult(chain_id="empty", steps=[], edges=[])

        raw_chain = self._graph.get_chain(sid, max_depth=max_depth)
        step_ids = [sid] + [s.step_id for s, _ in raw_chain]
        edges = self._graph.get_edges_for_chain(step_ids)

        steps = [
            BehaviorContextItem(
                step_id=s.step_id,
                action_summary=s.action_summary,
                action_type=s.action_type,
                entities=s.entities,
                result=s.result,
                timestamp=s.timestamp,
                edge_weight=e.weight if e else 0.5,
                success_rate=getattr(e, "success_rate", 0.5) if e else 0.5,
                chain_depth=i,
            )
            for i, (s, e) in enumerate(raw_chain)
        ]

        total_weight = sum(s.edge_weight for s in steps) if steps else 0.0
        avg_success = sum(s.success_rate for s in steps) / len(steps) if steps else 0.0
        is_stable = all(
            getattr(e, "is_stable", True) for e in edges
        ) if edges else True

        return BehaviorChainResult(
            chain_id=f"chain_{sid}",
            steps=steps,
            edges=[{
                "edge_id": e.edge_id,
                "from_step_id": e.from_step_id,
                "to_step_id": e.to_step_id,
                "weight": e.weight,
                "success_rate": getattr(e, "success_rate", 0.5),
                "structural_prior": getattr(e, "structural_prior", 0.0),
                "is_stable": getattr(e, "is_stable", True),
            } for e in edges],
            total_weight=total_weight,
            avg_success_rate=avg_success,
            is_stable=is_stable,
        )

    def get_recent_chain(self, n_steps: int = 10) -> BehaviorChainResult:
        """Get the most recent N steps as a chain."""
        if not self._session_step_ids:
            return BehaviorChainResult(chain_id="empty", steps=[], edges=[])
        recent_ids = self._session_step_ids[-n_steps:]
        return self.get_chain_for_causal(recent_ids[0], max_depth=n_steps)

    # ── Statistics ──

    def stats(self) -> Dict[str, Any]:
        """Return adapter statistics."""
        gs = self._graph.get_statistics()
        return {
            "node_count": gs.node_count,
            "edge_count": gs.edge_count,
            "total_samples": gs.total_samples,
            "session_steps": len(self._session_step_ids),
            "avg_weight": gs.avg_weight,
            "avg_importance": gs.avg_importance,
            "unstable_edges": gs.unstable_edge_count,
        }

    # ── Persistence ──

    def save(self, path: Optional[str] = None) -> None:
        """Persist graph to disk."""
        target = path or self._graph_path
        if target:
            self._graph.save(target)
            logger.info("BehaviorGraph saved to %s", target)

    def load(self, path: Optional[str] = None) -> None:
        """Load graph from disk."""
        target = path or self._graph_path
        if target:
            self._graph = V3BehaviorGraph.load(target)
            # v3_2 load() doesn't initialize weight_updater; fix here
            if self._graph.weight_updater is None:
                from core.agent.v3_2.behavior_graph.weight_updater import WeightUpdater
                self._graph.weight_updater = WeightUpdater()
            if self._graph.cold_start is None:
                from core.agent.v3_2.behavior_graph.cold_start import ColdStartManager
                self._graph.cold_start = ColdStartManager()
            self._session_step_ids.clear()
            self._last_step_id = None
            logger.info("BehaviorGraph loaded from %s: nodes=%d edges=%d", target,
                        len(self._graph.nodes), len(self._graph.edges))

    # ── v4 RuntimeAdapter helper ──

    def to_runtime_result(self) -> Dict[str, Any]:
        """Serialize current state for RuntimeContext."""
        return {
            "graph_stats": self.stats(),
            "last_step_id": self._last_step_id,
            "session_chain_length": len(self._session_step_ids),
        }
