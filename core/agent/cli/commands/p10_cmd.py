"""P10: Algorithmic CLI triggers — expose engine algorithms as DM commands.

Every subsystem's core algorithm is now independently callable.
This is what makes the Blueprint actually composable.
"""
import json, os, time
from core.agent.cli.engine import get_engine, get_session, PROJECT_ROOT


# ═══════════════════════════════════════════════════════════
# Discourse: SyntacticDecomposer, MacroMicroQuantizer, BlockTree
# ═══════════════════════════════════════════════════════════

def cmd_discourse_decompose(args):
    """dm discourse decompose <text> — run SyntacticDecomposer on text, show EDUs."""
    from core.agent.compiler.discourse_block_tree import SyntacticDecomposer
    text = " ".join(args.text) if hasattr(args, 'text') else getattr(args, 'text', '')
    d = SyntacticDecomposer()
    edus = d.decompose(text)
    result = [{"id": e.edu_id, "text": e.raw_text, "subject": e.subject,
                "predicate": e.predicate, "obj": e.obj, "entities": list(e.entities)}
              for e in edus]
    print(json.dumps({"edus": result, "count": len(edus)}, ensure_ascii=False, default=str))


def cmd_discourse_cohesion(args):
    """dm discourse cohesion <text1> --text2=<text2> — compute MacroMicro cohesion."""
    from core.agent.compiler.discourse_block_tree import SyntacticDecomposer, MacroMicroQuantizer
    text1 = " ".join(args.text1) if hasattr(args, 'text1') else ""
    text2 = getattr(args, 'text2', '')
    d = SyntacticDecomposer()
    q = MacroMicroQuantizer()
    edu1 = d.decompose(text1)[0] if text1 else None
    edu2 = d.decompose(text2)[0] if text2 else None
    if not edu1 or not edu2:
        return print('{"error":"need two texts"}')
    c = q.compute(edu1, edu2)
    print(json.dumps({
        "decision": c.decision, "total": c.total,
        "lexical": c.lexical, "micro": c.micro, "macro": c.macro,
        "topic_embed": c.topic_embed, "entity_overlap": c.entity_overlap,
        "intent_match": c.intent_match,
    }, ensure_ascii=False, default=str))


def cmd_discourse_block_tree(args):
    """dm discourse block-tree <sid> — show actual block tree with parent/child relations."""
    e = get_engine()
    tree_mgr = getattr(e, '_discourse_tree', None)
    if not tree_mgr:
        return print('{"error":"discourse tree not loaded"}')
    sid = getattr(args, 'sid', get_session()) if hasattr(args, 'sid') else get_session()
    rel = tree_mgr.get_block_relations(sid)
    print(json.dumps(rel, ensure_ascii=False, default=str))


def cmd_discourse_context_build(args):
    """dm discourse context-build <sid> — build LLM context from block tree."""
    e = get_engine()
    tree_mgr = getattr(e, '_discourse_tree', None)
    if not tree_mgr:
        return print('{"error":"discourse tree not loaded"}')
    sid = getattr(args, 'sid', get_session()) if hasattr(args, 'sid') else get_session()
    ctx = tree_mgr.build_context(sid, max_blocks=getattr(args, 'max_blocks', 8) if hasattr(args, 'max_blocks') else 8)
    print(json.dumps({"context": ctx[:500], "length": len(ctx)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Meta: self_audit, anomaly detection
# ═══════════════════════════════════════════════════════════

def cmd_meta_self_audit(args):
    """dm meta self-audit — run MetaCognition self_audit on recent decisions."""
    e = get_engine()
    mc = getattr(e, '_meta_cognition', None)
    if not mc or not hasattr(mc, 'self_audit'):
        return print('{"error":"meta_cognition not loaded or no self_audit"}')
    result = mc.self_audit()
    print(json.dumps({"audit": str(result)[:500]}, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# Behavior: pattern discovery
# ═══════════════════════════════════════════════════════════

def cmd_behavior_discover(args):
    """dm behavior discover [--min-support=3] — run BehaviorDiscovery.discover()."""
    e = get_engine()
    bd = getattr(e, '_behavior_discovery', None)
    if not bd or not hasattr(bd, 'discover'):
        return print('{"error":"behavior_discovery not loaded"}')
    ms = getattr(args, 'min_support', 3) if hasattr(args, 'min_support') else 3
    patterns = bd.discover(min_support=ms)
    result = [{"pattern": str(getattr(p, 'pattern', p)), "count": getattr(p, 'count', 1)}
              for p in (patterns if patterns else [])]
    print(json.dumps({"patterns": result, "count": len(result)}, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# Profile: full OCEAN recalculation
# ═══════════════════════════════════════════════════════════

def cmd_profile_analyze(args):
    """dm profile analyze <sid> — full OCEAN recalculation from session history."""
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if not ocean:
        return print('{"error":"ocean_analyst not loaded"}')
    sid = getattr(args, 'sid', get_session()) if hasattr(args, 'sid') else get_session()
    if not hasattr(ocean, 'analyze'):
        print('{"error":"analyze method not available"}')
        return
    # P11: 签名对齐 — analyze(engine, turn_text, llm_response)。
    # 从会话历史（conversation tracker）取最近轮次喂入，而不是传 session_id。
    tracker = getattr(e, '_conversation_tracker', None)
    history = tracker.get_history_entries(max_entries=8) if tracker and hasattr(tracker, 'get_history_entries') else []
    if not history:
        print('{"error":"no conversation history — send a message first"}')
        return
    last_reply = getattr(e, '_last_llm_response', "") or ""
    analyzed = 0
    for entry in history:
        text = entry.get("text", "")
        if not text:
            continue
        try:
            ocean.analyze(e, text, last_reply)
            analyzed += 1
        except Exception as err:
            print(json.dumps({"error": f"analyze turn failed: {err}"}, ensure_ascii=False))
            return
    snap = ocean.snapshot() if hasattr(ocean, 'snapshot') else {}
    print(json.dumps({
        "dims": snap.get("dims", {}),
        "mbti": snap.get("mbti", "?"),
        "turns_analyzed": analyzed,
    }, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# Memory: compile from events
# ═══════════════════════════════════════════════════════════

def cmd_memory_compile_events(args):
    """dm memory compile-events <sid> — compile events into MemoryCompiler tiers."""
    e = get_engine()
    mc = getattr(e, '_memory_compiler', None)
    if not mc:
        return print('{"error":"memory compiler not loaded"}')
    events = []
    # Try reading from event log
    el = getattr(e, '_event_log', None)
    if el and hasattr(el, 'replay_unconsumed'):
        events = el.replay_unconsumed(50)
    result = mc.compile(events)
    print(json.dumps(result, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# Context: ThreeParadigmContext build
# ═══════════════════════════════════════════════════════════

def cmd_context_paradigm(args):
    """dm context paradigm <text> — build ThreeParadigmContext from discourse blocks."""
    from core.agent.compiler.three_paradigm_context import ThreeParadigmContext
    e = get_engine()
    tree_mgr = getattr(e, '_discourse_tree', None)
    topic = getattr(e, '_topic_tree', None)
    sid = getattr(args, 'sid', get_session()) if hasattr(args, 'sid') else get_session()
    blocks = []
    if tree_mgr:
        tree = tree_mgr.get_tree(sid)
        if tree and hasattr(tree, 'blocks'):
            blocks = list(tree.blocks.values())[:8]
    text = " ".join(args.text) if hasattr(args, 'text') and args.text else ""
    compass = ThreeParadigmContext(topic_tree=topic)
    ctx = compass.build(blocks, current_text=text, max_tokens=getattr(args, 'max_tokens', 2000) if hasattr(args, 'max_tokens') else 2000)
    print(json.dumps({"context": ctx[:500] if ctx else "", "length": len(ctx) if ctx else 0}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Causal: trigger causal chain processing
# ═══════════════════════════════════════════════════════════

def cmd_causal_trigger(args):
    """dm causal trigger — trigger CausalPlanner.process_chain if chain long enough."""
    e = get_engine()
    cp = getattr(e, '_causal_planner', None)
    if cp and hasattr(cp, 'process_chain'):
        recent = cp.get_recent_chain(20)
        if len(recent) > 5:
            result = cp.process_chain()
            print(json.dumps({"triggered": result.triggered,
                              "edge_updates": len(result.edge_updates) if hasattr(result, 'edge_updates') else 0},
                             ensure_ascii=False, default=str))
        else:
            print(json.dumps({"triggered": False, "reason": f"chain too short: {len(recent)}"}, ensure_ascii=False))
    else:
        print('{"error":"causal planner not loaded"}')


# ═══════════════════════════════════════════════════════════
# Association: run full association chain on text
# ═══════════════════════════════════════════════════════════

def cmd_assoc_analyze(args):
    """dm assoc analyze <text> — run L1 modifier extraction on input text."""
    text = " ".join(args.text) if hasattr(args, 'text') and args.text else ""
    if not text:
        return print('{"error":"need text"}')
    e = get_engine()
    l1 = getattr(e, '_l1_modifier', None)
    if l1 and hasattr(l1, 'extract'):
        modifiers = l1.extract(text)
        print(json.dumps({"modifiers": [str(m) for m in modifiers] if modifiers else [],
                          "count": len(modifiers) if modifiers else 0}, ensure_ascii=False, default=str))
    else:
        # Fallback: use SyntacticDecomposer
        from core.agent.compiler.discourse_block_tree import SyntacticDecomposer
        d = SyntacticDecomposer()
        edus = d.decompose(text)
        entities = list(set(e for edu in edus for e in getattr(edu, 'entities', [])))
        print(json.dumps({"modifiers": [str(e) for e in entities],
                          "count": len(entities), "source": "syntactic"}, ensure_ascii=False, default=str))

def cmd_eventbus_wire(args):
    """dm alg eventbus-wire — activate all EventBus subscribers."""
    e = get_engine()
    from core.agent.event.subscribers import wire_subscribers
    stats = wire_subscribers(e)
    print(json.dumps({"status":"wired","subscribers":stats["subscribers"],
                      "names":stats["names"]}, ensure_ascii=False))

def cmd_trace_show(args):
    """dm alg trace-show — show recent pipeline traces."""
    e = get_engine()
    tracer = getattr(e, '_tracer', None)
    if not tracer:
        return print('{"error":"tracer not loaded"}')
    traces = tracer.recent(limit=getattr(args, 'limit', 10) if hasattr(args, 'limit') else 10)
    print(json.dumps({"traces": traces, "stats": tracer.stats()}, ensure_ascii=False, default=str))

def cmd_trace_errors(args):
    """dm alg trace-errors -- show structured error aggregation (B3 whitebox)."""
    e = get_engine()
    tracer = getattr(e, '_tracer', None)
    if not tracer:
        return print('{"error":"tracer not loaded"}')
    if not hasattr(tracer, "error_report"):
        return print('{"error":"error_report unavailable"}')
    window = getattr(args, 'window', 200) if hasattr(args, 'window') else 200
    print(json.dumps(tracer.error_report(window=window), ensure_ascii=False, default=str))


def cmd_trace_turn(args):
    """dm alg trace-turn <trace_id> -- show per-phase detail of one turn."""
    e = get_engine()
    tracer = getattr(e, '_tracer', None)
    if not tracer:
        return print('{"error":"tracer not loaded"}')
    if not hasattr(tracer, "turn_detail"):
        return print('{"error":"turn_detail unavailable"}')
    tid = getattr(args, 'trace_id', None)
    limit = getattr(args, 'limit', 100) if hasattr(args, 'limit') else 100
    if not tid:
        # default: latest trace
        recent = tracer.recent(limit=1)
        tid = recent[0]["trace_id"] if recent else None
        if not tid:
            return print('{"error":"no traces yet"}')
    steps = tracer.turn_detail(trace_id=tid, limit=limit)
    print(json.dumps({"trace_id": tid, "steps": steps, "step_count": len(steps)},
                     ensure_ascii=False, default=str))


def cmd_trace_metrics(args):
    """dm alg trace-metrics — show per-subsystem metrics."""
    e = get_engine()
    tracer = getattr(e, '_tracer', None)
    if not tracer:
        return print('{"error":"tracer not loaded"}')
    print(json.dumps(tracer.metrics(), indent=2, ensure_ascii=False, default=str))


# ── Gap closure CLI ──

def cmd_cli_version(args):
    """dm alg cli-version — show CLI ABI compatibility info."""
    from core.agent.event.closure import get_cli_abi, check_compatibility
    abi = get_cli_abi()
    print(json.dumps({"abi": abi, "compat": "stable"}, ensure_ascii=False))

def cmd_hotreload(args):
    """dm alg hotreload <subsystem> — hot-reload a subsystem without restart."""
    e = get_engine()
    hr = getattr(e, '_hot_reloader', None)
    if not hr:
        return print('{"error":"hot_reloader not loaded"}')
    name = " ".join(args.subsystem) if hasattr(args, 'subsystem') else ""
    result = hr.reload(e, name) if name else hr.list_reloadable(e)
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_rate_guard(args):
    """dm alg rate-guard — show rate limiter stats."""
    e = get_engine()
    rg = getattr(e, '_rate_guard', None)
    if not rg:
        return print('{"error":"rate_guard not loaded"}')
    print(json.dumps(rg.stats(), indent=2, ensure_ascii=False))

def cmd_capability(args):
    """dm alg capability <subsystem> — show capability permissions."""
    e = get_engine()
    cg = getattr(e, '_cap_guard', None)
    if not cg:
        return print('{"error":"capability guard not loaded"}')
    name = " ".join(args.subsystem) if hasattr(args, 'subsystem') and args.subsystem else ""
    if name:
        p = cg.profile(name)
        result = {"name": name, "allowed": [c.value for c in p.allowed]} if p else {"error": "not found"}
    else:
        result = cg.all_profiles()
    print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_subprocess_run(args):
    """dm alg subprocess-run <module> <func> [args...] — run in isolated subprocess."""
    from core.agent.event.closure import SubprocessRunner
    runner = SubprocessRunner()
    mod = args.module if hasattr(args, 'module') else ""
    fn = args.func if hasattr(args, 'func') else ""
    extra = args.args if hasattr(args, 'args') else []
    result = runner.run_isolated("cli", mod, fn, tuple(extra))
    print(json.dumps(result, ensure_ascii=False, default=str))
