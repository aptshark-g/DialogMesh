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
| P0-B | Sidebar 分组(主导航/项目/洞察/工程/系统)+ 双激活态区分 + 底部瘦身(悬浮/嵌入移走,Backend 状态点化) | Sidebar.tsx | 待做 |
| P0-C | 分隔重做:Layout/RightPanel 砍通长分割线,dock 改浮动卡片(栏间 12px 缝) | Layout.tsx, RightPanel.tsx, tailwind 语义类 | 待做 |
| P1-A | 双槽位骨架:布局 store(zustand)+ 表面注册表 + 副槽切换器/交换⇄/收起 | 新 lib/layoutStore.ts, Layout.tsx | 待做 |
| P1-B | 聊天页副槽 = 上下文工作台(本轮注入条 + 记忆卡三态,操作先本地状态) | RightPanel/dock 组件, ChatPage | 待做 |
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

## 3. 风险与约束

1. **扩展模式**(`.extension-mode`,360px 宽浏览器插件壳)别破坏——Sidebar 改动要过一遍该模式
2. **MobileBottomNav** 保留;P4 才处理移动端深化
3. 不改路由路径,不删页面;任务页等"待决命运"页面保持原样直到拍板
4. 每步提交前:`npx tsc --noEmit -p tsconfig.app.json` + `npm run build` 全绿才算完
5. git:仓库有并行会话扫提交的先例,改动前确认分支与工作区状态

## 4. 变更日志

- 2026-08-15 P0-A 完成:index.css 增补 `--border-hairline` / `--r-card` / `--r-pill` / `--bg-dock` 四枚 token(双主题),滚动条改 overlay 式(默认隐藏,hover 出现,8px 全圆角)
