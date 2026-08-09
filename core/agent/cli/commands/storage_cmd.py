"""CLI commands for Phase 1-3 storage subsystem (argparse-compatible).

dm chunk stats|search|add
dm graph entities|traverse
dm meta show|tag|cluster
dm tiered stats|archive|rehydrate   (G10-P2 分层存储)
"""
from __future__ import annotations

import argparse


def register_cmds(sp):
    """Register storage commands as argparse subparsers (matches other cmd modules)."""

    # ── chunk ──
    p = sp.add_parser("chunk", help="ChunkStore operations")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("stats", help="ChunkStore statistics")
    p_s = p2.add_parser("search", help="Vector search")
    p_s.add_argument("query", nargs="+")
    p_a = p2.add_parser("add", help="Add text to ChunkStore")
    p_a.add_argument("text", nargs="+")

    # ── graph ──
    p = sp.add_parser("rgraph", help="RelationGraph operations")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("entities", help="List entities")
    p_t = p2.add_parser("traverse", help="BFS traversal")
    p_t.add_argument("entity_id")
    p_t.add_argument("depth", nargs="?", default=2, type=int)

    # ── meta ──
    p = sp.add_parser("blockmeta", help="Block metadata operations")
    p2 = p.add_subparsers(dest="subcommand")
    p_s = p2.add_parser("show", help="Show block metadata")
    p_s.add_argument("block_id")
    p_t = p2.add_parser("tag", help="Add tags to block")
    p_t.add_argument("block_id")
    p_t.add_argument("tags", nargs="+")
    p_c = p2.add_parser("cluster", help="Recluster blocks")
    p_c.add_argument("cluster_id")
    p_c.add_argument("blocks", nargs="+")

    # ── tiered (G10-P2: TieredStorageManager) ──
    p = sp.add_parser("tiered", help="Tiered storage (Hot/Warm/Cold)")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("stats", help="Tiered storage statistics")
    p_a = p2.add_parser("archive", help="Archive expired warm sessions to cold")
    p_a.add_argument("--dry-run", action="store_true")
    p_r = p2.add_parser("rehydrate", help="Rehydrate cold session to warm")
    p_r.add_argument("session_id")

    # ── recall (B2-3 P1: 统一召回接口) ──
    p = sp.add_parser("recall", help="统一召回 (混合锚点+扩散+融合)")
    p.add_argument("query", nargs="+")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--weights", action="store_true",
                   help="显示各源置信度 (A18 参数白盒)")


# ═══════════════════════════════════════════════════════════
# Dispatch handlers (called from entry.py _dispatch_p8)
# ═══════════════════════════════════════════════════════════

def _engine():
    from core.agent.cli.engine import get_engine
    return get_engine()


def cmd_chunk_stats(args=None):
    """dm chunk stats — ChunkStore statistics."""
    e = _engine()
    cs = getattr(e, '_chunk_store', None)
    if not cs:
        return "ChunkStore not available"
    s = cs.stats()
    return "\n".join(f"  {k}: {v}" for k, v in s.items())


def cmd_chunk_search(args=None):
    """dm chunk search <query> — vector search."""
    e = _engine()
    cs = getattr(e, '_chunk_store', None)
    if not cs:
        return "ChunkStore not available"
    query = " ".join(getattr(args, "query", []) or [])
    if not query:
        return "Usage: dm chunk search <query>"
    results = cs.search(query, top_k=5)
    if not results:
        return f"No results for: {query}"
    lines = [f"  {a.atom_id[:8]} [{a.block_id[:8]}] {'✓' if a.chunkable else '✗'} {a.text[:60]}"
             for a in results]
    return "\n".join(lines)


def cmd_chunk_add(args=None):
    """dm chunk add <text> — add text to ChunkStore."""
    e = _engine()
    cs = getattr(e, '_chunk_store', None)
    if not cs:
        return "ChunkStore not available"
    text = " ".join(getattr(args, "text", []) or [])
    if not text:
        return "Usage: dm chunk add <text>"
    atom = cs.add_text(text, block_id=f"cli_{hash(text) & 0xFFFF:04x}")
    if atom:
        return f"Added: {atom.atom_id[:8]} (chunkable={atom.chunkable})"
    return "Duplicate — already in store"


def cmd_graph_entities(args=None):
    """dm graph entities — list RelationGraph entities."""
    e = _engine()
    rg = getattr(e, '_relation_graph', None)
    if not rg:
        return "RelationGraph not available"
    s = rg.stats()
    entities = getattr(rg._backend, 'entities', [])
    if not entities:
        return f"No entities stored. Total: {s['entities']} entities, {s['relationships']} rels"
    lines = [f"  {en.get('id','')[:30]:<32} {en.get('type',''):<12} conf={en.get('confidence',0):.2f}"
             for en in entities[:20]]
    return "\n".join(lines) + f"\n\nTotal: {s['entities']} entities, {s['relationships']} rels"


def cmd_graph_traverse(args=None):
    """dm graph traverse <entity_id> [depth] — BFS traversal."""
    e = _engine()
    rg = getattr(e, '_relation_graph', None)
    if not rg:
        return "RelationGraph not available"
    entity_id = getattr(args, "entity_id", "")
    depth = getattr(args, "depth", 2) or 2
    if not entity_id:
        return "Usage: dm graph traverse <entity_id> [depth=2]"
    nodes = rg.traverse(entity_id, depth=depth)
    return "\n".join(f"  {n}" for n in nodes) + f"\nDepth: {depth}, Nodes: {len(nodes)}"


def cmd_meta_show(args=None):
    """dm meta show <block_id> — show block metadata."""
    e = _engine()
    bm = getattr(e, '_block_meta', None)
    if not bm:
        return "BlockMeta not available"
    block_id = getattr(args, "block_id", "")
    if not block_id:
        return "Usage: dm meta show <block_id>"
    meta = bm.get(block_id)
    if not meta:
        return f"No metadata for block: {block_id}"
    return "\n".join([
        f"  summary:     {meta.summary[:80]}",
        f"  tags:        {', '.join(meta.tags) or '—'}",
        f"  cluster_id:  {meta.cluster_id or '—'}",
        f"  priority:    {meta.priority:.2f}",
        f"  chunkable:   {meta.chunkable}",
    ])


def cmd_meta_tag(args=None):
    """dm meta tag <block_id> <tag1> [tag2...]."""
    e = _engine()
    bm = getattr(e, '_block_meta', None)
    if not bm:
        return "BlockMeta not available"
    block_id = getattr(args, "block_id", "")
    tags = getattr(args, "tags", []) or []
    if not block_id or not tags:
        return "Usage: dm meta tag <block_id> <tag1> [tag2...]"
    bm.update_tags(block_id, tags)
    return f"Tagged {block_id}: {tags}"


def cmd_meta_cluster(args=None):
    """dm meta cluster <cluster_id> <b1> [b2...]."""
    e = _engine()
    bm = getattr(e, '_block_meta', None)
    if not bm:
        return "BlockMeta not available"
    cluster_id = getattr(args, "cluster_id", "")
    blocks = getattr(args, "blocks", []) or []
    if not cluster_id or not blocks:
        return "Usage: dm meta cluster <cluster_id> <block_id1> [block_id2...]"
    bm.recluster(blocks, cluster_id)
    return f"Clustered {len(blocks)} blocks → {cluster_id}"


# ═══════════════════════════════════════════════════════════
# G10-P2: Tiered storage commands
# ═══════════════════════════════════════════════════════════

def cmd_tiered_stats(args=None):
    """dm tiered stats — TieredStorageManager statistics."""
    e = _engine()
    sl = getattr(e, '_storage', None)
    if not sl:
        return "StorageLayer not available"
    stats = sl.tiered_stats()
    if not stats.get("enabled"):
        return f"Tiered storage disabled ({stats.get('error') or 'not wired'})"
    lines = [
        "Hot:   sessions=%d max=%d" % (
            stats["hot"]["sessions"], stats["hot"]["max"]),
        "Warm:  sessions=%d turns=%d db=%s" % (
            stats["warm"]["sessions"], stats["warm"]["turns"],
            stats["warm"]["db_path"]),
        "Cold:  files=%d size_mb=%.2f dir=%s" % (
            stats["cold"]["files"], stats["cold"]["size_mb"],
            stats["cold"]["dir"]),
    ]
    return "\n".join(lines)


def cmd_tiered_archive(args=None):
    """dm tiered archive [--dry-run] — archive expired sessions."""
    e = _engine()
    sl = getattr(e, '_storage', None)
    if not sl:
        return "StorageLayer not available"
    dry = bool(getattr(args, "dry_run", False))
    result = sl.archive_tiered(dry_run=dry)
    if not result.get("enabled"):
        return "Tiered storage disabled"
    prefix = "[DRY-RUN] " if dry else ""
    return (f"{prefix}Archived {result['archived_sessions']} sessions, "
            f"{result['archived_turns']} turns")


def cmd_tiered_rehydrate(args=None):
    """dm tiered rehydrate <session_id> — restore cold session to warm."""
    e = _engine()
    sl = getattr(e, '_storage', None)
    if not sl:
        return "StorageLayer not available"
    sid = getattr(args, "session_id", "")
    if not sid:
        return "Usage: dm tiered rehydrate <session_id>"
    session = sl.rehydrate_tiered(sid)
    if session is None:
        return f"No archived session found: {sid}"
    return f"Rehydrated session {sid} (turns={session.turn_count})"


def cmd_recall(args=None):
    """dm recall <query> [--top-k N] [--weights] — 统一召回接口。"""
    e = _engine()
    if getattr(args, "weights", False):
        try:
            from core.agent.recall import RecallService
            svc = RecallService(engine=e)
            return "\n".join(
                f"  {k}: {v}" for k, v in svc.weights().items())
        except Exception as exc:
            return f"RecallService error: {exc}"
    query = " ".join(getattr(args, "query", []) or [])
    if not query:
        return "Usage: dm recall <query> [--top-k N] [--weights]"
    top_k = int(getattr(args, "top_k", 10))
    try:
        from core.agent.recall import RecallService
        svc = RecallService(engine=e)
        result = svc.recall(query, top_k=top_k)
        if not result.hits:
            return f"No recall hits for: {query} (latency {result.latency_ms:.0f}ms)"
        lines = [f"Recall: {query} | {len(result.hits)} hits | "
                 f"expanded={len(result.expanded_queries)} | "
                 f"latency {result.latency_ms:.0f}ms"]
        for i, h in enumerate(result.hits, 1):
            spo = ""
            if h.spo and h.spo.get("predicate"):
                spo = f" SPO[{h.spo.get('subject')}|{h.spo.get('predicate')}|{h.spo.get('obj')}]"
            lines.append(
                f"  {i}. [{h.source:<9}] fused={h.fused():.3f} "
                f"conf={h.confidence:.2f} hops={h.hops}{spo} {h.text[:46]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"RecallService error: {exc}"
