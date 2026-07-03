# DialogMesh v3.0 — 前端 GUI 最终设计规范

**版本**: 3.0.0-final  
**日期**: 2026-07-03  
**设计基准**: 暗色模式优先，基于最终 UI 原型（聊天主界面、对话树图谱、任务规划 DAG）
**设计哲学**: 低饱和度暖色调、深邃暗色模式、清晰信息层次、可视化即认知、动画克制且有意义。

---

## 1. 设计概述

### 1.1 产品愿景
DialogMesh 是一个面向对话 AI 的**外置认知系统**。它不只是"聊天"——它是你对话过程的认知外挂。你可以像 Obsidian 一样看到整个对话的图谱结构，像仪表盘一样监控认知画像的演化，像思维导图一样审视任务规划的全貌。

### 1.2 核心原则

1. **信息密度与呼吸感并存** — 高密度的可视化需要足够的留白来平衡
2. **暗色模式优先** — 长时间使用的工具，暗色模式更护眼。亮色模式后续提供，但暗色为默认
3. **可视化即认知** — 所有数据都应通过合适的图形化表达，不要隐藏
4. **动画服务理解** — 每个动画都有语义目的（加载 = 思考、浮现 = 新增、抖动 = 错误）
5. **外挂友好** — 插件架构设计，让 DialogMesh 可以挂载到 ChatGPT、Claude、Kimi 等任意 AI 上

### 1.3 目标用户
- 技术研究者（用对话管理实验）
- 内容创作者（需要跟踪长篇对话的上下文）
- 开发者（需要调试 AI 的推理过程）

---

## 2. 设计系统（Design System）

### 2.1 颜色体系

#### 基础色板

```css
/* === 品牌色 === */
--color-amber: #D97706;           /* 主色：琥珀橙 — 用于选中态、边框、按钮、雷达图 */
--color-amber-light: #F59E0B;     /* 亮色：亮琥珀 — 用于指标数字、高亮、雷达图顶点 */
--color-amber-dark: #B45309;      /* 暗色：深琥珀 — 用于 hover 状态 */
--color-amber-subtle: rgba(217, 119, 6, 0.10); /* 背景强调：意图标签背景、徽章背景 */

/* === 辅助色 === */
--color-teal: #0D9488;            /* 辅助色：teal 绿 — READ_MEMORY 意图 */
--color-rose: #E11D48;            /* 强调色：玫瑰红 — HACK_VALUE 意图、失败状态 */
--color-slate: #64748B;           /* 中性色：石板灰 — 次要图标 */
--color-emerald: #10B981;         /* 成功色：翡翠绿 — 已完成、成功状态 */
--color-blue: #3B82F6;            /* 信息色：蓝色 — 信息提示 */

/* === 暗色模式（Dark Mode — 默认）=== */
--bg-surface: #0C0A0F;            /* 主背景：深邃紫黑 — 页面最底层 */
--bg-sidebar: #121018;              /* 侧边栏：稍浅紫黑 — 导航区域 */
--bg-card: #1A1724;               /* 卡片背景：深紫灰 — 面板、消息卡片、气泡 */
--bg-card-hover: #252134;          /* 卡片悬停：更亮紫灰 — hover 状态 */
--bg-card-active: #312E40;         /* 卡片激活：最亮紫灰 — 选中状态 */
--bg-input: #1A1724;              /* 输入框背景 */
--bg-overlay: rgba(0, 0, 0, 0.6);   /* 遮罩：模态框、抽屉 */

--text-primary: #E8E6F0;           /* 主要文字：暖白 — 标题、重要内容 */
--text-secondary: #A9A5B8;         /* 次要文字：淡紫灰 — 正文、描述 */
--text-muted: #6B6680;            /* 弱化文字：暗紫灰 — 时间戳、标签、占位符 */
--text-ai: #F59E0B;                /* AI 文字色：亮琥珀 — AI 消息、强调文字 */
--text-on-primary: #FFFFFF;         /* 主色上的文字：纯白 */

--border-subtle: #2A2635;          /* 微弱边框：分割线、输入框边框 */
--border-medium: #3A3548;          /* 中等边框：卡片边框、节点边框 */
--border-strong: #4A4560;         /* 强边框：选中边框、hover 边框 */

/* === 状态色 === */
--status-success: #10B981;          /* 已完成 / 成功 */
--status-warning: #F59E0B;          /* 执行中 / 警告 */
--status-error: #EF4444;            /* 失败 / 错误 */
--status-info: #3B82F6;             /* 信息 / 提示 */
--status-pending: #6B6680;         /* 待执行 / 等待 */

/* === 意图类型色（用于图谱节点、标签）=== */
--intent-scan-memory: #D97706;     /* SCAN_MEMORY: 琥珀 */
--intent-read-memory: #0D9488;     /* READ_MEMORY: 青色 */
--intent-write-memory: #8B5CF6;    /* WRITE_MEMORY: 紫色 */
--intent-hack-value: #E11D48;      /* HACK_VALUE: 玫瑰 */
--intent-explain: #3B82F6;         /* EXPLAIN: 蓝色 */
--intent-provide-code: #10B981;    /* PROVIDE_CODE: 绿色 */
--intent-unknown: #6B6680;         /* UNKNOWN: 灰色 */
```

**设计说明**：
- 暗色模式的背景色是深紫黑色（`#0C0A0F`），不是纯黑。纯黑在暗色下太刺眼，深紫黑更柔和。
- 琥珀色（`#D97706`）作为品牌色，在暗色模式下用于边框、选中态、按钮，文字高亮用更亮的 `#F59E0B`。
- 所有颜色使用 CSS 变量 + Tailwind 的 `dark:` 前缀实现。亮色模式后续开发，优先级较低。

#### 背景层级（从外到内）

```
页面背景: #0C0A0F
  └─ 侧边栏: #121018
  └─ 卡片/面板: #1A1724
      └─ 卡片 hover: #252134
      └─ 卡片 active: #312E40
      └─ 输入框: #1A1724
```

### 2.2 字体排版

```css
/* === 字体栈 === */
--font-sans: 'Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;

/* === 字号体系（基于 UI 原型）=== */
--text-xs:  12px;  --line-xs:  16px;   /* 标签、徽章、时间戳 */
--text-sm:  14px;  --line-sm:  20px;   /* 次要内容、导航项、状态说明 */
--text-base: 15px; --line-base: 22px;  /* 正文（比标准 16px 稍小，更紧凑）*/
--text-lg:  16px;  --line-lg:  24px;   /* 小标题 */
--text-xl:  18px;  --line-xl:  28px;   /* 区块标题 */
--text-2xl: 20px;  --line-2xl: 30px;   /* 页面标题 */
--text-3xl: 28px;  --line-3xl: 36px;   /* 指标大数字 */
--text-4xl: 36px;  --line-4xl: 44px;   /* 展示数字 */

/* === 字重 === */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

**排版规则**：
- 页面标题：`text-2xl` + `font-semibold` + `text-primary`（如"会话洞察"）
- 区块标题：`text-xl` + `font-semibold` + `text-primary`（如"认知画像"）
- 正文：`text-base` + `font-normal` + `text-secondary`
- 时间戳/标签：`text-xs` + `text-muted`
- 指标大数字：`text-3xl` + `font-bold` + `color-amber-light`（如"76"、"84"）
- 代码块：`font-mono` + `text-sm` + 深色背景

### 2.3 间距体系

```css
/* === 间距 Token（Tailwind 兼容）=== */
--space-1: 4px;    --space-2: 8px;     --space-3: 12px;
--space-4: 16px;   --space-5: 20px;    --space-6: 24px;
--space-8: 32px;   --space-10: 40px;   --space-12: 48px;

/* === 圆角体系 === */
--radius-sm: 4px;    /* 小元素：意图标签、徽章 */
--radius-md: 8px;    /* 中等：卡片、按钮、输入框 */
--radius-lg: 12px;   /* 大元素：面板、消息气泡 */
--radius-xl: 16px;   /* 超大：模态框 */
--radius-full: 9999px; /* 完全圆：头像、圆形按钮 */
```

**布局规则（基于 UI 原型）**：
- 页面布局：Sidebar 240px + 中间内容区（flex-1）+ 右侧面板 340px
- 卡片内边距：`p-5`（20px）或 `px-5 py-4`（20px 水平 / 16px 垂直）
- 卡片间距：`gap-4`（16px）
- 元素间距：`gap-2`（8px）或 `gap-3`（12px）
- 消息气泡间距：`gap-4`（16px）
- 消息内边距：`px-5 py-4`（20px 水平 / 16px 垂直）

### 2.4 阴影与层级

```css
/* === 阴影（暗色模式下阴影使用透明度）=== */
--shadow-card: 0 1px 3px rgba(0, 0, 0, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2);
--shadow-card-hover: 0 4px 12px rgba(0, 0, 0, 0.4), 0 2px 4px rgba(0, 0, 0, 0.3);
--shadow-modal: 0 24px 48px rgba(0, 0, 0, 0.5), 0 12px 24px rgba(0, 0, 0, 0.4);
--shadow-amber: 0 0 12px rgba(217, 119, 6, 0.3);  /* 琥珀色发光：执行中节点 */

/* === 层级（z-index）=== */
--z-base: 0;
--z-dropdown: 100;
--z-sticky: 200;
--z-drawer: 300;
--z-modal: 400;
--z-toast: 500;
--z-tooltip: 600;
```

### 2.5 动画体系

```css
/* === 缓动函数 === */
--ease-out: cubic-bezier(0, 0, 0.2, 1);              /* 减速进入 */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);  /* 弹性回弹 */
--ease-smooth: cubic-bezier(0.25, 0.1, 0.25, 1);   /* 平滑 */

/* === 动画时长 === */
--duration-fast: 150ms;    /* 微交互：hover、按钮点击 */
--duration-normal: 250ms;   /* 标准过渡：面板展开、开关 */
--duration-slow: 400ms;     /* 重要过渡：页面切换、消息入场 */
--duration-slower: 600ms;   /* 展示动画：图表节点入场 */

/* === 预设动画 keyframes === */
/* 消息入场（从下方滑入）*/
@keyframes message-enter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
/* 卡片浮现 */
@keyframes card-appear {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}
/* 思考脉冲（三个圆点）*/
@keyframes thinking-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}
/* 执行中脉冲（节点高亮）*/
@keyframes executing-pulse {
  0%, 100% { box-shadow: 0 0 0px rgba(217, 119, 6, 0); border-color: #D97706; }
  50% { box-shadow: 0 0 12px rgba(217, 119, 6, 0.4); border-color: #F59E0B; }
}
/* 节点入场（图谱）*/
@keyframes node-fade-in {
  from { opacity: 0; transform: scale(0); }
  to { opacity: 1; transform: scale(1); }
}
/* 边展开动画 */
@keyframes edge-grow {
  from { stroke-dashoffset: 1000; }
  to { stroke-dashoffset: 0; }
}
/* 骨架屏 shimmer */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

**动画规则**：
- 消息入场：`animate-[message-enter_400ms_ease-out]`，每轮消息延迟 50ms
- 卡片浮现：`animate-[card-appear_300ms_ease-spring]`
- 思考状态：3 个圆点依次脉冲，间隔 200ms，颜色 `#D97706`
- 执行中节点：持续脉冲动画，琥珀色阴影
- 图谱节点：力导向布局时，新节点入场 `node-fade-in`，600ms
- 新增边：`stroke-dashoffset` 动画，从源节点"画"到目标节点，600ms

---

## 3. 页面布局设计

### 3.1 整体布局架构（基于图1）

```
┌────────────────────────────────────────────────────────────┐
│  Sidebar (240px)  │  Main Content (flex-1)  │  Right Panel (340px) │
│  ───────────────  │  ─────────────────────  │  ──────────────────  │
│  ┌───────────┐  │  ┌───────────────────┐  │  ┌──────────────┐  │
│  │ Logo      │  │  │  Toolbar (48px)   │  │  │ 认知画像     │  │
│  ├───────────┤  │  ├───────────────────┤  │  │  雷达图      │  │
│  │ Navigation│  │  │                   │  │  ├──────────────┤  │
│  │ - Chat    │  │  │  Content Area     │  │  │ 指标卡片     │  │
│  │ - 图谱    │  │  │  ───────────────  │  │  ├──────────────┤  │
│  │ - 画像    │  │  │  Messages...      │  │  │ 状态监测     │  │
│  │ - 任务    │  │  │  ───────────────  │  │  └──────────────┘  │
│  │ - 设置    │  │  │  Input Area       │  │                    │
│  ├───────────┤  │  └───────────────────┘  │                    │
│  │ 最近会话  │  │                         │                    │
│  │ 列表      │  │                         │                    │
│  └───────────┘  └─────────────────────────┘                    │
└────────────────────────────────────────────────────────────────────┘
```

**布局说明**：
- 左侧 Sidebar 固定宽度 240px（桌面端），移动端折叠为抽屉
- 中间 Main Content 自适应剩余宽度（flex-1）
- 右侧认知面板固定宽度 340px（桌面端），可折叠（点击 ← 按钮）
- 所有页面共享这个布局骨架，但全屏视图（图谱、任务规划）时右侧面板隐藏
- 整体最小宽度：1024px（低于此宽度时提示"请使用更大屏幕"）

### 3.2 侧边栏（Sidebar）

**结构**：
```
┌──────────────────┐
│ 🔶 DialogMesh    │  ← 40px 高，琥珀色图标 + "DialogMesh" 文字 + "v3.0" 版本号
│    v3.0          │
├──────────────────┤
│ 图标  聊天       │  ← 导航项，激活时左侧 3px 琥珀色竖线 + 背景高亮
│ 图标  图谱       │
│ 图标  画像       │
│ 图标  任务       │
│ 图标  设置       │
├──────────────────┤
│ 最近会话  +新建  │  ← 标题栏 + 新建按钮
│  ┌────────────┐  │
│  │头像 标题   │  ← 会话列表项：头像（32px）+ 标题（截断16字）+ 时间
│  │    时间    │  ← 激活会话：左侧琥珀色竖线 + 背景 #1A1724
│  └────────────┘  │
│  ...             │
│  ▼ 查看全部会话  │
└──────────────────┘
```

**样式**：
- 背景：`bg-sidebar`（`#121018`）
- 宽度：240px，无边框，右侧与主内容区自然分隔（通过背景色差异）
- 导航项：高度 40px，圆角 `radius-md`（8px），左侧内边距 12px
  - 默认：文字 `text-secondary`（`#A9A5B8`），图标 18px
  - Hover：`bg-card-hover`（`#252134`），文字 `text-primary`（`#E8E6F0`）
  - 激活：左侧 3px 琥珀色竖线（`#D97706`），背景 `bg-card`（`#1A1724`），文字 `text-primary` + `font-medium`
- 最近会话列表：
  - 头像：32px 圆形，与标题间距 12px
  - 标题：`text-sm` + `font-medium` + `text-primary`，单行截断
  - 时间：`text-xs` + `text-muted`（右侧对齐）
  - 激活项：左侧 3px 琥珀色竖线，背景 `bg-card`
- 新建按钮：右侧悬浮，圆形 24px，琥珀色图标

### 3.3 顶部工具栏（Toolbar）

**结构**：
```
┌────────────────────────────────────────────┐
│ 会话标题 ▼    │ 搜索框        │ 主题 │ 设置 │ 更多 │
│ 如何构建长期记忆机制          🔍 搜索消息  🌙  ⚙️  ⋮  │
└────────────────────────────────────────────┘
```

**样式**：
- 高度：48px，背景与主内容区一致（`#0C0A0F`）
- 左侧：会话标题（`text-lg` + `font-semibold`）+ 下拉箭头（表示可切换会话）
- 中间：搜索框（圆角 `radius-md`，背景 `bg-card`，占位符"搜索消息"）
- 右侧：图标按钮组（主题切换 🌙、设置 ⚙️、更多 ⋮），每个 36px 圆形，hover 时 `bg-card-hover`
- 底部：1px 分隔线（`border-subtle` `#2A2635`）

### 3.4 右侧认知面板（Right Panel）

**结构**：
```
┌────────────────────────┐
│ 认知画像 🛈             │  ← 标题 + 信息图标（tooltip）
├────────────────────────┤
│ 认知能力雷达            │  ← 小标题
│      ┌────────┐       │
│     ╱  元认知  ╲      │  ← 5 维度雷达图（元认知/推理深度/置信度/稳定性/发散度）
│    │  置信度    │      │  ← 琥珀色填充（rgba(217,119,6,0.15)），顶点 `#F59E0B`
│     ╲  稳定性 ╱       │  ← 网格线 `#3A3548`
│        发散度         │  ← 维度标签 `text-xs` + `text-muted`
├────────────────────────┤
│  76  │  84  │  71      │  ← 三指标大数字（推理深度/元认知/表达清晰度）
│ 推理深度 元认知 表达清晰度│  ← 标签 `text-xs` + `text-muted`
│  ↑8   ↑6   ↑5          │  ← 趋势箭头（绿色表示上升）
├────────────────────────┤
│ 状态监测                │  ← 小标题
│ 🛡 成功状态    82%      │  ← 进度条（琥珀色，80%）+ 百分比 + 说明文字
│ 任务完成度高，推理路径稳定 │
│ ⚠ 风险状态    18%        │  ← 进度条（红色，20%）+ 百分比 + 说明文字
│ 存在知识不确定性，建议验证 │
├────────────────────────┤
│ 数据更新于 14:32:18 ↻  │  ← 底部时间戳 + 刷新按钮
└────────────────────────┘
```

**样式**：
- 宽度：340px，背景 `#0C0A0F`（与页面背景一致），左侧 1px 分隔线（`border-subtle`）
- 内边距：`p-5`（20px）
- 卡片间距：`gap-5`（20px）
- 每个区块：无显式边框，通过背景色差异自然分隔
- 可折叠：右上角 ← 按钮，折叠后面板隐藏，中间内容区扩展

---

## 4. 核心页面设计

### 4.1 聊天页面（ChatPage）—— 主界面

**布局（基于图1）**：

```
┌────────────────────────────────────────────────────────────┐
│ Toolbar: 会话标题 + 搜索框 + 主题切换 + 设置 + 更多       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────┐  ┌────────────────┐  │
│  │  聊天区域（主）                   │  │ 认知画像面板   │  │
│  │  ─────────────────────────────   │  │  ────────────  │  │
│  │  ┌────────────────────────────┐  │  │  雷达图        │  │
│  │  │ 如何让agent具备长期记忆能力？│  │  │  ──────────  │  │
│  │  │ 14:30  [用户头像]           │  │  │  三指标卡片    │  │
│  │  └────────────────────────────┘  │  │  ──────────  │  │
│  │  [AI头像]  ┌──────────────────┐  │  │  状态监测      │  │
│  │  │ 🔶      │ 要让Agent具备长期记忆能力... │  │  └────────────────┘  │
│  │  │         │ 1. 记忆分层...             │  │                    │
│  │  │         │ 2. 向量化存储...           │  │                    │
│  │  │         │ 3. 检索增强...             │  │                    │
│  │  │         │ 意图 SCAN_MEMORY EXPLAIN  │  │                    │
│  │  │         │ 14:30  [复制] [赞] [踩]   │  │                    │
│  │  └─────────┴──────────────────┘  │                    │
│  │  ┌────────────────────────────┐  │                    │
│  │  │ 能否给一个简单的代码示例？   │  │                    │
│  │  │ 14:31  [用户头像]           │  │                    │
│  │  └────────────────────────────┘  │                    │
│  │  [AI头像]  ┌──────────────────┐  │                    │
│  │  │ 🔶      │ 当然可以...       │  │                    │
│  │  │         │ ```python         │  │                    │
│  │  │         │ from vectorstore...│  │                    │
│  │  │         │ ```               │  │                    │
│  │  │         │ 意图 PROVIDE_CODE EXAMPLE│  │                    │
│  │  │         │ 14:31  [复制] [赞] [踩]   │  │                    │
│  │  └─────────┴──────────────────┘  │                    │
│  │                                  │                    │
│  │  ┌─ Input Area ─────────────────┐│                    │
│  │  │ 输入消息...                   ││                    │
│  │  │ [附件] [代码] [@] [图片] [网格]││                    │
│  │  │                              [发送]│                │
│  │  └──────────────────────────────┘│                    │
│  └──────────────────────────────────┘                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**用户消息气泡**：
- 右对齐，最大宽度 70%
- 背景：`bg-card`（`#1A1724`）
- 左边框：3px 琥珀色竖线（`#D97706`）
- 圆角：`12px 12px 12px 4px`（左下小圆角，形成指向用户的箭头感）
- 内边距：`px-5 py-4`（20px 水平 / 16px 垂直）
- 文字：`text-base` + `text-primary`（`#E8E6F0`）
- 下方：时间戳（`text-xs` + `text-muted`）+ 用户头像（32px 圆形，右侧）

**AI 消息气泡**：
- 左对齐，最大宽度 80%
- 无背景色（或极淡的 `bg-card`），靠左一条 3px 琥珀色竖线
- 圆角：`4px 12px 12px 12px`（左上小圆角）
- 内边距：`px-5 py-4`
- 文字：`text-base` + `text-secondary`（`#A9A5B8`）
- AI 头像：左侧 32px 圆形，DialogMesh logo（🔶）
- 列表项：有序列表（1. 2. 3.），数字琥珀色，内容 `text-secondary`
- 代码块：深色背景（`#0C0A0F`），圆角 `radius-md`，边框 `border-subtle`，字体 `font-mono`，右上角显示语言标签（"python"）+ 复制按钮
- 意图标签：消息下方小徽章，圆角 `radius-sm`（4px），背景 `color-amber-subtle`，文字 `color-amber`，如 `SCAN_MEMORY`、`EXPLAIN`、`PROVIDE_CODE`
- 操作按钮：时间戳右侧，复制、赞、踩图标（24px，hover 时 `text-primary`）

**输入区域（Input Area）**：
- 固定在底部，背景 `bg-card`（`#1A1724`），圆角 `radius-lg`（12px）
- 多行文本框：最小 1 行，最大 6 行，auto-resize
- 占位符：`text-muted`（"输入消息... (Shift + Enter 换行, Enter 发送)"）
- 底部工具栏：附件 📎、代码 `</>`、@、图片 🖼、网格 🔲 图标（20px，`text-muted`，hover 时 `text-secondary`）
- 发送按钮：右侧圆形，48px，琥珀色背景（`#D97706`），白色纸飞机图标，hover 时放大 1.05x + 阴影加深
- 快捷键：Enter 发送，Shift+Enter 换行

**消息状态指示**：
- 发送中：消息气泡右侧显示旋转加载器（18px，琥珀色）
- 已发送：无额外指示（成功后即显示 AI 回复）
- 流式输出：AI 消息逐字显示，光标为竖线（`|`，`#D97706`，0.5s 闪烁动画）
- 错误：消息气泡变红（左边框红色 `#EF4444`），显示错误图标 + 重试按钮

### 4.2 对话树图谱页面（ConversationGraphPage）—— 基于图2

**核心概念**：像 Obsidian 一样，以力导向图的形式展示所有对话 session 的关系。每个节点是一轮对话，边是上下文继承关系。

**布局**：
```
┌────────────────────────────────────────────────────────────────┐
│ 🔶 DialogMesh v3.0  │  对话树图谱                               │
├────────────────────────────────────────────────────────────────┤
│ Toolbar:                                                      │
│ [🔍 搜索节点内容...] [✓ SCAN_MEMORY] [✓ READ_MEMORY] [✓ HACK_VALUE] [✓ UNKNOWN] │
│ 视图模式: [力导向] [时间线] [树形]       - 81% +  [全屏]        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│    ┌──────────┐              ┌──────────┐                  │
│    │ 存储设计  │──branch──→   │ 记忆冲突  │                  │
│    │ 需要考... │  (琥珀)     │ 解决相关  │                  │
│    └────┬─────┘              └────┬─────┘                  │
│         │                          │                         │
│    ┌────┴─────┐              ┌────┴─────┐                  │
│    │ 如何设计  │              │ 短期记忆  │                  │
│    │ 记忆存储..│              │ 用于当前..│                  │
│    └────┬─────┘              └────┬─────┘                  │
│         │                          │                         │
│    ┌────┴─────┐              ┌────┴─────┐                  │
│    │  ◯◯◯    │              │  ◯◯◯    │  ← 簇节点(虚线)   │
│    │ 冲突解决 │              │ 记忆类型 │                  │
│    │ 相关(18) │              │ 对比(12) │                  │
│    └──────────┘              └──────────┘                  │
│                                                                │
│  [左下角] 迷你地图 + 缩放控制(+/-)  [右下角] 图例(意图类型)      │
│  [底部]  节点总数: 292  显示节点: 292  选中节点: 0  更新时间: ..  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**节点设计**：
- **用户节点**：圆形，白色边框（`#E8E6F0`，1.5px），背景透明，直径 40-60px
  - 文字：节点内部显示用户输入前 10 字，`text-xs` + `text-primary`，居中
  - 悬停：放大 1.1x，tooltip 显示完整消息（深色背景，最大宽度 300px，多行）
- **AI 节点**：圆角矩形，圆角 8px，意图色边框（1.5px），宽度 120-160px，高度自适应
  - 边框颜色：按意图类型（SCAN_MEMORY=琥珀 `#D97706`、READ_MEMORY=青色 `#0D9488`、HACK_VALUE=玫瑰 `#E11D48`、UNKNOWN=灰色 `#6B6680`）
  - 文字：AI 回复摘要前 15 字，`text-xs` + `text-secondary`
  - 背景：透明或极淡的意图色（`rgba(217,119,6,0.05)`）
- **簇节点**：虚线圆圈（`stroke-dasharray: 4 4`），边框 `#6B6680`，直径 60px
  - 文字：聚合名称 + 数量，如"冲突解决相关 (18)"，`text-xs` + `text-muted`
  - 点击：展开为子节点，动画 400ms
- **节点大小**：根据消息长度动态缩放（最小 40px，最大 100px）
- **节点入场**：新节点从中心点放大浮现（`node-fade-in`，600ms，ease-spring）

**边设计**：
- 带箭头的贝塞尔曲线，颜色 `#3A3548`（`border-medium`），线宽 1.5px
- 方向：从用户输入指向 AI 响应，或从 AI 响应指向下一轮用户输入
- 新增边动画：从一端"画"到另一端（`stroke-dashoffset` 动画，600ms，ease-out）
- 悬停：线宽变为 2.5px，颜色变为琥珀色（`#D97706`），显示连接关系 tooltip

**工具栏**：
- 搜索框：左侧，圆角 `radius-md`，背景 `bg-card`，占位符"搜索节点内容..."
- 意图过滤器：复选框组，每个意图类型带颜色圆点 + 文字标签 + 数量
- 视图模式： segmented control（力导向/时间线/树形），选中项琥珀色背景
- 缩放控制：- / 百分比 / + / 全屏按钮

**迷你地图**：左下角，80x80px，显示整个图的缩略图，当前视图用矩形框标记（琥珀色边框）

**图例**：右下角，显示意图类型颜色对照 + 各类型节点数量

**状态栏**：底部，显示节点总数 / 显示节点 / 选中节点 / 数据更新时间 + 刷新按钮

**交互**：
- 拖拽：节点可拖拽，力导向图实时更新位置
- 缩放：滚轮缩放，范围 0.1x ~ 3x，支持触摸板双指缩放
- 平移：拖拽空白区域平移画布
- 点击：点击节点跳转到该对话轮次的聊天页面，高亮该消息
- 双击：双击簇节点展开聚合
- 搜索：匹配的节点高亮发光（琥珀色阴影），其他节点半透明（opacity 0.2）

### 4.3 任务规划页面（TaskPlanningPage）—— 基于图3

**核心概念**：以 DAG（有向无环图）的形式展示 AI 的任务规划过程。用户可以像看思维导图一样看到任务执行的完整路径，包括条件分支。

**布局**：
```
┌────────────────────────────────────────────────────────────────┐
│ 🔶 DialogMesh v3.0  │  任务规划  │  长期记忆检索与更新任务        │
│ 任务ID: task_20250516_001                       [▶ 播放] [⏸ 暂停] [↺ 重置] │
├────────────────────────────────────────────────────────────────┤
│ 总任务: 18 │ 已完成: 7 │ 执行中: 2 │ 待执行: 8 │ 失败: 1      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────┐     ┌──────────────────┐                        │
│  │ 全局记忆  │←────│ 执行向量检索      │  ← 执行中（琥珀高亮）    │
│  │ 扫描      │     │ 在向量库中检索...  │     执行中              │
│  └──────────┘     └────────┬─────────┘                        │
│                             │                                  │
│                   ┌─────────┴─────────┐                      │
│              if found > 0        if found = 0                 │
│                   ↓                     ↓                      │
│         ┌──────────┐          ┌──────────┐                  │
│         │ 结果去重   │          │ 扩展检索  │                  │
│         │ 与排序     │          │ 策略      │                  │
│         │ 已完成(绿) │          │ 待执行(灰)│                  │
│         └────┬─────┘          └────┬─────┘                  │
│              │                      │                        │
│         ┌────┴─────┐          ┌────┴─────┐                  │
│         │ 记忆内容   │          │ 检查记忆  │                  │
│         │ 验证       │          │ 权限      │                  │
│         │ 已完成(绿) │          │ 待执行(灰)│                  │
│         └────┬─────┘          └────┬─────┘                  │
│              │                      │                        │
│         ┌────┴─────┐          ┌────┴─────┐                  │
│         │ 验证是否  │          │ 权限是否  │                  │
│         │ 通过?     │          │ 充足?     │                  │
│         └────┬─────┘          └────┬─────┘                  │
│        if pass    if not pass        │  if yes    if no       │
│              │                      │                        │
│    ┌─────────┐  ┌──────────┐   ┌──────────┐                  │
│    │ 整合记忆 │  │ 触发人工 │   │ 权限提升 │  ← 失败（红色）     │
│    │ 片段     │  │ 审核     │   │ 请求     │                     │
│    │ 执行中   │  │ 失败     │   │ 失败     │                     │
│    └────┬─────┘  └──────────┘   └──────────┘                     │
│         │                                                        │
│    ┌────┴─────┐                                                  │
│    │ 更新长期  │                                                  │
│    │ 记忆库    │                                                  │
│    │ 待执行    │                                                  │
│    └────┬─────┘                                                  │
│         │                                                        │
│    ┌────┴─────┐     ┌──────────┐     ┌──────────┐               │
│    │ 生成回复  │────→│ 结束     │    │          │               │
│    │ 待执行    │     │ 任务完成  │    │          │               │
│    └──────────┘     └──────────┘    │          │               │
│                                     │          │               │
│ [右下角] 迷你地图                   │          │               │
│ [右侧]  任务详情面板（可折叠）       │          │               │
└────────────────────────────────────────────────────────────────┘
```

**节点设计**：
- 圆角矩形（8px 圆角），内边距 `px-4 py-3`（16px 水平 / 12px 垂直）
- 节点类型：
  - **开始/结束**：标准圆角矩形，无特殊图标
  - **理解/执行**：左侧图标（理解=🧠、执行=⚡），图标与文字间距 8px
  - **判断**：菱形（CSS 旋转 45° 或 SVG），条件文字在菱形内部或下方
- 节点状态（边框颜色 + 背景 + 动画）：
  - **待执行**：边框 `#6B6680`（灰色），背景透明，文字 `text-muted`
  - **执行中**：边框 `#D97706`（琥珀），背景 `rgba(217,119,6,0.05)`，文字 `text-primary`，**持续脉冲动画**（`executing-pulse`）
  - **已完成**：边框 `#10B981`（绿色），背景 `rgba(16,185,129,0.05)`，文字 `text-secondary`
  - **失败**：边框 `#EF4444`（红色），背景 `rgba(239,68,68,0.05)`，文字 `text-secondary`
- 危险操作节点：右上角小警告图标（`⚠` `text-warning`）
- 状态标签：节点右下角小徽章，文字 `text-xs`，如"已完成"、"执行中"、"待执行"

**边设计**：
- 带箭头的贝塞尔曲线，颜色按源节点状态（执行中=琥珀虚线动画、已完成=绿色、待执行=灰色）
- 条件判断边：显示条件文本（如 "if found > 0"），文字 `text-xs` + `text-muted`，位于边的中点上方
- 执行中动画：虚线"流动"效果（`stroke-dashoffset` 循环动画，像数据传输）

**顶部控制栏**：
- 左侧：标题"任务规划" + 当前任务名 + 任务 ID（`text-xs` + `text-muted`）
- 右侧：播放 ▶ / 暂停 ⏸ / 重置 ↺ / 自动布局 / 导出 / 设置 按钮组
- 按钮样式：圆角 `radius-md`，背景 `bg-card`，hover 时 `bg-card-hover`，播放按钮用琥珀色填充

**左侧统计栏**：
- 总任务 / 已完成 / 执行中 / 待执行 / 失败，水平排列
- 数字：`text-xl` + `font-bold` + 对应状态色
- 标签：`text-xs` + `text-muted`

**右侧详情面板（可折叠）**：
- 宽度：320px，背景 `bg-card`（`#1A1724`），左侧 1px 分隔线
- 内容：
  - 任务名 + 状态徽章（右上角）+ 折叠按钮
  - 任务 ID（`text-xs` + `text-muted`）
  - 描述（`text-sm` + `text-secondary`）
  - 输入参数：JSON 格式，`font-mono` + `text-sm` + 深色背景，语法高亮（键名青色，字符串绿色，数字琥珀）
  - 输出结果：同上格式
  - 执行信息：开始时间、预计耗时、执行时长、重试次数（`text-xs`）
  - 状态信息：进度条（琥珀色）+ 百分比 + 当前状态文字
  - 依赖任务：列表，每个依赖项显示名称 + 状态图标
  - 查看日志按钮（底部，全宽，琥珀色边框）
- 迷你地图：右下角，显示整个 DAG 缩略图

**交互**：
- 拖拽：节点可拖拽，自动重新布局（保持 DAG 结构）
- 点击：显示详情面板
- 双击：编辑节点参数（如果允许）
- 右键：上下文菜单（重新执行、跳过、查看日志）
- 缩放/平移：滚轮缩放，拖拽空白平移

### 4.4 认知画像页面（CognitiveProfilePage）

**布局**：
- 全屏内容区，不使用右侧固定面板（因为本身就是画像页面）
- 顶部：标题"认知画像" + 时间范围选择器（本周/本月/本季度） + 导出按钮
- 内容：网格布局，2 列
  - 左侧列：雷达图（大） + 意图分布饼图
  - 右侧列：认知趋势折线图 + 会话统计卡片 + 实体词云

**雷达图**：
- 5 维度：元认知（顶部）、推理深度（右上）、发散度（右下）、稳定性（左下）、置信度（左上）
- 当前值：琥珀色填充（`rgba(217, 119, 6, 0.15)`）+ 琥珀色边框（`#D97706`）+ 顶点 `#F59E0B`
- 历史平均：灰色虚线边框（`#6B6680`）
- 网格线：`#3A3548`，文字标签：`text-xs` + `text-muted`
- 悬停：显示该维度历史变化趋势 tooltip

**认知趋势**：
- 最近 7 天的折线图，多条线（不同维度，可开关）
- 网格线 `#3A3548`，文字 `#A9A5B8`

**意图分布饼图**：
- 按意图类型分类，使用意图色（琥珀/青色/玫瑰/灰色）
- 图例在右侧，点击可隐藏/显示

**会话统计卡片**：
- 4 个卡片：总会话数、识别意图数、触发澄清次数、平均响应延迟
- 大号数字（`text-3xl` + `font-bold`）+ 标签（`text-sm` + `text-muted`）

**实体词云**：
- 从对话中提取的实体，按频率排序，字体大小反映频率
- 颜色按实体类型（地址=青色，数值=琥珀，状态=玫瑰）

---

## 5. 组件设计

### 5.1 消息气泡（MessageBubble）

```tsx
interface MessageBubbleProps {
  message: {
    id: string;
    role: 'user' | 'ai';
    content: string;
    timestamp: string;
    intents?: string[];           // 意图标签，如 ['SCAN_MEMORY', 'EXPLAIN']
    codeBlocks?: CodeBlock[];     // 代码块列表
    isStreaming?: boolean;        // 是否流式输出中
    status?: 'sent' | 'sending' | 'error';
  };
  onIntentClick?: (intent: string) => void;  // 点击意图标签跳转图谱
  onCopy?: () => void;
  onLike?: () => void;
  onDislike?: () => void;
  onRetry?: () => void;
}
```

**样式**：
- 用户消息：右对齐，`max-w-[70%]`，背景 `bg-card`（`#1A1724`），左边框 3px `#D97706`，圆角 `12px 12px 12px 4px`
- AI 消息：左对齐，`max-w-[80%]`，无背景，左边框 3px `#D97706`，圆角 `4px 12px 12px 12px`
- 代码块：背景 `#0C0A0F`，边框 `border-subtle`，圆角 `radius-md`，字体 `font-mono`，右上角语言标签 + 复制按钮
- 意图标签：消息下方，圆角 `radius-sm`，背景 `color-amber-subtle`，文字 `color-amber`，间距 `gap-2`，可点击
- 操作按钮：时间戳右侧，图标 20px，`text-muted`，hover 时 `text-primary`
- 流式光标：`|`，颜色 `#D97706`，0.5s 闪烁动画
- 错误状态：左边框变为 `#EF4444`，显示错误图标 + 重试按钮

**动画**：
- 入场：`message-enter`（400ms，translateY(12px)→0 + opacity）
- 流式输出：逐字显示，每字延迟 15ms（模拟打字效果）
- 错误：水平抖动（translateX -4px→4px→0，300ms，spring）

### 5.2 意图标签（IntentTag）

```tsx
interface IntentTagProps {
  intent: string;                  // 意图类型，如 'SCAN_MEMORY'
  size?: 'sm' | 'md';             // 尺寸
  clickable?: boolean;            // 是否可点击
  onClick?: () => void;
}
```

**样式**：
- 圆角 `radius-sm`（4px）
- 内边距：`px-2 py-0.5`（8px 水平 / 2px 垂直）
- 文字：`text-xs` + `font-medium`
- 背景：意图色 10% 透明度（如 `rgba(217,119,6,0.10)`）
- 文字颜色：意图色（如 `#D97706`）
- Hover（可点击时）：背景变为 20% 透明度，光标 pointer
- 尺寸：sm 用于消息内标签，md 用于过滤器选项

### 5.3 认知雷达图（CognitiveRadarChart）

```tsx
interface CognitiveRadarChartProps {
  data: {
    dimension: string;            // 维度名称，如 '元认知'
    value: number;                // 0-1
    fullMark?: number;            // 满分，默认 1
  }[];
  historicalData?: RadarData[];   // 历史数据，可选
  size?: number;                  // 图表尺寸，默认 200
}
```

**样式**：
- 使用 Recharts `RadarChart` 组件
- 5 个维度均匀分布（元认知、推理深度、置信度、稳定性、发散度）
- 当前值：填充 `rgba(217, 119, 6, 0.15)`，边框 `#D97706`（2px），顶点 `#F59E0B`（4px 圆点）
- 历史平均：填充透明，边框 `#6B6680`（1px 虚线）
- 网格线：`#3A3548`（1px）
- 维度标签：`text-xs` + `text-muted`，位于顶点外侧
- 悬停：显示 tooltip（深色背景，圆角 8px，显示维度名 + 当前值 + 历史值）

### 5.4 指标卡片（MetricCard）

```tsx
interface MetricCardProps {
  value: number;                  // 大数字，如 76
  label: string;                  // 标签，如 '推理深度'
  trend?: number;                // 趋势变化，如 +8
  trendDirection?: 'up' | 'down' | 'neutral';
  color?: 'amber' | 'teal' | 'rose';  // 颜色主题
}
```

**样式**：
- 文字居中对齐
- 数字：`text-3xl` + `font-bold` + 颜色主题（如 `#F59E0B`）
- 标签：`text-xs` + `text-muted`，数字下方
- 趋势：数字下方，`text-xs` + 趋势色（上升绿色 `#10B981`，下降红色 `#EF4444`）+ 箭头图标
- 无背景，无边框，纯文字排版

### 5.5 状态进度条（StatusProgress）

```tsx
interface StatusProgressProps {
  label: string;                  // 标签，如 '成功状态'
  percentage: number;             // 0-100
  description: string;            // 说明文字
  icon: React.ReactNode;          // 状态图标
  color: 'amber' | 'green' | 'red'; // 进度条颜色
}
```

**样式**：
- 图标：左侧，20px，颜色与主题一致
- 标签：图标右侧，`text-sm` + `font-medium` + `text-primary`
- 百分比：右侧对齐，`text-sm` + `font-bold` + 颜色主题
- 进度条：高度 4px，圆角 `radius-full`，背景 `border-subtle`，填充色为主题色
- 说明文字：进度条下方，`text-xs` + `text-muted`
- 间距：图标-标签-百分比一行，下方进度条，再下方说明文字，整体 `gap-2`

### 5.6 输入区域（ChatInput）

```tsx
interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  onAttach?: () => void;
  onCodeBlock?: () => void;
  onMention?: () => void;
  onImage?: () => void;
  onGrid?: () => void;
}
```

**样式**：
- 容器：背景 `bg-card`（`#1A1724`），圆角 `radius-lg`（12px），边框 `border-subtle`（聚焦时变为 `border-strong`）
- 文本框：多行，auto-resize（最小 1 行，最大 6 行），背景透明，无边框
- 占位符：`text-muted`（"输入消息... (Shift + Enter 换行, Enter 发送)"）
- 底部工具栏：左对齐，图标 20px，`text-muted`，hover 时 `text-secondary`，间距 `gap-3`
- 发送按钮：右侧，圆形 48px，琥珀色背景 `#D97706`，白色纸飞机图标，hover 时 `scale(1.05)` + `shadow-amber`
- 字数统计：右下角（可选），`text-xs` + `text-muted`

### 5.7 对话树图谱组件（ConversationGraph）

```tsx
interface ConversationGraphProps {
  sessions: Session[];
  selectedNodeId?: string;
  viewMode?: 'force' | 'timeline' | 'tree';
  filters?: IntentFilter[];
  searchQuery?: string;
  onNodeClick?: (nodeId: string) => void;
  onNodeDoubleClick?: (nodeId: string) => void;
}
```

**技术实现**：基于 `react-force-graph-2d`（Canvas 渲染）

**节点渲染**：
- 自定义 Canvas 绘制函数
- 用户节点：圆形，白色边框 1.5px，半径 20-30px（动态），文字居中
- AI 节点：圆角矩形，意图色边框 1.5px，宽度 120px，高度自适应
- 簇节点：虚线圆形，灰色边框，半径 30px

**力导向参数**：
- 节点间排斥力：60
- 连线长度：150
- 中心引力：0.05
- 阻尼：0.9
- 超过 200 节点时启用聚类

### 5.8 任务 DAG 组件（TaskFlow）

```tsx
interface TaskFlowProps {
  taskGraph: TaskGraph;
  executionStatus: ExecutionStatus;
  selectedNodeId?: string;
  onNodeClick?: (nodeId: string) => void;
  onNodeExecute?: (nodeId: string) => void;
}
```

**技术实现**：基于 `@reactflow/core`

**节点类型**：
- `startNode`：开始节点，圆角矩形，绿色边框
- `processNode`：处理节点，圆角矩形，图标 + 标题 + 描述 + 状态徽章
- `decisionNode`：判断节点，菱形（CSS `rotate(45deg)` 或 SVG），条件文字
- `endNode`：结束节点，圆角矩形

**边类型**：
- `defaultEdge`：默认边，带箭头
- `animatedEdge`：执行中边，虚线流动动画（CSS `stroke-dashoffset` 动画）
- `conditionEdge`：条件边，带条件文字标签

**布局**：Dagre 自动布局，从上到下

---

## 6. 交互设计

### 6.1 页面切换

- 使用 React Router `<Outlet />` + Framer Motion `AnimatePresence`
- 切换动画：当前页面向左滑出（`translateX(-20px) opacity 0`），新页面从右滑入（`translateX(20px) opacity 1 → 0`），300ms，ease-out
- 所有页面共享 Sidebar 和 Toolbar，只切换 Main Content
- 全屏页面（图谱、任务规划）时，Toolbar 保留但简化，右侧面板隐藏

### 6.2 暗色模式切换

- 切换按钮：Toolbar 右侧，太阳/月亮图标（Lucide `Sun` / `Moon`）
- 切换动画：
  1. CSS 变量在 300ms 内渐变（`transition: all 300ms`）
  2. 图标旋转动画（Framer Motion：`rotate: 180` + `scale: 0` → `rotate: 0` + `scale: 1`）
- 主题状态：存储在 `localStorage`，首次访问检测 `prefers-color-scheme`
- 图表暗色：Recharts 网格线 `#3A3548`，文字 `#A9A5B8`；React Flow 背景 `#0C0A0F`，节点边框 `#3A3548`

### 6.3 加载状态

- **全局加载**：页面首次加载，全屏 DialogMesh logo 脉冲 + "正在启动认知系统..."（2-3 秒）
- **局部加载**：
  - 消息发送：旋转加载器（18px，琥珀色）
  - 数据加载：骨架屏（`shimmer` 动画，背景 `#1A1724` → `#252134` 渐变）
  - 图表加载："正在构建认知图谱..." + 进度条
- **骨架屏样式**：
  ```css
  .skeleton {
    background: linear-gradient(90deg, #1A1724 25%, #252134 50%, #1A1724 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
  }
  ```

### 6.4 错误处理

- **全局错误**：Toast 通知（右上角），琥珀色边框，包含错误图标 + 标题 + 描述 + 关闭按钮 + 重试按钮
- **消息错误**：消息气泡左边框变红（`#EF4444`），显示错误图标 + 重试按钮
- **连接断开**：顶部横幅（`sticky top-0`，琥珀色背景），"连接已断开，正在重试..." + 进度条
- **API 错误**：内联错误信息（红色文字 + 图标），不阻断整个页面

### 6.5 响应式设计

**断点**：
- `lg`: 1024px — 桌面三栏布局（Sidebar 240px + 内容区 + 右侧面板 340px）
- `md`: 768px — 平板：Sidebar 收缩为 60px 图标栏，右侧面板隐藏（可点击展开）
- `sm`: 640px — 手机：Sidebar 完全隐藏（汉堡菜单），右侧面板隐藏，底部 Tab 导航

**移动端适配**：
- Sidebar：折叠为底部 Tab 导航（5 个图标：聊天、图谱、画像、任务、设置）
- 右侧面板：隐藏，点击消息上的"认知"按钮弹出底部 sheet
- 聊天区域：全屏，消息气泡最大宽度 90%
- 图谱页面：双指缩放，节点点击后底部弹出详情 sheet
- 任务规划：简化显示，只展示当前执行路径，横向滚动

---

## 7. 外挂架构设计（Plugin Architecture）

### 7.1 核心思想

DialogMesh 作为**认知外挂**，可以挂载到 ChatGPT、Claude、Kimi 等 AI 上。

**挂载方式**：
1. **浏览器扩展（Chrome Extension）**：最通用，注入到任意 AI 网页
2. **Tampermonkey 脚本**：快速部署
3. **Electron 桌面应用**：独立窗口，系统级快捷键呼出
4. **API 中间件**：代理层，拦截 AI API 请求

### 7.2 架构分层

```
┌─────────────────────────────────────────────────────┐
│  DialogMesh Plugin Host                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ ChatGPT  │ │  Claude  │ │   Kimi   │  ...       │
│  │ Adapter  │ │ Adapter  │ │ Adapter  │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       └────────────┴────────────┘                    │
│              Unified Message Interface                │
│  ┌─────────────────────────────────────┐             │
│  │  DialogMesh Core Engine               │             │
│  │  PCR | Intent | Planning | Answer     │             │
│  └─────────────────────────────────────┘             │
│       │                                              │
│  ┌────┴────────────────────────────────────┐         │
│  │  Visualization Layer                      │         │
│  │  Chat UI | Graph | Profile | Task Map    │         │
│  └────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

### 7.3 注入 UI 设计

**浮动按钮**：
- 位置：右下角（距边缘 24px），圆形，56px
- 颜色：琥珀色 `#D97706`，白色 DialogMesh 图标
- 动画：hover 放大 1.1x，点击缩小 0.9x 后弹回（spring）
- 状态指示：连接中时脉冲光环（2s 周期），连接成功时绿色小圆点

**侧边面板（注入到 AI 页面）**：
- 宽度：380px，从右侧滑入
- 背景：`rgba(12, 10, 15, 0.92)` + `backdrop-blur-lg`（毛玻璃）
- 阴影：`shadow-xl`，左侧边框 `border-medium`
- 内容：与独立应用的 ChatPage 一致，但缩小比例（字体小一号，间距缩小）
- 滑入动画：`translateX(100%) → 0`，300ms，spring

### 7.4 Chrome Extension manifest

```json
{
  "manifest_version": 3,
  "name": "DialogMesh — AI 认知外挂",
  "version": "3.0.0",
  "permissions": ["storage", "activeTab", "scripting"],
  "host_permissions": [
    "https://chat.openai.com/*",
    "https://claude.ai/*",
    "https://kimi.moonshot.cn/*",
    "http://localhost:8000/*"
  ],
  "content_scripts": [{
    "matches": ["https://chat.openai.com/*", "https://claude.ai/*", "https://kimi.moonshot.cn/*"],
    "js": ["content.js"],
    "css": ["content.css"],
    "run_at": "document_end"
  }],
  "background": { "service_worker": "background.js" },
  "action": { "default_popup": "popup.html" }
}
```

---

## 8. 技术选型与依赖

### 8.1 新增依赖

| 库 | 用途 | 版本 | 大小（gzip） |
|---|------|------|-------------|
| `react-force-graph-2d` | 对话树力导向图（Obsidian 风格） | ^1.25 | ~60KB |
| `recharts` | 认知画像雷达图 + 趋势折线图 + 饼图 | ^2.12 | ~45KB |
| `@reactflow/core` | 任务规划 DAG 图 | ^11.10 | ~55KB |
| `@reactflow/background` | React Flow 背景网格 | ^11.10 | ~5KB |
| `@reactflow/minimap` | React Flow 迷你地图 | ^11.10 | ~8KB |
| `framer-motion` | 页面切换、组件入场、主题切换动画 | ^11.0 | ~25KB |
| `react-syntax-highlighter` | 代码块高亮（Prism 主题） | ^15.5 | ~30KB |
| `prism-themes` | 代码高亮暗色主题 | ^1.9 | ~10KB |

**总计新增**：约 240KB gzipped（Tree-shaking 后实际更小）

**已存在依赖**（保持不变）：
- `react` ^19, `react-dom` ^19, `react-router-dom` ^7
- `tailwindcss` ^4, `zustand` ^5, `lucide-react` ^0.x
- `clsx`, `tailwind-merge`

### 8.2 性能优化策略

1. **代码分割**：
   - 图谱页面：`lazy(() => import('./pages/ConversationGraphPage'))`
   - 画像页面：`lazy(() => import('./pages/CognitiveProfilePage'))`
   - 任务规划：`lazy(() => import('./pages/TaskPlanningPage'))`
   - 图表库：recharts 和 react-force-graph 按需加载

2. **图表虚拟化**：
   - 对话树超过 200 节点时启用聚类（clustering）
   - 使用 `requestAnimationFrame` 优化动画

3. **状态管理**：
   - Zustand `subscribe` 只监听需要的切片（`useShallow`）
   - 大对象使用不可变更新

4. **构建优化**：
   - Vite `manualChunks` 将图表库单独打包
   - `vite-plugin-compression` 生成 gzip/brotli

---

## 9. 文件结构

```
frontend/src/
├── App.tsx                          # 主应用（路由 + 布局 + 动画）
├── main.tsx                         # 入口
├── index.css                        # 全局样式（CSS 变量、动画、暗色模式）
├──
├── api/                             # API 客户端
│   ├── session.ts
│   └── task.ts                      # 新增：任务规划 API
│
├── types/                           # 类型定义
│   ├── api.ts
│   ├── chat.ts
│   ├── graph.ts                     # 图谱相关类型
│   ├── profile.ts                   # 认知画像类型
│   └── task.ts                      # 任务规划类型
│
├── stores/                          # Zustand 状态管理
│   ├── index.ts
│   ├── sessionStore.ts
│   ├── themeStore.ts                # 暗色模式状态
│   ├── graphStore.ts                # 图谱数据状态
│   └── taskStore.ts                 # 任务规划状态
│
├── hooks/                           # 自定义 Hooks
│   ├── useChat.ts
│   ├── useHealth.ts
│   ├── useSession.ts
│   ├── useWebSocket.ts
│   ├── useTheme.ts                  # 暗色模式切换
│   ├── useGraphData.ts              # 图谱数据获取
│   └── useTaskGraph.ts              # 任务图数据
│
├── lib/                             # 工具函数
│   ├── api.ts
│   ├── config.ts
│   ├── utils.ts
│   ├── websocket.ts
│   ├── chartTheme.ts                # 图表暗色主题配置
│   ├── graphUtils.ts                # 图谱数据处理
│   └── taskLayout.ts                # DAG 自动布局
│
├── components/                      # 通用组件
│   ├── Layout.tsx                     # 布局骨架（Sidebar + Toolbar + Main + RightPanel）
│   ├── Sidebar.tsx                    # 侧边栏（导航 + 会话列表）
│   ├── Toolbar.tsx                    # 顶部工具栏
│   ├── RightPanel.tsx                 # 右侧认知面板（雷达图 + 指标 + 状态）
│   ├── ChatPanel.tsx                  # 聊天面板（消息列表 + 输入框）
│   ├── ChatInput.tsx                  # 输入框（多行 + 工具栏 + 发送按钮）
│   ├── MessageBubble.tsx              # 消息气泡（用户/AI + 意图标签 + 代码块）
│   ├── IntentTag.tsx                  # 意图标签（徽章）
│   ├── CodeBlock.tsx                  # 代码块高亮（Prism + 复制按钮）
│   ├── ThinkingPanel.tsx              # 思考面板（可折叠步骤）
│   ├── ClarificationPanel.tsx         # 澄清面板
│   ├── TaskGraphView.tsx              # 任务列表（迷你版，用于聊天页）
│   ├── ConnectionStatus.tsx           # 连接状态
│   ├──
│   ├── graph/                         # 图谱组件
│   │   ├── ConversationGraph.tsx        # 对话树力导向图（主组件）
│   │   ├── GraphNode.tsx              # 自定义节点渲染
│   │   ├── GraphToolbar.tsx           # 图谱工具栏（搜索 + 过滤器 + 视图模式）
│   │   ├── GraphLegend.tsx            # 图例
│   │   ├── GraphMinimap.tsx           # 迷你地图
│   │   └── GraphFilters.tsx           # 过滤器面板
│   │
│   ├── profile/                       # 认知画像组件
│   │   ├── CognitiveRadarChart.tsx    # 雷达图（Recharts）
│   │   ├── CognitiveTrendChart.tsx    # 趋势折线图
│   │   ├── MetricCards.tsx            # 指标卡片（三指标）
│   │   ├── StatusProgress.tsx         # 状态进度条
│   │   ├── IntentDistributionChart.tsx  # 意图分布饼图
│   │   └── EntityWordCloud.tsx        # 实体词云
│   │
│   ├── task/                          # 任务规划组件
│   │   ├── TaskFlow.tsx               # 任务 DAG（React Flow）
│   │   ├── TaskNode.tsx               # 自定义任务节点
│   │   ├── TaskEdge.tsx               # 自定义任务边（带动画）
│   │   ├── TaskDetailPanel.tsx        # 任务详情面板
│   │   ├── TaskExecutionControls.tsx  # 执行控制按钮组
│   │   └── TaskStatsBar.tsx           # 统计栏（总/完成/执行/待执行/失败）
│   │
│   └── ui/                            # 通用 UI 组件
│       ├── Card.tsx                   # 卡片容器
│       ├── Button.tsx                 # 按钮（多变体：primary/outline/ghost）
│       ├── Badge.tsx                  # 徽章
│       ├── Tooltip.tsx                # 工具提示
│       ├── Toast.tsx                  # 通知 Toast
│       ├── Skeleton.tsx               # 骨架屏
│       ├── Modal.tsx                  # 模态框
│       ├── Drawer.tsx                 # 抽屉面板
│       ├── Tabs.tsx                   # 标签页
│       ├── ThemeToggle.tsx            # 主题切换按钮
│       └── ScrollArea.tsx             # 自定义滚动区域
│
├── pages/                             # 页面组件
│   ├── ChatPage.tsx                   # 聊天页面（主界面）
│   ├── ConversationGraphPage.tsx      # 对话树图谱
│   ├── CognitiveProfilePage.tsx       # 认知画像
│   ├── TaskPlanningPage.tsx           # 任务规划
│   ├── SessionsPage.tsx               # 会话列表
│   ├── SettingsPage.tsx               # 设置页面
│   ├── DashboardPage.tsx              # 仪表盘（简化版）
│   └── NotFoundPage.tsx               # 404
│
└── plugin/                            # 外挂架构（后续开发）
    ├── adapters/
    │   ├── BaseAdapter.ts
    │   ├── ChatGPTAdapter.ts
    │   ├── ClaudeAdapter.ts
    │   └── KimiAdapter.ts
    ├── injectors/
    │   ├── PanelInjector.ts
    │   ├── FloatButtonInjector.ts
    │   └── MessageDecorator.ts
    └── bridge/
        ├── MessageBridge.ts
        └── StorageSync.ts
```

---

## 10. 实现 Roadmap（Phase 顺序）

### Phase 1：设计系统与基础（Day 1-2）
- [ ] 更新 `index.css`：CSS 变量、暗色模式、动画 keyframes、自定义滚动条
- [ ] 创建 `themeStore.ts`：暗色模式状态管理（`localStorage` 持久化）
- [ ] 创建通用 UI 组件：`Button.tsx`、`Card.tsx`、`Badge.tsx`、`Tooltip.tsx`、`Toast.tsx`、`Skeleton.tsx`、`ThemeToggle.tsx`
- [ ] 更新 `Layout.tsx`：三栏骨架（Sidebar 240px + Main + RightPanel 340px）
- [ ] 创建 `Sidebar.tsx`：导航 + 最近会话列表
- [ ] 创建 `Toolbar.tsx`：会话标题 + 搜索 + 主题切换 + 设置
- [ ] 安装 `framer-motion`，配置页面切换动画

### Phase 2：聊天页面重构（Day 3-5）
- [ ] 创建 `MessageBubble.tsx`：用户/AI 消息气泡、意图标签、代码块、操作按钮
- [ ] 创建 `IntentTag.tsx`：意图徽章组件
- [ ] 创建 `CodeBlock.tsx`：Prism 代码高亮 + 复制按钮
- [ ] 创建 `ChatInput.tsx`：多行 auto-resize + 底部工具栏 + 琥珀发送按钮
- [ ] 创建 `RightPanel.tsx`：认知画像面板（迷你雷达图 + 指标卡片 + 状态进度）
- [ ] 创建 `CognitiveRadarChart.tsx`：Recharts 雷达图（5 维度）
- [ ] 创建 `MetricCards.tsx`：三指标大数字卡片
- [ ] 创建 `StatusProgress.tsx`：成功/风险状态进度条
- [ ] 更新 `ChatPage.tsx`：整合三栏布局
- [ ] 安装 `react-syntax-highlighter` + `prism-themes`

### Phase 3：对话树图谱（Day 6-8）
- [ ] 安装 `react-force-graph-2d`
- [ ] 创建 `graph.ts` 类型定义
- [ ] 创建 `graphStore.ts` 状态管理
- [ ] 创建 `graphUtils.ts`：数据处理、聚类算法
- [ ] 创建 `ConversationGraph.tsx`：主图谱组件（力导向布局）
- [ ] 创建 `GraphToolbar.tsx`：搜索 + 意图过滤器 + 视图模式 + 缩放
- [ ] 创建 `GraphLegend.tsx`：图例（意图颜色 + 数量）
- [ ] 创建 `GraphMinimap.tsx`：迷你地图
- [ ] 创建 `ConversationGraphPage.tsx`：全屏图谱页面
- [ ] 添加路由 `/graph`

### Phase 4：任务规划 DAG（Day 9-11）
- [ ] 安装 `@reactflow/core`、`@reactflow/background`、`@reactflow/minimap`
- [ ] 创建 `task.ts` 类型定义
- [ ] 创建 `taskStore.ts` 状态管理
- [ ] 创建 `TaskNode.tsx`：自定义节点（开始/处理/判断/结束）
- [ ] 创建 `TaskEdge.tsx`：自定义边（带动画 + 条件标签）
- [ ] 创建 `TaskFlow.tsx`：React Flow DAG 主组件
- [ ] 创建 `TaskDetailPanel.tsx`：右侧详情面板（参数/结果/执行信息）
- [ ] 创建 `TaskExecutionControls.tsx`：播放/暂停/重置/自动布局/导出
- [ ] 创建 `TaskStatsBar.tsx`：总/完成/执行/待执行/失败统计
- [ ] 创建 `TaskPlanningPage.tsx`：全屏任务规划页面
- [ ] 添加路由 `/tasks`

### Phase 5：认知画像页面（Day 12-13）
- [ ] 安装 `recharts`
- [ ] 创建 `chartTheme.ts`：暗色/亮色图表主题配置
- [ ] 创建 `CognitiveRadarChart.tsx`（全尺寸，非迷你版）
- [ ] 创建 `CognitiveTrendChart.tsx`：趋势折线图
- [ ] 创建 `IntentDistributionChart.tsx`：意图分布饼图
- [ ] 创建 `EntityWordCloud.tsx`：实体词云（可用 `react-wordcloud`）
- [ ] 创建 `CognitiveProfilePage.tsx`：全屏画像页面（2 列网格）
- [ ] 添加路由 `/profile`

### Phase 6：动画与交互（Day 14-15）
- [ ] 页面切换动画：`AnimatePresence` + `motion.div`
- [ ] 消息入场动画：Framer Motion `motion.div`（translateY + opacity）
- [ ] 卡片浮现动画：scale + opacity
- [ ] 暗色模式切换动画：CSS `transition` + Framer Motion 图标旋转
- [ ] 骨架屏：`Skeleton.tsx` 的 shimmer 动画
- [ ] 错误抖动：Framer Motion shake 变体
- [ ] Toast 入场/退场动画
- [ ] 图谱节点入场、边展开动画
- [ ] 任务节点脉冲、边流动动画

### Phase 7：响应式与移动端（Day 16-17）
- [ ] 移动端 Sidebar：底部 Tab 导航
- [ ] 右侧面板移动端：隐藏/底部弹出 sheet
- [ ] 聊天移动端：全屏，气泡最大宽度 90%
- [ ] 图谱移动端：双指缩放 + 底部 sheet
- [ ] 任务规划移动端：简化显示，横向滚动
- [ ] 触摸优化：最小点击区域 44px

### Phase 8：外挂架构（Day 18-24，后续）
- [ ] 创建 `BaseAdapter.ts`、`ChatGPTAdapter.ts`
- [ ] 创建 `PanelInjector.ts`、`FloatButtonInjector.ts`
- [ ] 创建 `MessageBridge.ts`
- [ ] Chrome Extension `manifest.json`、`content.ts`、`background.ts`
- [ ] 测试挂载到 ChatGPT/Claude/Kimi
- [ ] 独立窗口（Electron 或 `window.open`）

---

## 11. 设计检查清单

- [ ] 所有颜色在暗色模式下对比度 ≥ 4.5:1（WCAG AA）
- [ ] 动画不引起眩晕（无高频闪烁、无大范围旋转）
- [ ] 图表在暗色模式下颜色正确（使用 CSS 变量而非硬编码）
- [ ] 移动端所有功能可访问（触控、手势、键盘导航）
- [ ] 外挂架构不破坏目标网站（沙箱隔离、CSS 命名空间）
- [ ] 所有新增依赖有 TypeScript 类型定义
- [ ] 代码分割后每个 chunk < 200KB（gzip）
- [ ] 所有文本支持国际化（使用 i18n key，目前中文）
- [ ] 键盘快捷键：Enter 发送、Shift+Enter 换行、Ctrl+K 搜索、Ctrl+D 暗色切换
- [ ] 无障碍：ARIA 标签、焦点管理、屏幕阅读器支持
