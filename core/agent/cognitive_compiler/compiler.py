"""Cognitive Compiler — v3.0 ENGINEERING_COGNITIVE_COMPILER §5.

Single entry point for writing to the Cognitive Tree.
Compiles 6 LLM instance outputs into CognitiveTreeNode nodes.
Manages lifecycle, edges, access control, and event notification.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class CompileInput:

    """Input from one LLM instance."""
    llm_instance: str          # "pcr"/"intent"/"meta"/"planning"/"answer"/"reflective"
    content: str
    node_type: str             # PERCEPTION/HYPOTHESIS/REASONING/DECISION/ACTION/...
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    action: Optional[str] = None
    action_result: Optional[str] = None
    cross_refs: List[str] = field(default_factory=list)  # node_ids


@dataclass
class CompileResult:
    """Result of one compile cycle."""
    nodes_created: int = 0
    edges_created: int = 0
    nodes_archived: int = 0
    events_emitted: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

CompiledInput = CompileInput  # backward compat alias


class CognitiveCompiler:
    """ENGINEERING_COGNITIVE_COMPILER §5 — bridges 6 LLMs → CognitiveTree.

    Principle: Cognitive Tree is the shared mental space of all LLMs.
    The compiler is the ONLY entry point for information entering that space.
    """

    MAX_NODES = 1000
    DEFAULT_DEPTH_LIMIT = 20

    def __init__(self, tree_store=None, access_control=None,
                 event_bus=None, lifecycle_manager=None, edge_manager=None):
        self._store = tree_store
        self._access = access_control
        self._bus = event_bus
        self._lifecycle = lifecycle_manager
        self._edges = edge_manager

        # Lazy-load from v3_0 if not provided
        if self._store is None:
            self._store = self._make_tree_store()
        if self._access is None:
            self._access = self._make_access_control()
        if self._bus is None:
            self._bus = self._make_event_bus()

    def compile(self, inputs: List[CompileInput], session_id: str = "default") -> CompileResult:
        """Process multiple LLM outputs into Cognitive Tree nodes.

        Flow: validate → create nodes → create edges → notify → archive stale.
        """
        t0 = time.time()
        result = CompileResult()

        if not self._store:
            return result

        for inp in inputs:
            # 1. Access control: can this LLM write?
            if self._access:
                try:
                    from core.agent.v3_0.cognitive_tree.models import CogType
                    cog_type = (CogType[inp.node_type]
                                if inp.node_type in CogType.__members__
                                else None)
                    perms = getattr(self._access, "permissions", {})
                    # 未配置权限矩阵的 LLM = 内部白盒系统 LLM → 默认允许 (M3)
                    check = getattr(self._access, "can_write", None) or \
                            getattr(self._access, "check_create", None)
                    if check is not None and perms:
                        if inp.llm_instance not in perms:
                            logger.debug("LLM %s 未配置权限矩阵 → 内部白盒允许",
                                         inp.llm_instance)
                        elif cog_type is not None and not check(inp.llm_instance, cog_type):
                            logger.debug("Access denied: %s→%s",
                                         inp.llm_instance, inp.node_type)
                            continue
                except Exception:
                    pass  # 权限检查失败不阻塞写入（懒初始化上下文）

            # 2. Create node
            node = self._create_node(inp, session_id)
            if node:
                self._store.add_node(node)
                result.nodes_created += 1

                # 3. Create edges (cross-reference connections)
                for ref_id in inp.cross_refs:
                    if self._store.get_node(ref_id):
                        from core.agent.v3_0.cognitive_tree.models import (
                            CognitiveTreeEdge, CogEdgeType,
                        )
                        edge = CognitiveTreeEdge(
                            edge_id=f"{node.node_id}_{ref_id}_CROSS_REF",
                            source_id=node.node_id, target_id=ref_id,
                            edge_type=CogEdgeType.CROSS_REF,
                        )
                        self._store.add_edge(edge)
                        result.edges_created += 1

                # 4. Notify
                if self._bus:
                    try:
                        from core.agent.v3_0.cognitive_compiler.event_bus import Event
                        self._bus.publish(Event(
                            type="NODE_CREATED",
                            data={
                                "node_id": node.node_id,
                                "type": inp.node_type,
                                "source_llm": inp.llm_instance,
                                "confidence": inp.confidence,
                            },
                        ))
                        result.events_emitted.append("NODE_CREATED")
                    except Exception:
                        pass  # 事件通知失败不阻塞写树

            # 5. Lifecycle: archive nodes past depth limit
            if self._lifecycle:
                archived = self._lifecycle.prune_beyond_depth(self.DEFAULT_DEPTH_LIMIT)
                result.nodes_archived += archived

        result.latency_ms = (time.time() - t0) * 1000
        return result

    def _create_node(self, inp: CompileInput, session_id: str):
        """Create CognitiveTreeNode from LLM output."""
        try:
            from core.agent.v3_0.cognitive_tree.models import (
                CognitiveTreeNode, CogNodeStatus, CogType,
            )
            node_id = f"{session_id}_{inp.llm_instance}_{int(time.time()*1000)}"
            cog_type = (CogType[inp.node_type]
                        if inp.node_type in CogType.__members__
                        else CogType.REASONING)
            return CognitiveTreeNode(
                node_id=node_id,
                cog_type=cog_type,
                source_llm=inp.llm_instance,
                timestamp=time.time(),
                content=inp.content,
                confidence=inp.confidence,
                evidence=inp.evidence,
                action=inp.action,
                action_result=inp.action_result,
                status=CogNodeStatus.ACTIVE,
            )
        except Exception as e:
            logger.debug("Node creation failed: %s", e)
            return None

    def get_tree_stats(self) -> dict:
        if self._store:
            return self._store.stats() if hasattr(self._store, 'stats') else {}
        return {}

    # ═══ Factory methods ═══

    @staticmethod
    def _make_tree_store():
        try:
            # v3_0 思考树（manager.py）为唯一共享心智空间（LLM-1/B1-8 定案）。
            # 注意: 旧默认 CognitiveTreeStore 的 API 是 save_node/load_node,
            # 与 compiler 的 add_node/get_node 调用不匹配 — 已修正。
            from core.agent.v3_0.cognitive_tree.manager import CognitiveTree
            return CognitiveTree(session_id="default")
        except Exception:
            return None

    @staticmethod
    def _make_access_control():
        try:
            from core.agent.v3_0.cognitive_tree.models import AccessControlMatrix
            return AccessControlMatrix()
        except Exception:
            return None

    @staticmethod
    def _make_event_bus():
        # v3_0 cognitive EventBus 是 async 实现 — 在 v6 同步引擎路径
        # (engine._init_cognitive_runtime) 下无运行中 event loop,
        # start() 会创建未 await 的 coroutine (RuntimeWarning)。
        # 写树 (CognitiveCompiler.compile) 不依赖事件通知 → 直接 None。
        # 事件通知接线归 G2 (EventBus 生命周期) 施工, 与主总线统一。
        return None
