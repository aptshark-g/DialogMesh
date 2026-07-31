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
    import os as _os

    def _persist_disk_file(path: str, data: dict):
        """Append data to a disk file (list of entries). Persist data dir from project root."""
        import json as _json
        root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
        fpath = _os.path.join(root, path)
        _os.makedirs(_os.path.dirname(fpath), exist_ok=True)
        existing = []
        if _os.path.exists(fpath):
            try:
                with open(fpath, encoding='utf-8') as f:
                    existing = _json.load(f)
                    if not isinstance(existing, list):
                        existing = [existing]
            except: pass
        existing.append(data)
        # Keep last 50 entries
        trimmed = existing[-50:]
        with open(fpath, 'w', encoding='utf-8') as f:
            _json.dump(trimmed, f, indent=2, ensure_ascii=False)
        # Auto-populate HotStore cache
        _cache_hot(path, trimmed)

    def _cache_hot(rel_path: str, data):
        """Write to HotStore memory cache so CLI _disk() hits immediately."""
        try:
            store = getattr(engine, '_storage', None)
            if store and hasattr(store, 'hot'):
                store.hot.set(f"disk:{rel_path}", data)
        except:
            pass
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
            # Always store PCR zone info even if route returns None
            engine._last_pcr = result if result is not None else {"zone": "MIXED", "source": "mock"}
            return {
                "zone": getattr(result, 'zone', 'MIXED'),
                "cognitive_level": getattr(result, 'cognitive_level', 'moderate'),
                "execution_mode": getattr(result, 'execution_mode', 'auto'),
            }
        # No router — record fallback so downstream can observe
        engine._last_pcr = {"zone": "MIXED", "source": "fallback"}
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
                engine._last_intent = result if result is not None else {"intent": "general", "confidence": 0.5, "source": "mock"}
                return {
                    "category": str(getattr(getattr(result, 'intent', None), 'category', 'general')),
                    "confidence": getattr(result, 'confidence', 0.5),
                    "segments": getattr(result, 'segments', [text[:50]]),
                }
            except:
                pass
        # Fallback for no parser (mock mode)
        engine._last_intent = {"intent": "general", "confidence": 0.5, "source": "fallback"}
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
            # ── Coverage gap: TopicTree.touch ──
            tt = getattr(engine, '_topic_tree', None)
            if tt and text:
                import re as _re2
                entities = _re2.findall(r'[A-Z]{2,}', text)
                tt.touch(message_id=f"msg_{int(time.time()*1000)}", content=text, entities=entities)
            if reply: dt.feed(reply[:500], sid)
            rel = dt.get_block_relations(sid)
            return {"blocks": len(rel.get("blocks", {})), "relations": len(rel.get("relations", []))}
        return {"blocks": 0}
    sm.register_handler(PipelinePhase.DISCOURSE, lambda ctx: _trace("discourse", handle_discourse, ctx))

    # ── BEHAVIOR — BehaviorGraph record ──
    def handle_behavior(ctx):
        bg = getattr(engine, '_behavior_graph_adapter', None) or getattr(engine, '_behavior_graph', None)
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
                logger.debug("Behavior handler failed: %s", e)
        # ── Coverage gap: _feed_trackb ──
        if text and hasattr(engine, '_feed_trackb'):
            try:
                engine._feed_trackb(text)
            except:
                pass
        return {"recorded": False, "msg": "behavior skipped" if not text else "no graph"}
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
        results = {"persisted": False, "trace": False}
        # Save engine state
        if hasattr(engine, '_persist_state'):
            try:
                engine._persist_state()
                results["persisted"] = True
            except:
                pass
        # Save trace from pipeline results
        tracer = getattr(engine, '_tracer', None)
        if tracer and ctx:
            try:
                tracer.record("pipeline", "complete", True, 0, {"phases": str(ctx)[:200]})
                results["trace"] = True
            except:
                pass
        # Persist annotations from meta feedback
        mc = getattr(engine, '_meta_cognition', None)
        if mc and hasattr(mc, 'self_audit'):
            try:
                audit = mc.self_audit()
                if audit:
                    _persist_disk_file("data/annotations.json", {"audit": str(audit)[:500], "ts": time.time()})
                    results["annotations"] = True
            except:
                pass
        # Persist corrections from behavior
        bg = getattr(engine, '_behavior_graph_adapter', None)
        if bg and hasattr(bg, 'stats'):
            try:
                s = bg.stats()
                _persist_disk_file("data/corrections.json", {"stats": s, "ts": time.time()})
                results["corrections"] = True
            except:
                pass
        # Persist feedback from pipeline errors
        errors = {k: v for k, v in ctx.items() if 'error' in str(k).lower() or 'error' in str(v).lower()}
        if errors:
            _persist_disk_file("data/feedback.json", {"errors": errors, "ts": time.time()})
            results["feedback"] = True
        return results
    sm.register_handler(PipelinePhase.PERSIST, lambda ctx: _trace("persist", handle_persist, ctx))

    # ── ASSOCIATION — Phase 2: Pre-processor (resolve → qualify) ──
    def handle_association(ctx):
        """Pre-processor: pronoun resolution + context qualification before chunking.
        
        Pipeline: raw → resolve() → enriched → qualify() → text forwarded to Discourse.
        """
        text = ctx.get("text", "")
        if not text:
            return {}
        
        resolver = getattr(engine, '_pronoun_resolver', None)
        qualifier = getattr(engine, '_context_qualifier', None)
        results = {}
        
        # Step 1: Resolve pronouns
        if resolver and text:
            entities = engine._extract_concepts_from_text(text) if hasattr(engine, '_extract_concepts_from_text') else []
            enriched = resolver.resolve(text, entities)
            ctx["enriched_text"] = enriched
            results["pronouns_resolved"] = enriched != text
            results["entities_tracked"] = len(resolver.recent_entities)
        
        # Step 2: Qualify with dependencies
        if qualifier and resolver:
            enriched_text = ctx.get("enriched_text", text)
            recent_ents = resolver.recent_entities if resolver else []
            qualified = qualifier.qualify(enriched_text, recent_ents)
            ctx["qualified_text"] = qualified
            results["deps_injected"] = qualified != enriched_text
        
        return results
    sm.register_handler(PipelinePhase.ASSOCIATION, lambda ctx: _trace("association", handle_association, ctx))
    # Register ASSOCIATION in state transitions if not present
    from core.agent.event.statemachine import STATE_TRANSITIONS
    if PipelinePhase.ASSOCIATION not in STATE_TRANSITIONS.get(PipelinePhase.META, {}):
        STATE_TRANSITIONS.setdefault(PipelinePhase.META, {})["normal"] = PipelinePhase.ASSOCIATION
        STATE_TRANSITIONS.setdefault(PipelinePhase.ASSOCIATION, {})["normal"] = PipelinePhase.PROFILE

    engine._state_machine = sm
    return {"handlers": len(sm._phase_handlers), "phases": [p.value for p in sm._phase_handlers.keys()]}
