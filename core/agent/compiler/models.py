"""约束补全编译器 — 数据模型"""
from dataclasses import dataclass, field, asdict
from typing import Optional

STANDARD_SLOTS = {"agent", "action", "patient", "result", "cause"}


@dataclass
class SlotValue:
    """单个语义槽位的值+置信度"""
    value: str
    confidence: float = 0.5
    source: str = "llm"
    overridden: bool = False
    raw_text: str = ""

    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, self.confidence))
        assert self.source in ("llm", "rule", "hybrid"), f"invalid source: {self.source}"


@dataclass
class ParseContext:
    """前序轮次上下文"""
    entities: dict[str, list[str]] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    constraint_state: dict = field(default_factory=dict)
    prev_stability: float = 0.0
    turn_count: int = 0
    correction_hint: Optional[str] = None

    def add_entity(self, category: str, value: str):
        if category not in self.entities:
            self.entities[category] = []
        if value not in self.entities[category]:
            self.entities[category].append(value)


@dataclass
class ParseResult:
    """编译器输出的结构化表示"""
    slots: dict[str, SlotValue] = field(default_factory=dict)
    stability: float = 0.0
    utterance_type: str = "statement"
    sentiment: str = "neutral"
    degraded: bool = False
    undefined: bool = False
    reasons: list[str] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def is_reliable(self) -> bool:
        return self.stability >= 0.6 and not self.undefined

    def to_dict(self) -> dict:
        return {
            "slots": {
                k: {"value": v.value, "confidence": v.confidence,
                    "source": v.source, "overridden": v.overridden}
                for k, v in self.slots.items()
            },
            "stability": self.stability,
            "utterance_type": self.utterance_type,
        }


@dataclass
class ConstraintRule:
    """约束规则（帧库条目）"""
    frame_name: str
    slot_name: str
    candidates: list[str]
    domain: str = "general"
    incompatible_with: dict[str, list[str]] = field(default_factory=dict)
    priority: int = 0
    condition: str = ""

    def is_applicable(self, ctx: ParseContext) -> bool:
        if not self.condition:
            return True
        parts = [p.strip() for p in self.condition.split(",")]
        for part in parts:
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k == "topic_contains" and v not in ctx.topics:
                return False
        return True


BEHAVIOR_TYPE_WEIGHTS = {
    "TOOL_EXEC": (0.7, 0.3),
    "CODE_RUN": (0.7, 0.3),
    "LOG_CHECK": (0.4, 0.6),
    "ENTITY_ANALYZE": (0.3, 0.7),
    "CONFIG_MODIFY": (0.5, 0.5),
    "EXPLORATION": (0.3, 0.7),
}


def get_behavior_weights(behavior_type: str) -> tuple[float, float]:
    return BEHAVIOR_TYPE_WEIGHTS.get(behavior_type, (0.5, 0.5))
