"""TriggerRule — learn from tool successes/failures and auto-select tools.

When a custom tool succeeds for a specific domain/pattern, we record a rule
so next time the same pattern appears, the tool is auto-selected.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("dm.rules")

RULES_DIR = Path(__file__).parent.parent.parent.parent / "data" / "rules"
RULES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TriggerRule:
    """Auto-select a tool when conditions match."""
    domain: str = ""              # website domain pattern (e.g. "*.example.com")
    intent: str = ""              # intent match (e.g. "scrape", "download")
    action: str = ""              # original action that failed
    fallback: str = ""            # tool to use instead
    tool_path: str = ""           # path to generated tool code
    confidence: float = 1.0       # decay over time
    hits: int = 0
    created_at: str = ""
    last_used_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain, "intent": self.intent,
            "action": self.action, "fallback": self.fallback,
            "tool_path": self.tool_path, "confidence": self.confidence,
            "hits": self.hits, "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> TriggerRule:
        return cls(**{k: d.get(k, "") for k in cls.__dataclass_fields__})


class RuleStore:
    """Persistent rule storage."""
    _rules: Dict[str, List[TriggerRule]] = {}
    _path = RULES_DIR / "trigger_rules.json"

    @classmethod
    def _load(cls):
        if cls._rules:
            return
        if cls._path.exists():
            try:
                data = json.loads(cls._path.read_text(encoding="utf-8"))
                cls._rules = {k: [TriggerRule.from_dict(r) for r in v] for k, v in data.items()}
            except Exception:
                cls._rules = {}

    @classmethod
    def _save(cls):
        data = {k: [r.to_dict() for r in v] for k, v in cls._rules.items()}
        cls._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def add(cls, rule: TriggerRule):
        cls._load()
        now = datetime.now(timezone.utc).isoformat()
        rule.created_at = rule.created_at or now
        rule.last_used_at = now
        cls._rules.setdefault(rule.domain, []).append(rule)
        cls._save()
        logger.info("+rule domain=%s intent=%s → %s", rule.domain, rule.intent, rule.fallback)

    @classmethod
    def find(cls, domain: str = "", intent: str = "") -> Optional[TriggerRule]:
        """Find a matching rule for the given domain/intent."""
        cls._load()
        # Domain match
        if domain:
            for d, rules in cls._rules.items():
                if domain_match(d, domain):
                    for r in sorted(rules, key=lambda r: r.confidence * r.hits, reverse=True):
                        if intent and intent.lower() in r.intent.lower():
                            r.hits += 1
                            cls._save()
                            return r
        # Intent-only match
        if intent:
            for rules in cls._rules.values():
                for r in rules:
                    if intent.lower() in r.intent.lower():
                        r.hits += 1
                        cls._save()
                        return r
        return None

    @classmethod
    def list_all(cls) -> List[Dict]:
        cls._load()
        return [r.to_dict() for rules in cls._rules.values() for r in rules]


def domain_match(pattern: str, domain: str) -> bool:
    """Simple glob matching: *.example.com matches api.example.com."""
    if pattern == domain:
        return True
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return domain.endswith(suffix) or domain == suffix
    return False
