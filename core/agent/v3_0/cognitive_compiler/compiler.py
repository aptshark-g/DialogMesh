# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/compiler.py
────────────────────────────────────────────────
认知编译器主类。

6 个 LLM 实例的推理结果进入 Cognitive Tree 的唯一入口。
提供 compile() 和 compile_batch() 方法，统一处理权限检查、
节点创建、边关系建立与事件通知。

对应工程文档: ENGINEERING_COGNITIVE_COMPILER.md §5
版本: 3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.v3_0.cognitive_tree.manager import CognitiveTree
from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeEdge,
    CognitiveTreeNode,
    CogEdgeType,
    CogType,
)
from core.agent.v3_0.cognitive_compiler.event_bus import Event, CogEventType

logger = logging.getLogger(__name__)


class CognitiveTreeStore:
    """
    多会话 Cognitive Tree 存储管理器。

    内部维护 session_id → CognitiveTree 的映射，
    为认知编译器提供统一的多会话存储接口。
    """

    def __init__(self) -> None:
        self._trees: Dict[str, CognitiveTree] = {}

    def _get_tree(self, session_id: str) -> CognitiveTree:
        """获取或创建指定会话的认知树。"""
        if session_id not in self._trees:
            self._trees[session_id] = CognitiveTree(session_id=session_id)
        return self._trees[session_id]

    def save_node(
        self, session_id: str, node: CognitiveTreeNode, requesting_llm: str = ""
    ) -> None:
        """保存节点到指定会话。"""
        try:
            tree = self._get_tree(session_id)
            tree.add_node(
                node, check_permission=True, requester_llm=requesting_llm
            )
        except Exception as e:
            logger.error("save_node failed: %s", e)
            raise

    def load_node(self, session_id: str, node_id: str) -> Optional[CognitiveTreeNode]:
        """按 ID 加载节点。"""
        try:
            tree = self._get_tree(session_id)
            return tree.get_node(node_id)
        except Exception as e:
            logger.error("load_node failed: %s", e)
            return None

    def load_nodes(self, session_id: str) -> List[CognitiveTreeNode]:
        """加载会话中所有节点。"""
        try:
            tree = self._get_tree(session_id)
            return list(tree.nodes.values())
        except Exception as e:
            logger.error("load_nodes failed: %s", e)
            return []

    def update_node(
        self,
        session_id: str,
        node_id: str,
        updates: Dict[str, Any],
        requesting_llm: str = "",
    ) -> bool:
        """更新节点字段。"""
        try:
            tree = self._get_tree(session_id)
            return tree.update_node(node_id, requesting_llm, **updates)
        except Exception as e:
            logger.error("update_node failed: %s", e)
            return False

    def save_edge(self, session_id: str, edge: CognitiveTreeEdge) -> None:
        """保存边到指定会话。"""
        try:
            tree = self._get_tree(session_id)
            tree.add_edge(edge, check_nodes_exist=True)
        except Exception as e:
            logger.error("save_edge failed: %s", e)
            raise

    def add_edge(self, session_id: str, edge: CognitiveTreeEdge) -> None:
        """添加边（不校验节点存在性）。"""
        try:
            tree = self._get_tree(session_id)
            tree.add_edge(edge, check_nodes_exist=False)
        except Exception as e:
            logger.error("add_edge failed: %s", e)
            raise

    def load_edges(self, session_id: str) -> List[CognitiveTreeEdge]:
        """加载会话中所有边。"""
        try:
            tree = self._get_tree(session_id)
            return list(tree.edges)
        except Exception as e:
            logger.error("load_edges failed: %s", e)
            return []

    def load_edges_from(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """加载从某节点出发的所有边。"""
        try:
            tree = self._get_tree(session_id)
            return tree.get_outgoing(node_id)
        except Exception as e:
            logger.error("load_edges_from failed: %s", e)
            return []

    def load_edges_to(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """加载指向某节点的所有边。"""
        try:
            tree = self._get_tree(session_id)
            return tree.get_incoming(node_id)
        except Exception as e:
            logger.error("load_edges_to failed: %s", e)
            return []

    def get_tree(self, session_id: str) -> Optional[CognitiveTree]:
        """直接获取底层 CognitiveTree 实例（用于高级操作）。"""
        return self._trees.get(session_id)

    def list_sessions(self) -> List[str]:
        """返回所有已注册的会话 ID。"""
        return list(self._trees.keys())

    def remove_session(self, session_id: str) -> bool:
        """移除会话及其所有数据。"""
        try:
            if session_id in self._trees:
                del self._trees[session_id]
                return True
            return False
        except Exception as e:
            logger.error("remove_session failed: %s", e)
            return False


class CognitiveCompiler:
    """
    认知编译器 — 6 个 LLM 实例的推理结果进入 Cognitive Tree 的唯一入口。

    编译流程:
      1. 权限检查: llm_name 是否可以创建 cog_type 类型的节点？
      2. 创建节点
      3. 如果有 parent_node_id，创建边关系
      4. 触发事件 (NODE_CREATED)
      5. 返回节点
    """

    def __init__(
        self,
        cognitive_tree_store: CognitiveTreeStore,
        access_control: Any,
        event_bus: Any,
        lifecycle_manager: Any,
        edge_manager: Any,
    ) -> None:
        """
        Args:
            cognitive_tree_store: 多会话存储管理器
            access_control: 访问控制矩阵
            event_bus: 异步事件总线
            lifecycle_manager: 节点生命周期管理器
            edge_manager: 边关系管理器
        """
        self._store = cognitive_tree_store
        self._access = access_control
        self._event_bus = event_bus
        self._lifecycle = lifecycle_manager
        self._edge_mgr = edge_manager

    def compile(
        self,
        session_id: str,
        llm_name: str,
        cog_type: CogType,
        content: str,
        confidence: float = 0.5,
        evidence: Optional[List[str]] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        parent_node_id: Optional[str] = None,
        edge_type: CogEdgeType = CogEdgeType.DERIVES,
    ) -> Optional[CognitiveTreeNode]:
        """
        将 LLM 推理结果编译为 Cognitive Tree 节点。

        这是 6 个 LLM 实例将信息写入 Cognitive Tree 的唯一入口。

        Args:
            session_id: 会话标识
            llm_name: LLM 实例名称（如 "Planning-LLM"）
            cog_type: 认知节点类型
            content: 认知内容
            confidence: 置信度 [0, 1]
            evidence: 证据引用列表
            action: 产生的行动描述
            action_result: 行动结果
            parent_node_id: 父节点 ID（可选）
            edge_type: 与父节点的边类型

        Returns:
            创建的认知节点，或 None（权限不足时抛出异常）

        Raises:
            PermissionError: LLM 无权限创建该类型节点
        """
        try:
            if not self._access.check_create(llm_name, cog_type):
                allowed = self._access.get_allowed_types(llm_name)
                raise PermissionError(
                    f"LLM '{llm_name}' cannot create {cog_type.value} nodes. "
                    f"Allowed types: {allowed}"
                )

            node = CognitiveTreeNode(
                cog_type=cog_type,
                source_llm=llm_name,
                content=content,
                confidence=confidence,
                evidence=evidence or [],
                action=action,
                action_result=action_result,
            )

            self._store.save_node(session_id, node, requesting_llm=llm_name)

            if parent_node_id:
                self._edge_mgr.create_edge(
                    session_id=session_id,
                    source_id=parent_node_id,
                    target_id=node.node_id,
                    edge_type=edge_type,
                    requesting_llm=llm_name,
                )

            self._event_bus.publish(
                Event(
                    type=CogEventType.NODE_CREATED,
                    data={
                        "session_id": session_id,
                        "node_id": node.node_id,
                        "cog_type": cog_type.value,
                        "source_llm": llm_name,
                        "confidence": confidence,
                    },
                )
            )

            logger.debug(
                "Compiled node %s (type=%s, llm=%s)",
                node.node_id, cog_type.value, llm_name,
            )
            return node
        except PermissionError:
            raise
        except Exception as e:
            logger.error(
                "compile failed for session %s, llm %s: %s",
                session_id, llm_name, e,
            )
            raise

    def compile_batch(
        self,
        session_id: str,
        llm_name: str,
        nodes_data: List[Dict[str, Any]],
    ) -> List[CognitiveTreeNode]:
        """
        批量编译节点（用于 Reflective-LLM 的批量复盘）。

        对列表中的每个节点数据调用 compile()，
        权限不足的节点被跳过，不中断整体流程。

        Args:
            session_id: 会话标识
            llm_name: LLM 实例名称
            nodes_data: 节点参数字典列表，每个字典包含 compile() 的可选参数

        Returns:
            成功创建的节点列表
        """
        results: List[CognitiveTreeNode] = []
        for data in nodes_data:
            try:
                node = self.compile(
                    session_id=session_id,
                    llm_name=llm_name,
                    cog_type=data["cog_type"],
                    content=data["content"],
                    confidence=data.get("confidence", 0.5),
                    evidence=data.get("evidence"),
                    action=data.get("action"),
                    parent_node_id=data.get("parent_node_id"),
                    edge_type=data.get("edge_type", CogEdgeType.DERIVES),
                )
                if node:
                    results.append(node)
            except PermissionError:
                logger.debug(
                    "compile_batch: skipped node for %s (permission denied)",
                    llm_name,
                )
                continue
            except Exception as e:
                logger.error("compile_batch item failed: %s", e)
                continue
        return results
