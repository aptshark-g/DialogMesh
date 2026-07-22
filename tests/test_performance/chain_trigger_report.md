# 链触发条件 — 测试报告

> 2026-07-22 · 20/20 PASS

---

## Trigger Condition Tests (14 tests)

```
✅ PCR always triggers
✅ Router always triggers  
✅ Intent skipped for ATOMIC zone
✅ Intent triggers for PRECISION zone
✅ Planner triggers for PRECISION/ABYSS
✅ Planner skips for ATOMIC/EXPLORE/PSYCHE/MIXED
✅ Context always triggers
✅ LLM always triggers
✅ Profile with PCR
✅ Profile with behavior burst
✅ Behavior always
✅ ABC always
✅ Mind always
✅ Meta every 5 ticks + behavior surge
```

## Full Pipeline Tests (6 tests)

```
✅ ATOMIC zone: intent+planning skipped
✅ PRECISION zone: all active
✅ EXPLORE zone: planner skipped
✅ 10 consecutive runs: meta triggers at least once
✅ Cost control: ATOMIC 6 chains vs PRECISION 9 chains
✅ Pipeline integrity: core chains always run
```

## Zone Cost Matrix

| Zone | Chains Triggered | Skipped | Savings |
|------|:---:|:---:|:---:|
| ATOMIC | 6 | 4 (intent,planning,profile,meta) | -40% |
| PRECISION | 9 | 1 (profile) | -10% |
| EXPLORE | 7 | 3 (planning,profile,meta) | -30% |
| ABYSS | 9 | 1 (profile) | -10% |
| PSYCHE | 7 | 3 (planning,profile,meta) | -30% |
| MIXED | 7 | 3 (planning,profile,meta) | -30% |
