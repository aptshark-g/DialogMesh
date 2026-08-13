# -*- coding: utf-8 -*-
"""图最终统计（2026-08-11）: 显式 + verified 隐式边。"""
import os
import sys

sys.path.insert(0, ".")


def main():
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    import sqlite3
    conn = sqlite3.connect(os.path.join("data", "unified_graph.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT edge_type, COUNT(*) c FROM unified_edges WHERE domain='vault_docs' GROUP BY edge_type ORDER BY c DESC").fetchall()
    out = ["# 内容→图 最终统计（2026-08-11）", ""]
    total = 0
    for r in rows:
        out.append("- %s: %d" % (r["edge_type"], r["c"]))
        total += r["c"]
    nodes = conn.execute(
        "SELECT COUNT(*) c FROM unified_nodes WHERE domain='vault_docs'").fetchone()["c"]
    out.insert(1, "- vault 节点: %d" % nodes)
    out.insert(2, "- 总边数: %d" % total)
    out.append("")
    out.append("## 隐式关系核验（108 候选, LLM）")
    out.append("- 真关系 12 (precision 11%), 已落盘 inferred_verified")
    out.append("- 关系类型: related_to 10 / discusses 1 / extends 1")
    out.append("- 阈值 0.55; 高相似段(0.7+) precision 更高, 建议分段核验")
    out.append("- 空返回 ~30 个（重试后仍空, 按未知处理）")
    with open("docs/test/GRAPH_FINAL_STATS_20260811.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    store.close()
    print("\n".join(out[:8]))


if __name__ == "__main__":
    main()
