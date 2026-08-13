# -*- coding: utf-8 -*-
"""验证 vault 图落盘（2026-08-11）。"""
import os
import sys

sys.path.insert(0, ".")


def main():
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    stats = store.stats
    print("全库 stats: nodes=%s edges=%s" % (
        stats.get("node_count"), stats.get("edge_count")))
    # 读 vault 节点
    import sqlite3
    conn = sqlite3.connect(os.path.join("data", "unified_graph.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT node_id, node_type, summary FROM unified_nodes WHERE domain='vault_docs' LIMIT 5").fetchall()
    out = []
    for r in rows:
        out.append("node: %s | %s | %s" % (
            r["node_id"], r["node_type"], (r["summary"] or "")[:40]))
    edge_types = conn.execute(
        "SELECT edge_type, COUNT(*) c FROM unified_edges WHERE domain='vault_docs' GROUP BY edge_type").fetchall()
    for e in edge_types:
        out.append("edge_type=%s count=%d" % (e["edge_type"], e["c"]))
    # 验证 delete_domain 幂等
    store.delete_domain("vault_docs")
    after = conn.execute(
        "SELECT COUNT(*) c FROM unified_nodes WHERE domain='vault_docs'").fetchone()["c"]
    out.append("delete_domain 后 vault 节点: %d" % after)
    conn.close()
    store.close()
    with open("_verify_graph.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
