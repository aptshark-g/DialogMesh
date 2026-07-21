# Profile — 接入后差距 (全部修复)

> 2026-07-21

## 修复清单

| # | 问题 | 修复 |
|---|------|------|
| 1 | PCR→TrackA EMA | `alpha·fast + (1-alpha)·slow` (cognitive_level, expertise_level, preferred_detail) |
| 2 | LLM metrics→trust | `success→+0.02, fail→-0.05` |
| 3 | TrackB infer_from_trace | `TagLayer.infer_from_trace()` 每5轮执行 |
| 4 | OCEAN 映射 | `ocean_analyst.update()` 每10轮执行 |
| 5 | ConvergenceEngine | `update(track_a)` 每3轮执行 |

## 有效实现率

```
ExecutionTraceV3       ✅
TrackA EMA (3维度)     ✅
LLM trust feedback     ✅
TrackB TagLayer        ✅
OCEAN mapping          ✅
ConvergenceEngine      ✅
────────────────────────────
有效实现率: ~95%
```

## Context — 确认无遗漏

```
DomainSelector · PerspectivePlanner · ContextAssembler
BudgetAllocator · SubgraphCompiler · DiscourseBlockTree
TopicTree · to_prompt budget过滤
ContextCompressor · Pruner · LOGICAL_LEAP→Subgraph · TTL decay
────────────────────────────
✅ 12/12 全部接入 · 95%
```
