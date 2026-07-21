# Profile — 接入后差距

> 2026-07-21

## 修复

| # | 问题 | 修复 | 状态 |
|---|------|------|:---:|
| 1 | PCR→TrackA EMA 未接 | alpha·fast + (1-alpha)·slow | ✅ |
| 2 | LLM metrics→trust 未接 | success→+0.02, fail→-0.05 | ✅ |
| 3 | TrackB infer_from_trace | 代码完整未调用 | ❌ |
| 4 | OCEAN→行为链偏置 | 未接 | ❌ |
| 5 | ConvergenceEngine | 未调用 | ❌ |

## 有效实现率

```
ExecutionTraceV3       ✅
TrackA EMA             ✅
LLM trust update       ✅
TrackB                 ❌
OCEAN→Behavior         ❌
ConvergenceEngine      ❌
────────────────────────────
有效实现率: ~55%
```
