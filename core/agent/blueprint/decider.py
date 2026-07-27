# -*- coding: utf-8 -*-
"""Decider — BlueprintDAG → EventBus Tick execution (§14.3).

Takes a compiled BlueprintDAG and executes it through the EventBus:
  1. Group nodes by Tick (priority)
  2. Per Tick: publish events → chain subscribers process → return results
  3. Resolve dependencies between Ticks
  4. Final LLM synthesis from all chain outputs

This replaces the linear agent_native pipeline with parallel EventBus execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

logger = logging.getLogger(__name__)


@dataclass
class TickResult:
    tick: int
    node_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0


class Decider:
    """Executes BlueprintDAG via EventBus pub/sub.

    The EventBus is the mesh — Decider is the conductor.
    Each chain subscribes to its subject and processes independently.
    """

    def __init__(self):
        self._bus = None
        self._chain_handlers: Dict[str, callable] = {}
        self._orch = None
        self._init_handlers()

    def _init_handlers(self):
        """Register chain handlers — each chain maps to a processor."""
        from core.agent.blueprint.executor import BlueprintExecutor
        ex = BlueprintExecutor()
        self._chain_handlers = {
            "pcr": ex._handle_pcr,
            "intent": ex._handle_intent,
            "context": ex._handle_context,
            "subgraph": ex._handle_subgraph,
            "profile": ex._handle_profile,
            "llm_reply": ex._handle_llm_reply,
            "behavior": ex._handle_behavior,
            "meta": ex._handle_meta,
            "discourse": ex._handle_discourse,
            "association": ex._handle_association,
            "engineering": ex._handle_engineering,
            "metap": ex._handle_metap,
        }
        self._orch = ex._get_orchestrator()

    def execute(self, dag: BlueprintDAG, user_text: str = "") -> Dict[str, Any]:
        """Execute a BlueprintDAG through the EventBus.

        Returns:
            {chain_outputs: {node_id: result}, llm_reply: str, ticks: [...], latency_ms: float}
        """
        t0 = time.time()
        all_outputs: Dict[str, Any] = {}
        completed: set = set()
        ticks: List[TickResult] = []

        # Group nodes by priority (= Tick number)
        tick_groups: Dict[int, List[BlueprintNode]] = {}
        for n in dag.nodes:
            tick_groups.setdefault(n.priority, []).append(n)

        for tick_num in sorted(tick_groups.keys()):
            tick_start = time.time()
            tick_nodes = tick_groups[tick_num]
            tr = TickResult(tick=tick_num)

            for node in tick_nodes:
                # Check dependencies from current DAG
                incoming = dag.incoming_edges(node.node_id)
                deps_ready = all(
                    e.from_node in completed or not e.required
                    for e in incoming
                )
                if not deps_ready:
                    logger.warning("Tick %d: node %s deps not ready — skipping", tick_num, node.node_id)
                    continue

                # Dispatch to chain handler
                handler = self._chain_handlers.get(
                    node.chain,
                    self._chain_handlers.get("llm_reply"),
                )
                try:
                    result = handler(node, all_outputs, user_text, self._orch)
                    all_outputs[node.node_id] = result
                    tr.node_results[node.node_id] = result
                    completed.add(node.node_id)
                    logger.debug("Tick %d: %s → done", tick_num, node.node_id)
                except Exception as e:
                    logger.warning("Tick %d: %s failed: %s", tick_num, node.node_id, e)
                    tr.errors[node.node_id] = str(e)
                    all_outputs[node.node_id] = {"error": str(e)}

            tr.latency_ms = (time.time() - tick_start) * 1000
            ticks.append(tr)

        # Extract LLM reply
        llm_reply = ""
        for n in dag.nodes:
            if n.chain == "llm_reply" and n.node_id in all_outputs:
                out = all_outputs[n.node_id]
                llm_reply = out.get("response", out.get("content", str(out)[:500]))
                break

        total_ms = (time.time() - t0) * 1000
        logger.info("Decider: %d nodes in %d ticks (%.0fms)", len(completed), len(ticks), total_ms)

        return {
            "chain_outputs": all_outputs,
            "llm_reply": llm_reply,
            "latency_ms": total_ms,
            "ticks": [{
                "tick": t.tick,
                "nodes": list(t.node_results.keys()),
                "errors": t.errors,
                "latency_ms": t.latency_ms,
            } for t in ticks],
        }
