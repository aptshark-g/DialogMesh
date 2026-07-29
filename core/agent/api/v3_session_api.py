"""v3 Session API — bridges old frontend to v6 agent_native backend."""

import uuid, time, logging, traceback, json, os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
TASK_GRAPHS_DIR = os.path.join(DATA_DIR, "task_graphs")
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v3/session")

# ═══ Persistence ═══
_SESSIONS_FILE = Path(os.path.join(DATA_DIR, "v3_sessions.json"))
_SESSIONS_LOCK = __import__("threading").Lock()

def _load_sessions() -> Dict[str, Dict[str, Any]]:
    """Load sessions from JSON file."""
    try:
        if _SESSIONS_FILE.exists():
            with open(_SESSIONS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Failed to load sessions: %s", e)
    return {}

def _save_sessions():
    """Save sessions to JSON file (thread-safe)."""
    with _SESSIONS_LOCK:
        try:
            _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(_SESSIONS_FILE) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_sessions, f, ensure_ascii=False, default=str)
            os.replace(tmp, str(_SESSIONS_FILE))
        except Exception as e:
            logger.warning("Failed to save sessions: %s", e)

# Load sessions at module import time
_sessions: Dict[str, Dict[str, Any]] = _load_sessions()


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
    _save_sessions()
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
    _save_sessions()

    t0 = time.time()
    content = ""
    msg_id = str(uuid.uuid4())[:8]  # generate early for tracing
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

        # Phase 3.5: Execute BlueprintDAG via Decider (EventBus) — enrich context
        decider_context = ""
        chain_summary = {}
        ticks_count = 0
        dag_nodes = 0
        trace_errors = []
        try:
            from core.agent.blueprint.engine import BlueprintEngine
            from core.agent.orchestrator.agent_native import AgentOrchestrator
            from core.agent.blueprint.tracer import PipelineTracer
            engine = BlueprintEngine()
            intent = cognitive_ctx.get("intents", {}).get("primary", "")
            if not intent:
                segments = cognitive_ctx.get("intents", {}).get("segments", [])
                intent = segments[0] if segments else "通用对话"
            dag = engine.build(req.content, intent=intent)
            dag_nodes = dag.node_count
            orch = AgentOrchestrator()
            chain_result = orch.process_dag(dag, user_text=req.content)
            ticks_count = len(chain_result.get("ticks", []))
            # Build context enrichment
            chain_parts = []
            for node_id, output in chain_result.get("chain_outputs", {}).items():
                status = "ok" if output and not output.get("error") else "empty"
                chain = node_id.split("_")[0] if "_" in node_id else node_id
                chain_summary[chain] = status
                if node_id.startswith("intent"):
                    intents = output.get("intents", output)
                    chain_parts.append(f"意图: {str(intents)[:200]}")
                elif node_id.startswith("pcr"):
                    route = output.get("route", output)
                    chain_parts.append(f"路由: {str(route)[:200]}")
                elif node_id.startswith("context"):
                    chain_parts.append(f"上下文: {str(output.get('assembled_context', output))[:200]}")
            if chain_parts:
                decider_context = "## 管线分析\n" + "\n".join(chain_parts)
            # Record trace
            PipelineTracer.record(
                request_id=msg_id or str(uuid.uuid4())[:8],
                session_id=session_id,
                data={
                    "intent": intent,
                    "strategy": dag.strategy,
                    "blueprint_nodes": dag_nodes,
                    "chain_summary": chain_summary,
                    "ticks": ticks_count,
                    "errors": trace_errors,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
            )
        except Exception as e:
            logger.warning("Decider pipeline skipped: %s", e)
            trace_errors.append(str(e)[:200])

        # Enrich messages if decider provided context
        history = session["messages"][-20:]

        # Read confirmed task_graph from standalone storage
        tg_context = ""
        try:
            import os as _os2
            tg_path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
            if _os2.path.exists(tg_path):
                with open(tg_path, "r", encoding="utf-8") as f:
                    tg_data = json.load(f)
                tg_nodes = tg_data.get("nodes", [])
                tg_edges = tg_data.get("edges", [])
                if tg_nodes or tg_edges:
                    tg_context = f"\n\n[用户已确认的任务规划]\n节点: {json.dumps(tg_nodes, ensure_ascii=False)}\n连线: {json.dumps(tg_edges, ensure_ascii=False)}"
        except Exception:
            pass

        all_messages = [{"role": "system", "content": system_prompt}] + history
        if decider_context:
            all_messages[-1]["content"] = f"{req.content}\n\n{decider_context}"
        if tg_context:
            all_messages[-1]["content"] = all_messages[-1]["content"] + tg_context

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

        # ── Pipeline state persistence (discourse/behavior/profile) ──
        try:
            import os as _osp
            root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")
            os.makedirs(root, exist_ok=True)
            # Discourse: feed block tree
            from core.agent.compiler.discourse_block_tree import DiscourseBlockTreeManager
            dt = DiscourseBlockTreeManager()
            dt.feed(req.content, session_id)
            dt.feed(content[:500], session_id)
            rel = dt.get_block_relations(session_id)
            with open(os.path.join(root, "discourse_state.json"), "w", encoding="utf-8") as f:
                json.dump(rel, f, indent=2, ensure_ascii=False, default=str)
            # Profile: OCEAN dimension analysis from conversation
            pp = os.path.join(root, "profile_state.json")
            saved = {}
            try: saved = json.load(open(pp, encoding="utf-8"))
            except: pass
            saved["turn_count"] = saved.get("turn_count", 0) + 1
            # OCEAN keyword analysis
            dims = saved.get("dims", {"O":0.5,"C":0.5,"E":0.5,"A":0.5,"N":0.5})
            combined = (req.content + " " + content[:500]).lower()
            # O: openness — creativity, curiosity, abstract thinking
            o_kw = ["探索","创造","新","尝试","可能","抽象","设计","概念","模式","模型","哲学","理论"]
            o_hit = sum(1 for k in o_kw if k in combined)
            # C: conscientiousness — planning, organization, detail-oriented
            c_kw = ["计划","步骤","组织","完成","具体","明确","验证","测试","规范","标准","流程","结构"]
            c_hit = sum(1 for k in c_kw if k in combined)
            # E: extraversion — social, energetic, talkative
            e_kw = ["喜欢","觉得","感觉","我想","我觉得","朋友","交流","讨论","合作","团队"]
            e_hit = sum(1 for k in e_kw if k in combined)
            # A: agreeableness — cooperative, trusting, helpful  
            a_kw = ["帮助","相信","信任","合作","友好","同意","支持","理解","尊重","包容"]
            a_hit = sum(1 for k in a_kw if k in combined)
            # N: neuroticism — anxiety, emotional intensity
            n_kw = ["担心","焦虑","可能不行","问题","困难","复杂","麻烦","错误","失败"]
            n_hit = sum(1 for k in n_kw if k in combined)
            # Update with momentum (smoothing)
            alpha = 0.3  # update rate
            dims["O"] = round(dims["O"] * (1-alpha) + min(1.0, 0.3 + o_hit * 0.07) * alpha, 2)
            dims["C"] = round(dims["C"] * (1-alpha) + min(1.0, 0.3 + c_hit * 0.07) * alpha, 2)
            dims["E"] = round(dims["E"] * (1-alpha) + min(1.0, 0.3 + e_hit * 0.07) * alpha, 2)
            dims["A"] = round(dims["A"] * (1-alpha) + min(1.0, 0.3 + a_hit * 0.07) * alpha, 2)
            dims["N"] = round(dims["N"] * (1-alpha) + min(1.0, 0.3 + n_hit * 0.07) * alpha, 2)
            saved["dims"] = dims
            with open(pp, "w", encoding="utf-8") as f:
                json.dump(saved, f, indent=2, ensure_ascii=False)
            # Meta: save turn count
            with open(os.path.join(root, "meta_state.json"), "w", encoding="utf-8") as f:
                json.dump({"turn_count": saved["turn_count"]}, f, indent=2, ensure_ascii=False)
            logger.debug("Pipeline state persisted: discourse + profile + meta")            # Rule enforcement: check engineering constraints against user message
            try:
                rules_path = os.path.join(root, "data", "engineering_rules.json")
                rules_data = {}
                if os.path.exists(rules_path):
                    rules_data = json.load(open(rules_path, encoding="utf-8"))
                for rule in rules_data.get("rules", []):
                    pattern = rule.get("pattern", "")
                    rtype = rule.get("type", "")
                    if pattern and pattern.lower() in req.content.lower():
                        # Rule triggered — record annotation
                        ann_path = os.path.join(root, "data", "annotations.json")
                        annotations = []
                        if os.path.exists(ann_path):
                            try: annotations = json.load(open(ann_path, encoding="utf-8"))
                            except: pass
                        annotations.append({
                            "rule_id": rule.get("id", ""),
                            "type": rtype,
                            "pattern": pattern,
                            "message": req.content[:100],
                            "session_id": session_id,
                            "timestamp": time.time(),
                        })
                        with open(ann_path, "w", encoding="utf-8") as f:
                            json.dump(annotations[-20:], f, indent=2, ensure_ascii=False)
            except: pass
        except Exception as _ep:
        except Exception as _ep:
            logger.debug("Pipeline state persist skipped: %s", _ep)

        # Phase 5: Extract task plan from LLM response (preferred) or fall back to BlueprintEngine
        task_graph = []
        # Try to parse LLM-generated task JSON first
        parsed = _parse_plan_json(content)
        if parsed:
            task_graph = parsed
        else:
            # Fall back to BlueprintEngine
            try:
                from core.agent.blueprint.engine import BlueprintEngine
                engine = BlueprintEngine()
                intent = cognitive_ctx.get("intents", {}).get("primary", "")
                if not intent:
                    segments = cognitive_ctx.get("intents", {}).get("segments", [])
                    intent = segments[0] if segments else "通用对话"
                dag = engine.build(req.content, intent=intent)
                for n in dag.nodes:
                    task_graph.append({
                        "id": n.node_id,
                        "name": f"{n.chain}",
                        "type": n.chain,
                        "status": "pending",
                        "dependencies": [e.from_node for e in dag.edges if e.to_node == n.node_id],
                    })
            except Exception as e:
                logger.warning("BlueprintEngine failed: %s", e)
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        content = _fallback_reply(req.content)
    latency = int((time.time() - t0) * 1000)
    session["messages"].append({"role": "assistant", "content": content})
    _save_sessions()

    # Also save task_graph as standalone resource — only if no user-confirmed version exists
    if task_graph:
        try:
            import os as _os
            tg_path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
            if not _os.path.exists(tg_path):  # don't overwrite user's confirmed edits
                _os.makedirs(TASK_GRAPHS_DIR, exist_ok=True)
                with open(tg_path, "w") as f:
                    json.dump({"nodes": task_graph, "edges": []}, f, ensure_ascii=False)
        except Exception:
            pass

    return SendMessageResponse(
        message_id=msg_id,
        session_id=session_id,
        status="accepted",
        content=content,
        task_graph=task_graph,
        latency_ms=latency,
    )


class DAGEditRequest(BaseModel):
    """LLM-driven DAG editing via natural language."""
    instruction: str          # "把上下文那步移到子图之后"
    current_nodes: list = []  # Current DAG nodes


@router.post("/{session_id}/dag-edit")
async def edit_dag(session_id: str, req: DAGEditRequest):
    """LLM modifies the DAG based on natural language instruction."""
    try:
        import json as _json, urllib.request
        nodes_text = _json.dumps(req.current_nodes, ensure_ascii=False)
        prompt = (
            f"当前任务图节点:\n{nodes_text}\n\n"
            f"用户指令: {req.instruction}\n\n"
            f"请输出修改后的节点列表(JSON数组), 保持相同格式。"
            f"只输出 JSON, 不要其他文字。"
        )
        body = _json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": "你是 DAG 编辑器。根据用户指令修改任务图节点列表。"},
                {"role": "user", "content": prompt},
            ],
        }).encode()
        http_req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions",
            data=body,
            headers={"Authorization": "Bearer dm-client", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_req, timeout=30) as resp:
            data = _json.loads(resp.read())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Extract JSON
        import re
        match = re.search(r'\[[\s\S]*\]', content)
        updated_nodes = _json.loads(match.group()) if match else req.current_nodes
        return {"status": "ok", "nodes": updated_nodes}
    except Exception as e:
        logger.warning("DAG edit failed: %s", e)
        return {"status": "error", "error": str(e)[:200], "nodes": req.current_nodes}


class TaskGraphUpdateRequest(BaseModel):
    nodes: list = []
    edges: list = []


@router.get("/{session_id}/task-graph")
async def get_task_graph(session_id: str):
    """Return the standalone task graph for a session."""
    try:
        import json, os
        path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        # Fallback: extract from session messages
        session_path = os.path.join(DATA_DIR, "v3_sessions.json")
        if os.path.exists(session_path):
            with open(session_path, "r") as f:
                sessions = json.load(f)
            s = sessions.get(session_id, {})
            for msg in reversed(s.get("messages", [])):
                if msg.get("metadata", {}).get("taskGraph"):
                    return {"nodes": msg["metadata"]["taskGraph"], "edges": []}
        return {"nodes": [], "edges": []}
    except Exception as e:
        logger.warning("Get task_graph failed: %s", e)
        return {"nodes": [], "edges": []}


@router.put("/{session_id}/task-graph")
async def update_task_graph(session_id: str, req: TaskGraphUpdateRequest):
    """Persist user-modified task graph as a standalone resource."""
    try:
        import json, os
        os.makedirs(TASK_GRAPHS_DIR, exist_ok=True)
        path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
        with open(path, "w") as f:
            json.dump({"nodes": req.nodes, "edges": req.edges}, f, ensure_ascii=False, indent=2)
        logger.info("Saved task_graph for session %s: %d nodes", session_id[:8], len(req.nodes))
        return {"status": "ok", "nodes": req.nodes, "edges": req.edges}
    except Exception as e:
        logger.warning("Task graph save failed: %s", e)
        return {"status": "error", "error": str(e)[:200]}


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
    parts = ["你是 DialogMesh v6 认知助手。根据用户画像调整回复风格，保持专业但自然。"]

    if profile_text:
        parts.append(profile_text)

    if cognitive_ctx:
        intents = cognitive_ctx.get("intents", {})
        route = cognitive_ctx.get("route", {})
        compass = cognitive_ctx.get("compass", {})

        segments = intents.get("segments", [])
        if segments:
            parts.append(f"当前用户意图: {'、'.join(segments)} (置信度 {intents.get('confidence', 0):.2f})")

        compass_signal = compass.get("signal", "")
        if compass_signal and len(str(compass_signal)) < 200:
            parts.append(f"信号检测: {str(compass_signal)[:200]}")

        zone = route.get("zone", "")
        if zone:
            parts.append(f"路由区域: {zone}")

    parts.append("当用户要求规划任务或编排流程时，请在回复末尾附上任务计划 JSON。格式如下：\n```json\n[{\"id\":\"1\",\"name\":\"任务名\",\"description\":\"说明\",\"status\":\"pending\",\"node_type\":\"write|analyze|explain|scan|read\",\"depends_on\":[]}]\n```\n步骤控制在 3-7 个。同时回复文字说明。系统会提取 JSON 在任务页面展示，用户可修改后确认执行。")
    parts.append("当上下文包含 [用户已确认的任务规划] 时，用户已审核通过这些任务。你应该按任务逐个执行，每完成一个就在回复中标记进度。使用你的工具（terminal、write_file 等）实际完成这些任务，而不是只描述计划。")
    parts.append("用中文回复。支持 Markdown 格式（含 mermaid 流程图）。")
    return "\n".join(parts)


def _json_compact(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, default=str)[:500]


_PLANNER_SYSTEM = """你是 DialogMesh 任务规划器。根据用户消息和助手回复，生成结构化任务计划。

输出格式（严格 JSON 数组）：
```json
[
  {"id":"1","name":"步骤名称","description":"详细说明","status":"PENDING","node_type":"scan|read|write|analyze|ask_user|explain|fallback","depends_on":[],"is_destructive":false},
  {"id":"2","name":"步骤2","description":"...","status":"PENDING","node_type":"analyze","depends_on":["1"],"is_destructive":false}
]
```

规则:
- id 为数字字符串 "1","2","3"
- depends_on 列出依赖的前置步骤 id
- node_type: scan(扫描/收集)/read(读取)/write(写入/修改)/analyze(分析)/ask_user(询问用户)/explain(解释)/fallback(兜底)
- is_destructive: 是否不可逆操作
- 步骤控制在 3-7 个

只输出 JSON，不要其他文字。"""


def _build_plan_prompt(user_msg: str, reply: str, cognitive_ctx: dict) -> str:
    intents = cognitive_ctx.get("intents", {})
    segments = intents.get("segments", [])
    intent_text = "、".join(segments) if segments else "通用对话"
    return f"用户消息: {user_msg}\n助手回复摘要: {reply[:300]}\n识别意图: {intent_text}\n\n请生成任务计划。"


def _parse_plan_json(text: str) -> list:
    """Extract JSON array from LLM plan output and normalize to frontend TaskGraphNode."""
    import json, re
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        return []
    try:
        raw = json.loads(match.group())
    except:
        return []
    # Normalize LLM output → frontend TaskGraphNode fields
    nodes = []
    for n in raw:
        if not isinstance(n, dict):
            continue
        nodes.append({
            "id": str(n.get("id", "")),
            "name": n.get("name", ""),
            "type": n.get("node_type", n.get("type", "generic")),
            "status": str(n.get("status", "pending")).lower(),
            "dependencies": n.get("depends_on", n.get("dependencies", [])),
            "description": n.get("description", ""),
        })
    return nodes


def _fallback_reply(prompt: str) -> str:
    """Generate a simple fallback reply when LLM is unavailable."""
    prompt_lower = prompt.strip().lower()
    if any(w in prompt_lower for w in ["你好", "hello", "hi"]):
        return "你好！我是 DialogMesh v6 助手。目前 agent_native 尚未完全接入，我会在后续版本中提供更完整的回复。有什么可以帮你的？"
    if "?" in prompt_lower or "？" in prompt_lower:
        return "这是一个好问题。当前我正在使用 fallback 回复模式，完整 AI 回复能力将在 agent_native 接入后启用。"
    return f"收到你的消息：\"{prompt[:50]}{'...' if len(prompt)>50 else ''}\"。\n\n⚠️ 当前处于 fallback 模式，agent_native 暂未完全启动。完整聊天功能正在开发中。"
