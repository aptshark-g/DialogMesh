# DialogMesh CLI — 完整设计

> 版本: v2.0 | 日期: 2026-07-28 | 状态: 设计评审
> 原则: Unix 管道组合，每个命令一个职责，stdin/stdout JSON，stderr 日志
> 覆盖: 10 链 + 引擎 + 会话 + 应用层

---

## 一、架构定位

```
┌─────────────────────────────────────────────────────────┐
│  dm (CLI entry)                                        │
│                                                         │
│  ┌─ 引擎 ─────────────────────────────────────────────┐│
│  │ engine start/stop/status                           ││
│  ├─ 会话 ─────────────────────────────────────────────┤│
│  │ session new/list/use/history                        ││
│  ├─ 全链路 ───────────────────────────────────────────┤│
│  │ event send <text>    (PCR→Intent→Plan→Decider→Reply)││
│  ├─ 逐层调试 ─────────────────────────────────────────┤│
│  │ pcr → intent → discourse → context → blueprint     ││
│  │ → decider → reply → meta → association → behavior  ││
│  │ → engineering → profile-show → rules               ││
│  ├─ 知识/观察 ────────────────────────────────────────┤│
│  │ obs show/search  knowledge export  concepts         ││
│  ├─ 任务图 ───────────────────────────────────────────┤│
│  │ task show/save/confirm                              ││
│  ├─ 应用层 ───────────────────────────────────────────┤│
│  │ chat/test/ab/profile/monitor/export/config/clean    ││
│  └─ 数据管理 ─────────────────────────────────────────┘│
│  data paths/export/info                                │
└──────────────┬──────────────────────────────────────────┘
               │ 直接调用 (同进程, 不过 HTTP)
               ▼
┌─────────────────────────────────────────────────────────┐
│  CognitiveRuntimeEngine                                 │
│  ┌── Async Path: on_event() → PCR → Discourse → ...    │
│  ├── MultiLayerLLM (pcr/intent/planning/meta/answer/   │
│  │                   reflective)                        │
│  ├── BlueprintEngine → Decider → EventBus (12 chain)   │
│  ├── ContextCompiler → ContextIR                        │
│  ├── ObservationPool → ConceptGraph → SemanticIndex     │
│  ├── BehaviorChain, AssociationFunnel, MetaCognitive    │
│  └── Profile: OCEAN/MBTI/BFI, ABC Rules, Mind           │
└─────────────────────────────────────────────────────────┘
```

---

## 二、命令全集

### 通用约定
- 每个命令 stdin 接受 JSON (管道输入)，stdout 输出 JSON
- 退出码: 0=成功, 1=引擎未启动, 2=模块错误, 3=参数错误
- 命令通过引擎单例共享状态，避免每次初始化

### 引擎生命周期

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm engine start` | — | `{"status":"running"}` | 启动 CRG，加载 LLM provider，注入设计文档到 pool/graph |
| `dm engine start --llm=deepseek --key=SK-...` | — | 同上 | 指定 LLM provider |
| `dm engine start --docs=docs/v3.0/*.md` | — | 同上 | 指定设计文档路径 |
| `dm engine stop` | — | `{"status":"stopped"}` | 停止引擎 |
| `dm engine status` | — | `{"running":bool,"chains":{...},"stats":{...}}` | 全状态 |

### 会话管理

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm session new` | — | `{"session_id":"uuid"}` | 创建会话 |
| `dm session list` | — | `[{"id":"...","title":"...","turns":N}]` | 列出会话 |
| `dm session use <id>` | — | `{"session_id":"id"}` | 设置当前会话 |
| `dm session history` | — | `[{"role":"user","content":"..."},...]` | 当前会话消息历史 |

### 全链路对话 (核心)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm event send <text>` | 管道: `{"text":"...","sid":"..."}` | `{"reply":"...","task_graph":[...],"pcr":{...},"intent":{...},"discourse":{...}}` | 完整 PCR→Intent→Blueprint→Decider→Reply |

**event send 内部流程**:
```
用户文本 → DialogAdapter.adapt() → EventIR
  → engine.on_event(event)        # Async Path
    → PCR: zone/expectation/noise
    → DiscourseBlockTree: 对话块 + 话题
    → Intent: segments/entities/ambiguities
    → ContextCompiler: ContextIR (subgraph 裁剪)
    → BlueprintEngine: 意图→BlueprintDAG
    → Decider: DAG→EventBus 3 Tick (12 chain)
    → AnswerLLM: 最终回复
  → 返回 {reply, task_graph, pcr, intent, discourse, blueprint, chains}
```

---

## 三、逐层调试命令 (每个对应一个引擎模块)

### PCR (Pre-Cognitive Router)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm pcr <text>` | 管道: `{"text":"..."}` | `{"zone":"TOOL\|ADVISOR\|...","complexity":0.6,"expectation":"...","profile":{}}` | 认知路由分析 |

### Intent (意图分析)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm intent <text>` | 管道: `{"text":"...","pcr":{...}}` | `{"segments":["..."],"entities":[...],"ambiguities":[...],"confidence":0.8}` | 意图分解 + 实体提取 |

### Discourse (对话树)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm discourse list` | — | `[{"id":"...","text":"...","parent":"..."}]` | 对话块列表 |
| `dm discourse tree` | — | `{"root":"...","blocks":{...},"tree":{...}}` | 对话树结构 |
| `dm discourse feed <text>` | 管道: `{"text":"...","sid":"..."}` | `{"route":"...","blocks_added":N}` | 喂文本 → 生成对话块 |
| `dm discourse topic` | — | `{"topics":["..."]}` | 话题树快照 |

### Context (上下文编译)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm context compile` | 管道: `{"text":"...","sid":"..."}` | `{"entries":[...],"tokens_total":N}` | 编译 ContextIR |
| `dm context show` | — | `{"entries":[...]}` | 最近编译的上下文 |
| `dm context subgraph` | 管道: `{"entity":"..."}` | `{"nodes":[...],"edges":[...]}` | 子图裁剪结果 |

### Blueprint + Decider (编排)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm blueprint` | 管道: `{"intent":"...","segments":[...]}` | `{"dag":{"nodes":[...],"edges":[...]}, "strategy":"HYBRID"}` | 从意图构建 DAG |
| `dm blueprint strategy` | — | `["TEMPLATE","HYBRID","LLM_DRIVEN"]` | 可用策略 |
| `dm decider` | 管道: `{"dag":{...},"user_text":"..."}` | `{"chain_outputs":{...},"llm_reply":"...","ticks":[...]}` | 执行 DAG |
| `dm decider chains` | — | `{"pcr":"✅","intent":"✅",...}` | 12 链状态 |

### Reply (LLM 回复)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm reply` | 管道: `{"context":{...},"chain_outputs":{...}}` | `{"reply":"...","model":"deepseek-chat"}` | 生成最终回复 |
| `dm reply raw <prompt>` | 管道: `{"prompt":"..."}` | `{"reply":"..."}` | 裸 LLM 调用 |

### Meta (元认知)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm meta review` | 管道: `{"reply":"...","pipelie_outputs":{...}}` | `{"anomalies":[...],"corrections":[...],"score":0.7}` | 复盘审查 |
| `dm meta corrections` | — | `[{"target":"pcr","action":"..."}]` | 待修正列表 |
| `dm meta apply` | 管道: `{"corrections":[...]}` | `{"applied":N}` | 批量应用修正 |

### Association (关联链 L1→L5)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm association show` | — | `{"funnel":{"L1":N,"L2":N,...},"relations":[...]}` | 关联漏斗状态 |
| `dm association search <entity>` | — | `{"matches":[...],"path":"L1→L2→..."}` | 搜索关联 |
| `dm association promote <entity>` | — | `{"from":"L2","to":"L3"}` | 手动晋升 |

### Behavior (行为链)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm behavior predict` | 管道: `{"context":{...}}` | `{"prediction":"...","confidence":0.7,"tree_path":[...]}` | 行为预测 |
| `dm behavior stats` | — | `{"edges":N,"patterns":[...]}` | 行为统计 |

### Engineering (工程链)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm engineering constraint <spec>` | 管道: `{"type":"...","target":"..."}` | `{"satisfied":bool,"violations":[...]}` | 约束检查 |
| `dm engineering propagate` | 管道: `{"change":"...","affected":[...]}` | `{"impact":[...],"delta":[...]}` | 变更传播 |

### Profile (画像)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm profile show` | — | OCEAN 10 维 + MBTI + BFI | 当前画像 (保留原 CLI 输出格式) |
| `dm profile reset` | — | `{"status":"reset"}` | 重置画像 |
| `dm profile history` | — | `[{"turn":N,"dims":{...},"mbti":"..."}]` | 画像变化历史 |

### Rules (ABC 规则)

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm rules show` | — | `[{"id":"...","antecedent":"...","behavior":"...","consequence":"..."}]` | 所有规则 |
| `dm rules search <keyword>` | — | `[{"id":"...",...}]` | 搜索规则 |
| `dm rules add` | 管道: `{"antecedent":"...","behavior":"...","consequence":"..."}` | `{"id":"...","status":"added"}` | 手动添加规则 |

### 知识图谱 / 观察

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm obs show` | — | `{"total":N,"by_domain":{...}}` | 观察池统计 |
| `dm obs search <query>` | — | `[{"domain":"...","content":"..."}]` | 搜索观察 |
| `dm knowledge export` | — | `{"objects":N}` (JSON 到 stdout) | 导出知识对象 |
| `dm concepts` | — | `["concept1","concept2",...]` | 概念列表 |

### 任务图

| 命令 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `dm task show` | — | `{"nodes":[...],"edges":[...]}` | 当前会话任务图 |
| `dm task save` | 管道: JSON | `{"status":"ok"}` | 覆写任务图 |
| `dm task confirm` | — | `{"status":"confirmed"}` | 标记确认 (下次 event 注入) |

---

## 四、应用层命令 (保留现有)

| 命令 | 说明 | 保留 |
|------|------|:---:|
| `dm chat [--turns N]` | 交互对话 + 画像追踪 | ✅ |
| `dm test [bench]` | benchmark (live/controlled/implicit/monitored) | ✅ |
| `dm ab` | A/B OCEAN 对比 | ✅ |
| `dm monitor [--list]` | 查看会话日志 | ✅ |
| `dm export [--format json\|csv]` | 导出会话数据 | ✅ |
| `dm config` | 查看配置/持久化状态 | ✅ |
| `dm clean [--all]` | 重置数据 | ✅ |

---

## 五、数据管理

| 命令 | 说明 |
|------|------|
| `dm data paths` | 列出所有数据文件路径和大小 |
| `dm data export <module>` | 导出指定模块数据 (profile/rules/mind/annotations/monitor/obs/knowledge/graph) |

---

## 六、典型工作流

### 完整对话 + 调试
```bash
# 启动
dm engine start

# 全链路对话
dm event send "规划登录系统"
# → {reply, task_graph, pcr, intent, discourse, chains}

# 查看 PCR 怎么判的
dm pcr "规划登录系统" | jq .zone

# 查看对话树
dm discourse tree | jq .tree

# 查看蓝图 DAG
dm blueprint --pipe '{"intent":"code_generation"}' | jq .dag

# 修改任务图
dm task show | jq '.nodes += [{"id":"5","name":"测试"}]' | dm task save

# 确认
dm task confirm

# 继续对话 (LLM 收到确认的 task_graph)
dm event send "开始执行"
```

### 画像分析
```bash
dm chat --turns 10    # 对话建立画像
dm profile show        # 查看 OCEAN/MBTI
dm chat --turns 10    # 再对话 (画像累进)
dm ab                  # 对比变化
dm export --format csv # 导出
```

---

## 七、目录结构

```
core/agent/cli/
├── __init__.py
├── entry.py              # dm 入口 (argparse → subcommands)
├── engine.py             # 引擎单例 (全局共享)
├── state.py              # CLI state: ~/.dialogmesh/state.json
├── commands/
│   ├── __init__.py
│   ├── engine_cmd.py     # dm engine *
│   ├── session_cmd.py    # dm session *
│   ├── event_cmd.py      # dm event send
│   ├── pcr_cmd.py        # dm pcr
│   ├── intent_cmd.py     # dm intent
│   ├── discourse_cmd.py  # dm discourse *
│   ├── context_cmd.py    # dm context *
│   ├── blueprint_cmd.py  # dm blueprint *
│   ├── decider_cmd.py    # dm decider *
│   ├── reply_cmd.py      # dm reply *
│   ├── meta_cmd.py       # dm meta *
│   ├── association_cmd.py# dm association *
│   ├── behavior_cmd.py   # dm behavior *
│   ├── engineering_cmd.py# dm engineering *
│   ├── profile_cmd.py    # dm profile *
│   ├── rules_cmd.py      # dm rules *
│   ├── obs_cmd.py        # dm obs *, knowledge, concepts
│   ├── task_cmd.py       # dm task *
│   ├── app_cmd.py        # dm chat/test/ab/monitor/export/config/clean
│   └── data_cmd.py       # dm data *
├── _old/
│   ├── main.py           # 旧 V4CLI
│   └── cli.py            # 旧 v6 cli.py
└── tests/
    └── test_cli.py
```

---

## 八、实现路径

### Phase 1: 引擎 + 会话 (基础)
- `dm engine start/stop/status`
- `dm session new/list/use/history`
- 引擎单例 + state 持久化

### Phase 2: 全链路 (核心)
- `dm event send` — 打通 PCR→Intent→Blueprint→Decider→Reply
- 结果包含 task_graph, pcr, intent, discourse, chains

### Phase 3: 任务图 + 应用层
- `dm task show/save/confirm`
- `dm chat/test/ab/profile/monitor/export/config/clean` (移植)

### Phase 4: 逐层调试 (10 链)
- pcr → intent → discourse → context → blueprint → decider → reply
- meta → association → behavior → engineering
- profile-show/history, rules show/search/add

### Phase 5: 知识/观察/数据
- obs show/search, knowledge export, concepts
- data paths/export
