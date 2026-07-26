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
        """Execute one chain node via its type-specific handler.

        Chain dispatch table — each chain has its own implementation.
        Dependencies resolved from upstream outputs via data_keys.
        """
        chain = node.chain
        handlers = {
            "pcr": self._handle_pcr,
            "intent": self._handle_intent,
            "context": self._handle_context,
            "subgraph": self._handle_subgraph,
            "profile": self._handle_profile,
            "llm_reply": self._handle_llm_reply,
            "behavior": self._handle_behavior,
            "meta": self._handle_meta,
            "discourse": self._handle_discourse,
            "association": self._handle_association,
            "engineering": self._handle_engineering,
            "metap": self._handle_metap,
        }

        handler = handlers.get(chain, self._handle_default)
        return handler(node, all_outputs, user_text, orch)

    def _find_upstream(self, chain: str, all_outputs: dict) -> dict:
        """Find the first output from a given chain type."""
        for node_id, output in all_outputs.items():
            if chain in node_id:
                return output
        return {}

    # ─── Per-chain handlers ───

    def _handle_pcr(self, node, outputs, text, orch) -> dict:
        if orch:
            result = orch.process(text=text)
            return {"route": result.get("route", {}), "compass": result.get("compass", {})}
        return {"chain": "pcr", "status": "fallback"}

    def _handle_intent(self, node, outputs, text, orch) -> dict:
        if orch:
            result = orch.process(text=text)
            return {"intents": result.get("intents", {}), "segments": result.get("intents", {}).get("segments", [])}
        return {"chain": "intent", "status": "fallback"}

    def _handle_context(self, node, outputs, text, orch) -> dict:
        upstream = self._find_upstream("intent", outputs)
        if orch:
            result = orch.process(text=text)
            ctx = result.get("context", {})
            return {"assembled_context": ctx, "dialogue": ctx.get("dialogue", ""), "upstream": upstream}
        return {"chain": "context", "status": "fallback"}

    def _handle_subgraph(self, node, outputs, text, orch) -> dict:
        upstream = self._find_upstream("context", outputs)
        # Subgraph compiler: extract compiled subgraph from context
        ctx = upstream.get("assembled_context", upstream)
        return {"compiled_subgraph": ctx, "upstream_key": "compiled_subgraph"}

    def _handle_profile(self, node, outputs, text, orch) -> dict:
        try:
            import urllib.request, json
            req = urllib.request.Request("http://127.0.0.1:8000/v6/profile")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            p = data.get("profile", data)
            return {"profile_text": json.dumps(p, ensure_ascii=False, default=str)[:500]}
        except Exception:
            return {"chain": "profile", "status": "fetch_failed"}

    def _handle_llm_reply(self, node, outputs, text, orch) -> dict:
        # LLM reply — aggregate all upstream context
        return {"chain": "llm_reply", "context": {k: v for k, v in outputs.items() if k != node.node_id}}

    def _handle_behavior(self, node, outputs, text, orch) -> dict:
        if orch:
            result = orch.process(text=text)
            return result.get("cognition", {})
        return {"chain": "behavior", "status": "fallback"}

    def _handle_meta(self, node, outputs, text, orch) -> dict:
        return {"chain": "meta", "status": "async", "note": "Meta 异步审计，不阻塞执行"}

    def _handle_discourse(self, node, outputs, text, orch) -> dict:
        if orch:
            result = orch.process(text=text)
            return result.get("context", {}).get("dialogue", {})
        return {"chain": "discourse", "status": "fallback"}

    def _handle_association(self, node, outputs, text, orch) -> dict:
        return {"chain": "association", "status": "deferred", "note": "L1-L5 漏斗 — 后台异步"}

    def _handle_engineering(self, node, outputs, text, orch) -> dict:
        return {"chain": "engineering", "status": "deferred", "note": "7类节点约束 — 待接入"}

    def _handle_metap(self, node, outputs, text, orch) -> dict:
        return {"chain": "metap", "status": "async", "note": "EventLog 元持久化 — 后台"}

    def _handle_default(self, node, outputs, text, orch) -> dict:
        """Fallback handler for unknown chain types."""
        if orch:
            try:
                return orch.process(text=text)
            except Exception:
                pass
        return {"chain": node.chain, "status": "unknown_chain"}
