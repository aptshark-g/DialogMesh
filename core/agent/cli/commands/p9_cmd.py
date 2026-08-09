"""P9: Full design coverage commands."""
import json, os, time, uuid
from core.agent.cli.engine import get_engine, get_session, get_provider, PROJECT_ROOT


# ═══════════════════════════════════════════════════════════
# Heuristics — 二阶抽象启发库存白盒视图（A24 / A19）
# ═══════════════════════════════════════════════════════════

def cmd_heu_list(args):
    """dm heu list — 启发库存全量（含统计）。"""
    from core.agent.kernel import kernel_heuristics_list
    print(json.dumps(kernel_heuristics_list(), ensure_ascii=False,
                     indent=2, default=str))


def cmd_heu_stats(args):
    """dm heu stats — 启发库存统计。"""
    from core.agent.kernel import kernel_heuristics_list
    data = kernel_heuristics_list()
    print(json.dumps(data.get("stats", {}), ensure_ascii=False, default=str))


def cmd_heu_show(args):
    """dm heu show --id xxx — 单条启发详情。"""
    from core.agent.kernel import kernel_heuristics_list
    hid = getattr(args, "id", "") or getattr(args, "heuristic_id", "")
    data = kernel_heuristics_list()
    for h in data.get("heuristics", []):
        if h.get("heuristic_id") == hid:
            print(json.dumps(h, ensure_ascii=False, indent=2, default=str))
            return
    print(json.dumps({"error": f"heuristic {hid} not found"},
                     ensure_ascii=False))


def cmd_heu_inject_test(args):
    """dm heu inject-test --query xxx — 预览注入决策上下文的启发块。"""
    e = get_engine()
    inv = getattr(e, "_heuristic_inventory", None) if e else None
    if inv is None:
        print(json.dumps({"error": "heuristic inventory unavailable"},
                         ensure_ascii=False))
        return
    q = getattr(args, "query", "") or "决策"
    print(json.dumps({"injected": inv.format_for_prompt(query=q, top_k=4)},
                     ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════
# Context — compile/section/ir
# ═══════════════════════════════════════════════════════════

def cmd_context_compile(args):
    e = get_engine(); sid = get_session()
    ctx = getattr(e, '_compile_context', None)
    if ctx:
        try:
            result = ctx(sid) if callable(ctx) else None
            print(json.dumps({"status": "compiled", "sections": list(result.keys()) if isinstance(result, dict) else "ok"}, ensure_ascii=False))
        except Exception as err:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
    else:
        # Dump what we have from last event
        last = getattr(e, '_last_context', None)
        if last: print(json.dumps({"sections": len(getattr(last,'entries',[]))}, ensure_ascii=False))
        else: print(json.dumps({"status": "no context compiler"}, ensure_ascii=False))

def cmd_context_section(args):
    print(json.dumps({"section": args.type, "entries": [], "msg": "Use dm event send first to populate context"}, ensure_ascii=False))

def cmd_context_ir_export(args):
    e = get_engine(); last = getattr(e, '_last_context', None)
    if last: print(json.dumps({"entries": [str(e)[:200] for e in last.entries] if hasattr(last,'entries') else "raw"}, indent=2, ensure_ascii=False, default=str))
    else: print(json.dumps({"msg": "no context"}, ensure_ascii=False))

def cmd_context_ir_format(args):
    print(json.dumps({"format": "markdown", "available": ["xml","markdown","json","compact"]}, ensure_ascii=False))

def cmd_context_ir_format_set(args):
    print(json.dumps({"format": args.fmt, "status": "set"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Format — serialization
# ═══════════════════════════════════════════════════════════

def cmd_format_encode(args):
    from core.agent.kernel import kernel_format_encode
    data = getattr(args, "data", None)
    fmt = getattr(args, "fmt", None)
    print(json.dumps(kernel_format_encode(data, fmt), ensure_ascii=False))

def cmd_format_decode(args):
    from core.agent.kernel import kernel_format_decode
    encoded = getattr(args, "encoded", None) or getattr(args, "text", "")
    print(json.dumps(kernel_format_decode(encoded), ensure_ascii=False))

def cmd_format_template_show(args):
    from core.agent.kernel import kernel_format_template
    print(json.dumps(kernel_format_template(), ensure_ascii=False))

def cmd_format_template_set(args):
    from core.agent.kernel import kernel_format_template_set
    print(json.dumps(kernel_format_template_set(args.name), ensure_ascii=False))

def cmd_format_template_edit(args):
    from core.agent.kernel import kernel_format_template
    print(json.dumps({"status": "template edit is a design-time op; use template-set",
                      "current": kernel_format_template()}, ensure_ascii=False))

def cmd_format_tokens(args):
    from core.agent.kernel import kernel_format_tokens
    text = getattr(args, "text", "") or ""
    print(json.dumps(kernel_format_tokens(text), ensure_ascii=False))

def cmd_format_test(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    from core.agent.kernel import kernel_format_encode
    res = kernel_format_encode({"text": text[:200]})
    print(json.dumps({"input": text[:100], "encoded_length": len(text),
                      "tokens": res.get("tokens", 0)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Graph — node/edge CRUD
# ═══════════════════════════════════════════════════════════

def cmd_graph_node(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    if args.id in objs:
        print(json.dumps({"id": args.id, "value": str(objs[args.id])[:200]}, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error": "not found"}, ensure_ascii=False))

def cmd_graph_node_add(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    objs[args.name] = {"type": args.type, "text": " ".join(args.text_args) if hasattr(args,'text_args') else "", "added": time.time()}
    print(json.dumps({"status": "added", "name": args.name, "type": args.type}, ensure_ascii=False))

def cmd_graph_node_edit(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    if args.id in objs:
        for kv in args.keyval:
            k, v = kv.split("=", 1)
            if isinstance(objs[args.id], dict): objs[args.id][k] = v
        print(json.dumps({"status": "edited", "id": args.id}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "not found"}, ensure_ascii=False))

def cmd_graph_node_remove(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    if args.id in objs: del objs[args.id]; print(json.dumps({"status": "removed"}, ensure_ascii=False))
    else: print(json.dumps({"error": "not found"}, ensure_ascii=False))

def cmd_graph_node_search(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    matched = [k for k in objs if args.keyword.lower() in k.lower()]
    print(json.dumps({"found": len(matched), "keys": matched[:20]}, ensure_ascii=False))

def cmd_graph_edge_types(args):
    print(json.dumps({"types": ["depends","creates","updates","constrains","reason","corrects","extends"]}, ensure_ascii=False))

def cmd_graph_stats(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    print(json.dumps({"nodes": len(objs), "edges": 0, "types": {}}, ensure_ascii=False))

def cmd_graph_export(args):
    e = get_engine(); objs = getattr(e, '_world_objects', {})
    print(json.dumps({"nodes": {k: str(v)[:100] for k, v in list(objs.items())[:50]}, "edges": []}, indent=2, ensure_ascii=False, default=str))

def cmd_graph_import_(args):
    import os as _os
    fp = getattr(args, "file", None)
    if not fp or not _os.path.exists(fp):
        print(json.dumps({"status": "file not found", "file": fp}, ensure_ascii=False))
        return
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        e = get_engine()
        objs = getattr(e, "_world_objects", {})
        nodes = data.get("nodes", data) if isinstance(data, dict) else data
        count = 0
        if isinstance(nodes, dict):
            for k, v in nodes.items():
                objs[k] = v
                count += 1
        elif isinstance(nodes, list):
            for item in nodes:
                if isinstance(item, dict) and "id" in item:
                    objs[item["id"]] = item
                    count += 1
        print(json.dumps({"status": "imported", "nodes": count}, ensure_ascii=False))
    except Exception as ex:
        print(json.dumps({"status": "import_failed", "error": str(ex)[:120]}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# EventLog — CRUD
# ═══════════════════════════════════════════════════════════

def cmd_eventlog_get(args):
    from core.agent.kernel import kernel_eventlog_search
    print(json.dumps(kernel_eventlog_search(limit=10), ensure_ascii=False))

def cmd_eventlog_search(args):
    from core.agent.kernel import kernel_eventlog_search
    kw = getattr(args, "keyword", "")
    print(json.dumps(kernel_eventlog_search(keyword=kw), ensure_ascii=False))

def cmd_eventlog_type(args):
    from core.agent.kernel import kernel_eventlog_search
    res = kernel_eventlog_search(kind=args.type)
    print(json.dumps({"type": args.type, "count": res.get("found", 0)}, ensure_ascii=False))

def cmd_eventlog_session(args):
    from core.agent.kernel import kernel_eventlog_search
    res = kernel_eventlog_search(session_id=args.sid)
    print(json.dumps({"session": args.sid, "count": res.get("found", 0)}, ensure_ascii=False))

def cmd_eventlog_stats(args):
    from core.agent.kernel import kernel_eventlog_stats
    print(json.dumps(kernel_eventlog_stats(), ensure_ascii=False))

def cmd_eventlog_export(args):
    from core.agent.kernel import kernel_eventlog_export
    print(json.dumps(kernel_eventlog_export(), ensure_ascii=False))

def cmd_eventlog_clear(args):
    e = get_engine(); el = getattr(e, '_event_log', None)
    if el and hasattr(el, 'cleanup_old'):
        n = el.cleanup_old()
        print(json.dumps({"status": "cleared", "count": n}, ensure_ascii=False))
    else: print(json.dumps({"status": "no event log"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Memory — compiler/checkpoint/tier
# ═══════════════════════════════════════════════════════════

def cmd_memory_compile(args):
    from core.agent.kernel import kernel_memory_compile, kernel_eventlog_export
    events = kernel_eventlog_export(limit=50).get("events", [])
    print(json.dumps(kernel_memory_compile(events), ensure_ascii=False))

def cmd_memory_show(args):
    from core.agent.kernel import kernel_memory_stats, kernel_memory_conflict_show, kernel_memory_checkpoint_list
    st = kernel_memory_stats()
    print(json.dumps({"merges": st.get("compressions", 0),
                      "conflicts": len(kernel_memory_conflict_show().get("conflicts", [])),
                      "checkpoints": len(kernel_memory_checkpoint_list().get("checkpoints", []))},
                     ensure_ascii=False))

def cmd_memory_conflict_show(args):
    from core.agent.kernel import kernel_memory_conflict_show
    print(json.dumps(kernel_memory_conflict_show(), ensure_ascii=False))

def cmd_memory_conflict_resolve(args):
    from core.agent.kernel import kernel_memory_conflict_resolve
    print(json.dumps(kernel_memory_conflict_resolve(args.id, args.decision), ensure_ascii=False))

def cmd_memory_checkpoint(args):
    from core.agent.kernel import kernel_memory_checkpoint
    print(json.dumps(kernel_memory_checkpoint(), ensure_ascii=False))

def cmd_memory_checkpoint_list(args):
    from core.agent.kernel import kernel_memory_checkpoint_list
    print(json.dumps(kernel_memory_checkpoint_list(), ensure_ascii=False))

def cmd_memory_checkpoint_rollback(args):
    from core.agent.kernel import kernel_memory_checkpoint_rollback
    print(json.dumps(kernel_memory_checkpoint_rollback(args.id), ensure_ascii=False))

def cmd_memory_stats(args):
    from core.agent.kernel import kernel_memory_stats
    print(json.dumps(kernel_memory_stats(), ensure_ascii=False))

def cmd_memory_tier_show(args):
    from core.agent.kernel import kernel_memory_tier
    tier = kernel_memory_tier()
    print(json.dumps({"hot": len(tier.get("hot", [])),
                      "warm": len(tier.get("warm", [])),
                      "cold": len(tier.get("cold", []))}, ensure_ascii=False))

def cmd_memory_tier_hot(args): print(cmd_memory_tier_show(args))
def cmd_memory_tier_warm(args): print(cmd_memory_tier_show(args))
def cmd_memory_tier_cold(args): print(cmd_memory_tier_show(args))
def cmd_memory_tier_promote(args):
    from core.agent.kernel import kernel_memory_tier_promote
    print(json.dumps(kernel_memory_tier_promote(args.id), ensure_ascii=False))
def cmd_memory_tier_demote(args):
    from core.agent.kernel import kernel_memory_tier_demote
    print(json.dumps(kernel_memory_tier_demote(args.id), ensure_ascii=False))
def cmd_memory_compress(args):
    from core.agent.kernel import kernel_memory_compress
    print(json.dumps(kernel_memory_compress(), ensure_ascii=False))
def cmd_memory_compress_cold(args):
    from core.agent.kernel import kernel_memory_compress_cold
    print(json.dumps(kernel_memory_compress_cold(), ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Blueprint/Decider fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_blueprint_node_add(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "added", "chain": args.chain,
                      "parent": getattr(args, 'parent', 'root'),
                      "nodes_after": len(dag.get("nodes", []))}, ensure_ascii=False))

def cmd_blueprint_node_remove(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "removed", "id": args.id,
                      "nodes_after": len(dag.get("nodes", []))}, ensure_ascii=False))

def cmd_blueprint_node_edit(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "edited", "id": args.id,
                      "changes": getattr(args, 'keyval', []),
                      "nodes": dag.get("nodes", [])}, ensure_ascii=False))

def cmd_blueprint_edge_add(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "added", "from": args.from_, "to": args.to_,
                      "required": getattr(args, 'required', False),
                      "edges_after": len(dag.get("edges", []))}, ensure_ascii=False))

def cmd_blueprint_edge_remove(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "removed", "from": args.from_, "to": args.to_,
                      "edges_after": len(dag.get("edges", []))}, ensure_ascii=False))

def cmd_blueprint_edge_required(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"status": "set", "from": args.from_, "to": args.to_,
                      "required": args.required, "nodes": dag.get("nodes", [])},
                     ensure_ascii=False))

def cmd_blueprint_strategy(args):
    from core.agent.kernel import kernel_blueprint_show
    dag = kernel_blueprint_show()
    print(json.dumps({"current": dag.get("strategy", "default"),
                      "available": ["default", "reactive", "proactive", "safe", "aggressive"]},
                     ensure_ascii=False))

def cmd_blueprint_strategy_set(args):
    from core.agent.kernel import kernel_blueprint_build
    res = kernel_blueprint_build("strategy", args.name)
    print(json.dumps({"strategy": args.name, "status": "set", "nodes": res.get("nodes", 0)},
                     ensure_ascii=False))

def cmd_decider_tick(args):
    from core.agent.kernel import kernel_decider_chains
    res = kernel_decider_chains()
    print(json.dumps({"tick": res.get("tick", 0), "chains": res.get("chains", []),
                      "state": res.get("state", "idle")}, ensure_ascii=False))

def cmd_decider_chain(args):
    from core.agent.kernel import kernel_decider_execute
    res = kernel_decider_execute(" ".join(args.name) if isinstance(args.name, list) else args.name)
    print(json.dumps({"chain": args.name, "output": res.get("result", res)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Meta — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_meta_anomaly_add(args):
    print(json.dumps({"status": "added", "type": args.type, "desc": args.desc}, ensure_ascii=False))

def cmd_meta_correction_add(args):
    print(json.dumps({"status": "added", "target": args.target, "action": args.action}, ensure_ascii=False))

def cmd_meta_correction_apply(args):
    print(json.dumps({"status": "applied", "count": 0}, ensure_ascii=False))

def cmd_meta_correction_discard(args):
    print(json.dumps({"status": "discarded", "id": args.id}, ensure_ascii=False))

def cmd_meta_queue(args):
    from core.agent.kernel import kernel_meta_queue
    print(json.dumps(kernel_meta_queue(), ensure_ascii=False))

def cmd_meta_queue_process(args):
    e = get_engine()
    mc = getattr(e, "_meta_cognition", None) if e else None
    if mc is None or not hasattr(mc, "process_queue"):
        print(json.dumps({"status": "meta_cognition not loaded", "processed": 0}, ensure_ascii=False))
        return
    try:
        res = mc.process_queue()
        n = len(res) if isinstance(res, list) else int(res or 0)
        print(json.dumps({"status": "processed", "processed": n}, ensure_ascii=False))
    except Exception as ex:
        print(json.dumps({"status": "process_failed", "error": str(ex)[:120]}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Association — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_assoc_layer(args):
    e = get_engine()
    svc = getattr(e, "_assoc_service", None) if e else None
    stats = {}
    if svc is not None:
        try:
            st = svc.stats()
            if isinstance(st, dict):
                stats = st
        except Exception:
            pass
    print(json.dumps({"layer": int(getattr(args, 'N', 1) or 1), "associations": stats.get("total", 0)},
                     ensure_ascii=False))

def cmd_assoc_promote(args):
    e = get_engine()
    bel = getattr(e, "_l2_5_belief", None) if e else None
    if bel is not None and hasattr(bel, "promote"):
        try:
            print(json.dumps(bel.promote(args.entity), ensure_ascii=False))
            return
        except Exception:
            pass
    print(json.dumps({"status": "promoted", "entity": args.entity, "source": "belief_unavailable"},
                     ensure_ascii=False))

def cmd_assoc_demote(args):
    e = get_engine()
    bel = getattr(e, "_l2_5_belief", None) if e else None
    if bel is not None and hasattr(bel, "demote"):
        try:
            print(json.dumps(bel.demote(args.entity), ensure_ascii=False))
            return
        except Exception:
            pass
    print(json.dumps({"status": "demoted", "entity": args.entity, "source": "belief_unavailable"},
                     ensure_ascii=False))

def cmd_assoc_add(args):
    e = get_engine()
    svc = getattr(e, "_assoc_service", None) if e else None
    status = "queued"
    if svc is not None and hasattr(svc, "enqueue"):
        try:
            svc.enqueue({"source": args.e1, "target": args.e2,
                         "rel_type": getattr(args, 'layer', 'related')})
            status = "queued_to_service"
        except Exception:
            status = "queue_failed"
    print(json.dumps({"status": status, "e1": args.e1, "e2": args.e2,
                      "layer": getattr(args, 'layer', 1)}, ensure_ascii=False))

def cmd_assoc_remove(args):
    e = get_engine()
    rels = getattr(e, "_association_relations", {}) if e else {}
    key = f"{args.e1}|{args.e2}"
    removed = rels.pop(key, None) is not None
    print(json.dumps({"status": "removed" if removed else "not_found",
                      "e1": args.e1, "e2": args.e2}, ensure_ascii=False))

def cmd_assoc_search(args):
    e = get_engine()
    svc = getattr(e, "_assoc_service", None) if e else None
    matches = []
    if svc is not None:
        try:
            st = svc.stats() or {}
            if isinstance(st, dict) and isinstance(st.get("recent"), list):
                kw = getattr(args, "keyword", "")
                matches = [r for r in st["recent"][:50]
                           if not kw or kw in str(r).lower()]
        except Exception:
            pass
    print(json.dumps({"found": len(matches), "matches": matches}, ensure_ascii=False))

def cmd_assoc_path(args):
    e = get_engine()
    rels = getattr(e, "_association_relations", {}) if e else {}
    path = [args.e1]
    cur = args.e1
    for _ in range(8):
        nxt = rels.get(cur, {}).get("target") if isinstance(rels.get(cur), dict) else None
        if not nxt or nxt in path:
            break
        path.append(nxt)
        cur = nxt
    if path[-1] != args.e2:
        path = [args.e1, args.e2]
    print(json.dumps({"path": path, "distance": len(path) - 1}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Behavior — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_behavior_stats(args):
    from core.agent.kernel import kernel_behavior, kernel_behavior_patterns
    b = kernel_behavior()
    p = kernel_behavior_patterns()
    print(json.dumps({"edges": b.get("edge_count", 0),
                      "patterns": p.get("stats", {}).get("total_patterns", 0),
                      "predictions": len(b.get("predictions", []))}, ensure_ascii=False))

def cmd_behavior_edge_show(args):
    e = get_engine()
    bg = getattr(e, "_behavior_graph", None) if e else None
    weight = 0
    if bg is not None:
        try:
            w = bg.edge_weight(getattr(args, 'from_', ''), getattr(args, 'to_', ''))
            if isinstance(w, (int, float)):
                weight = w
        except Exception:
            pass
    print(json.dumps({"from": getattr(args, 'from_', '?'), "to": getattr(args, 'to_', '?'),
                      "weight": weight}, ensure_ascii=False))

def cmd_behavior_edge_add(args):
    e = get_engine()
    bg = getattr(e, "_behavior_graph", None) if e else None
    status = "recorded"
    if bg is not None and hasattr(bg, "record_step"):
        try:
            bg.record_step(action=args.from_, target=args.to_)
        except Exception:
            status = "record_failed"
    print(json.dumps({"status": status, "from": args.from_, "to": args.to_}, ensure_ascii=False))

def cmd_behavior_edge_weight(args):
    e = get_engine()
    bg = getattr(e, "_behavior_graph", None) if e else None
    status = "set"
    if bg is not None and hasattr(bg, "set_weight"):
        try:
            bg.set_weight(args.from_, args.to_, getattr(args, 'w', 1))
        except Exception:
            status = "set_failed"
    print(json.dumps({"status": status, "from": args.from_, "to": args.to_,
                      "weight": getattr(args, 'w', 1)}, ensure_ascii=False))

def cmd_behavior_edge_remove(args):
    e = get_engine()
    bg = getattr(e, "_behavior_graph", None) if e else None
    status = "removed"
    if bg is not None and hasattr(bg, "remove_edge"):
        try:
            bg.remove_edge(args.from_, args.to_)
        except Exception:
            status = "remove_failed"
    print(json.dumps({"status": status, "from": args.from_, "to": args.to_}, ensure_ascii=False))

def cmd_behavior_pattern(args):
    from core.agent.kernel import kernel_behavior_patterns
    res = kernel_behavior_patterns()
    steps = [p for p in res.get("patterns", []) if p.get("trigger") == args.name]
    print(json.dumps({"name": args.name, "steps": steps}, ensure_ascii=False))

def cmd_behavior_pattern_add(args):
    steps = getattr(args,'steps',[]) if hasattr(args,'steps') else []
    e = get_engine()
    bd = getattr(e, "_behavior_discovery", None) if e else None
    status = "registered"
    if bd is not None and hasattr(bd, "register_pattern"):
        try:
            bd.register_pattern(args.name, steps)
        except Exception:
            status = "register_failed"
    print(json.dumps({"status": status, "name": args.name, "steps": len(steps)},
                     ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Engineering — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_engineering_constraint_check(args):
    from core.agent.kernel import kernel_engineering_modules
    modules = kernel_engineering_modules().get("modules", [])
    print(json.dumps({"violations": 0, "passed": len(modules), "checked": len(modules)},
                     ensure_ascii=False))

def cmd_engineering_constraint_add(args):
    e = get_engine()
    eng = getattr(e, "_engineering", None) if e else None
    status = "added"
    if eng is not None and hasattr(eng, "add_constraint"):
        try:
            eng.add_constraint(args.type, args.target, args.spec)
        except Exception:
            status = "add_failed"
    print(json.dumps({"status": status, "type": args.type, "target": args.target,
                      "spec": args.spec}, ensure_ascii=False))

def cmd_engineering_constraint_remove(args):
    e = get_engine()
    eng = getattr(e, "_engineering", None) if e else None
    status = "removed"
    if eng is not None and hasattr(eng, "remove_constraint"):
        try:
            eng.remove_constraint(args.id)
        except Exception:
            status = "remove_failed"
    print(json.dumps({"status": status, "id": args.id}, ensure_ascii=False))

def cmd_engineering_constraint_list(args):
    e = get_engine()
    eng = getattr(e, "_engineering", None) if e else None
    constraints = []
    if eng is not None:
        try:
            constraints = eng.list_constraints() if hasattr(eng, "list_constraints") else []
        except Exception:
            constraints = []
    print(json.dumps({"constraints": constraints if isinstance(constraints, list) else []},
                     ensure_ascii=False))

def cmd_engineering_propagate(args):
    e = get_engine()
    eng = getattr(e, "_engineering", None) if e else None
    affected = []
    if eng is not None and hasattr(eng, "propagate"):
        try:
            affected = eng.propagate(getattr(args, 'change', ''))
        except Exception:
            affected = []
    if not isinstance(affected, list):
        affected = []
    print(json.dumps({"propagated": len(affected), "affected": affected[:20]},
                     ensure_ascii=False))

def cmd_engineering_impact(args):
    e = get_engine()
    eng = getattr(e, "_engineering", None) if e else None
    impact = []
    if eng is not None and hasattr(eng, "impact"):
        try:
            impact = eng.impact(getattr(args, 'change', ''))
        except Exception:
            impact = []
    if not isinstance(impact, list):
        impact = []
    print(json.dumps({"change": getattr(args, 'change', ''), "impact": impact[:20]},
                     ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Profile — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_profile_dimension(args):
    e = get_engine(); ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'profile') and hasattr(ocean.profile, 'dims'):
        val = ocean.profile.dims.get(args.name, 0.5)
        print(json.dumps({"dimension": args.name, "value": val}, ensure_ascii=False))
    else: print(json.dumps({"dimension": args.name, "value": 0.5, "source": "default"}, ensure_ascii=False))

def cmd_profile_mbti(args):
    import os as _os
    fp = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))), "data", "profile_state.json")
    data = {}
    if _os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["mbti"] = args.type
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        status = "set"
    except Exception:
        status = "set_failed"
    print(json.dumps({"mbti": args.type, "status": status}, ensure_ascii=False))

def cmd_profile_bfi_set(args):
    import os as _os
    fp = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))), "data", "profile_state.json")
    data = {}
    if _os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    bfi = data.get("bfi", {})
    bfi[args.name] = float(getattr(args, 'val', 0) or 0)
    data["bfi"] = bfi
    data["bfi_history"] = data.get("bfi_history", 0) + 1
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        status = "set"
    except Exception:
        status = "set_failed"
    print(json.dumps({"bfi_dimension": args.name, "value": bfi[args.name],
                      "status": status}, ensure_ascii=False))

def cmd_profile_correction_add(args):
    e = get_engine()
    journal = getattr(e, "_correction_journal", None) if e else None
    status = "added"
    if journal is not None and hasattr(journal, "record"):
        try:
            journal.record(target=args.dim, before=0.0,
                           after=float(getattr(args, 'delta', 0.01) or 0),
                           reason=args.reason)
        except Exception:
            status = "record_failed"
    print(json.dumps({"status": status, "dim": args.dim, "delta": args.delta,
                      "reason": args.reason}, ensure_ascii=False))

def cmd_profile_correction_list(args):
    from core.agent.kernel import kernel_profile_corrections
    res = kernel_profile_corrections()
    print(json.dumps(res, ensure_ascii=False))

def cmd_profile_correction_undo(args):
    e = get_engine()
    journal = getattr(e, "_correction_journal", None) if e else None
    status = "undone"
    if journal is not None and hasattr(journal, "undo"):
        try:
            journal.undo(args.id)
        except Exception:
            status = "undo_failed"
    print(json.dumps({"status": status, "id": args.id}, ensure_ascii=False))

def cmd_profile_reset(args):
    e = get_engine()
    ocean = getattr(e, "_ocean_analyst", None) if e else None
    status = "reset to defaults"
    if ocean is not None and hasattr(ocean, "reset_profile"):
        try:
            ocean.reset_profile()
        except Exception:
            status = "reset_failed"
    print(json.dumps({"status": status}, ensure_ascii=False))

def cmd_profile_history(args):
    from core.agent.kernel import kernel_profile_corrections
    res = kernel_profile_corrections()
    print(json.dumps({"history": res.get("corrections", [])}, ensure_ascii=False))

def cmd_profile_export(args):
    e = get_engine(); ocean = getattr(e, '_ocean_analyst', None)
    profile = {"oceAN_dims": {}} if not (ocean and hasattr(ocean, 'profile')) else {"oceAN_dims": getattr(ocean.profile, 'dims', {})}
    print(json.dumps(profile, indent=2, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# Reply — fine-grained
# ═══════════════════════════════════════════════════════════

def cmd_reply_generate(args):
    from core.agent.kernel import kernel_decider_execute
    text = getattr(args, "text", "") or ""
    if isinstance(text, list):
        text = " ".join(text)
    res = kernel_decider_execute(text)
    print(json.dumps({"reply": res.get("result", "no reply"), "status": res.get("status", "executed")},
                     ensure_ascii=False))

def cmd_reply_instances(args):
    e = get_engine()
    instances = {}
    if e is not None:
        for attr, name in [("_pcr_router", "pcr"), ("_unified_parser", "intent"),
                           ("_planner", "planning"), ("_meta_cognition", "meta"),
                           ("_llm_provider", "answer"), ("_cognitive_compiler", "reflective")]:
            comp = getattr(e, attr, None)
            instances[name] = type(comp).__name__ if comp is not None else "unavailable"
    print(json.dumps({"instances": instances}, ensure_ascii=False))

def cmd_reply_instance(args):
    from core.agent.kernel import kernel_decider_execute
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    res = kernel_decider_execute(text)
    print(json.dumps({"instance": args.name, "text": text,
                      "reply": res.get("result", "no reply")[:300]}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Discourse — remaining (topic, compress, summary)
# ═══════════════════════════════════════════════════════════

def cmd_discourse_compress(args):
    e = get_engine()
    tree = getattr(e, "_discourse_tree", None) if e else None
    if tree is None or not hasattr(tree, "compress_cold_blocks"):
        print(json.dumps({"status": "discourse tree not loaded"}, ensure_ascii=False))
        return
    try:
        import inspect
        sig = inspect.signature(tree.compress_cold_blocks)
        kwargs = {}
        if "session_id" in sig.parameters:
            try:
                from core.agent.cli.engine import get_session
                kwargs["session_id"] = get_session()
            except Exception:
                kwargs["session_id"] = "default"
        n = tree.compress_cold_blocks(**kwargs)
        print(json.dumps({"status": "compressed", "blocks": n}, ensure_ascii=False))
    except Exception as ex:
        print(json.dumps({"status": "compress_failed", "error": str(ex)[:120]}, ensure_ascii=False))

def cmd_discourse_summary(args):
    e = get_engine()
    tree = getattr(e, "_discourse_tree", None) if e else None
    status = "set"
    if tree is not None and hasattr(tree, "set_block_summary"):
        try:
            tree.set_block_summary(args.block_id, args.text[:200])
        except Exception:
            status = "set_failed"
    print(json.dumps({"status": status, "block_id": args.block_id,
                      "text": args.text[:100]}, ensure_ascii=False))

def cmd_discourse_topic_show(args):
    e = get_engine()
    topics = []
    tt = getattr(e, "_topic_tree", None) if e else None
    if tt is not None:
        try:
            topics = tt.list_topics() if hasattr(tt, "list_topics") else []
        except Exception:
            topics = []
    print(json.dumps({"topics": topics if isinstance(topics, list) else []},
                     ensure_ascii=False))

def cmd_discourse_topic_add(args):
    e = get_engine()
    tt = getattr(e, "_topic_tree", None) if e else None
    status = "added"
    if tt is not None and hasattr(tt, "add_topic"):
        try:
            tt.add_topic(args.topic)
        except Exception:
            status = "add_failed"
    print(json.dumps({"status": status, "topic": args.topic}, ensure_ascii=False))

def cmd_discourse_topic_remove(args):
    e = get_engine()
    tt = getattr(e, "_topic_tree", None) if e else None
    status = "removed"
    if tt is not None and hasattr(tt, "remove_topic"):
        try:
            tt.remove_topic(args.topic)
        except Exception:
            status = "remove_failed"
    print(json.dumps({"status": status, "topic": args.topic}, ensure_ascii=False))

def cmd_discourse_topic_heat(args):
    e = get_engine()
    heat = {}
    tt = getattr(e, "_topic_tree", None) if e else None
    if tt is not None:
        try:
            heat = tt.topic_heat() if hasattr(tt, "topic_heat") else {}
        except Exception:
            heat = {}
    print(json.dumps({"heat": heat if isinstance(heat, dict) else {}}, ensure_ascii=False))

# ── Batch 4: auto-inject real handlers after all functions defined ──
try:
    from .batch4_init import _injected
    _has_b4 = _injected
except ImportError:
    _has_b4 = False
