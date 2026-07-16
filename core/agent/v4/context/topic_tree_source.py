"""TopicTreeContextSource: discourse tree context with backtracking support.

Wraps TopicTreeManager as a ContextAssembler source.
Provides hierarchical conversation context:
  - Current topic and its ancestors (upward pointers — macro view)
  - Sibling topics (breadth)
  - Topic routing decisions (fork/attach/continue)

This is how the discourse tree integrates into v4's Context IR.
Replaces the flat ConversationTracker history injection with
hierarchical topic tree traversal.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from core.agent.v4.context.source import ContextSource, ContextItem

logger = logging.getLogger(__name__)


class TopicTreeContextSource(ContextSource):
    """Conversation context from the discourse topic tree.

    Name="topic_tree" — injected into ContextAssembler as an additional source.
    DomainSelector's C domain will prefer this over flat ObservationSource
    when topic context is available.

    Backtracking support: when LLM is stuck in detail, this source can
    inject ancestor topics (macro view) by walking up the tree via
    _get_path_to_root(). This is the "root node reshaping" the design
    calls for — discourse tree pointers provide natural hierarchy.
    """

    def __init__(self, topic_tree=None, discourse_manager=None):
        self._topic_tree = topic_tree        # TopicTreeManager instance
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
        """Extract context from TopicTreeManager."""
        tm = self._topic_tree
        items = []

        # Current topic
        current_id = tm.current_topic_id if hasattr(tm, 'current_topic_id') else None
        if not current_id and hasattr(tm, 'tree') and tm.tree:
            current_id = tm.current_topic_id if hasattr(tm, 'current_topic_id') else None

        if current_id and hasattr(tm, 'tree') and hasattr(tm.tree, 'nodes'):
            node = tm.tree.nodes.get(current_id)
            if node:
                items.append(ContextItem(
                    source=self.name,
                    content=node,
                    text=f"[Current Topic] {getattr(node, 'title', str(node))}",
                    relevance=0.95,
                    metadata={"type": "current_topic", "node_id": current_id},
                ))

        # Macro expansion: walk up to ancestors
        if expand_macro and current_id:
            try:
                ancestors = tm._get_ancestors(current_id, depth=3)
                for i, ancestor in enumerate(ancestors):
                    items.append(ContextItem(
                        source=self.name,
                        content=ancestor,
                        text=f"[Ancestor L{i+1}] {getattr(ancestor, 'title', str(ancestor))}",
                        relevance=0.85 - i * 0.1,
                        metadata={"type": "ancestor", "depth": i+1},
                    ))
            except Exception:
                pass

            # Path to root for full backtracking
            try:
                path = tm._get_path_to_root(current_id)
                if len(path) > 2:
                    items.append(ContextItem(
                        source=self.name,
                        content=path,
                        text="Topic path: " + " → ".join(
                            getattr(n, 'title', str(n)) for n in path
                        ),
                        relevance=0.80,
                        metadata={"type": "topic_path", "length": len(path)},
                    ))
            except Exception:
                pass

        # Descendants for breadth
        if current_id:
            try:
                children = tm._get_descendants(current_id, depth=1)
                for child in children[:3]:
                    items.append(ContextItem(
                        source=self.name,
                        content=child,
                        text=f"[Sub-topic] {getattr(child, 'title', str(child))}",
                        relevance=0.6,
                        metadata={"type": "sub_topic"},
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
