# DialogMesh v6 — 前端架构文档

> 2026-07-25 · React 19 + TypeScript + Vite + Zustand · 24K行 110+文件

---

## 一、技术栈

```
框架:   React 19.2
语言:   TypeScript
构建:   Vite 6
路由:   React Router (隐式, 基于 App.tsx 页面切换)
状态:   Zustand (轻量 store)
样式:   Tailwind CSS + framer-motion (动画)
图表:   Recharts (统计), ForceGraph (关系图)
流图:   @reactflow/core (TaskFlow, 执行图)
```

---

## 二、页面清单 (15页)

| 页面 | 文件 | 功能 | 接入状态 |
|------|------|------|---------|
| Chat | ChatPage.tsx | 对话 + PlanGate审批 | ⚠️ 有UI, 需接v6管线 |
| Dashboard | DashboardPage.tsx | 概览统计卡片 | ⚠️ 读API, 需数据 |
| Pipeline | PipelinePage.tsx | 管线参数/降级/调试 | ⚠️ 有UI, 需接ParameterRegistry |
| TaskPlanning | TaskPlanningPage.tsx | 任务图(ReactFlow) + 执行状态 | ⚠️ 有UI, 需接ExecutionPipeline |
| CognitiveProfile | CognitiveProfilePage.tsx | OCEAN画像+惯性 | ✅ useV6Profile |
| Engineering | EngineeringPage.tsx | 约束规则管理 | ⚠️ 有UI, 需接ConstraintTree |
| Gateway | GatewayPage.tsx | 服务检测+Provider管理 | ✅ useV6Gateway |
| MetaCenter | MetaCenterPage.tsx | 元认知审计+版本 | ⚠️ 有UI, 需接MetaTree |
| Settings | SettingsPage.tsx | 系统配置 | ⚠️ 读API |
| Sessions | SessionsPage.tsx | 会话管理 | ✅ useV6Sessions |
| DeepChain | DeepChainPage.tsx | 深层链路追踪 | ⚠️ 有UI, 需接SpanTracer |
| Behavior | BehaviorPage.tsx | 行为模式分析 | ⚠️ 有UI |
| ConversationGraph | ConversationGraphPage.tsx | 对话图可视化 | ⚠️ 有UI |
| NotFound | NotFoundPage.tsx | 404 | ✅ |
| — | GraphPage (内嵌) | 子图浏览器 | ⚠️ 有UI |

---

## 三、核心组件 (按功能分组)

### TaskFlow 执行流 (ReactFlow)
```
TaskFlow.tsx              — 主画布
TaskNode.tsx              — 节点 (状态颜色)
TaskEdge.tsx              — 边 (依赖箭头)
TaskDetailPanel.tsx       — 节点详情抽屉
TaskExecutionControls.tsx — 执行控制 (播放/暂停/停止)
TaskStatsBar.tsx          — 统计条
```
接入需求: ExecutionPipeline 实时状态 → TaskFlow 节点

### PlanGate 审批
```
ChatPanel.tsx             — 对话面板 (含审批UI)
ChatInput.tsx             — 输入框
MessageBubble.tsx         — 消息气泡
ThinkingBlock.tsx         — LLM思考块
ClarificationPanel.tsx    — 澄清面板
```
接入需求: PlanGate.checkpoint → ChatPanel 审批展示

### Profile 画像
```
ProfileStatsGrid.tsx      — 5维雷达图
ProfileCorrectionsPanel.tsx — 修正历史
ProfileInertiaPanel.tsx   — 惯性追踪
DimensionBreakdown.tsx    — 维度分解
MindSpacePanel.tsx        — 心智空间
```
接入: ✅ useV6Profile 已有

### Gateway 网关
```
ProviderSelector.tsx      — provider选择器
ConnectionIndicator.tsx   — 连接状态
ApiConfigPanel.tsx        — API配置
```
接入: ✅ useV6Gateway 已有

### Graph 图可视化
```
DiscourseTreeView.tsx     — 对话树
ConversationGraph.tsx     — 概念图
ObjectsView.tsx           — 对象视图
AnnotationsView.tsx       — 标注
GraphToolbar.tsx          — 工具栏
```

---

## 四、Hooks 清单 (12个)

| Hook | 用途 | 接入 |
|------|------|------|
| useChat | 对话发送/接收 | ⚠️ 需接v6管线 |
| useV6Pipeline | 管线参数/降级 | ⚠️ 需接ParameterRegistry |
| useV6Gateway | Provider/Model切换 | ✅ 已接 |
| useV6Profile | 画像数据 | ✅ 已接 |
| useV6DeepChain | 链路追踪 | ⚠️ 需接SpanTracer |
| useV6Sessions | 会话管理 | ✅ 已接 |
| useV6Graph | 图数据 | ⚠️ 需接 |
| useSession | 老session | ⚠️ 需更新 |
| useWebSocket | WS连接 | ⚠️ 需接:9100 |
| useHealth | 健康检查 | ⚠️ 需接 |
| useContentScript | 内容脚本桥 | ⚠️ |
| useMediaQuery | 响应式 | ✅ |

---

## 五、Store 清单 (10个, Zustand)

| Store | 职责 | 接入 |
|-------|------|------|
| chatStore | 消息列表/发送状态/审批 | ⚠️ 需接管线 |
| taskStore | 任务图/执行步骤/状态 | ⚠️ 需接ExecutionPipeline |
| graphStore | 图数据/布局/选中 | ⚠️ 需接 |
| profileStore | 画像数据 | ✅ |
| sessionStore | 会话列表 | ✅ |
| analyticsStore | 统计指标 | ⚠️ |
| themeStore | 主题切换 | ✅ |
| overlayStore | 浮层状态 | ✅ |
| uiStore | UI状态 | ✅ |
| index.ts | 聚合导出 | ✅ |

---

## 六、API 层

| 文件 | 行数 | 端点 | 状态 |
|------|------|------|------|
| v6.ts | 653L | 42端点 | ⚠️ 定义完整, 部分未接后端 |
| v4.ts | — | 老端点 | ⚠️ 需更新 |
| session.ts | — | 会话 CRUD | ✅ |

---

## 七、优先接入顺序 (P0→P1→P2)

```
P0 (核心体验):
  1. Chat管线接入        — useChat → agent_native.process()
  2. PlanGate审批        — checkpoint → ChatPanel
  3. TaskFlow实时更新     — ExecutionPipeline → taskStore
  4. WebSocket :9100     — useWebSocket 接执行引擎

P1 (管理面板):
  5. Pipeline参数面板    — ParameterRegistry → PipelinePage
  6. Gateway Provider管理  — useV6Gateway (已部分接)
  7. SpanTracer追踪      — trace_id → DeepChainPage
  8. MetaCenter审计      — MetaTree → MetaCenterPage

P2 (增强):
  9. ConstraintTree管理   — EngineeringPage
  10. 图可视化           — ConversationGraphPage
  11. 行为分析           — BehaviorPage
```

---

## 八、后端API缺口

```
已有端点 (需验证):
  /v6/pipeline/status      — 管线状态
  /v6/parameters           — 参数CRUD
  /v6/profile              — 画像 (已接)
  /v6/gateway/providers    — Provider管理 (已接)
  /v6/sessions             — 会话 (已接)
  /v6/trace                — 追踪 (SpanTracer)

缺少端点:
  /v6/chat                 — 对话管线入口 (需新加)
  /v6/execution/status     — 执行状态 (需新加)
  /v6/checkpoint/respond   — 用户审批回传 (需新加)
  /v6/ws                   — WebSocket升级 (/ws, 需新加)
```
