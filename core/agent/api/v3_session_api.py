"""v3 Session API — bridges old frontend to v6 agent_native backend."""

import uuid, time, logging, traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v3/session")

# Per-session state
_sessions: Dict[str, Dict[str, Any]] = {}


# ═══ Models ═══

class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    ws_url: str
    status: str
    capabilities: List[str]
    session_ttl_seconds: int


class SendMessageRequest(BaseModel):
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None


class SendMessageResponse(BaseModel):
    message_id: str
    session_id: str
    status: str
    content: str
    response_format: str = "markdown"
    intent: str = "chat"
    task_graph: Optional[List[Any]] = None
    clarifications: List[Any] = []
    suggestions: List[str] = []
    latency_ms: int = 0


class ClarifyRequest(BaseModel):
    clarification_id: str
    answers: Dict[str, Any] = {}


class ClarifyResponse(BaseModel):
    message_id: str
    session_id: str
    status: str
    content: str


# ═══ Endpoints ═══

@router.post("", response_model=CreateSessionResponse)
async def create_session():
    sid = str(uuid.uuid4())[:12]
    _sessions[sid] = {"created_at": time.time(), "messages": []}
    return CreateSessionResponse(
        session_id=sid,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ws_url=f"ws://localhost:8000/v6/ws?session={sid}",
        status="active",
        capabilities=["chat", "task-planning", "engineering"],
        session_ttl_seconds=3600,
    )


@router.post("/{session_id}/message", response_model=SendMessageResponse)
async def send_message(session_id: str, req: SendMessageRequest):
    if session_id not in _sessions:
        # Auto-create session if needed
        _sessions[session_id] = {"created_at": time.time(), "messages": []}

    session = _sessions[session_id]
    session["messages"].append({"role": "user", "content": req.content})

    t0 = time.time()
    content = ""
    try:
        # Try agent_native processing
        from core.agent.agent_native import AgentOrchestrator
        orch = AgentOrchestrator()
        result = orch.process(req.content, session_id=session_id,
                              provider=req.provider, model=req.model)
        content = result.get("response", "") or result.get("content", "")
        if not content:
            content = str(result)
    except Exception as e:
        logger.warning("agent_native failed, fallback: %s", e)
        content = _fallback_reply(req.content)

    latency = int((time.time() - t0) * 1000)
    msg_id = str(uuid.uuid4())[:8]
    session["messages"].append({"role": "assistant", "content": content})

    return SendMessageResponse(
        message_id=msg_id,
        session_id=session_id,
        status="accepted",
        content=content,
        latency_ms=latency,
    )


@router.post("/{session_id}/clarify", response_model=ClarifyResponse)
async def submit_clarification(session_id: str, req: ClarifyRequest):
    return ClarifyResponse(
        message_id=str(uuid.uuid4())[:8],
        session_id=session_id,
        status="accepted",
        content="Clarification received.",
    )


@router.get("/{session_id}/history")
async def get_history(session_id: str):
    session = _sessions.get(session_id, {"messages": []})
    return {"session_id": session_id, "messages": session.get("messages", [])}


@router.get("/{session_id}/status")
async def get_status(session_id: str):
    active = session_id in _sessions
    session = _sessions.get(session_id, {})
    return {
        "session_id": session_id,
        "status": "active" if active else "completed",
        "message_count": len(session.get("messages", [])),
        "uptime": time.time() - session.get("created_at", time.time()),
    }


def _fallback_reply(prompt: str) -> str:
    """Generate a simple fallback reply when agent_native is unavailable."""
    prompt_lower = prompt.strip().lower()
    if any(w in prompt_lower for w in ["你好", "hello", "hi"]):
        return "你好！我是 DialogMesh v6 助手。目前 agent_native 尚未完全接入，我会在后续版本中提供更完整的回复。有什么可以帮你的？"
    if "?" in prompt_lower or "？" in prompt_lower:
        return "这是一个好问题。当前我正在使用 fallback 回复模式，完整 AI 回复能力将在 agent_native 接入后启用。"
    return f"收到你的消息：\"{prompt[:50]}{'...' if len(prompt)>50 else ''}\"。\n\n⚠️ 当前处于 fallback 模式，agent_native 暂未完全启动。完整聊天功能正在开发中。"
