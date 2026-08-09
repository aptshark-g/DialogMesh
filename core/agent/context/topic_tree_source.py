"""TopicTreeContextSource: topic tree context with backtracking support.

Wraps TopicTreeManagerV2（唯一内核，T4 归一）as a ContextAssembler source.
Provides hierarchical conversation context:
  - Current topic and its ancestors (upward pointers — macro view)
  - Active path from root to current (backtracking)
  - Sub-topics (breadth)

T2/T4 修复（2026-08-05）: 原实现调用 V1 不存在的 API（current_topic_id / tree.nodes
/ _get_ancestors），从未产生上下文；现改为 V2 公开 API（get_current_node /
get_active_path / get_node）。
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from core.agent.context.source import ContextSource, ContextItem

logger = logging.getLogger(__name__)


class TopicTreeContextSource(ContextSource):
    """Conversation context from the topic tree (V2 内核).

    Name="topic_tree" — injected into ContextAssembler as an additional source.
    DomainSelector's C domain will prefer this over flat ObservationSource
    when topic context is available.

    Backtracking support: when LLM is stuck in detail, this source can
    inject ancestor topics (macro view) by walking up the tree via
    _get_path_to_root(). This is the "root node reshaping" the design
    calls for — discourse tree pointers provide natural hierarchy.
    """

    def __init__(self, topic_tree=None, discourse_manager=None):
        self._topic_tree = topic_tree        # TopicTreeManagerV2 instance
        self._discourse = discourse_manager  # DiscourseBlockTreeManager instance

    @property
    def name(self) -> str:
        return "topic_tree"

    def retrieve(self, query: str, top_k: int = 5,
                 expand_macro: bool = False, **kwargs) -> List[ContextItem]:
        """Retrieve conversation context from the discourse tree.

        If expand_macro=True, walks up to ancestors for macro-level context.
        Returns:
            - Current topic block
            - Direct ancestors (parent → grandparent → root)
            - Active child topics (breadth)
        """
        items: List[ContextItem] = []

        if self._topic_tree is not None:
            items.extend(self._from_topic_tree(query, top_k, expand_macro))

        if self._discourse is not None:
            items.extend(self._from_discourse_blocks(query, top_k))

        return items

    def _from_topic_tree(self, query: str, top_k: int,
                         expand_macro: bool) -> List[ContextItem]:
        """Extract context from TopicTreeManagerV2（V2 公开 API）。"""
        tm = self._topic_tree
        if tm is None:
            return []
        items = []

        # Current topic
        current = tm.get_current_node()
        if current is None:
            return items
        items.append(ContextItem(
            source=self.name,
            content=current.to_dict() if hasattr(current, "to_dict") else current,
            text=f"[Current Topic] {getattr(current, 'name', '') or current.id}",
            relevance=0.95,
            metadata={
                "type": "current_topic",
                "node_id": current.id,
                "intent": getattr(current, "intent_category", ""),
                "depth": getattr(current, "depth", 0),
            },
        ))

        # Active path (root → current) for backtracking
        if expand_macro:
            try:
                path = tm.get_active_path()
                if len(path) > 1:
                    items.append(ContextItem(
                        source=self.name,
                        content=[n.to_dict() if hasattr(n, "to_dict") else str(n) for n in path],
                        text="Topic path: " + " → ".join(
                            getattr(n, "name", "") or n.id for n in path
                        ),
                        relevance=0.80,
                        metadata={"type": "topic_path", "length": len(path)},
                    ))
            except Exception:
                pass

        # Sub-topics for breadth
        try:
            children = [tm.get_node(cid) for cid in getattr(current, "children_ids", [])]
            children = [c for c in children if c is not None][:3]
            for child in children:
                items.append(ContextItem(
                    source=self.name,
                    content=child.to_dict() if hasattr(child, "to_dict") else child,
                    text=f"[Sub-topic] {getattr(child, 'name', '') or child.id}",
                    relevance=0.6,
                    metadata={"type": "sub_topic", "node_id": child.id},
                ))
        except Exception:
            pass

        return items

    def _from_discourse_blocks(self, query: str, top_k: int) -> List[ContextItem]:
        """Extract context from DiscourseBlockTreeManager blocks."""
        dm = self._discourse
        items = []

        if not dm.blocks:
            return items

        # Most recent blocks
        recent = sorted(
            dm.blocks.values(),
            key=lambda b: getattr(b, 'last_active_turn', 0),
            reverse=True,
        )[:top_k]

        for block in recent:
            text = getattr(block, 'summary', '') or getattr(block, 'raw_text', '') or str(block)
            parent = dm.blocks.get(getattr(block, 'parent_id', ''))
            parent_text = f" (↑ {getattr(parent, 'summary', '')[:50]})" if parent else ""

            items.append(ContextItem(
                source=self.name,
                content=block,
                text=f"[Block T{getattr(block, 'created_at_turn', '?')}] {text[:200]}{parent_text}",
                relevance=0.7,
                metadata={
                    "type": "discourse_block",
                    "block_id": getattr(block, 'block_id', ''),
                    "parent_id": getattr(block, 'parent_id', ''),
                    "turn": getattr(block, 'created_at_turn', 0),
                    "cohesion": getattr(block, 'cohesion_boundary', 0),
                },
            ))

        return items

    def feed_turn(self, turn_index: int, text: str) -> None:
        """Feed a conversation turn into the discourse tree compiler."""
        if self._discourse is not None:
            try:
                self._discourse.ingest_turn(turn_index, text)
            except Exception as e:
                logger.warning("DiscourseBlockTree feed failed: %s", e)

    def has_context(self) -> bool:
        """Check if any discourse/topic context exists."""
        if self._discourse and self._discourse.blocks:
            return True
        if self._topic_tree:
            return True
        return False
