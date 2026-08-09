# 未对应设计文档批量精读 · 批 5 — 前端 / 图编辑器

> 日期: 2026-08-03 | 批次: 5/8 | 状态: 已读完（6 文档）

---

## 1. DESIGN_FRONTEND.md（v3.0, 334 行）— 前端架构设计（v3.0）

**技术栈**: React 18 + TypeScript 5 + Vite 5 + Tailwind 3 + React Router 6 + React Context
+ Fetch + 原生 WebSocket + Lucide + Inter/Noto Sans SC。

**设计原则**: 低饱和暖色调（米白/暖灰/浅橙，避免蓝紫渐变）/ 清晰层次（whitespace + 卡片
微阴影）/ 技术术语不翻译（Cognitive Tree、Fusion Engine、SchemaGuard 保留英文）/
Unicode 数学符号（ℕ、→、≠）/ 响应式（桌面主目标 + 移动适配）。

**页面**: ChatPage（主）+ DashboardPage。API 对接: REST + WebSocket。状态: React Context
（全局 State）。关键交互: 创建会话→发送消息 / 澄清交互 / 重连逻辑。

---

## 2. FRONTEND_ARCHITECTURE.md（181 行）— v6 前端架构（现状快照）

**技术栈**: React 19.2 + TS + Vite 6 + Zustand + Tailwind + framer-motion + Recharts +
ForceGraph + @reactflow/core。体量: 24K 行 / 110+ 文件。

**15 页清单 + 接入状态**（关键）:
```
CognitiveProfile ✅ useV6Profile / Gateway ✅ useV6Gateway / Sessions ✅ useV6Sessions
Chat ⚠️ 有UI需接v6管线 / Dashboard ⚠️ 读API需数据 / Pipeline ⚠️ 需接ParameterRegistry
TaskPlanning ⚠️ 需接ExecutionPipeline / Engineering ⚠️ 需接ConstraintTree
MetaCenter ⚠️ 需接MetaTree / DeepChain ⚠️ 需接SpanTracer / Behavior ⚠️ 有UI
ConversationGraph ⚠️ 有UI / GraphPage(子图浏览器) ⚠️ 有UI
```

**核心组件**: TaskFlow（ReactFlow 执行流）/ PlanGate 审批 / Profile / Gateway / Graph 可视化。
12 Hooks + 10 Zustand Stores。附"后端 API 缺口"清单。

---

## 3. FRONTEND_BUSINESS_FLOW.md（189 行）— v6 前端业务流（Mermaid）

**全局启动流**: start.bat → Gateway(:8080 读 provider.yaml 注册 + auto-save) → API(:8000
读 runtime.yaml 初始化引擎 + 自动配置 LLM Provider→switch) → FE(:4173) → health 探测 +
gateway/providers 列表。

**Gateway 页面**: useV6Gateway 轮询 15s → API 在线则 GET /v6/gateway/providers，否则
DEFAULT_PROVIDERS 兜底 → 9 Provider 卡片 → API Key/Base URL 输入。

**六、前端 14 页 × 后端交互矩阵** + **八、当前功能完成度**——与 FRONTEND_ARCHITECTURE
接入状态一致（大部分"有 UI 需接管线"）。

---

## 4. DESIGN_FRONTEND_CLI_MAPPING.md（316 行）— 前端 ↔ CLI 对应设计

**原则**: 前端每个展示的数据 → CLI 有对应 read 命令；前端每次操作 → CLI 有对应 write 命令。

**架构**: 浏览器(5173) ↔ Backend(8000) ↔ engine singleton ↔ CLI(dm)。
read 方向: Backend v6 endpoints → 前端 page → 展示；write 方向: 前端操作 → POST/PUT →
引擎 → 磁盘持久化；CLI 调试: dm <module> show → 同 Backend 数据源。

**14 页 × CLI 映射示例**: DashboardPage（session list / engine status / metrics show /
intent parse / discourse search）；ChatPage（核心）等。附 v6 API 端点 → CLI 映射表 +
当前实现状态（✅ 双通 / ⚠️ 数据有但未连线）。

---

## 5. DESIGN_GRAPH_EDITOR.md（223 行）— 交互式图编辑 & 子图上下文

**核心思想**: "图的编辑能力不是功能点，是用户对 LLM 上下文的控制权。一处设计，四处复用:
DiscourseTree / KnowledgeGraph / Subgraph / PersistentGraph。"

**架构**: 用户（对话树图/知识对象图/子图编辑器）→ 统一 GraphEditor（右键/拖拽/双击/框选）
→ 后端 Graph CRUD API（node/add / edge/add / subgraph/compile）→ SubgraphCompiler +
ContextAssembler → LLM prompt。

**子图（用户控制 LLM 上下文）**: 子图是关键——用户通过编辑子图直接控制 LLM 输入窗口；
子图持久化 + 复用场景。CLI 对等命令"全部已有"。

**冲突登记（暂不裁决）**: 与 api/api_viz_edit.py（白盒编辑 API，对话树审计已核）——本文档
是编辑交互的设计源，api_viz_edit 是后端实现；与子图审计（用户可编辑子图 → 上下文控制权）
方向一致 → 归并对话树/子图/白盒化（A19）讨论。

---

## 6. DESIGN_SVG_FLOWCHART.md（155 行）— SVG 流程图编辑器交互

**目标**: WPS 流程图级交互体验（对标 Figma/WPS）。节点操作（拖拽/缩放 Vivo 原子组件风格/
选中态/双击编辑）；连线操作（4 连接点 Handle / 自动路由 A* 避障默认 / 手动路由 PS 钢笔
风格 / 连线状态色 pending灰 running蓝 completed绿 failed红）；画布小工具栏；快捷键。

**冲突登记（暂不裁决）**: 与 DESIGN_GRAPH_EDITOR 是同一编辑器家族的两份设计（流程图 vs
知识图）→ 前端图编辑统一交互规范待整合。

---

## 批 5 汇总（冲突登记清单）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B5-1 | 前端 15 页大部分"有 UI 需接管线"（与后端断线）| FRONTEND_ARCHITECTURE vs 各模块审计 |
| B5-2 | 图编辑三份设计（GRAPH_EDITOR / SVG_FLOWCHART / api_viz_edit）归一 | 批 5 vs 对话树/子图审计 |
| B5-3 | 子图编辑=用户上下文控制权 vs 子图审计（A/B 路径）| GRAPH_EDITOR vs 子图审计 |
| B5-4 | 前端↔CLI 双通道 vs CLI 目标态（批 4）| FRONTEND_CLI_MAPPING vs 批 4 |

