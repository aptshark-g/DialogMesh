# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/window.py
─────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文窗口管理器

用途：
- Token 估算（启发式字符除法 + 可选 tiktoken 回退）。
- 上下文截断策略（FIFO / RECENCY / RELEVANCE / SUMMARY / HYBRID）。
- 自动压缩与摘要生成（将旧切片合并为 ContextSummary）。
- 相关性评分（基于关键词与实体匹配）。

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.v3_0.context_manager.models import (
    ContextPriority,
    ContextSlice,
    ContextSummary,
    TruncationStrategy,
    WindowConfig,
)
from core.agent.v3_0.data_models import Intent_v3

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Token 估算
# ═══════════════════════════════════════════════════════════════════════════

class TokenEstimator:
    """Token 估算器 — 提供启发式与精确两种估算模式。"""

    def __init__(self, chars_per_token: int = 4) -> None:
        self.chars_per_token = chars_per_token
        self._tiktoken_available = False
        try:
            import tiktoken  # noqa: F401
            self._tiktoken_available = True
        except ImportError:
            logger.debug("tiktoken not installed, using heuristic token estimation")

    def estimate_text(self, text: str) -> int:
        """估算文本的 token 数。"""
        try:
            if not text:
                return 0
            return max(1, len(text) // self.chars_per_token)
        except Exception as exc:
            logger.warning(f"TokenEstimator.estimate_text failed: {exc}")
            return 0

    def estimate_slice(self, slice_obj: ContextSlice) -> int:
        """估算 ContextSlice 的 token 数。"""
        try:
            slice_obj._recalculate_tokens()
            return slice_obj.token_estimate
        except Exception as exc:
            logger.warning(f"TokenEstimator.estimate_slice failed: {exc}")
            return 0

    def estimate_summary(self, summary: ContextSummary) -> int:
        """估算 ContextSummary 的 token 数。"""
        try:
            text = summary.to_prompt_text()
            return self.estimate_text(text)
        except Exception as exc:
            logger.warning(f"TokenEstimator.estimate_summary failed: {exc}")
            return 0


# ═══════════════════════════════════════════════════════════════════════════
# 相关性评分
# ═══════════════════════════════════════════════════════════════════════════

class RelevanceScorer:
    """相关性评分器 — 基于关键词与实体匹配的简单评分。

    可替换为向量检索或更复杂的语义相似度模型。
    """

    def __init__(self) -> None:
        self._cache: Dict[str, float] = {}

    def score_slice(self, slice_obj: ContextSlice, current_intent: Optional[Intent_v3]) -> float:
        """为切片相对于当前意图评分（0.0 ~ 1.0）。"""
        try:
            if not current_intent:
                return 0.5

            score = 0.0
            # 1. 实体匹配
            current_entities = {e.type.value: str(e.value) for e in current_intent.entities}
            for intent in slice_obj.intents:
                for e in intent.entities:
                    if e.type.value in current_entities:
                        score += 0.3

            # 2. 关键词重叠（简单子串匹配）
            current_keywords = set(current_intent.raw_input.lower().split())
            slice_text = slice_obj.to_prompt_text().lower()
            for kw in current_keywords:
                if kw in slice_text:
                    score += 0.1

            # 3. 优先级加成
            priority_weights = {
                ContextPriority.SYSTEM: 0.5,
                ContextPriority.USER_GOAL: 0.4,
                ContextPriority.CLARIFICATION: 0.2,
                ContextPriority.TASK_RESULT: 0.1,
                ContextPriority.INTERMEDIATE: 0.0,
                ContextPriority.CHITCHAT: -0.1,
            }
            score += priority_weights.get(slice_obj.priority, 0.0)

            # 4. 时间衰减（越旧的切片分数越低）
            age_seconds = time.time() - slice_obj.created_at
            decay = max(0.0, 1.0 - age_seconds / 3600.0)  # 1 小时衰减到 0
            score *= (0.5 + 0.5 * decay)

            return min(1.0, max(0.0, score))
        except Exception as exc:
            logger.warning(f"RelevanceScorer.score_slice failed: {exc}")
            return 0.0

    def score_summary(self, summary: ContextSummary, current_intent: Optional[Intent_v3]) -> float:
        """为摘要相对于当前意图评分。"""
        try:
            if not current_intent:
                return 0.5
            score = 0.0
            current_keywords = set(current_intent.raw_input.lower().split())
            summary_text = summary.text.lower()
            for kw in current_keywords:
                if kw in summary_text:
                    score += 0.2
            # 实体匹配加成
            for e in current_intent.entities:
                if str(e.value) in summary_text or e.type.value in summary_text:
                    score += 0.3
            return min(1.0, max(0.0, score))
        except Exception as exc:
            logger.warning(f"RelevanceScorer.score_summary failed: {exc}")
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 上下文压缩器
# ═══════════════════════════════════════════════════════════════════════════

class ContextCompressor:
    """上下文压缩器 — 将多个旧切片合并为 ContextSummary。

    当前使用启发式规则提取关键信息；可接入 LLM 做语义压缩。
    """

    def __init__(self, estimator: Optional[TokenEstimator] = None) -> None:
        self.estimator = estimator or TokenEstimator()

    async def compress(self, slices: List[ContextSlice], session_id: str) -> ContextSummary:
        """异步压缩切片列表为摘要。

        Args:
            slices: 要压缩的切片列表（按时间顺序）。
            session_id: 所属会话 ID。

        Returns:
            生成的 ContextSummary。
        """
        try:
            await asyncio.sleep(0)

            # 提取关键信息
            key_entities: Dict[str, Any] = {}
            key_decisions: List[str] = []
            summary_parts: List[str] = []
            source_ids: List[str] = []

            for s in slices:
                source_ids.append(s.slice_id)
                # 提取用户目标与结果
                for intent in s.intents:
                    if intent.category.value != "unknown":
                        summary_parts.append(f"User intent: {intent.category.value}")
                    for e in intent.entities:
                        if e.confidence >= 0.7:
                            key_entities[e.type.value] = e.value

                # 提取任务结果
                for msg in s.messages:
                    content = getattr(msg, "content", "")
                    if "result" in content.lower() or "success" in content.lower():
                        key_decisions.append(content[:200])

            # 去重并生成摘要文本
            unique_parts = list(dict.fromkeys(summary_parts))
            text = "; ".join(unique_parts) if unique_parts else "Previous context summary."

            summary = ContextSummary(
                session_id=session_id,
                text=text,
                key_entities=key_entities,
                key_decisions=list(dict.fromkeys(key_decisions)),
                source_slice_ids=source_ids,
            )
            summary.token_estimate = self.estimator.estimate_summary(summary)
            return summary

        except Exception as exc:
            logger.error(f"ContextCompressor.compress failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
# 上下文窗口管理器
# ═══════════════════════════════════════════════════════════════════════════

class ContextWindow:
    """上下文窗口管理器 — 控制会话上下文在 token 限制内。

    核心流程：
    1. 接收新切片，追加到窗口。
    2. 重新估算总 token 数。
    3. 若溢出，按策略截断或压缩。
    4. 返回最终注入 prompt 的文本。
    """

    def __init__(
        self,
        config: Optional[WindowConfig] = None,
        estimator: Optional[TokenEstimator] = None,
        scorer: Optional[RelevanceScorer] = None,
        compressor: Optional[ContextCompressor] = None,
    ) -> None:
        self.config = config or WindowConfig()
        self.estimator = estimator or TokenEstimator()
        self.scorer = scorer or RelevanceScorer()
        self.compressor = compressor or ContextCompressor(self.estimator)

        self.slices: List[ContextSlice] = []
        self.summaries: List[ContextSummary] = []
        self._current_intent: Optional[Intent_v3] = None

    @property
    def total_tokens(self) -> int:
        """当前窗口总 token 估算值。"""
        try:
            slice_tokens = sum(self.estimator.estimate_slice(s) for s in self.slices)
            summary_tokens = sum(self.estimator.estimate_summary(s) for s in self.summaries)
            return slice_tokens + summary_tokens
        except Exception as exc:
            logger.warning(f"ContextWindow.total_tokens failed: {exc}")
            return 0

    def set_current_intent(self, intent: Optional[Intent_v3]) -> None:
        """设置当前意图，用于相关性评分。"""
        self._current_intent = intent

    def add_slice(self, slice_obj: ContextSlice) -> None:
        """添加切片到窗口。"""
        self.slices.append(slice_obj)
        logger.debug(
            "ContextWindow add_slice: %s (total_slices=%d, total_tokens=%d)",
            slice_obj.slice_id, len(self.slices), self.total_tokens,
        )

    def add_summary(self, summary: ContextSummary) -> None:
        """添加摘要到窗口。"""
        self.summaries.append(summary)
        logger.debug(
            "ContextWindow add_summary: %s (total_summaries=%d)",
            summary.summary_id, len(self.summaries),
        )

    async def fit(self) -> None:
        """异步调整窗口，使其符合 token 限制。

        按策略截断或压缩，直到 total_tokens <= effective_max_tokens。
        """
        try:
            await asyncio.sleep(0)
            max_tokens = self.config.effective_max_tokens

            # 若未超限，直接返回
            if self.total_tokens <= max_tokens:
                return

            logger.info(
                "ContextWindow overflow: %d / %d tokens, strategy=%s",
                self.total_tokens, max_tokens, self.config.strategy.value,
            )

            if self.config.strategy == TruncationStrategy.FIFO:
                await self._truncate_fifo(max_tokens)
            elif self.config.strategy == TruncationStrategy.RECENCY:
                await self._truncate_recency(max_tokens)
            elif self.config.strategy == TruncationStrategy.RELEVANCE:
                await self._truncate_relevance(max_tokens)
            elif self.config.strategy == TruncationStrategy.SUMMARY:
                await self._truncate_summary(max_tokens)
            elif self.config.strategy == TruncationStrategy.HYBRID:
                await self._truncate_hybrid(max_tokens)
            else:
                logger.warning("Unknown strategy %s, falling back to HYBRID", self.config.strategy)
                await self._truncate_hybrid(max_tokens)

        except Exception as exc:
            logger.error(f"ContextWindow.fit failed: {exc}")
            raise

    async def _truncate_fifo(self, max_tokens: int) -> None:
        """FIFO 截断：丢弃最旧的切片，直到满足限制。"""
        try:
            while self.slices and self.total_tokens > max_tokens and len(self.slices) > self.config.min_messages_to_keep:
                removed = self.slices.pop(0)
                logger.debug("FIFO remove slice: %s", removed.slice_id)
        except Exception as exc:
            logger.error(f"_truncate_fifo failed: {exc}")
            raise

    async def _truncate_recency(self, max_tokens: int) -> None:
        """RECENCY 截断：保留最近 N 条，丢弃其余。"""
        try:
            keep = self.config.min_messages_to_keep
            while len(self.slices) > keep and self.total_tokens > max_tokens:
                removed = self.slices.pop(0)
                logger.debug("RECENCY remove slice: %s", removed.slice_id)
        except Exception as exc:
            logger.error(f"_truncate_recency failed: {exc}")
            raise

    async def _truncate_relevance(self, max_tokens: int) -> None:
        """RELEVANCE 截断：按相关性评分丢弃最低分切片。"""
        try:
            # 为每个切片评分（低到高排序）
            scored = [
                (s, self.scorer.score_slice(s, self._current_intent))
                for s in self.slices
            ]
            scored.sort(key=lambda x: x[1])

            while scored and self.total_tokens > max_tokens and len(scored) > self.config.min_messages_to_keep:
                slice_to_remove, score = scored.pop(0)
                if slice_to_remove in self.slices:
                    self.slices.remove(slice_to_remove)
                    logger.debug("RELEVANCE remove slice: %s (score=%.2f)", slice_to_remove.slice_id, score)
        except Exception as exc:
            logger.error(f"_truncate_relevance failed: {exc}")
            raise

    async def _truncate_summary(self, max_tokens: int) -> None:
        """SUMMARY 截断：将旧切片压缩为摘要，用摘要替代原文。"""
        try:
            while self.slices and self.total_tokens > max_tokens and len(self.slices) > self.config.min_messages_to_keep:
                # 取最旧的若干切片（一次取 3 个，避免过度压缩）
                batch_size = min(3, len(self.slices) - self.config.min_messages_to_keep)
                if batch_size <= 0:
                    break
                batch = self.slices[:batch_size]
                session_id = batch[0].session_id
                summary = await self.compressor.compress(batch, session_id)
                self.summaries.append(summary)
                for s in batch:
                    self.slices.remove(s)
                logger.debug("SUMMARY compressed %d slices into summary %s", batch_size, summary.summary_id)
        except Exception as exc:
            logger.error(f"_truncate_summary failed: {exc}")
            raise

    async def _truncate_hybrid(self, max_tokens: int) -> None:
        """HYBRID 截断：先 FIFO 到阈值，再 SUMMARY。"""
        try:
            # 阶段 1: 简单 FIFO 快速降压到 1.5 倍限制
            intermediate_limit = int(max_tokens * 1.5)
            while self.slices and self.total_tokens > intermediate_limit and len(self.slices) > self.config.min_messages_to_keep:
                removed = self.slices.pop(0)
                logger.debug("HYBRID phase-1 FIFO remove: %s", removed.slice_id)

            # 阶段 2: 若仍超限，使用 SUMMARY
            if self.total_tokens > max_tokens:
                await self._truncate_summary(max_tokens)

            # 阶段 3: 若仍超限，使用 RELEVANCE
            if self.total_tokens > max_tokens:
                await self._truncate_relevance(max_tokens)
        except Exception as exc:
            logger.error(f"_truncate_hybrid failed: {exc}")
            raise

    def to_prompt_text(self) -> str:
        """将当前窗口内容转换为注入 LLM prompt 的文本。

        顺序：Summary（最旧）→ Slices（最新）。
        """
        parts: List[str] = []
        if self.summaries:
            parts.append("[CONTEXT SUMMARIES]")
            for summary in self.summaries:
                parts.append(summary.to_prompt_text())
        if self.slices:
            parts.append("[RECENT CONTEXT]")
            for slice_obj in self.slices:
                parts.append(slice_obj.to_prompt_text())
        return "\n\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """获取窗口统计信息。"""
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.config.max_tokens,
            "effective_max_tokens": self.config.effective_max_tokens,
            "slice_count": len(self.slices),
            "summary_count": len(self.summaries),
            "strategy": self.config.strategy.value,
            "current_intent": self._current_intent.category.value if self._current_intent else None,
        }
