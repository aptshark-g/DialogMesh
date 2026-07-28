"""DiscourseBlockTree CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_session


def _root():
    p = __import__("os").path
    return p.dirname(p.dirname(p.dirname(p.dirname(p.dirname(p.abspath(__file__))))))


def cmd_show(args):
    e = get_engine()
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        print(json.dumps({"error": "Discourse tree not loaded"}, ensure_ascii=False))
        return
    t = tree.get_tree(sid)
    if not t:
        print(json.dumps({"blocks": {}, "relations": []}, ensure_ascii=False))
        return
    stats = tree.get_stats(sid)
    stats["blocks"] = {}
    for bid, b in t.blocks.items():
        stats["blocks"][bid] = {
            "edus": len(b.edus) if hasattr(b, 'edus') else 0,
            "parent": getattr(b, 'parent', ''),
            "children": list(getattr(b, 'children', [])),
            "temperature": getattr(b, 'temperature', 0),
        }
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def cmd_tree(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
        return
    rels = tree.get_block_relations(get_session(
        args.sid if hasattr(args, 'sid') else None))
    print(json.dumps(rels, indent=2, ensure_ascii=False))


def cmd_block(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
        return
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    t = tree.get_tree(sid)
    if not t or args.id not in t.blocks:
        print(json.dumps({"error": f"Block {args.id} not found"}, ensure_ascii=False))
        return
    b = t.blocks[args.id]
    info = {
        "id": b.block_id if hasattr(b, 'block_id') else args.id,
        "edus": len(b.edus) if hasattr(b, 'edus') else 0,
        "parent": b.parent if hasattr(b, 'parent') else "",
        "children": list(b.children if hasattr(b, 'children') else []),
        "temperature": b.temperature if hasattr(b, 'temperature') else 0,
        "summary": getattr(b, 'summary', '')[:200] if hasattr(b, 'summary') else "",
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_feed(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
        return
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    result = tree.feed(text, sid)
    print(json.dumps({"status": "fed", "decision": result.decision.value if result else "?",
                       "block_id": result.target_block_id if result else ""}, ensure_ascii=False))


def cmd_search(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
        return
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    bid = tree.find_block_by_reference(sid, args.keyword)
    print(json.dumps({"found": bid is not None, "block_id": bid}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("discourse", help="DiscourseBlockTree operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("tree")
    b = sp.add_parser("block")
    b.add_argument("id")
    f = sp.add_parser("feed")
    f.add_argument("text", nargs="+")
    s = sp.add_parser("search")
    s.add_argument("keyword")
