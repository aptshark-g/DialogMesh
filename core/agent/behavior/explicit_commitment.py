"""Explicit commitment — the explicit layer of the behavior chain.

Design mapping (DESIGN_BEHAVIOR §2 + PRINCIPLES arXiv:2509.17459):
    storage:  when(situation) -> should(strategy)
              + rather_than(failed) + because(reason)
    lifecycle: pending -> armed -> fired -> done
              (pending/armed -> cancelled | expired)
    schedule:  deterministic match -> hidden context blocks (<=3/turn);
               explicit commitments never compete in implicit prediction.
    feedback:  completion/cancel flows back to the behavior graph (显式->隐式);
               the trigger itself is NOT a learning signal (防自我强化).
    distillation: stable graph patterns -> explicit principle (隐式->显式, A24).
    cold start:  PRINCIPLES fallback re-simulation, gated by a PCR trigger (B5).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Lifecycle ────────────────────────────────────────────────────────────────

ACTIVE_STATUSES = {"pending", "armed"}
TERMINAL_STATUSES = {"done", "cancelled", "expired"}
TRANSITIONS = {
    "pending": {"armed", "cancelled", "expired"},
    "armed": {"fired", "cancelled", "expired"},
    "fired": {"done", "cancelled"},
}


@dataclass
class Commitment:
    id: str
    when: str
    should: str
    rather_than: str = ""
    because: str = ""
    status: str = "pending"
    source: str = "user"          # user | distilled
    trigger_keywords: List[str] = field(default_factory=list)
    created_at: float = 0.0
    fired_at: float = 0.0
    done_at: float = 0.0
    trigger_hits: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Commitment":
        return cls(**{k: d.get(k) for k in (
            "id", "when", "should", "rather_than", "because", "status",
            "source", "trigger_keywords", "created_at", "fired_at",
            "done_at", "trigger_hits", "metadata",
        )})

    def block(self) -> dict:
        """Hidden context block (design: <=3 per turn, explicit only)."""
        return {
            "commitment_id": self.id,
            "when": self.when,
            "should": self.should,
            "rather_than": self.rather_than,
            "because": self.because,
            "status": self.status,
            "source": self.source,
        }


# ── Declaration recognition (multi-perspective seed, B7) ─────────────────────

_STOPWORDS = {"当", "如果", "用户", "说", "到", "时", "的", "了", "要", "请", "记得",
              "以后", "每次", "下次", "都", "再", "先", "就", "我们", "我", "你"}

_DECLARE_PATTERNS = [
    re.compile(r"以后(?:每次|都|再)?[^，。；]{1,24}?(?:要|记得|先)[^，。；]{1,24}"),
    re.compile(r"下次[^，。；]{1,24}?(?:要|记得|先)[^，。；]{1,24}"),
    re.compile(r"当[^，。；]{1,24}时[^，。；]{1,24}?(?:要|请|记得)[^，。；]{1,24}"),
    re.compile(r"when\s+.{1,60}\s+should\s+.{1,60}", re.IGNORECASE),
]


def extract_keywords(text: str, max_keys: int = 6) -> List[str]:
    """Deterministic keyword extraction for FTS-style matching."""
    tokens = []
    try:
        import jieba
        tokens = jieba.lcut(text)
    except Exception:
        # Fallback: ASCII words + CJK 2-grams (no jieba available).
        ascii_words = re.findall(r"[A-Za-z0-9_]{2,}", text)
        cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
        for run in cjk_runs:
            if len(run) <= 2:
                tokens.append(run)
            else:
                tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
        tokens.extend(ascii_words)
    keys = []
    for t in tokens:
        if not t or t in _STOPWORDS or len(t) < 2:
            continue
        if t not in keys:
            keys.append(t)
    return keys[:max_keys]


def recognize_declaration(text: str) -> Optional[Tuple[str, str, float]]:
    """Recognize an explicit commitment declaration.

    Returns (when, should, confidence) or None. Confidence < 0.7 signals
    ambiguity → the system should ask the user for confirmation (B7).
    """
    if not text:
        return None
    for pat in _DECLARE_PATTERNS:
        m = pat.search(text)
        if m:
            matched = m.group(0)
            when, should = _split_when_should(matched)
            if when and should:
                confidence = 0.9 if pat.pattern.startswith("when") else 0.7
                return when, should, confidence
    return None


def _split_when_should(matched: str) -> Tuple[str, str]:
    """Split a declaration into (when, should) heuristically."""
    if matched.lower().startswith("when "):
        parts = re.split(r"\s+should\s+", matched, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts[0][5:].strip(), parts[1].strip()
    for kw in ("时要", "时要记得", "的时候", "时候", "时", "要", "记得", "先"):
        idx = matched.find(kw)
        if 0 < idx < len(matched) - 1:
            when = matched[:idx].lstrip("当如果用户说")
            should = matched[idx + len(kw):]
            if when and should:
                return when.strip("，。；"), should.strip("，。；")
    return "", ""


# ── Registry ─────────────────────────────────────────────────────────────────

class CommitmentRegistry:
    """Store + lifecycle state machine + deterministic matching.

    The registry is deliberately graph-agnostic: it shares the behavior-graph
    store via the feedback path (explicit->implicit), not via embedded nodes.
    """

    def __init__(self, store_path: Optional[str] = None):
        self._commitments: Dict[str, Commitment] = {}
        self._lock = threading.Lock()
        self._store_path = store_path
        self._event_log: List[dict] = []
        self._load()

    # ── lifecycle ──

    def add(self, when: str, should: str, rather_than: str = "",
            because: str = "", source: str = "user",
            trigger_keywords: Optional[List[str]] = None,
            metadata: Optional[dict] = None) -> Commitment:
        with self._lock:
            c = Commitment(
                id=f"cm_{uuid.uuid4().hex[:8]}",
                when=when,
                should=should,
                rather_than=rather_than,
                because=because,
                source=source,
                trigger_keywords=trigger_keywords or extract_keywords(when),
                metadata=metadata or {},
                created_at=time.time(),
            )
            self._commitments[c.id] = c
            self._log("add", c.id)
            return c

    def get(self, cid: str) -> Optional[Commitment]:
        return self._commitments.get(cid)

    def list(self, status: Optional[str] = None) -> List[Commitment]:
        items = list(self._commitments.values())
        if status:
            items = [c for c in items if c.status == status]
        return sorted(items, key=lambda c: c.created_at)

    def _transition(self, cid: str, target: str) -> Optional[Commitment]:
        c = self._commitments.get(cid)
        if c is None:
            return None
        if target not in TRANSITIONS.get(c.status, set()):
            return None
        c.status = target
        if target == "fired":
            c.fired_at = time.time()
            c.trigger_hits += 1
        if target == "done":
            c.done_at = time.time()
        self._log(target, cid)
        return c

    def arm(self, cid: str) -> Optional[Commitment]:
        return self._transition(cid, "armed")

    def fire(self, cid: str) -> Optional[Commitment]:
        return self._transition(cid, "fired")

    def complete(self, cid: str) -> Optional[Commitment]:
        return self._transition(cid, "done")

    def cancel(self, cid: str) -> Optional[Commitment]:
        return self._transition(cid, "cancelled")

    def expire(self, cid: str) -> Optional[Commitment]:
        return self._transition(cid, "expired")

    # ── matching (deterministic FTS; explicit never competes implicitly) ──

    def match(self, text: str, active_only: bool = True) -> List[Commitment]:
        """Return commitments whose trigger keywords hit the text."""
        if not text:
            return []
        hits = []
        for c in self._commitments.values():
            if active_only and c.status not in ACTIVE_STATUSES | {"fired"}:
                continue
            if any(k and k in text for k in c.trigger_keywords):
                hits.append(c)
        return hits

    def context_blocks(self, text: str, max_blocks: int = 3) -> List[dict]:
        """Hidden context blocks for a turn (design: <=3, no implicit race)."""
        matched = self.match(text)[:max_blocks]
        return [c.block() for c in matched]

    # ── feedback (显式->隐式; trigger itself is NOT a signal) ──

    def feedback(self, cid: str, outcome: str, graph=None) -> Optional[dict]:
        """Complete/cancel feedback → behavior-graph learning signal.

        completed → reinforce ``should`` (success edge)
        cancelled → downweight ``should`` (failure edge)
        Firing/triggering alone never emits a learning signal.
        """
        c = self._commitments.get(cid)
        if c is None or c.status not in ("fired", "done", "cancelled"):
            return None
        if outcome == "completed" and c.status != "done":
            self.complete(cid)
        elif outcome == "cancelled" and c.status not in ("cancelled", "done"):
            self.cancel(cid)
        if graph is not None:
            from core.agent.behavior.models import BehaviorStep
            prev_latest = None
            if graph.nodes:
                prev_latest = max(
                    graph.nodes.values(), key=lambda s: s.timestamp,
                )
            step = BehaviorStep(
                step_id=f"commit_{cid}_{int(time.time() * 1000)}",
                action_summary=c.should,
                action_type="commitment",
                timestamp=time.time(),
                metadata={"commitment_id": cid, "outcome": outcome},
            )
            graph.add_step(step)
            if prev_latest is not None:
                graph.record_edge(
                    prev_latest, step,
                    success=(outcome == "completed"),
                    correction=(outcome == "cancelled"),
                )
        return {
            "commitment_id": cid,
            "outcome": outcome,
            "should": c.should,
            "rather_than": c.rather_than,
            "delta_t": time.time() - (c.fired_at or c.created_at),
        }

    # ── distillation (隐式->显式, A24) ──

    def distill_from_graph(self, graph, min_sample: int = 5,
                           min_success: float = 0.7,
                           max_principles: int = 10) -> List[Commitment]:
        """Stable graph patterns -> explicit principles (source='distilled')."""
        created = []
        edges = list(getattr(graph, "edges", {}).values())
        stable = [
            e for e in edges
            if getattr(e, "is_stable", False)
            and e.sample_count >= min_sample
            and e.success_rate >= min_success
        ]
        stable.sort(key=lambda e: (-e.sample_count, -e.success_rate))
        for e in stable[:max_principles]:
            fs = graph.nodes.get(e.from_step_id)
            ts = graph.nodes.get(e.to_step_id)
            if not fs or not ts:
                continue
            when = fs.action_summary
            should = ts.action_summary
            existing = any(
                c.when == when and c.should == should for c in self._commitments.values()
            )
            if existing:
                continue
            created.append(self.add(
                when=when, should=should, source="distilled",
                because=f"stable pattern (n={e.sample_count}, success={e.success_rate:.2f})",
                rather_than="",
            ))
        return created

    # ── persistence / white-box ──

    def stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for c in self._commitments.values():
            counts[c.status] = counts.get(c.status, 0) + 1
        return {
            "total": len(self._commitments),
            "by_status": counts,
            "distilled": sum(1 for c in self._commitments.values() if c.source == "distilled"),
            "recent_events": self._event_log[-10:],
        }

    def _log(self, event: str, cid: str) -> None:
        self._event_log.append({"t": time.time(), "event": event, "cid": cid})
        if len(self._event_log) > 50:
            self._event_log = self._event_log[-50:]

    def save(self) -> None:
        if not self._store_path:
            return
        data = [c.to_dict() for c in self._commitments.values()]
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not self._store_path:
            return
        try:
            with open(self._store_path, encoding="utf-8") as f:
                for d in json.load(f):
                    c = Commitment.from_dict(d)
                    self._commitments[c.id] = c
        except (FileNotFoundError, json.JSONDecodeError):
            pass


# ── Cold-start fallback re-simulation (PRINCIPLES, B5) ──────────────────────

def cold_start_retry_trigger(pcr_output=None, turn: int = 0,
                             ambiguity: float = 0.0) -> bool:
    """B5 gate: only re-simulate when PCR flags specific cold-start features.

    Trigger when: very early session, or PCR reports an ambiguous/chaotic zone.
    """
    if turn <= 3:
        return True
    zone = None
    if isinstance(pcr_output, dict):
        zone = pcr_output.get("zone")
        ambiguity = max(ambiguity, float(pcr_output.get("ambiguity", 0.0)))
    else:
        zone = getattr(pcr_output, "zone", None)
        ambiguity = max(
            ambiguity, float(getattr(pcr_output, "ambiguity", 0.0) or 0.0),
        )
    if zone in ("ABYSS", "CHAOS", "MIXED") and ambiguity > 0.5:
        return True
    return ambiguity > 0.7


async def simulate_with_retry(llm, scenario: str, success_check: Callable,
                              max_attempts: int = 3,
                              token_budget: int = 800) -> Optional[Commitment]:
    """PRINCIPLES fallback re-simulation loop.

    simulate -> fail -> fall back to the failure point -> revise the strategy
    -> re-simulate until success or budget exhaustion.
    """
    history: List[dict] = []
    for attempt in range(max_attempts):
        prompt = _build_sim_prompt(scenario, history, attempt)
        try:
            raw = await llm.generate(prompt, max_tokens=token_budget)
        except Exception as e:
            logger.debug("Re-simulation LLM failed (attempt %d): %s", attempt, e)
            break
        ok, feedback = success_check(raw)
        if ok:
            should = str(raw).strip()[:120] or "follow-up action"
            return Commitment(
                id=f"cm_sim_{uuid.uuid4().hex[:8]}",
                when=scenario,
                should=should,
                because=f"re-simulated principle (attempt {attempt + 1})",
                source="distilled",
                trigger_keywords=extract_keywords(scenario),
                created_at=time.time(),
                metadata={"sim_attempts": attempt + 1, "feedback": feedback},
            )
        history.append({"attempt": attempt, "failure": feedback})
    return None


def _build_sim_prompt(scenario: str, history: List[dict], attempt: int) -> str:
    prompt = (
        f"Simulate the user's situation: {scenario}\n"
        "Derive ONE actionable strategy the assistant should commit to.\n"
    )
    if history:
        prompt += "Previous attempts failed:\n"
        for h in history:
            prompt += f"- attempt {h['attempt'] + 1}: {h['failure']}\n"
        prompt += "Revise the strategy, do not repeat the failed approach.\n"
    prompt += "Return the strategy text only."
    return prompt
