"""Meta-cognition: the system's second brain.

Design: BUSINESS_CHAIN_09
P0: review queue, retrospection engine, dual-mode decision, self-retrospection.

Data sources (passive + active):
  Passive: pushed from chains (corrections, anomalies, drifts, candidates)
  Active: periodic scan (low-confidence edges, stale annotations, decayed patterns)
"""
from __future__ import annotations
import json, os, time, logging
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from .version_control import GlobalVersionControl, Commit

logger = logging.getLogger(__name__)


# ── Data Models ──

class ReviewPriority(Enum):
    URGENT = 1     # risk operations, user corrections, drifts > 0.25
    HIGH = 2       # breaker OPEN, pattern candidate with high support
    NORMAL = 3     # low-confidence edges, parameter changes
    LOW = 4        # decayed patterns, long-term unscanned

class DecisionMode(Enum):
    RAPID = "rapid"           # single LLM call, <5s, immediate action
    DELIBERATE = "deliberate" # multi-round, multi-perspective, may surface to user

@dataclass
class ReviewItem:
    """One item in the meta-cognition review queue."""
    item_id: str
    source: str              # "behavior_chain" | "association" | "profile" | "engineering" | "self"
    target: str              # specific data target (e.g. "behavior.pattern.add_test")
    priority: ReviewPriority
    mode: DecisionMode
    data: Dict[str, Any]     # context for the review
    created_at: float = field(default_factory=time.time)
    reviewed_at: Optional[float] = None
    verdict: Optional[str] = None  # "approved" | "rejected" | "rollback" | "escalate" | "surface_to_user"
    verdict_reason: Optional[str] = None

@dataclass
class RetrospectionReport:
    """Before/after comparison of a change."""
    target: str
    commit: Optional[Commit]
    metrics_before: Dict[str, Any]
    metrics_after: Dict[str, Any]
    delta: Dict[str, float]
    verdict: str             # "effective" | "neutral" | "harmful" | "inconclusive"
    recommendation: str      # "keep" | "rollback" | "adjust" | "investigate"
    confidence: float

@dataclass
class MetaDecision:
    """Record of a meta-cognition decision (for self-retrospection)."""
    decision_id: str
    timestamp: float
    review_item: str         # item_id
    verdict: str
    reasoning: str
    was_correct: Optional[bool] = None  # verified later

MetaReflection = MetaDecision  # backward compat — renamed during v4→v6 merge


# ── Meta-cognition Engine ──

class MetaCognition:
    """The second brain — reviews, retrospects, decides.
    
    API:
      submit(item)          → push to review queue
      scan(engine)          → active scanning for issues
      process_queue()       → review pending items (urgent first)
      retrospect(commit)    → before/after impact analysis
      self_audit()          → review own decision accuracy
    """

    def __init__(self, llm_provider=None, vcs: GlobalVersionControl = None,
                 persist_dir: str = "data/meta", meta_consumer: Any = None):
        self._llm = llm_provider
        self._vcs = vcs or GlobalVersionControl()
        self._queue: List[ReviewItem] = []
        self._decisions: List[MetaDecision] = []
        self._persist_dir = persist_dir
        # M8 归一: v6 MetaConsumer 作为本内核的组件（学习闭环接入层），
        # 不再作为"第三套并行实现"独立存在。
        self._meta_consumer = meta_consumer
        os.makedirs(persist_dir, exist_ok=True)
        self._load()

    # ── Review Queue ──

    def submit(self, source: str, target: str, data: Dict,
               priority: ReviewPriority = ReviewPriority.NORMAL,
               mode: DecisionMode = DecisionMode.DELIBERATE) -> ReviewItem:
        """Push an item into the review queue (passive receive)."""
        item = ReviewItem(
            item_id=f"rev_{int(time.time()*1000)}_{source}",
            source=source, target=target, priority=priority, mode=mode, data=data,
        )
        self._queue.append(item)
        self._queue.sort(key=lambda x: x.priority.value)
        logger.info("MetaCognition: queued review %s [%s/%s]", item.item_id, source, priority.name)
        return item

    def scan(self, engine) -> List[ReviewItem]:
        """Active scan: find issues that weren't pushed."""
        items = []
        # Scan profile drift
        if hasattr(engine, '_correction_journal') and engine._correction_journal:
            ocean = getattr(getattr(engine, '_ocean_analyst', None), 'profile', None)
            if ocean:
                journal = engine._correction_journal
                for dim, val in ocean.dims.items():
                    drift = journal.check_drift(dim, val)
                    if drift:
                        items.append(self.submit(
                            "profile_drift", f"profile.{dim}",
                            {"drift": drift, "current": val},
                            ReviewPriority.URGENT, DecisionMode.RAPID,
                        ))
        # Scan low-confidence relations (placeholder)
        # Scan stale annotations (placeholder)
        # Scan unreviewed patterns (placeholder)
        return items

    def consume_trace(self, trace, turn_count: int) -> Dict[str, Any]:
        """M8 归一入口: 消费 ExecutionTraceV3 → 建议转审核队列。

        v6 MetaConsumer 原为"第三套并行实现"（runtime/engine 从未接线）。
        现在作为本内核组件: consume() 产出的建议直接进入审核队列（ReviewItem），
        裁决/复盘/自我复盘仍由本内核统一处理。
        """
        if self._meta_consumer is None:
            try:
                from core.agent.v4.cognitive.meta_consumer import MetaConsumer
                self._meta_consumer = MetaConsumer()
            except Exception as e:
                logger.debug("MetaConsumer unavailable: %s", e)
                return {"adjust": False}
        advice = self._meta_consumer.consume(trace, turn_count)
        if advice and advice.get("adjust"):
            warnings = advice.get("warnings") or []
            for warning in warnings[:3]:
                self.submit(
                    source="self",
                    target="learning_loop",
                    data={
                        "warning": warning,
                        "turn": turn_count,
                        "suggestions": (advice.get("suggestions") or [])[:3],
                    },
                    priority=(
                        ReviewPriority.URGENT if "REJECT" in warning.upper()
                        else ReviewPriority.NORMAL
                    ),
                    mode=DecisionMode.RAPID,
                )
        return advice

    def process_queue(self, max_items: int = 3) -> List[ReviewItem]:
        """Process pending review items (urgent first). Returns reviewed items."""
        reviewed = []
        pending = [i for i in self._queue if i.verdict is None]
        
        for item in pending[:max_items]:
            if item.mode == DecisionMode.RAPID:
                self._rapid_review(item)
            else:
                self._deliberate_review(item)
            
            item.reviewed_at = time.time()
            reviewed.append(item)
            
            # Record decision
            self._decisions.append(MetaDecision(
                decision_id=f"dec_{int(time.time()*1000)}",
                timestamp=time.time(), review_item=item.item_id,
                verdict=item.verdict or "pending",
                reasoning=item.verdict_reason or "",
            ))
            
            # Record to version control
            self._vcs.commit(
                "meta_decision", item.target,
                before={"status": "pending_review"},
                after={"verdict": item.verdict, "reason": item.verdict_reason},
                author="meta_cognition",
                reason=f"reviewed: {item.verdict}",
            )
        
        self._save()
        return reviewed

    def _rapid_review(self, item: ReviewItem):
        """Single LLM call, immediate verdict."""
        if self._llm and item.data:
            try:
                prompt = self._build_rapid_prompt(item)
                from core.agent.llm_providers.base import GenerateRequest
                result = self._llm.generate(GenerateRequest(prompt=prompt, max_tokens=300, temperature=0.3))
                text = result.text if hasattr(result, 'text') else str(result)
                # Parse verdict
                if "APPROVE" in text.upper():
                    item.verdict = "approved"
                elif "REJECT" in text.upper():
                    item.verdict = "rejected"
                elif "ROLLBACK" in text.upper():
                    item.verdict = "rollback"
                else:
                    item.verdict = "escalate"
                item.verdict_reason = text[:300]
            except Exception as e:
                item.verdict = "escalate"
                item.verdict_reason = f"LLM unavailable: {e}"
        else:
            # No LLM → heuristic fallback
            if "drift" in item.data and item.data.get("drift", {}).get("severity") == "high":
                item.verdict = "escalate"
                item.verdict_reason = "high drift, needs LLM review"
            else:
                item.verdict = "approved"
                item.verdict_reason = "heuristic: low risk, auto-approved"

    def _deliberate_review(self, item: ReviewItem):
        """Multi-perspective review — placeholder for full implementation."""
        # For now: multi-round LLM with evidence collection
        if self._llm:
            try:
                prompt = self._build_deliberate_prompt(item)
                from core.agent.llm_providers.base import GenerateRequest
                result = self._llm.generate(GenerateRequest(prompt=prompt, max_tokens=500, temperature=0.3))
                text = result.text if hasattr(result, 'text') else str(result)
                item.verdict = "approved" if "valid" in text.lower() else "escalate"
                item.verdict_reason = text[:400]
            except Exception as e:
                item.verdict = "escalate"
                item.verdict_reason = f"LLM error: {e}"
        else:
            item.verdict = "approved"
            item.verdict_reason = "heuristic: no LLM, auto-approved"

    # ── Retrospection ──

    def retrospect(self, target: str, category: str = "parameters") -> Optional[RetrospectionReport]:
        """Before/after comparison of a change."""
        store = self._vcs.store(category)
        commits = store.history(target, 5)
        if len(commits) < 2: return None

        latest = commits[0]
        prev = commits[1]

        # Simple delta: compare numeric values
        delta = {}
        try:
            before_val = float(str(prev.after).split()[-1]) if prev.after else 0
            after_val = float(str(latest.after).split()[-1]) if latest.after else 0
            delta["value_change"] = after_val - before_val
            delta["direction"] = "increase" if after_val > before_val else "decrease"
        except (ValueError, AttributeError):
            delta["value_change"] = 0

        verdict = "inconclusive"
        if abs(delta.get("value_change", 0)) > 0:
            # heuristic: any change = needs evaluation
            verdict = "neutral"

        return RetrospectionReport(
            target=target, commit=latest,
            metrics_before={"value": str(prev.after)[:100]},
            metrics_after={"value": str(latest.after)[:100]},
            delta=delta, verdict=verdict,
            recommendation="keep" if verdict in ("effective", "neutral") else "investigate",
            confidence=0.5,
        )

    # ── Self-Retrospection ──

    def self_audit(self) -> Dict[str, Any]:
        """Review own decision accuracy."""
        total = len(self._decisions)
        if total == 0: return {"total": 0}
        
        verified = [d for d in self._decisions if d.was_correct is not None]
        correct = [d for d in verified if d.was_correct]
        accuracy = len(correct) / len(verified) if verified else 0
        
        by_verdict = {}
        for d in self._decisions:
            v = d.verdict
            by_verdict[v] = by_verdict.get(v, 0) + 1
        
        return {
            "total_decisions": total,
            "verified": len(verified),
            "accuracy": round(accuracy, 2),
            "by_verdict": by_verdict,
            "recommendation": "lower_threshold" if accuracy < 0.7 else "maintain",
        }

    def verify_past_decision(self, item_id: str, was_correct: bool):
        """Mark a past decision as verified correct/incorrect."""
        for d in self._decisions:
            if d.review_item == item_id and d.was_correct is None:
                d.was_correct = was_correct
                break

    # ── Prompt builders ──

    def _build_rapid_prompt(self, item: ReviewItem) -> str:
        return f"""Rapid review: {item.source} → {item.target}
Data: {json.dumps(item.data, ensure_ascii=False)[:500]}

Respond with single word: APPROVE, REJECT, ROLLBACK, or ESCALATE.
Then briefly explain why."""

    def _build_deliberate_prompt(self, item: ReviewItem) -> str:
        return f"""Deliberate review: {item.source} → {item.target}
Data: {json.dumps(item.data, ensure_ascii=False)[:800]}

Consider multiple perspectives:
  Design: is this consistent with known design patterns?
  Engineering: does this satisfy engineering constraints?
  Behavior: does this match observed user behavior?
  Association: do relation chains support this?

Respond: valid (APPROVE) or escalate (NEEDS MORE REVIEW). Explain."""

    # ── Persistence ──

    def _save(self):
        path = f"{self._persist_dir}/meta_state.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "queue_size": len(self._queue),
                "decisions": [{"id": d.decision_id, "ts": d.timestamp, "item": d.review_item,
                               "verdict": d.verdict, "correct": d.was_correct}
                              for d in self._decisions[-50:]],
            }, f, ensure_ascii=False, indent=2)

    def _load(self):
        path = f"{self._persist_dir}/meta_state.json"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("decisions", []):
                self._decisions.append(MetaDecision(
                    decision_id=d["id"], timestamp=d["ts"], review_item=d["item"],
                    verdict=d.get("verdict", "?"), was_correct=d.get("correct"),
                ))

    def stats(self) -> Dict[str, Any]:
        return {
            "queue_size": len(self._queue),
            "pending": sum(1 for i in self._queue if i.verdict is None),
            "reviewed": sum(1 for i in self._queue if i.verdict is not None),
            "decisions_total": len(self._decisions),
            "self_audit": self.self_audit(),
        }
