# 前端深度审计 — 第三轮（2026-08-06）

> 触发: 阶段 B 前端绑定前，用户要求"先对照 docs/only/frontend 设计文档 →
> 对已实现内容深度审计 → 再准备绑定和延拓"。
> 方法: 对照 FE_DEEP_AUDIT_20260805 / FRONTEND_IMPL_AUDIT_20260803 /
> RIGHT_DOCK_DESIGN_20260805 三份设计文档 → tsc 全量编译 → 前后端契约
> 逐项实测（后端 kernel dispatch 源码对照前端类型/页面用法）。
> 结论先行: **深审文档 B1（GatewayPage 崩溃）已过时（实测已修复）; 真实
> 契约漂移集中在 4 处（providers/graph/metrics/chatStore）; 另有 1 处真实
> 运行期 bug（theme 解构错误）+ 1 处 ReferenceError 隐患（debug._syncEnabled）。**

---

## 一、编译状态（与深审一致，无新增）

`tsc --noEmit -p tsconfig.app.json` = **53 错误**，与 08-05 深审完全一致。
错误分布（实测）:

| 类别 | 数量 | 代表 |
|---|---:|---|
| TS6133 未使用 | ~25 | TaskFlow/useChat/ChatOverlay/ConversationGraph 死 import |
| 类型契约错误 | 11 | SettingsPage metrics/providers；ConversationGraphPage label/type；chatStore addAIMessage |
| 真实 API 不匹配 | 9 | TaskFlow Position/NodeTypes/EdgeTypes/BackgroundVariant |
| 运行期 bug 类 | 2 | ConversationGraph theme 解构；debug._syncEnabled |
| 其他 | 6 | ChatPage _ConnectionState；ChatOverlay 参数个数等 |

## 二、深审 B1 过时修正（重要）

深审文档 B1（P0）: "GatewayPage onUpdateForm/onSetActive 未定义 → 配置表单
输入即崩溃"。**实测: 已修复/不存在** —
`updateConfigForm`（L546）+ `handleSetActive`（L572）已定义，L803-804 已传给
ProviderCard，tsc 对 GatewayPage 零报错。
→ 修正: B1 无需再修 GatewayPage；本轮编译归零不含此项。

## 三、契约实测（本轮新增，前后端对照）

### 3.1 V6ProvidersResponse vs kernel_providers（真漂移，SettingsPage 显示 '—'）
- 后端 `kernel_providers()`（dispatch.py:1118）返回 `{active:{name,model,healthy,stats},
  failover}`；前端 `V6ProvidersResponse = {active, failover}` ✅ 类型一致
- 但 SettingsPage:164-165 用 `providers?.active_provider/active_model`——类型不存在，
  运行期 undefined → 永远显示 '—'
- GatewayPage 用 `getGatewayProviders()`（/v6/gateway/providers, switch 代理）✅ 正常
- **修**: 后端 kernel_providers 补 `active_provider/active_model` 冗余字段（真实值，
  内核自洽）; 前端类型加可选字段 → SettingsPage 直接可用

### 3.2 V6GraphNode vs kernel_graph（类型落后，后端数据已有）
- 后端 `kernel_graph()` 真实返回 `{id, label, type, size, temperature, entities}`
  （dispatch.py:205-258, discourse tree 或 v3_sessions 兜底）
- 前端 `V6GraphNode = {id, state}` 缺字段 → ConversationGraphPage:84-86 报错
- **修**: 前端类型补 `label/type/size/temperature/entities`（非后端缺数据）

### 3.3 V6MetricsResponse（SettingsPage 渲染 unknown）
- 类型 `{[key:string]: unknown}` → `metrics?.subsystems_loaded` 是 unknown 不能渲染
- 后端 `kernel_metrics()` 真实返回 4 字段（engine_uptime/subsystems_loaded/
  subsystems_total/total_turn_count）✅ 与用法一致
- **修**: 前端类型细化这 4 字段（保留 index signature 兼容）

### 3.4 chatStore addAIMessage（接口落后于实现）
- 接口声明 `(content: string) => void`；实现 `(content, extra)` 双参（extra spread
  进 ChatMessage）→ ChatPage/ChatOverlay 双参调用报错
- **修**: 接口改 `(content: string, extra?: Partial<ChatMessage>) => void`

### 3.5 ConversationGraph theme 解构（真实运行期 bug）
- `useTheme()` 返回 `Theme`（'dark'|'light' **字符串**，themeStore.ts），
  组件却 `const { theme } = useTheme()` → theme 恒 undefined → isDark 恒 false
  → 右键菜单/深色样式永远浅色
- **修**: 两处改 `const theme = useTheme()`

### 3.6 debug.ts `_syncEnabled`（ReferenceError 隐患）
- `pauseDebug()` 引用未定义变量 `_syncEnabled` → 点击"暂停调试"运行期崩溃
- **修**: 删该句（disableBackendSync() 已做实际工作）

### 3.7 其余（浅修）
- ChatPage `import type { _ConnectionState }` 不存在且未使用 → 删
- ChatOverlay `AnimatePresence` 未使用 → 删 import；`addAI` 调用去 `as any`
  （chatStore 签名修好后）+ taskGraph null→undefined 处理
- FlowchartCanvas `clickMode/setClickMode` 未使用 → 删

## 四、死代码确认（重扫，与深审一致 + 精确化）

- task 全家桶孤儿 ✅（TaskFlow/TaskNode/TaskEdge/TaskDetailPanel/
  TaskStatsBar/TaskExecutionControls/task/index.ts）——taskStore/types/task.ts
  活跃（TaskPlanningPage 用），保留
- useChat.ts 孤儿 ✅（无反向引用; 其 execution 字段错误随归档消失）
- WS 四套全部孤儿 ✅（useWebSocket→websocketClient 互引; websocket/ws 无消费者;
  ApiConfigPanel 仅自带 wsUrl 文本不引用 lib/ws）
- useV6TaskWS 孤儿 ✅; chatConnection/animations/graph-utils/useMediaQuery/
  useSession 孤儿 ✅
- 孤儿组件 ✅（ClarificationPanel/ConnectionIndicator/IntentTag/StatusBadge/
  StatusBar/TaskGraphView/ThinkingBlock/ThinkingPanel/ThemeToggle）

## 五、本轮修复范围（B1/B2/B4 编译归零，不动 B3 归档）

| # | 文件 | 修复 |
|---|---|---|
| 1 | types/api.ts | V6GraphNode/V6ProvidersResponse/V6MetricsResponse 补字段 |
| 2 | stores/chatStore.ts | addAIMessage 接口双参 |
| 3 | components/ChatOverlay.tsx | 删 AnimatePresence；去 as any |
| 4 | components/graph/ConversationGraph.tsx | theme 解构 ×2；删未用 import/参数 |
| 5 | components/task/FlowchartCanvas.tsx | 删 clickMode |
| 6 | pages/ChatPage.tsx | 删 _ConnectionState import；taskGraph null 处理 |
| 7 | lib/debug.ts | 删 _syncEnabled |
| 8 | core/agent/kernel/dispatch.py | kernel_providers 补 active_provider/active_model |

## 六、后续（本轮完成后）

- B3: 死代码归档（task 全家桶/useChat/WS 四套/孤儿组件 → un_use/）→ 消除
  ~15 个 TS 错误 + 减 ~200KB 源码
- B5: 13 页真数据绑定 smoke（页面→端点逐页验证）
- B6: RightDock 三屏结构（RIGHT_DOCK_DESIGN，uiStore 扩展 + 拖拽 resize +
  路由联动 + 内容坞切换）
- GAP-F1: 变更日志视图（决策事件数据源已就绪）

---

## 七、本轮施工结果（2026-08-06 晚）

**编译: 53 错误 → 0**（tsc 归零 + `vite build` 成功，产物 3.00s 出包）。
后端 `core/agent/api/tests/test_kernel_dispatch.py` 49/49 全绿
（含 test_gateway_providers_no_fake）。

### 已修复（对应 §五 计划 1-8 全部落地）
1. types/api.ts: V6GraphNode 补 label/type/size/temperature/entities;
   V6ProvidersResponse 补 active_provider/active_model; V6MetricsResponse 细化 4 字段
2. stores/chatStore.ts: addAIMessage 接口 `(content, extra?: Partial<ChatMessage>)`
3. ChatOverlay: 删 AnimatePresence; addAI 去 `as any` + taskGraph null→undefined
4. ConversationGraph: `useTheme()` 解构 bug ×2（theme 恒 undefined → isDark 恒 false）;
   删 NodeMouseHandler/GripVertical/onEdgeClick/onNodeAdd 未用项
5. FlowchartCanvas: 删死功能 clickMode（setClickMode 从未调用，删除模式是死的）
6. ChatPage: 删 _ConnectionState import; 无效动态 import 清理; taskGraph null 处理
7. lib/debug.ts: 删 `_syncEnabled`（pauseDebug 运行期 ReferenceError 隐患）
8. kernel/dispatch.py: kernel_providers 补 active_provider/active_model 冗余字段

### 归档（B3 最小集，编译报错的孤儿）
- `components/task/` 全家桶（TaskFlow/TaskNode/TaskEdge/TaskDetailPanel/
  TaskStatsBar/TaskExecutionControls/index）→ `src/un_use/components/task/`
- `hooks/useChat.ts` → `src/un_use/hooks/`
- `lib/chatConnection.ts` → `src/un_use/lib/`
- tsconfig.app.json 加 `exclude: ["src/un_use"]`（保留文件供参考，不参与编译）
- taskStore/types/task.ts/FlowchartCanvas 保留（TaskPlanningPage 活跃使用）

### 本轮判定（重要）
- 深审 B1（GatewayPage 崩溃）过时修正: 已定义接线，无需修
- 契约漂移 4 处全部修复（providers/graph/metrics/chatStore），其中 2 处为
  前端类型落后（后端数据本就正确）、1 处为内核补字段、1 处接口落后实现
- 发现 2 处真实运行期 bug（theme 解构 / debug._syncEnabled）已修复

### 待办（下一阶段 B）
- B3 完整归档（其余无编译错误的孤儿: WS 四套/useMediaQuery/useSession/
  ClarificationPanel/ConnectionIndicator/IntentTag/StatusBadge/StatusBar/
  TaskGraphView/ThinkingBlock/ThinkingPanel/ThemeToggle/animations/graph-utils
  /useV6TaskWS）— 需先确认 WS 四套引用矩阵（本轮已确认全部无外部消费者）
- B5: 13 页真数据绑定 smoke（需启动 start.bat: v6_app 8000 + 网关 8080）
- B6: RightDock 三屏结构（布局延拓, 依赖 B5 后地基稳定）
- GAP-F1: 变更日志视图
