"""Unified Audit Trail — aggregate all user operations into one view.

Sources:
  - Git version control (version_control.py) — data changes
  - Unified event log (unified_event_log.py) — system events
  - Correction journal — profile edits
  - Switch audit log — gateway admin operations (via proxy)
  - Frontend actions — explicit log_user_action() calls

ARCHIVED (2026-08-16): A17 记录已由 decision_bus + 各子系统 JSONL 分散承担;
统一审计聚合视图属 P2（前端绑定阶段再做聚合端点）。保留代码不删（A17）。
"""
from __future__ import annotations
import json, os, time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    ts: float
    category: str              # profile | gateway | discourse_tree | behavior | parameter | meta
    action: str                # edit | create | delete | approve | reject | configure
    target: str                # what was modified
    before: Optional[str] = None
    after: Optional[str] = None
    author: str = "user"       # user | engine | meta_cognition
    session_id: str = ""
    verified: bool = False     # meta-cognition reviewed?


class AuditTrail:
    """Unified audit trail aggregating all sources."""

    def __init__(self, persist_dir: str = "data/audit"):
        self._dir = persist_dir
        self._records: List[AuditRecord] = []
        os.makedirs(persist_dir, exist_ok=True)
        self._load()

    def log(self, category: str, action: str, target: str,
            before: Any = None, after: Any = None, author: str = "user"):
        """Record a user operation."""
        r = AuditRecord(
            ts=time.time(), category=category, action=action, target=target,
            before=str(before)[:200] if before else None,
            after=str(after)[:200] if after else None,
            author=author,
        )
        self._records.append(r)

        # Append to daily audit file
        date = time.strftime("%Y-%m-%d")
        path = f"{self._dir}/audit_{date}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": r.ts, "category": r.category, "action": r.action,
                "target": r.target, "before": r.before, "after": r.after,
                "author": r.author, "verified": r.verified,
            }, ensure_ascii=False) + "\n")

        return r

    def query(self, category: str = "", action: str = "", 
              target: str = "", limit: int = 50) -> List[AuditRecord]:
        """Query audit records with optional filters."""
        results = []
        for r in reversed(self._records):
            if category and r.category != category: continue
            if action and r.action != action: continue
            if target and target not in r.target: continue
            results.append(r)
            if len(results) >= limit: break
        return results

    def recent_user_actions(self, limit: int = 20) -> List[AuditRecord]:
        """Recent actions by the user (not engine/meta)."""
        return [r for r in reversed(self._records) 
                if r.author == "user"][:limit]

    def stats(self) -> Dict[str, Any]:
        by_category = {}
        by_action = {}
        user_edits = 0
        engine_edits = 0
        for r in self._records:
            by_category[r.category] = by_category.get(r.category, 0) + 1
            by_action[r.action] = by_action.get(r.action, 0) + 1
            if r.author == "user": user_edits += 1
            else: engine_edits += 1
        
        return {
            "total_operations": len(self._records),
            "user_operations": user_edits,
            "system_operations": engine_edits,
            "by_category": by_category,
            "by_action": by_action,
            "last_action": {
                "ts": self._records[-1].ts if self._records else 0,
                "category": self._records[-1].category if self._records else "",
                "action": self._records[-1].action if self._records else "",
                "target": self._records[-1].target if self._records else "",
            } if self._records else None,
        }

    def _load(self):
        """Load today's audit file."""
        date = time.strftime("%Y-%m-%d")
        path = f"{self._dir}/audit_{date}.jsonl"
        if not os.path.exists(path): return
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    self._records.append(AuditRecord(
                        ts=d["ts"], category=d["category"], action=d["action"],
                        target=d["target"], before=d.get("before"),
                        after=d.get("after"), author=d.get("author", "user"),
                        verified=d.get("verified", False),
                    ))
                except Exception: pass

    def history(self, days_back: int = 7) -> Dict[str, int]:
        """Audit activity over past N days."""
        result = {}
        cutoff = time.time() - days_back * 86400
        for r in self._records:
            if r.ts >= cutoff:
                day = time.strftime("%Y-%m-%d", time.localtime(r.ts))
                result[day] = result.get(day, 0) + 1
        return result
