"""Tests for streaming validator"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.compiler.streaming_validator import StreamingValidator, ValidationConflict
from core.agent.compiler.rule_engine import RuleConstraintEngine, FrameLibrary
from core.agent.compiler.models import SlotValue, ParseContext


class TestStreamingValidator:
    def setup_method(self):
        self.engine = RuleConstraintEngine(FrameLibrary.load_default())
        self.validator = StreamingValidator(self.engine)

    def test_no_conflict(self):
        slot = SlotValue("drink", confidence=0.9)
        self.validator.on_slot_received("patient", slot, ParseContext())
        assert len(self.validator.conflicts) == 0

    def test_clear(self):
        slot = SlotValue("drink", confidence=0.9)
        self.validator.on_slot_received("patient", slot, ParseContext())
        self.validator.clear()
        assert len(self.validator.conflicts) == 0

    def test_resolve_no_change(self):
        slots = {"test": SlotValue("x")}
        result = self.validator.resolve(slots)
        assert result["test"].value == "x"


class TestValidationConflict:
    def test_defaults(self):
        vc = ValidationConflict("test", "a", "b", "hard")
        assert not vc.resolved
        assert vc.conflict_type == "hard"
        assert vc.slot_name == "test"
