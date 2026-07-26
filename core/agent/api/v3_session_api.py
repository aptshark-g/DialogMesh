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
        # Phase 1: Cognitive analysis via AgentOrchestrator
        import json as _json
        cognitive_ctx = {}
        try:
            from core.agent.orchestrator.agent_native import AgentOrchestrator
            orch = AgentOrchestrator()
            cog = orch.process(text=req.content)
            cognitive_ctx = {
                "intents": cog.get("intents", {}),
                "route": cog.get("route", {}),
                "compass": cog.get("compass", {}),
                "context": cog.get("context", {}),
                "cognition": cog.get("cognition", {}),
            }
        except Exception as e:
            logger.warning("Cognitive pipeline skipped: %s", e)

        # Phase 2: Fetch user profile + subgraph context
        profile_text = ""
        try:
            resp = await _fetch_json("http://127.0.0.1:8000/v6/profile")
            p = resp.get("profile", resp)
            oceAN = p.get("oceAN_dims", {})
            mbti = p.get("mbti", "N/A")
            profile_text = (
                f"## 用户画像\n"
                f"MBTI: {mbti}\n"
                f"OCEAN: O={oceAN.get('O',0):.2f} C={oceAN.get('C',0):.2f} E={oceAN.get('E',0):.2f} "
                f"A={oceAN.get('A',0):.2f} N={oceAN.get('N',0):.2f}\n"
                f"BFI-10 C维度: {p.get('bfi_latest',{}).get('C','N/A')}\n"
            )
        except Exception as e:
            logger.warning("Profile fetch failed: %s", e)

        # Phase 3: Build messages with full context
        system_prompt = _build_system_prompt(profile_text, cognitive_ctx)
        history = session["messages"][-20:]
        all_messages = [{"role": "system", "content": system_prompt}] + history

        # Phase 4: Call LLM via switch gateway
        import urllib.request
        body = {
            "provider": req.provider or "deepseek",
            "model": req.model or "deepseek-v4-flash",
            "messages": all_messages,
        }
        http_req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions",
            data=_json.dumps(body).encode(),
            headers={"Authorization": "Bearer dm-client", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_req, timeout=60) as resp:
            data = _json.loads(resp.read())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            content = str(data)
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
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


async def _fetch_json(url: str) -> dict:
    """Async HTTP GET → dict."""
    import urllib.request, json
    loop = __import__("asyncio").get_event_loop()
    def _get():
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    return await loop.run_in_executor(None, _get)


def _build_system_prompt(profile_text: str = "", cognitive_ctx: dict = {}) -> str:
    """Build a system prompt incorporating user profile and cognitive context."""
    parts = ["你是 DialogMesh v6 认知助手。分析用户输入并提供洞察。\n"]

    if profile_text:
        parts.append(profile_text)
        parts.append("请根据以上用户画像调整回复风格和深度。\n")

    if cognitive_ctx:
        intents = cognitive_ctx.get("intents", {})
        route = cognitive_ctx.get("route", {})
        compass = cognitive_ctx.get("compass", {})
        context = cognitive_ctx.get("context", {})

        if intents.get("multi"):
            parts.append(f"用户意图: 多意图 - 置信度 {intents.get('confidence', 0):.2f}")
        else:
            parts.append(f"用户意图: 单意图 - 置信度 {intents.get('confidence', 0):.2f}")

        if route:
            parts.append(f"路由区域: {route.get('zone', 'N/A')}")

        if context:
            parts.append(f"关联上下文: {_json_compact(context)}")

    parts.append("\n用中文回复。保持专业但自然。")
    return "\n\n".join(parts)


def _json_compact(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, default=str)[:500]


def _fallback_reply(prompt: str) -> str:
    """Generate a simple fallback reply when LLM is unavailable."""
    prompt_lower = prompt.strip().lower()
    if any(w in prompt_lower for w in ["你好", "hello", "hi"]):
        return "你好！我是 DialogMesh v6 助手。目前 agent_native 尚未完全接入，我会在后续版本中提供更完整的回复。有什么可以帮你的？"
    if "?" in prompt_lower or "？" in prompt_lower:
        return "这是一个好问题。当前我正在使用 fallback 回复模式，完整 AI 回复能力将在 agent_native 接入后启用。"
    return f"收到你的消息：\"{prompt[:50]}{'...' if len(prompt)>50 else ''}\"。\n\n⚠️ 当前处于 fallback 模式，agent_native 暂未完全启动。完整聊天功能正在开发中。"
