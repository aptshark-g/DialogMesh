# -*- coding: utf-8 -*-
"""BlueprintEngine — orchestrates DAG construction by strategy.

Three entry paths (§十):
  TEMPLATE/RULE_BASED → direct template return
  HYBRID   → template floor + LLM node override
  LLM_DRIVEN → full diverge→learn→converge pipeline

ConstraintChecker validates every DAG before execution.
"""

from __future__ import annotations

import copy
import logging
from typing import List, Optional, Tuple

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
    VALID_STRATEGIES,
)
from core.agent.blueprint.skill_registry import SkillRegistry
from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder

logger = logging.getLogger(__name__)


class ConstraintChecker:
    """Validates BlueprintDAG against structural + resource constraints.

    Aligned to §十二 工程文档约束层:
      - 安全: is_destructive → checkpoint required
      - 资源: node_count ≤ 7, depth ≤ 3
      - 依赖: topological order, no cycles, data_key resolution
      - 权限: Capability check (reserved for Execution)
    """

    MAX_NODES = 7
    MAX_DEPTH = 18

    def validate(self, dag: BlueprintDAG,
                 strictness: float = 0.5) -> Tuple[bool, List[str]]:
        """Validate a BlueprintDAG. Returns (is_valid, error_messages).

        GAP-P1（DESIGN_DEEP_AUDIT §P2 控制面板参数化）: strictness ∈ [0,1]
        缩放约束:
          - 0.0 宽松 → 节点上限放宽到 12, 深度放宽到 24
          - 0.5 默认 → 7 / 18
          - 1.0 严格 → 5 / 12
        """
        errors = []

        # Structural validation
        errors.extend(dag.validate())

        # Node count
        max_nodes = self._scaled_limit(self.MAX_NODES, strictness,
                                       lo=5, hi=12)
        if dag.node_count > max_nodes:
            errors.append(f"Node count {dag.node_count} exceeds max {max_nodes}")
        if dag.node_count == 0:
            errors.append("DAG has no nodes")

        # Dag depth (longest path)
        depth = self._max_depth(dag)
        max_depth = self._scaled_limit(self.MAX_DEPTH, strictness,
                                       lo=12, hi=24)
        if depth > max_depth:
            errors.append(f"DAG depth {depth} exceeds max {max_depth}")

        # Check LLM reply present
        has_llm_reply = any(n.chain == "llm_reply" for n in dag.nodes)
        if not has_llm_reply:
            errors.append("DAG must contain at least one llm_reply node")

        # Check PCR present as entry point
        roots = dag.roots()
        has_pcr_root = any(n.chain == "pcr" for n in roots)
        if not has_pcr_root and dag.node_count > 0:
            errors.append("DAG should start with a pcr node")

        # Cycle detection
        if self._has_cycle(dag):
            errors.append("DAG contains a cycle")

        # Data key resolution: every edge's data_key must be a known key
        valid_keys = {"route", "intent_context", "assembled_context", "compiled_subgraph",
                      "profile_text", "compass", "data",
                      # 2026-08-13 修复（蓝图薄点实锤）: recall_pipeline /
                      # intent_multi_recall 模板的 recall_anchor→subgraph
                      # 边用 "anchors"（锚点注入通道）— 此前不在白名单,
                      # 模板构建恒校验失败回退最小 DAG, "意图→召回→图扩展
                      # →回复"链路在 build 层就断掉。
                      "anchors"}
        for e in dag.edges:
            if e.data_key not in valid_keys:
                errors.append(f"Unknown data_key '{e.data_key}' in edge {e.from_node}→{e.to_node}")

        return len(errors) == 0, errors

    @staticmethod
    def _scaled_limit(base: int, strictness: float, lo: int, hi: int) -> int:
        """按严格度缩放上限: 0.0 → hi（宽松）, 1.0 → lo（严格）."""
        try:
            s = max(0.0, min(1.0, float(strictness)))
        except (TypeError, ValueError):
            s = 0.5
        return int(round(hi - (hi - lo) * s))

    def _max_depth(self, dag: BlueprintDAG) -> int:
        """Longest path from any root to any leaf."""
        adj = {n.node_id: [] for n in dag.nodes}
        for e in dag.edges:
            if e.from_node in adj:
                adj[e.from_node].append(e.to_node)

        memo = {}
        def dfs(node_id: str, visited: set) -> int:
            if node_id in memo:
                return memo[node_id]
            if node_id in visited:
                return 0
            visited.add(node_id)
            max_child = 0
            for child in adj.get(node_id, []):
                max_child = max(max_child, dfs(child, visited))
            visited.discard(node_id)
            memo[node_id] = 1 + max_child
            return memo[node_id]

        max_d = 0
        for n in dag.nodes:
            max_d = max(max_d, dfs(n.node_id, set()))
        return max_d

    def _has_cycle(self, dag: BlueprintDAG) -> bool:
        """DFS cycle detection."""
        adj = {n.node_id: [] for n in dag.nodes}
        for e in dag.edges:
            if e.from_node in adj:
                adj[e.from_node].append(e.to_node)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n.node_id: WHITE for n in dag.nodes}

        def dfs(node_id: str) -> bool:
            color[node_id] = GRAY
            for child in adj.get(node_id, []):
                if color.get(child) == GRAY:
                    return True
                if color.get(child) == WHITE and dfs(child):
                    return True
            color[node_id] = BLACK
            return False

        for n in dag.nodes:
            if color[n.node_id] == WHITE and dfs(n.node_id):
                return True
        return False


# ═══════════════════════════════════════════════
# BlueprintEngine
# ═══════════════════════════════════════════════

class BlueprintEngine:
    """Orchestrates Blueprint DAG construction — three strategy paths.

    Usage:
      engine = BlueprintEngine()
      dag = engine.build("用户输入文本", "代码分析")
      # dag is ready for Decider → EventBus execution
    """

    def __init__(self, decision_bus=None, registry=None,
                 default_strictness: float = 0.5,
                 default_depth: int = 18,
                 default_breadth: int = 3):
        # GAP-D2: registry 可注入 — 生产路径共享 engine 持有的 registry
        # （v3_session_api 本地 BlueprintEngine 与 runtime engine 的
        # learning_bridge 共用同一 SkillRegistry, match/learn 不分叉）。
        self.registry = registry or SkillRegistry()
        self.builder = LLMDAGBuilder()
        self.checker = ConstraintChecker()
        self._strategy_cache: dict = {}  # Simple in-memory cache
        # 决策变更事件总线（META_ARBITER §3.2）: 构建期策略选择/降级可记录
        self._decision_bus = decision_bus
        # GAP-P1 控制面板默认参数（可被 build() 显式覆盖）
        self._default_strictness = default_strictness
        self._default_depth = default_depth
        self._default_breadth = default_breadth
        self.checker.MAX_DEPTH = default_depth

    def build(self, text: str, intent: str = None, strategy: str = None,
              strictness: float = None, depth: int = None,
              breadth: int = None, decision_mode: str = None,
              template: str = None) -> BlueprintDAG:
        """Build a BlueprintDAG for the given input.

        Args:
            text: user input text
            intent: user intent (auto-detected if None)
            strategy: force a strategy (uses registry.match if None)
            strictness: 约束严格度 0.0-1.0（控制面板; None → 默认 0.5）
            depth: 图深度上限（None → 默认 18）
            breadth: 发散路径数 2-6（LLM_DRIVEN; None → 默认 3）
            decision_mode: auto|template|hybrid|llm — 决策模式映射 strategy
              （auto → registry.match; 其余强制对应策略）
            template: 显式模板名（2026-08-13, 多意图入口）— 跳过 registry
              match 直接取 BUILTIN_TEMPLATES[template]; 未知名回退 match。

        Returns:
            BlueprintDAG ready for execution
        """
        t0 = __import__("time").time()
        strictness = self._default_strictness if strictness is None else strictness
        depth = self._default_depth if depth is None else depth
        breadth = self._default_breadth if breadth is None else breadth
        # GAP-P1: 决策模式 → 策略映射
        mode_map = {
            "template": "TEMPLATE", "hybrid": "HYBRID", "llm": "LLM_DRIVEN",
            "rule_based": "RULE_BASED",
        }
        if decision_mode in mode_map:
            strategy = mode_map[decision_mode]
        self.checker.MAX_DEPTH = depth

        # Auto-detect intent + strategy
        if intent is None:
            intent = "通用对话"  # default fallback
        blueprint = None
        if template:
            from core.agent.blueprint.skill_registry import BUILTIN_TEMPLATES
            explicit = BUILTIN_TEMPLATES.get(template)
            if explicit is not None:
                blueprint = explicit
                if strategy is None:
                    strategy = explicit.strategy
        if blueprint is None:
            if strategy is None:
                strategy, blueprint = self.registry.match(intent)
            else:
                _, blueprint = self.registry.match(intent)

        # Cache key for fast path — deterministic, no hash collision
        cache_key = f"{intent}:{strategy}:{template or '-'}:{text[:200]}"
        if cache_key in self._strategy_cache:
            logger.info("Cache hit for %s", intent)
            # Return a copy so callers cannot mutate the cached DAG
            return copy.deepcopy(self._strategy_cache[cache_key])

        # Isolate from the shared BUILTIN_TEMPLATES — LLM overrides / strategy
        # writes must never leak into the global templates (P0-1).
        blueprint = copy.deepcopy(blueprint)

        # ── Route by strategy ──
        if strategy in ("TEMPLATE", "RULE_BASED"):
            dag = self._build_template(intent, blueprint)
        elif strategy == "HYBRID":
            dag = self._build_hybrid(text, intent, blueprint)
        elif strategy == "LLM_DRIVEN":
            dag = self._build_llm_driven(text, intent, breadth=breadth)
        else:
            logger.warning("Unknown strategy '%s' → falling back to HYBRID", strategy)
            dag = self._build_hybrid(text, intent, blueprint)

        # ── Constraint check ──
        valid, errors = self.checker.validate(dag, strictness=strictness)
        if not valid:
            logger.warning("Constraint check failed: %s — falling back to TEMPLATE", errors)
            dag = self._build_template(intent, blueprint)
            valid2, _ = self.checker.validate(dag)
            if not valid2:
                # Ultimate fallback — minimal working DAG
                dag = BlueprintDAG(
                    nodes=[
                        BlueprintNode("pcr_0", "pcr"),
                        BlueprintNode("llm_1", "llm_reply", priority=1),
                    ],
                    edges=[BlueprintEdge("pcr_0", "llm_1", "route")],
                    strategy="RECOVERY",
                    confidence=0.5,
                    design_rationale="约束检查失败后的最小保底DAG",
                )

        if dag.strategy != "RECOVERY":
            dag.strategy = strategy
        elapsed = (__import__("time").time() - t0) * 1000
        logger.info("BlueprintEngine: built %s DAG (%d nodes, %.0fms)", strategy, dag.node_count, elapsed)

        # Cache
        self._strategy_cache[cache_key] = dag
        # Return a copy so callers cannot mutate the cached DAG (same as hit path)
        return copy.deepcopy(dag)

    def _build_template(self, intent: str, blueprint: BlueprintDAG) -> BlueprintDAG:
        """TEMPLATE strategy — direct template return (deterministic)."""
        return blueprint

    def _build_hybrid(self, text: str, intent: str, blueprint: BlueprintDAG) -> BlueprintDAG:
        """HYBRID strategy — template floor + LLM node override.

        LLM sees the template and user input, suggests:
          - add: new chains needed (context, subgraph)
          - remove: unnecessary chains
          - reorder: priority adjustments
        """
        # Build prompt showing current template
        node_list = "\n".join(
            f"  {n.node_id}: chain={n.chain}, priority={n.priority}, deps={[e.from_node for e in blueprint.edges if e.to_node == n.node_id]}"
            for n in blueprint.nodes
        )
        prompt = (
            f"用户意图: {intent}\n"
            f"用户输入: {text[:800]}\n\n"
            f"当前模板节点:\n{node_list}\n\n"
            f"请建议调整（可选: add/remove/reorder）。\n"
            f"输出 JSON: {{\"action\":\"none\"}} 或 {{\"action\":\"modify\",\"add\":[],\"remove\":[],\"reorder\":{{}}}}"
        )

        system = (
            "你是 Blueprint 优化器。根据用户意图判断模板是否需要调整。\n"
            "add: 需要增加的链节点 (如缺少 context 则加 context)\n"
            "remove: 可移除的冗余节点\n"
            "reorder: {{node_id: new_priority}}\n"
            "只在确实需要时修改，大多数情况返回 none。\n"
            "只输出 JSON。"
        )

        try:
            response = self.builder._call_llm(system, prompt, temperature=0.3, max_tokens=500)
            data = self.builder._extract_json(response)
            if isinstance(data, dict) and data.get("action") == "modify":
                self._apply_llm_overrides(blueprint, data)
                logger.info("HYBRID: LLM suggested modifications to template")
        except Exception as e:
            logger.warning("HYBRID LLM override failed: %s", e)

        return blueprint

    def _apply_llm_overrides(self, dag: BlueprintDAG, mods: dict):
        """Apply LLM-suggested node modifications to a template DAG."""
        # Remove nodes
        for rm_id in mods.get("remove", []):
            dag.nodes = [n for n in dag.nodes if n.node_id != rm_id]
            dag.edges = [e for e in dag.edges if e.from_node != rm_id and e.to_node != rm_id]

        # Add nodes
        for add_spec in mods.get("add", []):
            if isinstance(add_spec, dict):
                new_id = add_spec.get("node_id", f"custom_{len(dag.nodes)}")
                chain = add_spec.get("chain", "intent")
                priority = add_spec.get("priority", 1)
                deps = add_spec.get("deps", [])
                try:
                    dag.nodes.append(BlueprintNode(new_id, chain, priority=priority))
                    for dep in deps:
                        dag.edges.append(BlueprintEdge(dep, new_id, "data"))
                except ValueError:
                    pass

        # Reorder priorities
        for node_id, new_priority in mods.get("reorder", {}).items():
            for n in dag.nodes:
                if n.node_id == node_id:
                    n.priority = new_priority

    def _build_llm_driven(self, text: str, intent: str,
                          breadth: int = 3) -> BlueprintDAG:
        """LLM_DRIVEN strategy — full diverge→learn→converge pipeline.

        Falls back to TEMPLATE on failure.
        """
        dag = self.builder.build_llm_driven(text, intent, breadth=breadth)
        if dag is None:
            logger.warning("LLM_DRIVEN failed → falling back to general_chat TEMPLATE")
            dag = copy.deepcopy(self.registry.builtin_template("general_chat"))
            dag.strategy = "RECOVERY"
            dag.design_rationale = "LLM_DRIVEN failed, recovered to general_chat template"
        return dag
