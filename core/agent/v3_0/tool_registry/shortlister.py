# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/shortlister.py
────────────────────────────────────────────
DialogMesh v3.0 工具筛选器。

用途：
- 解决 Tool Overflow 问题——当注册工具数量超过 LLM 上下文窗口承载能力时，
  从全部工具中筛选最相关的子集（默认 Top 32）。
- 实现 5 阶段漏斗筛选：意图标签匹配 → 语义相似度排序 → 历史偏好 boost →
  容量截断 → 兜底策略。
- 若 embedding provider 不可用，自动降级为关键词重叠启发式。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

from core.agent.v3_0.tool_registry.models import (
    ShortlistResult,
    ToolDefinition,
)
from core.agent.v3_0.tool_registry.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolShortlister:
    """工具筛选器 — 5 阶段漏斗筛选。

    设计文档 §4.6.2 算法：
        Selected = Truncate(
            Capacity,
            Rank(HistoryBoost(SemanticScore(Filter(Intent, AllTools))))
        )

    阶段 1: 意图标签匹配（粗筛）
    阶段 2: 语义相似度排序（精排）
    阶段 3: 历史偏好 boost（个性化）
    阶段 4: 容量截断（上下文窗口限制）
    阶段 5: 兜底策略（强制保留通用工具）
    """

    def __init__(
        self,
        registry: ToolRegistry,
        embedding_provider: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._embedding = embedding_provider
        self._logger = logging.getLogger("tool_shortlister")

    # ── 主筛选入口 ─────────────────────────────────────────────────────────

    async def shortlist(
        self,
        intent: Any,
        all_tools: Optional[List[ToolDefinition]] = None,
        capacity: int = 32,
    ) -> ShortlistResult:
        """5 阶段漏斗筛选。

        参数:
            intent: 意图对象（需支持 tags / description / normalized_input 属性）。
            all_tools: 待筛选的工具列表；None 时从 registry 获取全部。
            capacity: 最大返回工具数（默认 32）。

        返回:
            ShortlistResult 包含筛选后的工具子集与统计信息。
        """
        try:
            await asyncio.sleep(0)  # 让出事件循环

            tools = all_tools or await self._registry.list_all()
            total = len(tools)

            # 阶段 1: 意图标签匹配
            intent_tags = self._extract_intent_tags(intent)
            if intent_tags:
                filtered = [t for t in tools if set(t.tags) & intent_tags]
                if not filtered:
                    filtered = tools  # 放宽到全部工具，避免过度过滤
            else:
                filtered = tools
            after_tag = len(filtered)

            # 阶段 2: 语义相似度排序
            intent_text = self._extract_intent_text(intent)
            scored = []
            for tool in filtered:
                score = await self._semantic_score(intent_text, tool.description, tool)
                scored.append((tool, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            after_semantic = len(scored)

            # 阶段 3: 历史偏好 boost
            boosted = []
            for tool, score in scored:
                boost = self._history_boost(tool)
                boosted.append((tool, score + boost))
            boosted.sort(key=lambda x: x[1], reverse=True)

            # 阶段 4: 容量截断（保守估计每个工具描述约 200 tokens）
            selected = [tool for tool, _ in boosted[:capacity]]

            # 阶段 5: 兜底策略 — 强制保留通用工具
            fallback_names = {"ask_user", "finish"}
            existing = {t.name for t in selected}
            for fb_name in fallback_names:
                if fb_name not in existing:
                    fb_tool = await self._registry.get(fb_name)
                    if fb_tool:
                        selected.append(fb_tool)

            return ShortlistResult(
                tools=selected,
                total_available=total,
                filtered_by_tag=after_tag,
                ranked_by_semantic=after_semantic,
                capacity_limit=capacity,
                fallback_included=True,
            )
        except Exception as exc:
            self._logger.error(f"shortlist failed: {exc}")
            raise

    # ── 辅助方法 ───────────────────────────────────────────────────────────

    def _extract_intent_tags(self, intent: Any) -> set:
        """从意图对象提取标签集合。"""
        tags = getattr(intent, "tags", None)
        if tags:
            return set(tags)
        # 尝试从 intent.category 推断标签
        category = getattr(intent, "category", None)
        if category:
            return {str(category.value).lower()}
        return set()

    def _extract_intent_text(self, intent: Any) -> str:
        """从意图对象提取用于语义匹配的文本。"""
        desc = getattr(intent, "description", "") or ""
        norm = getattr(intent, "normalized_input", "") or ""
        raw = getattr(intent, "raw_input", "") or ""
        return desc or norm or raw or ""

    async def _semantic_score(
        self, intent_text: str, tool_description: str, tool: ToolDefinition
    ) -> float:
        """语义相似度计算。

        如果 embedding provider 可用，使用余弦相似度；
        否则降级为关键词重叠启发式。
        """
        try:
            if self._embedding and intent_text and tool_description:
                intent_emb = await self._encode_async(intent_text)
                tool_emb = await self._encode_async(tool_description)
                if intent_emb and tool_emb:
                    return self._cosine_similarity(intent_emb, tool_emb)
        except Exception as exc:
            self._logger.debug(f"Embedding semantic score failed: {exc}")

        # 降级：关键词重叠启发式
        return self._keyword_overlap(intent_text, tool_description)

    async def _encode_async(self, text: str) -> Optional[List[float]]:
        """异步编码文本为 embedding 向量。"""
        if self._embedding is None:
            return None
        try:
            await asyncio.sleep(0)
            # 支持同步或异步 encode 方法
            if asyncio.iscoroutinefunction(self._embedding.encode):
                return await self._embedding.encode(text)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._embedding.encode, text)
        except Exception as exc:
            self._logger.debug(f"encode_async failed: {exc}")
            return None

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度。"""
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a > 0 and norm_b > 0:
                return dot / (norm_a * norm_b)
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _keyword_overlap(text_a: str, text_b: str) -> float:
        """关键词重叠启发式。"""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        overlap = len(words_a & words_b)
        return overlap / max(len(words_a), len(words_b))

    @staticmethod
    def _history_boost(tool: ToolDefinition) -> float:
        """历史偏好 boost。

        设计文档公式：
            HistoryBoost(t) = success_rate(t) × min(1, call_count(t)/10) × 0.1
        boost 不超过 10%。
        """
        stats = tool.execution_stats
        if stats.call_count == 0:
            return 0.0
        return stats.success_rate * min(1.0, stats.call_count / 10.0) * 0.1


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/shortlister self-test ===")

        from core.agent.v3_0.tool_registry.registry import ToolRegistry

        registry = ToolRegistry()

        # 构造模拟意图
        class FakeIntent:
            tags = ["memory"]
            description = "scan memory for health value"
            normalized_input = "scan memory for health"
            raw_input = "scan memory for health"

        intent = FakeIntent()

        # 注册工具
        tools = [
            ToolDefinition(name="memory_scan", description="扫描内存地址", tags=["memory", "scan"]),
            ToolDefinition(name="pointer_scan", description="扫描指针链", tags=["memory", "pointer"]),
            ToolDefinition(name="process_list", description="列出进程", tags=["process"]),
            ToolDefinition(name="web_search", description="网页搜索", tags=["web", "search"]),
            ToolDefinition(name="ask_user", description="询问用户", tags=["meta"]),
            ToolDefinition(name="finish", description="结束会话", tags=["meta"]),
        ]
        for t in tools:
            await registry.register(t)

        # 模拟历史调用，给 memory_scan 增加成功率
        tools[0].execution_stats.update(success=True, latency_ms=100.0)
        tools[0].execution_stats.update(success=True, latency_ms=120.0)

        shortlister = ToolShortlister(registry)

        # 1. 筛选
        result = await shortlister.shortlist(intent, capacity=4)
        assert len(result.tools) <= 6  # capacity + 2 fallback
        names = {t.name for t in result.tools}
        assert "ask_user" in names and "finish" in names
        print(f"[PASS] shortlist: {len(result.tools)} tools (capacity=4, fallback included)")
        print(f"         total={result.total_available}, after_tag={result.filtered_by_tag}")

        # 2. memory_scan 应该排名靠前（历史 boost + 标签匹配）
        first_names = [t.name for t in result.tools[:2]]
        assert "memory_scan" in first_names or "pointer_scan" in first_names
        print(f"[PASS] semantic ranking: top tools = {first_names}")

        # 3. 关键词重叠
        score = ToolShortlister._keyword_overlap("scan memory", "scan memory address")
        assert score > 0.0
        print(f"[PASS] keyword_overlap: {score:.2f}")

        # 4. history_boost
        boost = ToolShortlister._history_boost(tools[0])
        assert boost > 0.0
        print(f"[PASS] history_boost: {boost:.4f}")

        logger.info("=== All v3.0 tool_registry/shortlister self-tests passed ===")

    asyncio.run(_self_test())
