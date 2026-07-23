"""ContextSerializer: multi-strategy IR-to-prompt conversion.

Refinements over base spec:
1. Provider-aware strategy selection (GPT/DeepSeek/local)
2. Budget-aware format (full cross_ref vs abbreviated)
3. Pluggable serialization delegates
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from .models import Domain, ContextEntry, CrossDomainContextIR

logger = logging.getLogger(__name__)

DOMAIN_LABELS: Dict[Domain, str] = {
    Domain.ENGINEERING: "[工程]",
    Domain.CONVERSATION: "[对话]",
    Domain.PROFILE:    "[画像]",
    Domain.BEHAVIOR:   "[行为]",
    Domain.CAUSAL:     "[因果]",
}


class SerializeStrategy:
    """Pluggable serialization strategy."""

    def serialize(self, ir: CrossDomainContextIR) -> str:
        raise NotImplementedError


class StandardStrategy(SerializeStrategy):
    """Default structured format with cross_refs."""

    def serialize(self, ir: CrossDomainContextIR) -> str:
        parts = []
        parts.append(f"[CONTEXT] turn={ir.turn_number} strategy={ir.compile_strategy}")

        domain_entries: Dict[Domain, List[ContextEntry]] = {}
        for entry in ir.entries:
            domain_entries.setdefault(entry.domain, []).append(entry)

        for domain, entries in domain_entries.items():
            label = DOMAIN_LABELS.get(domain, f"[{domain.value}]")
            for entry in entries:
                line = f"{label} {entry.entry_type}: {entry.content}"
                for ref in entry.cross_refs:
                    line += f"\n  ^ref: {ref.target_domain.value}.{ref.target_event_id} = {ref.note}"
                if entry.source_events:
                    line += f"\n  src: {','.join(entry.source_events)}"
                parts.append(line)

        return "\n".join(parts)


class CompactStrategy(SerializeStrategy):
    """Abbreviated format for small-budget contexts (less 300 tokens)."""

    def serialize(self, ir: CrossDomainContextIR) -> str:
        parts = [f"[CTX t={ir.turn_number}]"]
        seen_domains = set()
        for entry in ir.entries:
            if entry.domain not in seen_domains:
                label = DOMAIN_LABELS.get(entry.domain, f"[{entry.domain.value}]")
                parts.append(f"{label} {entry.content[:200]}")
                seen_domains.add(entry.domain)
        return " | ".join(parts)


class PlainStrategy(SerializeStrategy):
    """Plain text for local models that struggle with structured format."""

    def serialize(self, ir: CrossDomainContextIR) -> str:
        lines = ["Context summary:"]
        for entry in ir.entries:
            domain_name = str(entry.domain.name).lower()
            lines.append(f"In terms of {domain_name}: {entry.content}")
            for ref in entry.cross_refs:
                lines.append(f"  (This relates to {ref.target_event_id}: {ref.note})")
        return "\n".join(lines)


class ContextSerializer:

    def __init__(self, provider_type: str = "default", monitor=None):
        self._provider_type = provider_type.lower()
        self._monitor = monitor
        self._strategies: Dict[str, SerializeStrategy] = {
            "standard": StandardStrategy(),
            "compact": CompactStrategy(),
            "plain": PlainStrategy(),
        }

    def serialize(self, ir: CrossDomainContextIR) -> str:
        strategy = self._choose_strategy(ir)
        result = strategy.serialize(ir)
        if self._monitor:
            estimated = max(1, len(result) // 3)
            self._monitor.record("context_serializer", "serialize", {
                "provider": self._provider_type,
                "strategy": type(strategy).__name__,
                "entries": len(ir.entries),
                "chars": len(result),
                "est_tokens": estimated,
            })
        return result

    def _choose_strategy(self, ir: CrossDomainContextIR) -> SerializeStrategy:
        if self._provider_type in ("ollama", "local", "lmstudio"):
            return self._strategies["plain"]
        if ir.total_estimated_tokens < 300:
            return self._strategies["compact"]
        return self._strategies["standard"]

    def set_provider(self, provider_type: str):
        self._provider_type = provider_type.lower()


def create_context_serializer(provider_type: str = "default", monitor=None) -> ContextSerializer:
    return ContextSerializer(provider_type=provider_type, monitor=monitor)
