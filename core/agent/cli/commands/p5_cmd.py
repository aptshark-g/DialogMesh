"""Rules, ABC, Annotations, Corrections, Feedback, Inertia, Versions, Metrics."""
import json
from core.agent.cli.engine import get_engine, get_session


def cmd_rules_show(args):
    e = get_engine()
    abc = getattr(e, '_abc_orchestrator', None)
    if abc:
        rules = getattr(abc, 'rules', None)
        if isinstance(rules, dict):
            print(json.dumps({"rules": len(rules), "keys": list(rules.keys())[:20]}, ensure_ascii=False))
        elif isinstance(rules, list):
            print(json.dumps({"rules": len(rules)}, ensure_ascii=False))
        else:
            print(json.dumps({"rules": 0}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "ABC orchestrator not loaded"}, ensure_ascii=False))


def cmd_rules_add(args):
    e = get_engine()
    abc = getattr(e, '_abc_orchestrator', None)
    if abc and hasattr(abc, 'add_rule'):
        abc.add_rule({"antecedent": args.antecedent, "behavior": args.behavior, "consequence": args.consequence})
        print(json.dumps({"status": "added"}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "Cannot add rules"}, ensure_ascii=False))


def cmd_abc_show(args):
    e = get_engine()
    abc = getattr(e, '_abc_orchestrator', None)
    if abc:
        info = {"type": type(abc).__name__}
        if hasattr(abc, 'status'):
            info.update(abc.status())
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "ABC not loaded"}, ensure_ascii=False))


def cmd_annotations_show(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind and hasattr(mind, 'mistakes'):
        mm = mind.mistakes
        count = len(getattr(mm, 'items', getattr(mm, 'entries', [])))
        print(json.dumps({"annotations": count}, ensure_ascii=False))
    else:
        print(json.dumps({"annotations": 0}, ensure_ascii=False))


def cmd_corrections_show(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if ocean:
        hist = getattr(ocean, 'history', [])
        print(json.dumps({"corrections": len(hist)}, ensure_ascii=False))
    else:
        print(json.dumps({"corrections": 0}, ensure_ascii=False))


def cmd_feedback_show(args):
    e = get_engine()
    meta = getattr(e, '_meta_cognition', None)
    if meta and hasattr(meta, 'reviews'):
        print(json.dumps({"reviews": len(meta.reviews or [])}, ensure_ascii=False))
    else:
        print(json.dumps({"msg": "No feedback data"}, ensure_ascii=False))


def cmd_inertia_show(args):
    e = get_engine()
    inert = getattr(e, '_inertia', None)
    if inert:
        info = {"type": type(inert).__name__}
        if hasattr(inert, '__dict__'):
            for k, v in inert.__dict__.items():
                if not k.startswith('_') and not callable(v):
                    if isinstance(v, (int, float, str)):
                        info[k] = v
                    elif hasattr(v, '__len__'):
                        info[k] = len(v)
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "Inertia not loaded"}, ensure_ascii=False))


def cmd_versions_show(args):
    e = get_engine()
    meta = getattr(e, '_meta_cognition', None)
    if meta:
        vcs = getattr(meta, '_vcs', None) or getattr(e, '_vcs', None)
        if vcs and hasattr(vcs, 'list_versions'):
            info = vcs.list_versions()
            print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"versions": 0}, ensure_ascii=False))
    else:
        print(json.dumps({"versions": 0}, ensure_ascii=False))


def cmd_metrics_show(args):
    e = get_engine()
    stats = getattr(e, '_stats', None) or {}
    if isinstance(stats, dict):
        metric_info = {k: v for k, v in stats.items() if isinstance(v, (int, float, str))}
        print(json.dumps(metric_info, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"msg": "No metrics"}, ensure_ascii=False))


def register_cmds(subparsers):
    # Rules
    p = subparsers.add_parser("rules", help="ABC rule operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    a = sp.add_parser("add")
    a.add_argument("antecedent")
    a.add_argument("behavior")
    a.add_argument("consequence")

    # ABC
    p = subparsers.add_parser("abc", help="ABC Orchestrator")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Annotations
    p = subparsers.add_parser("annotations", help="Mind annotations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Corrections
    p = subparsers.add_parser("corrections", help="Profile corrections")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Feedback
    p = subparsers.add_parser("feedback", help="Meta feedback")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Inertia
    p = subparsers.add_parser("inertia", help="Inertia weight graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Versions
    p = subparsers.add_parser("versions", help="Version control")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Metrics
    p = subparsers.add_parser("metrics", help="Engine metrics")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Add-ons: rules stats, inertia patterns
    rs = subparsers.add_parser("rules").add_subparsers(dest="subcommand")
    rs.add_parser("show"); rs.add_parser("add"); rs.add_parser("stats")
    inert = subparsers.add_parser("inertia").add_subparsers(dest="subcommand")
    inert.add_parser("show"); inert.add_parser("patterns")
