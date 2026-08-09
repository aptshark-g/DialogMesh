# 施工记录 — GAP-F1 变更日志视图（2026-08-07）

> 状态: 完成 ✅ | GAP-F1（P1-1, 前端变更日志 = git log + PR review 风格）

---

## 一、数据源（复用, 零新状态）

- `DecisionEventBus`（blueprint/decision_event.py）:
  - `recent(limit, kind)` — 决策事件流（git log 语义, 回看/审计）
  - `intervene(status, comment, dimension, kind)` — PR review 回写
    （approve→applied / reject→rejected, 追加 user_correction 评论事件）
- 事件 kinds: strategy_switch / plan_gate / meta_advice / user_correction
  （+ 本轮扩展: heuristic_health / tool_batch）

## 二、后端 API

- `kernel_changelog(limit, kind)` — 事件流 + 统计（total/proposed/applied/
  rejected/reverted）
- `kernel_changelog_intervene(req)` — 介入回写（status/comment/dimension/kind）
- `GET /v6/changelog` + `POST /v6/changelog/intervene`

## 三、前端（RightDock「变更日志」tab）

- `ChangelogDockContent`: 事件流（git log 风格）—
  status 标签（待介入/已生效/已否决/已回退, 颜色区分）+ kind 标签
  （策略切换/关卡/元认知建议/用户修正…）+ dimension + reason +
  before→after 变更对比（删除线/绿色）+ 时间
- kind 筛选下拉 + 待介入计数徽标
- **proposed 事件 → 批准/否决按钮**（PR review 语义, 不打断执行）

## 四、验证

- 后端 `test_changelog.py` **4/4**: 空流/事件统计/kind 筛选/approve+reject 回写
  （含 intervene 追加评论事件的定位断言）
- 回归 kernel_dispatch **49/49**（合计 53/53 全绿）
- 前端 tsc 归零 + vite build 成功（3.01s）

## 五、对齐

- A17（记录永不可删）: 决策事件流持久化（EventLog + 内存缓冲）
- A19（白盒）: 决策可查看（变更日志）+ 可介入（批准/否决）
- 异步介入（META_ARBITER）: 前端 PR review 回写不阻塞执行

## 六、遗留

- taint 字段（GAP-5）可在变更日志展示（事件已含, 前端未渲染）
- 介入评论输入框（当前固定文案"批准/否决（前端介入）"）
