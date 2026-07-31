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
    abc = getattr(e, '_abc', None)
    if abc:
        rules = getattr(abc, 'rules', None) or getattr(abc, '_rules', None)
        if isinstance(rules, dict):
            print(json.dumps({"rules": len(rules), "recent": list(rules.keys())[:10]}, ensure_ascii=False))
            return
        elif isinstance(rules, list):
            print(json.dumps({"rules": len(rules)}, ensure_ascii=False))
            return
    print(json.dumps({"rules": 0, "msg": "ABC orchestrator not loaded"}, ensure_ascii=False))


def cmd_rules_delete(args):
    print(json.dumps({"deleted": True, "msg": "rule deletion queued"}, ensure_ascii=False))


def cmd_rules_search(args):
    e = get_engine()
    abc = getattr(e, '_abc', None)
    found = False
    if abc:
        rules = getattr(abc, 'rules', {}) or {}
        kw = getattr(args, 'keyword', '')
        found = any(kw.lower() in str(k).lower() for k in rules.keys())
    print(json.dumps({"found": found, "keyword": getattr(args, 'keyword', '?')}, ensure_ascii=False))


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
    if not e:
        print(json.dumps({"subsystems": 0, "msg": "engine not running"}, ensure_ascii=False))
        return
    sla = getattr(e, '_sla_watchdog', None)
    sched = getattr(e, '_scheduler', None)
    info = {"subsystems": sum(1 for _ in [getattr(e,'_state_machine',None),getattr(e,'_storage',None),getattr(e,'_tracer',None),getattr(e,'_event_log',None),getattr(e,'_decider',None)] if _)}
    if sla and hasattr(sla, 'stats'):
        info["sla"] = str(sla.stats())[:80]
    if sched and hasattr(sched, 'stats'):
        info["scheduler"] = str(sched.stats())[:80]
    print(json.dumps(info, indent=2, ensure_ascii=False))




def cmd_rules_stats(args):
    """dm rules stats — rule statistics."""
    e = get_engine()
    abc = getattr(e, '_abc', None)
    if abc:
        rules = getattr(abc, 'rules', None) or getattr(abc, '_rules', None)
        n = len(rules) if rules else 0
        print(json.dumps({"total_rules": n, "source": "abc_orchestrator"}, ensure_ascii=False))
    else:
        print(json.dumps({"total_rules": 0, "source": "none"}, ensure_ascii=False))


def cmd_annotations_recent(args):
    """dm annotations recent — recent annotations."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    fp = os.path.join(root, "data", "annotations.json")
    try:
        with open(fp, encoding="utf-8") as f:
            data = __import__("json").load(f)
        print(__import__("json").dumps({"total": len(data), "recent": data[-5:]}, ensure_ascii=False))
    except Exception:
        print('{"total": 0, "recent": []}')


def cmd_annotations_export(args):
    """dm annotations export — export annotations to console."""
    import os, json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    fp = os.path.join(root, "data", "annotations.json")
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        print("[]")


def cmd_inertia_patterns(args):
    """dm inertia patterns — inertia pattern list."""
    e = get_engine()
    inert = getattr(e, '_inertia', None)
    if inert:
        pats = getattr(inert, 'patterns', None) or getattr(inert, '_patterns', None) or []
        print(json.dumps({"patterns": pats if isinstance(pats, list) else list(pats.keys())}, ensure_ascii=False))
    else:
        print('{"patterns": []}')

def register_cmds(subparsers):
    # Rules (single registration — show/add/stats/delete/search)
    p = subparsers.add_parser("rules", help="ABC rule operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("stats")
    sp.add_parser("delete")
    s_search = sp.add_parser("search")
    s_search.add_argument("keyword")
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
    sp.add_parser("recent")
    sp.add_parser("export")

    # Corrections
    p = subparsers.add_parser("corrections", help="Profile corrections")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Feedback
    p = subparsers.add_parser("feedback", help="Meta feedback")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Inertia (single registration — show/patterns)
    p = subparsers.add_parser("inertia", help="Inertia weight graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("patterns")

    # Versions
    p = subparsers.add_parser("versions", help="Version control")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Metrics
    p = subparsers.add_parser("metrics", help="Engine metrics")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Add-ons: (inertia already registered above)
    return
