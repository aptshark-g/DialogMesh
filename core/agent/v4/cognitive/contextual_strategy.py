"""ContextualStrategy — Mind learns WHICH strategy works in WHICH context.

Upgrades Mind from EMA (经验统计) to Context-Aware Learning:
  Before: "Strategy A有效, 用了45次"
  After:  "Strategy A在Architecture+Depth=3+Runtime问题下效果0.94,
           但在Engineering+UI下效果0.52"
"""
from __future__ import annotations
import hashlib, time, json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════ StrategyContext ═══════════════════════

@dataclass
class StrategyContext:
    """The specific context in which a strategy was applied."""
    perspective: str = ""          # architecture/engineering/evolution/execution
    depth: int = 1                 # reasoning depth (1-5)
    domain: str = ""               # problem domain (Runtime/Scheduler/UI/...)
    time_of_day: str = ""          # morning/afternoon/evening
    discussion_mode: str = ""      # continuous/topic_switch/correction/new_topic
    user_state: str = ""           # user cognitive state summary
    turn_number: int = 0           # conversation progress

    def hash(self) -> str:
        """Deterministic context hash for grouping."""
        key = f"{self.perspective}|{self.depth}|{self.domain}|{self.discussion_mode}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    @classmethod
    def from_engine(cls, engine) -> "StrategyContext":
        """Extract context from current engine state."""
        perspective = "architecture"
        if hasattr(engine, '_last_perspective'):
            perspective = engine._last_perspective or perspective

        domain = ""
        if hasattr(engine, '_conversation_tracker'):
            topic = engine._conversation_tracker.get_current_topic()
            domain = topic or ""

        discussion_mode = "new_topic"
        if hasattr(engine, '_conversation_tracker'):
            patterns = engine._conversation_tracker.behavior_pattern
            if "drill_down" in patterns:
                discussion_mode = "continuous"
            elif "topic_switch" in patterns:
                discussion_mode = "topic_switch"

        return cls(
            perspective=perspective,
            depth=min(5, engine._turn_counter // 2 + 1),
            domain=domain,
            discussion_mode=discussion_mode,
            turn_number=engine._turn_counter,
        )


# ═══════════════════════ StrategyRecord ═══════════════════════

@dataclass
class StrategyRecord:
    """How effective a strategy is in a specific context."""
    effectiveness: float = 0.5     # 0-1
    uses: int = 0
    last_used: float = 0.0
    avg_confidence_gain: float = 0.0  # average confidence delta when used

    def update(self, result: float, confidence_delta: float = 0):
        """EMA update with new result."""
        alpha = 0.15 if self.uses < 5 else 0.05  # Fast initial, slow later
        self.effectiveness = (1 - alpha) * self.effectiveness + alpha * result
        self.uses += 1
        self.last_used = time.time()
        self.avg_confidence_gain = (
            0.9 * self.avg_confidence_gain + 0.1 * confidence_delta
        )


# ═══════════════════════ ContextualStrategyEngine ═══════════════════════

class ContextualStrategyEngine:
    """Learns strategy effectiveness per context.

    Usage:
        engine = ContextualStrategyEngine()
        # When a strategy is applied:
        ctx = StrategyContext(perspective="architecture", depth=3, domain="Runtime")
        engine.record("explain_via_relation", ctx, effectiveness=0.88, confidence_gain=0.12)
        # Later, to choose strategy:
        best = engine.best_for(ctx)  # → ("explain_via_relation", 0.88)
    """

    def __init__(self):
        self._strategies: Dict[str, Dict[str, StrategyRecord]] = {}
        # strategy_name → {context_hash → StrategyRecord}

    def record(
        self,
        strategy_name: str,
        context: StrategyContext,
        effectiveness: float,
        confidence_gain: float = 0.0,
    ):
        """Record a strategy's effectiveness in a specific context."""
        ctx_hash = context.hash()
        if strategy_name not in self._strategies:
            self._strategies[strategy_name] = {}

        records = self._strategies[strategy_name]
        if ctx_hash not in records:
            records[ctx_hash] = StrategyRecord()
        records[ctx_hash].update(effectiveness, confidence_gain)

    def best_for(self, context: StrategyContext) -> Tuple[Optional[str], float]:
        """Find the best strategy for the given context.

        First: exact context hash match
        Second: similar context match (same perspective + domain)
        Third: global best strategy
        """
        ctx_hash = context.hash()
        best_name, best_score = None, 0.0

        # 1. Exact match
        for name, records in self._strategies.items():
            if ctx_hash in records and records[ctx_hash].uses >= 3:
                eff = records[ctx_hash].effectiveness
                if eff > best_score:
                    best_name, best_score = name, eff
        if best_name:
            return best_name, best_score

        # 2. Similar context (same perspective + domain)
        for name, records in self._strategies.items():
            for ch, rec in records.items():
                # Check if context is similar enough
                if self._context_similar(context, ch) and rec.uses >= 2:
                    if rec.effectiveness > best_score:
                        best_name, best_score = name, rec.effectiveness
        if best_name:
            return best_name, best_score

        # 3. Global best
        for name, records in self._strategies.items():
            avg = sum(r.effectiveness for r in records.values()) / max(1, len(records))
            if avg > best_score:
                best_name, best_score = name, avg
        return best_name, best_score

    def _context_similar(self, ctx: StrategyContext, ctx_hash: str) -> bool:
        """Check if a stored context hash is similar to current context."""
        # Loose match: same perspective + domain prefix
        perspective = ctx.perspective
        domain = ctx.domain[:10] if len(ctx.domain) > 10 else ctx.domain
        return perspective in ctx_hash or domain in ctx_hash

    def stats(self) -> Dict[str, Any]:
        """Summary statistics."""
        total_strategies = len(self._strategies)
        total_contexts = sum(len(r) for r in self._strategies.values())
        total_uses = sum(
            sum(rec.uses for rec in records.values())
            for records in self._strategies.values()
        )
        return {
            "total_strategies": total_strategies,
            "total_contexts": total_contexts,
            "total_uses": total_uses,
        }

    def export(self) -> Dict[str, Any]:
        """Export for persistence."""
        data = {}
        for name, records in self._strategies.items():
            data[name] = {
                ch: {
                    "effectiveness": rec.effectiveness,
                    "uses": rec.uses,
                    "last_used": rec.last_used,
                    "avg_confidence_gain": rec.avg_confidence_gain,
                }
                for ch, rec in records.items()
            }
        return data
