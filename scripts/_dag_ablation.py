# -*- coding: utf-8 -*-
"""dag_layer_expand 开/关消融（文档图, 2026-08-11）。

构建: docs/v3.0 DESIGN_*.md → ObservationPool → ConceptGraph
对比: dag_layer_expand 开 vs 关, 图检索参与召回后的 Recall@k 变化。
"""
import glob
import sys

sys.path.insert(0, ".")

from core.agent.observation.pool import ObservationPool
from core.agent.document.pipeline import DocumentIngestionPipeline
from core.agent.chunking.strategies import default_registry, RuntimeConstraints
from core.agent.context.graph_source import ConceptGraph


def build():
    pool = ObservationPool()
    docs = glob.glob("docs/v3.0/DESIGN_*.md")[:8]
    pipeline = DocumentIngestionPipeline(
        pool=pool, registry=default_registry())
    for d in docs:
        pipeline.ingest_file(d, constraints=RuntimeConstraints(500))
    graph = ConceptGraph()
    n = graph.build_from_pool(pool)
    return graph, n, docs


def main():
    graph, n, docs = build()
    print("docs=%d graph_nodes=%d edges=%d communities=%d" % (
        len(docs), n, len(graph._edges), len(graph._communities)))
    # 简单 query 集: 从文档标题生成（消融用, 非正式评测）
    queries = []
    for d in docs:
        title = d.split("/")[-1].replace("_", " ").replace(".md", "")
        queries.append(title)
    print("queries=%d" % len(queries))

    for mode in (False, True):
        graph.dag_layer_expand = mode
        hit1 = hit5 = 0
        for q in queries:
            items = graph.compile_context(q, top_k=10, max_nodes=12)
            if items:
                hit1 += 1
            if len(items) >= 3:
                hit5 += 1
        print("dag_layer_expand=%s -> 有命中: %d/%d (%.0f%%) 覆盖>=3: %d" % (
            mode, hit1, len(queries), 100.0 * hit1 / len(queries), hit5))


if __name__ == "__main__":
    main()
