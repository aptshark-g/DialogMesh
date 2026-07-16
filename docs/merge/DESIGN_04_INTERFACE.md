# 接口与工具设计

> **本文档合并自以下源头文档**（原文件保留于 `docs/v3.0/` 不删除）：
> - `DESIGN_API_EVENT_LOG.md` — REST API + EventLog 持久化
> - `DESIGN_CLI_REFERENCE.md` — CLI 命令大全（27 个命令）
> - `DESIGN_CLI_INSPECT.md` — CLI inspect 命令族
> - `DESIGN_TUI.md` — Textual 终端仪表盘
> - `DESIGN_FRONTEND.md` — 前端架构（标记为 legacy）

---

## 1. REST API

> 源自 `DESIGN_API_EVENT_LOG.md` + 代码 `core/agent/v4/api.py`

### 1.1 端点总览

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/v4/event` | 发送事件到认知运行时 |
| GET | `/v4/status` | 运行时引擎统计 |
| GET | `/v4/inspect/{module}` | 系统检查（JSON） |
| POST | `/v4/checkpoint` | 手动触发 Slow Path |
| GET | `/v4/health` | 健康检查 |

### 1.2 事件请求

```json
POST /v4/event
{
  "event_id": "evt_001",
  "kind": "dialog.message",
  "payload": {"text": "你好"},
  "trace_id": "trace_abc"
}
```

响应应包含 LLM 回复（当前未实现——见已知缺口）：

```json
{
  "event_id": "evt_001",
  "status": "processed",
  "llm_response": "你好！我是 DialogMesh...",
  "context_tokens": 125,
  "llm_metrics": {
    "latency_ms": 3175,
    "input_tokens": 326,
    "output_tokens": 234,
    "provider": "deepseek"
  }
}
```

### 1.3 状态查询

```json
GET /v4/status
{
  "async_stats": {"trigger_count": 42, "success_count": 40, "failure_count": 2},
  "slow_stats": {"trigger_count": 1, "success_count": 1},
  "deep_stats": {"trigger_count": 0}
}
```

### 1.4 初始化

```python
def init_api(db_path="data/event_log.db", config_path=None):
    _event_log = EventLog(db_path)
    _event_log.open()
    _engine = CognitiveRuntimeEngine(config_path=config_path)
    _engine.start()
    # Replay unconsumed events from crash
```

---

## 2. EventLog

> 源自 `DESIGN_API_EVENT_LOG.md` + 代码 `core/agent/v4/api_event_log.py`

### 2.1 设计

EventLog 为 v4 提供持久化事件日志，保证 crash recovery。

- 存储：SQLite WAL 模式
- 写入：追加式，不修改已有记录
- 恢复：启动时 replay unconsumed events

### 2.2 Schema

```sql
CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,        -- JSON
    refs TEXT,                     -- JSON
    metadata TEXT,                 -- JSON
    timestamp REAL NOT NULL,
    consumed INTEGER DEFAULT 0,   -- 0=未消费, 1=已消费
    consumed_at REAL
);
```

### 2.3 Crash Recovery

```
启动 → 查询 consumed=0 的 events → 逐个 replay → 标记 consumed=1
```

---

## 3. CLI

> 源自 `DESIGN_CLI_REFERENCE.md` + `DESIGN_CLI_INSPECT.md` + 代码 `core/agent/v4/cli/main.py`

### 3.1 命令总览

```bash
dialogmesh start [--config runtime.yaml]    # 启动认知运行时
dialogmesh stop                              # 停止运行时
dialogmesh status                            # 显示运行时统计
dialogmesh event "文本"                      # 发送用户事件
dialogmesh events history                    # 事件审计历史
dialogmesh events replay                     # 重放未消费事件
```

### 3.2 Pipeline 编排

```bash
dialogmesh pipeline create my-pipeline       # 创建管线
dialogmesh pipeline add my-pipeline module type --path async  # 添加模块
dialogmesh pipeline connect my-pipeline from_mod to_mod       # 连接模块
dialogmesh pipeline param my-pipeline module key value        # 设置参数
dialogmesh pipeline show my-pipeline          # 查看管线
dialogmesh pipeline list                      # 列出所有管线
dialogmesh pipeline export my-pipeline path   # 导出为 YAML
dialogmesh pipeline default                   # 构建默认 v4 DAG
```

### 3.3 Inspect 命令族

类似 Linux `ps`/`top`/`ls` 的文本表格查看能力。所有 inspect 命令只读。

```bash
dialogmesh inspect observations [--detail] [--id ID] [--page 1] [--page-size 10] [--json]
dialogmesh inspect hypotheses [--detail] [--id ID] [--json]
dialogmesh inspect knowledge [--detail] [--id ID] [--json]
dialogmesh inspect skills [--detail] [--id name] [--json]
dialogmesh inspect world [--detail] [--id unit_id]
dialogmesh inspect context [--detail] [--json]
# v3.2 简单查看器
dialogmesh inspect behavior
dialogmesh inspect causal
dialogmesh inspect constraints
dialogmesh inspect discourse
dialogmesh inspect fusion
dialogmesh inspect summary
dialogmesh inspect store
dialogmesh inspect pcr
dialogmesh inspect topics
```

### 3.4 其他命令

```bash
dialogmesh snapshot list                     # 列出快照
dialogmesh snapshot restore <snapshot_id>    # 恢复快照
dialogmesh config show                       # 显示配置
dialogmesh config set <key> <value>          # 设置配置
dialogmesh health                            # 健康检查
dialogmesh maintenance gc                    # 垃圾回收
dialogmesh maintenance stats                 # 存储统计
dialogmesh search <keyword>                  # 跨模块搜索
dialogmesh export knowledge                  # 导出知识
dialogmesh export skills                     # 导出技能
dialogmesh session list                      # 列出会话
dialogmesh session show <session_id>         # 查看会话详情
```

### 3.5 缺失的 chat 命令

> 当前未实现，Phase 0 需要添加

```bash
dialogmesh chat "你好"    # 发送事件并打印 LLM 回复
```

---

## 4. TUI

> 源自 `DESIGN_TUI.md` + 代码 `core/agent/v4/tui/app.py`

### 4.1 定位

Textual-based 终端仪表盘，实时监控四条认知路径（Async/Slow/Deep/Fast）。

### 4.2 12 个 Tab

| Tab | 内容 |
|:---|:---|
| Dashboard | 运行时总览：路径状态、事件计数、延迟 |
| Observations | Observation Pool 内容浏览 |
| Hypotheses | 假设竞争状态 |
| Knowledge | 冻结的知识节点 |
| Skills | 技能池状态 |
| World | World Graph 可视化 |
| Context | 最近编译的 Context IR |
| Events | Event Log 审计 |
| Snapshot | 快照管理 |
| Config | 配置查看与修改 |
| Health | 健康检查 |
| Settings | 语言切换（EN/ZH） |

### 4.3 特性

- 交错面板刷新（避免首次加载 UI 冻结）
- 语言切换缓存 + 延迟引擎启动
- Windows Terminal 检测 + cmd 回退
- i18n：26 个 TUI 字符串支持中英文

### 4.4 启动

```bash
# Windows
tui.bat

# Linux/Mac
./tui.sh
```

---

## 5. Frontend (Legacy)

> 源自 `DESIGN_FRONTEND.md` — 标记为 legacy，后续按需重写

### 5.1 原设计

| 层级 | 技术 | 状态 |
|:---|:---|:---|
| UI 框架 | React Context + useReducer | 原生 |
| 状态管理 | React Context | 原生 |
| 通信 | WebSocket | 已实现 |
| 可视化 | D3.js / React Flow | 设计阶段 |

### 5.2 当前状态

前端设计文档存在，但实际代码未在 v4 中实现。当前通过 CLI + TUI + API 作为用户界面。

### 5.3 后续方向

如果需要 Web 前端，建议：
- 基于 v4 REST API 重新设计
- 优先实现 Context IR 可视化（展示 cross_ref 子图）
- World Model 图可视化（ReferenceUnit + 多类型边）

---

## 6. LLM Provider

> 源自代码 `core/agent/llm_providers/`

### 6.1 抽象层

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult: ...

@dataclass
class GenerateRequest:
    prompt: str = ""
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None  # OpenAI Chat messages 格式
    max_tokens: int = 512
    temperature: float = 0.3
    timeout_ms: int = 30000
    response_format: Optional[str] = None  # "json" | "text"
    json_schema: Optional[Dict] = None

@dataclass
class GenerateResult:
    text: str
    metrics: LLMCallMetrics
    structured: Optional[Dict] = None  # JSON 解析结果
```

### 6.2 已实现的 Provider

| Provider | 文件 | 说明 |
|:---|:---|:---|
| `OpenAIProvider` | `openai_provider.py` | OpenAI 兼容 API（含 DeepSeek） |
| `LocalProvider` | `local_provider.py` | Ollama 本地模型 |
| `MockProvider` | `mock_provider.py` | 测试用，返回固定文本 |
| `FailoverProvider` | `failover_provider.py` | 多 Provider 故障转移 |
| `HybridRouter` | `hybrid_router.py` | 按任务类型路由到不同 Provider |

### 6.3 配置方式

三种配置优先级：

1. 构造函数注入：`CognitiveRuntimeEngine(llm_provider=provider)`
2. 环境变量：`DIALOGMESH_LLM_PROVIDER=openai|local|mock`
3. 默认：MockProvider（安全回退，无网络）

```bash
# DeepSeek 示例
export DIALOGMESH_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-***
export OPENAI_MODEL=deepseek-chat
# 或通过 OpenAI-compatible base_url
```

### 6.4 已知问题

`CognitiveRuntimeEngine.start()` 不调用 `_init_llm_provider()`，`on_event()` 不调用 `_call_llm()`。这两个方法已实现但未接线。**这是 Phase 0 的首要修复项。**

---

## 7. 实现状态

| 组件 | 文件 | 状态 |
|------|------|------|
| FastAPI REST API | `api.py` (288行) | ✅ 5 个端点 |
| EventLog | `api_event_log.py` | ✅ SQLite WAL |
| CLI | `cli/main.py` (493行) | ✅ 27 个命令 |
| CLI inspect | `cli/inspect.py` + `inspect_v3.py` | ✅ 14 个 inspect 子命令 |
| CLI builder | `cli/builder.py` | ✅ Runtime DAG 编辑器 |
| CLI snapshot | `cli/snapshot.py` | ✅ 快照管理 |
| CLI config | `cli/config_cmd.py` | ✅ 配置管理 |
| CLI health | `cli/health.py` | ✅ 健康检查 |
| CLI events | `cli/event_cmd.py` | ✅ 事件审计 |
| CLI maintenance | `cli/maintenance_cmd.py` | ✅ GC + stats |
| CLI search | `cli/search_cmd.py` | ✅ 跨模块搜索 |
| CLI export | `cli/export_cmd.py` | ✅ 知识/技能导出 |
| CLI session | `cli/session_cmd.py` | ✅ 会话管理 |
| TUI | `tui/app.py` (508行) | ✅ 12 tab Textual 仪表盘 |
| LLM Provider 抽象 | `llm_providers/base.py` | ✅ 完整抽象层 |
| OpenAIProvider | `llm_providers/openai_provider.py` | ✅ 含 async |
| LocalProvider | `llm_providers/local_provider.py` | ✅ Ollama |
| MockProvider | `llm_providers/mock_provider.py` | ✅ 测试回退 |
| FailoverProvider | `llm_providers/failover_provider.py` | ✅ 故障转移 |
| HybridRouter | `llm_providers/hybrid_router.py` | ✅ 混合路由 |
| ProviderFactory | `llm_providers/provider_factory.py` | ✅ 工厂模式 |
| Frontend | — | ❌ legacy，未实现 |
| `chat` CLI 命令 | — | ❌ 未实现（Phase 0） |

---

> 本文档定义接口与工具层。具体实现见代码 `core/agent/v4/api.py`、`core/agent/v4/cli/`、`core/agent/v4/tui/`、`core/agent/llm_providers/`。
