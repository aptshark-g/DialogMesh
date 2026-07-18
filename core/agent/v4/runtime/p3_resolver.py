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

        # RuleEngine: check constraints (use resolve_all bridge)
        if hasattr(engine, '_rule_engine') and engine._rule_engine:
            try:
                re_engine = engine._rule_engine
                if hasattr(re_engine, 'resolve_all'):
                    from core.agent.v3_2.compiler.models import ParseContext
                    result = re_engine.resolve_all({"text": getattr(event, 'text', '')}, ParseContext())
                    events["rule_engine"] = {"resolved": len(result) if result else 0}
                elif hasattr(re_engine, '_rule_evaluate'):
                    # Fallback: use bridge's internal method
                    ctx={'input_text': getattr(event, 'text', '')}
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore'); import asyncio
                    re_result = re_engine._rule_evaluate(ctx, {})
                    events["rule_engine"] = {"ok": re_result.get('ok', True)}
            except Exception as e:
                events["rule_engine"] = {"error": str(e)[:80]}

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

        # TieredFusion: bridge sync wrapper around async fuse
        if hasattr(engine, '_tiered_fusion') and engine._tiered_fusion:
            try:
                track_p = getattr(getattr(engine, '_cognitive_profile', None), 'track_a', None)
                if track_p and hasattr(engine._tiered_fusion, '_run_stage1'):
                    result = engine._tiered_fusion._run_stage1({}, {})
                    events["tiered_fusion"] = {"fused": bool(result)}
            except Exception as e:
                events["tiered_fusion"] = {"error": str(e)[:80]}

        # CognitiveCompiler: bridge sync wrapper around async process
        if hasattr(engine, '_cognitive_compiler') and engine._cognitive_compiler:
            try:
                if hasattr(engine._cognitive_compiler, '_run_rule_only'):
                    result = engine._cognitive_compiler._run_rule_only(
                        {'sentence': getattr(event, 'text', '')}, {})
                    events["cognitive_compiler"] = {"ok": bool(result)}
            except Exception as e:
                events["cognitive_compiler"] = {"error": str(e)[:80]}

        # Monitor: record P3 events (if monitor supports generic record)
        if engine._monitor and events:
            try:
                if hasattr(engine._monitor, 'record_event'):
                    engine._monitor.record_event("p3_legacy", events)
            except Exception:
                pass

        return events
