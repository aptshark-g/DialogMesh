"""流式验证器 — 硬冲突标记 + 后覆盖"""
from dataclasses import dataclass
from .models import SlotValue, ParseContext
from .rule_engine import RuleConstraintEngine


@dataclass
class ValidationConflict:
    slot_name: str
    llm_value: str
    rule_suggestion: str
    conflict_type: str
    resolved: bool = False


class StreamingValidator:
    def __init__(self, engine: RuleConstraintEngine):
        self.engine = engine
        self.conflicts: list[ValidationConflict] = []

    def on_slot_received(self, slot_name: str, slot_value: SlotValue, context: ParseContext):
        rules = self.engine.library.query(slot_name, slot_value.value)
        for rule in rules:
            if not rule.is_applicable(context):
                continue
            if slot_value.value not in rule.candidates and rule.priority >= 10:
                suggestion = rule.candidates[0] if rule.candidates else ""
                self.conflicts.append(ValidationConflict(
                    slot_name=slot_name, llm_value=slot_value.value,
                    rule_suggestion=suggestion, conflict_type="hard"
                ))

    def resolve(self, slots: dict[str, SlotValue]) -> dict[str, SlotValue]:
        result = dict(slots)
        for c in self.conflicts:
            if c.conflict_type == "hard" and not c.resolved and c.rule_suggestion:
                result[c.slot_name] = SlotValue(
                    value=c.rule_suggestion, confidence=0.82,
                    source="rule", overridden=True
                )
                c.resolved = True
        return result

    def clear(self):
        self.conflicts.clear()
