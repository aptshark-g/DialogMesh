"""E2E Test: Document Ingestion + Chat with DeepSeek

Usage:
    set DEEPSEEK_API_KEY=sk-...
    python tests/test_e2e_dil_chat.py

Flow:
    1. Ingest docs/v3.0/ into ObservationPool
    2. Start CognitiveRuntimeEngine with DeepSeek
    3. Interactive chat loop
    4. Log all I/O to data/e2e_chat_log.jsonl
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("e2e_test")

# ---- Imports ----
from core.agent.events.event_ir import EventIR, DialogAdapter
from core.agent.document.pipeline import DocumentIngestionPipeline
from core.agent.chunking.strategies import default_registry, RuntimeConstraints
from core.agent.observation.pool import ObservationPool
from core.agent.runtime.engine import CognitiveRuntimeEngine


# ---- Config ----
DOCS_DIR = PROJECT_ROOT / "docs" / "v3.0"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "e2e_chat_log.jsonl"


def log_io(event_type: str, data: dict):
    """Append structured log entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "session_id": SESSION_ID,
        **data,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def ingest_docs() -> dict:
    """Step 1: Ingest all MD files from docs/v3.0/"""
    logger.info("=" * 60)
    logger.info("Step 1: Ingesting documents from %s", DOCS_DIR)
    logger.info("=" * 60)

    pool = ObservationPool()
    pipeline = DocumentIngestionPipeline(
        pool=pool,
        registry=default_registry(),
    )

    # Ingest with conservative constraints (Header strategy preferred)
    constraints = RuntimeConstraints(max_latency_ms=500, llm_available=False)

    start = time.time()
    bundles = pipeline.ingest_directory(
        str(DOCS_DIR),
        pattern="*.md",
        constraints=constraints,
    )
    elapsed = time.time() - start

    # Stats
    total_obs = sum(len(b.observations) for b in bundles)
    type_dist = {}
    for b in bundles:
        for obs in b.observations:
            t = obs.observation_type or "unknown"
            type_dist[t] = type_dist.get(t, 0) + 1

    stats = {
        "files_ingested": len(bundles),
        "total_observations": total_obs,
        "elapsed_sec": round(elapsed, 2),
        "observation_types": type_dist,
        "pool_stats": pool.stats(),
    }

    logger.info("Ingested %d files → %d observations in %.1fs",
                stats["files_ingested"], stats["total_observations"], elapsed)
    logger.info("Type distribution: %s", type_dist)
    logger.info("Pool stats: %s", stats["pool_stats"])

    log_io("ingestion_complete", stats)
    return {"pool": pool, "stats": stats}


def start_engine(pool: ObservationPool) -> CognitiveRuntimeEngine:
    """Step 2: Start engine with DeepSeek provider."""
    logger.info("=" * 60)
    logger.info("Step 2: Starting CognitiveRuntimeEngine")
    logger.info("=" * 60)

    # Use environment variable for API key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set — using MockProvider")
    else:
        logger.info("DeepSeek API key configured (len=%d)", len(api_key))

    # Create engine with explicit provider
    from core.agent.llm_providers.openai_provider import OpenAIProvider

    provider = None
    if api_key:
        try:
            provider = OpenAIProvider(
                "deepseek",
                {
                    "api_key": api_key,
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
            )
            logger.info("DeepSeek provider created: %s", provider.name)
        except Exception as e:
            logger.warning("Failed to create DeepSeek provider: %s", e)

    engine = CognitiveRuntimeEngine(llm_provider=provider)
    engine.start()

    # Inject the pre-populated pool
    engine._observation_pool = pool
    logger.info("Engine started — observation pool injected")
    logger.info("Engine stats: adapters=%d, paths=%s",
                engine.adapter_count, list(engine.stats.keys()))

    log_io("engine_start", {
        "provider": provider.name if provider else "mock",
        "pool_bundles": pool.stats()["total_bundles"],
    })

    return engine


def chat_loop(engine: CognitiveRuntimeEngine):
    """Step 3: Interactive chat with logging."""
    logger.info("=" * 60)
    logger.info("Step 3: Chat loop started")
    logger.info("Commands: /quit, /status, /context, /pool")
    logger.info("=" * 60)

    adapter = DialogAdapter()
    turn = 0

    while True:
        try:
            user_text = input("\n[You] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_text:
            continue
        if user_text.lower() in ("/quit", "/q", "exit"):
            break

        # Commands
        if user_text.lower() == "/status":
            print(f"[Status] {json.dumps(engine.stats, indent=2, default=str)}")
            continue
        if user_text.lower() == "/context":
            ctx = engine.last_context
            if ctx:
                print(f"[Context] {len(ctx.entries)} entries, {ctx.total_estimated_tokens} tokens")
                for entry in ctx.entries[:5]:
                    print(f"  [{entry.domain}] {entry.type}: {entry.content[:80]}...")
            else:
                print("[Context] No context compiled yet")
            continue
        if user_text.lower() == "/pool":
            if engine._observation_pool:
                print(f"[Pool] {json.dumps(engine._observation_pool.stats(), indent=2)}")
            else:
                print("[Pool] No pool attached")
            continue

        # Normal chat
        turn += 1
        event = adapter.adapt(user_text, session_id=SESSION_ID, turn_number=turn)

        # Log user input
        log_io("user_input", {
            "turn": turn,
            "event_id": event.id,
            "text": user_text,
        })

        # Process event
        start = time.time()
        try:
            response = engine.on_event(event)
        except Exception as e:
            logger.exception("Engine error")
            response = f"[Error: {e}]"
        elapsed = (time.time() - start) * 1000

        # Get metrics
        metrics = engine.llm_metrics or {}
        context = engine.last_context

        # Log assistant output
        log_io("assistant_output", {
            "turn": turn,
            "event_id": event.id,
            "response": response,
            "latency_ms": round(elapsed, 1),
            "llm_metrics": metrics,
            "context_entries": len(context.entries) if context else 0,
            "context_tokens": context.total_estimated_tokens if context else 0,
        })

        # Print response
        if response:
            print(f"\n[DialogMesh] {response}")
            if metrics:
                print(f"  [metrics: {metrics.get('input_tokens', 0)} in / {metrics.get('output_tokens', 0)} out, {metrics.get('latency_ms', 0):.0f}ms]")
        else:
            print("\n[DialogMesh] (no response)")

    logger.info("Chat loop ended — %d turns", turn)
    log_io("chat_end", {"total_turns": turn})


def main():
    global SESSION_ID
    SESSION_ID = f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    print(f"\n{'='*60}")
    print(f"DialogMesh v4 E2E Test")
    print(f"Session: {SESSION_ID}")
    print(f"Log: {LOG_FILE}")
    print(f"{'='*60}\n")

    # Step 1: Ingest
    ingestion = ingest_docs()
    pool = ingestion["pool"]

    # Step 2: Start engine
    engine = start_engine(pool)

    # Step 3: Chat
    try:
        chat_loop(engine)
    finally:
        # Step 4: Cleanup
        logger.info("=" * 60)
        logger.info("Step 4: Cleanup")
        logger.info("=" * 60)
        engine.stop()
        logger.info("Engine stopped")

        # Final stats
        final_stats = {
            "session_id": SESSION_ID,
            "engine_stats": engine.stats,
            "pool_stats": pool.stats() if pool else {},
        }
        log_io("session_end", final_stats)
        logger.info("Session logged to %s", LOG_FILE)
        print(f"\n[Done] Log saved: {LOG_FILE}")


if __name__ == "__main__":
    main()
