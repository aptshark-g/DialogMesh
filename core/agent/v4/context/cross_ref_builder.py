"""CrossRefBuilder: generates cross-domain cross_ref pointers between Context IR entries.

Design doc reference: §6 跨域引用格式规范, §7 Context IR v2 格式
Stub — interface complete, logic minimized.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass(frozen=True)
class CrossRefPointer:
    """A single cross-domain pointer from one entry to another."""
    target_domain: str          # E/C/P/B/K
    target_event_id: str
    note: str = ""


@dataclass
class ContextIREntry:
    """Minimal stand-in for CrossDomainContextIR.entries items."""
    domain: str
    entry_type: str
    content: str
    source_events: List[str] = field(default_factory=list)
    cross_refs: List[CrossRefPointer] = field(default_factory=list)
    confidence: float = 0.0
    estimated_tokens: int = 0


class CrossRefBuilder:
    """Builds bidirectional cross_ref pointers across domain entries.

    Stub: naive matching by shared event_id overlap.
    Production: multi-hop expansion, semantic similarity,
                structural betweenness, domain heuristics.
    """

    DOMAINS: Set[str] = {"E", "C", "P", "B", "K"}

    def __init__(self, max_refs_per_entry: int = 3):
        self._max_refs = max_refs_per_entry

    def build(self, entries: List[ContextIREntry]) -> List[ContextIREntry]:
        """Return entries with cross_refs populated (stub: shared event_id match)."""
        if not entries:
            return []

        event_index: Dict[str, List[int]] = {}
        for idx, ent in enumerate(entries):
            for evt in ent.source_events:
                event_index.setdefault(evt, []).append(idx)

        result: List[ContextIREntry] = []
        for idx, ent in enumerate(entries):
            refs: List[CrossRefPointer] = []
            seen: Set[str] = set()
            for evt in ent.source_events:
                for oi in event_index.get(evt, []):
                    if oi == idx:
                        continue
                    other = entries[oi]
                    if other.domain == ent.domain:
                        continue
                    key = f"{other.domain}:{other.entry_type}:{other.content[:32]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    refs.append(CrossRefPointer(
                        target_domain=other.domain,
                        target_event_id=evt,
                        note=f"shared event {evt}",
                    ))
            refs.sort(key=lambda r: self._domain_priority(r.target_domain))
            ent.cross_refs = refs[: self._max_refs]
            result.append(ent)
        return result

    @classmethod
    def _domain_priority(cls, domain: str) -> int:
        order = {"E": 0, "B": 1, "C": 2, "P": 3, "K": 4}
        return order.get(domain, 99)

    def build_from_ir(self, ir: dict) -> dict:
        """Convenience wrapper accepting/returning raw CrossDomainContextIR dict."""
        raw = ir.get("entries", [])
        entries = [
            ContextIREntry(
                domain=e.get("domain", ""),
                entry_type=e.get("type", ""),
                content=e.get("content", ""),
                source_events=e.get("source_events", []),
                confidence=e.get("confidence", 0.0),
                estimated_tokens=e.get("estimated_tokens", 0),
            )
            for e in raw
        ]
        built = self.build(entries)
        for r, b in zip(raw, built):
            r["cross_refs"] = [
                {"target_domain": ref.target_domain,
                 "target_event_id": ref.target_event_id,
                 "note": ref.note}
                for ref in b.cross_refs
            ]
        return ir
