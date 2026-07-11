"""Tests for DialogueTreePersistenceAdapter."""
import pytest
from core.agent.v4.node_annotation_store import NodeAnnotationStore
from core.agent.v4.dialogue_tree_persistence_adapter import (
    DialogueTreePersistenceAdapter, LoadResult,
)


class MockStore:
    def __init__(self):
        self._nodes = {}
    def put_node(self, node):
        self._nodes[node["id"]] = node
    def load_node(self, node_id):
        return self._nodes.get(node_id)
    def get_by_conversation(self, conv_id):
        return list(self._nodes.values())


class TestDialogueTreePersistenceAdapter:
    def test_persist_node_with_annotation(self):
        store = MockStore()
        annotation_store = NodeAnnotationStore()
        adapter = DialogueTreePersistenceAdapter(store=store, annotation_store=annotation_store)

        tree_node = {"node_id": "N1", "summary": "User asks about monitoring", "parent_id": ""}
        gid = adapter.persist_node(tree_node)
        assert gid.startswith("g_")
        stored = store.load_node(gid)
        assert stored is not None
        assert stored["data"]["summary"] == "User asks about monitoring"
        ann = annotation_store.get("N1", "dialogue")
        assert ann is not None

    def test_persist_node_with_resolver(self):
        from core.agent.v4.tiered_action_resolver import TieredActionResolver, DomainAdapter
        resolver = TieredActionResolver()
        adapter_d = DomainAdapter(
            domain="dialogue",
            rules={"ask": ["how", "what"], "request_change": ["change", "update"]},
        )
        resolver.register_domain(adapter_d)

        store = MockStore()
        annotation_store = NodeAnnotationStore()
        adapter = DialogueTreePersistenceAdapter(
            store=store, resolver=resolver, annotation_store=annotation_store,
        )

        tree_node = {"node_id": "N2", "summary": "how do I add monitoring?"}
        gid = adapter.persist_node(tree_node)
        stored = store.load_node(gid)
        assert stored["data"]["action"] == "ask"
        assert stored["data"]["action_source"] == "rule"

    def test_persist_tree(self):
        store = MockStore()
        adapter = DialogueTreePersistenceAdapter(store=store)
        root = {"node_id": "R", "summary": "root", "children": [
            {"node_id": "C1", "summary": "child1", "children": []},
            {"node_id": "C2", "summary": "child2", "children": []},
        ]}
        ids = adapter.persist_tree(root)
        assert len(ids) == 3

    def test_load_node(self):
        store = MockStore()
        adapter = DialogueTreePersistenceAdapter(store=store)
        tree_node = {"node_id": "N3", "summary": "test"}
        gid = adapter.persist_node(tree_node)
        result = adapter.load_node(gid)
        assert result is not None
        assert len(result.nodes) == 1
        assert "N3" in result.annotations

    def test_validate_adjacent_action_shift(self):
        adapter = DialogueTreePersistenceAdapter(store=MockStore())
        a = {"node_id": "A", "summary": "how to deploy"}
        b = {"node_id": "B", "summary": "change config"}
        adapter._annotations.put("A", "dialogue", {"action": "ask"})
        adapter._annotations.put("B", "dialogue", {"action": "request_change"})
        edges = adapter.validate_adjacent(a, b)
        assert len(edges) >= 1
        shift = [e for e in edges if e["type"] == "action_shift"]
        assert len(shift) >= 1

    def test_validate_adjacent_merge_hint(self):
        adapter = DialogueTreePersistenceAdapter(store=MockStore())
        a = {"node_id": "A", "summary": "add monitoring to gateway"}
        b = {"node_id": "B", "summary": "add monitoring to the gateway"}
        adapter._annotations.put("A", "dialogue", {"action": "add"})
        adapter._annotations.put("B", "dialogue", {"action": "add"})
        edges = adapter.validate_adjacent(a, b)
        merge = [e for e in edges if e["type"] == "merged_from"]
        assert len(merge) >= 1
