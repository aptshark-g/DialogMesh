# Topic Tree — 接入后差距

> 2026-07-21

## 修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | 分支切换 | `switch_branch()` on PCR topic_shift |
| 2 | 摘要压实 | `compact_summary()` 每5轮 |

## 有效实现率

```
feed_turn            ✅
Context injection    ✅
分支切换              ✅
摘要压实              ✅
行为链内建            ❌ (v3.1设计)
递归收敛快匹配        ❌ (Tier0独立)
────────────────────────────
有效实现率: ~70%
```
