# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_tree/cross_ref.py
────────────────────────────────────────
Cognitive Tree v3.0 — 交叉引用管理器

职责:
  - 维护 Cognitive Tree 与 Topic Tree 之间的双向交叉引用
  - 支持正向查询（Topic → Cognitive）和反向查询（Cognitive → Topic）
  - 管理引用的生命周期（创建、更新、解除、批量清理）
  - 提供一致性校验（孤立引用检测）

设计原则:
  - 引用是单向的：Cognitive Tree 节点生命周期独立于 Topic Tree
  - 使用内存字典维护引用关系，异步批量持久化

对应工程文档: ENGINEERING_TOPIC_TREE.md §9
对应设计文档: DESIGN_MULTILAYER_LLM_COGNITIVE.md §2.3

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeNode,
    CognitiveTreeEdge,
)
from core.agent.topic_tree.models import TopicNode

logger = logging.getLogger(__name__)


@dataclass(frozen=False)
class CrossRefLink:
    """单个交叉引用链接记录"""
    topic_node_id: str
    cognitive_node_id: str
    link_type: str = "automatic"   # "automatic" | "manual" | "inferred"
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_node_id": self.topic_node_id,
            "cognitive_node_id": self.cognitive_node_id,
            "link_type": self.link_type,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CrossRefLink":
        return cls(
            topic_node_id=d.get("topic_node_id", ""),
            cognitive_node_id=d.get("cognitive_node_id", ""),
            link_type=d.get("link_type", "automatic"),
            confidence=d.get("confidence", 1.0),
            created_at=d.get("created_at", time.time()),
            metadata=dict(d.get("metadata", {})),
        )


class CrossRefManager:
    """Topic Tree 与 Cognitive Tree 的交叉引用管理器

    对应工程文档: ENGINEERING_TOPIC_TREE.md §9.1
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id: Optional[str] = session_id

        # 双向引用索引
        # topic_id -> {cognitive_node_id, ...}
        self._topic_to_cog: Dict[str, Set[str]] = {}
        # cognitive_node_id -> {topic_id, ...}
        self._cog_to_topic: Dict[str, Set[str]] = {}

        # 完整链接记录（按 (topic_id, cog_id) 索引）
        self._links: Dict[str, CrossRefLink] = {}

        # 异步锁
        self._lock = asyncio.Lock()

    # ═══════════════════════════════════════════════════════════════════
    # 引用创建与更新
    # ═══════════════════════════════════════════════════════════════════

    async def link(
        self,
        topic_node_id: str,
        cognitive_node_id: str,
        link_type: str = "automatic",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CrossRefLink:
        """创建 Topic Tree 节点与 Cognitive Tree 节点之间的交叉引用

        Args:
            topic_node_id: Topic Tree 节点 ID
            cognitive_node_id: Cognitive Tree 节点 ID
            link_type: 链接类型 (automatic / manual / inferred)
            confidence: 链接置信度 [0, 1]
            metadata: 额外元数据

        Returns:
            创建的 CrossRefLink 实例
        """
        async with self._lock:
            try:
                # 更新双向索引
                self._topic_to_cog.setdefault(topic_node_id, set()).add(cognitive_node_id)
                self._cog_to_topic.setdefault(cognitive_node_id, set()).add(topic_node_id)

                link_key = f"{topic_node_id}:{cognitive_node_id}"
                link = CrossRefLink(
                    topic_node_id=topic_node_id,
                    cognitive_node_id=cognitive_node_id,
                    link_type=link_type,
                    confidence=confidence,
                    metadata=metadata or {},
                )
                self._links[link_key] = link

                logger.debug(
                    "创建交叉引用: %s <-> %s (type=%s)",
                    topic_node_id, cognitive_node_id, link_type
                )
                return link

            except Exception as e:
                logger.error("link 失败: %s", e)
                raise

    async def unlink(
        self,
        topic_node_id: str,
        cognitive_node_id: str,
    ) -> bool:
        """解除 Topic Tree 节点与 Cognitive Tree 节点之间的交叉引用

        Returns:
            True 如果成功解除，False 如果引用不存在
        """
        async with self._lock:
            try:
                link_key = f"{topic_node_id}:{cognitive_node_id}"
                if link_key not in self._links:
                    return False

                del self._links[link_key]

                # 更新双向索引
                self._topic_to_cog.get(topic_node_id, set()).discard(cognitive_node_id)
                self._cog_to_topic.get(cognitive_node_id, set()).discard(topic_node_id)

                # 清理空集合
                if topic_node_id in self._topic_to_cog and not self._topic_to_cog[topic_node_id]:
                    del self._topic_to_cog[topic_node_id]
                if cognitive_node_id in self._cog_to_topic and not self._cog_to_topic[cognitive_node_id]:
                    del self._cog_to_topic[cognitive_node_id]

                logger.debug(
                    "解除交叉引用: %s <-> %s", topic_node_id, cognitive_node_id
                )
                return True

            except Exception as e:
                logger.error("unlink 失败: %s", e)
                raise

    async def remove_all_for_topic(self, topic_node_id: str) -> int:
        """移除某 Topic Tree 节点的所有交叉引用

        Returns:
            移除的引用数量
        """
        async with self._lock:
            cog_ids = list(self._topic_to_cog.get(topic_node_id, set()))
            count = 0
            for cog_id in cog_ids:
                try:
                    link_key = f"{topic_node_id}:{cog_id}"
                    if link_key in self._links:
                        del self._links[link_key]
                        count += 1

                    self._cog_to_topic.get(cog_id, set()).discard(topic_node_id)
                    if cog_id in self._cog_to_topic and not self._cog_to_topic[cog_id]:
                        del self._cog_to_topic[cog_id]
                except Exception as e:
                    logger.warning("移除 topic 引用时出错: %s", e)

            self._topic_to_cog.pop(topic_node_id, None)
            logger.debug("移除 Topic 节点 %s 的 %d 条引用", topic_node_id, count)
            return count

    async def remove_all_for_cognitive(self, cognitive_node_id: str) -> int:
        """移除某 Cognitive Tree 节点的所有交叉引用

        Returns:
            移除的引用数量
        """
        async with self._lock:
            topic_ids = list(self._cog_to_topic.get(cognitive_node_id, set()))
            count = 0
            for topic_id in topic_ids:
                try:
                    link_key = f"{topic_id}:{cognitive_node_id}"
                    if link_key in self._links:
                        del self._links[link_key]
                        count += 1

                    self._topic_to_cog.get(topic_id, set()).discard(cognitive_node_id)
                    if topic_id in self._topic_to_cog and not self._topic_to_cog[topic_id]:
                        del self._topic_to_cog[topic_id]
                except Exception as e:
                    logger.warning("移除 cognitive 引用时出错: %s", e)

            self._cog_to_topic.pop(cognitive_node_id, None)
            logger.debug("移除 Cognitive 节点 %s 的 %d 条引用", cognitive_node_id, count)
            return count

    # ═══════════════════════════════════════════════════════════════════
    # 查询 API
    # ═══════════════════════════════════════════════════════════════════

    def get_cognitive_ids_for_topic(self, topic_node_id: str) -> List[str]:
        """获取与某 Topic 节点关联的所有 Cognitive 节点 ID"""
        return list(self._topic_to_cog.get(topic_node_id, set()))

    def get_topic_ids_for_cognitive(self, cognitive_node_id: str) -> List[str]:
        """获取与某 Cognitive 节点关联的所有 Topic 节点 ID"""
        return list(self._cog_to_topic.get(cognitive_node_id, set()))

    def get_links_for_topic(self, topic_node_id: str) -> List[CrossRefLink]:
        """获取某 Topic 节点的所有交叉引用详情"""
        cog_ids = self._topic_to_cog.get(topic_node_id, set())
        links: List[CrossRefLink] = []
        for cog_id in cog_ids:
            link_key = f"{topic_node_id}:{cog_id}"
            if link_key in self._links:
                links.append(self._links[link_key])
        return links

    def get_links_for_cognitive(self, cognitive_node_id: str) -> List[CrossRefLink]:
        """获取某 Cognitive 节点的所有交叉引用详情"""
        topic_ids = self._cog_to_topic.get(cognitive_node_id, set())
        links: List[CrossRefLink] = []
        for topic_id in topic_ids:
            link_key = f"{topic_id}:{cognitive_node_id}"
            if link_key in self._links:
                links.append(self._links[link_key])
        return links

    def get_link_detail(
        self,
        topic_node_id: str,
        cognitive_node_id: str,
    ) -> Optional[CrossRefLink]:
        """获取单个交叉引用的详情"""
        link_key = f"{topic_node_id}:{cognitive_node_id}"
        return self._links.get(link_key)

    # ═══════════════════════════════════════════════════════════════════
    # 一致性校验
    # ═══════════════════════════════════════════════════════════════════

    def validate_consistency(
        self,
        existing_topic_ids: Optional[Set[str]] = None,
        existing_cognitive_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """校验交叉引用一致性，检测孤立引用

        Args:
            existing_topic_ids: 当前系统中存在的 Topic 节点 ID 集合
            existing_cognitive_ids: 当前系统中存在的 Cognitive 节点 ID 集合

        Returns:
            校验报告字典
        """
        orphan_topic: List[str] = []
        orphan_cog: List[str] = []
        broken_links: List[str] = []

        for link_key, link in self._links.items():
            if existing_topic_ids is not None and link.topic_node_id not in existing_topic_ids:
                orphan_topic.append(link.topic_node_id)
                broken_links.append(link_key)
            if existing_cognitive_ids is not None and link.cognitive_node_id not in existing_cognitive_ids:
                orphan_cog.append(link.cognitive_node_id)
                broken_links.append(link_key)

        report = {
            "total_links": len(self._links),
            "broken_links": len(set(broken_links)),
            "orphan_topic_ids": list(set(orphan_topic)),
            "orphan_cognitive_ids": list(set(orphan_cog)),
            "is_consistent": len(broken_links) == 0,
        }
        return report

    async def prune_orphans(
        self,
        existing_topic_ids: Optional[Set[str]] = None,
        existing_cognitive_ids: Optional[Set[str]] = None,
    ) -> int:
        """清理孤立引用

        Returns:
            清理的引用数量
        """
        async with self._lock:
            to_remove: List[str] = []
            for link_key, link in self._links.items():
                if existing_topic_ids is not None and link.topic_node_id not in existing_topic_ids:
                    to_remove.append(link_key)
                elif existing_cognitive_ids is not None and link.cognitive_node_id not in existing_cognitive_ids:
                    to_remove.append(link_key)

            for link_key in to_remove:
                try:
                    link = self._links.pop(link_key)
                    self._topic_to_cog.get(link.topic_node_id, set()).discard(link.cognitive_node_id)
                    self._cog_to_topic.get(link.cognitive_node_id, set()).discard(link.topic_node_id)
                except Exception as e:
                    logger.warning("清理孤立引用时出错: %s", e)

            # 清理空索引
            for key in list(self._topic_to_cog.keys()):
                if not self._topic_to_cog[key]:
                    del self._topic_to_cog[key]
            for key in list(self._cog_to_topic.keys()):
                if not self._cog_to_topic[key]:
                    del self._cog_to_topic[key]

            logger.info("清理 %d 条孤立引用", len(to_remove))
            return len(to_remove)

    # ═══════════════════════════════════════════════════════════════════
    # 序列化
    # ═══════════════════════════════════════════════════════════════════

    def to_dict(self) -> Dict[str, Any]:
        """序列化交叉引用状态"""
        return {
            "session_id": self.session_id,
            "links": [link.to_dict() for link in self._links.values()],
            "__version__": "3.0",
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CrossRefManager":
        """从字典反序列化"""
        try:
            manager = cls(session_id=d.get("session_id"))
            for link_dict in d.get("links", []):
                try:
                    link = CrossRefLink.from_dict(link_dict)
                    link_key = f"{link.topic_node_id}:{link.cognitive_node_id}"
                    manager._links[link_key] = link
                    manager._topic_to_cog.setdefault(link.topic_node_id, set()).add(link.cognitive_node_id)
                    manager._cog_to_topic.setdefault(link.cognitive_node_id, set()).add(link.topic_node_id)
                except Exception as e:
                    logger.warning("CrossRefLink 反序列化失败: %s", e)
            return manager
        except Exception as e:
            logger.error("CrossRefManager.from_dict 失败: %s", e)
            raise

    def __repr__(self) -> str:
        return (
            f"CrossRefManager(session={self.session_id!r}, "
            f"links={len(self._links)})"
        )
