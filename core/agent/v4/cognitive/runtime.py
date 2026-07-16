"""Cognitive Runtime — LLM-driven reasoning loop.

Design: docs/v3.0/DESIGN_COGNITIVE_RUNTIME.md §2.3

Wire: MetaCognition(LLM) → Scheduler(thin) → Executor → Workspace → Trace
"""
from __future__ import annotations
import time, logging
from typing import Optional

from .workspace import CognitiveWorkspace, WorkspaceGraph, WorkspaceNode, ExecutionTrace, TraceStep
from .scheduler import Observer, CognitiveTask, CognitiveScheduler
from .metacognition import MetaCognition, MetaReflection

logger = logging.getLogger(__name__)


def run_cognitive_loop(
    observer: Observer,
    scheduler: CognitiveScheduler,
    engine=None,
    question: str = "",
    max_iterations: int = 10,
) -> ExecutionTrace:
    """Main loop: PERCEIVE → [REASON → REFLECT → 决策 → 执行]* → COMMIT.

    Args:
        observer: Cognitive CPU with perspective + budget
        scheduler: Thin dispatcher (MetaCognition → task)
        engine: DialogMesh engine (for PERCEIVE + REASON)
        question: User's question
        max_iterations: Max REASON → REFLECT cycles

    Returns:
        ExecutionTrace with all steps recorded
    """
    trace = ExecutionTrace(session_id=f"cog_{int(time.time())}")

    # ── INIT ──
    ws = CognitiveWorkspace(
        id="ws_main",
        goal=question,
        state="INIT",
    )
    node = WorkspaceNode(workspace=ws, status="running")
    observer._workspace_graph = WorkspaceGraph()
    observer._workspace_graph.add(node)
    observer._workspace = ws

    def _record(state: str, decision: str = "", llm_out: str = ""):
        step = TraceStep(
            step_id=f"{ws.id}_{state}_{len(trace.steps)}",
            state=state,
            observer_snapshot=observer.snapshot(),
            workspace_snapshot={
                "active_objects": ws.active_objects,
                "hypotheses_count": len(ws.hypotheses),
                "confidence": ws.confidence,
                "state": ws.state,
                "depth": ws.reasoning_depth,
            },
            decision=decision,
            llm_output=llm_out[:200],
        )
        trace.add(step)

    # ── PERCEIVE ──
    ws.state = "PERCEIVING"
    if engine:
        try:
            from core.agent.v4.event_ir import DialogAdapter
            ad = DialogAdapter()
            engine.on_event(ad.adapt(question, session_id=trace.session_id, turn_number=1))
            ctx = getattr(engine, 'last_context', None)
            if ctx and ctx.entries:
                world_entries = [e for e in ctx.entries if 'world_view' in str(getattr(e, 'type', ''))]
                for e in world_entries[:5]:
                    content = getattr(e, 'content', '')
                    # Extract concept names from world_view content
                    import re
                    camel = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', content)
                    for c in camel[:3]:
                        if c not in ws.active_objects:
                            ws.active_objects.append(c)
        except Exception as e:
            logger.warning("PERCEIVE via engine failed: %s", e)
    _record("PERCEIVE", f"perceived {len(ws.active_objects)} objects")

    # ── Main loop: REASON → REFLECT → 决策 ──
    for iteration in range(max_iterations):
        # REASON
        ws.state = "REASONING"
        if engine:
            try:
                from core.agent.v4.event_ir import DialogAdapter
                ad = DialogAdapter()
                prompt = f"{question}\n\n[Context: active objects = {ws.active_objects}, hypotheses = {len(ws.hypotheses)}]"
                resp = engine.on_event(ad.adapt(prompt, session_id=trace.session_id, turn_number=iteration + 2))
                if resp:
                    ws.candidate_answers.append({"content": resp[:300], "iteration": iteration})
                    ws.reasoning_tree = {"response": resp[:200]}
            except Exception as e:
                logger.warning("REASON via engine failed: %s", e)
        _record("REASON", f"reasoning iteration {iteration+1}")

        # REFLECT
        ws.state = "REFLECTING"
        task = scheduler.next(observer)
        _record("REFLECT", f"{task.type}: {task.reason}")

        # COMMIT check
        if task.type == "COMMIT":
            ws.state = "COMMITTING"
            ws.committed = True
            _record("COMMIT", "committed")
            break

        # Execute (RETRIEVE or EXPAND)
        scheduler.execute(observer, task, engine)
        _record(task.type, task.reason)

    # ── Finalize ──
    trace.final_answer = (
        ws.candidate_answers[-1]["content"][:200]
        if ws.candidate_answers else "(no answer)"
    )
    trace.final_confidence = ws.confidence
    observer.active = False
    ws.state = "DONE"

    logger.info("Cognitive loop: %s", trace.summary())
    return trace
