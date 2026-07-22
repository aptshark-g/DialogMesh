# 设计对齐核查

> 2026-07-22 · 混合架构 DES DESIGN_HYBRID_ARCHITECTURE.md

---

## 对齐状态

| 设计要求 | 代码实现 | 状态 |
|------|------|:---:|
| EventLog (SQLite append-only) | `api_event_log.py` EventLog.put_event() | ✅ |
| EventBus (环形缓冲 pub/sub) | `event_bus.py` EventBus.publish/subscribe | ✅ |
| PCR publish | `self._publish(ET.PCR_COMPUTED.value)` | ✅ |
| Router publish | `self._publish(ET.ROUTE_GENERATED.value)` | ✅ |
| Intent publish | `self._publish(ET.INTENT_PARSED.value)` | ✅ |
| Planner publish | `self._publish(ET.PLAN_GENERATED.value)` | ✅ |
| Context publish | `self._publish(ET.CONTEXT_COMPILED.value)` | ✅ |
| LLM publish | `self._publish(ET.REPLY_GENERATED.value)` | ✅ |
| Profile publish | `self._publish(ET.PROFILE_UPDATED.value)` | ✅ |
| Behavior publish | `self._publish(ET.BEHAVIOR_RECORDED.value)` | ✅ |
| ABC publish | `self._publish(ET.ABC_EVALUATED.value)` | ✅ |
| Mind publish | `self._publish(ET.MIND_LEARNED.value)` | ✅ |
| Meta 订阅 8 事件 | PCR+Route+Intent+Reply+Profile+Behavior+ABC+Mind | ✅ |
| Assoc 订阅 5 事件 | PCR+Route+Intent+Reply+Behavior | ✅ |
| 热路径不变 | on_event() 同步管道 | ✅ |
| 冷路径隔离 | Meta+Assoc 独立 subscriber, 不阻塞热路径 | ✅ |

---

## 验证数据

```
EventLog:  data/test_align.db ✅
EventBus:  13 subscribers, 0 dropped  ✅
Meta:      40 turns, 5 behaviors      ✅
Assoc:     intent=ANALYZE, 5 behaviors ✅
测试:      96/96 PASS                  ✅
```

## 剩余差距

| 项目 | 状态 |
|------|:---:|
| EventLog.tail() for incremental replay | ❌ 未添加, put_event 已覆盖 |
| Association 关联发现逻辑 | ⚠️ 基础框架, 需接入 v3_2/fusion/ |
| 冷→热回写 (Meta→Intent, Assoc→Context) | ❌ 待实现 |
| Decider/Trigger 清理 | ⚠️ 保留兼容, 热路径仍同时走 Decider |
