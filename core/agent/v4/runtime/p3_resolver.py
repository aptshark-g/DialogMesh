"""P3 Resolver — wire v3_2 legacy modules (via v4 wrappers) into engine + monitoring.

Correct method names:
  TieredRuleEngine.evaluate(text) → (ok, conf, warnings)
  TieredNegativeKB.check(ctx) → NegativeResult
  TieredFusionEngine.fuse(track0,track1,track_p,causal) → FusionResult
  TieredCognitiveCompiler.process(sentence,context) → ParseResult

Monitoring: every P3 call logged to InternalStateMonitor.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class P3Resolver:
    @staticmethod
    def wire(engine) -> dict:
        status = {}
        # 1. TieredRuleEngine
        try:
            from core.agent.v4.tiered.rule_engine import TieredRuleEngine
            engine._rule_engine = TieredRuleEngine(llm_provider=getattr(engine, '_llm_provider', None))
            status["rule_engine"] = "ok"
            logger.info("P3: TieredRuleEngine")
        except Exception as e:
            engine._rule_engine = None; status["rule_engine"] = str(e)

        # 2. TieredNegativeKB
        try:
            from core.agent.v4.tiered.negative_kb import TieredNegativeKB
            engine._negative_kb = TieredNegativeKB()
            status["negative_kb"] = "ok"
            logger.info("P3: TieredNegativeKB")
        except Exception as e:
            engine._negative_kb = None; status["negative_kb"] = str(e)

        # 3. TieredFusionEngine
        try:
            from core.agent.v4.tiered.fusion import TieredFusionEngine
            engine._tiered_fusion = TieredFusionEngine()
            status["tiered_fusion"] = "ok"
            logger.info("P3: TieredFusionEngine")
        except Exception as e:
            engine._tiered_fusion = None; status["tiered_fusion"] = str(e)

        # 4. TieredCognitiveCompiler
        try:
            from core.agent.v4.tiered.cognitive_compiler import TieredCognitiveCompiler
            engine._cognitive_compiler = TieredCognitiveCompiler(llm_provider=getattr(engine, '_llm_provider', None))
            status["cognitive_compiler"] = "ok"
            logger.info("P3: TieredCognitiveCompiler")
        except Exception as e:
            engine._cognitive_compiler = None; status["cognitive_compiler"] = str(e)

        return status

    @staticmethod
    def inject_in_context(engine, event) -> dict:
        """Call P3 modules during context compilation. Returns monitor events."""
        events = {}
        if not engine._last_context:
            return events

        # RuleEngine: evaluate text for conflicts
        if hasattr(engine, '_rule_engine') and engine._rule_engine:
            try:
                ok, conf, warnings = engine._rule_engine.evaluate(getattr(event, 'text', ''))
                events["rule_engine"] = {"ok": ok, "conf": conf, "warnings": str(warnings)[:100]}
                if warnings:
                    from core.agent.v4.context.cross_domain_ir import IREntry
                    for w in (warnings if isinstance(warnings, list) else [str(warnings)])[:2]:
                        engine._last_context.add_entry(domain="W", entry=IREntry(
                            domain="W", type="rule_warning",
                            content=f"[WARN:v3] {w}"[:200], confidence=0.5))
            except Exception as e:
                events["rule_engine"] = {"error": str(e)[:100]}

        # NegativeKB: check for bad patterns
        if hasattr(engine, '_negative_kb') and engine._negative_kb:
            try:
                result = engine._negative_kb.check(getattr(event, 'text', ''))
                events["negative_kb"] = {"triggered": result.triggered if hasattr(result, 'triggered') else False}
                if hasattr(result, 'triggered') and result.triggered:
                    from core.agent.v4.context.cross_domain_ir import IREntry
                    engine._last_context.add_entry(domain="W", entry=IREntry(
                        domain="W", type="negative_pattern",
                        content=f"[AVOID:v3] {getattr(result,'reason','unknown')}"[:200], confidence=0.4))
            except Exception as e:
                events["negative_kb"] = {"error": str(e)[:100]}

        # TieredFusion: fuse context (light: only when both track0 and track_p present)
        if hasattr(engine, '_tiered_fusion') and engine._tiered_fusion:
            try:
                track_p = getattr(getattr(engine, '_cognitive_profile', None), 'track_a', None)
                if track_p:
                    result = engine._tiered_fusion.fuse(track_p=track_p)
                    events["tiered_fusion"] = {"fused": True} if result else {"fused": False}
            except Exception as e:
                events["tiered_fusion"] = {"error": str(e)[:100]}

        # CognitiveCompiler: process sentence for structured parsing
        if hasattr(engine, '_cognitive_compiler') and engine._cognitive_compiler:
            try:
                result = engine._cognitive_compiler.process(getattr(event, 'text', ''))
                events["cognitive_compiler"] = {"ok": getattr(result, 'ok', True)}
            except Exception as e:
                events["cognitive_compiler"] = {"error": str(e)[:100]}

        # Monitor: record P3 events
        if engine._monitor and events:
            engine._monitor.record("p3_legacy", events)

        return events
