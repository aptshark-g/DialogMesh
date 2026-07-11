"""Tests for TieredActionResolver."""
import pytest
from core.agent.v4.tiered_action_resolver import (
    ActionCandidate, EmbeddingIndex, DomainAdapter, TieredActionResolver,
)


class MockLLM:
    def __call__(self, prompt):
        import json
        return json.dumps({"action": "deploy", "confidence": 0.9, "is_new_action": False})


class TestEmbeddingIndex:
    def test_add_and_get(self):
        idx = EmbeddingIndex(dim=4)
        idx.add("test", [0.1, 0.2, 0.3, 0.4])
        assert idx.size() == 1
        emb = idx.get_embedding("test")
        assert emb is not None
        assert len(emb) == 4

    def test_nearest_returns_best_match(self):
        idx = EmbeddingIndex(dim=4)
        idx.add("deploy", [0.9, 0.1, 0.0, 0.0])
        idx.add("restart", [0.1, 0.9, 0.0, 0.0])
        query = [0.85, 0.15, 0.0, 0.0]
        result = idx.nearest(query, threshold=0.7)
        assert result == "deploy"

    def test_nearest_below_threshold_returns_none(self):
        idx = EmbeddingIndex(dim=4)
        idx.add("deploy", [0.9, 0.1, 0.0, 0.0])
        query = [0.1, 0.9, 0.0, 0.0]  # close to restart
        result = idx.nearest(query, threshold=0.9)
        assert result is None

    def test_hash_embedding_deterministic(self):
        e1 = EmbeddingIndex.hash_embedding("reorder", dim=8)
        e2 = EmbeddingIndex.hash_embedding("reorder", dim=8)
        assert e1 == e2


class TestDomainAdapter:
    def test_rule_matching(self):
        adapter = DomainAdapter(
            domain="test",
            rules={"deploy": ["deploy", "release"], "restart": ["restart", "reboot"]},
        )
        resolver = TieredActionResolver()
        resolver.register_domain(adapter)
        results = resolver.resolve("test", "please deploy the package")
        assert len(results) == 1
        assert results[0].action == "deploy"
        assert results[0].source == "rule"

    def test_falls_back_to_embedding(self):
        adapter = DomainAdapter(
            domain="test",
            rules={"deploy": ["deploy"]},
            action_index=EmbeddingIndex(dim=4),
        )
        adapter.action_index.add("restart", [0.1, 0.9, 0.0, 0.0])
        resolver = TieredActionResolver()
        resolver.register_domain(adapter)
        results = resolver.resolve("test", "reboot the service")
        assert len(results) >= 1

    def test_llm_fallback_when_no_rule_or_embedding(self):
        adapter = DomainAdapter(
            domain="test",
            rules={},
            llm_prompt_template="Classify: {text}",
            llm_callable=MockLLM(),
        )
        resolver = TieredActionResolver()
        resolver.register_domain(adapter)
        results = resolver.resolve("test", "unknown action")
        assert len(results) >= 1
        llm_result = [r for r in results if r.source == "llm"]
        assert len(llm_result) >= 1

    def test_no_adapter_returns_unknown(self):
        resolver = TieredActionResolver()
        results = resolver.resolve("nonexistent", "anything")
        assert results[0].action == "unknown"

    def test_on_new_action_updates_rules_and_index(self):
        adapter = DomainAdapter(
            domain="test",
            rules={},
            action_index=EmbeddingIndex(dim=4),
        )
        adapter.on_new_action("add monitoring", "add_monitoring")
        assert "add_monitoring" in adapter.rules
        assert adapter.action_index.size() == 1

    def test_stats(self):
        resolver = TieredActionResolver()
        resolver.register_domain(DomainAdapter(domain="test"))
        s = resolver.stats()
        assert "test" in s["domains"]
        assert s["per_domain"]["test"]["rules_count"] >= 0
