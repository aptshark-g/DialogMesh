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
    if hasattr(ocean, 'analyze'):
        result = ocean.analyze(session_id=sid)
        dims = getattr(getattr(result, 'dims', {}), '__dict__', {}) if hasattr(result, 'dims') else {}
        print(json.dumps({"dims": dims, "mbti": getattr(result, 'mbti', '?')}, ensure_ascii=False, default=str))
    else:
        print('{"error":"analyze method not available"}')


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
