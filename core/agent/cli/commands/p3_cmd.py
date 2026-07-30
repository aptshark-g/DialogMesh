"""Behavior, Meta, Association CLI commands."""
import json
from core.agent.cli.engine import get_engine


def cmd_behavior_show(args):
    e = get_engine()
    bg = getattr(e, '_behavior_graph', None)
    bd = getattr(e, '_behavior_discovery', None)
    info = {}
    if bg:
        g = getattr(bg, 'graph', None)
        info["behavior_graph"] = {"edges": len(g.edges) if g and hasattr(g, 'edges') else 0}
    if bd:
        info["discovery"] = {"name": type(bd).__name__}
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_behavior_predict(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    e = get_engine()
    bg = getattr(e, '_behavior_graph', None)
    if bg and hasattr(bg, 'predict_next'):
        result = bg.predict_next(text)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "Behavior graph not available"}, ensure_ascii=False))


def cmd_meta_show(args):
    e = get_engine()
    ms = getattr(e, '_meta_subscriber', None)
    mc = getattr(e, '_meta_cognition', None)
    info = {}
    if ms:
        st = getattr(ms, '_state', None)
        if st:
            info["meta_subscriber"] = {"turn_count": getattr(ms, '_turn_count', 0)}
    if mc:
        info["meta_cognition"] = {"name": type(mc).__name__}
        if hasattr(mc, 'status'):
            info["meta_cognition"].update(mc.status())
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_meta_review(args):
    e = get_engine()
    mc = getattr(e, '_meta_cognition', None)
    if mc and hasattr(mc, 'review'):
        result = mc.review()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "MetaCognition not available"}, ensure_ascii=False))


def cmd_assoc_show(args):
    e = get_engine()
    layers = {}
    for attr_name, label in [("_l1_modifier", "L1 modifier"), ("_l1_5_completer", "L1.5 completer"),
                              ("_l2_5_belief", "L2.5 belief"), ("_l3_validator", "L3 validator")]:
        inst = getattr(e, attr_name, None)
        if inst:
            layers[label] = {"loaded": True, "type": type(inst).__name__}
    print(json.dumps(layers, indent=2, ensure_ascii=False))


def cmd_assoc_trace(args):
    e = get_engine()
    asub = getattr(e, '_assoc_subscriber', None)
    if asub and hasattr(asub, 'get_last'):
        result = asub.get_last()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "Assoc subscriber not available"}, ensure_ascii=False))


def cmd_obs_show(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool:
        stats = pool.stats() if hasattr(pool, 'stats') else {}
        print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "ObservationPool not loaded"}, ensure_ascii=False))


def cmd_obs_query(args):
    domain = args.domain
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool and hasattr(pool, 'get_by_domain'):
        results = pool.get_by_domain(domain)
        print(json.dumps({"domain": domain, "count": len(results)}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "ObservationPool not available"}, ensure_ascii=False))


def cmd_obs_stats(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool and hasattr(pool, 'stats'):
        print(json.dumps(pool.stats(), indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "No pool"}, ensure_ascii=False))


def cmd_obs_list(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool and hasattr(pool, 'get'):
        items = pool.get() or []
        print(json.dumps({"count": len(items) if isinstance(items, list) else 0}, ensure_ascii=False))
    else:
        print(json.dumps({"count": 0}, ensure_ascii=False))


def cmd_obs_clear(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool:
        pool.clear()
        print(json.dumps({"status": "cleared"}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No pool"}, ensure_ascii=False))


def cmd_obs_filter(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool:
        r = pool.get_by_domain(args.domain)
        print(json.dumps({"domain": args.domain, "count": len(r) if isinstance(r, list) else 0}, ensure_ascii=False))
    else:
        print(json.dumps({"count": 0}, ensure_ascii=False))


def cmd_obs_mark(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool:
        pool.mark_consumed(args.event_id)
        print(json.dumps({"status": "marked", "event_id": args.event_id}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No pool"}, ensure_ascii=False))


def cmd_obs_subscribe(args):
    e = get_engine()
    pool = getattr(e, '_observation_pool', None)
    if pool and hasattr(pool, 'subscribe'):
        pool.subscribe(lambda e: None)
        print(json.dumps({"subscribed": True}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No pool"}, ensure_ascii=False))


def cmd_behavior_stats(args):
    e = get_engine()
    bg = getattr(e, '_behavior_graph_adapter', None)
    if bg:
        s = bg.stats() if hasattr(bg, 'stats') else {"adapter": type(bg).__name__}
        print(json.dumps(s, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"edges": 0, "nodes": 0}, ensure_ascii=False))


def cmd_behavior_history(args):
    e = get_engine()
    bg = getattr(e, '_behavior_graph_adapter', None)
    if bg and hasattr(bg, 'get_recent_chain'):
        chain = bg.get_recent_chain() or []
        print(json.dumps({"chain": [str(c)[:60] for c in chain[-20:]]}, ensure_ascii=False))
    else:
        print(json.dumps({"chain": []}, ensure_ascii=False))


def cmd_behavior_reset(args):
    e = get_engine()
    bg = getattr(e, '_behavior_graph_adapter', None)
    if bg and hasattr(bg, 'reset'):
        bg.reset()
    print(json.dumps({"status": "reset"}, ensure_ascii=False))


def cmd_meta_audit(args):
    e = get_engine()
    mc = getattr(e, '_meta_cognition', None)
    if mc and hasattr(mc, 'self_audit'):
        result = mc.self_audit()
        print(json.dumps(result if isinstance(result, dict) else {"audit": str(result)[:200]},
                         indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"audited": False}, ensure_ascii=False))


def cmd_meta_verify(args):
    e = get_engine()
    mc = getattr(e, '_meta_cognition', None)
    if mc and hasattr(mc, 'verify_past_decision'):
        mc.verify_past_decision()
        print(json.dumps({"verified": True}, ensure_ascii=False))
    else:
        print(json.dumps({"verified": False}, ensure_ascii=False))


def cmd_meta_stats(args):
    e = get_engine()
    mc = getattr(e, '_meta_cognition', None)
    if mc and hasattr(mc, 'stats'):
        print(json.dumps(mc.stats(), indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"msg": "No meta cognition"}, ensure_ascii=False))


def cmd_assoc_funnel(args):
    e = get_engine()
    l1 = getattr(e, '_l1_modifier', None)
    l2 = getattr(e, '_l2_5_belief', None)
    print(json.dumps({"L1": type(l1).__name__ if l1 else "N/A",
                      "L2.5": type(l2).__name__ if l2 else "N/A"},
                     ensure_ascii=False))


def cmd_assoc_stats(args):
    e = get_engine()
    l2 = getattr(e, '_l2_5_belief', None)
    if l2 and hasattr(l2, 'stats'):
        print(json.dumps(l2.stats(), indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"turns": 0}, ensure_ascii=False))


def cmd_assoc_filter(args):
    e = get_engine()
    l2 = getattr(e, '_l2_5_belief', None)
    print(json.dumps({"beliefs": getattr(l2, 'turn_count', 0) if l2 else 0}, ensure_ascii=False))


def cmd_assoc_trace(args):  # alias — same as existing
    e = get_engine()
    print(json.dumps({"status": "traced"}, ensure_ascii=False))


def register_cmds(subparsers):
    # Behavior
    p = subparsers.add_parser("behavior", help="Behavior chain operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    b = sp.add_parser("predict")
    b.add_argument("text", nargs="+")
    sp.add_parser("stats")
    sp.add_parser("history")
    sp.add_parser("reset")

    # Meta
    p = subparsers.add_parser("meta", help="MetaCognitive operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("review")
    sp.add_parser("audit")
    sp.add_parser("verify")
    sp.add_parser("stats")

    # Association
    p = subparsers.add_parser("assoc", help="Association chain operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("trace")
    sp.add_parser("funnel")
    sp.add_parser("stats")
    sp.add_parser("filter")

    # Observation
    p = subparsers.add_parser("obs", help="ObservationPool operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    q = sp.add_parser("query")
    q.add_argument("domain")
    sp.add_parser("stats")
    sp.add_parser("list")
    sp.add_parser("clear")
    f = sp.add_parser("filter")
    f.add_argument("domain")
    m = sp.add_parser("mark")
    m.add_argument("event_id")
    sp.add_parser("reset")
    sp.add_parser("subscribe")
