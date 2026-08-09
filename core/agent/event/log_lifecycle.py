"""G2 EventLog 生命周期层 — 热全量 → 温减枝 → 冷摘要化。

G2-P3  温减枝: 全消费者已消费 + 超 retention + importance 三信号低 → 结构降级
G2-P4  冷摘要: 更老 + 锚点完整 → 语义摘要（结构降级 C 先做，LLM 摘要 B 可选）
G2-P5  A24 锚点完整性校验: 摘要锚点集 ⊇ 原文锚点集，不完整则跳过（保原文）

重要性三信号（GAP-2 定案，不 LLM 打分）:
  activation_count（payload 内已有）+ recency（created_at）+ semantic_value（锚点数）
"""
from __future__ import annotations
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.agent.api.api_event_log import EventLog

logger = logging.getLogger(__name__)

# G2-P5: 锚点 key（与 EventLog.ANCHOR_KEYS 对齐 + l2_summary）
ANCHOR_KEYS = EventLog.ANCHOR_KEYS + ("l2_summary",)


class EventLogLifecycle:
    """EventLog 三阶段生命周期管理（G2）。"""

    def __init__(self, log: EventLog, retention_hours: int = 24,
                 cold_age_hours: Optional[int] = None,
                 importance_threshold: float = 0.3,
                 warm_batch: int = 200,
                 cold_batch: int = 100,
                 llm_summarizer: Optional[Callable[[dict], Optional[str]]] = None):
        self._log = log
        self._retention_hours = retention_hours
        self._cold_age_hours = cold_age_hours or retention_hours * 3
        self._importance_threshold = importance_threshold
        self._warm_batch = warm_batch
        self._cold_batch = cold_batch
        self._llm_summarizer = llm_summarizer
        self._stats = {
            "warm_pruned": 0,
            "cold_summarized": 0,
            "skipped_anchor_incomplete": 0,
            "skipped_importance": 0,
            "last_run": 0.0,
        }

    # ── 三信号重要性 ─────────────────────────────────────────── #

    @staticmethod
    def _anchor_ids(payload: dict) -> set:
        """提取锚点 ID 集（cross_ref 条目 + l2_summary 存在标记）。"""
        ids = set()
        for key in ANCHOR_KEYS:
            v = payload.get(key)
            if isinstance(v, (list, tuple, set)):
                for item in v:
                    if isinstance(item, dict):
                        ids.add(str(item.get("id") or item.get("target") or item))
                    else:
                        ids.add(str(item))
            elif isinstance(v, dict):
                ids.update(str(k) for k in v.keys())
            elif v:
                ids.add(str(v))
        return ids

    def _importance(self, evt: dict) -> float:
        """三信号加权（0..1）。激活/锚点越多、越新 → 越重要。"""
        payload = evt.get("payload") or {}
        activation = float(payload.get("activation_count", 0) or 0)
        act_sig = min(1.0, activation / 10.0)

        age = max(0.0, time.time() - float(evt.get("created_at", time.time())))
        recency_sig = max(0.0, 1.0 - age / (self._retention_hours * 3600))

        sem_sig = min(1.0, float(evt.get("semantic_value", 0)) / 5.0)

        return 0.4 * recency_sig + 0.3 * act_sig + 0.3 * sem_sig

    # ── G2-P5: A24 锚点完整性校验 ─────────────────────────────── #

    def anchor_integrity(self, original_payload: dict, summary_payload: dict) -> bool:
        """摘要锚点集 == 原文锚点集（⊇ 且不引入歧义）。不完整 → False（跳过减枝）。"""
        orig = self._anchor_ids(original_payload)
        summ = self._anchor_ids(summary_payload)
        if not orig:
            # 无锚点 → 无锚点可保（结构降级不违反 A24）
            return True
        return orig <= summ

    # ── 结构降级 C（默认） ─────────────────────────────────────── #

    def _structural_summary(self, evt: dict) -> dict:
        """结构降级 C: 保留锚点（cross_ref/l2_summary）+ 顶层键摘要，丢弃非锚点细节。"""
        payload = evt.get("payload") or {}
        anchors = {k: v for k, v in payload.items() if k in ANCHOR_KEYS}
        top = {k: _type_name(v) for k, v in payload.items() if k not in ANCHOR_KEYS}
        return {
            "_pruned": True,
            "summary": {
                "kind": evt.get("kind", ""),
                "top": top,
            },
            **anchors,
        }

    def _llm_summary(self, evt: dict) -> Optional[dict]:
        """LLM 摘要 B（可选增强）。失败降级为结构摘要。"""
        if not self._llm_summarizer:
            return None
        try:
            text = self._llm_summarizer(evt.get("payload") or {})
            if not text:
                return None
            payload = evt.get("payload") or {}
            anchors = {k: v for k, v in payload.items() if k in ANCHOR_KEYS}
            return {
                "_pruned": True,
                "summary": {
                    "kind": evt.get("kind", ""),
                    "llm_text": text,
                },
                **anchors,
            }
        except Exception as e:
            logger.warning("LLM summarizer failed, fallback structural: %s", e)
            return None

    # ── G2-P3: 温减枝 ──────────────────────────────────────────── #

    def prune_warm(self, limit: Optional[int] = None) -> Dict[str, int]:
        """温减枝: 全消费者已消费 + 超期 + 三信号低于阈值 → 结构降级（锚点保留）。"""
        n = limit or self._warm_batch
        pruned = skipped_importance = 0
        for evt in self._log.prunable_events(limit=n, retention_sec=self._retention_hours * 3600):
            if self._importance(evt) >= self._importance_threshold:
                skipped_importance += 1
                continue
            original = evt.get("payload") or {}
            summary = self._llm_summary(evt) or self._structural_summary(evt)
            if not self.anchor_integrity(original, summary):
                self._stats["skipped_anchor_incomplete"] += 1
                continue
            self._log.update_payload(evt["event_id"], summary)
            pruned += 1
        self._stats["warm_pruned"] += pruned
        self._stats["skipped_importance"] += skipped_importance
        self._stats["last_run"] = time.time()
        logger.info("EventLogLifecycle prune_warm: pruned=%d skip_importance=%d",
                    pruned, skipped_importance)
        return {"pruned": pruned, "skipped_importance": skipped_importance}

    # ── G2-P4: 冷摘要化 ────────────────────────────────────────── #

    def summarize_cold(self, limit: Optional[int] = None) -> Dict[str, int]:
        """冷摘要: 更老（cold_age）+ 锚点完整 → 语义摘要；锚点不完整跳过保原文。"""
        n = limit or self._cold_batch
        summarized = skipped_anchor = 0
        for evt in self._log.prunable_events(limit=n, retention_sec=self._cold_age_hours * 3600):
            original = evt.get("payload") or {}
            if original.get("_pruned"):  # 已减枝过（结构降级后不再二次摘要）
                continue
            if not self._anchor_ids(original):
                # 无锚点 → 摘要无意义，直接跳过（A24 无锚可保）
                continue
            summary = self._llm_summary(evt) or self._structural_summary(evt)
            if not self.anchor_integrity(original, summary):
                self._stats["skipped_anchor_incomplete"] += 1
                skipped_anchor += 1
                continue
            self._log.update_payload(evt["event_id"], summary)
            summarized += 1
        self._stats["cold_summarized"] += summarized
        self._stats["last_run"] = time.time()
        logger.info("EventLogLifecycle summarize_cold: summarized=%d skip_anchor=%d",
                    summarized, skipped_anchor)
        return {"summarized": summarized, "skipped_anchor_incomplete": skipped_anchor}

    # ── 一键运行 + 白盒 ────────────────────────────────────────── #

    def run_gc(self) -> Dict[str, int]:
        """完整生命周期 GC：温减枝 + 冷摘要。"""
        warm = self.prune_warm()
        cold = self.summarize_cold()
        return {**warm, **cold}

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


def _type_name(v: Any) -> str:
    if isinstance(v, str):
        return v[:40]
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    return type(v).__name__


__all__ = ["EventLogLifecycle", "ANCHOR_KEYS"]
