# DESIGN_TUI.md -- Terminal UI for DialogMesh v4

> 版本: v1.0 | 日期: 2026-07-14
>
> Textual-based terminal dashboard for the v4 cognitive pipeline.
> Monitors all 4 paths (Async/Slow/Deep/Fast) in real-time with navigable panels.

---

## 1. 参考框架

| 参考 | 借鉴什么 |
|:---|:---|
| **Textual** (Python) | CSS布局、异步事件、DataTable、TabbedContent |
| **htop** | 实时刷新 (<1s interval)、渐变色条、CPU条 = 吞吐量条 |
| **k9s** | 导航式面板 (:obs → Observation, :hyp → Hypothesis)、Esc 返回 |
| **lazygit** | Tab 切换 (1-8 数字键)、状态颜色 (green=active, yellow=pending, red=error) |
| **bpytop** | 折叠面板、鼠标支持、theme selector |

## 2. 核心布局

`
+------------------------------------------------------------------+
|  DialogMesh v4 TUI                          [Async: OK] [Engine: ON] |
+------------------------------------------------------------------+
| 1.Dashboard | 2.Obs | 3.Hyp | 4.Know | 5.Skill | 6.World | 7.Ctx | 8.Log |
+------------------------------------------------------------------+
|                                                                  |
|  [Panel content — switches based on active tab]                  |
|                                                                  |
+------------------------------------------------------------------+
|  F1:Help  F2:Refresh  F3:Trigger Checkpoint  F10:Quit            |
+------------------------------------------------------------------+
`

### Tab 1: Dashboard (默认)
`
Async Path   [████████░░] 42 events  38 ok  4 fail
Slow Path    [██░░░░░░░░] 3 checkpoints
Deep Path    [█░░░░░░░░░] 1 skill distilled
Context      [█████░░░░░] Last IR: "gateway monitoring" (15 items)

Observation Pool:  12 bundles (5 engineering, 4 behavior, 3 memory)
Hypothesis Pool:   8 active, 3 frozen
Knowledge Vault:   5 nodes
Skill Forge:       2 verified, 3 candidates
`

### Tab 2: Observations (实时流)
`
ID              Domain        Summary                         Time
obs_001         engineering   Gateway monitoring pattern      12:34:56
obs_002         behavior      User dragging module            12:34:55
obs_003         memory        Pipeline structure changed      12:34:50
...
Enter: detail view  |  d: domain filter  |  j/k: scroll
`

### Tab 3: Hypotheses (竞争池)
`
ID         Statement                     Status   S   C   Stab
hyp_001    User developing Gateway       active   12  3   0.81
hyp_002    User learning Gateway         active   4   6   0.35
hyp_003    Gateway needs monitoring      frozen   20  1   0.92
...
Enter: detail (7-dim BeliefState)  |  f: freeze  |  d: discard
`

### Tab 4: Knowledge Vault
`
ID         Statement                     Domain        Score
k_001      Gateway needs monitoring      engineering   0.92
k_002      RateLimiter is middleware      engineering   0.88
...
Enter: evidence trace  |  s: search  |  e: export
`

### Tab 5: Skill Forge
`
Name                 Domain        Usage   Status
middleware_monitor   engineering   5       verified
health_check_pattern engineering   3       candidate
...
Enter: blueprint view  |  p: promote  |  d: deprecate
`

### Tab 6: World Map
`
Graph: code (342 nodes, 891 edges)
Communities: 12
Top Backbone: gateway.main(0.95), gateway.auth(0.88)

Community explorer:
  community_0: [gateway.main, gateway.auth, utils.logger] -- 23 nodes
  community_1: [utils.cache, redis.client] -- 15 nodes
...
Enter: expand community  |  b: backbone view  |  g: graph stats
`

### Tab 7: Context View
`
Last IR: "gateway monitoring"
Total: 15 items (850 tokens)

[knowledge]     5 items (relevance: 0.72-0.91)
[observation]   3 items (relevance: 0.50-0.65)
[skill]         2 items (relevance: 0.60-0.73)
[world]         5 items (relevance: 0.45-0.82)

Enter: expand source  |  r: reassemble  |  e: export IR
`

### Tab 8: Event Log
`
ID                  Kind                Created
sw-001              dialog.message      12:34:56
sw-002              ui.drag             12:34:55
sw-003              git.commit          12:30:00
...
Enter: detail  |  r: replay  |  f: filter by kind
`

## 3. 技术选型

| 项 | 选择 | 理由 |
|:---|:---|:---|
| 框架 | **Textual** | Python 原生，CSS 布局，内置 DataTable, TabbedPane |
| 数据源 | 直接调用 CLI inspect 函数 | 复用 CLI 代码，零后端 |
| 刷新 | set_interval(1s) | 比 --watch 更灵活，可暂停 |
| 状态 | 全局 _engine 单例 | 与 CLI 共享同一个引擎实例 |

## 4. 文件规划

`
core/agent/v4/tui/
├── app.py              # Textual App 主入口
├── dashboard.py        # Tab 1: Dashboard
├── panels.py           # 可复用面板组件
├── __init__.py
└── tests/
`

scripts/tui.py — 启动入口：python scripts/tui.py

## 5. 键盘快捷键

| 键 | 功能 |
|:---|:---|
| 1-8 | 切换 Tab |
| j / ↓ | 下移 |
| k / ↑ | 上移 |
| Enter | 详情 / 展开 |
| d | Domain 过滤 (Observations) |
| f | 冻结 Hypothesis |
| r | 刷新手动 |
| F2 | 自动刷新开关 |
| F3 | 触发 Checkpoint |
| F10 / q | 退出 |

## 6. 分层优先级

| 阶段 | 内容 | 时间 |
|:---|:---|:---|
| Phase 1 | Dashboard + Observations + Hypotheses | 核心三点 |
| Phase 2 | Knowledge + Skills + World | 扩展 |
| Phase 3 | Context + Event Log + 主题 | 完整 |
