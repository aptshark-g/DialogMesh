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


def register_cmds(subparsers):
    # Behavior
    p = subparsers.add_parser("behavior", help="Behavior chain operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    b = sp.add_parser("predict")
    b.add_argument("text", nargs="+")

    # Meta
    p = subparsers.add_parser("meta", help="MetaCognitive operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("review")

    # Association
    p = subparsers.add_parser("assoc", help="Association chain operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("trace")

    # Observation
    p = subparsers.add_parser("obs", help="ObservationPool operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    q = sp.add_parser("query")
    q.add_argument("domain")
