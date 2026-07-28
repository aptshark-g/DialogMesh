"""Batch 3: Real data handlers for placeholder stubs."""
import json, os, time
from core.agent.cli.engine import get_engine, get_session, PROJECT_ROOT


# ═══════════════════════════════════════════════════════════
# session clear/delete
# ═══════════════════════════════════════════════════════════

def cmd_session_clear(args):
    """Clear messages for current session but keep session record."""
    sid = get_session()
    sess_path = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    if os.path.exists(sess_path):
        with open(sess_path, encoding="utf-8") as f:
            sessions = json.load(f)
        if sid in sessions:
            sessions[sid]["messages"] = []
            with open(sess_path, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
            print(json.dumps({"status":"cleared","session_id":sid}, ensure_ascii=False))
            return
    print(json.dumps({"status":"cleared","session_id":sid}, ensure_ascii=False))

def cmd_session_delete(args):
    """Delete session and its task graph."""
    sid = args.id or get_session()
    sess_path = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    tg_path = os.path.join(PROJECT_ROOT, "data", "task_graphs", f"{sid}.json")
    if os.path.exists(sess_path):
        with open(sess_path, encoding="utf-8") as f:
            sessions = json.load(f)
        if sid in sessions:
            del sessions[sid]
            with open(sess_path, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
    if os.path.exists(tg_path):
        os.remove(tg_path)
    print(json.dumps({"status":"deleted","session_id":sid}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# engine stats
# ═══════════════════════════════════════════════════════════

def cmd_engine_stats(args):
    e = get_engine()
    stats = getattr(e, '_stats', {}) or {}
    reg = getattr(e, '_registry', None)
    obs = getattr(e, '_observation_pool', None)
    info = {
        "subsystems": len(reg._instances) if reg else 0,
        "observations": obs.stats().get("total_bundles", 0) if obs else 0,
        "events_processed": getattr(e, '_turn_counter', 0),
        "uptime_seconds": time.time() - getattr(e, '_start_time', time.time()),
        **{k: v for k, v in stats.items() if isinstance(v, (int, float, str))}
    }
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


# ═══════════════════════════════════════════════════════════
# memory: read from engine DiscourseBlockTree
# ═══════════════════════════════════════════════════════════

def cmd_memory_real_show(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if not tree:
        return print(json.dumps({"hot":0,"warm":0,"cold":0,"merges":0,"conflicts":0}, ensure_ascii=False))
    sid = get_session()
    t = tree.get_tree(sid) if hasattr(tree, 'get_tree') else None
    stats = tree.get_stats(sid) if hasattr(tree, 'get_stats') else {}
    info = {
        "hot": sum(1 for b in (t.blocks.values() if t else []) if getattr(b,'temperature',2) == 0),
        "warm": sum(1 for b in (t.blocks.values() if t else []) if 1 <= getattr(b,'temperature',2) <= 2),
        "cold": sum(1 for b in (t.blocks.values() if t else []) if getattr(b,'temperature',2) >= 3),
        "total_blocks": stats.get("total_blocks", 0),
        "max_depth": stats.get("max_depth", 0),
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_memory_real_compile(args):
    e = get_engine()
    tree = getattr(e, '_discourse_tree', None)
    if tree and hasattr(tree, 'compress_cold_blocks'):
        n = tree.compress_cold_blocks(get_session())
        print(json.dumps({"status":"compressed","blocks":n}, ensure_ascii=False))
    else:
        print(json.dumps({"status":"no discourse tree"}, ensure_ascii=False))


def cmd_memory_real_stats(args):
    cmd_memory_real_show(args)


# ═══════════════════════════════════════════════════════════
# format: read from context assembler
# ═══════════════════════════════════════════════════════════

def cmd_format_real_encode(args):
    e = get_engine()
    ca = getattr(e, '_context_assembler', None)
    if ca and hasattr(ca, 'encode'):
        result = ca.encode()
        print(json.dumps({"encoded": str(result)[:200], "tokens": len(str(result))}, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"encoded":"","tokens":0,"format":"markdown"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# association: read from association subscriber layers
# ═══════════════════════════════════════════════════════════

def cmd_assoc_real_show(args):
    e = get_engine()
    layers = {}
    for i, attr in enumerate(["_l1_modifier","_l1_5_completer","_l2_5_belief","_l3_validator"]):
        inst = getattr(e, attr, None)
        layers[f"L{i+1}"] = {"loaded": inst is not None, "type": type(inst).__name__ if inst else "missing"}
    print(json.dumps(layers, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# behavior real data
# ═══════════════════════════════════════════════════════════

def cmd_behavior_real_stats(args):
    e = get_engine()
    bg = getattr(e, '_behavior_graph', None)
    bd = getattr(e, '_behavior_discovery', None)
    info = {"edges": 0, "patterns": 0, "predictions": 0}
    if bg and hasattr(bg, 'graph'):
        info["edges"] = len(getattr(bg.graph, 'edges', []))
    if bd:
        info["discovery"] = type(bd).__name__
    print(json.dumps(info, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# reply show — from last event send
# ═══════════════════════════════════════════════════════════

def cmd_reply_real_show(args):
    e = get_engine()
    last = getattr(e, '_last_reply', None)
    if last:
        print(json.dumps({"last_reply": str(last)[:200], "length": len(str(last))}, ensure_ascii=False))
    else:
        print(json.dumps({"last_reply":"","turn_count":0}, ensure_ascii=False))
