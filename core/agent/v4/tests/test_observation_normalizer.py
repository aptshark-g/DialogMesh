"""Tests for Normalizer."""
import pytest
from core.agent.v4.observation_compiler.normalizer import Normalizer
from core.agent.v4.event_ir import EventIR


class TestNormalizer:
    def test_normalize_basic(self):
        n = Normalizer()
        event = EventIR(id="e1", kind="dialog.message", payload={"text": "hello"})
        result = n.normalize(event)
        assert result["event_id"] == "e1"
        assert result["kind"] == "dialog.message"
        assert result["flat_payload"]["text"] == "hello"

    def test_flatten_nested_payload(self):
        n = Normalizer()
        event = EventIR(id="e2", kind="ui.drag", payload={"node": {"id": "42", "x": 100}})
        result = n.normalize(event)
        assert result["flat_payload"]["node.id"] == "42"
        assert result["flat_payload"]["node.x"] == 100

    def test_timestamp_ms_to_sec(self):
        n = Normalizer()
        event = EventIR(id="e3", kind="ui.click", payload={}, timestamp=1700000000000)
        result = n.normalize(event)
        assert result["timestamp"] < 1e10
