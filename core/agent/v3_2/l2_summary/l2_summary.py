"""L2 Summary - session-level aggregation with LLM compression"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class L2SummaryEntry:
    """Session-level summary entry with v1-v4 summary state"""
    session_id: str = ""
    turn_count: int = 0
    topics: list = field(default_factory=list)
    key_actions: list = field(default_factory=list)
    total_latency_ms: float = 0.0
    avg_stability: float = 0.0
    summary_v1: str = ""      # raw concatenated
    summary_v2: str = ""      # entity-extracted
    summary_v3: str = ""      # milestone-extracted
    summary_v4: str = ""      # LLM-compressed
    summary_version: int = 1


class L2Summary:
    """L2 Summary with session-level aggregation and LLM compression callback"""

    def __init__(self, max_turns=100, llm_provider=None):
        self.max_turns = max_turns
        self.turns = []
        self.llm = llm_provider

    def add_turn(self, l1_data: dict):
        """Store L1 turn data"""
        self.turns.append(l1_data)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def summarize(self, session_id="", llm_callback=None) -> L2SummaryEntry:
        """Generate session-level aggregation with v1-v4 summary"""
        if not self.turns:
            return L2SummaryEntry(session_id=session_id)

        recent = self.turns[-20:]
        topics = list(set(str(t) for t in [x.get("topic", "") for x in recent] if str(t)))
        actions = list(set(str(a) for a in [x.get("action", "") for x in recent] if str(a)))
        stabs = [float(t.get("stability", 0)) for t in self.turns if t.get("stability")]
        avg_s = sum(stabs) / len(stabs) if stabs else 0.0
        last_q = str(recent[-1].get("query", ""))[:50] if recent else ""

        # v1: raw concatenated
        v1 = f"{len(self.turns)} turns, {len(topics)} topics, last: {last_q}"

        # v2: entity-extracted
        entities = [str(e) for t in recent for e in (t.get("entities", []) or []) if e]
        v2 = f"[{', '.join(topics[:5])}] key_actions: {', '.join(actions[:5])}"
        if entities:
            v2 += f" | entities: {', '.join(set(entities[:5]))}"

        # v3: milestone-extracted
        errors = sum(1 for t in recent if t.get("error"))
        corrections = sum(1 for t in recent if t.get("correction"))
        v3 = v2
        if errors or corrections:
            v3 += f" | {errors} errors, {corrections} corrections"

        # v4: LLM-compressed (callback)
        v4 = ""
        callback = llm_callback or self.llm
        if callback and len(self.turns) >= 5:
            try:
                text = v3 if len(v3) > len(v1) else v1
                prompt = f"Compress this conversation summary into <=80 chars. Keep topics and actions.\n{text}"
                if callable(callback):
                    result = callback(prompt)
                    if result and len(str(result)) > 10:
                        v4 = str(result)[:120]
                elif hasattr(callback, "generate"):
                    import asyncio
                    result = asyncio.run(callback.generate(prompt, max_tokens=100))
                    if result and len(str(result)) > 10:
                        v4 = str(result)[:120]
            except Exception:
                v4 = ""

        ver = 4 if v4 else 3 if corrections else 2 if entities else 1
        return L2SummaryEntry(
            session_id=session_id, turn_count=len(self.turns),
            topics=topics[:10], key_actions=actions[:10],
            avg_stability=avg_s, summary_v1=v1, summary_v2=v2,
            summary_v3=v3, summary_v4=v4, summary_version=ver,
        )


def build_daily_report(sessions):
    """Build multi-session report from list of L2SummaryEntry"""
    if not sessions:
        return "No sessions"
    all_topics = set()
    total_turns = 0
    for s_obj in sessions:
        s = s_obj if isinstance(s_obj, dict) else s_obj.__dict__
        top = s.get("topics", []) if isinstance(s, dict) else (getattr(s_obj, "topics", []) or [])
        all_topics.update(top[:5])
        total_turns += s.get("turn_count", 0) if isinstance(s, dict) else getattr(s_obj, "turn_count", 0)
    return f"{len(sessions)} sessions | {total_turns} turns | {len(all_topics)} unique topics: {', '.join(list(all_topics)[:8])}"
