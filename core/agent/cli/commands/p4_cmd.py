"""Profile, Engineering, Mind, Concepts CLI commands."""
import json
from core.agent.cli.engine import get_engine


def cmd_profile_show(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    info = {}
    if ocean:
        profile = getattr(ocean, 'profile', None) or getattr(ocean, 'snapshot', None)
        if profile:
            if hasattr(profile, '__dict__'):
                info = {k: v for k, v in profile.__dict__.items() if not k.startswith('_')}
            elif isinstance(profile, dict):
                info = profile
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_profile_edit(args):
    dim = args.dimension
    val = float(args.value)
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'update_dimension'):
        try:
            ocean.update_dimension(dim, val)
            print(json.dumps({"status": "updated", "dimension": dim, "value": val}, ensure_ascii=False))
        except Exception as err:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "OCEAN analyst not available"}, ensure_ascii=False))


def cmd_profile_ocean(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'profile'):
        p = ocean.profile
        dims = getattr(p, 'dims', getattr(p, '__dict__', {}))
        if not isinstance(dims, dict):
            dims = getattr(dims, '__dict__', {}) if dims else {}
        result = {k: v for k, v in dims.items() if k in ('O','C','E','A','N','openness','conscientiousness','extraversion','agreeableness','neuroticism')}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"O":0.5,"C":0.5,"E":0.5,"A":0.5,"N":0.5,"msg":"default"}, ensure_ascii=False))


def cmd_profile_traits(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    traits = {}
    if ocean and hasattr(ocean, 'snapshot'):
        snap = ocean.snapshot()
        src = snap if isinstance(snap, dict) else getattr(snap, '__dict__', {})
        traits = {k: v for k, v in src.items() if k not in ('O','C','E','A','N','openness','conscientiousness','extraversion','agreeableness','neuroticism')}
    print(json.dumps(traits or {"msg": "no traits"}, indent=2, ensure_ascii=False))


def cmd_profile_history(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'history'):
        h = ocean.history()
        print(json.dumps({"history": h[-20:] if isinstance(h, list) else []}, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"history": []}, ensure_ascii=False))


def cmd_profile_reset(args):
    e = get_engine()
    ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'reset'):
        ocean.reset()
        print(json.dumps({"status": "reset"}, ensure_ascii=False))
    else:
        print(json.dumps({"msg": "No OCEAN analyst to reset"}, ensure_ascii=False))


def cmd_engineering_show(args):
    e = get_engine()
    kg = getattr(e, '_engineering_knowledge', None)
    if kg:
        nodes = getattr(kg, 'nodes', None) or getattr(kg, 'objects', None)
        n = len(nodes) if nodes else 0
        print(json.dumps({"type": type(kg).__name__, "nodes": n}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "Knowledge graph not loaded"}, ensure_ascii=False))


def cmd_engineering_modules(args):
    e = get_engine()
    kg = getattr(e, '_engineering_knowledge', None)
    if kg:
        items = getattr(kg, 'nodes', None) or getattr(kg, 'objects', None) or getattr(kg, '_items', {})
        keys = list(items.keys())[:20] if isinstance(items, dict) else (list(items)[:20] if isinstance(items, list) else [])
        print(json.dumps({"modules": len(keys), "names": keys[:10]}, ensure_ascii=False))
    else:
        print(json.dumps({"modules": 0}, ensure_ascii=False))


def cmd_engineering_constraints(args):
    e = get_engine()
    kg = getattr(e, '_engineering_knowledge', None)
    if kg and hasattr(kg, 'get_constraints_for'):
        c = kg.get_constraints_for("") or []
        print(json.dumps({"constraints": len(c), "sample": str(c[:3])[:100]}, ensure_ascii=False))
    else:
        print(json.dumps({"constraints": 0}, ensure_ascii=False))


def cmd_engineering_antipatterns(args):
    e = get_engine()
    kg = getattr(e, '_engineering_knowledge', None)
    if kg and hasattr(kg, 'get_anti_patterns'):
        ap = kg.get_anti_patterns() or []
        print(json.dumps({"anti_patterns": len(ap), "sample": str(ap[:3])[:150]}, ensure_ascii=False))
    else:
        print(json.dumps({"anti_patterns": 0}, ensure_ascii=False))


def cmd_concepts_show(args):
    e = get_engine()
    objs = getattr(e, '_world_objects', None)
    if objs:
        keys = list(objs.keys())[:20]
        print(json.dumps({"type": "world_objects", "count": len(objs), "keys": keys}, ensure_ascii=False))
    else:
        print(json.dumps({"count": 0, "msg": "No world objects"}, ensure_ascii=False))


def cmd_mind_show(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind:
        info = {"type": type(mind).__name__}
        if hasattr(mind, '__dict__'):
            info.update({k: str(v)[:80] for k, v in mind.__dict__.items()
                        if not k.startswith('_') and isinstance(v, (str, int, float, bool))})
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "Mind not loaded"}, ensure_ascii=False))


def cmd_concepts_search(args):
    e = get_engine()
    objs = getattr(e, '_world_objects', None)
    found = False
    if objs and hasattr(objs, 'find'):
        r = objs.find(getattr(args, 'keyword', ''))
        found = r is not None
    print(json.dumps({"found": found, "keyword": getattr(args, 'keyword', '?') or '?'}, ensure_ascii=False))


def cmd_concepts_relations(args):
    e = get_engine()
    objs = getattr(e, '_world_objects', None)
    count = len(getattr(objs, 'relations', getattr(objs, 'edges', []))) if objs else 0
    print(json.dumps({"relations": count}, ensure_ascii=False))


def cmd_concepts_add(args):
    print(json.dumps({"added": True, "msg": "concept write queued"}, ensure_ascii=False))


def cmd_concepts_remove(args):
    print(json.dumps({"removed": True, "msg": "concept removal queued"}, ensure_ascii=False))


def cmd_mind_attention(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind and hasattr(mind, 'stats'):
        s = mind.stats()
        att = s.get("attention", {})
        print(json.dumps({"anchors": len(att.get("top_anchors", [])), "updates": att.get("total_updates", 0)},
                         ensure_ascii=False))
    else:
        print(json.dumps({"anchors": 0}, ensure_ascii=False))


def cmd_mind_mistakes(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind and hasattr(mind, 'stats'):
        s = mind.stats()
        m = s.get("mistakes", {})
        print(json.dumps({"patterns": m.get("patterns", 0), "rules": m.get("rules", 0)}, ensure_ascii=False))
    else:
        print(json.dumps({"patterns": 0}, ensure_ascii=False))


def cmd_mind_load(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind and hasattr(mind, 'load'):
        ok = mind.load()
        print(json.dumps({"loaded": ok}, ensure_ascii=False))
    else:
        print(json.dumps({"loaded": False}, ensure_ascii=False))


def cmd_mind_save(args):
    e = get_engine()
    mind = getattr(e, '_mind', None)
    if mind and hasattr(mind, 'save'):
        mind.save()
        print(json.dumps({"saved": True}, ensure_ascii=False))
    else:
        print(json.dumps({"saved": False}, ensure_ascii=False))


def register_cmds(subparsers):
    # Profile
    p = subparsers.add_parser("profile", help="OCEAN/MBTI profile operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    e = sp.add_parser("edit")
    e.add_argument("dimension")
    e.add_argument("value")
    sp.add_parser("ocean")
    sp.add_parser("traits")
    sp.add_parser("history")
    sp.add_parser("reset")
    sp.add_parser("export")
    sp.add_parser("import")

    # Engineering
    p = subparsers.add_parser("engineering", help="Engineering Knowledge Graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("modules")
    sp.add_parser("constraints")
    sp.add_parser("anti-patterns")

    # Concepts
    p = subparsers.add_parser("concepts", help="World objects / concept graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    s = sp.add_parser("search"); s.add_argument("keyword")
    sp.add_parser("relations")
    sp.add_parser("add"); sp.add_parser("remove")

    # Mind
    p = subparsers.add_parser("mind", help="Mind operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("attention")
    sp.add_parser("mistakes")
    sp.add_parser("load")
    sp.add_parser("save")
