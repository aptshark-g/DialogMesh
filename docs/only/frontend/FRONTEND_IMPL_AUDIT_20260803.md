# 前端实现审计 — frontend/ 真实 React+Vite 项目（最大审计盲区补全）

> 日期: 2026-08-03 | 触发: 用户核查新增「前端项目 139 文件 1.3MB src 从未被审计」。
> 方法: 全量源码盘点（排除 node_modules）+ 前后端 API 接线矩阵 + 孤儿组件扫描 +
> 后端路由注册核查（探针/源码）。
> 结论先行: **前端是真实且庞大的 React+Vite 项目（src 约 136 源文件），与后端形成
> "前端全接口 vs 后端半注册"的割裂——白盒编辑 API（/v6/edit/*）后端未注册 → 前端
> GraphEditPanel 调用必然 404；10+ 组件为孤儿死代码。**

---

## 一、体量与组成（实测）

```
frontend/ 含 node_modules（.js 11128 / .map 3273 / .mjs 4103 等噪音）
真实源码 src/ ≈ 136 文件（87 .tsx + 44 .ts + 5 .css），约 700KB

目录分布:
  components/   72 文件（graph 7 / profile 8 / sessions 3 / task 8 / ui 9 / 其他 37）
  pages/        14 文件（GatewayPage 70.4KB 最大 / MetaCenter 31.3 / Pipeline 31.6 /
                         ConversationGraph 25.9 / DeepChain 25.4 / Behavior 25.8）
  hooks/        13 / stores/ 10（Zustand）/ types/ 10 / api/ 3 / lib/ 10 / adapters/ 1
  App.tsx + main.tsx + background.ts + index.css + light.css

技术栈: React 19 + TS + Vite + Zustand + ReactFlow + dagre + Mermaid + framer-motion
        + Recharts + ForceGraph（types/force-graph.d.ts 声明）
```

---

## 二、API 接线矩阵（前端 api/v6.ts ↔ 后端 v6_app 注册）

### 2.1 前端 42 端点（api/v6.ts, 31.9KB）
```
Profile:      getProfile/editProfile/getTrace/getAbc/getMind/getMindFull
可视化:        getGraph/getDiscourseTree/getObjects
深层链:        getRelations/getCausal/getBehavior/getEngineering
规则:          getRules/editRule/submitFeedback
Provider:      getProviders/switchProvider/getTokens/testProviderConnection
参数:          editParameters + Pipeline + Persistence + Subgraph
工程链:         editEngineeringConstraints
白盒编辑(可视化): editGraph→PUT /v6/edit/graph
                editDiscourseTree→PUT /v6/edit/discourse-tree
                editObjects→PUT /v6/edit/objects
                （types/api.ts 还声明 editRelations/editIr → /v6/edit/relations /v6/edit/ir）
```

### 2.2 后端注册实况（v6_app.py 源码 + 全库 rg）
```
v6_app 注册列表（_try_include 17 项）:
  api_gateway / api_sessions / api_trace / api_profile / api_objects / api_rules /
  api_relations / api_parameters / api_context / api_pipeline / api_metrics /
  api_persistence / api_meta / api_abc / api_mind / api_versions / api_subgraph
  + 固定: debug/chat/v3_session/pipeline/stubs + /v6/ws + /v6/audit

⚠️ api_viz_edit（/v6/edit/* 5 端点）不在注册列表!
  全库唯一引用: un_use/legacy_api.py:84
    from core.agent.v4.api_viz_edit import router...  ← v4 路径不存在（Test-Path=False）
  → 白盒编辑路由从未挂载，且其 import 目标已不存在
```

### 2.3 图编辑器接线
```
ConversationGraphPage（25.9KB）:
  useV6Graph → getGraph/getDiscourseTree/getObjects（读 ✅ 后端已注册）
  graphStore.setNodes/setEdges → ConversationGraph 渲染
  GraphEditPanel → editGraph/editDiscourseTree/editObjects（写 ❌ 后端 404）
GraphEditPanel（9.5KB）: 节点 state 编辑/边权重/增边，submitting 状态 → 提交失败静默
GraphToolbar（10KB）: 视图模式/筛选/搜索 → 纯前端
```

---

## 三、孤儿/死代码组件（全库引用扫描）

以下 13 个组件/hook/lib **全库仅自引用（0 外部引用）**:
```
components/ui/ThemeToggle.tsx / ClarificationPanel.tsx / ConnectionIndicator.tsx /
IntentTag.tsx / StatusBadge.tsx / StatusBar.tsx / TaskGraphView.tsx /
ThinkingBlock.tsx / ThinkingPanel.tsx / hooks/useMediaQuery.ts / hooks/useV6TaskWS.ts /
hooks/useWebSocket.ts / lib/animations.ts / lib/chatConnection.ts / lib/graph-utils.ts
（types/*.d.ts 3 个为类型声明，非死代码）
→ 约 12 个组件/hook/lib 未被任何页面/组件 import（设计中存在，UI 未接入）
```

> 注: useWebSocket.ts（13.5KB）与 lib/websocket.ts/websocketClient.ts/ws.ts 四套 WS
> 实现并存，仅 lib/websocketClient.ts 被实际使用（useChat 等）——多代演进同型（P-2）。

---

## 四、与设计文档的对应关系

| 设计文档 | 前端实现 | 状态 |
|---|---|---|
| DESIGN_FRONTEND（v3.0, React 18 栈）| 现实现 React 19 + Zustand | 已演进，架构文档 FRONTEND_ARCHITECTURE 更准 |
| FRONTEND_ARCHITECTURE（15 页）| 14 页全有（缺 GraphPage 内嵌）| 页面齐全 |
| FRONTEND_BUSINESS_FLOW | Gateway/Chat/Sessions 流程 | 与后端 Gateway 真接线（useV6Gateway 14.9KB）|
| DESIGN_GRAPH_EDITOR（统一图编辑）| GraphEditPanel + GraphToolbar 已实现 | **写路径断（后端 404）** |
| DESIGN_SVG_FLOWCHART | FlowchartCanvas（task/17.1KB）+ TaskFlow | 任务图真接线（ReactFlow+dagre）|
| FRONTEND_CLI_MAPPING | 14 页 × CLI 映射表 | 映射文档存在，未验证 CLI 对等命令 |
| DESIGN_FRONTEND_CLI_MAPPING | — | 设计已读（BATCH5）|

---

## 五、问题清单

| # | 级别 | 问题 | 证据 |
|---|---|---|---|
| FE-1 | P0 | 白盒编辑 API（/v6/edit/* 5 端点）后端未注册 → 图编辑/对话树编辑/对象编辑全部 404 | v6_app 列表无 api_viz_edit；唯一引用在 un_use + import 目标不存在 |
| FE-2 | P1 | 前端 12+ 组件/hook/lib 死代码（0 引用）| 全库引用扫描 |
| FE-3 | P1 | 四套 WebSocket 实现并存（useWebSocket/websocket/websocketClient/ws）| 引用矩阵 |
| FE-4 | P2 | 后端 stubs_api 为大量 /v6/* 提供 stub 响应——前端"读到数据"可能是假数据 | stubs 模式（白盒审计已提）|
| FE-5 | P2 | 前端页面接入状态多为"有 UI 需接管线"（FRONTEND_ARCHITECTURE 自述）| 架构文档 |
| FE-6 | P3 | GraphEditPanel 提交失败静默（无 404 提示）| 源码 |

---

## 六、与全局拍板池的关系

- **P-1 接线断裂** +1（最严重实例）: 前端实现了完整白盒编辑 UI，后端路由从未挂载——
  这是"组件齐备、接线断裂"的前端镜像（前后端两侧都齐，中间断）。
- **P-2 多代演进分裂** +1: 四套 WS 实现；api_viz_edit 与 legacy_api 引用已删除的
  v4 路径（演进后未清理）。
- **P-4 双路径分裂** 补充: 前端主路径（Browser→API）与 CLI 主路径并存，v6_app 是
  前端的唯一后端入口，但其覆盖度（17 注册路由）小于前端期望（42 端点 + 5 edit）。

