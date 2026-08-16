# DialogMesh UI 重构实施计划(在现有基础上渐进改,不重写)

> 2026-08-15 立项 · 依据:UI_DESIGN_DISCUSSION.md(方向 4 纸上工作室)、UI_DETAIL_GAP.md(P0–P1 细节清单)、RIGHT_SURFACE_MODEL.md(双槽位)、PROJECT_DIMENSION.md(项目组)
> 原则:**渐进修改现有代码**,每步 `tsc --noEmit` + `npm run build` + Playwright 截图验证;**本轮全部不动后端**;浅色模式(light.css / :root.light)同步维护。

## 0. 现状资产盘点(已核实)

| 资产 | 现状 | 结论 |
|---|---|---|
| Design tokens | `src/index.css` 已有双套(`:root` 暗 / `:root.light` 亮),Tailwind 映射 | 沿用其色值家族,只**增补**不发色 |
| 滚动条 | 已定制但常驻可见(6px,`--border-medium`) | 改 overlay 式(默认隐藏,hover 淡入) |
| Sidebar | `Sidebar.tsx` 平铺 13 项,lucide 图标,framer-motion,有 collapsed/mobile 态 | 分组改造 + 项目组插入 |
| 右栏 | `RightPanel.tsx` + `components/dock/`(已有 DockPicker!) | 先浮动卡片化,后改上下文工作台 |
| 双槽位 | 无,Layout 固定结构 | 需新建布局 store + 表面注册表 |
| 项目概念 | 前后端均无(GUI_API v10 已 grep 证实) | 前端-only 假数据起步 |

## 1. 分期路线

| 阶段 | 内容 | 改动面 | 状态 |
|---|---|---|---|
| P0-A | token 增补(hairline/radius/dock 底色)+ 滚动条 overlay 化 | index.css / light.css | ✅ 本轮完成 |
| P0-B | Sidebar 分组(主导航/项目/洞察/工程/系统)+ 双激活态区分 + 底部瘦身(悬浮/嵌入移走,Backend 状态点化) | Sidebar.tsx | ✅ 已完成(08-16, 截图 real_p0b_chat.png) |
| P0-C | 分隔重做:砍通长分割线,dock 改浮动卡片(栏间缝 + 圆角 14px);附带修掉 dock 双标题头(DockPanel 内层头移除) | SidePanel.tsx, RightDock.tsx, DockContents.tsx, Toolbar.tsx, tailwind.config.js(语义类), light.css(dock 例外) | ✅ 已完成(08-16, 截图 real_p0c_chat_{dark,light}.png) |
| P0-D | 去示范数据 + 比例调整:项目组空态/画像假数值(雷达 84/76…、指标卡 76/84/71、状态条 82%/18%)全部改诚实空态;空态判定看 oceAN_dims 本身(后端首用返回空对象,非全 50);MetricCards 趋势 ↑0 假精度隐藏;聊天列与输入条 max-w-3xl 居中,输入条改浮动圆角条;dock 默认宽 340→320 | Sidebar.tsx, MetricCards.tsx, StatusProgress.tsx, CognitiveRadarChart.tsx, DockContents.tsx, ChatPanel.tsx, ChatInput.tsx, uiStore.ts | ✅ 已完成(08-16, 截图 real_p0d_{chat_dark,chat_light,final_dark}.png) |
| P1-A | 双槽位骨架:layoutStore(配对记忆)+ 表面注册表(SURFACES/SURFACE_MAP/交换判定)+ 副槽切换器/交换⇄ + ChatSideSurface(副槽迷你对话, useChatSend 与主槽共享);顺带修正 auto 配对死映射(/task-planning→/tasks) | 新 lib/{layoutStore.ts,surfaceRegistry.tsx}, components/dock/ChatSideSurface.tsx, hooks/useChatSend.ts, RightDock/CenterDock/dockTabs/uiStore/ChatPage | ✅ 已完成(08-16, 截图 real_p1a_{switcher,chat_side,swapped}.png) |
| P1-B | 聊天页副槽 = 上下文工作台(本轮注入条:域分布/token 占比;记忆卡三态:正常/钉住/移除,本地状态+全部恢复;8s 静默轮询;/chat 默认配对改为 context) | 新 stores/contextWorkbenchStore.ts(指纹键+三态), DockContents.tsx(ContextDockContent 重写), surfaceRegistry.tsx(title+默认配对) | ✅ 已完成(08-16, 截图 real_p1b_{workbench,marks,empty}.png) |
| P1-C | 顶栏瘦身:搜索框 → ⌘K 触发器,画像监控降为状态点 | Toolbar.tsx 等 | 待做 |
| P2 | 项目组接数据:本地映射 session→project,切换过滤会话列表 | stores/, Sidebar.tsx, SessionsPage | 待做 |
| P3 | ⌘K 命令面板;会话列表人性化(标题摘要/相对时间) | 新组件, SessionsPage | 待做 |
| P4 | 浅色模式逐页验收;移动端抽屉化 | 全量 | 待做 |

## 2. 后端调整需求登记表(开发中持续追加,本轮不动后端)

| # | 需求 | 触发场景 | 前端临时方案 | 状态 |
|---|---|---|---|---|
| B1 | `project_id` 实体:session/task/graph-node 挂项目字段 | 项目组切换要真实过滤 | localStorage 映射表 session_id→project | 登记 |
| B2 | ContextCompiler 检索加 `project` 范围参数 | 项目 = 认知边界的核心价值 | 无(等 B1) | 登记 |
| B3 | 上下文钉住/移除接口(记忆片段级,作用于下轮编译) | 上下文工作台的记忆卡三态 | 本地状态,仅 UI 表达 | 登记 |
| B4 | 画像健康度聚合值(一个数)供顶栏状态点 | 监控数据撤出右栏后的归宿 | 复用现有画像端点取首值 | 登记 |
| B5 | 会话标题摘要 + 相对时间字段(替代裸 session id) | 会话列表人性化 | 前端截断 + 本地别名 | 登记 |
| B6 | 画像"成功状态/风险状态"指标数据源(原 StatusProgress 82%/18% 是纯装饰,从未接线;P0-D 起前端隐藏该卡) | 右栏画像/画像页要展示健康度与风险 | 组件无数据时显示空态,dock 内暂不渲染 | 登记 |
| B7 | 画像冷启动语义决策:`turn_count=0` 时 `/v6/profile` 返回的 `oceAN_dims` 是空对象(实测 08-16),不是全 0.5 基线 — 产品上要"空态"还是"全 50 基线起步"?若要基线,后端需在首用时返回基线值 | 首次使用的画像呈现(用户明确要求"默认正常即可") | 前端对空 dims 统一显示空态(hasDims 判定) | 待后端决策 |
| B8 | 槽位配对偏好持久化:配对记忆现存 localStorage(`dm_layout_pairing`),跨设备同步需用户偏好端点 | P1-A 副槽配对记忆 | localStorage | 登记 |
| B9 | 自动化视口配对协议(远期):UI 自动化时主槽=执行视口/副槽=对话,需要自动化运行时的视口状态流(截图帧/CDP 等),纯前端无法做 | 用户提出的"中间屏幕像虚拟机"场景 | 无 | 远期 |
| B10 | `/v6/context` 字段补全:① `total_tokens`/`budget` 未返回(注入条只能显示已用分布,无法显示预算水位);② 条目无稳定 ID(钉住/移除的本地键只能用内容指纹,条目内容微调后标记即失配) | P1-B 上下文工作台 | 前端用 estimated_tokens 求和代替总量;内容散列做会话内指纹键 | 登记 |

## 3. 风险与约束

1. **扩展模式**(`.extension-mode`,360px 宽浏览器插件壳)别破坏——Sidebar 改动要过一遍该模式
2. **MobileBottomNav** 保留;P4 才处理移动端深化
3. 不改路由路径,不删页面;任务页等"待决命运"页面保持原样直到拍板
4. 每步提交前:`npx tsc --noEmit -p tsconfig.app.json` + `npm run build` 全绿才算完
5. git:仓库有并行会话扫提交的先例,改动前确认分支与工作区状态

## 4. 变更日志

- 2026-08-15 P0-A 完成:index.css 增补 `--border-hairline` / `--r-card` / `--r-pill` / `--bg-dock` 四枚 token(双主题),滚动条改 overlay 式(默认隐藏,hover 出现,8px 全圆角)
- 2026-08-16 P0-B 完成:Sidebar 分组(主导航/项目/洞察/工程/系统)+ 双激活态区分 + 底部瘦身
- 2026-08-16 P0-C 完成:砍通长分割线,dock 改浮动卡片(栏间缝 + 圆角 14px),修掉 dock 双标题头
- 2026-08-16 P0-D 完成:去示范数据(项目组空态/画像假数值→诚实空态,hasDims 判定),聊天列 max-w-3xl 居中 + 输入条浮动圆角,dock 默认宽 340→320
- 2026-08-16 P1-A 完成:双槽位骨架落地 — 新建 `lib/surfaceRegistry.tsx`(表面注册表:label/title/icon/component/mainRoute,无 mainRoute 表面不可交换)、`lib/layoutStore.ts`(配对记忆 zustand,localStorage `dm_layout_pairing`)、`hooks/useChatSend.ts`、`components/dock/ChatSideSurface.tsx`(副槽迷你对话,共享 chatStore);改写 RightDock(切换器+交换⇄+联动/固定)/CenterDock/dockTabs/uiStore/ChatPage;修正旧 ROUTE_DOCK_MAP `/task-planning`→`/tasks` 死映射;登记 B8/B9;tsc+build 全绿,截图 real_p1a_{switcher,chat_side,swapped}.png
- 2026-08-16 P1-B 完成:上下文工作台 — ContextDockContent 重写(本轮注入条:域 token 占比分段条+图例+意图域;记忆卡三态:正常/钉住 amber 边+实心 Pin/移除 45% 透明+Undo2,汇总条+全部恢复;8s 静默轮询;保留 GAP-4 压缩反馈);新建 `stores/contextWorkbenchStore.ts`(djb2 内容指纹键,in-memory 不持久化);surfaceRegistry:/chat 默认配对 profile→context,标题改「上下文工作台」;登记 B10;tsc+build 全绿,截图 real_p1b_{workbench,marks,empty}.png
