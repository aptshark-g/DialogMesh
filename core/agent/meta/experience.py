# -*- coding: utf-8 -*-
"""自愈经验库（贝叶斯 prior 累积, 2026-08-16）。

设计: SELF_REPAIR_DESIGN_20260816 §八 + PARADIGM A13（长证明后验）+
伪二阶抽象（逆推验证的凝练）。

外部多 agent 修复无演进 = 缺"被修对象的设计约束"作先验（bc 在自己
约束上下文执行, 没有 a 的视角）。元认知持有 a 的约束 → 修复历史按
伪二阶抽象凝练为"可逆推的设计教训" → 写入经验库 → 后续诊断检索作为
prior 证据注入（贝叶斯式累积）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "data", "self_repairs.jsonl")


class ExperienceStore:
    """自愈经验库（JSONL 追加; 线程安全）。"""

    def __init__(self, path: str = "", max_entries: int = 500):
        self._path = path or _default_path()
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []
        self._max = max_entries
        self._load()

    def _load(self) -> None:
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f.readlines()[-self._max:]:
                    line = line.strip()
                    if line:
                        try:
                            self._entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("experience load failed: %s", e)

    def add(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """追加经验条目（根因/修复/设计教训/影响公理）。"""
        rec = {
            "ts": time.time(),
            "scope": str(entry.get("scope", "")),
            "root_cause": str(entry.get("root_cause", ""))[:300],
            "fix_summary": str(entry.get("fix_summary", ""))[:300],
            "design_lesson": str(entry.get("design_lesson", ""))[:500],
            "axioms": list(entry.get("axioms", [])),
            "verify_passed": bool(entry.get("verify_passed", True)),
            "source": str(entry.get("source", "diagnosis")),
        }
        with self._lock:
            self._entries.append(rec)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
            self._persist(rec)
        return rec

    def _persist(self, rec: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("experience persist failed: %s", e)

    def search(self, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """检索相似经验（诊断时作为 prior 证据注入, 贝叶斯先验）。"""
        q = (text or "").lower()
        if not q:
            return []
        scored = []
        with self._lock:
            for e in self._entries:
                hay = " ".join([
                    e.get("scope", ""), e.get("root_cause", ""),
                    e.get("fix_summary", ""), e.get("design_lesson", "")])
                score = sum(1 for w in q.split()[:8]
                            if w.lower() in hay)
                if score > 0:
                    scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total": len(self._entries),
                "recent": list(self._entries[-10:]),
            }


_store: Optional[ExperienceStore] = None


def get_experience_store(path: str = "") -> ExperienceStore:
    global _store
    if _store is None:
        _store = ExperienceStore(path=path)
    return _store


def record_experience(entry: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_experience_store().add(entry)
    except Exception:
        return {}


def search_experience(text: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        return get_experience_store().search(text, limit=limit)
    except Exception:
        return []
