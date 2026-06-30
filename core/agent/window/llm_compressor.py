# -*- coding: utf-8 -*-
"""
core/agent/window/llm_compressor.py
──────────────────────────────────
LLM-driven smart Cold-summary compressor.

设计要点：
  - 可选依赖：LLMProvider 不可用时自动回退到规则压缩
  - 使用索引卡提示词（简洁，<150 tokens）
  - 生成自然语言摘要，比规则压缩更连贯
  - 失败时回退到 _generate_cold_summary（本地规则）
  - 遵循 prompt_budget：摘要控制在 200 tokens 以内

使用条件：
  - HierarchicalCompressor.enable_cold_summary=True 且 cold_entries 较多
  - 或用户显式设置 llm_compressor=True
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from core.agent.pcr.datacontract import HistoryEntry
from core.agent.window.token_counter import TokenCounter

try:
    from core.agent.llm_providers.base import LLMProvider, GenerateRequest
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMProvider = None
    GenerateRequest = None

import logging
logger = logging.getLogger(__name__)


# ── 默认系统提示词（索引卡模式）────────────────────────────

_DEFAULT_SUMMARY_PROMPT = """你是对话摘要助手。将以下对话历史压缩为 1-2 句连贯摘要。

保留：用户画像特征、主要技术主题、高频意图、关键实体。
丢弃：具体数值、地址、详细输出、问候语。

格式：
[历史摘要] 用户主要关注{主题}，涉及{意图}等操作，共{N}轮对话。

只输出摘要文本，不要解释。"""


class LLMCompressor:
    """
    LLM 驱动的智能 Cold 摘要压缩器。

    不依赖外部 NLP 库，只依赖可选的 LLMProvider。
    如果 LLM 不可用或调用失败，回退到本地规则摘要。
    """

    def __init__(
        self,
        provider: Optional[Any] = None,
        max_summary_tokens: int = 200,
        system_prompt: Optional[str] = None,
        timeout_seconds: float = 10.0,
        fallback_to_rule: bool = True,
    ):
        """
        :param provider: LLMProvider 实例（None 则尝试从配置加载）
        :param max_summary_tokens: 摘要最大 token 数（控制预算）
        :param system_prompt: 自定义系统提示词（None 用默认）
        :param timeout_seconds: LLM 调用超时
        :param fallback_to_rule: LLM 失败时是否回退到规则压缩
        """
        self._provider = provider
        self._max_summary_tokens = max_summary_tokens
        self._system_prompt = system_prompt or _DEFAULT_SUMMARY_PROMPT
        self._timeout = timeout_seconds
        self._fallback = fallback_to_rule
        self._counter = TokenCounter()

        # 延迟加载 provider（如果未传入）
        self._lazy_loaded = False

    # ── 核心 API ───────────────────────────────────────────

    def compress(self, entries: List[HistoryEntry]) -> Optional[HistoryEntry]:
        """
        对历史记录生成 LLM 摘要。

        :return: HistoryEntry(role="system", expectation="cold_summary")
                 或 None（LLM 不可用且 fallback=False）
        """
        if not entries:
            return None

        provider = self._get_provider()
        if provider is None:
            if self._fallback:
                return self._rule_fallback(entries)
            return None

        # 构建极简 prompt（控制 token 预算）
        prompt = self._build_prompt(entries)

        # 检查 prompt 是否过长（防御性）
        prompt_tokens = self._counter.estimate_text(prompt)
        if prompt_tokens > 2000:
            # 截断历史到最近 20 轮
            entries = entries[-20:]
            prompt = self._build_prompt(entries)

        try:
            start = time.time()
            result = self._call_llm(provider, prompt)
            latency = (time.time() - start) * 1000

            if result and result.strip():
                logger.debug("LLMCompressor: summary generated in %.1fms", latency)
                return HistoryEntry(
                    role="system",
                    content=result.strip(),
                    expectation="cold_summary",
                    metadata={
                        "compressed_turns": len(entries),
                        "llm_summary": True,
                        "latency_ms": round(latency, 1),
                    },
                )

        except Exception as exc:
            logger.warning("LLMCompressor failed: %s", exc)

        # 回退
        if self._fallback:
            return self._rule_fallback(entries)
        return None

    # ── 内部 ───────────────────────────────────────────

    def _get_provider(self) -> Optional[Any]:
        """获取 LLM Provider（延迟加载）。"""
        if self._provider is not None:
            return self._provider

        if not HAS_LLM or self._lazy_loaded:
            return None

        self._lazy_loaded = True

        # 尝试从 ConfigManager 加载默认 provider
        try:
            from core.agent.config import config as cfg_mgr
            cfg = cfg_mgr.get()

            # 检查是否有 llm_providers 配置
            if hasattr(cfg, "llm_profiles") and cfg.llm_profiles:
                # 尝试加载 local_thinking 或 default profile
                profile = cfg_mgr.get_llm_profile("local_thinking")
                # 注：这里需要实际创建 provider 实例，但 ConfigManager 只存配置
                # 实际创建需要 provider 工厂，这里标记为无法自动加载
                logger.debug("LLMCompressor: config found but no auto-instantiation path")
        except Exception:
            pass

        return None

    def _build_prompt(self, entries: List[HistoryEntry]) -> str:
        """构建极简 LLM prompt（控制长度）。"""
        lines = []
        # 只取 user 和 assistant 的角色+内容，忽略 tool/system
        for e in entries:
            if e.role in ("user", "assistant"):
                # 截断单条内容到 80 字符
                content = e.content[:80] + "..." if len(e.content) > 80 else e.content
                lines.append(f"{e.role}: {content}")

        # 统计信息
        user_count = sum(1 for e in entries if e.role == "user")
        assistant_count = sum(1 for e in entries if e.role == "assistant")
        expectations = list(dict.fromkeys(
            e.expectation for e in entries if e.expectation and e.expectation not in ("", "SYSTEM", "UNKNOWN")
        ))[:5]

        header = (
            f"对话历史：共 {len(entries)} 轮，"
            f"用户 {user_count} 轮，助手 {assistant_count} 轮。"
        )
        if expectations:
            header += f"主要意图：{', '.join(expectations)}。"

        return header + "\n" + "\n".join(lines[-30:])  # 最多 30 行

    def _call_llm(self, provider: Any, prompt: str) -> str:
        """调用 LLM 生成摘要。"""
        if GenerateRequest is None:
            raise RuntimeError("LLMProvider not available")

        req = GenerateRequest(
            prompt=prompt,
            system_prompt=self._system_prompt,
            max_tokens=self._max_summary_tokens,
            temperature=0.3,  # 低温度，确保稳定
        )
        result = provider.generate(req)

        if not result.metrics.success:
            raise RuntimeError(f"LLM generation failed: {result.metrics.error_message}")

        return result.text or ""

    def _rule_fallback(self, entries: List[HistoryEntry]) -> HistoryEntry:
        """LLM 失败时的规则回退（与 HierarchicalCompressor 一致）。"""
        expectations = [e.expectation for e in entries if e.expectation]
        roles = [e.role for e in entries]
        user_count = roles.count("user")
        assistant_count = roles.count("assistant")

        content = (
            f"[历史摘要] 共 {len(entries)} 轮对话，"
            f"用户 {user_count} 轮，助手 {assistant_count} 轮。"
        )
        if expectations:
            uniq = list(dict.fromkeys(expectations))[:5]
            content += f" 涉及意图：{', '.join(uniq)}。"

        return HistoryEntry(
            role="system",
            content=content,
            expectation="cold_summary",
            metadata={"compressed_turns": len(entries), "llm_summary": False},
        )
