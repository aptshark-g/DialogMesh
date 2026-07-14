"""CrossDomainContextIR: intent-aware intermediate representation.

Design: §7.1 Context IR v2 — structured data with domain allocation,
cross-domain references, and budget-aware entries.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntentCategory(str, Enum):
    TASK = "task"
    QUERY = "query"
    CORRECTION = "correction"
    DISCUSSION = "discussion"
    CASUAL = "casual"
    TOPIC_SWITCH = "topic_switch"


class DomainRole(str, Enum):
    PRIMARY = "primary"
    AUXILIARY = "auxiliary"
    ANCHOR = "anchor"


class CompileStrategy(str, Enum):
    PRIMARY_DEEP = "primary_deep"
    BALANCED = "balanced"
    SUMMARY_FALLBACK = "summary_fallback"


@dataclass
class DomainAllocation:
    domain: str          # E / C / P / B / K
    role: DomainRole
    budget_pct: float    # 0.0–1.0
    budget_tokens: int = 0


@dataclass
class CrossRef:
    target_domain: str
    target_event_id: str
    note: str = ""


@dataclass
class IREntry:
    domain: str
    type: str
    content: str
    cross_refs: List[CrossRef] = field(default_factory=list)
    source_events: List[str] = field(default_factory=list)
    confidence: float = 0.0
    estimated_tokens: int = 0


@dataclass
class CrossDomainContextIR:
    """Intent-aware IR. Replaces flat CrossDomainContext in the new pipeline."""
    intent_category: IntentCategory
    domain_allocation: List[DomainAllocation] = field(default_factory=list)
    entries: List[IREntry] = field(default_factory=list)
    total_estimated_tokens: int = 0
    compile_strategy: CompileStrategy = CompileStrategy.BALANCED
    metadata: Dict[str, Any] = field(default_factory=dict)

    def primary_domain(self) -> Optional[str]:
        for a in self.domain_allocation:
            if a.role == DomainRole.PRIMARY:
                return a.domain
        return None

    def budget_for(self, domain: str) -> int:
        for a in self.domain_allocation:
            if a.domain == domain:
                return a.budget_tokens
        return 0

    def recalc_total(self) -> int:
        self.total_estimated_tokens = sum(e.estimated_tokens for e in self.entries)
        return self.total_estimated_tokens

    def entries_for(self, domain: str) -> List[IREntry]:
        return [e for e in self.entries if e.domain == domain]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_category": self.intent_category.value,
            "domain_allocation": [
                {
                    "domain": a.domain,
                    "role": a.role.value,
                    "budget_pct": a.budget_pct,
                    "budget_tokens": a.budget_tokens,
                }
                for a in self.domain_allocation
            ],
            "entries": [
                {
                    "domain": e.domain,
                    "type": e.type,
                    "content": e.content,
                    "cross_refs": [
                        {
                            "target_domain": r.target_domain,
                            "target_event_id": r.target_event_id,
                            "note": r.note,
                        }
                        for r in e.cross_refs
                    ],
                    "source_events": e.source_events,
                    "confidence": e.confidence,
                    "estimated_tokens": e.estimated_tokens,
                }
                for e in self.entries
            ],
            "total_estimated_tokens": self.total_estimated_tokens,
            "compile_strategy": self.compile_strategy.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossDomainContextIR":
        return cls(
            intent_category=IntentCategory(data.get("intent_category", "task")),
            domain_allocation=[
                DomainAllocation(
                    domain=a["domain"],
                    role=DomainRole(a["role"]),
                    budget_pct=a["budget_pct"],
                    budget_tokens=a.get("budget_tokens", 0),
                )
                for a in data.get("domain_allocation", [])
            ],
            entries=[
                IREntry(
                    domain=e["domain"],
                    type=e["type"],
                    content=e["content"],
                    cross_refs=[
                        CrossRef(
                            target_domain=r["target_domain"],
                            target_event_id=r["target_event_id"],
                            note=r.get("note", ""),
                        )
                        for r in e.get("cross_refs", [])
                    ],
                    source_events=e.get("source_events", []),
                    confidence=e.get("confidence", 0.0),
                    estimated_tokens=e.get("estimated_tokens", 0),
                )
                for e in data.get("entries", [])
            ],
            total_estimated_tokens=data.get("total_estimated_tokens", 0),
            compile_strategy=CompileStrategy(
                data.get("compile_strategy", "balanced")
            ),
            metadata=data.get("metadata", {}),
        )

    def to_prompt(self, system_instruction: str = None, max_tokens: int = None) -> str:
        """Serialize IR to Transformer-ready prompt string.

        Format:
          [System]
          <system_instruction>

          [Context]
          <domain:role> budget=N tokens
          - <type> [conf=X.X] <content> [→ <cross_ref>]
          ...

          [User]
          <last user message>

        Args:
            system_instruction: Override system prompt. If None, uses default.
            max_tokens: Token budget for truncation. If None, uses all entries.

        Returns:
            Prompt string ready for LLM.generate().
        """
        lines: List[str] = []

        # System section
        if system_instruction:
            lines.append("[System]")
            lines.append(system_instruction)
            lines.append("")

        # Context header with intent and strategy
        lines.append("[Context]")
        lines.append(f"intent={self.intent_category.value} strategy={self.compile_strategy.value}")
        lines.append("")

        # Domain allocation summary
        if self.domain_allocation:
            lines.append("# Domain Allocation")
            for alloc in self.domain_allocation:
                role_tag = "★" if alloc.role == DomainRole.PRIMARY else "•" if alloc.role == DomainRole.AUXILIARY else "◎"
                lines.append(f"  {role_tag} {alloc.domain}: {alloc.budget_tokens} tokens ({alloc.budget_pct:.0%})")
            lines.append("")

        # Entries by domain, with cross-ref annotations
        current_domain = None
        total_used = 0
        for entry in self.entries:
            if max_tokens and total_used + entry.estimated_tokens > max_tokens:
                lines.append("  [... truncated by token budget]")
                break

            if entry.domain != current_domain:
                current_domain = entry.domain
                lines.append(f"## [{current_domain.upper()}]")

            # Cross-ref annotation
            cross_note = ""
            if entry.cross_refs:
                refs = [f"→{r.target_domain}:{r.target_event_id[:8]}" for r in entry.cross_refs[:2]]
                cross_note = " " + " ".join(refs)

            conf_tag = f"[{entry.confidence:.2f}]" if entry.confidence > 0 else ""
            token_tag = f"({entry.estimated_tokens}t)" if entry.estimated_tokens > 0 else ""

            content = entry.content.replace("\n", " ")[:500]  # flatten, cap length
            lines.append(f"  • {entry.type} {conf_tag} {content}{cross_note} {token_tag}")
            total_used += entry.estimated_tokens

        lines.append("")
        lines.append(f"# Total: {total_used} tokens used")
        lines.append("")

        return "\n".join(lines)

    def to_legacy_context(self) -> "CrossDomainContext":
        """Bridge to flat CrossDomainContext for backward compat."""
        from core.agent.v4.context.source import CrossDomainContext, ContextItem
        items = [
            ContextItem(
                source=e.domain,
                content=e.content,
                relevance=e.confidence,
                metadata={
                    "type": e.type,
                    "cross_refs": [
                        {"target": r.target_domain, "event": r.target_event_id}
                        for r in e.cross_refs
                    ],
                    "source_events": e.source_events,
                    "estimated_tokens": e.estimated_tokens,
                },
            )
            for e in self.entries
        ]
        stats = {}
        for e in self.entries:
            stats[e.domain] = stats.get(e.domain, 0) + 1
        return CrossDomainContext(
            intent=self.intent_category.value,
            items=items,
            source_stats=stats,
            total_items=len(items),
        )
