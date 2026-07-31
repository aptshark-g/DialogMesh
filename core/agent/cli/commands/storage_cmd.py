"""CLI commands for Phase 1-3 storage subsystem.

dm chunk add       — add discourse block to ChunkStore
dm chunk search    — vector search blocks
dm chunk stats     — storage statistics
dm graph entities  — list RelationGraph entities
dm graph traverse  — traverse entity neighborhood
dm meta show       — show block metadata
dm meta cluster    — recluster blocks
dm meta tag        — add tag to block
"""
from __future__ import annotations

from tabulate import tabulate


def register_storage_commands(commands: dict, get_engine):
    """Register all storage commands."""

    # ── ChunkStore ──

    def cmd_chunk_stats(args):
        """dm chunk stats — show ChunkStore statistics."""
        e = get_engine()
        cs = getattr(e, '_chunk_store', None)
        if not cs:
            return "ChunkStore not available (needs models)"
        s = cs.stats()
        rows = [[k, str(v)] for k, v in s.items()]
        return tabulate(rows, headers=["Key", "Value"], tablefmt="simple")

    def cmd_chunk_search(args):
        """dm chunk search <query> — vector search in ChunkStore."""
        e = get_engine()
        cs = getattr(e, '_chunk_store', None)
        if not cs:
            return "ChunkStore not available"
        query = " ".join(args) if args else args[0] if args else ""
        if not query:
            return "Usage: dm chunk search <query>"
        results = cs.search(query, top_k=5)
        if not results:
            return f"No results for: {query}"
        rows = [
            [a.atom_id[:8], a.text[:60], a.block_id[:8],
             "✓" if a.chunkable else "✗", f"{a.priority:.2f}"]
            for a in results
        ]
        return tabulate(rows, headers=["ID", "Text", "Block", "Chunkable", "Priority"])

    def cmd_chunk_add(args):
        """dm chunk add <text> — add text to ChunkStore."""
        e = get_engine()
        cs = getattr(e, '_chunk_store', None)
        if not cs:
            return "ChunkStore not available"
        text = " ".join(args)
        if not text:
            return "Usage: dm chunk add <text>"
        atom = cs.add_text(text, block_id=f"cli_{hash(text) & 0xFFFF:04x}")
        if atom:
            return f"Added: {atom.atom_id[:8]} (chunkable={atom.chunkable})"
        return "Duplicate — already in store"

    # ── RelationGraph ──

    def cmd_graph_entities(args):
        """dm graph entities — list entities in RelationGraph."""
        e = get_engine()
        rg = getattr(e, '_relation_graph', None)
        if not rg:
            return "RelationGraph not available"
        s = rg.stats()
        df = rg._backend.entities.head(20)
        if df.empty:
            return "No entities stored yet"
        rows = [[r["id"], r["type"], r["description"][:50],
                 r.get("confidence", "?"), r.get("block_id", "")[:8]]
                for _, r in df.iterrows()]
        return tabulate(rows, headers=["Entity", "Type", "Description", "Conf", "Block"])
        + f"\n\nTotal: {s['entities']} entities, {s['relationships']} relationships"

    def cmd_graph_traverse(args):
        """dm graph traverse <entity_id> [depth] — BFS traversal."""
        e = get_engine()
        rg = getattr(e, '_relation_graph', None)
        if not rg:
            return "RelationGraph not available"
        if not args:
            return "Usage: dm graph traverse <entity_id> [depth=2]"
        entity_id = args[0]
        depth = int(args[1]) if len(args) > 1 else 2
        nodes = rg.traverse(entity_id, depth=depth)
        return tabulate([[n] for n in nodes], headers=["Entity"],
                        tablefmt="simple") + f"\nDepth: {depth}, Nodes: {len(nodes)}"

    # ── BlockMeta ──

    def cmd_meta_show(args):
        """dm meta show <block_id> — show block metadata."""
        e = get_engine()
        bm = getattr(e, '_block_meta', None)
        if not bm:
            return "BlockMeta not available"
        if not args:
            return "Usage: dm meta show <block_id>"
        block_id = args[0]
        meta = bm.get(block_id)
        if not meta:
            return f"No metadata for block: {block_id}"
        rows = [
            ["summary", meta.summary[:80]],
            ["tags", ", ".join(meta.tags)],
            ["cluster_id", meta.cluster_id or "—"],
            ["priority", f"{meta.priority:.2f}"],
            ["chunkable", str(meta.chunkable)],
            ["confidence", f"{meta.confidence:.2f}"],
        ]
        return tabulate(rows, headers=["Field", "Value"], tablefmt="simple")

    def cmd_meta_tag(args):
        """dm meta tag <block_id> <tag1> [tag2...] — add tags to block."""
        e = get_engine()
        bm = getattr(e, '_block_meta', None)
        if not bm:
            return "BlockMeta not available"
        if len(args) < 2:
            return "Usage: dm meta tag <block_id> <tag1> [tag2...]"
        block_id = args[0]
        tags = args[1:]
        bm.update_tags(block_id, tags)
        return f"Tagged {block_id}: {tags}"

    def cmd_meta_cluster(args):
        """dm meta cluster <cluster_id> <b1> [b2...] — recluster blocks."""
        e = get_engine()
        bm = getattr(e, '_block_meta', None)
        if not bm:
            return "BlockMeta not available"
        if len(args) < 2:
            return "Usage: dm meta cluster <cluster_id> <block_id1> [block_id2...]"
        cluster_id = args[0]
        blocks = args[1:]
        bm.recluster(blocks, cluster_id)
        return f"Clustered {len(blocks)} blocks → {cluster_id}"

    # ── Register ──

    commands.update({
        "chunk": {
            "stats": cmd_chunk_stats,
            "search": cmd_chunk_search,
            "add": cmd_chunk_add,
        },
        "graph": {
            "entities": cmd_graph_entities,
            "traverse": cmd_graph_traverse,
        },
        "meta": {
            "show": cmd_meta_show,
            "tag": cmd_meta_tag,
            "cluster": cmd_meta_cluster,
        },
    })
