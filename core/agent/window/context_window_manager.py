# -*- coding: utf-8 -*-
"""
core/agent/window/context_window_manager.py
──────────────────────────────────────────
Context window manager: budget-aware history compression.

设计要点：
  - 从 ConfigManager 读取 context_window 和 prompt_budget 配置
  - 计算三层预算：Hot / Warm / Cold（按轮数 + token 双重限制）
  - 输出压缩后的 HistoryEntry 列表 + 统计元数据
  - 与 PCR 链集成：替换 session_history 的裸透传
  - 16K 默认窗口，当前预算占用约 50%（余量 7K tokens）
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.pcr.datacontract import HistoryEntry
from core.agent.window.token_counter import TokenCounter
from core.agent.window.compressor import (
    CompressionResult,
    Compressor,
    HierarchicalCompressor,
    PassThroughCompressor,
    TruncationCompressor,
)
from core.agent.window.llm_compressor import LLMCompressor


class WindowBudget:
    """
    窗口预算配置。
    基于 LLM context_window 和 prompt_budget 比例计算绝对 token 数。
    """

    def __init__(
        self,
        context_window: int = 16000,
        system_ratio: float = 0.05,
        history_ratio: float = 0.10,
        glossary_ratio: float = 0.05,
        output_ratio: float = 0.30,
        reserve_ratio: float = 0.10,
        hot_turns: int = 5,
        warm_turns: int = 15,
        cold_turns: int = 80,
    ):
        self.context_window = context_window
        self.system_ratio = system_ratio
        self.history_ratio = history_ratio
        self.glossary_ratio = glossary_ratio
        self.output_ratio = output_ratio
        self.reserve_ratio = reserve_ratio
        self.hot_turns = hot_turns
        self.warm_turns = warm_turns
        self.cold_turns = cold_turns

        # 绝对 token 预算
        self.system_tokens = int(context_window * system_ratio)
        self.history_tokens = int(context_window * history_ratio)
        self.glossary_tokens = int(context_window * glossary_ratio)
        self.output_tokens = int(context_window * output_ratio)
        self.reserve_tokens = int(context_window * reserve_ratio)

        # 可用历史 token（历史预算内再分配给 Hot/Warm）
        # Hot 占 history 的 60%，Warm 占 40%（经验值）
        self.hot_tokens = int(self.history_tokens * 0.6)
        self.warm_tokens = int(self.history_tokens * 0.4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_window": self.context_window,
            "system_tokens": self.system_tokens,
            "history_tokens": self.history_tokens,
            "glossary_tokens": self.glossary_tokens,
            "output_tokens": self.output_tokens,
            "reserve_tokens": self.reserve_tokens,
            "hot_turns": self.hot_turns,
            "warm_turns": self.warm_turns,
            "cold_turns": self.cold_turns,
            "hot_tokens": self.hot_tokens,
            "warm_tokens": self.warm_tokens,
        }

    @classmethod
    def from_config(cls, cfg: Any) -> "WindowBudget":
        """从 AgentConfig 构建预算。"""
        # 默认回退
        context_window = 16000
        system_ratio = 0.05
        history_ratio = 0.10
        glossary_ratio = 0.05
        output_ratio = 0.30
        reserve_ratio = 0.10
        hot_turns = 5
        warm_turns = 15
        cold_turns = 80

        # 尝试读取 llm_profiles 默认配置
        try:
            if hasattr(cfg, "llm_profiles") and cfg.llm_profiles:
                default_profile = cfg.llm_profiles.get("default", {})
                if hasattr(default_profile, "context_window"):
                    context_window = default_profile.context_window
                elif isinstance(default_profile, dict):
                    context_window = default_profile.get("context_window", context_window)
        except Exception:
            pass

        # 尝试读取 prompt_budget
        try:
            if hasattr(cfg, "prompt_budget") and cfg.prompt_budget:
                pb = cfg.prompt_budget
                if hasattr(pb, "system_prompt_max_ratio"):
                    system_ratio = pb.system_prompt_max_ratio
                    history_ratio = pb.history_max_ratio
                    glossary_ratio = pb.glossary_max_ratio
                    output_ratio = pb.output_max_ratio
                    reserve_ratio = pb.reserve_ratio
                elif isinstance(pb, dict):
                    system_ratio = pb.get("system_prompt_max_ratio", system_ratio)
                    history_ratio = pb.get("history_max_ratio", history_ratio)
                    glossary_ratio = pb.get("glossary_max_ratio", glossary_ratio)
                    output_ratio = pb.get("output_max_ratio", output_ratio)
                    reserve_ratio = pb.get("reserve_ratio", reserve_ratio)
        except Exception:
            pass

        # 尝试读取 context_window 阈值
        try:
            if hasattr(cfg, "thresholds") and cfg.thresholds:
                cw = cfg.thresholds.get("context_window", {}) if isinstance(cfg.thresholds, dict) else {}
                if hasattr(cfg.thresholds, "context_window"):
                    cw = cfg.thresholds.context_window
                if isinstance(cw, dict):
                    hot_turns = cw.get("hot_max", hot_turns)
                    warm_turns = cw.get("warm_max", warm_turns)
                    cold_turns = cw.get("cold_max", cold_turns)
        except Exception:
            pass

        return cls(
            context_window=context_window,
            system_ratio=system_ratio,
            history_ratio=history_ratio,
            glossary_ratio=glossary_ratio,
            output_ratio=output_ratio,
            reserve_ratio=reserve_ratio,
            hot_turns=hot_turns,
            warm_turns=warm_turns,
            cold_turns=cold_turns,
        )


class ContextWindowManager:
    """
    上下文窗口管理器。

    使用方式：
        mgr = ContextWindowManager()
        compressed, meta = mgr.compress(history_entries)
        # compressed 用于填入 PCRInput_v1.session_history
    """

    def __init__(
        self,
        budget: Optional[WindowBudget] = None,
        compressor: Optional[Compressor] = None,
    ):
        self._budget = budget
        self._compressor = compressor
        self._counter = TokenCounter()
        self._default_budget: Optional[WindowBudget] = None

        if self._budget is None:
            self._budget = self._load_budget_from_config()

        if self._compressor is None:
            self._compressor = self._build_default_compressor()

    # ── 配置加载 ───────────────────────────────────────────

    def _load_budget_from_config(self) -> WindowBudget:
        """从 ConfigManager 加载预算配置。"""
        try:
            from core.agent.config import get_config
            cfg = get_config()
            return WindowBudget.from_config(cfg)
        except Exception:
            # 回退到硬编码默认值
            return WindowBudget()

    def _build_default_compressor(self) -> Compressor:
        """基于预算构建默认分层压缩器。"""
        b = self._budget
        # 检查配置是否启用 LLM 智能摘要
        llm_compressor = None
        try:
            from core.agent.config import config as cfg_mgr
            cfg = cfg_mgr.get()
            if hasattr(cfg, "prompt_budget") and cfg.prompt_budget:
                # 如果预留比例 > 0 且上下文窗口较大，启用 LLM 摘要
                if b.reserve_tokens > 0 and b.context_window >= 16000:
                    llm_compressor = LLMCompressor()
        except Exception:
            pass

        return HierarchicalCompressor(
            hot_max_turns=b.hot_turns,
            warm_max_turns=b.warm_turns,
            cold_max_turns=b.cold_turns,
            hot_max_tokens=b.hot_tokens,
            warm_max_tokens=b.warm_tokens,
            enable_cold_summary=False,  # 默认不生成 Cold 摘要（按需启用）
            llm_compressor=llm_compressor,
        )

    # ── 核心 API ───────────────────────────────────────────

    def compress(
        self, entries: List[HistoryEntry]
    ) -> Tuple[List[HistoryEntry], Dict[str, Any]]:
        """
        压缩历史记录到预算内。

        :return: (compressed_entries, metadata)
        """
        if not entries:
            return [], {"status": "empty", "tokens_before": 0, "tokens_after": 0}

        tokens_before = self._counter.estimate_entries(entries)

        # 如果总 token 在预算内，直接透传
        if tokens_before <= self._budget.history_tokens:
            return list(entries), {
                "status": "pass_through",
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "compression_ratio": 1.0,
                "budget": self._budget.to_dict(),
            }

        # 执行压缩
        result = self._compressor.compress(entries)
        tokens_after = self._counter.estimate_entries(result.entries)

        # 如果压缩后仍超预算，追加截断（兜底）
        if tokens_after > self._budget.history_tokens:
            fallback = TruncationCompressor(
                max_turns=self._budget.hot_turns + self._budget.warm_turns,
                max_tokens=self._budget.history_tokens,
            )
            result = fallback.compress(result.entries)
            tokens_after = self._counter.estimate_entries(result.entries)

        compression_ratio = tokens_after / tokens_before if tokens_before > 0 else 1.0

        metadata = {
            "status": "compressed",
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "compression_ratio": round(compression_ratio, 3),
            "budget": self._budget.to_dict(),
            "compression": result.to_dict(),
            "timestamp": time.time(),
        }

        return result.entries, metadata

    def get_budget_summary(self) -> Dict[str, Any]:
        """获取当前预算摘要。"""
        return self._budget.to_dict()

    def get_stats(self, entries: List[HistoryEntry]) -> Dict[str, Any]:
        """获取当前历史记录的统计（不压缩）。"""
        if not entries:
            return {"turns": 0, "tokens": 0, "within_budget": True}

        tokens = self._counter.estimate_entries(entries)
        return {
            "turns": len(entries),
            "tokens": tokens,
            "budget_tokens": self._budget.history_tokens,
            "within_budget": tokens <= self._budget.history_tokens,
            "usage_ratio": round(tokens / self._budget.history_tokens, 3) if self._budget.history_tokens > 0 else 0.0,
        }
