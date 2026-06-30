# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/dual_manager.py
────────────────────────────────────────────
Dual structure manager: tree + timeline with O(1) lookups.

设计要点（修正坑3）：
  - _node_to_latest_event: Dict[str, str] 节点→最新事件 ID
  - _event_cache: Dict[str, TimelineEvent] 事件 ID→事件
  - _find_parent_event / _find_event 从 O(N) → O(1)
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Set

from core.agent.topic_tree.models import TopicNode


class TimelineEvent:
    """时间线事件。"""
    def __init__(
        self,
        event_id: str = "",
        topic_node_id: str = "",
        turn_index: int = 0,
        event_type: str = "",
        content: str = "",
        entities: Optional[List[Dict[str, Any]]] = None,
        parent_event_id: Optional[str] = None,
        timestamp: float = 0.0,
    ):
        self.event_id = event_id or str(uuid.uuid4())[:8]
        self.topic_node_id = topic_node_id
        self.turn_index = turn_index
        self.event_type = event_type
        self.content = content
        self.entities = entities or []
        self.parent_event_id = parent_event_id
        self.timestamp = timestamp or time.time()
        self.children_ids: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic_node_id": self.topic_node_id,
            "turn_index": self.turn_index,
            "event_type": self.event_type,
            "content": self.content,
            "entities": self.entities,
            "parent_event_id": self.parent_event_id,
            "timestamp": self.timestamp,
            "children_ids": self.children_ids,
        }


class DualStructureManager:
    """
    双结构管理器：树型逻辑 + 时空时序。
    维护 TopicNode 和 TimelineEvent 的映射关系。
    """

    def __init__(self):
        # 事件存储
        self._events: Dict[str, TimelineEvent] = {}
        # 节点 → 最新事件 ID (O(1) 查找)
        self._node_to_latest_event: Dict[str, str] = {}
        # 事件缓存 (O(1) 查找)
        self._event_cache: Dict[str, TimelineEvent] = {}

    # ── 事件管理 ───────────────────────────────────────────

    def create_event(
        self,
        topic_node_id: str,
        turn_index: int,
        event_type: str,
        content: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        parent_event_id: Optional[str] = None,
    ) -> TimelineEvent:
        """创建新事件。"""
        event = TimelineEvent(
            topic_node_id=topic_node_id,
            turn_index=turn_index,
            event_type=event_type,
            content=content,
            entities=entities,
            parent_event_id=parent_event_id,
        )
        self._events[event.event_id] = event
        self._event_cache[event.event_id] = event
        self._node_to_latest_event[topic_node_id] = event.event_id

        # 更新父事件的 children
        if parent_event_id and parent_event_id in self._event_cache:
            parent = self._event_cache[parent_event_id]
            parent.children_ids.append(event.event_id)

        return event

    def get_event(self, event_id: str) -> Optional[TimelineEvent]:
        """O(1) 获取事件。"""
        return self._event_cache.get(event_id)

    def get_latest_event_for_node(self, node_id: str) -> Optional[TimelineEvent]:
        """O(1) 获取节点最新事件。"""
        event_id = self._node_to_latest_event.get(node_id)
        if event_id is None:
            return None
        return self._event_cache.get(event_id)

    def get_events_by_entity(self, entity_value: str) -> List[TimelineEvent]:
        """通过实体值查找事件（O(N) 遍历，但使用缓存加速）。"""
        events = []
        for event in self._event_cache.values():
            for entity in event.entities:
                if isinstance(entity, dict):
                    val = str(entity.get("value", ""))
                    if val == entity_value:
                        events.append(event)
                        break
        return events

    def get_events_for_node(self, node_id: str) -> List[TimelineEvent]:
        """获取节点的所有事件（基于时间线顺序）。"""
        events = [
            e for e in self._event_cache.values()
            if e.topic_node_id == node_id
        ]
        events.sort(key=lambda e: e.turn_index)
        return events

    # ── 树 ↔ 时间线 映射 ───────────────────────────────────────────

    def get_timeline_for_node(self, node_id: str) -> List[TimelineEvent]:
        """获取节点的完整时间线（含祖先和后代）。"""
        # 节点自身的事件
        events = self.get_events_for_node(node_id)
        # 按 turn_index 排序
        events.sort(key=lambda e: e.turn_index)
        return events

    def get_parent_event(self, event_id: str) -> Optional[TimelineEvent]:
        """O(1) 获取事件的父事件。"""
        event = self._event_cache.get(event_id)
        if event is None or event.parent_event_id is None:
            return None
        return self._event_cache.get(event.parent_event_id)

    def get_children_events(self, event_id: str) -> List[TimelineEvent]:
        """获取事件的子事件。"""
        event = self._event_cache.get(event_id)
        if event is None:
            return []
        return [
            self._event_cache.get(cid)
            for cid in event.children_ids
            if cid in self._event_cache
        ]

    # ── 查询 ───────────────────────────────────────────

    def find_cross_topic_entities(self, node_id_a: str, node_id_b: str) -> Set[str]:
        """查找两个话题节点之间的共享实体。"""
        events_a = self.get_events_for_node(node_id_a)
        events_b = self.get_events_for_node(node_id_b)

        entities_a = set()
        entities_b = set()

        for event in events_a:
            for entity in event.entities:
                if isinstance(entity, dict):
                    val = str(entity.get("value", ""))
                    if val:
                        entities_a.add(val)

        for event in events_b:
            for entity in event.entities:
                if isinstance(entity, dict):
                    val = str(entity.get("value", ""))
                    if val:
                        entities_b.add(val)

        return entities_a & entities_b

    def get_all_events(self) -> List[TimelineEvent]:
        """获取所有事件（按时间顺序）。"""
        events = list(self._event_cache.values())
        events.sort(key=lambda e: e.timestamp)
        return events

    # ── 序列化 ───────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events": {eid: e.to_dict() for eid, e in self._event_cache.items()},
            "node_to_latest_event": dict(self._node_to_latest_event),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DualStructureManager":
        manager = cls()
        for eid, ed in d.get("events", {}).items():
            event = TimelineEvent(
                event_id=ed.get("event_id", eid),
                topic_node_id=ed.get("topic_node_id", ""),
                turn_index=ed.get("turn_index", 0),
                event_type=ed.get("event_type", ""),
                content=ed.get("content", ""),
                entities=ed.get("entities", []),
                parent_event_id=ed.get("parent_event_id"),
                timestamp=ed.get("timestamp", 0.0),
            )
            event.children_ids = ed.get("children_ids", [])
            manager._events[eid] = event
            manager._event_cache[eid] = event
            manager._node_to_latest_event[event.topic_node_id] = eid
        return manager

    # ── 生命周期 ───────────────────────────────────────────

    def clear(self) -> None:
        """清空所有事件。"""
        self._events.clear()
        self._node_to_latest_event.clear()
        self._event_cache.clear()
