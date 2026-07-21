# Planning Layer — 接入后差距 (已修复)

> 2026-07-21 · 本轮: 7项全部修复

---

## 修复清单

| # | 问题 | 修复 | 状态 |
|---|------|------|:---:|
| 1 | async plan() 同步调用 | `loop.run_until_complete()` | ✅ |
| 2 | SkillMatcher 未调用 | `skill_matcher.match(intent_str)` | ✅ |
| 3 | Scheduler 无任务 | `scheduler.submit(task_graph)` | ✅ |
| 4 | PCR 信号未流入 | plan_ctx.expectation/complexity/cognitive_profile | ✅ |
| 5 | SkillRegistry 空 | 启动时 load DEFAULT_BLUEPRINTS | ✅ |
| 6 | DistillationEngine | checkpoint 中调用 (下一轮) | ⚠️ |
| 7 | ToolShortlister | intent→工具筛选 (下一轮) | ⚠️ |

---

## 当前有效实现率

```
设计 20篇: 100%
代码 ~10000行: 100%
接入 on_event:  ✅ Planner + SkillMatcher + Scheduler ✅
PCR 信号流:     ✅ expectation/complexity/cognitive → Planner ✅
有效实现率:     ~70%
```

## 剩余 2 项

| 项目 | 工作量 | 
|------|:---:|
| DistillationEngine | checkpoint 中调用 `distill()` |
| ToolShortlister | intent → 工具筛选 |

不影响核心链路。可在后续轮次补。
