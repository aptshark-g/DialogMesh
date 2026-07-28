"""P7: Fine-grained CRUD — discourse split/merge, task node/edge, graph."""
import json
from core.agent.cli.engine import get_engine, get_session


# ── Discourse split/merge/delete/promote/demote ──

def cmd_discourse_split(args):
    e = get_engine(); t = getattr(e, '_discourse_tree', None)
    if not t: return print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
    sid = get_session()
    try:
        result = t.split_block(sid, args.block_id, args.position)
        print(json.dumps({"status": "split", "blocks": [result] if result else []}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def cmd_discourse_merge(args):
    e = get_engine(); t = getattr(e, '_discourse_tree', None)
    if not t: return print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
    sid = get_session()
    try:
        result = t.merge_blocks(sid, args.block_a.split(","))
        print(json.dumps({"status": "merged", "result": str(result)}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def cmd_discourse_delete(args):
    e = get_engine(); t = getattr(e, '_discourse_tree', None)
    if not t: return print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
    sid = get_session()
    try:
        t.delete_block(sid, args.block_id)
        print(json.dumps({"status": "deleted", "block_id": args.block_id}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def cmd_discourse_promote(args):
    e = get_engine(); t = getattr(e, '_discourse_tree', None)
    if not t: return print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
    try:
        t.promote_block(get_session(), args.block_id, int(args.levels or 1))
        print(json.dumps({"status": "promoted", "block_id": args.block_id}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def cmd_discourse_demote(args):
    e = get_engine(); t = getattr(e, '_discourse_tree', None)
    if not t: return print(json.dumps({"error": "not loaded"}, ensure_ascii=False))
    try:
        t.demote_block(get_session(), args.block_id, int(args.levels or 1))
        print(json.dumps({"status": "demoted", "block_id": args.block_id}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


# ── Task node/edge CRUD ──

def _task_graph_path(sid):
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    d = os.path.join(root, "data", "task_graphs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{sid}.json")


def _load_tg(sid):
    import os
    p = _task_graph_path(sid)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"nodes": [], "edges": []}


def _save_tg(sid, tg):
    with open(_task_graph_path(sid), "w", encoding="utf-8") as f:
        json.dump(tg, f, indent=2, ensure_ascii=False)


def cmd_task_node_add(args):
    tg = _load_tg(get_session())
    import uuid
    node = {"id": str(uuid.uuid4())[:8], "name": args.name, "status": "pending",
            "dependencies": args.deps.split(",") if getattr(args, 'deps', None) else []}
    tg.setdefault("nodes", []).append(node)
    _save_tg(get_session(), tg)
    print(json.dumps({"status": "added", "node": node}, ensure_ascii=False))


def cmd_task_node_edit(args):
    tg = _load_tg(get_session())
    for n in tg.get("nodes", []):
        if n["id"] == args.id:
            for kv in getattr(args, 'keyval', []):
                k, v = kv.split("=", 1)
                n[k] = v
            break
    _save_tg(get_session(), tg)
    print(json.dumps({"status": "edited", "id": args.id}, ensure_ascii=False))


def cmd_task_node_remove(args):
    tg = _load_tg(get_session())
    tg["nodes"] = [n for n in tg.get("nodes", []) if n["id"] != args.id]
    tg["edges"] = [e for e in tg.get("edges", []) if e.get("source") != args.id and e.get("target") != args.id]
    _save_tg(get_session(), tg)
    print(json.dumps({"status": "removed", "id": args.id}, ensure_ascii=False))


def cmd_task_edge_add(args):
    tg = _load_tg(get_session())
    import uuid
    edge = {"id": f"e_{args.from_[:4]}_{args.to_[:4]}", "source": args.from_, "target": args.to_}
    tg.setdefault("edges", []).append(edge)
    _save_tg(get_session(), tg)
    print(json.dumps({"status": "added", "edge": edge}, ensure_ascii=False))


def cmd_task_edge_remove(args):
    tg = _load_tg(get_session())
    tg["edges"] = [e for e in tg.get("edges", []) if e.get("source") != args.from_ and e.get("target") != args.to_]
    _save_tg(get_session(), tg)
    print(json.dumps({"status": "removed", "from": args.from_, "to": args.to_}, ensure_ascii=False))


def register_cmds(subparsers):
    # Don't create a new 'discourse' parser — add subcommands to existing
    pass  # dispatch handled via entry.py directly
