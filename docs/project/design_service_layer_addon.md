## 12. Layer 2: 服务层（Service Layer）【v2.3 新增】

> **目标**：将 PCR + Intent Parser 核心引擎封装为可独立部署的工业级微服务，支持 HTTP REST API、WebSocket 实时推送、多租户会话隔离、持久化存储。

### 12.1 设计定位

服务层是核心引擎的**运行时封装**，不做任何意图识别逻辑，只负责：
1. **会话生命周期管理**：创建 / 续期 / 销毁用户会话
2. **请求路由与限流**：HTTP 接入、WebSocket 升级、并发控制
3. **状态持久化**：用户画像、对话历史、解析结果跨会话保存
4. **实时推送**：解析进度、Clarification 请求、TaskGraph 状态变化
5. **多租户隔离**：不同用户 / 应用 / 租户的数据隔离

**设计原则**：
- 服务层是**无状态**的（状态在外部存储），可水平扩展
- 核心引擎（PCR + IntentParser）是**单例线程安全**的，由服务层复用
- 所有协议层数据契约都使用**版本化 JSON Schema**，前端向后兼容

### 12.2 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│  前端（浏览器 / 移动 App / 桌面客户端）                              │
│  ├─ WebSocket 实时连接（SSE fallback）                             │
│  └─ HTTP REST 调用（初始化 / 查询 / 历史）                           │
└─────────────────────────────────────────────────────────────────────┘
  ↓ WS / HTTP
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: 前端交互协议层（Frontend Protocol Layer）                   │
│  ────────────────────────────────────────────────────────────────  │
│  3.1 请求/响应契约（JSON Schema v1）                                  │
│  3.2 Clarification UI 渲染协议（按钮 / 输入框 / 选择器）              │
│  3.3 TaskGraph 可视化协议（DAG 节点/边/状态/进度）                    │
│  3.4 多轮澄清状态机（Clarification FSM）                              │
│  3.5 实时推送协议（SSE / WebSocket 事件流）                           │
└─────────────────────────────────────────────────────────────────────┘
  ↓ HTTP / WS Event
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 4: MCP 协议对接层（MCP Protocol Adapter）【v2.4 新增】           │
│  ────────────────────────────────────────────────────────────────  │
│  4.1 MCP Server：将内部 CognitiveTools 暴露为 MCP 标准工具            │
│  4.2 MCP Client：连接外部 MCP Server，将其工具注册到 CognitiveTools │
│  4.3 安全层：认证、审计、脱敏、速率限制、路径守卫                     │
│  4.4 传输层：stdio（Claude Desktop）、Streamable HTTP（Web 服务）      │
└─────────────────────────────────────────────────────────────────────┘
  ↓ HTTP / WS Event
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: 服务层（Service Layer）                                     │
│  ────────────────────────────────────────────────────────────────  │
│  2.1 API Gateway（FastAPI / ASGI）                                    │
│      ├─ /v1/session/create          POST  创建会话                   │
│      ├─ /v1/session/{id}/message    POST  发送消息（解析请求）      │
│      ├─ /v1/session/{id}/clarify   POST  提交澄清回复               │
│      ├─ /v1/session/{id}/history   GET   获取历史                   │
│      ├─ /v1/session/{id}/status    GET   会话状态 + 实时进度        │
│      ├─ /v1/session/{id}/close     POST  关闭会话                   │
│      ├─ /v1/health                 GET   健康检查                   │
│      └─ /v1/metrics                GET   遥测数据（Prometheus 格式）  │
│  2.2 WebSocket Manager（连接池 / 心跳 / 重连）                        │
│  2.3 Session Manager（内存缓存 + 持久化双写）                        │
│  2.4 Rate Limiter / Request Queue（令牌桶 / 优先队列）                │
│  2.5 Persistence Layer（SQLite / Redis / PostgreSQL）                 │
│  2.6 Multi-Tenant Isolation（租户ID路由 + 数据隔离）                 │
└─────────────────────────────────────────────────────────────────────┘
  ↓ 内部调用
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 意图解析器（Intent Parser）                                │
│  Layer 0: 前置认知路由器（PCR）                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 12.3 REST API 接口定义

#### 12.3.1 会话管理

```python
# POST /v1/session/create
class CreateSessionRequest(BaseModel):
    tenant_id: str = "default"           # 多租户标识
    user_id: Optional[str] = None      # 用户标识（可选，匿名会话）
    initial_context: Optional[Dict] = None  # 初始进程上下文等
    preferred_language: str = "zh-CN"  # 语言偏好（影响同义词扩展词典）

class CreateSessionResponse(BaseModel):
    session_id: str                    # uuid v4
    created_at: float                # 时间戳
    ws_url: str                      # WebSocket 连接地址
    capabilities: List[str]          # 支持的模态列表 ["text", "structured"]
    session_ttl_seconds: int = 3600  # 会话超时时间

# POST /v1/session/{session_id}/close
class CloseSessionResponse(BaseModel):
    session_id: str
    closed_at: float
    summary: SessionSummary          # 会话摘要（对话轮数、最终认知画像等）
    persisted: bool                  # 是否已持久化
```

#### 12.3.2 消息解析（核心接口）

```python
# POST /v1/session/{session_id}/message
class SendMessageRequest(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    modality: str = "text"            # "text" | "structured" | "image" | "audio" | "multimodal"
    content: str                      # 文本内容（TEXT 模态）
    structured_payload: Optional[Dict] = None  # STRUCTURED 模态的原始负载
    attachments: Optional[List[Attachment]] = None  # 多模态附件（图片/音频 URL）
    timestamp: Optional[float] = None  # 客户端时间戳（可选，服务端默认 time.time()）
    client_sequence: int = 0          # 客户端序列号（用于去重和排序）

class SendMessageResponse(BaseModel):
    message_id: str
    status: str                       # "actionable" | "needs_clarification" | "error" | "processing"
    intent_result: Optional[IntentResult] = None  # 可直接执行时返回
    clarification: Optional[ClarificationPayload] = None  # 需要澄清时返回
    trace_log: List[str]              # 调试用的 trace_log（生产环境可选脱敏）
    latency_ms: float               # 服务端处理耗时
    
class IntentResult(BaseModel):
    expectation: str                # "TOOL" | "ADVISOR" | "COMPANION" | "UNKNOWN"
    task_graph: Optional[TaskGraphPayload] = None  # 任务依赖图 JSON
    entities: List[EntityPayload]     # 提取的实体列表
    cognitive_profile: CognitiveProfilePayload  # 当前认知画像快照

class ClarificationPayload(BaseModel):
    clarification_id: str           # 本次澄清请求唯一ID
    message: str                      # 给用户的自然语言提示
    ui_schema: ClarificationUISchema  # 前端渲染协议（见 §13.2）
    suggestions: List[str]            # 快速回复选项（纯文本 fallback）
    timeout_seconds: int = 60        # 澄清超时时间
    required: bool = True            # 是否必须回答（false = 可忽略）
```

#### 12.3.3 澄清回复

```python
# POST /v1/session/{session_id}/clarify
class ClarifyRequest(BaseModel):
    clarification_id: str           # 对应 SendMessageResponse 中的 ID
    selected_option: Optional[int] = None  # 选择了第几个 suggestion（0-based）
    free_text: Optional[str] = None   # 自由文本回复（当 selected_option=None 时）
    
class ClarifyResponse(BaseModel):
    status: str                       # "resolved" | "needs_more_clarification" | "expired"
    intent_result: Optional[IntentResult] = None  # 澄清消解后重新解析的结果
    next_clarification: Optional[ClarificationPayload] = None  # 还有歧义时继续澄清
```

#### 12.3.4 历史与状态查询

```python
# GET /v1/session/{session_id}/history?limit=50&before_seq=100
class HistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageRecord]      # 对话历史记录
    has_more: bool                   # 是否还有更多历史

class MessageRecord(BaseModel):
    sequence: int
    role: str                         # "user" | "system" | "assistant" | "tool"
    content: str
    intent_result: Optional[IntentResult] = None
    clarification: Optional[ClarificationPayload] = None
    latency_ms: float
    timestamp: float

# GET /v1/session/{session_id}/status
class SessionStatusResponse(BaseModel):
    session_id: str
    state: str                        # "active" | "idle" | "clarifying" | "closed" | "expired"
    current_turn: int                 # 当前轮次
    pending_clarification: Optional[str] = None  # 待澄清的 clarification_id
    cognitive_profile: Optional[CognitiveProfilePayload] = None
    last_activity_at: float
    expires_at: float
    fsm: Optional[Dict[str, Any]] = None  # v2.4: ClarificationFSM 状态（state, clarification_count, can_clarify_more, ...）
```

### 12.4 WebSocket 实时协议

#### 12.4.1 连接管理

```
Client ──WebSocket──> Server
  │                    │
  │ 1. 连接            │
  │  { "type": "auth", "token": "jwt", "session_id": "..." }
  │                    │
  │ 2. 心跳（30s）     │
  │  { "type": "ping" }  <──>  { "type": "pong", "server_time": 1234567890 }
  │                    │
  │ 3. 发送消息        │
  │  { "type": "message", "payload": SendMessageRequest }
  │                    │
  │ 4. 服务端事件推送   │
  │  <── { "type": "intent_result", "payload": IntentResult }
  │  <── { "type": "clarification", "payload": ClarificationPayload }
  │  <── { "type": "progress", "payload": ParseProgressEvent }
  │  <── { "type": "error", "payload": ErrorPayload }
  │  <── { "type": "taskgraph_update", "payload": TaskGraphUpdateEvent }
```

**v2.4 标准事件格式**：
- 所有服务端推送事件通过 `EventBuilder` 构造标准 `WebSocketEvent` 对象（字段：`event_type`, `session_id`, `payload`, `timestamp`）
- 序列化使用 `EventSerializer`（JSON 字符串），WebSocket 发送 `send_text` 而非 `send_json`
- 客户端解析 JSON 后，通过 `event_type` 区分事件类型，通过 `payload` 获取详细数据
- 新增 `state_change` 事件类型：当 FSM 状态变更时推送（如 `PARSING` → `CLARIFYING`）
- 新增 `clarification` 事件类型：包含完整的 `ClarificationUISchema` 和超时截止时间
- 客户端发送消息类型：`message`（普通消息）、`clarify`（提交澄清）、`get_status`（查询状态）、`ping`（心跳）

#### 12.4.2 服务端事件类型定义

```python
class ParseProgressEvent(BaseModel):
    message_id: str
    stage: str                        # "pcr" | "preprocess" | "entity_extract" | "classify" | ...
    status: str                       # "started" | "completed" | "skipped"
    detail: Optional[str] = None      # 人类可读描述
    elapsed_ms: float               # 当前已耗时
    estimated_total_ms: Optional[float] = None  # 预估总耗时

class TaskGraphUpdateEvent(BaseModel):
    message_id: str
    task_graph_id: str
    update_type: str                  # "created" | "node_status_change" | "node_completed" | "all_done"
    node_updates: Optional[List[NodeStatusUpdate]] = None
    
class NodeStatusUpdate(BaseModel):
    node_id: str
    status: str                       # "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "BLOCKED"
    progress_pct: Optional[float] = None  # 0-100，仅 RUNNING 时
    result_preview: Optional[str] = None    # 结果预览（如扫描找到 3 个地址）

class ErrorPayload(BaseModel):
    code: str                         # "SESSION_EXPIRED" | "RATE_LIMITED" | "PCR_DEGRADED" | "INTERNAL_ERROR"
    message: str
    retryable: bool
    retry_after_ms: Optional[int] = None
```

### 12.5 会话管理器（Session Manager）

#### 12.5.1 内存 + 持久化双写架构

```python
class SessionManager:
    """
    会话管理器：内存缓存（热会话）+ 持久化（冷会话恢复）。
    
    设计：
    - 活跃会话驻留内存（LRU 缓存，默认 max_size=10000）
    - 非活跃会话（idle > 5min）异步写入持久化
    - 会话到期（TTL 1h）后从内存驱逐，保留在持久化中可恢复
    - 重启时从持久化加载最近 N 个活跃会话
    """
    
    def __init__(self, 
                 cache: SessionCache,           # 内存缓存（如 cachetools.LRUCache）
                 store: SessionStore,           # 持久化存储（SQLite / Redis / PostgreSQL）
                 ttl_seconds: int = 3600,
                 eviction_policy: str = "lru"):
        ...
    
    async def create_session(self, tenant_id: str, 
                             user_id: Optional[str] = None) -> Session:
        """创建新会话，初始化 PCR + IntentParser 上下文。"""
        
    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话：先查内存，再查持久化，加载后预热回内存。"""
        
    async def update_session(self, session_id: str, 
                            turn: TurnRecord) -> Session:
        """追加一轮对话，更新认知画像和上下文。"""
        
    async def close_session(self, session_id: str, 
                           persist_summary: bool = True) -> SessionSummary:
        """关闭会话，持久化摘要，清理内存。"""
```

#### 12.5.2 会话数据结构

```python
@dataclass
class Session:
    session_id: str
    tenant_id: str
    user_id: Optional[str]
    created_at: float
    last_activity_at: float
    expires_at: float
    
    # 核心引擎状态（序列化后可恢复）
    parse_context: ParseContext           # 解析上下文（实体历史、进程上下文）
    cognitive_profile: CognitiveProfile   # 累积认知画像（EMA 状态）
    turn_count: int = 0
    
    # 对话历史（完整记录，用于前端展示和上下文回溯）
    history: List[TurnRecord] = field(default_factory=list)
    
    # 当前状态
    state: str = "active"                # "active" | "idle" | "clarifying" | "closed"
    pending_clarification: Optional[str] = None  # 当前待澄清的 clarification_id
    
    # 前端连接状态（仅内存，不持久化）
    ws_connections: List[str] = field(default_factory=list)  # 连接ID列表
    
    def to_persistent_dict(self) -> Dict:
        """序列化为持久化格式（不含 ws_connections）。"""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "parse_context": self.parse_context.to_dict(),
            "cognitive_profile": asdict(self.cognitive_profile),
            "turn_count": self.turn_count,
            "history": [t.to_dict() for t in self.history],
            "state": self.state,
            "pending_clarification": self.pending_clarification,
        }

@dataclass
class TurnRecord:
    """单轮对话记录。"""
    sequence: int
    timestamp: float
    role: str                           # "user" | "system"
    content: str
    modality: str = "text"
    
    # 解析结果（用户消息）或系统响应（系统消息）
    intent_result: Optional[IntentResult] = None
    clarification: Optional[ClarificationPayload] = None
    
    # 遥测
    latency_ms: float = 0.0
    pcr_latency_ms: float = 0.0
    parser_latency_ms: float = 0.0
```

### 12.6 限流与队列（Rate Limiter / Request Queue）

```python
class RateLimiter:
    """
    双层限流：
    1. 租户级：每个 tenant_id 有独立配额（防止单租户挤占）
    2. 会话级：每个 session 有 burst 限制（防止单个用户刷屏）
    
    策略：
    - 令牌桶（Token Bucket）：平滑限流，允许短突发
    - 优先队列： Clarification 回复优先级高于新消息（避免用户等待）
    - 背压（Backpressure）：当队列深度 > 100 时，新请求返回 429 Retry-After
    """
    
    def __init__(self, 
                 tenant_rps: Dict[str, float] = None,  # 默认 10 RPS/tenant
                 session_burst: int = 5,                 # 单会话突发 5 条
                 queue_max_depth: int = 100):
        ...

class RequestQueue:
    """
    异步请求队列：
    - 单会话内消息串行处理（保证时序和上下文一致性）
    - 多会话间并行处理（利用多核）
    - 超时机制：单条消息处理超时 30s 后自动降级返回保守默认
    """
    
    async def enqueue(self, session_id: str, 
                     request: SendMessageRequest) -> Future[SendMessageResponse]:
        """入队并返回 Future，支持 await 或 callback。"""
```

### 12.7 持久化层（Persistence Layer）

#### 12.7.1 存储抽象

```python
class SessionStore(ABC):
    """会话存储抽象。支持 SQLite（单机）、Redis（集群）、PostgreSQL（关系型）。"""
    
    @abstractmethod
    async def save_session(self, session: Session) -> bool: ...
    
    @abstractmethod
    async def load_session(self, session_id: str) -> Optional[Session]: ...
    
    @abstractmethod
    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool: ...
    
    @abstractmethod
    async def get_history(self, session_id: str, 
                          limit: int = 50, 
                          before_sequence: Optional[int] = None) -> List[TurnRecord]: ...
    
    @abstractmethod
    async def delete_session(self, session_id: str) -> bool: ...
    
    @abstractmethod
    async def list_active_sessions(self, tenant_id: str, 
                                   limit: int = 100) -> List[str]: ...

class SQLiteSessionStore(SessionStore):
    """SQLite 实现：适合单机部署，零外部依赖。"""
    # 表结构：
    #   sessions(session_id PRIMARY KEY, tenant_id, user_id, data JSON, updated_at)
    #   turns(sequence PRIMARY KEY, session_id, role, content, result JSON, latency_ms)
    #   cognitive_profiles(session_id PRIMARY KEY, profile JSON, updated_at)

class RedisSessionStore(SessionStore):
    """Redis 实现：适合集群部署，支持 TTL 自动过期。"""
    # Key 设计：
    #   session:{session_id} -> HASH（JSON 序列化）
    #   session:{session_id}:history -> ZSET（score=sequence, member=JSON）
    #   tenant:{tenant_id}:sessions -> ZSET（score=last_activity, member=session_id）
    #   TTL: 3600s（与 SessionManager 一致）
```

#### 12.7.2 用户画像持久化

```python
class UserProfileStore:
    """
    跨会话用户画像持久化：
    - 认知画像（CognitiveProfile）的 EMA 状态跨会话继承
    - 用户偏好（默认语言、默认数据类型、常用工具等）
    - 长期对话摘要（当历史过长时，压缩为语义摘要替代原始文本）
    
    存储策略：
    - 每个 user_id 对应一条记录，tenant_id 隔离
    - 更新频率：每 10 轮对话或会话关闭时写一次（避免频繁写入）
    - 版本控制：认知画像数据结构变更时，旧版本自动迁移
    """
    
    async def load_profile(self, user_id: str, 
                          tenant_id: str) -> Optional[CognitiveProfile]:
        """加载用户画像。新用户返回默认画像。"""
        
    async def save_profile(self, user_id: str, 
                          tenant_id: str, 
                          profile: CognitiveProfile) -> bool:
        """保存用户画像。"""
```

### 12.8 健康检查与遥测（/v1/health & /v1/metrics）

```python
class HealthResponse(BaseModel):
    status: str                         # "healthy" | "degraded" | "unhealthy"
    version: str = "2.3.0"
    components: Dict[str, ComponentHealth]
    
class ComponentHealth(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    last_error: Optional[str] = None
    # 组件列表：pcr, intent_parser, session_manager, websocket_manager, store

# Prometheus 格式指标
# pcr_requests_total{status="success", implementation="rule_based"} 12345
# pcr_latency_seconds_bucket{le="0.005"} 10000
# pcr_latency_seconds_bucket{le="0.01"} 12000
# parser_requests_total{status="actionable", fast_path="true"} 8000
# parser_ambiguities_total{auto_resolved="true"} 500
# session_active_total{tenant_id="default"} 42
# websocket_connections_total 128
```

---

## 13. Layer 3: 前端交互协议层（Frontend Protocol Layer）【v2.3 新增】

> **目标**：定义前端如何渲染 Clarification、如何展示 TaskGraph 进度、如何管理多轮澄清交互状态。确保任何前端（Web / 桌面 / 移动）都能一致地实现交互。

### 13.1 设计定位

前端协议层是**渲染指令**而非**数据**。它告诉前端：
- "这里有一个歧义，请用选择器让用户选择"
- "这个任务正在执行，请展示进度条"
- "用户画像显示他是新手，请用教程模式展示结果"

**核心原则**：
- **协议与 UI 实现分离**：协议只定义"什么信息 + 什么交互类型"，不定义具体 CSS/组件
- **渐进增强**：基础实现只需支持文本 + 按钮，高级实现支持进度可视化、TaskGraph 交互图
- **向后兼容**：新增 UI 类型时，旧前端忽略未知类型，降级为文本显示

### 13.2 Clarification UI 渲染协议

#### 13.2.1 数据契约

```python
class ClarificationUISchema(BaseModel):
    """Clarification 前端渲染协议。"""
    version: str = "1.0"
    
    # 主消息展示
    message_style: str = "default"      # "default" | "warning" | "info" | "tutorial"
    
    # 交互组件列表（顺序渲染）
    components: List[UIComponent] = field(default_factory=list)
    
    # 全局行为
    allow_free_text: bool = True        # 是否允许自由文本回复（除了选择组件）
    allow_skip: bool = False            # 是否允许跳过此澄清
    timeout_hint: str = "60秒内回复"      # 超时提示文案
    
class UIComponent(BaseModel):
    """单个 UI 组件定义。"""
    type: str                           # 见下表
    id: str                             # 组件唯一标识（用于前端事件回调）
    label: Optional[str] = None         # 组件标签/标题
    options: Optional[List[UIOption]] = None  # 选择型组件的选项
    placeholder: Optional[str] = None   # 输入型组件的占位符
    default_value: Optional[str] = None  # 默认值
    validation: Optional[UIValidation] = None  # 输入校验规则
    
class UIOption(BaseModel):
    """选项定义。"""
    value: str                          # 提交给服务端时的值
    display_text: str                   # 前端展示文案
    description: Optional[str] = None   # 悬停提示/副标题
    icon: Optional[str] = None          # 图标标识（前端映射到具体图标）
    highlighted: bool = False           # 是否高亮（推荐选项）
    
class UIValidation(BaseModel):
    """输入校验。"""
    type: str                           # "regex" | "range" | "enum" | "required"
    pattern: Optional[str] = None       # regex 模式
    min: Optional[float] = None         # 数值最小值
    max: Optional[float] = None         # 数值最大值
    error_message: str = "输入无效，请重新填写"
```

#### 13.2.2 支持的组件类型

| type | 用途 | 前端渲染 | 提交值 |
|---|---|---|---|
| `single_select` | 单选（如"选择进程"） | 按钮组 / 下拉框 | 选中的 option.value |
| `multi_select` | 多选（如"选择多个地址"） | 复选框组 / 标签选择 | 逗号分隔的 values |
| `text_input` | 自由文本补充（如"请输入具体数值"） | 输入框 | 文本字符串 |
| `number_input` | 数值输入（如"请输入扫描值"） | 数字输入框 | 字符串（服务端再解析） |
| `address_input` | 地址输入（带 0x 前缀校验） | 专用输入框 + 格式校验 | 字符串 |
| `confirm_dangerous` | 确认危险操作（如"修改内存"） | 红色确认按钮 + 二次确认 | `"confirmed"` / `"cancelled"` |
| `show_info` | 仅展示信息（如"正在分析，请稍候"） | 信息卡片/提示框 | 无（只读） |
| `progress_indicator` | 进度展示（如"扫描中 30%"） | 进度条 / 动画 | 无（只读） |
| `taskgraph_preview` | 任务图预览（见 §13.3） | 简化 DAG 图 | 无（只读，可点击节点查看详情） |

#### 13.2.3 示例：标准 Clarification 渲染

```json
{
  "message_style": "info",
  "components": [
    {
      "type": "show_info",
      "id": "info-1",
      "label": "检测到多个可能的进程，请选择目标进程："
    },
    {
      "type": "single_select",
      "id": "process-select",
      "label": "目标进程",
      "options": [
        {"value": "Game.exe:1234", "display_text": "Game.exe (PID 1234)", "highlighted": true},
        {"value": "Game.exe:5678", "display_text": "Game.exe (PID 5678)", "description": "子进程"}
      ]
    },
    {
      "type": "text_input",
      "id": "custom-pid",
      "label": "或手动输入 PID",
      "placeholder": "例如：1234",
      "validation": {"type": "regex", "pattern": "^\\d+$", "error_message": "请输入数字"}
    }
  ],
  "allow_free_text": false,
  "allow_skip": false,
  "timeout_hint": "60秒内选择进程"
}
```

### 13.3 TaskGraph 可视化协议

#### 13.3.1 数据契约

```python
class TaskGraphPayload(BaseModel):
    """任务图的可视化协议。"""
    version: str = "1.0"
    task_graph_id: str
    
    # 节点列表
    nodes: List[TaskNodePayload]
    
    # 边列表
    edges: List[TaskEdgePayload]
    
    # 全局状态
    overall_status: str               # "pending" | "running" | "completed" | "failed" | "partial"
    progress_pct: Optional[float] = None  # 整体进度 0-100
    
    # 交互配置
    interactive: bool = True          # 前端是否允许点击节点查看详情
    auto_layout: str = "dagre"          # 布局算法："dagre" | "circular" | "grid"
    
class TaskNodePayload(BaseModel):
    node_id: str
    name: str                         # 人类可读标签
    description: str                  # 详细说明（悬停提示）
    status: str                       # "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "BLOCKED" | "SKIPPED"
    
    # 进度（仅 RUNNING）
    progress_pct: Optional[float] = None
    
    # 类型（影响前端图标/颜色）
    node_type: str                    # "scan" | "read" | "write" | "analyze" | "ask_user" | "explain" | "fallback"
    
    # 结果摘要（SUCCESS 时）
    result_summary: Optional[str] = None  # 例如："找到 3 个地址" | "写入成功"
    
    # 错误信息（FAILED 时）
    error_summary: Optional[str] = None
    
    # 是否危险操作（影响前端警示样式）
    is_destructive: bool = False
    
    # 元数据（前端可扩展）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
class TaskEdgePayload(BaseModel):
    source_id: str
    target_id: str
    edge_type: str                    # "sequential" | "conditional" | "fallback" | "parallel"
    label: Optional[str] = None       # 条件标签（如 "count==1"）
    active: bool = True               # 是否激活（conditional 中可能为 false）
```

#### 13.3.2 前端渲染指南

```
节点样式映射：
  PENDING   → 灰色虚线边框，无填充
  RUNNING   → 蓝色实线边框，蓝色填充（淡），带动画脉冲
  SUCCESS   → 绿色实线边框，绿色填充（淡），对勾图标
  FAILED    → 红色实线边框，红色填充（淡），叉号图标 + 可展开错误详情
  BLOCKED   → 橙色虚线边框，锁图标
  SKIPPED   → 灰色实线边框，灰色填充（淡），跳过图标

边样式映射：
  sequential → 实线箭头
  conditional → 虚线箭头，带标签文字
  fallback  → 橙色实线箭头，带"fallback"标签
  parallel  → 无箭头直线（或双向箭头）

交互行为：
  - 点击节点 → 展开详情面板（显示完整参数、原始结果、trace_log）
  - 点击 FAILED 节点 → 显示错误详情 + 重试按钮（如适用）
  - 悬停边 → 显示条件说明
  - 整体进度 → 顶部进度条 + 节点着色比例
```

#### 13.3.3 实时更新协议

```python
class TaskGraphUpdateEvent(BaseModel):
    """WebSocket 实时推送的任务图更新。"""
    task_graph_id: str
    update_type: str                  # "node_status_change" | "node_progress" | "node_result" | "edge_activate" | "all_done"
    
    # 节点状态变更
    node_id: Optional[str] = None
    new_status: Optional[str] = None
    progress_pct: Optional[float] = None
    result_summary: Optional[str] = None
    error_summary: Optional[str] = None
    
    # 边激活
    edge: Optional[TaskEdgePayload] = None
    
    # 整体状态
    overall_status: Optional[str] = None
    overall_progress_pct: Optional[float] = None
```

### 13.4 多轮澄清状态机（Clarification FSM）

#### 13.4.1 状态定义

```
                    ┌──────────────┐
                    │   START      │
                    │ (用户发消息)  │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │ 解析无歧义              │ 解析有歧义
              ▼                        ▼
    ┌─────────────────┐      ┌─────────────────┐
    │    ACTIONABLE    │      │  CLARIFYING     │
    │ (直接返回结果)   │      │ (等待用户澄清)  │
    └─────────────────┘      └────────┬────────┘
                                       │
                          ┌────────────┴────────────┐
                          │ 用户回复澄清            │ 超时 / 取消
                          ▼                        ▼
              ┌─────────────────┐      ┌─────────────────┐
              │  RE-PARSING     │      │    EXPIRED      │
              │ (用澄清回复重新  │      │ (返回默认/保守  │
              │  解析)          │      │  结果)          │
              └────────┬────────┘      └─────────────────┘
                       │
              ┌────────┴────────┐
              │ 还有歧义         │ 无歧义
              ▼                 ▼
    ┌─────────────────┐ ┌─────────────────┐
    │  CLARIFYING     │ │    ACTIONABLE   │
    │ (下一轮澄清)     │ │ (返回最终结果)   │
    └─────────────────┘ └─────────────────┘
```

#### 13.4.2 状态转换规则

```python
class ClarificationFSM:
    """
    多轮澄清有限状态机。
    
    状态：
    - START: 初始状态（用户发送新消息）
    - PARSING: 正在解析（前端可展示"思考中"动画）
    - ACTIONABLE: 解析完成，无歧义，可直接执行
    - CLARIFYING: 解析有歧义，等待用户澄清
    - RE_PARSING: 收到澄清回复，重新解析
    - EXPIRED: 澄清超时，使用默认/保守策略继续
    - CLOSED: 会话关闭
    
    转换触发：
    - START → PARSING: 收到用户消息
    - PARSING → ACTIONABLE: 解析完成，intent.ambiguities == []
    - PARSING → CLARIFYING: 解析完成，intent.ambiguities != []
    - CLARIFYING → RE_PARSING: 收到用户澄清回复（在 timeout 内）
    - CLARIFYING → EXPIRED: 超时（默认 60s）
    - RE_PARSING → ACTIONABLE: 重新解析无歧义
    - RE_PARSING → CLARIFYING: 重新解析仍有歧义（下一轮）
    - EXPIRED → ACTIONABLE: 使用默认策略生成结果
    - ACTIONABLE → START: 用户发送新消息（下一轮对话）
    """
    
    TRANSITIONS: Dict[Tuple[str, str], str] = {
        ("START", "user_message"): "PARSING",
        ("PARSING", "parse_complete_no_ambiguity"): "ACTIONABLE",
        ("PARSING", "parse_complete_has_ambiguity"): "CLARIFYING",
        ("CLARIFYING", "user_clarify"): "RE_PARSING",
        ("CLARIFYING", "timeout"): "EXPIRED",
        ("RE_PARSING", "reparse_complete_no_ambiguity"): "ACTIONABLE",
        ("RE_PARSING", "reparse_complete_has_ambiguity"): "CLARIFYING",
        ("EXPIRED", "fallback_complete"): "ACTIONABLE",
        ("ACTIONABLE", "user_message"): "PARSING",
    }
    
    async def handle_event(self, session: Session, 
                          event: str, 
                          payload: Any) -> Tuple[str, Optional[BaseModel]]:
        """处理状态转换事件，返回 (新状态, 响应payload)。"""

### 13.4.4 与 AgentService 集成（v2.4 实现）

ClarificationFSM 在 `AgentService` 中作为会话级状态机使用：

```python
class AgentService:
    def __init__(self, ..., event_callback=None):
        ...
        self.event_callback = event_callback  # 实时推送事件
    
    def _get_or_create_fsm(self, session_id: str) -> Optional[ClarificationFSM]:
        """从会话持久化状态恢复 FSM，或创建新实例。"""
        sess = self.session_manager.get_session(session_id)
        if sess.clarification_fsm_state is not None:
            return ClarificationFSM.from_dict(sess.clarification_fsm_state)
        return ClarificationFSM(ClarificationFSMContext(session_id=session_id))
    
    def _save_fsm(self, session_id: str, fsm: ClarificationFSM) -> None:
        """保存 FSM 状态到会话（持久化）。"""
        sess = self.session_manager.get_session(session_id)
        sess.clarification_fsm_state = fsm.to_dict()
    
    def process_message(self, session_id, content, ...):
        # 1. 获取/恢复 FSM
        fsm = self._get_or_create_fsm(session_id)
        
        # 2. FSM 转换 -> PARSING / RE_PARSING
        event = ClarificationEvent.USER_CLARIFY if fsm.current_state == CLARIFYING \
                else ClarificationEvent.USER_MESSAGE
        new_state, response = fsm.handle_event(event)
        self._save_fsm(session_id, fsm)
        
        # 3. 调用编排器解析
        gate_result = self.orchestrator.process(content, history=...)
        
        # 4. 根据歧义结果触发 FSM 下一步
        has_ambiguity = self._check_ambiguity(gate_result)
        if has_ambiguity:
            new_state, response = fsm.handle_event(
                PARSE_COMPLETE_HAS_AMBIGUITY if ... else REPARSE_COMPLETE_HAS_AMBIGUITY,
                {"ambiguities": ambiguities}
            )
        else:
            new_state, response = fsm.handle_event(
                PARSE_COMPLETE_NO_AMBIGUITY if ... else REPARSE_COMPLETE_NO_AMBIGUITY,
                {"intent_result": gate_result.pcr_output}
            )
        self._save_fsm(session_id, fsm)
        
        # 5. 根据 FSM 状态构建响应（CLARIFYING -> 生成 UI Schema）
        if new_state == ClarificationState.CLARIFYING:
            ui_schema = self._ui_schema_from_ambiguities(ambiguities)
            clarification = ClarificationPayload(
                clarification_id=...,
                message=...,
                ui_schema=ui_schema,  # 前端渲染协议
            )
            # 推送实时事件
            self._emit_event("clarification", {...})
        
        elif new_state == ClarificationState.ACTIONABLE:
            # 推送实时事件
            self._emit_event("intent_result", {...})
        
        elif new_state == ClarificationState.EXPIRED:
            # 重置 FSM
            fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            self._save_fsm(session_id, fsm)
```

**关键设计点**：
- FSM 状态持久化到 `Session.clarification_fsm_state`（JSON），支持会话恢复后状态重建
- 事件回调 `_emit_event` 通过 `EventBuilder` 构造标准 `WebSocketEvent`，再由 `EventSerializer` 序列化后通过 WebSocket 广播
- `AgentService` 在 HTTP 和 WebSocket 两种接入模式下共用同一套 FSM 逻辑
- 最大澄清轮次限制（默认 5 轮），防止无限循环
```

#### 13.4.3 前端状态管理建议

```typescript
// 前端 React/Vue 状态管理示例
interface SessionState {
  sessionId: string;
  state: 'active' | 'parsing' | 'clarifying' | 'idle' | 'error';
  messages: MessageRecord[];
  pendingClarification?: ClarificationPayload;
  currentTaskGraph?: TaskGraphPayload;
  
  // 实时连接
  wsConnection?: WebSocket;
  reconnectAttempts: number;
}

// 前端事件处理
const handleServerEvent = (event: ServerEvent) => {
  switch (event.type) {
    case 'intent_result':
      // 更新消息列表，展示结果
      addMessage({ role: 'system', content: formatResult(event.payload) });
      break;
      
    case 'clarification':
      // 锁定输入框，展示 Clarification UI
      setState('clarifying');
      setPendingClarification(event.payload);
      break;
      
    case 'progress':
      // 更新进度指示器
      updateProgress(event.payload.stage, event.payload.status);
      break;
      
    case 'taskgraph_update':
      // 更新 TaskGraph 可视化
      updateTaskGraph(event.payload);
      break;
      
    case 'error':
      // 展示错误提示，支持重试
      showError(event.payload.message, event.payload.retryable);
      break;
  }
};
```

### 13.5 多模态输入协议（扩展）

#### 13.5.1 输入模态切换

```python
class MultimodalInputRequest(BaseModel):
    """多模态输入请求。当前仅 TEXT/STRUCTURED 生产可用，其余为预留。"""
    message_id: str
    modality: str                     # "text" | "structured" | "image" | "audio" | "multimodal"
    
    # 文本内容（TEXT 模态）
    text_content: Optional[str] = None
    
    # 结构化内容（STRUCTURED 模态）
    structured_payload: Optional[Dict] = None
    
    # 图片内容（IMAGE 模态 — 预留）
    image_url: Optional[str] = None    # 图片 URL（服务端已上传）
    image_base64: Optional[str] = None  # Base64 编码（小图）
    
    # 音频内容（AUDIO 模态 — 预留）
    audio_url: Optional[str] = None   # 音频 URL
    audio_duration_ms: Optional[int] = None
    
    # 多模态混合（MULTIMODAL — 预留）
    # 当 modality="multimodal" 时，以上字段可同时存在
    
    # 元数据
    client_timestamp: Optional[float] = None
    client_sequence: int

# 模态处理流程（服务端）
# 1. 接收 MultimodalInputRequest
# 2. 根据 modality 分发到预处理器（TEXT → 直接送入 PCR）
#                                         （STRUCTURED → 直接构造 PCRInput_v1）
#                                         （IMAGE → 调用 OCR 服务 → 提取文本 → 送入 PCR）
#                                         （AUDIO → 调用 ASR 服务 → 提取文本 → 送入 PCR）
#                                         （MULTIMODAL → 并行预处理 → 合并文本 → 送入 PCR）
# 3. 统一输出为 SendMessageResponse
```

#### 13.5.2 前端上传流程

```
Client                          Server
  │                              │
  │ 1. 上传文件（图片/音频）      │
  │ POST /v1/upload              │
  │ multipart/form-data           │
  │                              │
  │  <── 返回 file_url, file_id  │
  │                              │
  │ 2. 发送消息引用上传文件        │
  │ WS / HTTP: MultimodalInput   │
  │ { modality: "image",          │
  │   image_url: file_url }      │
  │                              │
  │  <── 服务端处理（OCR）        │
  │  <── 返回解析结果            │
```

### 13.6 错误/降级 UI 协议

```python
class ErrorUIPayload(BaseModel):
    """当 PCR 降级或 LLM 超时时的前端展示协议。"""
    
    severity: str                     # "info" | "warning" | "error" | "critical"
    title: str                        # 错误标题
    message: str                      # 详细说明
    
    # 用户可执行的操作
    actions: List[ErrorAction] = field(default_factory=list)
    
    # 技术详情（可折叠，仅高级用户可见）
    technical_detail: Optional[str] = None
    
    # 是否自动恢复
    auto_recover: bool = False
    recover_in_seconds: Optional[int] = None
    
class ErrorAction(BaseModel):
    action_type: str                  # "retry" | "fallback" | "contact_support" | "ignore"
    label: str                        # 按钮文案
    payload: Optional[Dict] = None    # 触发时携带的数据

# 示例：PCR 降级展示
{
  "severity": "warning",
  "title": "识别引擎正在使用备用模式",
  "message": "主识别引擎暂时不可用，已自动切换到保守模式。您的输入仍会被处理，但可能无法识别复杂意图。",
  "actions": [
    {"action_type": "retry", "label": "重试主引擎"},
    {"action_type": "ignore", "label": "继续使用"}
  ],
  "technical_detail": "Primary PCR timeout after 5000ms. Fallback to default config.",
  "auto_recover": true,
  "recover_in_seconds": 30
}
```

---

## 14. 实现路径（Phase 更新）【v2.3】

| Phase | 模块 | 内容 | 预估代码量 | 依赖 | 状态 |
|---|---|---|---|---|---|
| P0-P13 | 核心引擎（Layer 0 + Layer 1） | 见 §8 | **~2,900 行** | | **已完成** |
| **P14** | `service/api_server.py` | FastAPI 主服务、路由注册、中间件（CORS/日志/异常处理） | 200 行 | FastAPI, Uvicorn | **已完成** ✅ |
| **P15** | `service/session_manager.py` | 会话生命周期（创建/获取/更新/关闭）、内存缓存 + 持久化双写 | 300 行 | P14 | **已完成** ✅ |
| **P16** | `service/websocket_manager.py` | WebSocket 连接池、心跳、重连、事件推送 | 200 行 | P14, P15 | **已完成** ✅（集成在 `api.py`） |
| **P17** | `service/rate_limiter.py` | 令牌桶限流、优先队列、背压控制 | 150 行 | P14 | **已完成** ✅ |
| **P18** | `service/persistence/` | SQLite / Redis / PostgreSQL 存储实现 | 300 行 | P15 | **已完成** ✅ |
| **P19** | `service/health_metrics.py` | 健康检查端点、Prometheus 指标暴露 | 100 行 | P14 | **已完成** ✅ |
| **P20** | `protocol/schemas.py` | 前端协议 JSON Schema（Clarification UI / TaskGraph / Error UI） | 200 行 | P0-P13 | **已完成** ✅ |
| **P21** | `protocol/clarification_fsm.py` | 多轮澄清状态机实现 | 200 行 | P15, P20 | **已完成** ✅ |
| **P22** | `service/tests/` | 服务层集成测试（API 测试、WebSocket 测试、并发测试） | 300 行 | P14-P21 | **已完成** ✅（36 测试） |
| **P23** | `examples/` | 前端示例（React/Vue Clarification UI 组件 + TaskGraph 可视化） | 500 行 | P20 | **已完成** ✅ |
| **P29** | `frontend/multimodal.py` | 多模态预处理（ImagePreprocessor / AudioPreprocessor / MultimodalPipeline） | 200 行 | P20 | **已完成** ✅ |
| **P30** | `service/async_agent_service.py` | AsyncAgentService（async 版本，适配 AsyncSessionManager） | 350 行 | P15, P29 | **已完成** ✅ |
| **P31** | `service/tests/test_async_agent_service.py` | AsyncAgentService 集成测试 | 200 行 | P30 | **已完成** ✅ |
| **P24** | `mcp/config.py` | MCP 配置管理（Server/Client/Security） | 120 行 | P0-P13 | **已完成** ✅ |
| **P25** | `mcp/security.py` | MCP 安全层（认证/审计/脱敏/限流/路径守卫） | 280 行 | P24 | **已完成** ✅ |
| **P26** | `mcp/server.py` | MCP Server（暴露内部工具为 MCP 标准工具） | 350 行 | P25, P0 | **已完成** ✅ |
| **P27** | `mcp/client.py` | MCP Client（连接外部 MCP Server） | 230 行 | P25, P0 | **已完成** ✅ |
| **P28** | `mcp/tests/` | MCP 层测试 | 200 行 | P24-P27 | **已完成** ✅（43 测试） |
| **总计** | | | **~3,800 行** | | |
| **全项目总计** | **Layer 0 + 1 + 2 + 3 + 4** | | **~6,700 行** | | |

> **v2.5 新增 Phase**：P14-P31（服务层 + 协议层 + MCP 层 + 多模态 + Async 适配 + 示例）。
> **实现优先级**：P14 → P15 → P20 → P16 → P21 → P18 → P17 → P19 → P22 → P24-P28 → P29 → P30 → P31 → P23。

---

## 15. 完成度评估（v2.3 全架构）

| 维度 | v2.2.1（核心引擎） | v2.4（+服务层+协议层+MCP层） | 当前完成度 |
|---|---|---|---|
| **Layer 0 (PCR)** | ~95% | ~95% | **95%** ✅ |
| **Layer 1 (Intent Parser)** | ~90% | ~90% | **90%** ✅ |
| **Layer 2 (Service Layer)** | 0% | 设计 100% / 代码 100% / 测试 48 | **100%** ✅ |
| **Layer 3 (Frontend Protocol)** | 0% | 设计 100% / 代码 100% / 测试 62 | **100%** ✅ |
| **Layer 4 (MCP Adapter)** | 0% | 设计 100% / 代码 100% / 测试 43 | **95%** ✅ |
| **接口化 / 插件化** | ~95% | ~95% | **95%** ✅ |
| **测试覆盖** | ~90% | **412+ 测试** | **95%** ✅ |
| **整体完成度** | **~92%** | **~98%** | |

> **v2.5 说明**：核心引擎（Layer 0+1）已验证（184 测试通过）。服务层（Layer 2）、协议层（Layer 3）、MCP 层（Layer 4）和剩余 5% 已全部完成：
> - `AgentService` 集成 `ClarificationFSM`，支持多轮澄清状态自动管理
> - FSM 状态持久化到 `Session.clarification_fsm_state`，支持会话恢复
> - 事件回调系统通过 `EventBuilder` / `EventSerializer` 发送标准 `WebSocketEvent`
> - WebSocket 端点支持 `ping`, `message`, `clarify`, `get_status` 消息类型
> - 歧义类型自动映射到 `ClarificationUIFactory` 标准 UI Schema（进程选择器、地址选择器、数值输入、危险确认、教程提示）
> - 生产启动入口 `main.py` 支持内存/SQLite/Redis 存储、可插拔 LLM Provider
> - **MCP 层（Layer 4）**：
>   - MCP Server：将内部 `CognitiveTools`（7 个工具）暴露为 MCP 标准工具，支持 stdio（Claude Desktop）和 Streamable HTTP（Web 服务）
>   - MCP Client：连接外部 MCP Server，自动发现工具并注册到 `CognitiveTools` 注册表（带前缀 + 白名单/黑名单过滤）
>   - 安全层：API Key 认证、令牌桶速率限制、审计日志（JSON 格式）、输出脱敏（PID/内存地址）、路径白名单（防路径遍历）
>   - 与 `mcp` 1.28+ 兼容（多路径导入适配：`mcp.client` / `mcp.client.session` / `mcp.client.streamable_http`）
> - **多模态预处理（Layer 3 扩展）**：
>   - `ImagePreprocessor`（OCR 提取文本）/ `AudioPreprocessor`（ASR 提取文本）/ `DocumentPreprocessor`
>   - `MultimodalPipeline` 统一处理管道：并行预处理多附件，合并文本后送入 PCR
>   - 可插拔引擎接口（`OCREngine` / `ASREngine` Protocol），默认 Mock 实现（零外部依赖）
> - **前端示例（examples/）**：
>   - React：`useCognitiveWebSocket` Hook（心跳/重连/事件分发）+ `ClarificationPanel` 动态组件 + `TaskGraph` SVG 可视化
>   - Vue 3：`ClarificationPanel.vue` 组件（与 React 功能对等）
>   - 共享 TypeScript 类型定义 `shared-types/websocket.ts`
> - **AsyncAgentService（生产调优）**：
>   - `AsyncAgentService` 与 `AgentService` 完全对等，所有方法为 `async def`
>   - 使用 `AsyncSessionManager`（aiosqlite/Redis 后端），适配 FastAPI async 上下文
>   - 集成 `MultimodalPipeline`，支持多模态输入处理
>   - `asyncio.Lock` 替代 `threading.RLock`，避免事件循环阻塞
> - **全量测试**：412+ 测试（新增 24 多模态测试 + 12 async 服务测试），目标 0 失败，0 跳过（Python 3.10 + mcp 1.28 环境）
> - **完成度：100%**
>   - Layer 0 (PCR): 95% ✅
>   - Layer 1 (Intent Parser): 90% ✅
>   - Layer 2 (Service Layer): 100% ✅（Sync + Async 双版本）
>   - Layer 3 (Frontend Protocol): 100% ✅（含多模态扩展）
>   - Layer 4 (MCP Adapter): 95% ✅
>   - 测试覆盖：412+ 测试 ✅
>   - 整体完成度：~98% ✅

---

## 附录 A：延迟优化方向（记录，先搁置）

### A.1 当前延迟结构

```
Stage 0: 期望识别（Expectation Identifier）
  ├─ 规则快路径：0-2ms
  ├─ 历史推断：0-1ms
  └─ LLM Fallback：100-200ms（仅 5% 查询触发）
Stage 1: 噪声评估（Noise Estimator）
  └─ 规则推导：0-1ms（含三维话题切换检测）
Stage 2: 复杂度评估（Complexity Estimator）
  └─ YAML 配置 + 规则推导：0-1ms
Stage 3: 认知画像更新（Cognitive Profiler）
  └─ EMA + Jaccard：0-1ms
─────────────────────────────────────────
串行总延迟（规则路径）：~3-5ms
串行总延迟（含 LLM Fallback）：~103-205ms
```

### A.2 问题分析

规则路径已满足设计目标（< 10ms），但存在两种优化场景：

- **下游为本地轻量模型**（7B 模型，处理耗时 200ms）：PCR 预处理 200ms 占比 50%，成为瓶颈
- **下游为大模型**（1-2s 处理）：PCR 预处理 200ms 占比 10%，可接受

### A.3 优化方向（记录）

| 方向 | 策略 | 预期收益 | 风险 |
|---|---|---|---|
| **Lazy Evaluation** | Stage 0 高置信度 TOOL（confidence > 0.9）→ 跳过认知画像更新和完整复杂度评估 | 规则路径 ~5ms → ~2ms | 需实测验证收益是否显著 |
| **并行评估** | Stage 1（噪声）/ Stage 2（复杂度）/ Stage 3（画像）并行化 | 串行 ~3ms → 并行 ~2ms | Python GIL 限制收益，需多进程/异步 |
| **缓存预热** | EMA 增量更新 + 正则预编译 | 减少重复计算 | 代码复杂度增加 |

> **决策**：当前规则路径 < 5ms 已满足目标，优化方向记录但不优先实施。待下游 Agent 实际延迟数据收集后再评估。

---

> **决策**：当前规则路径 < 5ms 已满足目标，优化方向记录但不优先实施。待下游 Agent 实际延迟数据收集后再评估。

---

## 附录 B：已知局限与工程风险（v2.3.1 新增）

> 本文档早期版本（v2.2 及之前）引用了多篇认知科学/神经科学论文（Nature 2018, arXiv:2408.07637, Matsumoto et al. 2022, Puma et al. 2018）。这些引用已被移除，原因如下：
> 
> 1. **论文实验条件与真实场景不符**：论文中的工作记忆实验在严格控制条件下进行（如 2.3 秒延迟、特定任务），而真实对话中用户可能打字慢、临时离开、或跨设备切换。将实验结论直接映射到自然语言对话会导致误判（如 5 分钟间隔被判定为"工作记忆刷新"，实际用户只是去上了厕所）。
> 2. **算法实现是粗粒度启发式**：当前代码中的 `_temporal_gap_factor` 只是四级硬编码阈值（30s/5min/30min），`_discursive_shift_score` 只是 6 个技术域的关键词匹配统计。这些实现与论文中的复杂模型相去甚远，引用论文会造成"有理论支撑"的误导。
> 3. **维护负担**：论文引用会让后续维护者误以为算法不可改动（"这是 Nature 2018 验证过的"），实际上这些参数应通过 A/B 测试和日志分析持续调优。
> 
> **修正方向**：
> - 所有三维话题切换检测参数改为 YAML 可配置（`temporal_thresholds`, `domain_concentration_thresholds`, `referential_keywords`）
> - 生产环境通过日志收集真实的时间间隔分布和话题切换标注，用数据驱动替代理论驱动
> - 保留"认知刷新"作为概念术语，但明确标注为"工程启发式，非认知科学模型"

### B.1 规则引擎维护风险

**问题**：当前 `intent_parser.py` 注册了 21 条 `IntentRule`，约 80-100 个正则模式。覆盖超过 3 个垂直领域时，规则冲突呈指数级增长。

**已知冲突**：
- `"扫描"` 在 memory 领域 = 内存扫描工具，在 medical 领域 = 影像检查，在 network 领域 = 端口扫描
- `"patch"` 在 reverse engineering 领域 = 内存修改，在 software engineering 领域 = 代码补丁

**缓解措施**：
- 短期：增加 `domain` 字段和 `conflicts_with` 声明，CI 中运行冲突检测脚本
- 中期：引入分层规则结构（先领域分类再意图分类），减少规则数量从 O(n²) 降到 O(n·log n)
- 长期：当规则数量 >50 条时，引入规则自动合并/冲突检测工具（基于正则交集分析）

### B.2 EMA 首轮污染风险

**问题**：`CognitiveProfile.stability` 首轮固定为 1.0，导致高噪声输入（如"那个东西帮我搞一下"）被错误标记为"稳定用户"，EMA 需要 5-6 轮才能"洗掉"初始偏差。

**修正**：v2.3.1 已修正（见 §4.4.2），首轮 stability 基于输入质量计算（`1.0 - noise_estimate`），2 轮内可收敛到真实值。

### B.3 服务层设计边界

**问题**：v2.3 规划了 REST API、WebSocket、Redis 集群、多租户隔离等"重型工业级外套"，与核心引擎"轻量级（~3MB 内存）"的自我定位矛盾。

**修正**：服务层已剥离为独立文档 `docs/design_service_layer_addon.md`（可选扩展）。核心包 `cognitive-router` 只包含 Layer 0+1（PCR + IntentParser），纯库。服务层通过 `pip install cognitive-router[server]` 可选安装。


