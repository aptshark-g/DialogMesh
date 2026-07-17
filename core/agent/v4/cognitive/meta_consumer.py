"""MetaConsumer — closes the learning loop by consuming ExecutionTraceV3 analysis.

Every N transitions, meta_analyze() the trace and:
  1. Detect unhealthy patterns (consecutive rejects, no evidence)
  2. Adjust strategy weights based on what worked
  3. Feed patterns into ContextualStrategy for long-term learning
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetaConsumer:
    """Consumes ExecutionTraceV3.meta_analyze() output to adjust behavior.

    Usage:
        consumer = MetaConsumer(strategy_engine)
        # After every 10 transitions:
        advice = consumer.consume(trace_v3)
        if advice["adjust"]:
            # e.g., lower confidence, gather more evidence, switch strategy
    """

    def __init__(self, strategy_engine=None):
        self._strategy_engine = strategy_engine
        self._consecutive_cycles = 0
        self._last_advice = {}

    def consume(self, trace, turn_count: int) -> Dict[str, Any]:
        """Analyze trace and return actionable advice.

        Returns dict with:
          adjust: bool          — should we change behavior?
          warnings: List[str]   — what's wrong
          suggestions: List[str] — what to do differently
          confidence_mod: float — suggested confidence adjustment
        """
        if trace is None:
            return {"adjust": False}

        m = trace.meta_analyze()
        if m.get("empty"):
            return {"adjust": False}

        advice = {"adjust": False, "warnings": [], "suggestions": [], "confidence_mod": 0.0}
        reason_dist = m.get("reason_distribution", {})

        # ── Pattern 1: Total rejects (not just consecutive) ──
        total_rejects = reason_dist.get("reject", 0)
        if total_rejects >= 2:
            advice["warnings"].append(f"共 {total_rejects} 次 REJECT——用户反复纠正")
            advice["suggestions"].append("回溯到 REJECT 前的状态, 尝试替代假设")
            advice["confidence_mod"] -= 0.15
            advice["adjust"] = True

        # ── Pattern 2: No OBSERVE, only INFER ──
        observe_count = reason_dist.get("observe", 0)
        infer_count = reason_dist.get("infer", 0)
        if observe_count == 0 and infer_count > 5:
            advice["warnings"].append("无 OBSERVE 转换——推理缺乏外部证据")
            advice["suggestions"].append("在下一轮强制检索更多 SemanticObject")
            advice["adjust"] = True

        # ── Pattern 3: Low confidence trend ──
        avg_conf = m.get("avg_confidence", 0.5)
        if avg_conf < 0.4 and turn_count > 5:
            advice["warnings"].append(f"平均置信度 {avg_conf:.2f} 过低")
            advice["suggestions"].append("降低回答的断言性, 标记为'低置信'")
            advice["confidence_mod"] -= 0.1
            advice["adjust"] = True

        # ── Pattern 4: Too many INFER without REFLECT ──
        reflect_count = reason_dist.get("reflect", 0)
        if infer_count > 8 and reflect_count < 2:
            advice["warnings"].append("大量推理但缺少反思— 可能过热")
            advice["suggestions"].append("强制插入反思步骤")
            advice["adjust"] = True

        # Pattern 5: Rapid topic switching (many WEAKEN)
        weaken_count = reason_dist.get("weaken", 0)
        if weaken_count >= 2:
            advice["warnings"].append(f"连续 {weaken_count} 次 WEAKEN——话题切换或观点冲突")
            advice["suggestions"].append("稳定当前视角")
            advice["confidence_mod"] -= 0.1
            advice["adjust"] = True

        # ── Feed patterns to ContextualStrategy ──
        if advice["adjust"] and self._strategy_engine:
            from core.agent.v4.cognitive.contextual_strategy import StrategyContext
            ctx = StrategyContext(
                discussion_mode="continuous" if turn_count > 5 else "new_topic",
                turn_number=turn_count,
            )
            strategy_score = max(0.3, 0.7 - len(advice["warnings"]) * 0.1)
            self._strategy_engine.record(
                "meta_adaptation",
                ctx,
                effectiveness=strategy_score,
                confidence_gain=advice["confidence_mod"],
            )

        self._last_advice = advice
        self._consecutive_cycles += 1

        if advice["adjust"]:
            logger.info(
                "MetaConsumer: %d warnings → conf_mod=%.2f",
                len(advice["warnings"]), advice["confidence_mod"],
            )

        return advice
