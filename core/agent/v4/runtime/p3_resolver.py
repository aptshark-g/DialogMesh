"""P3 Resolver — wire v3_2 legacy modules (via v4 wrappers) into engine.

Modules:
  tiered/rule_engine.py      → RuleEngine → conflict resolution in context
  tiered/fusion.py           → TieredFusion → multi-source fusion
  tiered/cognitive_compiler.py → CognitiveCompiler → fallback compilation
  tiered/negative_kb.py      → NegativeKB → pattern filtering

Strategy: light wire — each module called at most once per turn.
All v3_2 code reaches through existing v4 tiered/ wrappers.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class P3Resolver:
    """Wire P3 v3 legacy modules into engine."""

    @staticmethod
    def wire(engine) -> dict:
        status = {}
        # 1. RuleEngine — conflict resolution
        try:
            from core.agent.v4.tiered.rule_engine import TieredRuleEngine
            engine._rule_engine = TieredRuleEngine(llm_provider=getattr(engine, '_llm_provider', None))
            status["rule_engine"] = "wired"
            logger.info("P3: TieredRuleEngine wired")
        except Exception as e:
            engine._rule_engine = None
            status["rule_engine"] = f"skipped: {e}"

        # 2. NegativeKB — bad pattern knowledge
        try:
            from core.agent.v4.tiered.negative_kb import TieredNegativeKB
            engine._negative_kb = TieredNegativeKB()
            status["negative_kb"] = "wired"
            logger.info("P3: TieredNegativeKB wired")
        except Exception as e:
            engine._negative_kb = None
            status["negative_kb"] = f"skipped: {e}"

        # 3. TieredFusion — already partially integrated
        try:
            from core.agent.v4.tiered.fusion import TieredFusionEngine
            engine._tiered_fusion = TieredFusionEngine()
            status["tiered_fusion"] = "wired"
            logger.info("P3: TieredFusionEngine wired")
        except Exception as e:
            engine._tiered_fusion = None
            status["tiered_fusion"] = f"skipped: {e}"

        # 4. CognitiveCompiler — fallback compilation
        try:
            from core.agent.v4.tiered.cognitive_compiler import TieredCognitiveCompiler
            engine._cognitive_compiler = TieredCognitiveCompiler(llm_provider=getattr(engine, '_llm_provider', None))
            status["cognitive_compiler"] = "wired"
            logger.info("P3: TieredCognitiveCompiler wired")
        except Exception as e:
            engine._cognitive_compiler = None
            status["cognitive_compiler"] = f"skipped: {e}"

        return status

    @staticmethod
    def inject_in_context(engine, event) -> None:
        """Call P3 modules during context compilation (safe, fire-and-forget)."""
        if not engine._last_context:
            return

        # RuleEngine: check for conflicts
        if hasattr(engine, '_rule_engine') and engine._rule_engine:
            try:
                from core.agent.v4.context.cross_domain_ir import IREntry
                warnings = engine._rule_engine.check(getattr(event, 'text', ''))
                if warnings:
                    for w in warnings[:3]:
                        engine._last_context.add_entry(domain="W", entry=IREntry(
                            domain="W", type="rule_warning",
                            content=f"[WARN] {w}"[:200], confidence=0.5))
            except Exception:
                pass

        # NegativeKB: filter bad patterns
        if hasattr(engine, '_negative_kb') and engine._negative_kb:
            try:
                from core.agent.v4.context.cross_domain_ir import IREntry
                patterns = engine._negative_kb.query(getattr(event, 'text', ''))
                if patterns:
                    for p in patterns[:2]:
                        engine._last_context.add_entry(domain="W", entry=IREntry(
                            domain="W", type="negative_pattern",
                            content=f"[AVOID] {p}"[:200], confidence=0.4))
            except Exception:
                pass
