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
    # G1+G3-P5: 复用 registry 的 GlobalDecider 实例注入 StateMachine
    # （防广播风暴 + 状态底座；不暴露新决策器, 不改变路由）
    if getattr(sm, '_decider', None) is None:
        sm._decider = getattr(engine, '_decider', None)

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
            # P6 画像→PCR: OCEAN 偏置作为 subgraph_prior（DESIGN_PCR §5 用户偏置层）
            prior = engine._profile_prior_text() if hasattr(engine, '_profile_prior_text') else None
            try:
                result = pcr.route(text, subgraph_prior=prior)
            except TypeError:
                # 旧签名 route(text, history=None) 兜底
                result = pcr.route(text)
            # Always store PCR zone info even if route returns None
            engine._last_pcr = result if result is not None else {"zone": "MIXED", "source": "mock"}
            # P6 PCR→TrackA: 坐标/认知等级 EMA 进认知状态层（冷路径，不阻塞）
            if result is not None and hasattr(engine, '_update_profile_from_pcr'):
                try:
                    engine._update_profile_from_pcr(result)
                except Exception as e:
                    logger.debug("PCR→TrackA feed failed: %s", e)
            return {
                "zone": getattr(result, 'zone', 'MIXED'),
                "cognitive_level": getattr(result, 'cognitive_level', 'moderate'),
                "execution_mode": getattr(result, 'execution_mode', 'auto'),
                "x": getattr(result, 'x_axis', 0.5),
                "y": getattr(result, 'y_axis', 0.5),
                "z": getattr(result, 'z_axis', 0.0),
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
        if parser is None:
            # I3 (R3): 懒初始化 Agent-Native 意图管线（T1 热路径）。
            # 无 LLM 时 pipeline 内部显式降级（trace.degraded），不静默跳过。
            init = getattr(engine, "_init_intent_runtime", None)
            if init is not None:
                init()
            parser = getattr(engine, '_intent_parser', None)
        # 新包 pipeline: process(text) → PipelineResult(is_multi/segments/confidence/source)
        if parser is not None and hasattr(parser, "process") and text:
            try:
                from core.agent.intent.dual_track import PipelineResult
                result = parser.process(text)
                segments = list(result.segments) or [text[:50]]
                category = "multi" if result.is_multi else "general"
                payload = {
                    "intent": {"category": category},
                    "confidence": float(result.confidence),
                    "segments": segments,
                    "source": result.source,
                    "is_multi": bool(result.is_multi),
                    "cold_enqueued": bool(result.cold_enqueued),
                }
                engine._last_intent = payload
                engine._last_parse_result = type("ParseResult", (), {
                    "intent": type("Intent", (), {"category": category})(),
                    "confidence": float(result.confidence),
                    "segments": segments,
                })()
                return {
                    "category": category,
                    "confidence": float(result.confidence),
                    "segments": segments,
                    "source": result.source,
                    "is_multi": bool(result.is_multi),
                }
            except Exception as e:
                import logging
                logging.getLogger("dm.handlers").warning(
                    "Intent pipeline degraded: %s (fallback)", e)
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

    # ── PLANNING — Blueprint / plan generation (X3/X8: 补 handler + 懒初始化) ──
    def handle_planning(ctx):
        planner = getattr(engine, '_planner', None)
        if planner is None:
            try:
                from core.agent.planner.llm_planner import LLMPlanner
                planner = LLMPlanner(llm=getattr(engine, '_llm_provider', None))
                engine._planner = planner
            except Exception:
                planner = None
        text = ctx.get("text", "")
        if planner is None or not text:
            return {"plan": [], "source": "no_planner"}
        try:
            plan = planner.plan(text, context={
                "route": ctx.get("pcr", {}),
                "intents": ctx.get("intent", {}),
                "tools": {},
            })
            steps = plan.get("steps", []) if isinstance(plan, dict) else []
            engine._last_plan_result = plan
            return {"plan": steps, "step_count": len(steps),
                    "source": plan.get("source", "llm") if isinstance(plan, dict) else "unknown"}
        except Exception as e:
            return {"plan": [], "error": str(e)[:100]}
    sm.register_handler(PipelinePhase.PLANNING, lambda ctx: _trace("planning", handle_planning, ctx))

    # ── CONTEXT — Context assembly + subgraph (X3/X7: 接真实 IR, 不再幽灵调用) ──
    def handle_context(ctx):
        lc = getattr(engine, '_last_context', None)
        text = ctx.get("text", "")
        if lc is None:
            try:
                from core.agent.context.cross_domain_ir import (
                    CrossDomainContextIR, IntentCategory,
                )
                lc = CrossDomainContextIR(intent_category=IntentCategory.CASUAL)
                engine._last_context = lc
            except Exception:
                lc = None
        if lc is not None and text:
            try:
                from core.agent.context.cross_domain_ir import IREntry
                if not any(e.domain == "D" and
                           str(getattr(e, "content", ""))[:50] == text[:50]
                           for e in lc.entries):
                    lc.add_entry(domain="D", entry=IREntry(
                        domain="D", type="user_input",
                        content=text[:500], confidence=0.8))
            except Exception:
                pass
        # P8: P 域画像源注册 — 统一子图 P/F 域与 ContextCompiler 路径
        try:
            ps = getattr(engine, '_profile_source', None)
            if ps is not None and lc is not None:
                items = ps.retrieve(text, top_k=3)
                from core.agent.context.cross_domain_ir import IREntry
                for item in items:
                    txt = item.text if hasattr(item, 'text') else str(item)
                    if not any(e.domain == "P" for e in lc.entries):
                        lc.add_entry(domain="P", entry=IREntry(
                            domain="P", type="profile",
                            content=txt[:500], confidence=0.9))
        except Exception:
            pass
        # P1/P3 resolver 注入（白盒 IR 增强, 失败不阻塞）
        try:
            from core.agent.runtime.p1_resolver import P1Resolver
            from core.agent.runtime.p3_resolver import P3Resolver
            if lc is not None:
                evt = ctx.get("event")
                P1Resolver.inject_in_context(engine, evt)
                P3Resolver.inject_in_context(engine, evt)
        except Exception:
            pass
        entries = getattr(lc, "entries", []) if lc else []
        return {"ir_entries": len(entries),
                "domains": sorted(set(e.domain for e in entries)) if entries else []}
    sm.register_handler(PipelinePhase.CONTEXT, lambda ctx: _trace("context", handle_context, ctx))

    # ── LLM — LLM generation (X3: 补 handler + X4 回复传递) ──
    def handle_llm(ctx):
        llm = getattr(engine, '_llm_provider', None)
        text = ctx.get("text", "")
        if not text:
            return {"reply": "", "skipped": "no text"}
        # 无 LLM → 模板降级（mock 模式, A16 快速通道）
        if llm is None:
            engine._last_llm_response = f"[mock] {text[:80]}"
            return {"reply": engine._last_llm_response, "source": "mock"}
        try:
            from core.agent.llm_providers.base import GenerateRequest
            zone = ctx.get("pcr", {}).get("zone", "MIXED")
            intent_cat = ctx.get("intent", {}).get("category", "general")
            ir_count = ctx.get("context", {}).get("ir_entries", 0)
            prompt = (f"用户: {text}\n"
                      f"[zone={zone}, intent={intent_cat}, ir_entries={ir_count}]\n"
                      f"请回答准确简洁，通常 100-300 字，除非用户明确要求详细。\n"
                      f"回复:")
            # A18/PCR: 复杂度主动档位映射 max_tokens 保险丝
            # （简单问题不多花，复杂问题不截断）。
            # 长度本身由 prompt 软约束控制；这里只决定
            # 可用上限。thinking 模型会先烧 reasoning token，
            # 低限会空回复，所以保险丝下限 4096。
            _mode = str(zone).upper()
            _level = str(intent_cat).lower()
            if _mode in ("ABYSS", "DEEP") or _level in ("deep", "abyss"):
                _budget = 16384
            elif _mode in ("PRECISION", "SLOW") or _level in ("expert", "complex"):
                _budget = 8192
            else:
                _budget = 4096  # cache/fast/ATOMIC/LIGHT/general ? 保险丝下限
            result = llm.generate(GenerateRequest(
                prompt=prompt, max_tokens=_budget, temperature=0.5))
            reply = result.text if hasattr(result, 'text') else str(result)
            engine._last_llm_response = reply
            return {"reply": reply, "source": "llm"}
        except Exception as e:
            engine._last_llm_response = ""
            return {"reply": "", "error": str(e)[:100]}
    sm.register_handler(PipelinePhase.LLM, lambda ctx: _trace("llm", handle_llm, ctx))

    # ── DISCOURSE — DiscourseBlockTree feed ──
    def handle_discourse(ctx):
        dt = getattr(engine, '_discourse_tree', None)
        text = ctx.get("text", "")
        reply = ctx.get("reply", "")
        sid = ctx.get("session_id", "default")
        if dt:
            # P5: Track A 认知状态 → 组块边界判据（KERNEL §八.8.4）
            cognitive_hints = None
            if hasattr(engine, 'cognitive_state'):
                try:
                    cs = engine.cognitive_state()
                    cognitive_hints = cs if cs.get("available") else None
                except Exception:
                    cognitive_hints = None
            if text:
                try:
                    dt.feed(text, sid, cognitive_hints=cognitive_hints)
                except TypeError:
                    dt.feed(text, sid)
            # TopicTreeV2: route() ??????continue/fork/attach/new??
            # ? touch() ??? ? ?? phase_error???? route?
            tt = getattr(engine, '_topic_tree', None)
            if tt and text and hasattr(tt, "route"):
                import re as _re2
                entities = [{"name": e} for e in _re2.findall(r'[A-Z]{2,}', text)]
                try:
                    decision = tt.route(
                        query=text,
                        turn_index=getattr(engine, "_turn_counter", 0),
                        extracted_entities=entities,
                        query_intent="general",
                    )
                    if decision is not None:
                        engine._last_topic_decision = {
                            "action": getattr(decision, "action", ""),
                            "target": getattr(decision, "target_node_id", None),
                        }
                except Exception:
                    pass
            if reply:
                try:
                    dt.feed(reply[:500], sid, cognitive_hints=cognitive_hints)
                except TypeError:
                    dt.feed(reply[:500], sid)
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
                        # P1: behavior brain — learn + background next-step
                        # prediction (ADR-013: prior only, never same-turn).
                        run_brain = getattr(engine, '_run_behavior_brain', None)
                        if run_brain is not None:
                            try:
                                run_brain(evt)
                            except Exception as e:
                                logger.debug("BehaviorBrain run failed: %s", e)
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
        reviewed = False
        scanned = False
        if mc:
            if hasattr(mc, 'retrospect'):
                try:
                    # M4 修复: 意图参数真实化（此前 ctx intent 恒空 → 恒 general）
                    intent_ctx = ctx.get("intent") or {}
                    category = (
                        intent_ctx.get("category")
                        or intent_ctx.get("intent_category")
                        or (ctx.get("pcr") or {}).get("intent")
                        or "general"
                    )
                    mc.retrospect(target=str(category))
                    reviewed = True
                except:
                    pass
            if hasattr(mc, 'scan'):
                try:
                    mc.scan(engine)  # scan requires engine parameter
                    scanned = True
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
            # M4 附带修复: stats() 返回的 reviewed 计数会覆盖本 handler 的布尔标志
            # → 最后统一写入标志位（供 _feed_inertia_evidence 等消费方判真）
            results["reviewed"] = reviewed
            results["scanned"] = scanned
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
                # P2: Track A 认知状态层逐轮喂入（DynamicsComputer + Convergence）
                if hasattr(engine, '_feed_profile_runtime'):
                    try:
                        engine._feed_profile_runtime(text, reply)
                    except Exception as e:
                        logger.debug("Profile runtime feed failed: %s", e)
                # P11: analyze 后落盘（OCEANProfile.save 挂载）
                if hasattr(ocean, 'save'):
                    try:
                        ocean.save()
                    except Exception:
                        pass
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
