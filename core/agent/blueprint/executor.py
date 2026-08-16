# -*- coding: utf-8 -*-
"""BlueprintExecutor — mixed-mode DAG execution (§7.2, DESIGN_DEEP_AUDIT).

Sync aggregation segment: chain components called directly (white-box, typed):
  pcr → intent → context/subgraph → llm_reply (fan-in for final reply).
Async consumption segment: per-node outputs recorded to EventLog (git-style
  trace, §7.5 DAG snapshot base).

llm_reply supports reply modes (§7.6):
  mode=llm      → switch-gateway call with aggregated DAG context (default)
  mode=template → deterministic template reply (fast path, no LLM)
  mode=user/bp  → reserved (user-defined JSON blueprint behaviors)

No fake data: when a chain component is unavailable the handler returns an
explicit {"status": "unavailable"} instead of keyword-heuristic output.

ARCHIVED NOTE (2026-08-16): 生产执行已走 StateMachine.run_dag（B2/G1）,
BlueprintExecutor 保留为验证/回放工具。其中 _handle_discourse/_handle_engineering
为 deferred 占位（生产 handler 见 event/handlers.py）; expand_from_dag_trace /
route_mode 为 P2 设计承诺未兑现 —— 均不阻塞生产, 不删代码（A17）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
# G3 (FLOW_SELF_GROWTH §三 G3): LLM_DRIVEN 四保护
from core.agent.blueprint.protection import (
    PlanGate, Budget, LoopDetector, QualityGate,
)
# E5 (ERROR_META_REFLECTION): 错误模式计数 → meta_advice 反思事件
from core.agent.common.error_pattern import ErrorPatternTracker, classify_error

logger = logging.getLogger(__name__)

SWITCH_URL = "http://127.0.0.1:8080/v1/chat/completions"
SWITCH_KEY = "dm-client"
DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"


def call_switch(messages: List[dict], provider: str = DEFAULT_PROVIDER,
                model: str = DEFAULT_MODEL, temperature: Optional[float] = None,
                max_tokens: Optional[int] = None) -> str:
    """Shared switch-gateway LLM call (same contract as v3_session_api Phase 4).

    Returns response text, or "" on failure (callers degrade explicitly).
    """
    import urllib.request
    body = {"provider": provider, "model": model, "messages": messages}
    # 2026-08-14 修复: 网关默认 thinking 开, deepseek-v4 推理吃光预算
    # → content 空。llm_reply 默认关思考（需思考的场景再显式开）。
    body["thinking"] = {"type": "disabled"}
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    # 2026-08-15 修复: deepseek-v4-flash 密集输出随机空返回 → 重试 2 次
    # （与 tool_loop._call_gateway / claim_eval 同模式, 空回复根因）。
    import time as _time
    last = ""
    for _attempt in range(3):
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                SWITCH_URL,
                data=data,
                headers={"Authorization": f"Bearer {SWITCH_KEY}",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            text = result.get("choices", [{}])[0].get(
                "message", {}).get("content", "")
            if text:
                return text
            last = text
            _time.sleep(0.4 * (_attempt + 1))
        except Exception as e:
            logger.warning("switch call failed: %s", e)
            last = ""
            _time.sleep(0.4 * (_attempt + 1))
    return last


@dataclass
class TickResult:
    """Results from one execution Tick."""
    tick: int
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    node_latency: Dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0


class BlueprintExecutor:
    """Executes a BlueprintDAG — sync DAG calls + EventLog trace (§7.2).

    Dependencies are injectable (registry-style) so production can pass the
    real CognitiveRuntimeEngine / SubgraphCompiler; defaults lazy-load.
    """

    def __init__(self, pcr_router=None, subgraph_compiler=None,
                 dual_track=None, engine=None, recovery_hook=None,
                 decision_bus=None, attribution_hook=None, learn_hook=None,
                 plan_gate=None, loop_detector=None, budget=None,
                 quality_gate=None, gate_resolver=None, error_pattern=None,
                 intervention=None, heuristic_inventory=None,
                 learning_bridge=None):
        self._pcr_router = pcr_router
        self._subgraph = subgraph_compiler
        self._dual_track = dual_track
        self._engine = engine
        # RECOVERY 执行期策略切换（P0-2）: 节点失败时调用 hook 获取替换子图。
        # hook(node, error, all_outputs) → list[BlueprintNode]（替换失败节点）
        # 或 None（不切换）。默认 None = 保持"失败留痕"原语义。
        self._recovery_hook = recovery_hook
        self._decision_bus = decision_bus
        # T6 (BIDIRECTIONAL_ATTRIBUTION): 偏差归因回调 — 工具失败/超限时
        # 按归因类型（plan/constraint/data/tool）接到对应学习层。
        self._attribution_hook = attribution_hook
        # G2 (FLOW_SELF_GROWTH): 执行成功 → 沉淀学习模板（业务流自增长）。
        # learn_hook(dag, intent, request_id) → 由调用方决定是否沉淀。
        self._learn_hook = learn_hook
        # G3 四保护（LLM_DRIVEN 安全护栏, 设计 FLOW_SELF_GROWTH §三 G3）:
        #   plan_gate     — 高风险节点暂停（checkpoint/高风险链）
        #   loop_detector — 重访节点 3 次 → 强制 checkpoint
        #   budget        — 执行期总执行次数上限（防 RECOVERY 死循环）
        #   quality_gate  — 执行后评分 → 低分降级 HYBRID 事件
        # gate_resolver(node, outputs) → {"status": "approved"|"rejected",
        #   "comment": str, "adjust": [BlueprintNode]} — 用户介入回调
        self._plan_gate = plan_gate
        self._loop_detector = loop_detector
        self._budget = budget
        self._quality_gate = quality_gate
        self._gate_resolver = gate_resolver
        self._init_protections()
        # E5: 错误模式追踪（自动反思触发源）— 节点失败/工具失败上报
        self._error_pattern = error_pattern
        if self._error_pattern is None:
            self._error_pattern = ErrorPatternTracker(decision_bus=decision_bus)
        else:
            self._error_pattern.attach_bus(decision_bus)
        # P1-2: 三层介入分级路由（strategy_switch 中风险 → proposed 待 approve）
        self._intervention = intervention
        if self._intervention is None:
            from core.agent.blueprint.intervention import InterventionRouter
            self._intervention = InterventionRouter(decision_bus=decision_bus)
        else:
            self._intervention.attach_bus(decision_bus)
        self._unified_context = None
        self._event_log = None
        # 二阶抽象（A24 / blog chapter3）: 启发注入 + 变化驱动触发
        self._heuristic_inventory = heuristic_inventory
        self._learning_bridge = learning_bridge
        # GAP-5: 回合污染跟踪（OpenClaw toolResultTaintsTurn 对齐）—
        # 工具失败/异常结果污染当前回合, 影响后续判定（llm_reply 上下文标注）
        self._turn_tainted = False

    def _lazy_inventory(self):
        """懒拿启发库存（构造注入优先, 其次 engine）。"""
        if self._heuristic_inventory is not None:
            return self._heuristic_inventory
        eng = getattr(self, "_engine", None)
        if eng is not None:
            inv = getattr(eng, "_heuristic_inventory", None)
            if inv is not None:
                self._heuristic_inventory = inv
                return inv
        return None

    def _lazy_learning_bridge(self):
        """懒拿学习桥（构造注入优先, 其次 engine）。"""
        if self._learning_bridge is not None:
            return self._learning_bridge
        eng = getattr(self, "_engine", None)
        if eng is not None:
            lb = getattr(eng, "_learning_bridge", None)
            if lb is not None:
                self._learning_bridge = lb
                return lb
        return None

    def _lazy_negative_kb(self):
        """懒拿负知识库（engine._ensure_negative_kb, 负知识约束）。"""
        eng = getattr(self, "_engine", None)
        if eng is None:
            return None
        ensure = getattr(eng, "_ensure_negative_kb", None)
        if ensure is None:
            return None
        try:
            return ensure()
        except Exception:
            return None

    def _init_protections(self):
        """懒构建四保护（无注入时用默认; 均绑定 decision_bus）。"""
        bus = self._decision_bus
        if self._plan_gate is None:
            self._plan_gate = PlanGate(decision_bus=bus, resolver=self._gate_resolver)
        else:
            self._plan_gate.attach_bus(bus)
        if self._loop_detector is None:
            self._loop_detector = LoopDetector()
        if self._budget is None:
            self._budget = Budget()
        if self._quality_gate is None:
            self._quality_gate = QualityGate(decision_bus=bus)
        else:
            self._quality_gate.attach_bus(bus)

    def _record_switch(self, node, replacements, reason):
        """记录策略切换事件（决策变更事件总线, 异步介入回看基础）。"""
        # P1-2: 优先走三层介入路由 — strategy_switch = 中风险 →
        # status=proposed（PR review 语义: 异步通知, 不阻塞执行, 可 approve/reject）
        try:
            self._intervention.route(
                kind="strategy_switch",
                dimension=f"plan.node.{node.node_id}",
                before=node.node_id,
                after=",".join(r.node_id for r in replacements),
                reason=reason,
                actor="meta" if self._recovery_hook else "agent",
            )
            return
        except Exception as e:
            logger.debug("intervention route failed, fallback to bus: %s", e)
        bus = self._decision_bus
        if bus is None and self._engine is not None:
            bus = getattr(self._engine, "_decision_bus", None)
        if bus is None:
            return
        try:
            bus.log(
                kind="strategy_switch",
                dimension=f"plan.node.{node.node_id}",
                before=node.node_id,
                after=",".join(r.node_id for r in replacements),
                reason=reason,
                actor="meta" if self._recovery_hook else "agent",
            )
        except Exception as e:
            logger.debug("decision switch record failed: %s", e)

    # ─── Component accessors (injectable, lazy defaults) ───

    def _get_subgraph_compiler(self):
        if self._subgraph is None:
            from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
            self._subgraph = SubgraphCompiler(engine=self._engine)
        return self._subgraph

    def _get_dual_track(self):
        if self._dual_track is None:
            from core.agent.intent.dual_track import DualTrackIntentPipeline
            self._dual_track = DualTrackIntentPipeline()
        return self._dual_track

    def _get_unified_context(self):
        if self._unified_context is None:
            from core.agent.assembly.unified_context import UnifiedContext
            self._unified_context = UnifiedContext()
        return self._unified_context

    def _get_event_log(self):
        """Lazy EventLog (git-style trace). False sentinel = unavailable."""
        if self._event_log is None:
            try:
                from core.agent.api.api_event_log import EventLog
                el = EventLog(db_path="data/event_log.db")
                el.open()
                self._event_log = el
            except Exception as e:
                logger.warning("EventLog unavailable: %s", e)
                self._event_log = False
        return self._event_log or None

    # ─── Main loop ───

    def execute(self, dag: BlueprintDAG, user_text: str = "",
                request_id: str = None) -> Dict[str, Any]:
        """Execute a BlueprintDAG and return aggregated results.

        Returns dict: chain_outputs / llm_reply / latency_ms / ticks / quality.
        Same contract as v3_session_api + agent_native.process_dag expect.
        """
        t0 = time.time()
        self._turn_tainted = False
        all_outputs: Dict[str, Any] = {}
        completed: set = set()
        ticks: List[TickResult] = []
        # G3: 执行期保护 — 总执行次数预算（RECOVERY/PlanGate adjust 会放大）
        self._loop_detector.reset()
        max_exec = self._budget.max_executions(dag)
        exec_count = 0

        tick_groups: Dict[int, List[str]] = {}
        for n in dag.nodes:
            tick_groups.setdefault(n.priority, []).append(n.node_id)

        for tick_num in sorted(tick_groups.keys()):
            tick_start = time.time()
            pending = list(tick_groups[tick_num])
            tick_result = TickResult(tick=tick_num)

            # Multi-pass convergence: same-tick nodes may depend on each other
            # in any definition order (LLM_DRIVEN output is unordered).
            while pending:
                progressed = False
                for node_id in list(pending):
                    node = dag.get_node(node_id)
                    if node is None:
                        pending.remove(node_id)
                        continue
                    incoming = dag.incoming_edges(node.node_id)
                    deps_ready = all(
                        e.from_node in completed or not e.required
                        for e in incoming
                    )
                    if not deps_ready:
                        continue
                    pending.remove(node_id)
                    node_t0 = time.time()
                    # G3 预算保护: 总执行次数超限 → 剩余节点标记 skipped
                    exec_count += 1
                    if exec_count > max_exec:
                        for pend_id in list(pending):
                            logger.warning("Node %s budget exceeded — skipping", pend_id)
                            all_outputs[pend_id] = {
                                "status": "skipped",
                                "error": "execution budget exceeded",
                            }
                            tick_result.errors[pend_id] = "budget exceeded"
                        pending.clear()
                        progressed = True
                        break
                    # G3 LoopDetector: 重访计数 + 超阈值强制 checkpoint
                    self._loop_detector.visit(node.node_id)
                    loop_hit = self._loop_detector.requires_checkpoint(node.node_id)
                    # G3 PlanGate: checkpoint 节点/高风险链执行前暂停 → 用户裁决
                    if loop_hit or self._plan_gate.requires_gate(node):
                        verdict = self._plan_gate.resolve(
                            node, all_outputs,
                            request_id=request_id or "", turn=len(ticks),
                        )
                        if verdict["status"] == "rejected":
                            output = {
                                "status": "error",
                                "error": f"plan_gate rejected: {verdict.get('comment', '')[:120]}",
                            }
                            tick_result.node_latency[node.node_id] = (time.time() - node_t0) * 1000
                            all_outputs[node.node_id] = output
                            tick_result.outputs[node.node_id] = output
                            completed.add(node.node_id)
                            self._log_node(node, output, tick_num)
                            progressed = True
                            continue
                        if verdict.get("adjust"):
                            # adjust: 替换节点（同 RECOVERY 语义）
                            self._apply_replacements(
                                dag, node, verdict["adjust"],
                                pending, tick_result, all_outputs, completed,
                            )
                            progressed = True
                            continue
                    try:
                        output = self._execute_chain(node, all_outputs, user_text)
                    except Exception as e:
                        logger.warning("Node %s failed: %s", node.node_id, e)
                        output = {"status": "error", "error": str(e)[:200]}
                    # E5: 错误模式上报（节点失败 → 滑动窗口计数 → meta_advice）
                    if output.get("status") == "error":
                        err_text = str(output.get("error", ""))
                        try:
                            self._error_pattern.record(
                                classify_error(err_text),
                                example=f"{node.chain}:{node.node_id} {err_text[:100]}",
                                request_id=request_id or "",
                                turn=len(ticks),
                            )
                        except Exception as e:
                            logger.debug("error pattern record failed: %s", e)
                    # RECOVERY 执行期策略切换（P0-2）: 节点失败 → hook 提供
                    # 替换子图 → 替换进 DAG → 重跑（替换节点挂到当前 Tick）。
                    if output.get("status") == "error" and self._recovery_hook is not None:
                        try:
                            replacements = self._recovery_hook(
                                node, output.get("error", ""), all_outputs,
                            ) or []
                            if replacements:
                                self._record_switch(
                                    node, replacements,
                                    f"node failed: {output.get('error', '')[:80]}",
                                )
                                self._apply_replacements(
                                    dag, node, replacements,
                                    pending, tick_result, all_outputs, completed,
                                )
                                logger.info(
                                    "RECOVERY: node %s → %s",
                                    node.node_id,
                                    ",".join(r.node_id for r in replacements),
                                )
                                progressed = True
                                continue
                        except Exception as e:
                            logger.warning("RECOVERY hook failed: %s", e)
                    tick_result.node_latency[node.node_id] = (time.time() - node_t0) * 1000
                    all_outputs[node.node_id] = output
                    tick_result.outputs[node.node_id] = output
                    completed.add(node.node_id)
                    self._log_node(dag.get_node(node_id), output, tick_num)
                    progressed = True
                if not progressed:
                    for pend_id in pending:
                        logger.warning("Node %s deps not ready — skipping", pend_id)
                        all_outputs[pend_id] = {"status": "skipped",
                                                "error": "dependencies not satisfied"}
                        tick_result.errors[pend_id] = "deps not ready"
                    break

            tick_result.latency_ms = (time.time() - tick_start) * 1000
            ticks.append(tick_result)

        llm_reply = ""
        for n in dag.nodes:
            if n.chain == "llm_reply" and n.node_id in all_outputs:
                out = all_outputs[n.node_id]
                llm_reply = out.get("response", out.get("content", ""))
                break

        # G3 QualityGate: 执行后质量评分 → 低分降级 HYBRID 事件（可回看/介入）
        quality = self._quality_gate.evaluate(
            dag, all_outputs, llm_reply, strategy=dag.strategy,
            request_id=request_id or "", turn=len(ticks),
        )

        total_ms = (time.time() - t0) * 1000
        logger.info("BlueprintExecutor: executed %d nodes in %d ticks (%.0fms)",
                    len(completed), len(ticks), total_ms)
        self._save_snapshot(dag, all_outputs, total_ms, request_id)

        # G2: 执行成功且含 tool 节点 → learn_hook 沉淀模板（业务流自增长）
        if self._learn_hook is not None:
            try:
                self._learn_hook(dag, all_outputs, request_id)
            except Exception as e:
                logger.debug("learn hook failed: %s", e)

        return {
            "chain_outputs": all_outputs,
            "llm_reply": llm_reply,
            "latency_ms": total_ms,
            "quality": quality,
            "tainted": self._turn_tainted,
            "ticks": [{
                "tick": t.tick,
                "nodes": list(t.outputs.keys()),
                "errors": t.errors,
                "node_latency": t.node_latency,
                "latency_ms": t.latency_ms,
            } for t in ticks],
        }

    def _apply_replacements(self, dag, node, replacements,
                            pending, tick_result, all_outputs, completed):
        """DAG 手术（RECOVERY + PlanGate adjust 共用）:

        移除失败/被替换节点自身 → 出边重定向到替换节点 → 替换节点入 DAG
        → 直接下游失效重跑（保留已完成上游）。"""
        dag.nodes = [n for n in dag.nodes if n.node_id != node.node_id]
        new_edges = []
        for e in dag.edges:
            if e.from_node == node.node_id:
                # 出边重定向到替换节点（下游继续依赖新数据源）
                e.from_node = replacements[0].node_id
                new_edges.append(e)
            elif e.to_node == node.node_id:
                continue  # 入边删除（替换节点自包含）
            else:
                new_edges.append(e)
        dag.edges = new_edges
        # 替换节点入 DAG（priority 同失败节点）
        for r in replacements:
            dag.nodes.append(r)
        # 替换节点加入当前 pending 重跑
        pending.extend(r.node_id for r in replacements)
        tick_result.outputs.pop(node.node_id, None)
        all_outputs.pop(node.node_id, None)
        completed.discard(node.node_id)
        # 失败节点的直接下游重新执行（保留已完成上游, 如 pcr/intent）
        affected = set()
        for e in dag.edges:
            if e.from_node == replacements[0].node_id:
                affected.add(e.to_node)
        for other in dag.nodes:
            if other.node_id in affected:
                completed.discard(other.node_id)
                tick_result.outputs.pop(other.node_id, None)
                all_outputs.pop(other.node_id, None)
                pending.append(other.node_id)

    def _save_snapshot(self, dag: BlueprintDAG, all_outputs: dict,
                       latency_ms: float, request_id: Optional[str]):
        """Persist DAG snapshot (§7.5): nodes/edges/outputs summaries.

        Written as JSON to data/blueprint_dags/<request_id>.json. Summaries
        (not full outputs) keep it small — the git-style trace base for
        subgraph expand_from_dag_trace and multi-turn provenance.
        """
        if not request_id:
            return
        try:
            import os
            from pathlib import Path
            snap_dir = Path("data") / "blueprint_dags"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "request_id": request_id,
                "ts": time.time(),
                "strategy": dag.strategy,
                "nodes": [{
                    "node_id": n.node_id,
                    "chain": n.chain,
                    "priority": n.priority,
                    "checkpoint": n.checkpoint,
                    "params": {k: str(v)[:100] for k, v in n.params.items()},
                } for n in dag.nodes],
                "edges": [{
                    "from": e.from_node, "to": e.to_node,
                    "data_key": e.data_key, "required": e.required,
                } for e in dag.edges],
                "outputs": {
                    nid: {"status": out.get("status", "ok"),
                          "summary": self._summarize(out)[:300]}
                    for nid, out in all_outputs.items()
                },
                "latency_ms": round(latency_ms, 1),
            }
            path = snap_dir / f"{request_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.debug("DAG snapshot write failed: %s", e)

    def _log_node(self, node: BlueprintNode, output: dict, tick: int):
        """Record node output to EventLog (git-style trace, §7.5 base)."""
        el = self._get_event_log()
        if not el:
            return
        status = output.get("status", "ok")
        try:
            el.put_event(
                event_id=f"bp_{int(time.time()*1000)}_{node.node_id}",
                kind=f"blueprint.{node.chain}",
                payload={
                    "node": node.node_id,
                    "chain": node.chain,
                    "tick": tick,
                    "status": status,
                    "summary": self._summarize(output)[:500],
                },
            )
        except Exception as e:
            logger.debug("EventLog node write failed: %s", e)

    # ─── Dispatch ───

    def _execute_chain(self, node: BlueprintNode, all_outputs: dict,
                       user_text: str) -> Dict[str, Any]:
        handlers = {
            "pcr": self._handle_pcr,
            "intent": self._handle_intent,
            "context": self._handle_context,
            "subgraph": self._handle_subgraph,
            "profile": self._handle_profile,
            "llm_reply": self._handle_llm_reply,
            "tool": self._handle_tool,
            "behavior": self._handle_behavior,
            "meta": self._handle_meta,
            "discourse": self._handle_discourse,
            "association": self._handle_association,
            "engineering": self._handle_engineering,
            "metap": self._handle_metap,
        }
        handler = handlers.get(node.chain, self._handle_default)
        return handler(node, all_outputs, user_text)

    def _handle_tool(self, node, outputs, text) -> dict:
        """G1+T2+T4 (FLOW_SELF_GROWTH + BIDIRECTIONAL_ATTRIBUTION): 工具执行.

        node.params: {tool, args, max_steps: 3}
        P1-5 多工具并行: params.parallel = [{tool, args}, ...] →
          同一 tool 节点内并发执行（ThreadPoolExecutor）, 结果聚合。
        T2: 调用前校验（工具存在 + 必填参数完整, 不盲执行）
        T4 (ReAct 子循环): 执行结果不足/失败 → LLM 看结果再决策
        （改参数/换工具/完成）, 每步写 decision_bus 事件, 超 max_steps 终止。
        """
        parallel = node.params.get("parallel") or []
        if parallel:
            return self._handle_tool_parallel(node, parallel, text)
        batch = node.params.get("batch") or []
        if batch:
            return self._handle_tool_batch(node, batch, text)
        tool_name = node.params.get("tool", "")
        args = dict(node.params.get("args", {}) or {})
        max_steps = max(1, int(node.params.get("max_steps", 3)))
        try:
            # 确保 builtin 工具已注册（惰性 import）
            try:
                import core.agent.tools.builtin  # noqa: F401
            except Exception:
                pass
            from core.agent.tools.registry import ToolRegistry

            step = 0
            while step < max_steps:
                step += 1
                if not tool_name:
                    return {"status": "error",
                            "error": "tool node missing 'tool' param"}
                tool = ToolRegistry.resolve(tool_name, auto_install=False)
                schema = tool.input_schema or {}
                missing = [
                    k for k, v in schema.items()
                    if "optional" not in str(v).lower() and "default" not in str(v).lower()
                    and (k not in args or args.get(k) in (None, ""))
                ]
                if missing:
                    return {"status": "error",
                            "error": f"tool '{tool_name}' missing required args: {missing}",
                            "tool": tool_name}
                # 负知识约束（TieredNegativeKB）: HARD_BLOCK → 拦截; WARN → taint
                nk = self._lazy_negative_kb()
                if nk is not None:
                    try:
                        import json as _json
                        nr = nk.check(
                            f"{tool_name} {_json.dumps(args, ensure_ascii=False)}")
                        if nr.blocked:
                            return {"status": "blocked", "reason": "negative_kb",
                                    "message": getattr(nr, "message", ""),
                                    "tool": tool_name}
                        if getattr(nr, "level", None) in ("warn", "soft_discourage"):
                            self._turn_tainted = True  # GAP-5 联动: 需注意
                    except Exception as e:
                        logger.debug("negative kb check failed: %s", e)
                result = ToolRegistry.execute(tool_name, **args)
                self._record_tool_step(node, tool_name, args, result, step)
                if result.success:
                    if step < max_steps and self._tool_result_insufficient(
                            tool_name, result.data):
                        decision = self._llm_decide_tool(
                            tool_name, args, result, text, step, failed=False)
                        if decision.get("done"):
                            return {
                                "status": "ok", "tool": tool_name,
                                "tool_result": result.data,
                                "summary": self._summarize_tool_result(tool_name, result.data),
                                "react_steps": step,
                            }
                        tool_name = decision.get("tool", tool_name)
                        args = dict(decision.get("args", args))
                        continue
                    return {
                        "status": "ok", "tool": tool_name,
                        "tool_result": result.data,
                        "summary": self._summarize_tool_result(tool_name, result.data),
                        "react_steps": step,
                    }
                if step >= max_steps:
                    break
                decision = self._llm_decide_tool(
                    tool_name, args, result, text, step, failed=True)
                if decision.get("done") or not (decision.get("tool") or decision.get("args")):
                    break
                tool_name = decision.get("tool", tool_name)
                args = dict(decision.get("args", args))
            return {"status": "error",
                    "error": f"tool '{tool_name}' failed after {max_steps} steps",
                    "tool": tool_name}
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            return {"status": "error", "error": str(e)[:200], "tool": tool_name}

    def _handle_tool_parallel(self, node, parallel: list, text: str) -> dict:
        """P1-5: 多工具并行 — 同 Tick 内并发执行多个工具（OpenClaw 对齐）.

        parallel: [{"tool": "name", "args": {...}}, ...]
        并发上限 5（防资源滥用）; 每个工具独立校验/执行; 结果聚合
        {"tool_results": {tool: data}, "errors": {tool: err}}。
        """
        return self._execute_tool_specs(parallel)

    def _execute_tool_specs(self, specs: list) -> dict:
        """工具规格列表执行（校验 + ThreadPool 并发, 结果聚合）。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(spec: dict) -> tuple:
            name = spec.get("tool", "")
            cargs = dict(spec.get("args", {}) or {})
            try:
                import core.agent.tools.builtin  # noqa: F401
                from core.agent.tools.registry import ToolRegistry
                tool = ToolRegistry.resolve(name, auto_install=False)
                schema = tool.input_schema or {}
                missing = [
                    k for k, v in schema.items()
                    if "optional" not in str(v).lower() and "default" not in str(v).lower()
                    and (k not in cargs or cargs.get(k) in (None, ""))
                ]
                if missing:
                    return (name, None, f"missing required args: {missing}")
                result = ToolRegistry.execute(name, **cargs)
                if result.success:
                    return (name, result.data, None)
                return (name, None, result.error or "tool failed")
            except Exception as e:
                return (name, None, str(e)[:200])

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        specs = list(specs)[:5]
        with ThreadPoolExecutor(max_workers=min(len(specs), 5)) as pool:
            futures = {pool.submit(_run_one, s): s for s in specs}
            # 2026-08-13 修复: 结果按工具名 key, 同名工具（如批次内两个
            # file_read）互相覆盖, 只留最后一个（全量跑时随机丢内容）。
            # 现同名工具按出现序 key 为 name#2/#3..., 结果不丢。
            seen_names: Dict[str, int] = {}
            for fut in as_completed(futures):
                name, data, err = fut.result()
                seen_names[name] = seen_names.get(name, 0) + 1
                key = (f"{name}#{seen_names[name]}"
                       if seen_names[name] > 1 else name)
                if err:
                    errors[key] = err
                else:
                    results[key] = data
        status = "ok" if results and not errors else (
            "error" if errors and not results else "partial")
        return {
            "status": status,
            "tool": "parallel",
            "tool_results": results,
            "errors": errors,
            "summary": self._summarize_parallel(results, errors),
            "parallel": [s.get("tool") for s in specs],
        }

    def _handle_tool_batch(self, node, batch: list, text: str) -> dict:
        """GAP-3: 工具批次级介入（OpenClaw beforeToolBatch 对齐）.

        batch: [{"tool": "name", "args": {...}}, ...] — 同一节点内一批工具调用
        合并为一个决策事件（批维度 approve/reject）:
          1. 逐工具调用前校验（T2 必填参数, 不盲执行）
          2. 风险分级（RiskClassifier.classify_tool: 写/删/花钱→high, 只读→low）
          3. 批次介入（InterventionRouter.route_batch → 单一 tool_batch 事件）
          4. 含高危 → 整批拦截（sync_required, 待确认后重跑, 事件留痕）
             否则 → 并发执行（复用 _execute_tool_specs）
        """
        specs = list(batch)[:8]
        if not specs:
            return {"status": "error", "error": "tool batch empty"}
        validated: List[Dict[str, Any]] = []
        for spec in specs:
            name = spec.get("tool", "")
            cargs = dict(spec.get("args", {}) or {})
            if not name:
                return {"status": "error", "error": "tool batch item missing 'tool'"}
            try:
                import core.agent.tools.builtin  # noqa: F401
                from core.agent.tools.registry import ToolRegistry
                tool = ToolRegistry.resolve(name, auto_install=False)
                schema = tool.input_schema or {}
                missing = [
                    k for k, v in schema.items()
                    if "optional" not in str(v).lower() and "default" not in str(v).lower()
                    and (k not in cargs or cargs.get(k) in (None, ""))
                ]
                if missing:
                    return {"status": "error",
                            "error": f"tool '{name}' missing required args: {missing}",
                            "tool": name}
            except Exception as e:
                return {"status": "error",
                        "error": f"tool '{name}' resolve failed: {e}", "tool": name}
            validated.append({"tool": name, "args": cargs})
        try:
            r = self._intervention.route_batch(
                tools=validated,
                dimension=f"tool_batch.{node.node_id}",
                turn=int(getattr(self, "_turn", 0) or 0),
            )
        except Exception as e:
            logger.debug("tool batch route failed: %s", e)
            r = {"level": "low", "status": "applied", "sync_required": False}
        if r.get("sync_required"):
            return {
                "status": "blocked",
                "reason": "tool_batch_approval_required",
                "tools": [v["tool"] for v in validated],
                "level": r.get("level", "high"),
                "event": r.get("event"),
            }
        return self._execute_tool_specs(validated)

    def _summarize_parallel(self, results: dict, errors: dict) -> str:
        parts = []
        for name, data in list(results.items())[:5]:
            parts.append(f"{name}: {str(data)[:120]}")
        for name, err in list(errors.items())[:3]:
            parts.append(f"{name}: ERROR {err[:80]}")
        return " | ".join(parts) if parts else "（空）"

    def _record_tool_step(self, node, tool_name, args, result, step):
        """T4+T5: 每步写 decision_bus 事件（可回看/介入 + 归因）。

        T5 (BIDIRECTIONAL_ATTRIBUTION): 失败事件带 attribution —
        tool 失败默认归因 tool, 可被上层覆盖为 plan/constraint/data。
        """
        attribution = "tool" if not result.success else "none"
        # GAP-5: 失败/异常结果 → 污染当前回合
        if not result.success:
            self._turn_tainted = True
        # 二阶抽象: 工具失败 → 变化触发（on_tool_failure → 反向掩盖发散）
        if not result.success:
            lb = self._lazy_learning_bridge()
            if lb is not None:
                try:
                    lb.on_tool_failure(tool_name, result.error or "")
                except Exception as e:
                    logger.debug("tool failure trigger failed: %s", e)
        # T6: 归因回流（独立于 decision_bus — 无 bus 也要回流学习）
        if not result.success and self._attribution_hook is not None:
            try:
                self._attribution_hook(tool_name, args, result.error, attribution)
            except Exception as e:
                logger.debug("attribution hook failed: %s", e)
        try:
            bus = self._decision_bus
            if bus is None and self._engine is not None:
                bus = getattr(self._engine, "_decision_bus", None)
            if bus is None:
                return
            bus.log(
                kind="strategy_switch",
                dimension=f"tool.{tool_name}.step{step}",
                before={"args": args},
                after={"success": result.success,
                       "error": result.error if not result.success else None,
                       "tainted": not result.success},
                reason=f"tool step {step}: {'ok' if result.success else 'failed'}",
                actor="agent",
                attribution=attribution,
            )
        except Exception as e:
            logger.debug("tool step record failed: %s", e)

    def _tool_result_insufficient(self, tool_name, data) -> bool:
        """工具结果是否足够（启发式: 空结果/明显失败标记 = 不足）。"""
        if data is None:
            return True
        if isinstance(data, dict):
            if not data:
                return True
            for k in ("text", "content", "papers", "results"):
                if k in data and not data.get(k):
                    return True
        return False

    def _llm_decide_tool(self, tool_name, args, result, text, step,
                         failed: bool = False) -> dict:
        """T4: LLM 看工具结果决定下一步（改参数/换工具/完成）。"""
        try:
            status = "failed" if failed else "insufficient"
            outcome = result.error if failed else str(result.data)[:500]
            system = (
                "你是工具调度器。上一步工具调用后决定下一步。"
                "输出 JSON: {\"done\": true}（结果足够, 完成）或 "
                "{\"done\": false, \"tool\": \"工具名\", \"args\": {}}"
                "（换工具或改参数重试）。只在确有把握时重试, 否则 done。"
            )
            user = (
                f"工具: {tool_name}\n参数: {json.dumps(args, ensure_ascii=False)[:300]}\n"
                f"状态: {status}\n结果: {outcome}\n"
                f"用户目标: {text[:200]}\n"
                f"第 {step} 步, 输出下一步 JSON。"
            )
            resp = call_switch([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            data = json.loads(self._extract_json_text(resp))
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.debug("tool ReAct decision failed: %s", e)
        return {"done": True}

    def _extract_json_text(self, s: str) -> str:
        """从 LLM 回复提取 JSON 子串（markdown fence / 裸 JSON）。"""
        if not s:
            return "{}"
        import re
        m = re.search(r"\{[\s\S]*\}", s)
        return m.group(0) if m else "{}"

    def _summarize_tool_result(self, tool_name: str, data) -> str:
        """工具结果摘要（进 llm_reply 上下文, 不存全文）。"""
        detail = int(os.environ.get("DM_TOOL_DETAIL", "2000"))
        if isinstance(data, dict):
            if tool_name in ("arxiv_search",):
                papers = data.get("papers", [])
                parts = [f"{p.get('title', '')} ({p.get('published', '')})"
                         for p in papers[:5]]
                return f"找到 {data.get('count', len(papers))} 篇论文: " + "; ".join(parts)
            if tool_name in ("web_fetch", "pdf_extract"):
                text = data.get("text", "")
                return f"{tool_name}: {str(text)[:detail]}"
            if tool_name == "file_read":
                return f"file_read({data.get('path', '')}): {str(data.get('content', ''))[:detail]}"
            return str(data)[:300]
        return str(data)[:300]

    def _find_upstream(self, chain: str, all_outputs: dict) -> dict:
        for node_id, output in all_outputs.items():
            if chain in node_id:
                return output
        return {}

    def _summarize(self, output: dict) -> str:
        """Extract a short text summary from any chain output."""
        if not isinstance(output, dict):
            return str(output)[:200]
        # GAP-5: 失败/异常输出 → [不可信] 标注（污染传播到 llm_reply 上下文）
        if output.get("status") in ("error", "blocked", "unavailable") or output.get("error"):
            err = str(output.get("error", output.get("status", "")))[:120]
            return f"[不可信] {err}"
        # 2026-08-15 加固: 细节承载键（锚点/子图/工具结果）给更大上限,
        # 结构键保持 200 — 分级保留, 不统一压扁（P9 信息论分治落地）。
        detail_cap = {"compiled_subgraph": 2000, "anchors": 1500,
                      "tool_result": 2000, "response": 1200}
        for key in ("route", "segments", "intents", "compiled_subgraph",
                    "assembled_context", "profile_text", "response", "content",
                    "tool_result", "summary", "anchors"):
            if output.get(key):
                return str(output[key])[:detail_cap.get(key, 200)]
        return str(output.get("status", ""))[:100]

    # ─── Per-chain handlers (direct component calls, no fake data) ───

    def _handle_pcr(self, node, outputs, text) -> dict:
        """Real PCR V2 routing — zero-keyword structural→coordinate→zone."""
        try:
            from core.agent.pcr_router_v2 import PCRRouterV2
            router = self._pcr_router or PCRRouterV2
            result = router.route(text)
            return {
                "route": {
                    "zone": result.zone,
                    "x": result.x_axis,
                    "y": result.y_axis,
                    "z": result.z_axis,
                    "cognitive_level": getattr(result, "cognitive_level", None),
                    "execution_mode": getattr(result, "execution_mode", None),
                },
                "compass": {"labels": getattr(result, "labels", {})},
                "status": "ok",
            }
        except Exception as e:
            logger.warning("PCR unavailable: %s", e)
            return {"status": "unavailable", "error": str(e)[:200]}

    def _handle_intent(self, node, outputs, text) -> dict:
        """Real DualTrack intent parsing (hot path; cold path background)."""
        try:
            dt = self._get_dual_track()
            res = dt.process(text)
            segments = getattr(res, "segments", [])
            return {
                "intents": {
                    "segments": segments,
                    "confidence": getattr(res, "confidence", 0.5),
                    "source": getattr(res, "source", ""),
                },
                "segments": segments,
                "status": "ok",
            }
        except Exception as e:
            logger.warning("Intent unavailable: %s", e)
            return {"status": "unavailable", "error": str(e)[:200]}

    def _handle_context(self, node, outputs, text) -> dict:
        """Context assembly — UnifiedContext over upstream PCR/Intent outputs."""
        pcr_out = self._find_upstream("pcr", outputs)
        intent_out = self._find_upstream("intent", outputs)
        perception = {
            "route": pcr_out.get("route", {}),
            "intents": intent_out.get("intents", {}),
            "text": text,
        }
        try:
            ctx = self._get_unified_context().assemble(perception)
            return {"assembled_context": ctx, "status": "ok"}
        except Exception as e:
            logger.warning("Context assembly unavailable: %s", e)
            return {"status": "unavailable", "error": str(e)[:200],
                    "assembled_context": {}}

    def _handle_subgraph(self, node, outputs, text) -> dict:
        """Real SubgraphCompiler — compile_dialogue with upstream zone/intent."""
        pcr_out = self._find_upstream("pcr", outputs)
        intent_out = self._find_upstream("intent", outputs)
        zone = pcr_out.get("route", {}).get("zone")
        segments = intent_out.get("intents", {}).get("segments", [])
        intent_category = segments[0] if segments else None
        try:
            sc = self._get_subgraph_compiler()
            ctx = sc.compile_dialogue(
                intent=intent_category or "general_query",
                intent_category=intent_category,
                zone=zone,
            )
            return {"compiled_subgraph": ctx, "status": "ok"}
        except Exception as e:
            logger.warning("Subgraph compile unavailable: %s", e)
            return {"status": "unavailable", "error": str(e)[:200],
                    "compiled_subgraph": None}

    def _handle_profile(self, node, outputs, text) -> dict:
        """Fetch user profile from backend. No fake fallback — degrade empty."""
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8000/v6/profile")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            p = data.get("profile", data)
            oceAN = p.get("oceAN_dims", {})
            mbti = p.get("mbti", "N/A")
            bfi = p.get("bfi_latest", {})
            profile_text = (
                f"MBTI: {mbti} | "
                f"OCEAN: O={oceAN.get('O',0):.2f} C={oceAN.get('C',0):.2f} "
                f"E={oceAN.get('E',0):.2f} A={oceAN.get('A',0):.2f} N={oceAN.get('N',0):.2f} | "
                f"BFI-C: {bfi.get('C','N/A')}"
            )
            return {"profile_text": profile_text, "mbti": mbti, "status": "ok"}
        except Exception as e:
            logger.warning("Profile unavailable: %s", e)
            return {"status": "unavailable", "error": str(e)[:200],
                    "profile_text": ""}

    def _handle_llm_reply(self, node, outputs, text) -> dict:
        """Final reply — reply_mode dispatch (§7.6). No fake reply."""
        mode = node.params.get("reply_mode", "llm")
        blocks = []
        for nid, out in outputs.items():
            if nid == node.node_id:
                continue
            # 2026-08-15 加固（P9/A7 细节保留）: recall/subgraph 节点
            # 的锚点全文进上下文（此前 _summarize 只取 200 字符摘要,
            # 数字/细节在摘要里失真 → 事实矛盾幻觉的根因之一）。
            if nid.startswith(("recall", "subgraph")):
                detail = self._detail_block(out)
                if detail:
                    blocks.append(f"[{nid}] {detail}")
                continue
            summary = self._summarize(out)
            if summary:
                blocks.append(f"[{nid}] {summary}")
        context_block = "\n".join(blocks)

        if mode == "template":
            # Deterministic fast-path reply: summarize aggregated context only.
            reply = context_block[:500] if context_block else "（无上游上下文）"
            return {"response": reply, "mode": "template", "status": "ok"}

        # mode=llm (default): switch-gateway call with aggregated context
        system = ("你是 DialogMesh 认知助手。基于管线分析上下文生成最终回复。"
                  "回答必须基于上下文：数字、结论、细节必须来自上下文；"
                  "上下文不足时明确说明不知道，不编造。")
        user = f"用户: {text}\n\n管线上下文:\n{context_block}"
        # 二阶抽象: 启发注入决策上下文（与 engineering 约束并列, A19 白盒）
        inv = self._lazy_inventory()
        if inv is not None:
            try:
                heuristics_block = inv.format_for_prompt(query=text, top_k=4)
                if heuristics_block:
                    user += f"\n\n{heuristics_block}"
            except Exception as e:
                logger.debug("heuristic inject failed: %s", e)
        reply = call_switch([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        if reply:
            return {"response": reply, "mode": "llm", "status": "ok"}
        return {"status": "unavailable", "error": "switch call failed",
                "response": ""}

    def _detail_block(self, out: dict) -> str:
        """细节节点输出 → 全文块（recall/subgraph 锚点, 2026-08-15）。"""
        if not isinstance(out, dict):
            return ""
        hits = out.get("hits") or []
        parts = []
        # 变体档位（蓝图多样性, 2026-08-15）: 消融可调, 默认 top-3 × 1200
        top_n = int(os.environ.get("DM_CTX_DETAIL_TOP", "3"))
        chars = int(os.environ.get("DM_CTX_DETAIL_CHARS", "1200"))
        for h in hits[:top_n]:
            text = h.get("full_text") or h.get("text") or ""
            path = (h.get("path") or ["?"])[0]
            if text:
                parts.append(f"- {path}: {text[:chars]}")
        if parts:
            return "\n".join(parts)
        return str(out.get("anchors")
                   or out.get("compiled_subgraph") or "")[:1500]

    # ─── Async-consumption stubs (explicit, no fake work) ───

    def _handle_behavior(self, node, outputs, text) -> dict:
        """GAP-E2（COMPLETENESS_GAP_INVENTORY §B）: 行为链节点真接线.

        原占位 deferred → 真实调 engine._run_behavior_brain(event):
          行为学习（预测评估/DPO 偏好/承诺识别/画像更新）+ 背景预测 +
          冷启动回退重模拟 + CausalPlanner.record_step（因果链）。
        无 engine/brain 时显式 unavailable（不做伪数据）。
        """
        eng = getattr(self, "_engine", None)
        run_fn = getattr(eng, "_run_behavior_brain", None) if eng is not None else None
        if run_fn is None:
            return {"status": "unavailable",
                    "note": "行为链: engine._run_behavior_brain 未接线"}
        try:
            from types import SimpleNamespace
            event = SimpleNamespace(
                kind="blueprint.behavior",
                payload={"text": text or "", "node": node.node_id},
            )
            run_fn(event)
            brain = getattr(eng, "_behavior_brain", None)
            return {
                "status": "ok",
                "learned": bool(brain),
                "note": "行为链: learn_from_event + background predict",
                "stats": brain.stats() if brain is not None and
                         hasattr(brain, "stats") else None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    def _handle_meta(self, node, outputs, text) -> dict:
        """GAP-E1（COMPLETENESS_GAP_INVENTORY §B）: 元认知节点真接线.

        原占位 async → 真实调 engine._run_meta_consume():
          ExecutionTraceV3 → MetaConsumer 建议 → 审核队列（每 5 轮闭环）。
        同时把 QualityGate 评分/执行摘要写入 trace（元认知原料）。
        无 engine 时显式 unavailable（不做伪数据）。
        """
        eng = getattr(self, "_engine", None)
        if eng is None:
            return {"status": "unavailable", "note": "元认知: engine 未接线"}
        try:
            # 1) 执行摘要入 trace（元认知原料）
            trace = getattr(eng, "_trace_v3", None)
            if trace is not None and hasattr(trace, "record_transition"):
                quality = outputs.get("quality", {}) or {}
                try:
                    from core.agent.state.state_object import (
                        StateObject, TransitionReason,
                    )
                    if not getattr(trace, "states", None):
                        trace.snapshot(StateObject(id="root", data={"stage": "blueprint"}))
                    trace.record_transition(
                        reason=TransitionReason.OBSERVE,
                        from_state=StateObject(id="root", data={"stage": "start"}),
                        to_state=StateObject(id="meta", data={
                            "stage": "meta_audit",
                            "quality": quality.get("score"),
                            "degraded": quality.get("degraded"),
                            "node": node.node_id,
                        }),
                        evidence=[f"blueprint:{node.node_id}"],
                    )
                except Exception as e:
                    logger.debug("meta trace record failed: %s", e)
            # 2) 真实元认知消费（建议 → 审核队列）
            advice = eng._run_meta_consume() if hasattr(eng, "_run_meta_consume") else {}
            return {
                "status": "ok",
                "advice": advice,
                "note": "元认知: trace 记录 + MetaConsumer 消费",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    def _handle_discourse(self, node, outputs, text) -> dict:
        return {"status": "deferred", "note": "对话树: 后续接入"}

    def _handle_association(self, node, outputs, text) -> dict:
        """关联链独立服务接入（蓝图 §7.3，M→1 定向通道，不广播）。

        DAG 的 association 节点产出 → 定向投递到 engine 的
        AssociationService（EventLog 一次写入 + last_seq 增量消费）。
        无 engine/service 时显式返回 unavailable（不做伪数据）。
        """
        service = None
        eng = getattr(self, "_engine", None)
        if eng is not None:
            service = getattr(eng, "_assoc_service", None)
        if service is None:
            return {"status": "unavailable",
                    "note": "关联链独立服务未接线（engine._assoc_service 缺失）"}
        try:
            payload = {
                "text": text or "",
                "node": node.node_id,
                "upstream": self._find_upstream("intent", outputs),
            }
            ok = service.enqueue("intent_parsed", {
                "category": payload["upstream"].get("category", "general")
                if payload["upstream"] else "general",
                "text": payload["text"],
            })
            service.enqueue("route_generated", {
                "zone": payload["upstream"].get("zone", "MIXED")
                if payload["upstream"] else "MIXED",
            })
            return {
                "status": "enqueued" if ok else "dropped",
                "service": "association",
                "note": "定向投递（M→1），EventLog 已记录",
                "stats": service.stats(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    def _handle_engineering(self, node, outputs, text) -> dict:
        return {"status": "deferred", "note": "工程链: 待接入"}

    def _handle_metap(self, node, outputs, text) -> dict:
        return {"status": "async", "note": "元持久化: 后台"}

    def _handle_default(self, node, outputs, text) -> dict:
        return {"status": "unknown_chain", "chain": node.chain}
