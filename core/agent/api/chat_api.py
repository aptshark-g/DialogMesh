"""v6 Chat API — pipeline entry point + PlanGate checkpoint response.

Adds to FastAPI app:
  POST /v6/chat              — send message → agent_native.process()
  POST /v6/checkpoint/respond — user approves/adjusts plan → resume pipeline
  GET  /v6/execution/{id}     — execution status + node tree
"""

from __future__ import annotations
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging, time, uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6", tags=["v6-chat"])

# ═══ State (per-session) ═══
_sessions: Dict[str, dict] = {}  # session_id → {checkpoint, pipeline_result}

# ═══ Dependency: get orchestrator ═══
_orchestrator = None

def set_orchestrator(orch):
    global _orchestrator
    _orchestrator = orch

def get_orchestrator():
    if _orchestrator is None:
        from core.agent.orchestrator.bootstrap_v6 import bootstrap
        set_orchestrator(bootstrap())
    return _orchestrator


# ═══ Models ═══

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    session_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    trace_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    status: str                     # "completed" | "pending_review" | "error"
    answer: Optional[str] = None    # Final answer (if status=completed)
    checkpoint: Optional[dict] = None  # PlanGate review (if status=pending_review)
    latency_ms: float = 0
    trace_id: Optional[str] = None
    execution: Optional[dict] = None

class CheckpointResponse(BaseModel):
    session_id: str
    checkpoint_id: str
    decision: str                   # "approved" | "adjusted" | "rejected"
    note: Optional[str] = ""
    steps: Optional[dict] = None    # {"0": {approved:true, params:{...}}, ...}

class ExecuteResumeResponse(BaseModel):
    session_id: str
    status: str
    answer: Optional[str] = None
    execution: Optional[dict] = None
    latency_ms: float = 0


# ═══ POST /v6/chat ═══

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send message through full DialogMesh v6 pipeline.

    Returns:
      - status="completed": answer ready
      - status="pending_review": PlanGate checkpoint, user must approve
    """
    orch = get_orchestrator()
    session_id = req.session_id or str(uuid.uuid4())[:8]

    t0 = time.time()
    result = orch.process(req.message, trace_id=req.trace_id, instrument=True)

    lat = result.get("latency_ms", (time.time() - t0) * 1000)

    # Check if pipeline paused for PlanGate review
    if result.get("requires_user_review"):
        checkpoint = result.get("checkpoint", {})
        _sessions[session_id] = {"checkpoint": checkpoint, "result": result}
        return ChatResponse(
            session_id=session_id,
            status="pending_review",
            checkpoint=checkpoint,
            latency_ms=lat,
            trace_id=result.get("trace_id"),
        )

    # Completed
    answer = result.get("response", result.get("answer", str(result.get("plan", {}))))
    return ChatResponse(
        session_id=session_id,
        status="completed",
        answer=str(answer)[:10000],
        latency_ms=lat,
        trace_id=result.get("trace_id"),
        execution=result.get("execution"),
    )


# ═══ POST /v6/checkpoint/respond ═══

@router.post("/checkpoint/respond", response_model=ExecuteResumeResponse)
async def checkpoint_respond(req: CheckpointResponse):
    """User responds to PlanGate checkpoint → resume pipeline with adjusted plan.

    After this, the pipeline continues from the checkpoint → Execution → Answer.
    """
    orch = get_orchestrator()
    session = _sessions.get(req.session_id, {})
    prev_result = session.get("result", {})
    checkpoint = session.get("checkpoint", {})

    if not checkpoint:
        raise HTTPException(404, "No pending checkpoint for this session")

    # Build frontend response format expected by PlanGate.apply
    frontend_response = {
        "decision": req.decision,
        "note": req.note or "",
    }
    if req.steps:
        frontend_response["steps"] = req.steps

    # Resume pipeline from checkpoint
    t0 = time.time()
    result = orch.process_resume(req.session_id, frontend_response)

    lat = result.get("latency_ms", (time.time() - t0) * 1000)
    answer = result.get("answer", result.get("plan_status", str(result)))

    # Clean up
    _sessions.pop(req.session_id, None)

    return ExecuteResumeResponse(
        session_id=req.session_id,
        status="completed",
        answer=str(answer)[:10000],
        execution=result.get("execution"),
        latency_ms=lat,
    )
