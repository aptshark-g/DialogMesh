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
            if self._access and not self._access.can_write(inp.llm_instance, inp.node_type):
                logger.debug("Access denied: %s→%s", inp.llm_instance, inp.node_type)
                continue

            # 2. Create node
            node = self._create_node(inp, session_id)
            if node:
                self._store.add_node(node)
                result.nodes_created += 1

                # 3. Create edges (cross-reference connections)
                for ref_id in inp.cross_refs:
                    if self._store.get_node(ref_id):
                        edge_id = f"{node.node_id}_{ref_id}_CROSS_REF"
                        self._store.add_edge(edge_id, node.node_id, ref_id, "CROSS_REF")
                        result.edges_created += 1

                # 4. Notify
                if self._bus:
                    self._bus.publish("NODE_CREATED", {
                        "node_id": node.node_id,
                        "type": inp.node_type,
                        "source_llm": inp.llm_instance,
                        "confidence": inp.confidence,
                    })
                    result.events_emitted.append("NODE_CREATED")

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
                CognitiveTreeNode, CogNodeStatus, CogNodeType
            )
            node_id = f"{session_id}_{inp.llm_instance}_{int(time.time()*1000)}"
            return CognitiveTreeNode(
                node_id=node_id,
                cog_type=CogNodeType.PERCEPTION,  # default, can be refined
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
            from core.agent.v3_0.cognitive_compiler.compiler import CognitiveTreeStore
            return CognitiveTreeStore()
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
        try:
            from core.agent.v3_0.cognitive_compiler.event_bus import EventBus
            bus = EventBus()
            bus.start()
            return bus
        except Exception:
            return None
