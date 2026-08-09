# 前端实现深审 — 第二轮（2026-08-05）

> 日期: 2026-08-05 | 范围: frontend/src 全部 139 文件 / 23,334 行
> 触发: 用户要求阶段 B 前端绑定前先深审（08-03 首轮仅结构盘点，未跑构建/未验数据真实性）
> 方法: tsc 全量编译 + 运行时 API 探针 + import 引用矩阵 + 页面→API 调用链逐页核查
> 结论先行: **前端当前处于「编译失败」状态（53 个 TS 错误），但数据接线质量远超
> 首轮预期——FE-1/FE-4 已被 M1-M9 批次修复，真实缺口集中在类型契约 + 死代码。**

---

## 一、编译健康度（重大发现）

`tsc -b`（或 `tsc --noEmit -p tsconfig.app.json`）: **53 个 TS 错误，编译失败**。

### 1.1 根因（P0）: 类型遮蔽 shim
```
src/types/syntax-highlighter.d.ts（296 行，v3.0 时代 0e7a4aa 写入）:
  内嵌 declare module '@reactflow/core' / '@reactflow/background' /
  '@reactflow/minimap' 手写 shim → 遮蔽真实包类型（@reactflow/core 11.11.4
  自带完整 d.ts）→ addEdge/NodeProps/NodeMouseHandler/onNodeContextMenu/
  onNodesDelete/Minimap.pannable 全部"不存在" → graph 组件 15+ 错误。
  （另含 react-force-graph-2d 重复 shim——已由 ConversationGraph 的 ReactFlow 取代）
```

**处置（本批已做）**: shim 删除，仅保留 react-syntax-highlighter（该包无类型来源）。
删除后 @reactflow 遮蔽错误全部消失；剩余错误为**真实类型缺陷**。

### 1.2 剩余 53 个真实错误（分类）
| 类别 | 数量 | 代表 | 性质 |
|---|---:|---|---|
| TS6133 未使用（noUnusedLocals）| ~25 | TaskFlow useRef/addEdge/injectDashAnimation、ChatOverlay AnimatePresence、GatewayPage testLoading | 死代码信号 |
| 真实 API 不匹配 | 8 | TaskFlow Position/NodeTypes/EdgeTypes/BackgroundVariant；ConversationGraph Theme.theme | 运行期潜在 bug |
| 未定义标识符 | 5 | GatewayPage onUpdateForm×2/onSetActive；taskStore TaskNode/TaskNodeType/TaskEdge | **运行时会 ReferenceError** |
| 类型契约错误 | 8 | useChat execution 字段；SettingsPage active_provider/active_model；chatStore addAIMessage 签名 | 前后端契约漂移 |
| 其他 | 7 | ChatPage _ConnectionState、debug.ts _syncEnabled、ChatOverlay 参数个数等 | 杂项 |

> GatewayPage onUpdateForm/onSetActive: ProviderCard 内调用但主组件仅定义了
> updateConfigForm（签名 `field: 'apiKey'|'baseUrl'`）→ **配置表单输入即崩溃**（P0 级 UI bug）。

---

## 二、FE-1/FE-4 现状核查（首轮 P0/P2 — 已修复）

| 首轮问题 | 现状 | 证据 |
|---|---|---|
| FE-1 白盒编辑后端未注册 404 | ✅ 已修复（M2）| v6_app.py L82 `_try_include api_viz_edit` + L257 init(engine)；12 端点齐（graph/discourse-tree/objects/relations/ir/revert/mode/journal/serialize/format）|
| FE-4 stubs 假数据 | ✅ 已修复（M8）| stubs_api.py 重写为内核 dispatch（123 处 kernel_* 调用），docstring 明示"无 stub 假数据"；/v6/profile、/graph、/meta/queue、/causal-chain、/behavior/patterns 等均真函数 |
| FE-2 死代码 | ⚠️ 仍存在（本批重扫，见 §四）| 引用矩阵 |
| FE-3 四套 WS | ⚠️ 仍存在（全部死代码）| 引用矩阵 |

---

## 三、数据接线（页面→API 全链路，逐页核查）

13 路由页全部接线，数据源为真端点（非假数据）:
```
Chat/ChatOverlay         api/session.ts (createSession/sendMessage) + chatStore
ConversationGraphPage    useV6Graph → getGraph/getDiscourseTree/getObjects + editGraph/
                         editDiscourseTree/editObjects（白盒写路径已通）
GatewayPage              useV6Gateway → /v6/gateway/*（switch 真实代理）
PipelinePage             getCausalChain/getDegradation/getSubgraphCache/editParameters
MetaCenterPage           getMetaQueue/getMetaStats/getVersions
BehaviorPage             getBehaviorPatterns/getInertia/submitBehaviorFeedback
DeepChainPage            getSubgraph/getBelief（内核 dispatch）
EngineeringPage          getEngineering | SettingsPage getPersistence/getRules
Dashboard                api/v4 + useV6Sessions | SessionsPage useV6Sessions
```

后端端点存在性抽验（rg stubs_api）: /causal、/behavior/patterns、/meta/queue、
/causal-chain、/persistence、/sessions 等全部注册 ✅。

---

## 四、死代码重扫（相对首轮更新）

### 4.1 完全孤儿（0 外部引用）— 可安全归档
```
组件: ClarificationPanel / ConnectionIndicator / IntentTag / StatusBadge /
      StatusBar / TaskGraphView / ThinkingBlock / ThinkingPanel / ThemeToggle
task 全家桶: TaskFlow / TaskNode / TaskEdge / TaskDetailPanel / TaskStatsBar /
      TaskExecutionControls / task/index.ts（TaskPlanningPage 用 FlowchartCanvas 替代）
hooks: useChat（ChatPage 已改 api/session.ts + chatStore，useChat 被跳过）/
       useWebSocket / useV6TaskWS / useSession / useMediaQuery
lib:   ws.ts / websocket.ts / websocketClient.ts / chatConnection.ts /
       animations.ts / graph-utils.ts（30KB 全死）/
api:   session.ts 的 editDAG/submitClarification/getHistory；
       v6.ts 的 DEFAULT_PROVIDERS/checkServiceStatus/editIr/editRelations/
       submitProfileCorrections（5 个）
```

### 4.2 WS 四套终态（FE-3）
```
唯一活跃 WS 使用 = useChat 内部（V4WebSocketEvent 类型 + 浏览器原生 WebSocket
  via api/v4.ts getV4WsUrl）——但 useChat 本身是孤儿
→ 四套（useWebSocket/websocketClient/ws.ts/websocket.ts/chatConnection）全部死代码，
  真实聊天走 HTTP POST（api/session.ts sendMessage）
```

### 4.3 注意
- lib/api.ts 被 45 处引用（活跃，勿归档）；lib/config.ts 3 处活跃；lib/debug.ts 2 处活跃。
- stores/ 各 store 通过 stores/index.ts 门面被页面消费（扫描对门面有误报，已人工复核）。

---

## 五、前端↔后端契约漂移（阶段 B 前置）

```
1. V6GraphNode 缺 label/type 字段（ConversationGraphPage 用，类型未定义）→ 后端 graph 响应核对
2. V6ProvidersResponse 缺 active_provider/active_model（SettingsPage 用）→ 后端 providers 响应核对
3. ChatResponse 缺 execution 字段（useChat 用，但 useChat 是孤儿——若归档则消失）
4. chatStore.addAIMessage 签名与 useChatStore 用法不一致（2 参 vs 1 参）→ ChatPage 实际 2 参
5. _ConnectionState vs ConnectionState（ChatPage 导入错误）
```

---

## 六、审计结论与建议

### 已确认事实
1. **前端编译失败**（53 错误）→ 阶段 B 绑定前必须修通（P0）。
2. **数据链路真实**（FE-1/FE-4 已修复）→ 绑定不是"接假数据"，是"修类型 + 清死代码"。
3. **GatewayPage 配置表单运行时会炸**（onUpdateForm 未定义）→ 最紧急 UI bug。
4. 死代码量级大（~40 文件/6KB+ 组件）但**全部是历史演进残留**，归档无风险。

### 建议处置顺序（阶段 B 前置施工）
```
B1（P0）: 修 GatewayPage onUpdateForm/onSetActive + SettingsPage 契约 → tsc 归零
B2（P0）: TaskFlow/ConversationGraph 真实 API 适配（Position/NodeTypes/EdgeTypes/
          BackgroundVariant/theme）→ 编译通过
B3（P1）: 死代码归档（task 全家桶/WS 四套/useChat/孤儿组件/graph-utils）→ un_use/
B4（P1）: 契约核对（V6GraphNode/V6ProvidersResponse/chatStore 签名）
B5（P2）: 绑定验证（13 页真数据 smoke）
```

---

## 七、本批已做（审计顺带修复）
```
删除 src/types/syntax-highlighter.d.ts 中 @reactflow/core|background|minimap 遮蔽 shim
  + react-force-graph-2d 重复 shim（保留 react-syntax-highlighter 必要 shim）
  → 消除 ~15 个虚假类型错误；剩余 53 个为真实错误
```
