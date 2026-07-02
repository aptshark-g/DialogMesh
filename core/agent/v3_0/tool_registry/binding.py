# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/binding.py
─────────────────────────────────────────
DialogMesh v3.0 工具绑定引擎。

用途：
- 将 Planning 层生成的占位符（如 search_tool）绑定到 Tool 层的实际工具
  （如 github_api_search_repos）。
- 实现 4 策略绑定：精确匹配 → 标签匹配 → 语义匹配 → 参数兼容。
- 低置信度绑定（< 0.6）自动替换为 fallback 标记，由上层替换为 ask_user。
- 支持批量绑定 TaskGraph 中所有占位符节点。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.tool_registry.models import (
    BindingResult,
    BindingStrategy,
    ToolDefinition,
)
from core.agent.v3_0.tool_registry.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolBindingEngine:
    """工具绑定引擎 — 4 策略绑定。

    设计文档 §4.7 策略优先级：
        1. 精确匹配
        2. 标签匹配
        3. 语义匹配
        4. 参数兼容
    """

    def __init__(
        self,
        registry: ToolRegistry,
        embedding_provider: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._embedding = embedding_provider
        self._logger = logging.getLogger("tool_binding")

    # ── 单占位符绑定 ───────────────────────────────────────────────────────

    async def bind(
        self,
        placeholder: str,
        tool_hints: Optional[Dict[str, List[str]]] = None,
        required_params: Optional[List[str]] = None,
    ) -> BindingResult:
        """将占位符绑定到实际工具。

        参数:
            placeholder: 原始占位符名（如 "search_tool"）。
            tool_hints: Skill 模板提供的占位符→标签提示映射。
            required_params: 步骤所需的参数名列表，用于参数兼容性检查。

        返回:
            BindingResult，若 confidence < 0.6 则 fallback_to_ask_user=True。
        """
        try:
            all_tools = await self._registry.list_all()

            # 策略 1: 精确匹配
            exact_match = self._exact_match(placeholder, all_tools)
            if exact_match:
                return BindingResult(
                    placeholder=placeholder,
                    bound_tool=exact_match,
                    confidence=1.0,
                    strategy=BindingStrategy.EXACT_MATCH,
                )

            # 策略 2: 标签匹配
            tag_match, tag_conf = self._tag_match(placeholder, all_tools, tool_hints)
            if tag_match and tag_conf >= 0.6:
                return BindingResult(
                    placeholder=placeholder,
                    bound_tool=tag_match,
                    confidence=tag_conf,
                    strategy=BindingStrategy.TAG_MATCH,
                )

            # 策略 3: 语义匹配
            sem_match, sem_conf = await self._semantic_match(placeholder, all_tools)
            if sem_match and sem_conf >= 0.6:
                return BindingResult(
                    placeholder=placeholder,
                    bound_tool=sem_match,
                    confidence=sem_conf,
                    strategy=BindingStrategy.SEMANTIC_MATCH,
                )

            # 策略 4: 参数兼容（基于 JSON Schema 的 _resolve_binding）
            param_match, param_conf = self._param_compatible_match(
                placeholder, all_tools, required_params
            )
            if param_match and param_conf >= 0.6:
                return BindingResult(
                    placeholder=placeholder,
                    bound_tool=param_match,
                    confidence=param_conf,
                    strategy=BindingStrategy.PARAM_COMPATIBLE,
                )

            # 低置信度：回退
            candidates = [
                (tag_match, tag_conf),
                (sem_match, sem_conf),
                (param_match, param_conf),
            ]
            best_tool, best_conf = max(
                candidates,
                key=lambda x: x[1] if x[1] is not None else 0.0,
            )
            return BindingResult(
                placeholder=placeholder,
                bound_tool=best_tool,
                confidence=best_conf if best_conf is not None else 0.0,
                strategy=BindingStrategy.FALLBACK,
                fallback_to_ask_user=True,
            )
        except Exception as exc:
            self._logger.error(f"bind failed for placeholder '{placeholder}': {exc}")
            raise

    # ── 批量绑定 ───────────────────────────────────────────────────────────

    async def bind_task_graph(
        self,
        task_graph: Any,
        tool_hints: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, BindingResult]:
        """批量绑定 TaskGraph 中所有占位符。

        参数:
            task_graph: TaskGraph 对象，需包含 nodes 字典且节点有 tool_name 属性。
            tool_hints: Skill 模板提供的占位符→标签提示映射。

        返回:
            placeholder → BindingResult 的映射。
        """
        try:
            results: Dict[str, BindingResult] = {}
            nodes = getattr(task_graph, "nodes", {})
            for node in nodes.values():
                placeholder = getattr(node, "tool_name", None)
                if not placeholder:
                    continue
                if placeholder in results:
                    continue

                # 提取步骤所需参数（如果节点有 args 或 required_params 属性）
                required_params: Optional[List[str]] = None
                if hasattr(node, "required_params") and node.required_params:
                    required_params = list(node.required_params)
                elif hasattr(node, "args") and node.args:
                    required_params = list(node.args.keys())

                result = await self.bind(placeholder, tool_hints, required_params)
                results[placeholder] = result

                # 若绑定成功且置信度足够，更新节点的实际工具名
                if (
                    result.bound_tool
                    and not result.fallback_to_ask_user
                    and hasattr(node, "tool_name")
                ):
                    node.tool_name = result.bound_tool.name

            return results
        except Exception as exc:
            self._logger.error(f"bind_task_graph failed: {exc}")
            raise

    # ── 策略实现 ───────────────────────────────────────────────────────────

    def _exact_match(
        self, placeholder: str, tools: List[ToolDefinition]
    ) -> Optional[ToolDefinition]:
        """精确匹配：占位符去掉 '_tool' 后缀后与工具名做包含匹配。

        示例：search_tool → search_laptop（工具名包含 "search"）
        """
        base = placeholder.replace("_tool", "").replace("_", "")
        for tool in tools:
            tool_base = tool.name.replace("_", "")
            if base == tool_base or base in tool_base or tool_base in base:
                return tool
        return None

    def _tag_match(
        self,
        placeholder: str,
        tools: List[ToolDefinition],
        tool_hints: Optional[Dict[str, List[str]]],
    ) -> Tuple[Optional[ToolDefinition], float]:
        """标签匹配：基于 Skill 的 tool_hints 和工具标签的交集。"""
        if not tool_hints or placeholder not in tool_hints:
            return None, 0.0

        hint_tags = set(tool_hints[placeholder])
        best_tool: Optional[ToolDefinition] = None
        best_score = 0.0

        for tool in tools:
            overlap = len(set(tool.tags) & hint_tags)
            if overlap > 0:
                score = overlap / max(len(hint_tags), len(tool.tags))
                if score > best_score:
                    best_score = score
                    best_tool = tool

        return best_tool, best_score

    async def _semantic_match(
        self, placeholder: str, tools: List[ToolDefinition]
    ) -> Tuple[Optional[ToolDefinition], float]:
        """语义匹配：基于描述文本的 embedding 相似度。"""
        if not self._embedding:
            return None, 0.0

        placeholder_desc = placeholder.replace("_", " ")
        best_tool: Optional[ToolDefinition] = None
        best_score = 0.0

        try:
            await asyncio.sleep(0)
            if asyncio.iscoroutinefunction(self._embedding.encode):
                ph_emb = await self._embedding.encode(placeholder_desc)
            else:
                loop = asyncio.get_event_loop()
                ph_emb = await loop.run_in_executor(
                    None, self._embedding.encode, placeholder_desc
                )

            for tool in tools:
                if not tool.description:
                    continue
                if asyncio.iscoroutinefunction(self._embedding.encode):
                    t_emb = await self._embedding.encode(tool.description)
                else:
                    loop = asyncio.get_event_loop()
                    t_emb = await loop.run_in_executor(
                        None, self._embedding.encode, tool.description
                    )

                score = self._cosine_similarity(ph_emb, t_emb)
                if score > best_score:
                    best_score = score
                    best_tool = tool
        except Exception as exc:
            self._logger.debug(f"semantic_match failed: {exc}")

        return best_tool, best_score

    def _resolve_binding(
        self,
        placeholder: str,
        tool: ToolDefinition,
        required_params: Optional[List[str]] = None,
    ) -> Tuple[bool, float]:
        """参数兼容性检查：验证工具 JSON Schema 是否满足步骤参数需求。

        检查逻辑（对应设计文档 §4.7 策略 4）：
        1. 步骤所需参数（required_params）是否都在工具 properties 中定义
        2. 工具 required 是否为步骤所需参数的父集（tool_required ⊇ step_required）
        3. 基于参数覆盖度计算兼容性置信度

        参数:
            placeholder: 占位符名（用于日志）。
            tool: 待检查的工具定义。
            required_params: 步骤所需的参数名列表；None 时做通用兼容性评估。

        返回:
            (is_compatible, confidence_score) — is_compatible=True 表示参数兼容。
        """
        try:
            schema = tool.parameters
            props = schema.get("properties", {})
            tool_required = set(schema.get("required", []))

            if required_params is None:
                # 无明确步骤参数时，基于工具参数丰富度给出通用兼容性评分
                score = min(len(props) / 5.0, 1.0)
                return True, score

            step_params = set(required_params)

            # 检查 1：步骤参数是否都在工具 properties 中定义
            missing_props = step_params - set(props.keys())
            if missing_props:
                self._logger.debug(
                    f"占位符 '{placeholder}' 与工具 '{tool.name}' 不兼容: "
                    f"缺少参数定义 {missing_props}"
                )
                return False, 0.0

            # 检查 2：工具 required 是否为步骤 required 的父集
            # 即工具要求的所有参数必须包含步骤要求的参数
            if not tool_required.issuperset(step_params):
                # 步骤要求的参数，工具没有标记为 required（可能是 optional）
                # 不完全拒绝，但降低置信度
                coverage = (
                    len(step_params & tool_required) / len(step_params)
                    if step_params else 1.0
                )
                base_score = 0.3 * coverage
            else:
                base_score = 0.6

            # 额外分：工具参数丰富度（最多 0.3）
            richness = min(len(props) / 10.0, 0.3)

            # 额外分：required 完全匹配（最多 0.1）
            exact_match_bonus = 0.1 if tool_required == step_params else 0.0

            total_score = min(base_score + richness + exact_match_bonus, 1.0)
            return True, total_score
        except Exception as exc:
            self._logger.warning(f"_resolve_binding 异常 ({placeholder}, {tool.name}): {exc}")
            return False, 0.0

    def _param_compatible_match(
        self,
        placeholder: str,
        tools: List[ToolDefinition],
        required_params: Optional[List[str]] = None,
    ) -> Tuple[Optional[ToolDefinition], float]:
        """参数兼容匹配：基于 _resolve_binding 的真实参数兼容性检查。

        替代原启发式（仅属性数量计数），依据 JSON Schema 结构进行验证。

        参数:
            placeholder: 占位符名。
            tools: 候选工具列表。
            required_params: 步骤所需的参数名列表。

        返回:
            (best_tool, best_score) — 若无兼容工具则返回 (None, 0.0)。
        """
        best_tool: Optional[ToolDefinition] = None
        best_score = 0.0

        for tool in tools:
            compatible, score = self._resolve_binding(placeholder, tool, required_params)
            if compatible and score > best_score:
                best_score = score
                best_tool = tool

        return best_tool, best_score

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算余弦相似度。"""
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a > 0 and norm_b > 0:
                return dot / (norm_a * norm_b)
            return 0.0
        except Exception:
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/binding self-test ===")

        from core.agent.v3_0.tool_registry.registry import ToolRegistry

        registry = ToolRegistry()

        tools = [
            ToolDefinition(name="github_search", description="搜索 GitHub 仓库", tags=["search", "github"]),
            ToolDefinition(name="web_search", description="网页搜索", tags=["search", "web"]),
            ToolDefinition(name="memory_scan", description="扫描内存", tags=["memory", "scan"]),
            ToolDefinition(name="ask_user", description="询问用户", tags=["meta"]),
            ToolDefinition(name="finish", description="结束", tags=["meta"]),
        ]
        for t in tools:
            await registry.register(t)

        engine = ToolBindingEngine(registry)

        # 1. 精确匹配
        r1 = await engine.bind("search_tool")
        assert r1.strategy == BindingStrategy.EXACT_MATCH
        assert r1.bound_tool and r1.bound_tool.name == "github_search"
        print(f"[PASS] exact_match: {r1.bound_tool.name}, conf={r1.confidence}")

        # 2. 标签匹配（注意：scan_tool 在 _exact_match 中也会匹配到 memory_scan，
        #    因为 "scan" 包含于 "memory_scan"，所以预期策略为 EXACT_MATCH）
        hints = {"scan_tool": ["memory", "scan"]}
        r2 = await engine.bind("scan_tool", tool_hints=hints)
        assert r2.strategy == BindingStrategy.EXACT_MATCH
        assert r2.bound_tool and r2.bound_tool.name == "memory_scan"
        print(f"[PASS] exact_match via scan: {r2.bound_tool.name}, conf={r2.confidence}")

        # 3. 参数兼容（无匹配时的兜底）
        r3 = await engine.bind("unknown_xyz")
        assert r3.strategy == BindingStrategy.FALLBACK
        assert r3.fallback_to_ask_user is True
        print(f"[PASS] fallback: fallback_to_ask_user={r3.fallback_to_ask_user}")

        # 5. _resolve_binding 参数兼容性检查（required_params 匹配）
        tool_with_params = ToolDefinition(
            name="data_query",
            description="数据查询",
            tags=["data"],
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "columns": {"type": "array"},
                    "where": {"type": "string"},
                },
                "required": ["table", "columns"],
            },
        )
        await registry.register(tool_with_params)

        compatible, score = engine._resolve_binding("query_tool", tool_with_params, ["table", "columns"])
        assert compatible is True and score >= 0.6
        print(f"[PASS] _resolve_binding compatible: score={score:.2f}")

        # 6. _resolve_binding 不兼容（步骤参数不在工具 properties 中）
        incompatible, score2 = engine._resolve_binding("query_tool", tool_with_params, ["table", "limit"])
        assert incompatible is False and score2 == 0.0
        print(f"[PASS] _resolve_binding incompatible: missing param")

        # 7. bind 带 required_params 的参数兼容匹配（使用不触发精确匹配的占位符）
        r4 = await engine.bind("fetch_tool", required_params=["table", "columns"])
        assert r4.strategy == BindingStrategy.PARAM_COMPATIBLE
        assert r4.bound_tool is not None and r4.bound_tool.name == "data_query"
        print(f"[PASS] param_compatible_match with required_params: {r4.bound_tool.name}")

        # 8. bind_task_graph 提取节点 required_params
        class FakeNodeWithArgs:
            def __init__(self, tool_name, args=None):
                self.tool_name = tool_name
                self.args = args or {}

        class FakeGraph2:
            nodes = {
                "n1": FakeNodeWithArgs("fetch_data_tool", {"table": "users", "columns": ["id"]}),
            }

        graph2 = FakeGraph2()
        results2 = await engine.bind_task_graph(graph2)
        assert "fetch_data_tool" in results2
        assert results2["fetch_data_tool"].bound_tool.name == "data_query"
        print(f"[PASS] bind_task_graph with node args: {results2['fetch_data_tool'].bound_tool.name}")

        # 4. bind_task_graph
        class FakeNode:
            def __init__(self, tool_name):
                self.tool_name = tool_name

        class FakeGraph:
            nodes = {
                "n1": FakeNode("search_tool"),
                "n2": FakeNode("scan_tool"),
            }

        graph = FakeGraph()
        results = await engine.bind_task_graph(graph, tool_hints=hints)
        assert "search_tool" in results
        assert "scan_tool" in results
        print(f"[PASS] bind_task_graph: {len(results)} placeholders bound")

        logger.info("=== All v3.0 tool_registry/binding self-tests passed ===")

    asyncio.run(_self_test())
