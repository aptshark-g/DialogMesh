"""Profile Correction Journal — track, detect drift, trigger LLM review.

Every user correction is journaled with before/after/timestamp.
If system later diverges from user correction → flag + LLM retrospective.

"Behavior itself is the best implicit correlation data" — 用户纠正行为
本身就是人格信号 (高 conscientiousness, 高 meta-cognition).
"""
from __future__ import annotations
import json, os, time, logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CorrectionEntry:
    """Single user correction event."""
    timestamp: float = field(default_factory=time.time)
    dimension: str = ""          # "C", "A", "mbti", etc.
    before: Any = None           # system's value before correction
    after: Any = None            # user's corrected value
    reason: str = ""             # optional user-provided reason
    turn: int = 0                # which turn this happened


class CorrectionJournal:
    """Tracks all user corrections with drift detection.

    Stores: data/profile/corrections.jsonl
    Detects: when system diverges from user-set values
    Triggers: LLM retrospective review
    """

    def __init__(self, path: str = "data/profile/corrections.jsonl"):
        self._path = path
        self._entries: List[CorrectionEntry] = []
        self._last_corrected: Dict[str, CorrectionEntry] = {}  # dim → last correction
        self._load()

    def record(self, dimension: str, before: Any, after: Any,
               reason: str = "", turn: int = 0) -> CorrectionEntry:
        """Journal a correction."""
        entry = CorrectionEntry(
            dimension=dimension, before=before, after=after,
            reason=reason, turn=turn,
        )
        self._entries.append(entry)
        self._last_corrected[dimension] = entry

        # Append to JSONL
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps({
                "ts": entry.timestamp,
                "dim": dimension,
                "before": str(before),
                "after": str(after),
                "reason": reason,
                "turn": turn,
            }, ensure_ascii=False) + "\n")

        logger.info("Correction: %s: %s → %s (turn %d)", dimension, before, after, turn)
        return entry

    def check_drift(self, dimension: str, current_value: Any,
                    tolerance: float = 0.15) -> Optional[Dict]:
        """Check if system diverged from user correction.

        Returns drift alert if system moved > tolerance away from user-set value.
        """
        if dimension not in self._last_corrected:
            return None

        last = self._last_corrected[dimension]
        user_val = last.after

        # Compare based on type
        if isinstance(user_val, (int, float)) and isinstance(current_value, (int, float)):
            drift = abs(current_value - user_val)
            if drift > tolerance:
                return {
                    "dimension": dimension,
                    "user_set": user_val,
                    "current": round(current_value, 2),
                    "drift": round(drift, 2),
                    "corrected_at_turn": last.turn,
                    "turns_since": time.time() - last.timestamp,
                    "severity": "high" if drift > 0.3 else "medium" if drift > 0.2 else "low",
                }
        elif isinstance(user_val, str) and isinstance(current_value, str):
            if user_val != current_value:
                return {"dimension": dimension, "user_set": user_val,
                        "current": current_value, "severity": "high"}

        return None

    def build_retrospective_prompt(self, drifts: List[Dict],
                                    recent_turns: List[str]) -> str:
        """Build LLM prompt for retrospective review.

        When system drifts away from user correction, ask LLM:
        "What changed in the user's behavior? Was the correction wrong, or did behavior change?"
        """
        drift_lines = []
        for d in drifts:
            drift_lines.append(
                f"  {d['dimension']}: user set {d['user_set']}, now {d['current']} "
                f"(drift={d.get('drift', 'N/A')}, severity={d['severity']})"
            )

        recent = "\n".join(f"  T{i+1}: {t[:200]}" for i, t in enumerate(recent_turns[-5:]))

        return f"""The user previously corrected their profile. Now the system has drifted away.

USER CORRECTIONS (journaled):
{chr(10).join(drift_lines)}

RECENT CONVERSATION:
{recent}

Analyze and respond with JSON:
{{
  "verdict": "correction_still_valid|behavior_changed|correction_was_wrong",
  "explanation": "why the drift happened",
  "recommendation": "revert_to_user_value|accept_new_value|ask_user",
  "confidence": 0.5
}}

If the user's recent conversation style genuinely changed → behavior_changed.
If the system is just reverting to its default → correction_still_valid."""

    def stats(self) -> Dict[str, Any]:
        return {
            "total_corrections": len(self._entries),
            "by_dimension": {d: sum(1 for e in self._entries if e.dimension == d)
                           for d in set(e.dimension for e in self._entries)},
            "last": self._entries[-1].__dict__ if self._entries else None,
        }

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        entry = CorrectionEntry(
                            timestamp=d["ts"], dimension=d["dim"],
                            before=d.get("before"), after=d.get("after"),
                            turn=d.get("turn", 0),
                        )
                        self._entries.append(entry)
                        self._last_corrected[d["dim"]] = entry
                    except Exception:
                        pass
