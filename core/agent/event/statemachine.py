"""P2: State Machine Engine — Decider-driven pipeline coordination.

Currently the Decider just records ticks. This makes it actually DECIDE:
  1. What chains to run based on current state
  2. When to escalate (low confidence → deep path)
  3. When to skip (cache hit → fast path)
  4. Checkpoint after each decision for replay

Design: DESIGN_GLOBAL_STATE_MACHINE.md + LangGraph conditional_edges pattern.
"""
import threading, time, json, logging
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PipelinePhase(Enum):
    """Pipeline phases — the Decider routes through these."""
    IDLE = "idle"
    PCR = "pcr"               # Pre-cognitive routing
    INTENT = "intent"         # Intent parsing
    PLANNING = "planning"     # Blueprint / plan generation
    CONTEXT = "context"       # Context assembly + subgraph
    LLM = "llm"               # LLM generation
    DISCOURSE = "discourse"   # Discourse tree update
    BEHAVIOR = "behavior"     # Behavior graph
    META = "meta"             # Meta cognition review
    PROFILE = "profile"       # OCEAN analysis
    PERSIST = "persist"       # Persistence to storage
    ASSOCIATION = "association"  # L1 + L2.5 chain
    DONE = "done"


STATE_TRANSITIONS: Dict[PipelinePhase, Dict[str, PipelinePhase]] = {
    # Normal flow: PCR → Intent → Planning → Context → LLM → (subsystems) → DONE
    PipelinePhase.IDLE:      {"start": PipelinePhase.PCR},
    PipelinePhase.PCR:       {"normal": PipelinePhase.INTENT, "skip": PipelinePhase.LLM},
    PipelinePhase.INTENT:    {"normal": PipelinePhase.PLANNING, "simple": PipelinePhase.LLM},
    PipelinePhase.PLANNING:  {"normal": PipelinePhase.CONTEXT, "skip": PipelinePhase.LLM},
    PipelinePhase.CONTEXT:   {"normal": PipelinePhase.LLM},
    PipelinePhase.LLM:       {"normal": PipelinePhase.DISCOURSE, "error": PipelinePhase.DONE},
    PipelinePhase.DISCOURSE: {"normal": PipelinePhase.BEHAVIOR},
    PipelinePhase.BEHAVIOR:  {"normal": PipelinePhase.META},
    PipelinePhase.META:      {"normal": PipelinePhase.PROFILE},
    PipelinePhase.PROFILE:   {"normal": PipelinePhase.PERSIST},
    PipelinePhase.PERSIST:   {"normal": PipelinePhase.DONE},
}

# G1+G3-P2: Blueprint chain → PipelinePhase 映射（DAG 节点执行用）
CHAIN_TO_PHASE = {
    "pcr": PipelinePhase.PCR,
    "intent": PipelinePhase.INTENT,
    "context": PipelinePhase.CONTEXT,
    "subgraph": PipelinePhase.CONTEXT,
    "llm_reply": PipelinePhase.LLM,
    "behavior": PipelinePhase.BEHAVIOR,
    "meta": PipelinePhase.META,
    "metap": PipelinePhase.META,
    "discourse": PipelinePhase.DISCOURSE,
    "association": PipelinePhase.ASSOCIATION,
    "profile": PipelinePhase.PROFILE,
    "engineering": PipelinePhase.PLANNING,
}


@dataclass 
class StateSnapshot:
    """Snapshot of engine state for the Decider to make decisions."""
    phase: PipelinePhase = PipelinePhase.IDLE
    turn_count: int = 0
    last_pcr_zone: str = "MIXED"
    confidence: float = 0.5
    errors_in_phase: int = 0
    total_latency_ms: float = 0
    chain_results: Dict[str, Any] = field(default_factory=dict)
    checkpoint: Optional[str] = None


class DeciderStateMachine:
    """Coordinates pipeline execution by deciding what phase runs next.

    Replaces hardcoded on_event serial chain with state-driven routing.
    Pattern: LangGraph conditional_edges — each phase decides "where next?"
    """

    def __init__(self):
        self._state = StateSnapshot()
        self._lock = threading.Lock()
        self._history: List[StateSnapshot] = []
        self._phase_handlers: Dict[PipelinePhase, Callable] = {}
        self._running = True
        # G1+G3-P5: GlobalDecider 状态底座（复用 registry 实例, 不暴露新决策器）
        self._decider = None

    def register_handler(self, phase: PipelinePhase, handler: Callable):
        """Register a function to execute when this phase is reached."""
        self._phase_handlers[phase] = handler

    def current_phase(self) -> PipelinePhase:
        return self._state.phase

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                phase=self._state.phase,
                turn_count=self._state.turn_count,
                last_pcr_zone=self._state.last_pcr_zone,
                confidence=self._state.confidence,
                errors_in_phase=self._state.errors_in_phase,
                total_latency_ms=self._state.total_latency_ms,
            )

    def decide(self, phase: PipelinePhase, result: dict = None) -> PipelinePhase:
        """Given current phase and result, decide next phase.

        This is the core of the state machine — conditional routing.
        """
        transitions = STATE_TRANSITIONS.get(phase, {})

        if not transitions:
            return PipelinePhase.DONE

        # Decision logic based on result
        if result:
            if result.get("error"):
                # Error → skip to safe next phase
                return transitions.get("error", transitions.get("normal", PipelinePhase.DONE))
            if result.get("skip"):
                return transitions.get("skip", transitions.get("normal", PipelinePhase.DONE))
            if result.get("confidence", 0.5) < 0.3:
                # Low confidence → escalate (if available)
                pass  # Use normal path for now

            # G1+G3-P5: 记录决策事件到 GlobalDecider 状态底座（不改变路由）
            if self._decider is not None:
                try:
                    from core.agent.state.global_decider import Command
                    cmd_type = phase.value
                    cmd = Command(type=cmd_type, payload={
                        "zone": result.get("zone"),
                        "category": result.get("category"),
                        "task_count": result.get("step_count", 0),
                        "entries": result.get("ir_entries", 0),
                        "confidence": result.get("confidence"),
                    })
                    self._decider.evolve(self._decider.decide(cmd))
                except Exception:
                    pass  # 决策记录失败不影响路由

        return transitions.get("normal", PipelinePhase.DONE)

    def transition(self, to_phase: PipelinePhase, result: dict = None):
        """Record a state transition and save checkpoint."""
        with self._lock:
            self._state.phase = to_phase
            self._state.turn_count += 1
            if result:
                self._state.chain_results[to_phase.value] = result.get("summary", str(result)[:100])
                if "confidence" in result:
                    self._state.confidence = result["confidence"]

            # Checkpoint after every 3 transitions
            if self._state.turn_count % 3 == 0:
                self._state.checkpoint = f"ckpt_{self._state.turn_count}"
                self._history.append(StateSnapshot(
                    phase=self._state.phase,
                    turn_count=self._state.turn_count,
                    confidence=self._state.confidence,
                ))

    def run_pipeline(self, start_phase: PipelinePhase, context: dict = None) -> dict:
        """Execute the full pipeline from a starting phase.

        This is the state machine runtime — it iterates through phases,
        calling handlers, deciding next phase, until DONE.
        """
        current = start_phase
        results = {}
        self._state.chain_results = {}
        start_turn = self._state.turn_count  # per-run baseline for max-transition guard

        while current != PipelinePhase.DONE:
            result = {}  # X5: 每轮显式重置 — 无 handler 阶段不留上轮残留
            handler = self._phase_handlers.get(current)
            if handler:
                try:
                    # X4: 前序阶段结果注入 ctx — LLM/CONTEXT 等下游可消费
                    phase_ctx = dict(context or {})
                    phase_ctx.update(results)
                    result = handler(phase_ctx)
                    results[current.value] = result
                except Exception as e:
                    result = {"error": str(e)[:200]}
                    results[current.value] = result
            
            next_phase = self.decide(current, result)
            self.transition(current, result)
            current = next_phase

            # Safety: max 20 transitions per run (not cumulative)
            if self._state.turn_count - start_turn > 20:
                logger.warning("Pipeline exceeded max transitions, forcing DONE")
                break

        return {"phases": list(results.keys()), "checkpoint": self._state.checkpoint,
                "results": results}

    def run_dag(self, dag, context: dict = None) -> dict:
        """Execute a BlueprintDAG — 订阅表语义 (§14.3): 同 Tick 并行、跨 Tick 串行.

        Nodes are grouped by priority (= Tick). Within one Tick, ready nodes
        (dependencies satisfied) run in parallel via ThreadPoolExecutor;
        the next Tick starts only after the current Tick completes.
        async 段 (priority >= 9, meta/behavior) runs last, non-blocking order.

        Each BlueprintNode.chain maps to a registered PipelinePhase handler
        (CHAIN_TO_PHASE). Node outputs feed downstream nodes via data_key
        edges. 环形图返回 error（不执行）。
        """
        from collections import deque
        import threading
        context = dict(context or {})
        # 拓扑排序 (Kahn)
        in_degree = {n.node_id: len(dag.incoming_edges(n.node_id))
                     for n in dag.nodes}
        ready = deque(n.node_id for n in dag.nodes if in_degree[n.node_id] == 0)
        order = []
        while ready:
            nid = ready.popleft()
            order.append(nid)
            for e in dag.outgoing_edges(nid):
                in_degree[e.to_node] -= 1
                if in_degree[e.to_node] == 0:
                    ready.append(e.to_node)
        if len(order) != len(dag.nodes):
            return {"error": "DAG contains cycle", "phases": order,
                    "results": {}}

        results = {}
        node_outputs = {}
        completed: set = set()
        write_lock = threading.Lock()

        def _run_node(nid: str):
            """Execute one node; returns (node_id, output). Thread-safe."""
            node = dag.get_node(nid)
            if node is None:
                return nid, {"status": "missing"}
            # 下游数据注入提前: 上游节点输出按 data_key 提供
            # （subgraph 锚点节点 → tool 节点 data_key="anchors" 消费）.
            node_ctx = dict(context)
            node_ctx.update(results)
            for e in dag.incoming_edges(nid):
                if e.from_node in node_outputs:
                    node_ctx[e.data_key] = node_outputs[e.from_node]
            # v2.1 召回→执行层桥（RECALL_EXECUTION_BRIDGE_DESIGN §三）:
            # subgraph 节点声明 recall_anchor → 产出候选锚点（图拓扑节点,
            # 白盒可见）; 下游 tool 节点经 data_key="anchors" 依赖消费。
            if node.chain == "subgraph" and node.params.get("recall_anchor"):
                try:
                    from core.agent.recall.recall_service import (
                        RecallService, format_anchors)
                    rs = RecallService()
                    query = str(node.params.get("query")
                                or context.get("text") or "")
                    rr = rs.recall(query, top_k=int(
                        node.params.get("top_k", 5)),
                        intent=context.get("intent"),
                        sid=context.get("session_id") or "",
                        expand_graph=True)
                    anchors = format_anchors(rr, max_chars=int(
                        node.params.get("max_chars", 1200)))
                    hits = [h.to_dict() for h in (rr.hits or [])[:10]]
                    return nid, {"status": "ok", "anchors": anchors,
                                 "hits": hits, "recall": True}
                except Exception as ex:
                    return nid, {"status": "error",
                                 "error": str(ex)[:200], "anchors": ""}
            # tool 链: 蓝图工具节点 → 权限门 → ToolRegistry 执行（2026-08-08）
            if node.chain == "tool":
                try:
                    # v2 执行层（2026-08-09）: agentic 工具节点 → TaskRunner
                    # （LLM 在节点目标范围内自主调工具 + 元认知监控 + 重规划）
                    if node.params.get("agentic"):
                        from core.agent.llm.task_runner import (
                            TaskRunner, TaskConstraint)
                        goal = (node.params.get("goal")
                                or node.params.get("description", "")
                                or f"执行节点 {node.node_id}")
                        _dbus = context.get("decision_bus")
                        # 执行轨迹落树（P0）: 会话级 ExecutionTree
                        _exec_tree = None
                        try:
                            # 2026-08-15 修复: 七树容器经 context.agent_tree
                            # 注入（v3_session_api run_dag 已传）— 旧代码从
                            # discourse_tree._trees 取 execution 恒 None。
                            _mgr = getattr(context, "get", lambda k: None)(
                                "agent_tree")
                            if _mgr is None:
                                _dt = getattr(context, "get", lambda k: None)(
                                    "discourse_tree")
                                if _dt is not None and hasattr(
                                        _dt, "get_agent_tree"):
                                    _mgr = _dt.get_agent_tree(
                                        context.get("session_id") or "")
                            if _mgr is not None:
                                _exec_tree = getattr(
                                    _mgr, "execution", None)
                        except Exception:
                            _exec_tree = None
                        runner = TaskRunner(
                            decision_bus=_dbus,
                            meta_feedback=context.get("meta_feedback"),
                            model=context.get("model", ""),
                            execution_tree=_exec_tree)
                        constraint = TaskConstraint(
                            goal=goal,
                            scope=node.params.get("scope", ""),
                            allowed_tools=node.params.get("allowed_tools"),
                            max_rounds=int(node.params.get("max_rounds", 6)),
                            timeout_s=float(
                                node.params.get("timeout_s", 120)),
                            max_replans=int(
                                node.params.get("max_replans", 1)),
                        )
                        _tr = runner.run(
                            goal=goal, constraint=constraint, node_id=nid,
                            session_id=context.get("session_id", ""),
                            request_id=context.get("request_id", ""),
                            messages=context.get("messages"),
                            anchors=self._recall_anchors(
                                goal, context, node.params,
                                self._extract_anchors(node_ctx)),
                        )
                        return nid, {"status": _tr.status,
                                     "task_result": _tr.to_dict()}
                    from core.agent.blueprint.permission_engine import (
                        PermissionEngine, has_shell_operators)
                    tool = node.params.get("tool", "")
                    args = dict(node.params.get("args", {}) or {})
                    if not tool:
                        return nid, {"status": "error",
                                     "error": "tool node missing tool param"}
                    # 2026-08-13 修复（蓝图薄点实锤）: 模板工具节点参数
                    # （recall_pipeline 的 top_k/parallel）此前因缺 "args"
                    # 键从不进 handler, 工具以默认值空跑。现 params 直传:
                    # 保留键外全部作为工具 kwargs; query 缺省 = 上下文文本;
                    # 多意图 segments（intent 节点输出）注入 sub_queries。
                    _RESERVED = {"tool", "args", "agentic", "safety",
                                 "allowed_tools", "goal", "description",
                                 "scope", "max_rounds", "timeout_s",
                                 "max_replans", "recall_anchor"}
                    for _k, _v in node.params.items():
                        if _k not in _RESERVED and _k not in args:
                            args[_k] = _v
                    if tool == "recall_decompose":
                        if not args.get("query"):
                            args["query"] = context.get("text") or ""
                        if not args.get("sub_queries"):
                            _ic = node_ctx.get("intent_context") or {}
                            _segs = (_ic.get("segments") or []
                                     if isinstance(_ic, dict) else [])
                            if len(_segs) > 1:
                                args["sub_queries"] = _segs
                    decision = PermissionEngine().evaluate(tool, args)
                    if not decision.allowed:
                        if ("writable root" in decision.reason
                                or "read-only" in decision.reason):
                            return nid, {"status": "rejected",
                                         "error": decision.reason}
                        if tool == "run_shell" or tool.startswith("shell:"):
                            command = str(args.get("command", ""))
                            if has_shell_operators(command):
                                return nid, {"status": "rejected",
                                             "error": "shell chaining blocked"}
                    from core.agent.tools.registry import ToolRegistry
                    result = ToolRegistry.execute(tool, **args)
                    return nid, {
                        "status": "ok", "tool": tool,
                        "tool_result": (result.data if hasattr(result, "data")
                                        else result),
                    }
                except Exception as ex:
                    return nid, {"status": "error", "error": str(ex)[:200]}
            phase = CHAIN_TO_PHASE.get(node.chain)
            handler = self._phase_handlers.get(phase) if phase else None
            if handler:
                try:
                    out = handler(node_ctx)
                    return nid, out
                except Exception as ex:
                    return nid, {"error": str(ex)[:200]}
            return nid, {"skipped": f"no handler for chain {node.chain}"}

        # 按 Tick (priority) 分组: 同 Tick 并行, 跨 Tick 串行 (§14.3)
        tick_groups: Dict[int, List[str]] = {}
        for nid in order:
            node = dag.get_node(nid)
            tick_groups.setdefault(node.priority, []).append(nid)

        for tick in sorted(tick_groups.keys()):
            pending = list(tick_groups[tick])
            # 同 Tick 多轮收敛: 依赖可能在同一 Tick（LLM 乱序输出节点）
            while pending:
                # 只并行执行"无未完成入边依赖"的节点:
                # 有同 Tick 依赖的节点留在 pending，下一轮串行收敛
                # （避免并行读上游输出时 data_key 尚未注入的竞态）。
                batch = []
                for nid in pending:
                    incoming = dag.incoming_edges(nid)
                    if not incoming:
                        batch.append(nid)
                        continue
                    # 所有入边源节点都已完成 → 可安全并行
                    if all(
                        e.from_node in completed or not e.required
                        for e in incoming
                    ):
                        batch.append(nid)
                if not batch:
                    # 同 Tick 内依赖未满足 → 串行跳过（避免死锁）
                    for nid in pending:
                        results[nid] = {
                            "skipped": f"dependencies not satisfied in tick {tick}",
                        }
                        node_outputs[nid] = results[nid]
                        completed.add(nid)
                    break
                if len(batch) > 1:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=len(batch)) as ex:
                        futures = {ex.submit(_run_node, nid): nid for nid in batch}
                        for fut in futures:
                            nid_out, out = fut.result()
                            with write_lock:
                                results[nid_out] = out
                                node_outputs[nid_out] = out
                                completed.add(nid_out)
                    pending = [nid for nid in pending if nid not in completed]
                else:
                    # 单节点直接执行（无并发，依赖已由 batch 筛选保证）
                    nid = batch[0]
                    nid_out, out = nid, _run_node(nid)[1]
                    with write_lock:
                        results[nid_out] = out
                        node_outputs[nid_out] = out
                        completed.add(nid_out)
                    pending.remove(nid_out)

        return {"phases": order, "results": results,
                "strategy": getattr(dag, "strategy", "TEMPLATE")}

    @staticmethod
    def _recall_anchors(goal: str, context: dict, params: dict,
                        injected: str = "") -> str:
        """v2.1 召回→执行层桥:
        ① 优先图拓扑注入（上游 subgraph 锚点节点 data_key=anchors）;
        ② 否则节点声明 recall_anchor=True 时节点内自召回;
        ③ 失败静默降级（A16 快反馈, 不阻塞执行）。"""
        if injected:
            return injected
        if not params.get("recall_anchor"):
            return ""
        try:
            from core.agent.recall.recall_service import (
                RecallService, format_anchors)
            rs = RecallService()
            query = str(context.get("text") or goal)
            rr = rs.recall(query, top_k=5,
                           intent=context.get("intent"),
                           sid=context.get("session_id") or "",
                           expand_graph=True)
            return format_anchors(rr, max_chars=1200)
        except Exception:
            return ""

    @staticmethod
    def _extract_anchors(node_ctx: dict) -> str:
        """从 node_ctx 解包图拓扑注入的锚点（上游 subgraph 节点输出）。"""
        val = node_ctx.get("anchors")
        if isinstance(val, dict):
            return str(val.get("anchors") or "")
        return str(val or "")

    def replay(self, from_checkpoint: str) -> Optional[StateSnapshot]:
        """Replay from a checkpoint (for recovery)."""
        for snap in self._history:
            if snap.checkpoint == from_checkpoint:
                return snap
        return None
