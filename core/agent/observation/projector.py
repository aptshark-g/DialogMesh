"""Projector: routes Events to target cognitive domains based on EventKind."""
from __future__ import annotations
from typing import Dict, List


# Routing table: Event kind → target domains
ROUTING_TABLE: Dict[str, List[str]] = {
    "dialog.message": ["dialogue", "memory", "user"],
    "ui.click": ["behavior", "memory"],
    "ui.drag": ["engineering", "behavior", "memory"],
    "ui.drop": ["engineering", "behavior", "task"],
    "tool.call": ["engineering", "behavior", "causal"],
    "config.change": ["engineering", "memory"],
    "api.call": ["engineering", "causal"],
    "git.commit": ["engineering", "memory"],
}

DEFAULT_DOMAINS = ["memory"]


class Projector:
    """Determines which cognitive domains an Event should be projected to."""

    def project(self, kind: str) -> List[str]:
        return ROUTING_TABLE.get(kind, list(DEFAULT_DOMAINS))

    def all_domains(self) -> List[str]:
        """Return all known domains."""
        domains: set[str] = set(DEFAULT_DOMAINS)
        for targets in ROUTING_TABLE.values():
            domains.update(targets)
        return sorted(domains)
