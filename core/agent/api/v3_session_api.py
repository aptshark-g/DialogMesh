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


class _GatewayLLMAdapter:
    """内部模块 generate() 接口 → switch 网关（2026-08-13）。

    DualTrack/意图分类等模块期望 llm.generate(prompt, max_tokens,
    temperature); 接网关 deepseek-v4-flash, thinking 关闭（分类无需推理,
    快且稳）。此前这些模块 llm=None 走结构式降级, 意图分类恒失效。
    """

    def generate(self, prompt, max_tokens: int = 300,
                 temperature: float = 0.1, timeout_s: float = 20.0,
                 **kwargs) -> str:
        # 兼容两种调用约定（2026-08-16, 真 HyDE 评测接入）:
        #   _chat_once（recall_service._hyde_hypotheses）传 GenerateRequest
        #   对象（含 metadata.thinking）; 直接调用方传纯字符串。
        if hasattr(prompt, "prompt"):
            _req = prompt
            prompt = _req.prompt
            if getattr(_req, "max_tokens", None):
                max_tokens = _req.max_tokens
            if getattr(_req, "temperature", None) is not None:
                temperature = _req.temperature
            if getattr(_req, "timeout_ms", None):
                timeout_s = _req.timeout_ms / 1000.0
        import urllib.request
        import time as _time
        _t0 = _time.time()
        from core.agent.meta.governor import get_governor
        _gov = get_governor()
        if not _gov.allow("intent_classify"):
            raise ConnectionError("governor_open: intent_classify")
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens, "temperature": temperature,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                d = json.loads(resp.read())
            text = d["choices"][0]["message"].get("content") or ""
            from core.agent.llm.call_recorder import record_llm_call
            record_llm_call(
                stage="intent_classify", latency_ms=(_time.time() - _t0) * 1000,
                ok=bool(text), empty=not text)
            _gov.observe("intent_classify", bool(text))
            return text
        except Exception as e:
            from core.agent.llm.call_recorder import record_llm_call
            record_llm_call(
                stage="intent_classify", latency_ms=(_time.time() - _t0) * 1000,
                ok=False, error=str(e)[:120])
            _gov.observe("intent_classify", False, error=str(e))
            raise

    def classify_intent(self, text: str, budget_s: float = 20.0) -> str:
        """LLM 意图分类（2026-08-13, W1 正解）: 自由问句 → 固定意图集。

        泛化: LLM 理解改写/换说法, 不像关键词字面匹配那样脆;
        软编码: 意图集集中定义, 扩展只改一处;
        运行时可调: 每次消息都走一次分类（thinking 关闭, ~1s）。
        """
        categories = (
            "记忆召回（查历史对话/文档/知识/算法/原理/介绍/解释）|"
            "任务规划（规划/编排/任务图）|"
            "代码分析（写代码/改代码/审查代码/修bug）|"
            "数据搜索（查数据/查配置/找文件）|"
            "因果推理（为什么/原因/因果）|"
            "通用讨论（观点/设计/架构讨论）|"
            "casual（仅问候/闲聊/寒暄, 如'你好''在吗'）|"
            "通用对话（其他）"
        )
        prompt = (
            "把用户消息归类为以下意图之一（只输出类别名, 不要其他文字）。\n"
            "注意: 让 AI 写代码/做程序/实现功能/运行测试/写文件属于"
            "'代码分析'或'任务规划', 绝不是 casual。\n"
            f"{categories}\n\n"
            "示例:\n"
            "用户: 帮我写个五子棋 → 代码分析\n"
            "用户: 你好呀 → casual\n"
            "用户: 规划一下这个功能的实现步骤 → 任务规划\n\n"
            f"用户消息: {text[:300]}"
        )
        from core.agent.meta.governor import get_governor
        if not get_governor().allow("intent_classify"):
            return ""  # 熔断开断 → 快速降级（调用方走 DualTrack fallback）
        raw = self.generate(prompt, max_tokens=20, temperature=0.0,
                            timeout_s=budget_s)
        for cat in ("记忆召回", "任务规划", "代码分析", "数据搜索",
                    "因果推理", "通用讨论", "casual", "通用对话"):
            if cat in raw:
                return cat
        return "通用对话"


class _PlanningGatewayProvider:
    """PlanningSkill 期望的 generate_async → switch 网关（2026-08-16）。

    PlanningSkill（六策略规划器, 此前从未接生产）的 LLM provider 适配:
    把 GenerateRequest_v3 转网关调用（deepseek-v4-flash, thinking 关）。
    """

    def __init__(self, gateway_url: str = "http://127.0.0.1:8080/v1/chat/completions",
                 budget_s: float = 15.0, trace_id: str = ""):
        self._url = gateway_url
        self._budget_s = budget_s
        self._trace_id = trace_id  # §11.2: planning 在 to_thread 线程,
        # thread-local 不继承, 显式透传请求 trace_id

    async def generate_async(self, request):
        import asyncio as _aio
        import types as _types
        text = await _aio.to_thread(self._call, request)
        return _types.SimpleNamespace(
            success=bool(text), text=text,
            error_type=None if text else "empty")

    def _call(self, request):
        import urllib.request
        import time as _time
        _t0 = _time.time()
        if self._trace_id:
            try:
                from core.agent.event.tracer import set_trace_context
                set_trace_context(trace_id=self._trace_id)
            except Exception:
                pass
        from core.agent.meta.governor import get_governor
        _gov = get_governor()
        if not _gov.allow("planning"):
            raise ConnectionError("governor_open: planning")
        prompt = str(getattr(request, "prompt", "") or "")
        if not prompt:
            return ""
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": int(getattr(request, "max_tokens", 2048)),
            "temperature": float(getattr(request, "temperature", 0.2)),
        }).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        try:
            with urllib.request.urlopen(
                    req, timeout=min(15.0, self._budget_s)) as resp:
                d = json.loads(resp.read())
            text = d["choices"][0]["message"].get("content") or ""
            from core.agent.llm.call_recorder import record_llm_call
            record_llm_call(
                stage="planning",
                latency_ms=(_time.time() - _t0) * 1000,
                ok=bool(text), empty=not text)
            _gov.observe("planning", bool(text))
            return text
        except Exception as e:
            from core.agent.llm.call_recorder import record_llm_call
            record_llm_call(
                stage="planning",
                latency_ms=(_time.time() - _t0) * 1000,
                ok=False, error=str(e)[:120])
            _gov.observe("planning", False, error=str(e))
            raise


def _taskgraph_topological_steps(tg) -> list:
    """TaskGraph_v3 节点 → 拓扑序步骤名（Kahn; 环保护追加剩余）。"""
    import collections
    indeg = {nid: 0 for nid in tg.nodes}
    adj = {nid: [] for nid in tg.nodes}
    for e in tg.edges:
        if e.source_id in tg.nodes and e.target_id in tg.nodes:
            adj[e.source_id].append(e.target_id)
            indeg[e.target_id] += 1
    q = collections.deque([nid for nid, d in indeg.items() if d == 0])
    out = []
    while q:
        nid = q.popleft()
        node = tg.nodes[nid]
        out.append(str(node.name or node.goal or nid))
        for t in adj[nid]:
            indeg[t] -= 1
            if indeg[t] == 0:
                q.append(t)
    if len(out) < len(tg.nodes):
        done = set(out)
        for nid, node in tg.nodes.items():
            label = str(node.name or node.goal or nid)
            if label not in done:
                out.append(label)
                done.add(label)
    return out


def _taskgraph_to_frontend(tg) -> list:
    """TaskGraph_v3 → 前端 task_graph 格式（对齐 _parse_plan_json 输出）。"""
    front = []
    for nid, node in tg.nodes.items():
        deps = [e.source_id for e in tg.edges if e.target_id == nid]
        front.append({
            "id": nid,
            "name": node.name or node.goal or nid,
            "type": "plan",
            "status": "pending",
            "dependencies": deps,
            "description": node.goal or "",
        })
    return front


async def _plan_with_skill(text: str, intent_label: str,
                           budget_s: float = 15.0, trace_id: str = ""):
    """第二规划通道（2026-08-16）: PlanningSkill 生成任务图。

    返回 (steps: List[str] | None, frontend_task_graph: List[dict] | None)。
    HYBRID 策略: 网关可用 → 规则骨架 + LLM 细化; 网关不可用 →
    规则骨架兜底（_plan_hybrid 内部捕获）。全失败 → (None, None),
    调用方静默回退现有路径, 不阻塞主链路。
    """
    try:
        from core.agent.planner.planner import PlanningSkill
        from core.agent.v3_legacy.data_models import Intent_v3
        from core.agent.v3_common.models import IntentCategory
        intent = Intent_v3(
            raw_input=text, normalized_input=text,
            category=IntentCategory.UNKNOWN,
            confidence=0.8,
            metadata={"intent_label": intent_label},
        )
        planner = PlanningSkill(llm_provider=_PlanningGatewayProvider(
            budget_s=budget_s, trace_id=trace_id))
        result = await planner.plan(intent)
        tg = getattr(result, "task_graph", None)
        if not result.success or tg is None or not tg.nodes:
            return None, None
        steps = _taskgraph_topological_steps(tg)
        if not steps:
            return None, None
        return steps, _taskgraph_to_frontend(tg)
    except Exception as e:
        logger.debug("planning skill skipped: %s", e)
        return None, None


# ═══ Persistence ═══
_SESSIONS_FILE = Path(os.path.join(DATA_DIR, "v3_sessions.json"))
_SESSIONS_LOCK = __import__("threading").Lock()
# 2026-08-14（吸收 O2 并发纪律）: 同会话防双跑 — 每个 session 一把
# 执行锁, 工具循环串行（避免两条 tool_loop 并发污染同一执行树/文件）。
_SESSION_EXEC_LOCKS: Dict[str, Any] = {}
_SESSION_EXEC_LOCKS_GUARD = __import__("threading").Lock()


def _session_exec_lock(session_id: str):
    with _SESSION_EXEC_LOCKS_GUARD:
        lock = _SESSION_EXEC_LOCKS.get(session_id)
        if lock is None:
            lock = __import__("threading").Lock()
            _SESSION_EXEC_LOCKS[session_id] = lock
        return lock

# ═══ Task Graph Workspace (内存态=热 / 落盘=温, 版本冲突检测) ═══
_TASK_GRAPH_WORKSPACES: Dict[str, Dict[str, Any]] = {}
_TASK_GRAPHS_LOCK = __import__("threading").Lock()


def _get_task_graph_ws(session_id: str) -> Dict[str, Any]:
    """内存态优先; 无则读盘兜底; 返回 {nodes, edges, version, execution}。"""
    with _TASK_GRAPHS_LOCK:
        ws = _TASK_GRAPH_WORKSPACES.get(session_id)
        if ws is not None:
            return {"nodes": list(ws.get("nodes", [])), "edges": list(ws.get("edges", [])),
                    "version": int(ws.get("version", 0)),
                    "execution": dict(ws.get("execution") or {})}
    path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entry = {"nodes": data.get("nodes", []), "edges": data.get("edges", []),
                     "version": int(data.get("version", 1)),
                     "execution": data.get("execution") or {}}
            with _TASK_GRAPHS_LOCK:
                _TASK_GRAPH_WORKSPACES[session_id] = dict(entry)
            return entry
        except Exception as e:
            logger.warning("Load task_graph failed: %s", e)
    return {"nodes": [], "edges": [], "version": 0, "execution": {}}


def _persist_task_graph(session_id: str, ws: Dict[str, Any]) -> None:
    """写盘（温层, 含 version）。"""
    try:
        os.makedirs(TASK_GRAPHS_DIR, exist_ok=True)
        path = os.path.join(TASK_GRAPHS_DIR, f"{session_id}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"nodes": ws["nodes"], "edges": ws["edges"],
                       "version": ws["version"],
                       "execution": ws.get("execution") or {}},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Persist task_graph failed: %s", e)


def _put_task_execution(session_id: str, node_id: str,
                        exec_result: Dict[str, Any]) -> None:
    """记录一次节点执行迹（热内存 + 温落盘, v2 执行层白盒视图）。"""
    ws = _get_task_graph_ws(session_id)
    execs = dict(ws.get("execution") or {})
    execs[node_id] = exec_result
    with _TASK_GRAPHS_LOCK:
        current = _TASK_GRAPH_WORKSPACES.get(session_id) or {
            "nodes": ws.get("nodes", []), "edges": ws.get("edges", []),
            "version": ws.get("version", 0)}
        current = dict(current)
        current["execution"] = execs
        _TASK_GRAPH_WORKSPACES[session_id] = current
    _persist_task_graph(session_id, current)


def _put_task_graph(session_id: str, nodes: list, edges: list, version: Optional[int] = None) -> Dict[str, Any]:
    """写入工作区（热）并落盘（温）。不带 version = 强制覆盖（向后兼容）;
    带 version 且落后于当前 = 409 冲突。返回最新 entry。"""
    current = _get_task_graph_ws(session_id)
    cur_v = current["version"]
    if version is not None and version < cur_v:
        raise HTTPException(status_code=409, detail={
            "error": "version_conflict",
            "current_version": cur_v,
            "nodes": current["nodes"],
            "edges": current["edges"],
        })
    entry = {"nodes": nodes, "edges": edges, "version": cur_v + 1,
             "execution": current.get("execution") or {}}
    with _TASK_GRAPHS_LOCK:
        _TASK_GRAPH_WORKSPACES[session_id] = dict(entry)
    _persist_task_graph(session_id, entry)
    return entry


def _seed_task_graph(session_id: str, nodes: list) -> bool:
    """LLM 规划落盘 — 仅在无用户确认版本（version==0）时写入, 不覆盖用户编辑。"""
    current = _get_task_graph_ws(session_id)
    if current["version"] > 0:
        return False
    entry = {"nodes": nodes, "edges": [],
             "version": 1,
             "execution": current.get("execution") or {}}
    with _TASK_GRAPHS_LOCK:
        _TASK_GRAPH_WORKSPACES[session_id] = dict(entry)
    _persist_task_graph(session_id, entry)
    return True

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


class CreateSessionRequest(BaseModel):
    project_id: Optional[str] = None


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
async def create_session(req: Optional[CreateSessionRequest] = None):
    sid = str(uuid.uuid4())[:12]
    pid = (req.project_id if req else None) or None
    _sessions[sid] = {"created_at": time.time(), "messages": [],
                      "project_id": pid}
    if pid:
        # B16（2026-08-17）: 新建会话携带项目 → 同步归属映射。
        from core.agent.api.projects_api import set_session_project
        set_session_project(sid, pid)
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
        _sessions[session_id] = {"created_at": time.time(), "messages": [],
                                 "project_id": None}

    session = _sessions[session_id]
    session["messages"].append({"role": "user", "content": req.content})
    _save_sessions()

    t0 = time.time()
    # 2026-08-16（P1-② 观测）: 请求阶段计时 spans — 卡在哪直接查,
    # 不再靠猜（HA_EXECUTION_ANALYSIS §二.2 同类观测原则）。
    spans: dict = {"t0_ms": round(t0 * 1000, 1)}

    def _mark(name: str) -> None:
        spans[name] = round((time.time() - t0) * 1000, 1)

    # 2026-08-16（请求级总预算, HA_EXECUTION_ANALYSIS §三）: 单请求
    # 150s 总预算, 沿 classify→planning→TaskRunner 传剩余时间; 任何
    # 阶段超预算显式降级（骨架/直接回复）, 不再各层独立超时串行叠加。
    _req_deadline = time.time() + 150.0

    def _budget_left(min_s: float = 5.0) -> float:
        return max(min_s, _req_deadline - time.time())

    content = ""
    msg_id = str(uuid.uuid4())[:8]  # generate early for tracing
    # 2026-08-16（§11.2 trace_id 传播）: 请求级 trace_id 设置到 thread-local
    # TraceContext —— tool_loop/事件链/执行树同线程自动继承, /v6/trace 可
    # 按 trace_id 串整条链路（此前 msg_id 只在 post-LLM 事件出现）。
    try:
        from core.agent.event.tracer import set_trace_context
        set_trace_context(trace_id=msg_id, session_id=session_id)
    except Exception:
        pass
    # 防御初始化（B4-1-P2 全栈实测）: task_graph 在 try 内 Phase 5 才赋值，
    # 网关离线走 except 跳过后 `if task_graph:` 会 UnboundLocalError —
    # 本环境 switch 8080 未运行时这正是常态路径。
    task_graph = []
    try:
        # Phase 1: Cognitive analysis via AgentOrchestrator
        import json as _json
        cognitive_ctx = {}
        try:
            # M4-P3 (G1+G3-P3): 数据源从空壳 AgentOrchestrator 换真引擎。
            # 原 L125 无参构造 AgentOrchestrator() → 核心链全 None →
            # intents/route 恒空 = 认知结果被丢弃/伪造的数据流断裂。
            # 现在: 引擎 PCR router + IntentParser 轻量认知（不重跑 post-LLM
            # 管线, 避免与 L262 StateMachine 双跑）。保留 try/except fallback。
            from core.agent.cli.engine import get_engine
            eng = get_engine()
            _mark("phase1_get_engine")
            route_meta, intent_meta = {}, {}
            if eng is not None:
                pcr = getattr(eng, '_pcr_router', None)
                if pcr is not None:
                    try:
                        r = pcr.route(req.content)
                        if r is not None:
                            route_meta = {"zone": getattr(r, 'zone', 'MIXED')}
                            eng._last_pcr = r
                    except Exception:
                        pass
            _mark("phase1_pcr")
            parser = getattr(eng, '_intent_parser', None)
            if parser is not None:
                try:
                    pr = parser.parse(user_input=req.content)
                    eng._last_parse_result = pr
                    intent = getattr(pr, 'intent', None)
                    if intent is not None:
                        intent_meta = {
                            "segments": (getattr(intent, 'segments', None)
                                         or [req.content[:30]]),
                            "confidence": getattr(intent, 'confidence', 0.5),
                            "category": str(getattr(intent, 'category',
                                                   'general')),
                        }
                except Exception:
                    pass
            _mark("phase1_parse")
            if not route_meta:
                route_meta = {"zone": "MIXED"}
            cognitive_ctx = {
                "intents": intent_meta,
                "route": route_meta,
                "compass": {},
                "context": {},
                "cognition": {},
            }
        except Exception as e:
            logger.warning("Cognitive pipeline skipped: %s", e)
        _mark("phase1_cognitive")

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
        _mark("phase2_profile")

        # Phase 3: Build messages with full context
        system_prompt = _build_system_prompt(profile_text, cognitive_ctx)

        # Phase 3.5: Build BlueprintDAG (view layer) + execute via StateMachine
        # (B2/G1: BlueprintExecutor no longer the primary executor - the
        # StateMachine consumes the DAG through registered phase handlers.
        # BlueprintExecutor stays available as a validation/replay tool.)
        decider_context = ""
        chain_summary = {}
        ticks_count = 0
        dag_nodes = 0
        trace_errors = []
        intent = "通用对话"  # function-level: Phase 3.5 sets real value, Phase 5 reuses
        _multi_segments: List[str] = []  # 多意图拆分段（recall 消费, 2026-08-13）
        try:
            from core.agent.blueprint.engine import BlueprintEngine
            from core.agent.blueprint.tracer import PipelineTracer
            from core.agent.cli.engine import get_engine
            _eng = get_engine()
            _dbus = getattr(_eng, "_decision_bus", None) if _eng is not None else None
            # GAP-D2: 共享 registry — 本地 BlueprintEngine 与 runtime engine
            # 的 learning_bridge 共用同一 SkillRegistry（match/learn 不分叉,
            # LEARNED_TEMPLATES 生命周期可挂载）。
            _shared_registry = None
            if _eng is not None:
                try:
                    _shared_registry = getattr(
                        _eng, "_learning_bridge", None) and \
                        getattr(_eng._learning_bridge, "registry", None)
                except Exception:
                    _shared_registry = None
            engine = BlueprintEngine(decision_bus=_dbus, registry=_shared_registry)
            # Real intent from DualTrack so the 5 built-in templates can
            # actually be selected (P0-7/P1-25). 2026-08-13: 接网关 LLM —
            # 此前无 llm 退化结构式返回原文, 意图分类恒失效（W1 死参数
            # 根因）; thinking 关闭（分类无需推理, 快且稳）。
            # 2026-08-13 升级: LLM 意图分类（自由问句→意图集, 泛化于
            # 关键词字面匹配）; 失败降级 DualTrack 拆分。
            try:
                from core.agent.intent.dual_track import DualTrackIntentPipeline
                _adapter = _GatewayLLMAdapter()
                try:
                    _cat = _adapter.classify_intent(
                        req.content, budget_s=_budget_left())
                    if _cat:
                        intent = _cat
                except Exception:
                    _cat = ""
                if not _cat or _cat == "通用对话":
                    # 5 链数据源接线（2026-08-13, 意图副路径实质化）:
                    # fallback 管线喂画像/关联链/话语上下文, 算法链
                    # 不再全 abstain; 历史 = 会话最近消息（discourse 链）。
                    _hist = [str(m.get("content", ""))[:200]
                             for m in (session.get("messages") or [])[-5:]]
                    dt = DualTrackIntentPipeline(
                        llm=_adapter,
                        profile_resolver=(
                            lambda: getattr(
                                getattr(_eng, "_ocean_analyst", None),
                                "profile", None)),
                        association_resolver=(
                            getattr(_eng, "_intent_association_snapshot", None)
                            if _eng is not None else None),
                        discourse_resolver=(
                            getattr(_eng, "_l3_discourse_topics", None)
                            if _eng is not None else None),
                    )
                    dt_res = dt.process(req.content, history=_hist)
                    segs = list(getattr(dt_res, "segments", []) or [])
                    if segs:
                        intent = segs[0]
                        # 多意图消费: 拆分段保留, Phase 4 喂 recall
                        if getattr(dt_res, "is_multi", False) and len(segs) > 1:
                            _multi_segments = segs[1:]
            except Exception:
                pass
            # 多意图入口（2026-08-13）: 检测到意图拆分段 → 显式走
            # intent_multi_recall 模板（intent 节点 segments → recall
            # 多路召回 → 子图扩展 → 回复）; 单意图走 registry match。
            dag = engine.build(
                req.content, intent=intent,
                template=("intent_multi_recall"
                          if _multi_segments else None))
            dag_nodes = dag.node_count
            # Execute through the live StateMachine (registered handlers map
            # DAG chains to PipelinePhases via CHAIN_TO_PHASE).
            eng = get_engine()
            sm = getattr(eng, "_state_machine", None) if eng is not None else None
            if sm is not None and hasattr(sm, "run_dag"):
                # 2026-08-16（P1-② 预算接入）: run_dag 内部 handler 是
                # 同步 LLM 调用（intent/discourse 首调实测 13-35s, 上游
                # 慢时吃 provider 默认 60s×N）——直接同步调用会阻塞事件
                # 循环, 健康端点都不可达（实测 120s+ 整机卡死）。
                # → 挪 executor 异步等待（事件循环保持响应）+ deadline
                # 传入 context（handler 预算闸, 见 event/handlers.py）。
                _loop = __import__("asyncio").get_event_loop()
                _dag_ctx = {
                    "text": req.content, "session_id": session_id,
                    "request_id": msg_id,
                    "intent": intent,
                    "deadline": _req_deadline,
                    "decision_bus": _dbus,
                    "meta_feedback": (getattr(_eng, "_meta_feedback", None)
                                      if _eng is not None else None),
                    # 执行轨迹落树（P0）: 传会话树供 agentic 节点
                    "discourse_tree": (
                        getattr(_eng, "_discourse_tree", None)
                        if _eng is not None else None),
                    # 2026-08-15: 七树容器（ExecutionTree 挂载点）—
                    # agentic 节点从 agent_tree.execution 落树
                    "agent_tree": (
                        _eng.get_agent_tree(session_id)
                        if _eng is not None else None),
                    "model": req.model or "deepseek-v4-flash",
                }
                chain_result = await _loop.run_in_executor(
                    None,
                    lambda: sm.run_dag(
                        dag,
                        # 2026-08-16: 生产路径主回复在 Phase 4 生成 —
                        # DAG 内 llm_reply 节点跳过（防双重 LLM 调用卡死）
                        defer_llm=True,
                        # async 段（behavior/meta）由 post-LLM 管线/事件
                        # 订阅完成, run_dag 内同步等待实测阻塞 19s
                        # （BehaviorBrain 初始化）→ 生产跳过
                        defer_async=True,
                        context=_dag_ctx))
                dag_results = chain_result.get("results", {})
                ticks_count = len(dag_results)
                # GAP-D2/D1: 生产学习注入 — run_dag 成功后沉淀含 tool 节点
                # 的成功 DAG + 收集蒸馏原料（走共享 engine 的 learning_bridge,
                # 保证 registry 与本地 BlueprintEngine 一致）。
                try:
                    _learn_ok = False
                    for _out in dag_results.values():
                        if _out and not _out.get("error"):
                            _learn_ok = True
                            break
                    if _learn_ok:
                        _learn_fn = getattr(_eng, "learn_from_execution", None)
                        if _learn_fn is not None:
                            # 2026-08-16（高可用）: 学习沉淀/蒸馏是 async
                            # 段 — 后台线程执行, 不阻塞响应（A16 快反馈）。
                            import threading as _th_learn
                            _th_learn.Thread(
                                target=_learn_fn,
                                args=(dag,),
                                kwargs={"intent": intent,
                                        "request_id": msg_id,
                                        "success": True},
                                daemon=True).start()
                except Exception as _le:
                    logger.debug("learn_from_execution failed: %s", _le)
                # 2026-08-15（七树闭环）: run_dag 内 agentic 工具节点
                # （statemachine → TaskRunner）落树后立即消费+持久化 —
                # 此前只有 Phase 4 独立 TaskRunner 触发消费, DAG 内节点
                # 的执行树从不落盘（A17 记录不删）。
                try:
                    if _eng is not None and hasattr(
                            _eng, "_consume_execution_tree"):
                        # 2026-08-16（高可用）: 树消费/持久化也是 async 段,
                        # 后台执行避免阻塞主响应（AgentTreeManager 每会话
                        # 独立, 后台消费与后续 TaskRunner 落树无竞态——
                        # 消费是只读观察 + 树写入）。
                        import threading as _th_consume
                        _th_consume.Thread(
                            target=_eng._consume_execution_tree,
                            args=(session_id,),
                            kwargs={"force": True},
                            daemon=True).start()
                except Exception as _ce:
                    logger.debug("dag execution tree consume failed: %s", _ce)
                # Build context enrichment
                chain_parts = []
                for node_id, output in dag_results.items():
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
                    # W2（2026-08-13）: 消费 recall_pipeline 模板节点输出 —
                    # recall_anchor/subgraph 产出的锚点+编译子图必须进 LLM
                    # 上下文, 否则"意图→召回→图扩展→回复"链路在 API 层断掉
                    # （此前只有 intent/pcr/context 摘要进上下文, 锚点被丢）。
                    elif node_id.startswith(("recall", "subgraph")):
                        _anchors_txt = (
                            output.get("anchors") or ""
                            if isinstance(output, dict) else "")
                        _sub_txt = (
                            output.get("compiled_subgraph")
                            or output.get("content")
                            or ""
                            if isinstance(output, dict) else "")
                        _part = (_anchors_txt or _sub_txt or "")
                        if _part:
                            chain_parts.append(
                                f"{node_id}: {str(_part)[:800]}")
                if chain_parts:
                    decider_context = "## 管线分析\n" + "\n".join(chain_parts)
            else:
                # StateMachine unavailable - skip execution (never fake it)
                logger.warning("Decider pipeline skipped: no StateMachine")
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
                    "phase_ms": spans,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
            )
        except Exception as e:
            logger.warning("Decider pipeline skipped: %s", e)
            trace_errors.append(str(e)[:200])
        _mark("phase3_dag")

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
        tool_loop_used = False
        try:
            # task 类请求 → LLM 自主工具调用循环（function calling）
            # W5（2026-08-13）: 意图路由把 task 类 query 统一送执行层轨 —
            # 此前只有 is_code_request 字面判定; 现在 任务规划/代码分析
            # 意图（LLM 分类, 泛化于关键词）也进 TaskRunner（宏观蓝图
            # 约束 + 微观工具执行 + 元认知监控）。task 类正解 = 调工具
            # 读真实内容（dir_list/grep/file_read）, 比纯召回上下文准。
            from core.agent.blueprint.code_request import is_code_request
            _task_intents = ("任务规划", "代码分析")
            if is_code_request(req.content) or intent in _task_intents:
                # v2 执行层（2026-08-09）: TaskRunner = tool_loop + 蓝图约束
                # 注入（已确认任务图作为宏观约束）+ 元认知监控 + 决策事件。
                from core.agent.llm.task_runner import (
                    TaskRunner, TaskConstraint)
                # 已确认任务图 → 允许范围约束（蓝图宏观 → 执行层微观）
                scope = ""
                steps = None
                try:
                    _tg = _get_task_graph_ws(session_id) or {}
                    _tgn = _tg.get("nodes") or []
                    if _tgn:
                        scope = ("用户已确认的任务规划: " + json.dumps(
                            [{"id": n.get("id"),
                              "name": n.get("name", n.get("type", ""))}
                             for n in _tgn], ensure_ascii=False)[:1500])
                        # 2026-08-15（规划→执行步骤级接线）: 任务图节点
                        # 作为步骤地图注入执行层（落执行树 + 注入上下文）
                        steps = [
                            str(n.get("name", n.get("type", "?")))
                            for n in _tgn[:12]]
                except Exception:
                    steps = None
                # 第二规划通道（2026-08-16）: 无用户确认任务图时, 尝试
                # PlanningSkill 六策略规划器（HYBRID: 通用骨架+LLM 细化）。
                # 失败静默回退现有路径（PlanningSkill 从不阻塞主链路）。
                if not steps:
                    try:
                        _plan_label = {
                            "任务规划": "task_planning",
                            "代码分析": "code_analysis",
                            "数据搜索": "data_search",
                            "记忆召回": "recall",
                        }.get(intent, "task_planning")
                        _psteps, _pfront = await _plan_with_skill(
                            req.content, _plan_label,
                            budget_s=_budget_left(), trace_id=msg_id)
                        if _psteps:
                            steps = _psteps
                            if _pfront:
                                _seed_task_graph(session_id, _pfront)
                    except Exception:
                        steps = None
                _dbus2 = None
                _mf2 = None
                _eng2 = None
                _ts2 = None
                try:
                    from core.agent.cli.engine import get_engine as _ge2
                    _eng2 = _ge2()
                    _dbus2 = (getattr(_eng2, "_decision_bus", None)
                              if _eng2 is not None else None)
                    _mf2 = (getattr(_eng2, "_meta_feedback", None)
                            if _eng2 is not None else None)
                    _lb2 = (getattr(_eng2, "_learning_bridge", None)
                            if _eng2 is not None else None)
                    _ts2 = (getattr(_lb2, "trace_store", None)
                            if _lb2 is not None else None)
                except Exception:
                    _dbus2 = None
                    _mf2 = None
                _ts2 = None
                # 执行轨迹落树（P0）: per-session AgentTreeManager.execution
                _exec_tree = None
                try:
                    # 2026-08-15 修复: 七树容器挂 engine._agent_trees —
                    # 旧代码从 _discourse_tree._trees 取 execution 恒 None
                    # （DiscourseBlockTreeManager 无 execution 属性）。
                    if _eng2 is not None and hasattr(
                            _eng2, "get_agent_tree"):
                        _exec_tree = getattr(
                            _eng2.get_agent_tree(session_id),
                            "execution", None)
                except Exception:
                    _exec_tree = None
                _runner = TaskRunner(decision_bus=_dbus2,
                                     meta_feedback=_mf2,
                                     trace_store=_ts2,
                                     model=req.model or "deepseek-v4-flash",
                                     execution_tree=_exec_tree)
                # v2.1 召回→执行层桥: 编码/施工类请求先粗召回当前目标,
                # 结果作为候选锚点注入执行上下文（精确查阅由执行层工具完成）。
                anchors = ""
                try:
                    from core.agent.recall.recall_service import (
                        RecallService, format_anchors)
                    _rs = RecallService(engine=_eng2)
                    _rr = _rs.recall(
                        req.content, intent=intent, top_k=5,
                        sid=session_id, expand_graph=True,
                        sub_queries=_multi_segments or None)
                    anchors = format_anchors(_rr, max_chars=1200)
                    # recall→subgraph 桥: 锚点作为 seed 编译子图
                    # （含事件溯源=生产情景 + 图扩展=关联内容）
                    try:
                        from core.agent.v4.cognitive.subgraph_compiler import (
                            SubgraphCompiler)
                        _sc = SubgraphCompiler(engine=_eng2)
                        # C 最小版（2026-08-14）: 文件命中候选池扩展
                        # 也作为子图锚点（只扩候选不抬排序）
                        _anchors = list(_rr.hits) + list(
                            getattr(_rr, "pool_extras", []))
                        _sctx = _sc.compile_from_anchors(
                            _anchors, event_id=msg_id)
                        _sub = _sc.assemble_prompt(_sctx)
                        if _sub and _sub.strip():
                            anchors = anchors + "\n\n" + _sub
                    except Exception:
                        pass
                except Exception:
                    anchors = ""
                _exec_lock = _session_exec_lock(session_id)
                with _exec_lock:
                    _tr = _runner.run(
                        goal=req.content,
                        constraint=TaskConstraint(
                            goal=req.content, scope=scope, steps=steps,
                            max_rounds=6,
                            timeout_s=_budget_left(min_s=30.0),
                            max_replans=1),
                        node_id="root_task", session_id=session_id,
                        request_id=msg_id, messages=all_messages,
                        anchors=anchors)
                    # 执行树消费端（阶段 5 接线）: 任务收尾立即审计 +
                    # 模式沉淀（force=True 旁路频率门控 — 终端状态
                    # 立即消费, Hermes force_persist 同语义）
                    try:
                        if _eng2 is not None and hasattr(
                                _eng2, "_consume_execution_tree"):
                            _eng2._consume_execution_tree(
                                session_id, force=True)
                    except Exception:
                        pass
                tool_loop_used = True
                content = _tr.content or ""
                if _tr.tool_calls or _tr.verdict != "continue":
                    _exec_summary = "; ".join(
                        f"{c.get('name', '?')}:"
                        f"{'ok' if c.get('ok') else 'fail'}"
                        for c in _tr.tool_calls[:8])
                    logger.info("tool_loop: %d calls (%s)",
                                len(_tr.tool_calls), _exec_summary)
                # 执行迹 → 会话工作区（前端 /v6/execution 白盒视图）
                try:
                    _put_task_execution(session_id, "root_task",
                                        _tr.to_dict())
                except Exception as _pe:
                    logger.debug("put execution failed: %s", _pe)
        except Exception as _tle:
            logger.debug("tool_loop skipped: %s", _tle)
            tool_loop_used = False
        _mark("phase4_execute")
        if not tool_loop_used:
            body = {
                "provider": req.provider or "deepseek",
                "model": req.model or "deepseek-v4-flash",
                "messages": all_messages,
                # 2026-08-14 修复: 网关默认 thinking 开 → deepseek-v4
                # 推理吃光预算空返回（与 tool_loop/call_switch 同因）。
                "thinking": {"type": "disabled"},
            }
            http_req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=_json.dumps(body).encode(),
                headers={"Authorization": "Bearer dm-client", "Content-Type": "application/json"},
            )
            content = ""
            data = {}
            import time as _llm_t0_mod
            _llm_t0 = _llm_t0_mod.time()
            from core.agent.meta.governor import get_governor
            _gov = get_governor()
            # 2026-08-15 修复: deepseek-v4-flash 密集输出随机空返回 →
            # 空响应重试 2 次（与 tool_loop/call_switch 同模式）。
            for _attempt in range(3):
                # 2026-08-16（高可用）: 预算感知 + 熔断 — 原 60s×3 固定
                # 重试无预算上限（最坏 180s）。每轮按剩余预算截断, 熔断
                # 开断快速失败, 预算不足不再磨蹭。
                if not _gov.allow("llm_reply"):
                    break
                if _budget_left(min_s=0) < 8.0:
                    break
                try:
                    with urllib.request.urlopen(
                            http_req,
                            timeout=min(60.0, _budget_left())) as resp:
                        data = _json.loads(resp.read())
                    content = data.get("choices", [{}])[0].get(
                        "message", {}).get("content", "")
                    if content:
                        _gov.observe("llm_reply", True)
                        break
                    _gov.observe("llm_reply", False, error="empty_response")
                except Exception as _ge:
                    _gov.observe("llm_reply", False, error=str(_ge)[:120])
                import time as _t
                _t.sleep(0.4 * (_attempt + 1))
            from core.agent.llm.call_recorder import record_llm_call
            record_llm_call(
                stage="llm_reply",
                latency_ms=(_llm_t0_mod.time() - _llm_t0) * 1000,
                ok=bool(content), empty=not content,
                retries=0, error="" if content else "empty_or_error")
            _mark("phase4_llm_reply")
            if not content:
                content = str(data)

        # ── 代码执行后处理（2026-08-08, "实现软件"链路）──
        # LLM 回复含 ```python 代码块 → 自动执行 → 输出追加到回复。
        # 确定性, 不依赖 LLM 生成 tool 节点（LLM_DRIVEN 候选全是认知链）。
        try:
            if not tool_loop_used:
                import re as _re
                blocks = _re.findall(r"```python\n(.*?)```", content, _re.S)
                if blocks:
                    from core.agent.tools.os_tools import _run_python
                    exec_parts = []
                    for i, code in enumerate(blocks[:3], 1):
                        res = _run_python(code=code, timeout_s=30)
                        out = (res.data or {}).get("stdout", "") if hasattr(res, "data") else ""
                        err = (res.data or {}).get("stderr", "") if hasattr(res, "data") else ""
                        status = "ok" if res.success else "error"
                        exec_parts.append(
                            f"### 代码执行结果 (块 {i}, {status})\n"
                            f"```\n{out[-1500:]}\n```\n"
                            + (f"stderr:\n```\n{err[-800:]}\n```\n" if err else ""))
                    if exec_parts:
                        content = content + "\n\n---\n\n" + "\n".join(exec_parts)
        except Exception as _ce:
            logger.debug("code exec post-processing failed: %s", _ce)

        # ── StateMachine: unified post-LLM pipeline ──
        sm_results = {}
        try:
            from core.agent.cli.engine import get_engine
            eng = get_engine()
            sm = getattr(eng, '_state_machine', None)
            if sm:
                from core.agent.event.statemachine import PipelinePhase
                ctx = {"text": req.content, "reply": content[:500], "session_id": session_id}
                sm_results = sm.run_pipeline(PipelinePhase.DISCOURSE, ctx)
                logger.debug("StateMachine: %s phases completed", len(sm_results))
            # Fire EventBus subscribers in parallel (async, not ordered)
            if eng and hasattr(eng, '_publish'):
                if not getattr(eng, '_event_subscribers', None):
                    try:
                        from core.agent.event.subscribers import wire_subscribers
                        wire_subscribers(eng)
                    except: pass
                # 2026-08-16（高可用）: _publish 名为 fire-and-forget 实为
                # 同步广播 — 订阅者（behavior learn / causal planner 懒加载）
                # 实测阻塞响应数十秒 → 改后台线程真正不阻塞（A16 快反馈）。
                import threading as _th
                _pub_payload = {
                    "text": req.content, "reply": content[:500],
                    "session_id": session_id}
                _th.Thread(
                    target=eng._publish,
                    args=("user_message", _pub_payload),
                    daemon=True).start()
                # 情景溯源（RECALL_SUBGRAPH_BRIDGE §三）: 显式写带 msg_id
                # 的事件（事件 id + trace_id = msg_id）, 让 _expand_from_event
                # 能按 msg_id 反查"会话要求"支线。跨模块 trace 传播（§11.2）
                # 仍是基建待办, 目前至少 user_message 事件可命中。
                try:
                    _el = getattr(eng, "_event_log", None)
                    if _el is not None and hasattr(_el, "put_event"):
                        _el.put_event(
                            event_id=msg_id, kind="user_message",
                            payload={"text": req.content,
                                     "reply": content[:500],
                                     "session_id": session_id},
                            trace_id=msg_id)
                except Exception:
                    pass
        except Exception as _ep:
            logger.debug("Post-LLM pipeline skipped: %s", _ep)

        # Phase 5: Extract task plan from LLM response
        # Try to parse LLM-generated task JSON first
        parsed = _parse_plan_json(content)
        if parsed:
            task_graph = parsed
        else:
            # Fall back to BlueprintEngine
            try:
                from core.agent.blueprint.engine import BlueprintEngine
                engine = BlueprintEngine()
                dag = engine.build(req.content, intent=intent)
                chain_names = {
                    "pcr": "认知路由分析", "intent": "意图解析",
                    "planner": "方案规划", "compiler": "上下文编译",
                    "router": "路由决策", "discourse": "对话结构分析",
                    "pipeline": "管线调度", "route": "路由分发",
                    "pcr/compute": "认知计算", "intent/parse": "意图识别",
                    "pipeline/route": "管线路由",
                }
                for n in dag.nodes:
                    cn = chain_names.get(n.chain, n.chain)
                    task_graph.append({
                        "id": n.node_id,
                        "name": cn,
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
            _seed_task_graph(session_id, task_graph)
        except Exception:
            pass

    return SendMessageResponse(
        message_id=msg_id,
        session_id=session_id,
        status="accepted",
        content=content,
        # 2026-08-16: intent 此前未传 → 响应恒默认 "chat"（分类器实际
        # 正确, 字段丢在响应层）。传真实意图供前端/路由观察。
        intent=intent,
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
            # 2026-08-14: 与主回复同因 — 关思考保 JSON 提取稳定
            "thinking": {"type": "disabled"},
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
    version: Optional[int] = None


@router.get("/{session_id}/task-graph")
async def get_task_graph(session_id: str):
    """Return the standalone task graph for a session (memory-first, disk fallback)."""
    try:
        entry = _get_task_graph_ws(session_id)
        if entry["nodes"] or entry["edges"]:
            return entry
        # Fallback: extract from session messages
        session_path = os.path.join(DATA_DIR, "v3_sessions.json")
        if os.path.exists(session_path):
            with open(session_path, "r", encoding="utf-8") as f:
                sessions = json.load(f)
            s = sessions.get(session_id, {})
            for msg in reversed(s.get("messages", [])):
                if msg.get("metadata", {}).get("taskGraph"):
                    return {"nodes": msg["metadata"]["taskGraph"], "edges": [],
                            "version": entry["version"]}
        return {"nodes": [], "edges": [], "version": entry["version"]}
    except Exception as e:
        logger.warning("Get task_graph failed: %s", e)
        return {"nodes": [], "edges": [], "version": 0}


@router.put("/{session_id}/task-graph")
async def update_task_graph(session_id: str, req: TaskGraphUpdateRequest):
    """Persist user-modified task graph with version conflict detection."""
    try:
        entry = _put_task_graph(session_id, req.nodes, req.edges, req.version)
        logger.info("Saved task_graph for session %s: %d nodes (v%d)",
                    session_id[:8], len(req.nodes), entry["version"])
        return {"status": "ok", "nodes": req.nodes, "edges": req.edges, "version": entry["version"]}
    except HTTPException:
        raise
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
