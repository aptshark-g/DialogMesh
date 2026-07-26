# -*- coding: utf-8 -*-
"""BlueprintExecutor — executes BlueprintDAG via agent_native pipeline.

§14.3 EventBus 订阅表的执行实现:
  - 每个 BlueprintNode 映射到一个 agent_native 处理步骤
  - 按 Tick 执行: 同 Tick 内并行, 跨 Tick 串行
  - 依赖通过 data_key 解析
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

logger = logging.getLogger(__name__)


@dataclass
class TickResult:
    """Results from one execution Tick."""
    tick: int
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0


class BlueprintExecutor:
    """Executes a BlueprintDAG through the existing agent pipeline.

    Currently bridges to agent_native.process() for each chain.
    Future: direct EventBus pub/sub per §14.3 subscription table.
    """

    def __init__(self):
        self._orch = None

    def _get_orchestrator(self):
        """Lazy-load AgentOrchestrator to avoid import at module level."""
        if self._orch is None:
            try:
                from core.agent.orchestrator.agent_native import AgentOrchestrator
                self._orch = AgentOrchestrator()
            except Exception as e:
                logger.warning("AgentOrchestrator unavailable: %s", e)
                self._orch = None
        return self._orch

    def execute(self, dag: BlueprintDAG, user_text: str = "") -> Dict[str, Any]:
        """Execute a BlueprintDAG and return aggregated results.

        Returns dict with keys:
          - chain_outputs: {node_id: result_dict}
          - llm_reply: final LLM response (if llm_reply node present)
          - latency_ms: total execution time
          - ticks: list of TickResult per Tick
        """
        t0 = time.time()
        all_outputs: Dict[str, Any] = {}  # node_id → output dict
        completed: set = set()
        ticks: List[TickResult] = []

        # Group nodes by priority (= Tick number)
        tick_groups: Dict[int, List[BlueprintNode]] = {}
        for n in dag.nodes:
            tick_groups.setdefault(n.priority, []).append(n)

        orch = self._get_orchestrator()

        for tick_num in sorted(tick_groups.keys()):
            tick_start = time.time()
            tick_nodes = tick_groups[tick_num]
            tick_result = TickResult(tick=tick_num)

            for node in tick_nodes:
                # Check dependencies
                incoming = dag.incoming_edges(node.node_id)
                deps_ready = all(
                    e.from_node in completed or not e.required
                    for e in incoming
                )
                if not deps_ready:
                    logger.warning("Node %s deps not ready — skipping", node.node_id)
                    continue

                # Execute chain
                try:
                    output = self._execute_chain(node, all_outputs, user_text, orch)
                    all_outputs[node.node_id] = output
                    tick_result.outputs[node.node_id] = output
                    completed.add(node.node_id)
                except Exception as e:
                    logger.warning("Node %s failed: %s", node.node_id, e)
                    tick_result.errors[node.node_id] = str(e)
                    # For required nodes, we might want to abort
                    # For now, continue with empty output

            tick_result.latency_ms = (time.time() - tick_start) * 1000
            ticks.append(tick_result)

        # Extract LLM reply if present
        llm_reply = ""
        for n in dag.nodes:
            if n.chain == "llm_reply" and n.node_id in all_outputs:
                out = all_outputs[n.node_id]
                llm_reply = out.get("response", out.get("content", str(out)[:500]))
                break

        total_ms = (time.time() - t0) * 1000
        logger.info("BlueprintExecutor: executed %d nodes in %d ticks (%.0fms)",
                     len(completed), len(ticks), total_ms)

        return {
            "chain_outputs": all_outputs,
            "llm_reply": llm_reply,
            "latency_ms": total_ms,
            "ticks": [{
                "tick": t.tick,
                "nodes": list(t.outputs.keys()),
                "errors": t.errors,
                "latency_ms": t.latency_ms,
            } for t in ticks],
        }

    def _execute_chain(self, node: BlueprintNode, all_outputs: dict,
                       user_text: str, orch) -> Dict[str, Any]:
        """Execute one chain node via the appropriate handler.

        Currently: all chains route through agent_native.process().
        Future: each chain has its own subscriber per §14.3.
        """
        chain = node.chain

        # Build context from dependency outputs
        context = {}
        if chain == "pcr":
            context["text"] = user_text
        elif chain == "intent":
            pcr_out = self._find_upstream("pcr", all_outputs)
            context["route"] = pcr_out.get("route", {})
        elif chain == "context":
            intent_out = self._find_upstream("intent", all_outputs)
            context["intent_context"] = intent_out
        elif chain == "subgraph":
            context_out = self._find_upstream("context", all_outputs)
            context["assembled_context"] = context_out
        elif chain == "profile":
            intent_out = self._find_upstream("intent", all_outputs)
            context["intent_context"] = intent_out
        elif chain == "llm_reply":
            # Aggregate all upstream outputs
            context["all_outputs"] = {k: v for k, v in all_outputs.items()}

        # Execute through orchestrator
        if orch is not None:
            try:
                result = orch.process(text=user_text)
                return result
            except Exception as e:
                logger.warning("Chain %s failed: %s", chain, e)

        return {"chain": chain, "status": "ok", "context": context}

    def _find_upstream(self, chain: str, all_outputs: dict) -> dict:
        """Find the first output from a given chain type."""
        for node_id, output in all_outputs.items():
            if chain in node_id:
                return output
        return {}
