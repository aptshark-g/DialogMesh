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


def cmd_stats(args):
    e = get_engine()
    dt = getattr(e, '_discourse_tree', None)
    sid = getattr(args, 'sid', None)
    if not sid:
        # Use engine's current session or last saved
        sid = get_session(None)
    
    # Try engine's in-memory tree first
    blocks_count = 0; relations_count = 0; max_depth = 0
    if dt:
        tree = dt.get_tree(sid)
        if tree and tree.blocks:
            rel = dt.get_block_relations(sid)
            blocks_count = len(rel.get("blocks", {}))
            relations_count = len(rel.get("relations", []))
            max_depth = max((getattr(b, 'depth', 0) for b in tree.blocks.values()), default=0)
    
    # Fallback: read from persisted discourse_state.json
    if blocks_count == 0:
        import os as _os
        root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))))
        ds_path = _os.path.join(root, "data", "discourse_state.json")
        if _os.path.exists(ds_path):
            try:
                saved = json.load(open(ds_path, encoding="utf-8"))
                blocks_count = len(saved.get("blocks", {}))
                relations_count = len(saved.get("relations", []))
            except: pass
    
    # List all available sessions
    sessions_available = []
    if dt and hasattr(dt, '_trees'):
        sessions_available = list(dt._trees.keys())
    
    print(json.dumps({
        "blocks": blocks_count, "relations": relations_count, "max_depth": max_depth,
        "session_id": sid, "sessions_available": sessions_available[:10],
    }, ensure_ascii=False))


def cmd_compress(args):
    e = get_engine()
    dt = getattr(e, '_discourse_tree', None)
    if not dt: return print(json.dumps({"error": "not loaded"}))
    sid = get_session(getattr(args, 'sid', None))
    count = dt.compress_cold_blocks(sid) if hasattr(dt, 'compress_cold_blocks') else 0
    print(json.dumps({"compressed": count}, ensure_ascii=False))


def cmd_topics(args):
    e = get_engine()
    tt = getattr(e, '_topic_tree', None)
    sid = get_session(getattr(args, 'sid', None))
    topics = []
    if tt and hasattr(tt, '_nodes'):
        for n in tt._nodes[:30]:
            topics.append({"topic": str(getattr(n, 'topic', n)), "heat": getattr(n, 'heat', 0)})
    print(json.dumps({"session_id": sid, "topics": topics}, ensure_ascii=False))


def cmd_topic_tree(args):
    e = get_engine()
    tt = getattr(e, '_topic_tree', None)
    sid = get_session(getattr(args, 'sid', None))
    nodes = {}
    edges = []
    if tt and hasattr(tt, '_nodes'):
        for n in tt._nodes[:50]:
            nid = str(getattr(n, 'topic', id(n)))
            nodes[nid] = {"heat": getattr(n, 'heat', 0)}
            parent = getattr(n, 'parent', None)
            if parent:
                edges.append({"from": str(getattr(parent, 'topic', 'root')), "to": nid})
    print(json.dumps({"session_id": sid, "nodes": nodes, "edges": edges}, ensure_ascii=False))


def cmd_summary(args):
    e = get_engine()
    dt = getattr(e, '_discourse_tree', None)
    if not dt: return print(json.dumps({"error": "not loaded"}))
    sid = get_session(getattr(args, 'sid', None))
    tree = dt.get_tree(sid)
    if not tree or args.block_id not in tree.blocks:
        return print(json.dumps({"error": "block not found"}, ensure_ascii=False))
    block = tree.blocks[args.block_id]
    block.summary = " ".join(args.text)
    print(json.dumps({"status": "ok", "block_id": args.block_id}, ensure_ascii=False))


def cmd_topic_add(args):
    e = get_engine()
    tt = getattr(e, '_topic_tree', None)
    if not tt: return print(json.dumps({"error": "no topic tree"}))
    if hasattr(tt, 'add_topic'):
        tt.add_topic(args.topic)
    elif hasattr(tt, 'touch'):
        tt.touch(message_id=f"manual_{args.topic}", content=args.topic, entities=[args.topic])
    print(json.dumps({"status": "ok", "topic": args.topic}, ensure_ascii=False))


def cmd_topic_remove(args):
    e = get_engine()
    tt = getattr(e, '_topic_tree', None)
    if not tt: return print(json.dumps({"error": "no topic tree"}))
    if hasattr(tt, 'remove_topic'):
        tt.remove_topic(args.topic)
    print(json.dumps({"status": "ok", "topic": args.topic}, ensure_ascii=False))


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
    st = sp.add_parser("stats")
    st.add_argument("--sid", type=str, default=None)
    sp.add_parser("compress")
    sp.add_parser("topics")
    sp.add_parser("topic-tree")

    # Write ops
    ts = sp.add_parser("summary")
    ts.add_argument("block_id")
    ts.add_argument("text", nargs="+")
    ta = sp.add_parser("topic-add")
    ta.add_argument("topic")
    tr = sp.add_parser("topic-remove")
    tr.add_argument("topic")
