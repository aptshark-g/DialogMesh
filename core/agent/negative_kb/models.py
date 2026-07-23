from dataclasses import dataclass, field
from enum import Enum

class NegativeLevel(str, Enum):
    HARD_BLOCK = "hard_block"
    WARN = "warn"
    SOFT_DISCOURAGE = "soft_discourage"

@dataclass
class ContextualNegativeRule:
    rule_id: str
    level: NegativeLevel
    message: str
    domain: str = "general"
    is_verified: bool = False
    keywords: list = field(default_factory=list)

    def is_applicable(self, ctx_text: str = ""):
        if not self.keywords: return True
        return any(kw in ctx_text for kw in self.keywords)

@dataclass
class NegativeResult:
    level: NegativeLevel = None
    rule_id: str = ""
    message: str = ""
    blocked: bool = False
    learned: bool = False
    domain_exception: str = ""