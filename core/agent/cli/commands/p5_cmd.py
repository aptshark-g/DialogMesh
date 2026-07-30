"""Rules, ABC, Annotations, Corrections, Feedback, Inertia, Versions, Metrics."""
import json, os as _os
from core.agent.cli.engine import get_engine, get_session

ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

def _disk(key: str, rel_path: str):
    """Read disk-backed JSON with HotStore memory cache."""
    fpath = _os.path.join(ROOT, rel_path)
    cache_key = f"disk:{rel_path}"
    
    # 1. Try HotStore (memory, sub-ms)
    try:
        import core.agent.cli.engine as _eng
        e = _eng._engine
    except:
        e = None
    if e and hasattr(e, '_storage'):
        hot = e._storage.hot
        cached = hot.get(cache_key)
        if cached is not None:  # even empty list is valid cache
            count = len(cached) if isinstance(cached, list) else (1 if cached else 0)
            print(json.dumps({f"{key}_count": count, "source": rel_path, "cache": "hot"},
                             ensure_ascii=False))
            return
    
    # 2. Read from disk
    if _os.path.exists(fpath):
        try:
            import json as _json
            with open(fpath, encoding="utf-8") as f:
                data = _json.load(f)
            count = len(data) if isinstance(data, list) else (1 if data else 0)
            # Cache in HotStore (even if empty)
            if e and hasattr(e, '_storage'):
                e._storage.hot.set(cache_key, data)
            print(json.dumps({f"{key}_count": count, "source": rel_path, "cache": "miss"},
                             ensure_ascii=False))
            return
        except:
            print(json.dumps({f"{key}_count": 0, "error": "parse failed"}, ensure_ascii=False))
            return
    print(json.dumps({f"{key}_count": 0, "source": rel_path}, ensure_ascii=False))


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
    _disk("annotations", "data/annotations.json")


def cmd_corrections_show(args):
    _disk("corrections", "data/corrections.json")


def cmd_feedback_show(args):
    _disk("feedback", "data/feedback.json")


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
    sla = getattr(e, '_sla_watchdog', None)
    sched = getattr(e, '_scheduler', None)
    info = {"subsystems": sum(1 for _ in [e._state_machine,e._storage,e._tracer,e._event_log,e._decider] if _)}
    if sla and hasattr(sla, 'stats'):
        info["sla"] = str(sla.stats())[:80]
    if sched and hasattr(sched, 'stats'):
        info["scheduler"] = str(sched.stats())[:80]
    print(json.dumps(info, indent=2, ensure_ascii=False))


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
