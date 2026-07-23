"""Cross-domain context compiler data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Domain(Enum):
    ENGINEERING = "E"
    CONVERSATION = "C"
    PROFILE = "P"
    BEHAVIOR = "B"
    CAUSAL = "K"


class IntentCategory(Enum):
    TASK = "task"
    QUERY = "query"
    CORRECTION = "correction"
    DISCUSSION = "discussion"
    CASUAL = "casual"
    TOPIC_SWITCH = "topic_switch"


@dataclass
class IntentEstimate:
    category: IntentCategory
    confidence: float


@dataclass
class DomainSelection:
    weights: Dict[Domain, float]
    primary_domain: Domain
    domain_order: List[Domain]
    intent_blend: Dict[IntentCategory, float]
    strategy_hint: str


@dataclass
class DomainFeedback:
    turn_number: int
    missing_domain: Domain
    current_intent: IntentCategory
    confidence: float = 0.7


@dataclass
class ContextEntry:
    domain: Domain
    entry_type: str
    content: str
    cross_refs: List[CrossRef] = field(default_factory=list)
    source_events: List[str] = field(default_factory=list)
    confidence: float = 0.8
    estimated_tokens: int = 0


@dataclass
class CrossRef:
    target_domain: Domain
    target_event_id: str
    note: str = ""


@dataclass
class CrossDomainContextIR:
    intent_category: Optional[IntentCategory] = None
    domain_allocation: List[Dict] = field(default_factory=list)
    entries: List[ContextEntry] = field(default_factory=list)
    total_estimated_tokens: int = 0
    compile_strategy: str = "balanced"
    turn_number: int = 0
    compile_time_ms: float = 0.0
