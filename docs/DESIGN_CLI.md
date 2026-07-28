# DialogMesh CLI — 设计文档

> 版本: v1.0 | 日期: 2026-07-28 | 状态: 设计评审
> 原则: Unix 风格，每个命令一个职责，stdin/stdout JSON 管道组合即业务流

---

## 一、架构定位

```
┌─────────────────────────────────────────────┐
│  dm (CLI entry)                             │
│  ┌── dm engine start/stop/status           │
│  ├── dm session new/list/use                │
│  ├── dm event send <text>    ← 全链路       │
│  ├── dm pcr <text>                          │
│  ├── dm intent <text>                       │
│  ├── dm blueprint [--intent]                │
│  ├── dm decider [--dag]                     │
│  ├── dm reply [--ctx]                       │
│  └── dm task show/save/confirm              │
└──────────────┬──────────────────────────────┘
               │ 直接调用 (同进程, 不经过 HTTP)
               ▼
┌─────────────────────────────────────────────┐
│  CognitiveRuntimeEngine                     │
│  ┌── on_event() → Async Path               │
│  ├── PCR Router                             │
│  ├── MultiLayerLLM (6 instances)            │
│  ├── BlueprintEngine → DAG                  │
│  ├── Decider → EventBus (12 chain)          │
│  └── ObservationPool / ConceptGraph / ...   │
└─────────────────────────────────────────────┘
```

CLI 与引擎**同进程直连**，不经过 HTTP API。HTTP API (`v3_session_api.py`) 作为可选前端接入层保留，但 CLI 是主要交互面。

---

## 二、命令粒度

每个命令:
- **stdin** 接受 JSON (管道输入)
- **stdout** 输出 JSON (管道输出)
- **stderr** 输出日志/进度
- 退出码: 0=成功, 1=引擎未启动, 2=模块错误, 3=参数错误

```
# 完整对话 (event 内部走全链路)
dm session new | dm event send "规划登录系统"

# 逐层调试
echo '{"text":"写代码"}' | dm pcr | dm intent | dm blueprint | dm decider | dm reply

# 任务图
dm task show <sid> | jq '.nodes[0].name="注册"' | dm task save <sid>
```

---

## 三、模块分阶段实现

### Phase 1: `dm engine` — 引擎生命周期

| 命令 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `dm engine start` | — | `{"status":"running"}` | 启动 CognitiveRuntimeEngine, 加载 LLM provider, 加载设计文档到 pool/graph |
| `dm engine stop` | — | `{"status":"stopped"}` | 停止引擎, 清理 |
| `dm engine status` | — | `{"running":bool, "event_count":N, "chains":{...}, "pool":{...}}` | 状态摘要 |

**实现**: `core/agent/cli/commands/engine_cmd.py`
**依赖**: `CognitiveRuntimeEngine.start()` / `.stop()` / 状态查询
**验证**: 启动后 `dm engine status` 输出非空 JSON

### Phase 2: `dm session` — 会话管理

| 命令 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `dm session new` | — | `{"session_id":"uuid"}` | 创建会话 |
| `dm session list` | — | `[{"id":"...","title":"...","turns":N}]` | 列出会话 |
| `dm session use <id>` | — | `{"session_id":"id"}` | 设置当前会话 (写入 state 文件) |

**实现**: `core/agent/cli/commands/session_cmd.py`
**依赖**: 引擎的 session 管理 (复用现有 session 机制)
**验证**: `dm session new | jq .session_id` 返回非空

### Phase 3: `dm event send` — 全链路对话 (核心)

| 命令 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `dm event send <text>` | 管道: `{"text":"...","session_id":"..."}` | `{"reply":"...","task_graph":[...], "pcr":{...}, "intent":{...}}` | 发送消息 → 引擎全链路 → 回复 + 元数据 |

**内部流程**:
```
用户文本 → DialogAdapter.adapt() → EventIR
  → engine.on_event(event)
    → PCR: expectation/zone
    → DiscourseBlockTree: 对话块
    → Decider: BlueprintDAG → EventBus 3 Tick
    → LLM: 回复生成
  → 返回 {reply, task_graph, pcr, intent, discourse, chains}
```

**实现**: `core/agent/cli/commands/event_cmd.py`
**依赖**: Phase 1 (engine started), Phase 2 (session), `engine.on_event()`
**验证**: `dm event send "hello"` 返回非空 reply，含 task_graph

### Phase 4: `dm task` — 任务图 CRUD

| 命令 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `dm task show <sid>` | — | `{"nodes":[...],"edges":[...]}` | 查看会话任务图 |
| `dm task save <sid>` | stdin: `{"nodes":[...],"edges":[...]}` | `{"status":"ok"}` | 覆写任务图 |
| `dm task confirm <sid>` | — | `{"status":"confirmed"}` | 标记确认 |

**实现**: `core/agent/cli/commands/task_cmd.py`
**依赖**: Phase 3 (event 已生成 task_graph), 持久化层
**验证**: 管道 round-trip: `dm task show | dm task save`

### Phase 5: 细颗粒调试命令

| 命令 | 输入 | 输出 | 对应模块 |
|------|------|------|---------|
| `dm pcr <text>` | — | zone/expectation | PCR Router |
| `dm intent <text>` | stdin: PCR 输出 | segments/entities | Intent Parser |
| `dm blueprint` | stdin: intent 输出 | DAG JSON | BlueprintEngine |
| `dm decider` | stdin: DAG JSON | chain_outputs | Decider + EventBus |
| `dm reply` | stdin: decider 输出 + 上下文 | reply text | Answer LLM |

每层可独立运行，也可管道串联。用于调试和验证单个模块。

---

## 四、持久化

CLI 状态文件: `~/.dialogmesh/state.json`
```
{
  "current_session": "abc123",
  "sessions": {
    "abc123": {
      "created": "2026-07-28T12:00:00",
      "turns": 5,
      "last_task_graph": {"nodes":[...], "edges":[...], "confirmed": true}
    }
  }
}
```

任务图文件: `data/task_graphs/{session_id}.json` (已有，复用)

引擎持久化: `data/event_log.db` (已有，复用)

---

## 五、目录结构

```
core/agent/cli/
├── __init__.py
├── entry.py              # dm 入口 (argparse, dispatch)
├── state.py              # CLI state: ~/.dialogmesh/state.json 读写
├── commands/
│   ├── __init__.py
│   ├── engine_cmd.py     # Phase 1: dm engine
│   ├── session_cmd.py    # Phase 2: dm session
│   ├── event_cmd.py      # Phase 3: dm event
│   ├── task_cmd.py       # Phase 4: dm task
│   ├── pcr_cmd.py        # Phase 5: dm pcr
│   ├── intent_cmd.py     # Phase 5: dm intent
│   ├── blueprint_cmd.py  # Phase 5: dm blueprint
│   ├── decider_cmd.py    # Phase 5: dm decider
│   └── reply_cmd.py      # Phase 5: dm reply
├── old_main.py           # 旧 V4CLI (保留引用)
└── old_cli.py            # 旧 v6 cli.py (保留引用)
```

旧 CLI 文件重命名保留，不删除——设计文档和测试可能引用。
