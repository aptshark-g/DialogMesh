# -*- coding: utf-8 -*-
"""设计 5 端到端: 真实图 → expand_from_graph → file 桥路径（2026-08-11）。"""
import os
import sys

sys.path.insert(0, ".")


def main():
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    from core.agent.context.graph_source import ConceptGraph
    from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler

    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    g = ConceptGraph()
    g.build_from_graph_store(store)

    class Engine:
        _graph = g

    sc = SubgraphCompiler(engine=Engine())
    out = []
    for q in ["Behavior Chain", "Intent Parser", "Topic Tree"]:
        entries = sc.expand_from_graph(q, max_nodes=5)
        if not entries:
            out.append("Q=%s: 无图命中" % q)
            continue
        for e in entries[:3]:
            files = [r["note"] for r in e.cross_refs if r["target_domain"] == "file"]
            exists = [f for f in files if os.path.exists(
                os.path.join(os.getcwd(), f.replace("\\", "/")))]
            out.append("Q=%s 命中: %s | file桥=%d 存在=%d" % (
                q, e.content[:40], len(files), len(exists)))
    store.close()
    with open("_bridge_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
