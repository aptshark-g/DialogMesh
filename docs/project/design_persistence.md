# 会话持久化设计方案 v1.0

> 本文档定义 intent_trace_cli 的会话持久化架构设计，利用项目已有的 `AsyncSessionManager` + `AsyncSQLiteSessionStore` 基础设施，实现 CLI 级别的跨进程对话恢复。

## 目录

- [1. 背景与问题](#1-背景与问题)
- [2. 设计目标](#2-设计目标)
- [3. 架构概览](#3-架构概览)
- [4. 关键组件](#4-关键组件)
- [5. 接口定义](#5-接口定义)
- [6. 与 CLI 集成方案](#6-与-cli-集成方案)
- [7. 数据模型](#7-数据模型)
- [8. 测试策略](#8-测试策略)
- [9. 实现计划](#9-实现计划)
- [10. 风险与回退](#10-风险与回退)

---

## 1. 背景与问题

### 当前状态（CLI v1）

```python
# 纯内存，进程退出即丢失
history = []  # Python list
session_id = "cli-123"
```

### 问题

| 问题 | 影响 | 触发场景 |
|---|---|---|
| 进程重启丢失对话 | 用户需重新描述上下文 | 程序崩溃、关闭终端、重启电脑 |
| 认知画像不累积 | 每轮都像"新用户" | 每次启动新进程 |
| 自适应阈值重置 | 阈值调优失效 | 每次启动新进程 |
| 无法跨会话分析 | 无法对比用户长期行为 | 任何分析场景 |

### 项目已有基础设施

| 组件 | 路径 | 状态 | 说明 |
|---|---|---|---|
| `SessionStore` 抽象基类 | `service/stores/base.py` | ✅ 稳定 | 7 个纯异步接口 |
| `AsyncSQLiteSessionStore` | `service/stores/async_sqlite.py` | ✅ 稳定 | 真正非阻塞，懒加载连接 |
| `AsyncSessionManager` | `service/async_session_manager.py` | ✅ 稳定 | 内存缓存 + 后台驱逐 |
| `Session` 数据模型 | `service/models.py` | ✅ 稳定 | 含 `cognitive_profile`, `adaptive_thresholds`, `fsm_state` |
| `TurnRecord` | `service/models.py` | ✅ 稳定 | 每轮记录，含 `intent_result`, `latency_ms` |

---

## 2. 设计目标

### 功能目标

| ID | 目标 | 优先级 | 验收标准 |
|---|---|---|---|
| P-1 | CLI 进程重启后恢复最近对话 | P0 | `get_or_load(session_id)` 返回完整历史 |
| P-2 | 认知画像跨进程累积 | P0 | 重启后 `metacognition` 不重置为默认值 |
| P-3 | 自适应阈值持久化 | P0 | 重启后 `noise_fast_path` 保持上次值 |
| P-4 | 多会话管理（用户可切换） | P1 | `sessions` 命令列出所有会话，`load <id>` 切换 |
| P-5 | 会话导入/导出（JSON） | P2 | `export <file>` 导出，`import <file>` 恢复 |
| P-6 | 自动清理过期会话（30 天） | P2 | 后台任务清理 `expires_at` 过期的会话 |

### 非功能目标

| ID | 目标 | 指标 |
|---|---|---|
| N-1 | 持久化延迟 | 单次 `save_turn` < 50ms（SQLite 本地） |
| N-2 | 恢复延迟 | 加载 50 轮历史 < 100ms |
| N-3 | 存储空间 | 单会话 100 轮 < 1MB（JSON 文本） |
| N-4 | 并发安全 | 多线程 CLI 场景不崩溃（`asyncio.Lock`） |
| N-5 | 降级可用 | 数据库损坏时回退到内存模式，不阻塞对话 |

---

## 3. 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│  CLI 交互层（intent_trace_cli.py）                            │
│  - 用户输入 → 调用 run_intent_trace_with_persistence()        │
│  - 每轮后 → session_persistence.add_turn(...)               │
│  - 退出时 → session_persistence.close_session()               │
├──────────────────────────────────────────────────────────────┤
│  CLISessionPersistence 中间件                               │
│  - 同步外壳：为 CLI 提供同步接口                              │
│  - 内部异步：asyncio.run_coroutine_threadsafe()               │
│  - 独立事件循环：避免与主线程事件循环冲突                      │
├──────────────────────────────────────────────────────────────┤
│  AsyncSessionManager（已有）                                  │
│  - 内存缓存：Dict[str, Session]                               │
│  - 后台驱逐：每 5 分钟清理过期会话                             │
│  - 上限清理：超过 10,000 会话按 LRU 淘汰                      │
├──────────────────────────────────────────────────────────────┤
│  AsyncSQLiteSessionStore（已有）                             │
│  - 表：sessions, turns                                       │
│  - 索引：idx_sessions_tenant, idx_sessions_updated           │
│  - 懒加载：首次使用时创建连接                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 关键组件

### 4.1 CLISessionPersistence（新组件）

**职责**：为同步 CLI 代码提供异步存储的同步包装。

```python
class CLISessionPersistence:
    """
    CLI 会话持久化中间件。
    在独立线程中运行 asyncio 事件循环，避免与主线程冲突。
    """
    
    def __init__(self, db_path: str = "~/.memorygraph/sessions.db",
                 ttl_seconds: int = 3600,
                 max_memory_sessions: int = 10000):
        # 路径健壮性：确保目录存在（避免 No such file or directory）
        db_path = os.path.expanduser(db_path)
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        
        # 启动独立事件循环线程
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # 在事件循环中初始化异步组件
        self._store = AsyncSQLiteSessionStore(db_path)
        self._manager = AsyncSessionManager(
            store=self._store,
            ttl_seconds=ttl_seconds,
            max_memory_sessions=max_memory_sessions,
        )
        
        # 批量保存：缓存待写画像和阈值，每 5 轮或 session 关闭时持久化
        # 避免每轮都触发 SQLite 写，降低高频写带来的性能开销
        self._pending_profile_updates: Dict[str, CognitiveProfile_v1] = {}
        self._pending_threshold_updates: Dict[str, AdaptiveThresholds] = {}
        self._batch_save_counter = 0
        
        self._initialized = True
    
    def _run_loop(self):
        """后台线程运行事件循环。"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def _run(self, coro):
        """在后台线程执行协程并返回结果。"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()
    
    # ── 同步接口 ─────────────────────────────────────
    
    def create_session(self, user_id: str = None) -> str:
        """创建新会话，返回 session_id。"""
        session = self._run(self._manager.create_session(user_id=user_id))
        self._run(self._store.save_session(session))  # 立即持久化
        return session.session_id
    
    def get_or_load(self, session_id: str) -> Optional[Session]:
        """从内存或磁盘加载会话。"""
        try:
            return self._run(self._manager.get_session(session_id))
        except KeyError:
            # 内存未命中，尝试从磁盘加载
            session = self._run(self._store.load_session(session_id))
            if session:
                # 预热回内存
                self._run(self._manager._sessions.__setitem__(session_id, session))
            return session
    
    def add_turn(self, session_id: str, 
                 role: str, content: str,
                 intent_result: Dict = None,
                 execution_status: str = None,
                 latency_ms: float = 0):
        """追加一轮对话并持久化。"""
        turn = TurnRecord(
            sequence=self._get_next_sequence(session_id),
            timestamp=time.time(),
            role=role,
            content=content,
            intent_result=intent_result,
            data={"execution_status": execution_status} if execution_status else {},
            latency_ms=latency_ms,
        )
        self._run(self._manager.save_turn(session_id, turn))
    
    def update_cognitive_profile(self, session_id: str, 
                                  profile: CognitiveProfile_v1):
        """更新认知画像（批量缓存，每 5 轮或 session 关闭时持久化）。"""
        self._pending_profile_updates[session_id] = profile
        self._batch_save_counter += 1
        if self._batch_save_counter >= 5:
            self._flush_pending_updates()
            self._batch_save_counter = 0
    
    def update_adaptive_thresholds(self, session_id: str,
                                      thresholds: AdaptiveThresholds):
        """更新自适应阈值（批量缓存，每 5 轮或 session 关闭时持久化）。"""
        self._pending_threshold_updates[session_id] = thresholds
        self._batch_save_counter += 1
        if self._batch_save_counter >= 5:
            self._flush_pending_updates()
            self._batch_save_counter = 0
    
    def list_sessions(self, limit: int = 20) -> List[SessionSummary]:
        """列出最近活跃的会话。"""
        session_ids = self._run(self._store.list_active_sessions(limit=limit))
        sessions = []
        for sid in session_ids:
            sess = self._run(self._store.load_session(sid))
            if sess:
                sessions.append(SessionSummary(
                    session_id=sid,
                    last_active=sess.last_activity_at,
                    turn_count=sess.turn_count,
                    state=sess.state,
                ))
        return sessions
    
    def _flush_pending_updates(self):
        """批量保存所有 pending 的画像和阈值更新（带乐观锁版本号递增）。"""
        for sid, profile in self._pending_profile_updates.items():
            session = self.get_or_load(sid)
            if session:
                session.cognitive_profile = profile.to_dict()
                session.version = (session.version or 1) + 1
                self._run(self._store.save_session(session))
        self._pending_profile_updates.clear()
        
        for sid, thresholds in self._pending_threshold_updates.items():
            session = self.get_or_load(sid)
            if session:
                session.adaptive_thresholds = thresholds.to_dict()
                session.version = (session.version or 1) + 1
                self._run(self._store.save_session(session))
        self._pending_threshold_updates.clear()
    
    def close_session(self, session_id: str):
        """关闭会话，触发持久化（flush pending 更新）。"""
        self._flush_pending_updates()
        self._run(self._manager.close_session(session_id))
    
    def shutdown(self):
        """优雅关闭：等待所有未完成的协程和 pending writes 完成。"""
        # 1. 先批量保存所有 pending 的画像和阈值（避免丢数据）
        if self._pending_profile_updates or self._pending_threshold_updates:
            self._flush_pending_updates()
        
        # 2. 关闭 SQLite 存储（内部会 flush 连接）
        self._run(self._store.close())
        
        # 3. 等待所有 pending asyncio tasks 完成（5 秒超时）
        pending = asyncio.all_tasks(self._loop)
        if pending:
            self._run(asyncio.gather(*pending, return_exceptions=True))
        
        # 4. 停止事件循环
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            print("[WARN] 持久化线程未在 5 秒内退出，强制终止")
    
    def _get_next_sequence(self, session_id: str) -> int:
        """获取下一个 turn sequence。"""
        session = self.get_or_load(session_id)
        if session:
            return session.turn_count + 1
        return 1
```

### 4.2 存储路径与配置

```python
# 默认配置
DEFAULT_CONFIG = {
    "db_path": "~/.memorygraph/sessions.db",      # SQLite 文件路径
    "log_dir": "~/.memorygraph/logs",             # 结构化日志目录
    "ttl_seconds": 7 * 24 * 3600,                  # 7 天过期
    "max_memory_sessions": 100,                    # CLI 场景保持 100 个内存会话
    "eviction_interval_seconds": 300,             # 5 分钟清理一次
}

# 环境变量覆盖
MEMORYGRAPH_DB_PATH = os.getenv("MEMORYGRAPH_DB_PATH", DEFAULT_CONFIG["db_path"])
MEMORYGRAPH_TTL_DAYS = int(os.getenv("MEMORYGRAPH_TTL_DAYS", 7))
```

---

## 5. 接口定义

### 5.1 CLISessionPersistence 公共接口

```python
class ICLISessionPersistence(ABC):
    """CLI 持久化中间件接口。"""
    
    @abstractmethod
    def create_session(self, user_id: str = None) -> str: ...
    
    @abstractmethod
    def get_or_load(self, session_id: str) -> Optional[Session]: ...
    
    @abstractmethod
    def add_turn(self, session_id: str, role: str, content: str,
                 intent_result: Dict = None, execution_status: str = None,
                 latency_ms: float = 0): ...
    
    @abstractmethod
    def update_cognitive_profile(self, session_id: str, profile): ...
    
    @abstractmethod
    def update_adaptive_thresholds(self, session_id: str, thresholds): ...
    
    @abstractmethod
    def list_sessions(self, limit: int = 20) -> List[SessionSummary]: ...
    
    @abstractmethod
    def close_session(self, session_id: str): ...
    
    @abstractmethod
    def shutdown(self): ...
```

### 5.2 与 `run_intent_trace` 的集成点

```python
def run_intent_trace_with_persistence(
    query: str,
    persistence: ICLISessionPersistence,
    session_id: str,
    provider: Optional[LLMProvider] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    带持久化的意图追踪。
    1. 从持久化加载会话历史
    2. 执行决策链
    3. 保存结果到持久化
    """
    
    # 1. 加载会话
    session = persistence.get_or_load(session_id)
    if not session:
        session_id = persistence.create_session()
        session = persistence.get_or_load(session_id)
    
    # 2. 构建历史（从 Session 对象转换为 HistoryEntry）
    history = [
        HistoryEntry(
            role=turn.role,
            content=turn.content,
            expectation=turn.intent_result.get("expectation") if turn.intent_result else None,
            timestamp=turn.timestamp,
        )
        for turn in session.history[-50:]  # 最近 50 轮
    ]
    
    # 3. 加载认知画像（如果有）
    if session.cognitive_profile:
        profile = CognitiveProfile_v1.from_dict(session.cognitive_profile)
    else:
        profile = CognitiveProfile_v1()  # 默认
    
    # 4. 加载自适应阈值（如果有）
    if session.adaptive_thresholds:
        adaptive = AdaptiveThresholds.from_dict(session.adaptive_thresholds)
    else:
        adaptive = AdaptiveThresholds()
    
    # 5. 执行决策链（复用现有 run_intent_trace）
    start_time = time.time()
    result = run_intent_trace(
        query=query,
        provider=provider,
        history=history,
        session_id=session_id,
        verbose=verbose,
    )
    total_latency = (time.time() - start_time) * 1000
    
    # 6. 保存用户 turn
    persistence.add_turn(
        session_id=session_id,
        role="user",
        content=query,
        intent_result=result.get("summary", {}).get("intent_result"),
        execution_status=result.get("summary", {}).get("execution_status"),
        latency_ms=total_latency,
    )
    
    # 7. 如果 LLM 返回了 direct_reply，保存 assistant turn
    if result.get("summary", {}).get("execution_status") == "direct_reply":
        persistence.add_turn(
            session_id=session_id,
            role="assistant",
            content=result.get("summary", {}).get("message", ""),
            execution_status="direct_reply",
        )
    
    # 8. 更新认知画像（批量缓存，不立即写库，每 5 轮 flush）
    if result.get("cognitive_profile"):
        persistence.update_cognitive_profile(
            session_id, result["cognitive_profile"]
        )
    
    # 9. 更新自适应阈值（批量缓存，不立即写库，每 5 轮 flush）
    if result.get("adaptive_thresholds"):
        persistence.update_adaptive_thresholds(
            session_id, result["adaptive_thresholds"]
        )
    
    return result
```

---

## 6. 与 CLI 集成方案

### 6.1 交互式 CLI 流程

```python
# intent_trace_cli.py 交互模式

def interactive_mode(persistence: CLISessionPersistence, provider: LLMProvider):
    # 1. 尝试加载最近的会话
    recent = persistence.list_sessions(limit=1)
    if recent:
        session_id = recent[0].session_id
        print(f"[INFO] 恢复最近会话: {session_id}")
    else:
        session_id = persistence.create_session()
        print(f"[INFO] 创建新会话: {session_id}")
    
    history = []  # 内存缓存，加速当前轮
    
    while True:
        query = input("📝 > ").strip()
        
        if query in ("quit", "exit", "q"):
            persistence.close_session(session_id)
            persistence.shutdown()
            print("再见！")
            break
        
        elif query == "sessions":
            # 列出所有会话
            sessions = persistence.list_sessions(limit=20)
            for s in sessions:
                print(f"  {s.session_id[:8]}... | {s.turn_count} 轮 | "
                      f"{time.strftime('%m-%d %H:%M', time.localtime(s.last_active))}")
            continue
        
        elif query.startswith("load "):
            # 切换会话
            new_id = query[5:].strip()
            if persistence.get_or_load(new_id):
                session_id = new_id
                history = []  # 清空内存缓存，强制从持久化重新加载
                print(f"[INFO] 已切换到会话: {session_id}")
            else:
                print(f"[ERROR] 会话未找到: {new_id}")
            continue
        
        elif query.startswith("new"):
            # 创建新会话
            session_id = persistence.create_session()
            history = []
            print(f"[INFO] 创建新会话: {session_id}")
            continue
        
        # 执行意图追踪（带持久化）
        result = run_intent_trace_with_persistence(
            query=query,
            persistence=persistence,
            session_id=session_id,
            provider=provider,
        )
        
        # 更新内存缓存（加速下一轮）
        history.append({"role": "user", "content": query})
        if result.get("summary", {}).get("execution_status") == "direct_reply":
            history.append({"role": "assistant", "content": result["summary"].get("message", "")})
```

### 6.2 单轮模式（非交互）

```cmd
# 创建新会话并执行
python intent_trace_cli.py --query "scan 100" --lmstudio

# 指定已有会话（恢复上下文）
python intent_trace_cli.py --query "读取这个地址" --session abc123 --lmstudio

# 列出所有会话
python intent_trace_cli.py --sessions
```

---

## 7. 数据模型

### 7.1 会话表（已有）

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT DEFAULT 'default',
    user_id TEXT,
    version INTEGER DEFAULT 1,  -- 乐观锁版本号，每次更新 +1（防止并发写冲突）
    data JSON,          -- Session.to_persistent_dict() 的 JSON
    updated_at REAL     -- Unix timestamp
);

CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);
```

### 7.2 轮次表（已有）

```sql
CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    data JSON,          -- TurnRecord.to_dict() 的 JSON
    timestamp REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_turns_session ON turns(session_id, sequence DESC);
```

### 7.3 新增：SessionSummary（用于列表展示）

```python
@dataclass
class SessionSummary:
    session_id: str
    last_active: float      # Unix timestamp
    turn_count: int
    state: str              # active | idle | clarifying | closed | expired
    health_score: float = 0.0  # 可选：从 observability 模块获取
```

---

## 8. 测试策略

### 8.1 单元测试

```python
class TestCLISessionPersistence(unittest.TestCase):
    
    def setUp(self):
        self.db_path = ":memory:"  # 内存数据库，测试隔离
        self.persistence = CLISessionPersistence(db_path=self.db_path)
    
    def tearDown(self):
        self.persistence.shutdown()
    
    def test_create_and_load(self):
        """创建会话 → 关闭 → 重新加载。"""
        sid = self.persistence.create_session()
        self.persistence.close_session(sid)
        
        session = self.persistence.get_or_load(sid)
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, sid)
    
    def test_add_turn_and_recover(self):
        """添加 3 轮对话 → 重启 → 恢复 3 轮。"""
        sid = self.persistence.create_session()
        
        for i in range(3):
            self.persistence.add_turn(sid, "user", f"query {i}")
        
        # 模拟重启：新建 persistence 实例，连接同一个 db
        self.persistence.shutdown()
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        
        session = new_persistence.get_or_load(sid)
        self.assertEqual(session.turn_count, 3)
        self.assertEqual(len(session.history), 3)
    
    def test_cognitive_profile_persistence(self):
        """认知画像更新 → 重启 → 恢复。"""
        sid = self.persistence.create_session()
        profile = CognitiveProfile_v1(expertise=0.8, stability=0.9)
        
        self.persistence.update_cognitive_profile(sid, profile)
        self.persistence.shutdown()
        
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        session = new_persistence.get_or_load(sid)
        
        self.assertAlmostEqual(session.cognitive_profile["expertise"], 0.8)
        self.assertAlmostEqual(session.cognitive_profile["stability"], 0.9)
    
    def test_adaptive_thresholds_persistence(self):
        """自适应阈值更新 → 重启 → 恢复。"""
        sid = self.persistence.create_session()
        adaptive = AdaptiveThresholds()
        adaptive.feedback(required_clarification=True)
        
        self.persistence.update_adaptive_thresholds(sid, adaptive)
        self.persistence.shutdown()
        
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        session = new_persistence.get_or_load(sid)
        
        self.assertLess(session.adaptive_thresholds["noise_fast_path"], 0.30)
    
    def test_list_sessions(self):
        """创建 5 个会话 → 列出最近 3 个。"""
        for _ in range(5):
            self.persistence.create_session()
        
        sessions = self.persistence.list_sessions(limit=3)
        self.assertEqual(len(sessions), 3)
```

### 8.2 集成测试（CLI 流程）

```python
class TestCLIFlowWithPersistence(unittest.TestCase):
    """端到端：CLI 交互流程 + 持久化。"""
    
    def test_full_conversation_recovery(self):
        """
        1. 用户输入 3 轮
        2. 程序退出
        3. 重新启动
        4. 输入第 4 轮（引用前 3 轮）
        5. 验证引用解析正确
        """
        # Phase 1: 第一轮会话
        persistence = CLISessionPersistence(":memory:")
        sid = persistence.create_session()
        
        for query in ["scan 0x401000", "读取这个地址", "修改成 90"]:
            run_intent_trace_with_persistence(query, persistence, sid)
        
        persistence.shutdown()
        
        # Phase 2: 模拟重启（新进程）
        new_persistence = CLISessionPersistence(":memory:")
        session = new_persistence.get_or_load(sid)
        
        # 验证历史恢复
        self.assertEqual(session.turn_count, 3)
        self.assertEqual(session.history[0].content, "scan 0x401000")
        self.assertEqual(session.history[2].content, "修改成 90")
        
        # Phase 3: 引用解析（需要历史）
        result = run_intent_trace_with_persistence(
            "那个地址的附近", new_persistence, sid
        )
        # 验证引用解析成功（需要历史中有 0x401000）
        self.assertIn("0x401000", str(result.get("entities", [])))
```

---

## 9. 实现计划

### Phase 1: 基础设施（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1.1 | `service/session_persistence.py` | 创建 `CLISessionPersistence` 类 |
| 1.2 | `tests/test_session_persistence.py` | 单元测试（创建/加载/turn/画像/阈值） |
| 1.3 | 修改 `intent_trace_cli.py` | 集成 `CLISessionPersistence`，添加 `--session` 参数 |
| 1.4 | 修改 `intent_trace_cli.py` | 添加 `sessions`, `load`, `new` 指令 |
| 1.5 | 运行测试 | 确保 388 + 新增测试全部通过 |

### Phase 2: 进阶功能（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2.1 | `intent_trace_cli.py` | 添加 `export <file>` 指令（JSON 导出） |
| 2.2 | `intent_trace_cli.py` | 添加 `import <file>` 指令（JSON 导入） |
| 2.3 | `service/session_persistence.py` | 添加 `Session` 健康度字段（依赖 observability） |
| 2.4 | `tests/test_session_persistence_advanced.py` | 导出/导入/健康度测试 |

---

## 10. 风险与回退

### 风险 1: 数据库损坏

**回退**：启动时检测 SQLite 文件完整性，损坏时自动创建新文件（`sessions.db.bak`），打印警告。

```python
def _safe_load_db(path: str) -> bool:
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA integrity_check")
        conn.close()
        return True
    except sqlite3.DatabaseError:
        return False
```

### 风险 2: 磁盘空间不足

**回退**：每 10 轮后检查磁盘空间，不足 100MB 时打印警告，停止持久化但继续内存运行。

### 风险 3: 并发写入冲突

**回退**：SQLite 的 `WAL` 模式（Write-Ahead Logging）默认支持并发读写。`AsyncSQLiteSessionStore` 已使用 `aiosqlite` 的异步队列，无需额外锁。

---

## 附录：文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `service/stores/base.py` | ✅ 已有 | `SessionStore` 抽象基类 |
| `service/stores/async_sqlite.py` | ✅ 已有 | `AsyncSQLiteSessionStore` |
| `service/async_session_manager.py` | ✅ 已有 | `AsyncSessionManager` |
| `service/models.py` | ✅ 已有 | `Session`, `TurnRecord` 数据模型 |
| `service/session_persistence.py` | 🆕 新建 | `CLISessionPersistence` |
| `tests/test_session_persistence.py` | 🆕 新建 | 单元测试 |
| `tests/test_session_persistence_advanced.py` | 🆕 新建 | 进阶测试 |
| `intent_trace_cli.py` | 📝 修改 | 集成持久化中间件 |

---

## 设计文档体系

| 文档 | 说明 | 依赖 |
|---|---|---|
| `design_persistence.md` | 会话持久化（SQLite） | 无 |
| `design_context_window.md` | 上下文窗口管理（热/温/冷） | 读取持久化历史 |
| `design_observability.md` | 可观测性（日志/指标/告警） | 观察所有模块 |
| `design_topic_tree.md` | 话题树（对话图/回溯/分叉） | 依赖持久化 + 窗口管理 |
