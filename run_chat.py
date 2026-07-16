"""启动 DialogMesh v4 Engine，加载已导入的文档数据，进入交互对话模式。

Usage:
    set DEEPSEEK_API_KEY=sk-...
    python run_chat.py

Features:
    - 自动加载已导入的 ObservationPool（SQLite）
    - DeepSeek API 对话
    - 实时记录所有 I/O 到 data/chat_session_*.jsonl
    - 命令: /status, /context, /pool, /quit
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chat")

from core.agent.v4.event_ir import EventIR, DialogAdapter
from core.agent.v4.observation_compiler.pool import ObservationPool
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

DATA_DIR = PROJECT_ROOT / "data"
SESSION_ID = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
LOG_FILE = DATA_DIR / f"chat_session_{SESSION_ID}.jsonl"


def log_io(event_type: str, data: dict):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "session_id": SESSION_ID,
        **data,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_pool() -> ObservationPool:
    """Load ObservationPool — always re-ingest docs to ensure data is present."""
    pool = ObservationPool()
    
    # Always re-ingest (fast, ~1s for 88 files)
    from core.agent.v4.document.pipeline import DocumentIngestionPipeline
    from core.agent.v4.chunking.strategies import default_registry, RuntimeConstraints
    
    pipeline = DocumentIngestionPipeline(pool=pool, registry=default_registry())
    docs_dir = PROJECT_ROOT / "docs" / "v3.0"
    merge_dir = PROJECT_ROOT / "docs" / "merge"
    
    total_bundles = []
    for d in [docs_dir, merge_dir]:
        if d.exists():
            logger.info("Ingesting documents from %s...", d)
            bundles = pipeline.ingest_directory(str(d), pattern="*.md",
                                                constraints=RuntimeConstraints(max_latency_ms=500))
            total_bundles.extend(bundles)
            total_obs = sum(len(b.observations) for b in bundles)
            logger.info("  %s: %d files, %d observations", d.name, len(bundles), total_obs)
    logger.info("Ingest complete: %d files total, pool: %s", len(total_bundles), pool.stats())
    return pool


def start_engine(pool: ObservationPool) -> CognitiveRuntimeEngine:
    """Start engine with DeepSeek provider + RelationSubstrate."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    provider = None
    if api_key:
        try:
            from core.agent.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(
                "deepseek",
                {
                    "api_key": api_key,
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
            )
            logger.info("DeepSeek provider ready")
        except Exception as e:
            logger.warning("DeepSeek failed: %s", e)

    if not provider:
        from core.agent.llm_providers.mock_provider import MockProvider
        provider = MockProvider("mock", {"response_text": "[Mock: 请配置 DEEPSEEK_API_KEY]"})
        logger.info("Using MockProvider")

    engine = CognitiveRuntimeEngine(llm_provider=provider)
    engine.start()
    engine.set_observation_pool(pool)

    # ---- RelationSubstrate setup ----
    from core.agent.v4.compiler.relation_substrate import RelationSubstrate
    from core.agent.v4.compiler.content_provider import ContentProvider
    from core.agent.v4.compiler.parameter_registry import ParameterRegistry
    from core.agent.v4.compiler.semantic_path import SemanticIndex

    # Reuse graph from engine's ContentIndex (already built in set_observation_pool)
    graph = engine._content_index._graph if hasattr(engine._content_index, '_graph') else None
    # Build SemanticIndex fresh (lightweight once graph exists)
    idx = SemanticIndex()
    if graph:
        idx.build_from_pool(pool, graph)

    params = ParameterRegistry()
    params.load_defaults()

    rs = RelationSubstrate(params=params)
    if graph:
        rs.build_from_concept_graph(graph)
    rs.build_from_heading(idx, graph)

    provider_wrapper = ContentProvider(pool, idx)
    provider_wrapper.set_relation_substrate(rs)
    engine.set_content_provider(provider_wrapper)

    # Build SemanticObject graph + ObjectRuntime for world rendering
    from core.agent.v4.compiler.object_builder import build_object_graph
    from core.agent.v4.compiler.object_runtime import ObjectRuntime
    objects = build_object_graph(pool, graph, idx)
    obj_runtime = ObjectRuntime(provider=provider_wrapper)
    obj_runtime.set_store(objects)
    provider_wrapper.set_relation_substrate(rs)
    engine.set_object_store(objects, obj_runtime, provider_wrapper)
    logger.info("SemanticObject graph: %d objects, %d with composition",
                len(objects), sum(1 for o in objects.values() if o.composition_edges))

    log_io("init_relation_substrate", {
        "stats": rs.stats,
        "parameters": params.all(),
    })
    logger.info("RelationSubstrate: %s", rs.stats)

    logger.info("Engine ready — %d adapters, pool: %s",
                engine.adapter_count, pool.stats())
    return engine


def chat_loop(engine: CognitiveRuntimeEngine):
    adapter = DialogAdapter()
    turn = 0
    
    print(f"\n{'='*60}")
    print(f"DialogMesh v4 Chat — Session: {SESSION_ID}")
    print(f"Log: {LOG_FILE}")
    print(f"Commands: /status, /context, /pool, /quit")
    print(f"{'='*60}\n")
    
    while True:
        try:
            user_text = input("[You] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        
        if not user_text:
            continue
        if user_text.lower() in ("/quit", "/q", "exit"):
            break
        
        # Commands
        if user_text.lower() == "/status":
            stats = engine.stats
            stats_dict = {k: {"trigger_count": v.trigger_count, "success_count": v.success_count, 
                              "failure_count": v.failure_count, "total_latency_ms": v.total_latency_ms} 
                         for k, v in stats.items()}
            print(json.dumps(stats_dict, indent=2))
            continue
        if user_text.lower() == "/context":
            ctx = engine.last_context
            if ctx:
                print(f"Entries: {len(ctx.entries)}, Tokens: {ctx.total_estimated_tokens}")
                for e in ctx.entries[:5]:
                    print(f"  [{e.domain}] {e.type}: {e.content[:60]}...")
            else:
                print("No context")
            continue
        if user_text.lower() == "/pool":
            if engine._observation_pool:
                print(json.dumps(engine._observation_pool.stats(), indent=2))
            else:
                print("No pool")
            continue
        
        # Chat
        turn += 1
        event = adapter.adapt(user_text, session_id=SESSION_ID, turn_number=turn)
        
        log_io("user_input", {"turn": turn, "text": user_text})
        
        start = time.time()
        try:
            response = engine.on_event(event)
        except Exception as e:
            logger.exception("Engine error")
            response = f"[Error: {e}]"
        elapsed = (time.time() - start) * 1000
        
        metrics = engine.llm_metrics or {}
        ctx = engine.last_context
        persp = getattr(engine, '_last_perspective', None)

        log_io("assistant_output", {
            "turn": turn,
            "response": response,
            "latency_ms": round(elapsed, 1),
            "llm_metrics": metrics,
            "context_entries": len(ctx.entries) if ctx else 0,
            "perspective": {
                "strategy": persp.strategy if persp else "",
                "horizon": persp.horizon.depth if persp and hasattr(persp.horizon, 'depth') else 0,
                "domains": persp.domains if persp else {},
            } if persp else None,
        })

        # Log context details for analysis
        if ctx and ctx.entries:
            log_io("context_detail", {
                "turn": turn,
                "entries": [
                    {"domain": e.domain, "type": e.type if hasattr(e, "type") else "",
                     "content": (e.content if hasattr(e, "content") else str(e))[:300]}
                    for e in ctx.entries[:20]
                ],
                "total_tokens": ctx.total_estimated_tokens if hasattr(ctx, "total_estimated_tokens") else 0,
            })
        
        if response:
            print(f"\n[DialogMesh] {response}")
            if metrics.get("input_tokens"):
                print(f"  [{metrics['input_tokens']} in / {metrics['output_tokens']} out, {metrics.get('latency_ms', 0):.0f}ms]")
        else:
            print("\n[DialogMesh] (no response)")
    
    print(f"\n[Done] {turn} turns logged to {LOG_FILE}")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    
    # Step 1: Load pool
    print("[1/3] Loading ObservationPool...")
    pool = load_pool()
    print(f"  Pool ready: {pool.stats()}")
    
    # Step 2: Start engine
    print("[2/3] Starting Engine...")
    engine = start_engine(pool)
    
    # Step 3: Chat
    print("[3/3] Entering chat loop...")
    try:
        chat_loop(engine)
    finally:
        engine.stop()
        stats = engine.stats
        stats_dict = {k: {"trigger_count": v.trigger_count, "success_count": v.success_count,
                          "failure_count": v.failure_count, "total_latency_ms": v.total_latency_ms}
                     for k, v in stats.items()}
        log_io("session_end", {"engine_stats": stats_dict})

        # RelationSubstrate final state
        if hasattr(engine, '_content_provider') and engine._content_provider:
            prov = engine._content_provider
            if hasattr(prov, '_relation_substrate') and prov._relation_substrate:
                edges = prov._relation_substrate.query(relation_kind="behavioral")
                log_io("session_end_relations", {
                    "substrate_stats": prov._relation_substrate.stats,
                    "behavioral_edges": [
                        {"source": e.source, "target": e.target, "confidence": e.confidence}
                        for e in edges
                    ],
                })
        print(f"\n[Session End] Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
