"""StateMachine handler registration — maps PipelinePhase to engine methods.

Each handler: real engine call + trace recording + error isolation.
Replaces the scattered serial calls in v3_session_api with unified state machine.
"""
import time, json, logging

logger = logging.getLogger(__name__)


def register_all_handlers(engine, tracer=None):
    """Register all 12 pipeline phase handlers.

    Each handler returns a result dict that feeds into the next phase.
    """
    from core.agent.event.statemachine import DeciderStateMachine, PipelinePhase
    sm = getattr(engine, '_state_machine', None)
    if not sm:
        sm = DeciderStateMachine()
        engine._state_machine = sm

    def _trace(name: str, fn, *args):
        """Wrap a handler with trace recording."""
        start = time.time()
        try:
            result = fn(*args)
            latency = (time.time() - start) * 1000
            if tracer:
                tracer.record(name, "phase_complete", True, latency)
            return result if result is not None else {}
        except Exception as e:
            latency = (time.time() - start) * 1000
            if tracer:
                tracer.record(name, "phase_error", False, latency, {"error": str(e)[:100]})
            logger.debug("Phase %s failed: %s", name, e)
            return {"error": str(e)[:200]}

    # ── PCR — Pre-Cognitive Router ──
    def handle_pcr(ctx):
        pcr = getattr(engine, '_pcr_router', None)
        text = ctx.get("text", "")
        if pcr and text and hasattr(pcr, 'route'):
            result = pcr.route(text)
            return {
                "zone": getattr(result, 'zone', 'MIXED'),
                "cognitive_level": getattr(result, 'cognitive_level', 'moderate'),
                "execution_mode": getattr(result, 'execution_mode', 'auto'),
            }
        return {"zone": "MIXED"}
    sm.register_handler(PipelinePhase.PCR, lambda ctx: _trace("pcr", handle_pcr, ctx))

    # ── INTENT — Intent Parser ──
    def handle_intent(ctx):
        parser = getattr(engine, '_intent_parser', None)
        text = ctx.get("text", "")
        pcr_zone = ctx.get("pcr", {}).get("zone", "MIXED")
        if parser and text:
            try:
                result = parser.parse(user_input=text)
                return {
                    "category": str(getattr(getattr(result, 'intent', None), 'category', 'general')),
                    "confidence": getattr(result, 'confidence', 0.5),
                    "segments": getattr(result, 'segments', [text[:50]]),
                }
            except:
                pass
        return {"category": "general", "confidence": 0.5}
    sm.register_handler(PipelinePhase.INTENT, lambda ctx: _trace("intent", handle_intent, ctx))

    # ── DISCOURSE — DiscourseBlockTree feed ──
    def handle_discourse(ctx):
        dt = getattr(engine, '_discourse_tree', None)
        text = ctx.get("text", "")
        reply = ctx.get("reply", "")
        sid = ctx.get("session_id", "default")
        if dt:
            if text: dt.feed(text, sid)
            if reply: dt.feed(reply[:500], sid)
            rel = dt.get_block_relations(sid)
            return {"blocks": len(rel.get("blocks", {})), "relations": len(rel.get("relations", []))}
        return {"blocks": 0}
    sm.register_handler(PipelinePhase.DISCOURSE, lambda ctx: _trace("discourse", handle_discourse, ctx))

    # ── BEHAVIOR — BehaviorGraph record ──
    def handle_behavior(ctx):
        bg = getattr(engine, '_behavior_graph', None)
        text = ctx.get("text", "")
        if bg and text:
            try:
                from core.agent.events.event_ir import EventIR
                import uuid, time
                evt = EventIR(
                    id=f"turn_{uuid.uuid4().hex[:8]}",
                    kind="user_message",
                    payload={"text": text[:200], "session_id": ctx.get("session_id", "")},
                    metadata={},
                    timestamp=time.time(),
                )
                # BehaviorGraphAdapter uses record_event (adapter.py:174)
                # CausalPlanner uses record_step (planner.py:180)
                for method in ['record_event', 'record_step']:
                    if hasattr(bg, method):
                        getattr(bg, method)(evt, success=True)
                        if method == 'record_event':
                            return {"recorded": True, "event_id": evt.id}
                        else:
                            buf = getattr(bg, '_step_buffer', [])
                            return {"recorded": True, "edge_count": len(buf), "last_step": evt.id}
                # Fallback
                if hasattr(bg, 'load'):
                    bg.load()
                    chain = bg.get_recent_chain(5) if hasattr(bg, 'get_recent_chain') else []
                    return {"recorded": True, "chain_len": len(chain)}
            except Exception as e:
                logger.debug("Behavior record failed: %s", e)
        return {"recorded": False}
    sm.register_handler(PipelinePhase.BEHAVIOR, lambda ctx: _trace("behavior", handle_behavior, ctx))

    # ── META — MetaCognition review ──
    def handle_meta(ctx):
        mc = getattr(engine, '_meta_cognition', None)
        text = ctx.get("text", "")
        results = {"reviewed": False}
        if mc:
            if hasattr(mc, 'retrospect'):
                try:
                    mc.retrospect(target=ctx.get("intent", {}).get("category", "general"))
                    results["reviewed"] = True
                except:
                    pass
            if hasattr(mc, 'scan'):
                try:
                    mc.scan(engine)  # scan requires engine parameter
                    results["scanned"] = True
                except:
                    pass
            # Extract visible stats
            stats = getattr(mc, 'stats', None)
            if stats:
                if callable(stats):
                    try: results.update(stats())
                    except: pass
                elif isinstance(stats, dict):
                    results.update({k: v for k, v in stats.items() if isinstance(v, (str, int, float, bool))})
            elif hasattr(mc, 'get_stats'):
                try: results.update(mc.get_stats())
                except: pass
            elif hasattr(mc, '_history'):
                results["history_len"] = len(getattr(mc, '_history', []))
            elif hasattr(mc, '_reviews'):
                results["reviews"] = len(getattr(mc, '_reviews', []))
        return results
    sm.register_handler(PipelinePhase.META, lambda ctx: _trace("meta", handle_meta, ctx))

    # ── PROFILE — OCEAN analysis ──
    def handle_profile(ctx):
        ocean = getattr(engine, '_ocean_analyst', None)
        text = ctx.get("text", "")
        reply = ctx.get("reply", "")
        if ocean and text:
            try:
                result = ocean.analyze(engine, text, reply or text)
                dims = getattr(getattr(ocean, 'profile', None), 'dims', {})
                return {"dims_updated": bool(dims), "O": str(dims.get("O", 0.5))[:4]}
            except:
                pass
        return {"dims_updated": False}
    sm.register_handler(PipelinePhase.PROFILE, lambda ctx: _trace("profile", handle_profile, ctx))

    # ── PERSIST — Save to disk ──
    def handle_persist(ctx):
        if hasattr(engine, '_persist_state'):
            try:
                engine._persist_state()
                return {"persisted": True}
            except:
                pass
        return {"persisted": False}
    sm.register_handler(PipelinePhase.PERSIST, lambda ctx: _trace("persist", handle_persist, ctx))

    # ── ASSOCIATION — L1 + L2.5 chain ──
    def handle_association(ctx):
        text = ctx.get("text", "")
        l1 = getattr(engine, '_l1_modifier', None)
        l2 = getattr(engine, '_l2_5_belief', None)
        results = {}
        if l1 and text and hasattr(l1, 'extract'):
            try:
                mods = l1.extract(text)
                results["modifiers"] = len(mods) if mods else 0
            except: pass
        if l2 and text:
            try:
                from core.agent.association.l2_5_belief import Evidence
                ev = Evidence(entity_id=f"msg_{hash(text)%10000}", entity_name=text[:40],
                              relation_type="user_message", confidence=0.5)
                l2.ingest(ev)
                results["belief_updated"] = True
            except: pass
        return results
    sm.register_handler(PipelinePhase.ASSOCIATION, lambda ctx: _trace("association", handle_association, ctx))

    # Register ASSOCIATION in state transitions if not present
    from core.agent.event.statemachine import STATE_TRANSITIONS
    if PipelinePhase.ASSOCIATION not in STATE_TRANSITIONS.get(PipelinePhase.META, {}):
        STATE_TRANSITIONS.setdefault(PipelinePhase.META, {})["normal"] = PipelinePhase.ASSOCIATION
        STATE_TRANSITIONS.setdefault(PipelinePhase.ASSOCIATION, {})["normal"] = PipelinePhase.PROFILE

    engine._state_machine = sm
    return {"handlers": len(sm._phase_handlers), "phases": [p.value for p in sm._phase_handlers.keys()]}
