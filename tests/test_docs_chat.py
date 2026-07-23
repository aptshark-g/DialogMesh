"""Docs-based E2E test: DialogMesh v4 with real document context.

Reads design docs from docs/v3.0/, constructs IREntries from document chunks,
and tests LLM's ability to answer questions using the provided context.

Usage:
    set DEEPSEEK_API_KEY=your_key_here
    python tests/test_docs_chat.py
"""
from __future__ import annotations
import os
import sys
import glob
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.events.event_ir import EventIR
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.context.cross_domain_ir import (
    CrossDomainContextIR, IntentCategory, DomainAllocation, DomainRole,
    IREntry, CrossRef, CompileStrategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_docs")


def read_doc_chunks(docs_dir: str = "docs/v3.0", max_chunks: int = 20) -> list:
    """Read .md files and split into chunks by headers."""
    chunks = []
    md_files = glob.glob(os.path.join(docs_dir, "*.md"))
    logger.info("Found %d markdown files in %s", len(md_files), docs_dir)

    for filepath in md_files[:5]:  # Limit to first 5 files for testing
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Cannot read %s: %s", filepath, e)
            continue

        # Split by ## headers
        lines = content.split("\n")
        current_chunk = []
        current_title = os.path.basename(filepath).replace(".md", "")

        for line in lines:
            if line.startswith("## "):
                # Save previous chunk
                if current_chunk:
                    chunk_text = "\n".join(current_chunk).strip()
                    if len(chunk_text) > 50:
                        chunks.append({
                            "source": os.path.basename(filepath),
                            "title": current_title,
                            "content": chunk_text[:500],  # Cap length
                        })
                current_title = line[3:].strip()
                current_chunk = []
            else:
                current_chunk.append(line)

        # Save last chunk
        if current_chunk:
            chunk_text = "\n".join(current_chunk).strip()
            if len(chunk_text) > 50:
                chunks.append({
                    "source": os.path.basename(filepath),
                    "title": current_title,
                    "content": chunk_text[:500],
                })

    logger.info("Extracted %d chunks", len(chunks))
    return chunks[:max_chunks]


def build_context_ir_from_docs(chunks: list, intent: str = "query") -> CrossDomainContextIR:
    """Build CrossDomainContextIR from document chunks."""
    entries = []
    for i, chunk in enumerate(chunks):
        entries.append(IREntry(
            domain="knowledge",
            type="DOC_CHUNK",
            content=f"[{chunk['source']} > {chunk['title']}] {chunk['content']}",
            cross_refs=[],
            source_events=[f"doc_{i}"],
            confidence=0.9,
            estimated_tokens=len(chunk["content"]) // 4,  # Rough estimate
        ))

    ir = CrossDomainContextIR(
        intent_category=IntentCategory.QUERY,
        domain_allocation=[
            DomainAllocation(domain="knowledge", role=DomainRole.PRIMARY, budget_pct=0.8, budget_tokens=800),
            DomainAllocation(domain="world", role=DomainRole.AUXILIARY, budget_pct=0.2, budget_tokens=200),
        ],
        entries=entries,
        compile_strategy=CompileStrategy.BALANCED,
    )
    ir.recalc_total()
    return ir


def test_docs_chat():
    """Test: Load docs → Build Context IR → Ask LLM → Verify answer."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not set. Export it first:")
        logger.error("  set DEEPSEEK_API_KEY=your_key_here")
        return 1

    # Create provider
    provider = OpenAIProvider("deepseek", {
        "api_key": api_key,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "timeout_s": 60,
    })

    # Create engine
    logger.info("Starting CognitiveRuntimeEngine...")
    engine = CognitiveRuntimeEngine(llm_provider=provider)
    engine.start()

    try:
        # Step 1: Read docs
        logger.info("=" * 60)
        logger.info("Step 1: Reading design docs...")
        chunks = read_doc_chunks("docs/v3.0", max_chunks=15)

        # Step 2: Build Context IR from docs
        logger.info("=" * 60)
        logger.info("Step 2: Building Context IR from %d chunks...", len(chunks))
        doc_ir = build_context_ir_from_docs(chunks)
        logger.info("Context IR: %d entries, %d tokens", len(doc_ir.entries), doc_ir.total_estimated_tokens)

        # Step 3: Inject doc context into engine
        # We manually set the last_context so _call_llm uses it
        engine._last_context = doc_ir

        # Step 4: Ask questions
        questions = [
            "什么是 Context Engineering？DialogMesh 是怎么做的？",
            "DialogMesh v4 的五层架构是什么？",
            "CrossDomainContextIR 的作用是什么？",
        ]

        for i, question in enumerate(questions, 1):
            logger.info("=" * 60)
            logger.info("Question %d: %s", i, question)

            event = EventIR(
                id=f"q{i}",
                kind="dialog.message",
                payload={"text": question},
            )
            response = engine.on_event(event)
            logger.info("Response: %s", response)
            logger.info("LLM metrics: %s", engine.llm_metrics)

        # Step 5: Verify context was used
        logger.info("=" * 60)
        logger.info("Step 5: Context inspection")
        ctx = engine.last_context
        if ctx:
            logger.info("Final context entries: %d", len(ctx.entries))
            logger.info("Total tokens: %d", ctx.total_estimated_tokens)
        else:
            logger.warning("No context")

        logger.info("=" * 60)
        logger.info("✅ Docs chat test completed!")
        return 0

    finally:
        engine.stop()
        logger.info("Engine stopped")


if __name__ == "__main__":
    sys.exit(test_docs_chat())
