"""XML Memory Cards — structured user memory with person/relationship/backstory.

6 card types: person, preference, fact, event, plan, heuristic.
XML format: LLM-native understanding + attribute-based disambiguation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET
import time, uuid, re


# ── Card Types ──

@dataclass
class MemoryCard:
    """Base memory card."""
    card_id: str = field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    card_type: str = "fact"       # person | preference | fact | event | plan | heuristic
    confidence: float = 0.5
    created: str = ""
    updated: str = ""
    temperature: str = "warm"     # hot | warm | cold | frozen
    information_value: float = 0.5
    version: int = 1
    evidence: List[dict] = field(default_factory=list)  # [{session, turn, text}]
    
    def __post_init__(self):
        if not self.created:
            self.created = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.updated = self.created

    def to_xml(self) -> str:
        """Serialize to XML string."""
        raise NotImplementedError

    def update(self, **kwargs):
        """Partial update — modify specific fields without rewriting entire card."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.version += 1

    def _meta_xml(self) -> str:
        return f"""  <meta>
    <created>{self.created}</created>
    <updated>{self.updated}</updated>
    <temperature>{self.temperature}</temperature>
    <information_value>{self.information_value:.2f}</information_value>
    <version>{self.version}</version>
  </meta>"""

    def _evidence_xml(self) -> str:
        if not self.evidence:
            return ""
        lines = ["  <evidence>"]
        for e in self.evidence:
            lines.append(f'    <source session="{e.get("session","")}" turn="{e.get("turn","")}">')
            lines.append(f'      {_xml_escape(e.get("text","")[:200])}')
            lines.append(f'    </source>')
        lines.append("  </evidence>")
        return "\n".join(lines)


@dataclass
class PersonCard(MemoryCard):
    """A person the user interacts with."""
    card_type: str = "person"
    name: str = ""
    role: str = ""              # "牙科主治医师"
    relationship: str = ""       # "user_provider" | "family" | "colleague" | "friend"
    relationship_since: str = ""
    relationship_frequency: str = ""  # "quarterly" | "daily" | "rarely"
    last_interaction: str = ""
    backstory: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)

    def to_xml(self) -> str:
        attrs = "\n".join(f'    <attr key="{_xml_escape(k)}">{_xml_escape(v)}</attr>' 
                         for k, v in self.attributes.items())
        return f"""<memory_card id="{self.card_id}" type="person" confidence="{self.confidence:.2f}">
  <person name="{_xml_escape(self.name)}" role="{_xml_escape(self.role)}"/>
  <relationship type="{self.relationship}" since="{self.relationship_since}" 
                frequency="{self.relationship_frequency}" last_interaction="{self.last_interaction}"/>
  <backstory>{_xml_escape(self.backstory)}</backstory>
  <attributes>
{attrs}
  </attributes>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


@dataclass
class PreferenceCard(MemoryCard):
    """User preference in a domain."""
    card_type: str = "preference"
    domain: str = ""            # "travel" | "food" | "work" | "health"
    preferences: Dict[str, str] = field(default_factory=dict)

    def to_xml(self) -> str:
        prefs = "\n".join(f'    <preference key="{_xml_escape(k)}">{_xml_escape(v)}</preference>' 
                         for k, v in self.preferences.items())
        return f"""<memory_card id="{self.card_id}" type="preference" confidence="{self.confidence:.2f}">
  <domain>{_xml_escape(self.domain)}</domain>
  <preferences>
{prefs}
  </preferences>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


@dataclass
class FactCard(MemoryCard):
    """A single fact."""
    card_type: str = "fact"
    domain: str = ""
    key: str = ""
    value: str = ""

    def to_xml(self) -> str:
        return f"""<memory_card id="{self.card_id}" type="fact" confidence="{self.confidence:.2f}">
  <fact key="{_xml_escape(self.key)}" domain="{_xml_escape(self.domain)}">{_xml_escape(self.value)}</fact>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


@dataclass
class EventCard(MemoryCard):
    """An event in the user's life."""
    card_type: str = "event"
    date: str = ""
    category: str = ""          # "health" | "travel" | "work" | "life"
    description: str = ""
    outcome: str = ""

    def to_xml(self) -> str:
        return f"""<memory_card id="{self.card_id}" type="event" confidence="{self.confidence:.2f}">
  <event date="{self.date}" category="{_xml_escape(self.category)}">
    <description>{_xml_escape(self.description)}</description>
    <outcome>{_xml_escape(self.outcome)}</outcome>
  </event>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


@dataclass
class PlanCard(MemoryCard):
    """Predicted future intent (from L4 temporal)."""
    card_type: str = "plan"
    intent: str = ""
    trigger: str = ""           # what triggers this plan
    expected_action: str = ""   # what Agent should do
    conditions: List[str] = field(default_factory=list)

    def to_xml(self) -> str:
        conds = "\n".join(f'    <condition>{_xml_escape(c)}</condition>' for c in self.conditions)
        return f"""<memory_card id="{self.card_id}" type="plan" confidence="{self.confidence:.2f}">
  <intent>{_xml_escape(self.intent)}</intent>
  <trigger>{_xml_escape(self.trigger)}</trigger>
  <expected_action>{_xml_escape(self.expected_action)}</expected_action>
  <conditions>
{conds}
  </conditions>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


@dataclass
class HeuristicCard(MemoryCard):
    """Condensed thinking pattern (from DerivationCompressor)."""
    card_type: str = "heuristic"
    pattern: str = ""
    derivation: str = ""        # "发散→收敛"路径
    counterexample: str = ""
    test_results: List[bool] = field(default_factory=list)

    def to_xml(self) -> str:
        return f"""<memory_card id="{self.card_id}" type="heuristic" confidence="{self.confidence:.2f}">
  <pattern>{_xml_escape(self.pattern)}</pattern>
  <derivation>{_xml_escape(self.derivation)}</derivation>
  <counterexample>{_xml_escape(self.counterexample)}</counterexample>
{self._evidence_xml()}
{self._meta_xml()}
</memory_card>"""


# ── Utilities ──

def _xml_escape(text: str) -> str:
    """Escape XML special chars."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;"))


def parse_card(xml_str: str) -> Optional[MemoryCard]:
    """Parse XML string back to MemoryCard."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        # Try without XML declaration
        try:
            root = ET.fromstring(xml_str.split("?>", 1)[-1].strip())
        except ET.ParseError:
            return None

    card_id = root.get("id", "")
    card_type = root.get("type", "fact")
    confidence = float(root.get("confidence", 0.5))

    if card_type == "person":
        person_el = root.find("person")
        rel_el = root.find("relationship")
        backstory_el = root.find("backstory")
        attrs = {}
        for attr in root.findall(".//attr"):
            attrs[attr.get("key", "")] = attr.text or ""
        return PersonCard(
            card_id=card_id, confidence=confidence,
            name=person_el.get("name", "") if person_el is not None else "",
            role=person_el.get("role", "") if person_el is not None else "",
            relationship=rel_el.get("type", "") if rel_el is not None else "",
            backstory=(backstory_el.text or "") if backstory_el is not None else "",
            attributes=attrs,
        )
    elif card_type == "preference":
        domain_el = root.find("domain")
        prefs = {}
        for p in root.findall(".//preference"):
            prefs[p.get("key", "")] = p.text or ""
        return PreferenceCard(
            card_id=card_id, confidence=confidence,
            domain=(domain_el.text or "") if domain_el is not None else "",
            preferences=prefs,
        )
    elif card_type == "fact":
        fact_el = root.find("fact")
        return FactCard(
            card_id=card_id, confidence=confidence,
            key=fact_el.get("key", "") if fact_el is not None else "",
            domain=fact_el.get("domain", "") if fact_el is not None else "",
            value=(fact_el.text or "") if fact_el is not None else "",
        )

    return MemoryCard(card_id=card_id, card_type=card_type, confidence=confidence)
