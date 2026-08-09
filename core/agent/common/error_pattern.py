# -*- coding: utf-8 -*-
"""错误模式 → 元认知反思（ERROR_META_REFLECTION_20260806.md §三）.

治本机制: 同类错误重复出现 = 系统性问题信号, 不是逐个 patch 治标.

双触发通道:
  E5 规则触发: record() 滑动窗口计数 ≥ 阈值（默认 3）→ meta_advice 事件
  E6 用户明示: explicit_trigger()（用户说"反复出现"）→ 最高优先级反思

事件走 decision_bus（kind=meta_advice, dimension=error_pattern.<type>）,
前端可回看/介入; 无 bus 时安全降级（内存计数, 不阻塞）.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from core.agent.common.text_utils import normalize_text

logger = logging.getLogger(__name__)

# 默认阈值: 同类错误出现 3 次 → 自动反思
DEFAULT_THRESHOLD = 3
# 滑动窗口大小（按发生次数）
DEFAULT_WINDOW = 50
# E6 用户明示触发关键词（"这个反复出现" 等）
EXPLICIT_PHRASES = (
    "反复出现", "又失败了", "一直出错", "老是", "每次都", "又来了",
    "同样的错误", "重复出现", "老出问题", "又错了", "一直失败",
)

# 错误类型分类（ERROR_META_REFLECTION §一 三类 + 泛型）
ERROR_TYPES = {"type_mismatch", "encoding", "zh_match", "serialization", "unknown"}


def classify_error(error_text: str) -> str:
    """按错误文本归类（关键词匹配, 纯算法零 LLM）."""
    if not error_text:
        return "unknown"
    t = normalize_text(error_text)
    tl = t.lower()
    # 类型/签名错误
    if any(k in tl for k in (
            "typeerror", "type mismatch", "not subscriptable", "missing required",
            "attributeerror", "keyerror", "valueerror", "expected", "got ")):
        return "type_mismatch"
    # 序列化/JSON
    if any(k in tl for k in (
            "json", "serialize", "serialization", "not json serializable",
            "deserialize", "yaml", "marshal")):
        return "serialization"
    # 编码问题（json/序列化之后, 避免 "json decode" 误判 encoding）
    if any(k in t for k in (
            "????", "乱码", "encode", "decode", "utf-8", "utf8", "unicode",
            "gbk", "codec", "character")):
        return "encoding"
    # 中文匹配
    if any(k in t for k in ("匹配", "discover", "no match", "关键词", "keyword")):
        return "zh_match"
    return "unknown"


def maybe_user_explicit(text: str) -> bool:
    """E6: 用户明示"反复出现"类表达 → 触发最高优先级反思."""
    if not text:
        return False
    t = normalize_text(text)
    return any(p in t for p in EXPLICIT_PHRASES)


class ErrorPatternTracker:
    """错误模式计数 → meta_advice 反思事件（E5 + E6）.

    record(error_type, example) — 每次错误上报; 滑动窗口内同类型 ≥ 阈值
      时写 meta_advice 事件（自动反思, 不阻塞）。
    explicit_trigger(...)       — 用户明示 → 最高优先级反思事件。
    """

    def __init__(self, decision_bus=None, threshold: int = DEFAULT_THRESHOLD,
                 window: int = DEFAULT_WINDOW):
        self._bus = decision_bus
        self.threshold = threshold
        self.window = window
        self._counts: Dict[str, Deque[float]] = {}
        self._examples: Dict[str, Deque[str]] = {}

    def attach_bus(self, bus):
        if bus is not None:
            self._bus = bus

    def record(self, error_type: str, example: str = "",
               request_id: str = "", turn: int = 0) -> Dict[str, Any]:
        """上报一次错误. 返回 {"triggered": bool, "count": int, ...}."""
        if error_type not in ERROR_TYPES:
            error_type = "unknown"
        now = time.time()
        q = self._counts.setdefault(error_type, deque(maxlen=self.window))
        prev_count = len(q)
        q.append(now)
        count = len(q)
        if example:
            exq = self._examples.setdefault(error_type, deque(maxlen=5))
            exq.append(str(example)[:200])
        # 跨阈值判定（prev < threshold ≤ count）— 只在跨越阈值瞬间触发一次,
        # 窗口满后持续 ≥ 阈值不重复发事件
        if prev_count < self.threshold and count >= self.threshold:
            ev = self._emit_advice(
                error_type, count, request_id, turn, actor="meta",
                reason=f"error_pattern.{error_type} 出现 {count} 次（滑动窗口 {self.window}）",
                comment="; ".join(list(self._examples.get(error_type, []))[-3:]),
            )
            return {"triggered": True, "count": count, "event": ev}
        return {"triggered": False, "count": count}

    def explicit_trigger(self, error_type: str = "user_explicit",
                         reason: str = "", request_id: str = "",
                         turn: int = 0) -> Dict[str, Any]:
        """E6: 用户明示触发 → 最高优先级反思（不计入滑动窗口）."""
        reason = f"用户明示: {reason}" if reason else "用户明示: 问题反复出现, 触发最高优先级反思"
        ev = self._emit_advice(
            error_type, count=None, request_id=request_id, turn=turn,
            actor="user", priority="high",
            reason=reason,
        )
        return {"triggered": True, "event": ev}

    def _emit_advice(self, error_type: str, count: Optional[int],
                     request_id: str, turn: int, actor: str,
                     reason: str, comment: str = "",
                     priority: str = "auto") -> Dict[str, Any]:
        bus = self._bus
        if bus is None:
            return {"kind": "meta_advice", "dimension": f"error_pattern.{error_type}",
                    "reason": reason, "comment": comment, "status": "proposed"}
        try:
            d = bus.log(
                kind="meta_advice",
                dimension=f"error_pattern.{error_type}",
                before=None,
                after={"occurrence": count, "priority": priority} if count is not None
                      else {"priority": priority},
                reason=reason,
                actor=actor,
                comment=comment,
                status="proposed",
                request_id=request_id,
                turn=turn,
            )
            return d
        except Exception as e:
            logger.debug("meta_advice event failed: %s", e)
            return {"kind": "meta_advice", "dimension": f"error_pattern.{error_type}",
                    "reason": reason, "status": "proposed"}

    def counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._counts.items()}

    def summary(self) -> Dict[str, Any]:
        return {
            "threshold": self.threshold,
            "window": self.window,
            "counts": self.counts(),
            "examples": {k: list(v) for k, v in self._examples.items()},
        }
