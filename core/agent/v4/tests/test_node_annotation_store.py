"""Tests for NodeAnnotationStore."""
import pytest
from core.agent.v4.node_annotation_store import NodeAnnotationStore, NodeAnnotation


class TestNodeAnnotationStore:
    def test_put_and_get(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        ann = store.get("n1", "dialogue")
        assert ann is not None
        assert ann.data["action"] == "ask"
        assert ann.version == 1

    def test_update_increments_version(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.put("n1", "dialogue", {"action": "request_change"})
        ann = store.get("n1", "dialogue")
        assert ann.version == 2
        assert ann.data["action"] == "request_change"
        assert len(ann.previous_versions) == 1

    def test_mark_stale(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.mark_stale("n1", "dialogue")
        ann = store.get("n1", "dialogue")
        assert ann.stale is True

    def test_get_stale_returns_only_stale(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.put("n2", "dialogue", {"action": "confirm"})
        store.mark_stale("n1", "dialogue")
        stale = store.get_stale("dialogue")
        assert len(stale) == 1
        assert stale[0].node_id == "n1"

    def test_multi_domain_isolation(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.put("n1", "engineering", {"action": "modify"})
        assert store.get("n1", "dialogue").data["action"] == "ask"
        assert store.get("n1", "engineering").data["action"] == "modify"

    def test_history_tracks_previous(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.put("n1", "dialogue", {"action": "request"})
        store.put("n1", "dialogue", {"action": "clarify"})
        ann = store.get("n1", "dialogue")
        assert ann.version == 3
        hist = store.history("n1", "dialogue")
        assert len(hist) == 2

    def test_stats(self):
        store = NodeAnnotationStore()
        store.put("n1", "dialogue", {"action": "ask"})
        store.put("n2", "engineering", {"action": "modify"})
        s = store.stats()
        assert s["total_annotations"] == 2
        assert s["by_domain"]["dialogue"] == 1
