from dataclasses import dataclass, field
from enum import Enum


class ContentCategory(str, Enum):
    DETERMINISTIC = "deterministic"
    TEMPLATE = "template"
    LLM = "llm"


@dataclass
class L1SummaryEntry:
    turn_id: str
    strategy: str
    core_semantics: str
    meta_info: dict = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class L1MetaInfo:
    prev_action: str = ""
    current_action: str = ""
    predicted_next: list = field(default_factory=list)
    causal_events: list = field(default_factory=list)
    associations: list = field(default_factory=list)
    is_topic_switch: bool = False
    user_satisfaction: str = "neutral"
    correction_detected: bool = False
    topic_id: str = ""
