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


def cmd_engineering_show(args):
    e = get_engine()
    kg = getattr(e, '_engineering_knowledge', None)
    if kg:
        nodes = getattr(kg, 'nodes', None) or getattr(kg, 'objects', None)
        n = len(nodes) if nodes else 0
        print(json.dumps({"type": type(kg).__name__, "nodes": n}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "Knowledge graph not loaded"}, ensure_ascii=False))


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
                         if not k.startswith('_') and not callable(v)})
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "Mind not loaded"}, ensure_ascii=False))


def register_cmds(subparsers):
    # Profile
    p = subparsers.add_parser("profile", help="OCEAN/MBTI profile operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    e = sp.add_parser("edit")
    e.add_argument("dimension", help="e.g. openness, conscientiousness")
    e.add_argument("value")

    # Engineering
    p = subparsers.add_parser("engineering", help="Engineering Knowledge Graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Concepts
    p = subparsers.add_parser("concepts", help="World objects / concept graph")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    # Mind
    p = subparsers.add_parser("mind", help="Mind operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
