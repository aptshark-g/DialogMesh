# -*- coding: utf-8 -*-
"""技能生命周期 — GAP-D5（COMPLETENESS_GAP_INVENTORY §A）.

对齐 Hermes curator（benchmark GAP-2 拆条）: LEARNED_TEMPLATES 从
"只增不减"变为"活性状态机":

  active → stale（N 天未用）→ archived（M 天未用）→ pruned（P 天,
  从 LEARNED_TEMPLATES 移除, 保留元数据 provenance）

分治原则（与 Hot/Warm/Cold 同构）:
  - 确定性活性迁移（零 LLM, 纯时间/使用信号）
  - 可选 LLM 合并（curator consolidate 式, 后续 P2 接入）

保护:
  - pinned: 用户显式固定, 永不自动迁移
  - referenced: 被其他模块（cron/行为链/蓝图）引用, 不裁剪
  - use_count=0 的新技能: grace 期（stale_after 天前不裁剪）
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.blueprint.skill_registry import LEARNED_TEMPLATES

logger = logging.getLogger(__name__)

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"
STATE_PRUNED = "pruned"

# 默认时间阈值（天）— 与 Hermes curator 默认同量级
DEFAULT_STALE_AFTER_DAYS = 14
DEFAULT_ARCHIVE_AFTER_DAYS = 30
DEFAULT_PRUNE_AFTER_DAYS = 90


class SkillLifecycle:
    """LEARNED_TEMPLATES 的活性状态机（元数据平行表, 不侵入 DAG）."""

    def __init__(self, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
                 archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
                 prune_after_days: int = DEFAULT_PRUNE_AFTER_DAYS):
        self.stale_after = stale_after_days * 86400
        self.archive_after = archive_after_days * 86400
        self.prune_after = prune_after_days * 86400
        # intent -> {created_at, last_used, use_count, state, pinned, referenced_by}
        self._meta: Dict[str, Dict[str, Any]] = {}

    # ── 元数据 ──

    def register(self, intent: str, created_at: Optional[float] = None,
                 pinned: bool = False):
        """learn_blueprint 沉淀时登记（SkillRegistry 调用）."""
        now = created_at or time.time()
        if intent not in self._meta:
            self._meta[intent] = {
                "created_at": now,
                "last_used": now,
                "use_count": 0,
                "state": STATE_ACTIVE,
                "pinned": pinned,
                "referenced_by": [],
            }

    def touch(self, intent: str) -> None:
        """match 命中时更新活性（SkillRegistry.match 调用）."""
        m = self._meta.get(intent)
        if m is None:
            self.register(intent)
            m = self._meta[intent]
        m["last_used"] = time.time()
        m["use_count"] = m.get("use_count", 0) + 1
        if m["state"] in (STATE_STALE, STATE_ARCHIVED):
            # 被再次使用 → 复活
            m["state"] = STATE_ACTIVE

    def pin(self, intent: str) -> None:
        if intent not in self._meta:
            self.register(intent)
        self._meta[intent]["pinned"] = True

    def unpin(self, intent: str) -> None:
        if intent in self._meta:
            self._meta[intent]["pinned"] = False

    def add_reference(self, intent: str, referrer: str) -> None:
        """外部引用登记（cron/行为链/蓝图）— 被引用不裁剪."""
        if intent not in self._meta:
            self.register(intent)
        refs = self._meta[intent].setdefault("referenced_by", [])
        if referrer not in refs:
            refs.append(referrer)

    # ── 状态迁移（确定性, 零 LLM）──

    def apply_transitions(self, now: Optional[float] = None) -> Dict[str, int]:
        """按时间/使用做活性迁移. 返回计数 dict."""
        now = now or time.time()
        counts = {"active_to_stale": 0, "stale_to_archived": 0,
                  "archived_to_pruned": 0, "checked": 0}
        for intent, m in list(self._meta.items()):
            counts["checked"] += 1
            if m.get("pinned") or m.get("referenced_by"):
                continue
            # grace: use_count=0 的新技能不提前裁剪
            anchor = m.get("last_used") or m.get("created_at") or now
            age = now - anchor
            state = m.get("state", STATE_ACTIVE)
            if state == STATE_ACTIVE and age > self.stale_after:
                m["state"] = STATE_STALE
                counts["active_to_stale"] += 1
            elif state == STATE_STALE and age > self.archive_after:
                m["state"] = STATE_ARCHIVED
                counts["stale_to_archived"] += 1
            elif state == STATE_ARCHIVED and age > self.prune_after:
                m["state"] = STATE_PRUNED
                LEARNED_TEMPLATES.pop(intent, None)  # 从可匹配区移除
                counts["archived_to_pruned"] += 1
        if any(counts[k] for k in ("active_to_stale", "stale_to_archived",
                                   "archived_to_pruned")):
            logger.info("SkillLifecycle: %s", counts)
        return counts

    def prune_archived(self, now: Optional[float] = None) -> int:
        """强制裁剪（显式调用/维护时）. 返回裁剪数."""
        c = self.apply_transitions(now)
        return c["archived_to_pruned"]

    # ── 报告（dry-run 语义）──

    def report(self, dry_run: bool = True) -> Dict[str, Any]:
        """活性报告（dry_run=True 不迁移, 只预测）."""
        now = time.time()
        snapshot = {}
        for intent, m in self._meta.items():
            anchor = m.get("last_used") or m.get("created_at") or now
            age_days = (now - anchor) / 86400
            state = m.get("state", STATE_ACTIVE)
            if dry_run:
                if state == STATE_ACTIVE and age_days > self.stale_after / 86400:
                    state = STATE_STALE
                elif state == STATE_STALE and age_days > self.archive_after / 86400:
                    state = STATE_ARCHIVED
                elif state == STATE_ARCHIVED and age_days > self.prune_after / 86400:
                    state = STATE_PRUNED
            snapshot[intent] = {
                "state": state,
                "age_days": round(age_days, 1),
                "use_count": m.get("use_count", 0),
                "pinned": bool(m.get("pinned")),
                "referenced": bool(m.get("referenced_by")),
            }
        states = {}
        for v in snapshot.values():
            states[v["state"]] = states.get(v["state"], 0) + 1
        return {"total": len(snapshot), "by_state": states,
                "skills": snapshot, "dry_run": dry_run}

    def meta(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._meta)

