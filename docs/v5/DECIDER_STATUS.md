# 网状业务链 · Decider 接入状态

> 2026-07-22 · 9/9 链全部接入 Decider

---

## 事件流 (12 类型)

```
on_event Tick:
  user_message → PCR → routing → intent → planning → context → llm
  → profile → behavior → abc → mind → meta
```

## 接入验证

```
Decider:   12 ticks, 12 events ✅
State:     pcr=UNKNOWN, intent=UNKNOWN, trust=0.5
所有链:   写入 Event Log ✅
```

## 链间消费 (有向图)

```
PCR ──→ RouterV4
PCR ──→ IntentParser
RouterV4 ──→ LLM (system instruction zone)
IntentParser ──→ Planner ──→ LLM
Context ──→ LLM (to_prompt)
LLM ──→ Profile
LLM ──→ Behavior
LLM ──→ ABC
LLM ──→ Mind
Behavior ──→ Meta
```

## 尚未建模的网状关系

```
Profile ──→ RouterV4 (画像 → 路由校准) ❌
Behavior ──→ Meta (行为模式 → 元认知审核) ❌
Meta ──→ Profile (审核结果 → 画像更新) ❌
```

这些需要链间**双向通信**——当前 Decider 只记录事件，不推动消费。下一步做条件触发。
