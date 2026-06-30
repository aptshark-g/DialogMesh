# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/entity_cache.py
────────────────────────────────────────────
Entity cache: LRU ring buffer for historical entity backfill.

Session-scoped; injected by SessionManager, consumed by HeaderInjector.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Tuple


class EntityCache:
    """
    LRU 环状缓冲池。
    每轮结束，将 ParsedClause 中提取出的实体（包括通过 KB 补全的）压入缓存。
    """

    def __init__(self, max_rounds: int = 5):
        self._max_rounds = max_rounds
        self._entries: deque = deque(maxlen=max_rounds)
        # entries: List[{"turn_index": int, "entities": List[Dict]}]

    # ── 写入 ───────────────────────────────────────────

    def push(self, turn_index: int, entities: List[Dict[str, Any]]) -> None:
        """压入一轮实体。"""
        self._entries.append({"turn_index": turn_index, "entities": list(entities)})

    def clear(self) -> None:
        """清空缓存（话题切换时）。"""
        self._entries.clear()

    # ── 读取 ───────────────────────────────────────────

    def search_by_type(self, entity_type: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        按类型搜索（时间倒序）。
        返回 (value, full_entity_dict) 或 None。
        """
        for entry in reversed(self._entries):
            for entity in reversed(entry["entities"]):
                if entity.get("type") == entity_type:
                    return entity.get("value"), entity
        return None

    def search_last(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        取最近一轮的最后一个实体。
        返回 (value, full_entity_dict) 或 None。
        """
        if not self._entries:
            return None
        last = self._entries[-1]["entities"]
        if not last:
            return None
        entity = last[-1]
        return entity.get("value"), entity

    def search_by_keyword(self, keyword: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        按关键词搜索（时间倒序，部分匹配）。
        返回 (value, full_entity_dict) 或 None。
        """
        for entry in reversed(self._entries):
            for entity in reversed(entry["entities"]):
                val = str(entity.get("value", ""))
                if keyword in val or val in keyword:
                    return val, entity
        return None

    # ── 查询 ───────────────────────────────────────────

    def get_all_entities(self) -> List[Dict[str, Any]]:
        """获取所有实体（按时间顺序）。"""
        result = []
        for entry in self._entries:
            result.extend(entry["entities"])
        return result

    def get_summary(self) -> Dict[str, Any]:
        """获取缓存摘要。"""
        total = sum(len(e["entities"]) for e in self._entries)
        return {
            "rounds_cached": len(self._entries),
            "total_entities": total,
            "max_rounds": self._max_rounds,
        }

    def __repr__(self) -> str:
        return f"EntityCache(rounds={len(self._entries)}, max={self._max_rounds})"
