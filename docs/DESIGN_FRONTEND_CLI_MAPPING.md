# DialogMesh v6 — 前端 ↔ CLI 对应设计

> v1.0 | 2026-07-29
> 原则: 前端每个展示的数据 → CLI 有对应的 read 命令; 前端每次操作 → CLI 有对应的 write 命令。

---

## 架构概览

```
浏览器 (http://localhost:5173)
  ↕ fetch + WebSocket
Backend (http://localhost:8000)
  ↕ engine singleton
CLI (dm ...)
```

### 数据流方向
- **read 方向**: Backend v6 endpoints → 前端 page → 展示
- **write 方向**: 前端操作 → Backend POST/PUT → 引擎 → 磁盘持久化
- **CLI 调试**: dm <module> show → 同 Backend 数据源

---

## 页面详情 (14 pages)

### 1. DashboardPage — `/` (主页)

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 总会话数 | `useV6Sessions().sessions.length` | `dm session list` |
| API 状态 | `getHealth()` → `/v3/health` | `dm engine status` |
| 数据趋势图 | `useAnalyticsStore().trendData` | `dm metrics show` |
| 意图分布 | `useAnalyticsStore().intentDistribution` | `dm intent parse <text>` |
| 词云 | `useAnalyticsStore().wordCloud` | `dm discourse search <word>` |
| 会话列表 (名称/大小) | `sessions.map({name, size})` | `dm session list` |

**CLI 操作**:
- 刷新: `dm engine status` + `dm session list`
- 新建会话: `dm session new` + 导航到 `/chat?sid=xxx`

---

### 2. ChatPage — `/chat` (核心)

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 消息历史 | `chatStore.messages` | `dm session history <sid>` |
| 发送消息 | `sendMessage(sid, text)` | `dm event send "<text>" --sid=<sid>` |
| 任务图 (回复中) | `msg.taskGraph` | `dm task show --sid=<sid>` |
| 当前模型 | `chatStore.activeProvider` | `dm reply model` |
| 清空聊天 | `chatStore.clear()` | `dm session clear <sid>` |

**CLI 操作**:
- 发起对话: `dm session new` → `dm event send "你好"`
- 查看回复: `dm reply show`
- 查看任务图: `dm task show`
- 查看推理链: `dm decider chains`
- 调用工具: LLM 自主调用 ToolRegistry (7 tools)
- 切换模型: `dm reply model set <name>`

---

### 3. TaskPlanningPage — `/tasks`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 任务图 (节点+边) | `getTaskGraph(sid)` → nodes/edges | `dm task show --sid=<sid>` |
| 任务节点状态 | node.status | `dm tk node-status <id> <val>` |
| 手动编辑节点 | canvas drag/drop | `dm task node edit <id> <key=val>` |
| 添加任务 | + button | `dm task node add <name> [--deps=id1,id2]` |
| 删除任务 | delete button | `dm task node remove <id>` |
| 确认任务图 | confirm button | `dm task confirm` |
| 保存 | save button | `dm task save` |
| 导出/导入 | export/import | `dm task export` / `dm task import` |

**CLI 调试**: `dm task show | python -m json.tool`

---

### 4. CognitiveProfilePage — `/profile`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| OCEAN 10 维度 | `getProfile()` → oceAN_dims | `dm profile show` |
| MBTI 类型 | `getProfile()` → mbti | `dm profile mbti <type>` |
| BFI 维度 | `getProfile()` (optional) | `dm profile bfi-set <name> <val>` |
| 推理可信度分布 | `getTrace()` | `dm pcr route <text>` |
| 单维度详情 | click on dimension | `dm profile dimension <name>` |
| 维度修正 | manual edit | `dm profile correction add <dim> <delta>` |
| 修正列表 | corrections list | `dm profile correction-list` |
| 撤销修正 | undo | `dm profile correction-undo <id>` |
| 画像历史 | history chart | `dm profile history` |
| 导出画像 | export | `dm profile export` |
| 重置 | reset | `dm profile reset` |

---

### 5. SessionsPage — `/sessions`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 会话列表 (名称/大小) | `useV6Sessions().sessions` | `dm session list` |
| 持久化状态 | `getPersistence()` | `dm data show` |
| 持久化图统计 | `getPersistenceGraphs()` | `dm graph stats` |
| 会话详情 | `SessionDetailDrawer` | `dm session info <id>` |
| 会话历史 | (drawer content) | `dm session history <id>` |
| 删除会话 | delete button | `dm se delete <id>` |
| 导入文档 | `IngestDocumentModal` | `dm knowledge add <name> <type> <identity>` |
| 刷新 | refresh | `dm session list` + `dm data show` |

---

### 6. GatewayPage — `/gateway`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 模型列表 (9 providers) | `getGatewayProviders()` | `dm reply model` |
| Provider 配置 | ProviderCard[apiKey, baseUrl] | `dm cfg show` |
| API Key 管理 | form input | `dm cfg show` (readonly) |
| 连接测试 | `testProviderConnection()` | `dm engine status` (health check) |
| Token 用量 | `getTokens()` | `dm eventlog stats` (call count) |
| 使用统计 | `getGatewayUsage()` | `dm eg stats` |
| 健康检查 | `getGatewayHealth()` | `dm engine status` |
| Provider 切换 | `setActive()` | `dm reply model set <name>` |

---

### 7. ConversationGraphPage — `/graph`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 对话图 (节点+边) | `getGraph()` | `dm graph show` |
| 对话树 | `getDiscourseTree()` | `dm discourse tree` |
| 对象图 | `getObjects()` | `dm knowledge show` |
| 节点搜索 | search bar | `dm graph node-search <keyword>` |
| 添加节点 | + button | `dm graph node-add <name> --type=<type>` |
| 编辑节点 | click node | `dm graph node-edit <id>` |
| 删除节点 | delete | `dm graph node-remove <id>` |
| 图导出 | export | `dm graph export` |
| 图导入 | import | `dm graph import <file>` |

---

### 8. DeepChainPage — `/deepchain`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 关系链 | `getRelations()` | `dm assoc show` |
| 因果链 | `getCausal()` | `dm engineering impact <change>` |
| 行为图 | `getBehavior()` | `dm behavior show` |
| 工程约束 | `getEngineering()` | `dm engineering constraint-list` |
| 层级查看 | layer selector | `dm assoc layer <N>` |
| 行为边管理 | edge CRUD | `dm beh edge-add <from> <to>` |
| 模式查看 | pattern viewer | `dm beh pattern <name>` |
| 约束检查 | check | `dm engineering constraint-check` |

---

### 9. MetaCenterPage — `/meta`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 元认知状态 (队列/决策/精确度) | `getMetaStats()` | `dm meta show` |
| 审核队列 | `getMetaQueue()` | `dm meta queue` |
| 异常列表 | anomalies | `dm meta anomaly add <type> <desc>` |
| 修正建议 | corrections | `dm meta correction add <target> <action>` |
| 批量应用 | apply | `dm meta correction-apply` |
| 丢弃修正 | discard | `dm meta correction-discard <id>` |
| 处理队列 | process | `dm meta queue-process` |
| 版本历史 | versions | `dm versions show` |

---

### 10. PipelinePage — `/pipeline`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| Blueprint DAG | blueprint data | `dm blueprint show` |
| Decider 执行结果 | decider data | `dm decider show` |
| 12 链状态 | chain status | `dm decider chains` |
| Subgraph 编译 | subgraph view | `dm subgraph show` |
| Context IR | context view | `dm context compile` + `dm context show` |
| DAG 构建 | build | `dm blueprint build <text>` |
| DAG 节点操作 | node CRUD | `dm bp node-add <chain>` |
| DAG 边操作 | edge CRUD | `dm bp edge-add <from> <to>` |
| 策略切换 | strategy selector | `dm bp strategy-set <name>` |
| Tick 查看 | tick viewer | `dm dc tick <N>` |

---

### 11. BehaviorPage — `/behavior`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 行为图 | `getBehavior()` | `dm behavior show` |
| 行为预测 | prediction view | `dm behavior predict <text>` |
| 行为统计 | stats | `dm beh stats` |
| 行为边管理 | edge CRUD | `dm beh edge-add/weight/remove` |
| 模式管理 | pattern manager | `dm beh pattern <name>` |

---

### 12. EngineeringPage — `/engineering`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| 工程知识图 | `getEngineering()` | `dm engineering show` |
| 约束列表 | constraints | `dm engineering constraint-list` |
| 约束检查 | check | `dm engineering constraint-check` |
| 添加约束 | add | `dm engineering constraint-add <type> <target> <spec>` |
| 删除约束 | remove | `dm engineering constraint-remove <id>` |
| 变更传播 | propagate | `dm engineering propagate` |
| 影响分析 | impact | `dm engineering impact <change>` |
| 知识对象 | objects | `dm kn search <keyword>` |
| 关系管理 | relations | `dm kn relation-add/remove` |

---

### 13. SettingsPage — `/settings`

| 展示内容 | 前端数据源 | CLI 等价命令 |
|----------|-----------|------------|
| Provider 配置 | config view | `dm cfg show` |
| 模型选择 | model selector | `dm reply model set <name>` |
| 全局参数 | parameters | `dm eg stats` |
| 数据管理 | data panel | `dm dt paths` / `dm dt backup` / `dm dt restore` |
| 版本信息 | version | `dm gl version` |
| ABC 规则 | rules | `dm rules show/add/edit/remove` |
| 注解管理 | annotations | `dm annotations show` |
| 反馈管理 | feedback | `dm feedback show` |
| 惯性设定 | inertia | `dm inertia show` |

---

### 14. FloatingActionButton (浮动按钮)

| 功能 | CLI 等价命令 |
|------|------------|
| 快速聊天 | `dm session new` → `dm event send <text>` |
| 任务查看 | `dm task show` |
| 通知 | `dm eventlog tail` |

---

## v6 API 端点 → CLI 映射

| v6 Endpoint | 前端用途 | CLI 命令 |
|------------|---------|---------|
| GET /v6/profile | CognitiveProfilePage | `dm profile show` |
| GET /v6/trace | CognitiveProfilePage | `dm pcr route <text>` |
| GET /v6/abc | 规则详情 | `dm abc show` |
| GET /v6/mind | Mind agent | `dm mind show` |
| GET /v6/graph | ConversationGraphPage | `dm graph show` |
| GET /v6/discourse-tree | ConversationGraphPage | `dm discourse tree` |
| GET /v6/objects | 知识对象 | `dm knowledge show` |
| GET /v6/relations | DeepChainPage | `dm assoc show` |
| GET /v6/causal | DeepChainPage | `dm engineering show` |
| GET /v6/behavior | DeepChainPage/BehaviorPage | `dm behavior show` |
| GET /v6/engineering | DeepChainPage/EngineeringPage | `dm engineering constraint-list` |
| GET /v6/rules | SettingsPage | `dm rules show` |
| GET /v6/sessions | SessionsPage/DashboardPage | `dm session list` |
| GET /v6/persistence | SessionsPage | `dm data show` |
| GET /v6/gateway/providers | GatewayPage | `dm cfg show` |
| GET /v6/metrics | DashboardPage | `dm metrics show` |
| GET /v6/meta/stats | MetaCenterPage | `dm meta show` |

---

## 当前实现状态

### ✅ 已完成 (前端 + CLI 双通)
- ChatPage: 创建会话、发送消息、获取回复 → `dm session new / event send`
- TaskPlanningPage: 获取/保存任务图 → `dm task show / task save`
- DashboardPage: 会话列表、健康检查 → `dm session list / engine status`
- SessionsPage: 会话管理 → `dm session list / se clear / se delete`

### ⚠️ 数据有但未连线
- CognitiveProfilePage: 后端返回数据，前端未绑定到 UI
- ConversationGraphPage: 图数据有，未连线到画布
- GatewayPage: providers 数据有，API key 管理未连线
- MetaCenterPage: meta/stats 数据有，未连线
- DeepChainPage: 所有链数据有，未连线
- PipelinePage: blueprint 数据有，未连线
- BehaviorPage: behavior 数据有，未连线
- EngineeringPage: engineering 数据有，未连线

### ❌ 完全未实现
- SettingsPage: 空壳页面，无数据连线
- FloatingActionButton: ChatOverlay 未连线

---

## 实施优先级

```
Phase 1 — 核心数据绑定 (让所有页面有数据显示):
  P1.1 CognitiveProfilePage ← profile + trace
  P1.2 ConversationGraphPage ← graph + discourse-tree + objects
  P1.3 GatewayPage ← gateway/providers + tokens + usage
  P1.4 DeepChainPage ← relations + causal + behavior + engineering
  P1.5 MetaCenterPage ← meta/stats + meta/queue
  P1.6 PipelinePage ← blueprint + decider + subgraph

Phase 2 — 操作互动 (CRUD 绑定):
  P2.1 画像编辑 (dimension set, mbti, corrections)
  P2.2 图编辑 (node CRUD, edge CRUD)
  P2.3 任务图编辑 (drag + add + remove + confirm)
  P2.4 Gateway 配置 (provider add/remove, key management)

Phase 3 — 可视化:
  P3.1 OCEAN 雷达图
  P3.2 任务图 FlowchartCanvas 动画
  P3.3 DAG 管线可视化
  P3.4 行为图/关系图
```
