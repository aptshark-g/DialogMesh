# -*- coding: utf-8 -*-
"""端到端: 真实 vault 图 → ConceptGraph → 图导航（2026-08-11）。"""
import os
import sys

sys.path.insert(0, ".")


def main():
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    from core.agent.context.graph_source import ConceptGraph
    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    g = ConceptGraph()
    n = g.build_from_graph_store(store)
    out = []
    out.append("ConceptGraph 加载: %d 节点 / %d 边 / %d 社区" % (
        n, len(g._edges), len(g._communities)))
    # 图导航实测
    idx = [k for k in g._nodes if "00-INDEX" in k]
    if idx:
        start = idx[0]
        out.append("起点: %s" % start)
        out.append("邻居数: %d" % len(g.neighbors(start)))
        nbrs = g.neighbors(start)[:5]
        for nb in nbrs:
            out.append("  -> %s" % nb)
            out.append("     callers: %d" % len(g.callers(nb)))
        # path: INDEX → 任一邻居的邻居
        if nbrs:
            second = [x for nb in nbrs for x in g.neighbors(nb) if x != start]
            if second:
                target = second[0]
                p = g.path(start, target)
                out.append("path %s -> %s: %s" % (start[:30], target[:30], p))
    with open("_graph_e2e.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    store.close()
    print("done")


if __name__ == "__main__":
    main()
