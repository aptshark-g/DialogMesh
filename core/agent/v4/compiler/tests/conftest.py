"""Shared test fixtures. Uses subset of docs for fast startup (<10s)."""
import pytest, logging
logging.getLogger("jieba").setLevel(logging.WARNING)

@pytest.fixture(scope="session")
def world():
    from core.agent.v4.observation_compiler.pool import ObservationPool
    from core.agent.v4.document.pipeline import DocumentIngestionPipeline
    from core.agent.v4.chunking.strategies import default_registry, RuntimeConstraints
    from core.agent.v4.context.graph_source import ConceptGraph
    from core.agent.v4.compiler.semantic_path import SemanticIndex
    from core.agent.v4.compiler.relation_substrate import RelationSubstrate
    from core.agent.v4.compiler.content_provider import ContentProvider
    from core.agent.v4.compiler.object_builder import build_object_graph
    from core.agent.v4.compiler.object_runtime import ObjectRuntime
    import glob, os

    # Use only 5 design docs for fast startup
    docs = glob.glob("docs/v3.0/DESIGN_SEMANTIC_*.md")[:3] +            glob.glob("docs/v3.0/DESIGN_RELATION_*.md")[:1] +            glob.glob("docs/v3.0/DESIGN_PERSPECTIVE_*.md")[:1]
    docs = [d for d in docs if os.path.exists(d)][:5]

    pool = ObservationPool()
    pipeline = DocumentIngestionPipeline(pool=pool, registry=default_registry())
    for doc in docs:
        pipeline.ingest_file(doc, constraints=RuntimeConstraints(500))

    graph = ConceptGraph(); graph.build_from_pool(pool)
    idx = SemanticIndex(); idx.build_from_pool(pool, graph)
    rs = RelationSubstrate(); rs.build_from_concept_graph(graph); rs.build_from_heading(idx, graph)
    provider = ContentProvider(pool, idx); provider.set_relation_substrate(rs)
    objects = build_object_graph(pool, graph, idx)
    ort = ObjectRuntime(provider=provider); ort.set_store(objects)
    return (pool, graph, idx, rs, provider, objects, ort)

@pytest.fixture(scope="session")
def pool(world): return world[0]
@pytest.fixture(scope="session")
def graph(world): return world[1]
@pytest.fixture(scope="session")
def semantic_index(world): return world[2]
@pytest.fixture(scope="session")
def relation_substrate(world): return world[3]
@pytest.fixture(scope="session")
def content_provider(world): return world[4]
@pytest.fixture(scope="session")
def objects(world): return world[5]
@pytest.fixture(scope="session")
def object_runtime(world): return world[6]
