# DialogMesh CLI 参考手册 v6.4

> 2026-07-31 · 1324 tests collected, 0 errors · 17/17 subsystems

## 架构

```
CLI (dm) → Registry DI (37 subs) → on_event_sm (单轨)
StateMachine 8 phases → PERSIST → disk + HotStore
v6 API (:8000, 75 endpoints) → Frontend (:5173)
```

## 模块覆盖

| 模块 | 完成 | 状态 |
|------|:---:|:----:|
| engine | 5/5 | ✅ |
| session | 7/7 | ✅ |
| discourse | 16/16 | ✅ |
| pcr | 6/6 | ✅ |
| intent | 7/7 | ✅ |
| blueprint | 13/13 | ✅ |
| decider | 3/3 | ✅ |
| behavior | 9/9 | ✅ |
| meta | 8/8 | ✅ |
| assoc | 8/8 | ✅ |
| obs | 9/9 | ✅ |
| profile | 10/10 | ✅ |
| concepts | 5/5 | ✅ |
| mind | 5/5 | ✅ |
| rules | 5/5 | ✅ |
| engineering | 4/4 | ✅ |
| annotations | 7/7 | ✅ |
| knowledge | 7/7 | ✅ |
| task | 12/12 | ✅ |
| learning | 3/3 | ✅ |

**总计: ~168/173 (97% 设计)**

## 架构改进 (本日)

| 改进 | from | to |
|------|------|----|
| engine.py | 3734 行 | 805 行 (-78%) |
| 入口 | on_event + on_event_sm (双轨) | on_event_sm 单轨 |
| DI | 手动 try/except | Registry 37 subs |
| 测试 | 56 collection errors | 0 errors |
| v3_2 | 3 errors block | 195/200 pass |

## 多维度评估

| 维度 | 评分 | 变化 |
|------|:---:|:----:|
| 一致性 | 8/10 | ✅ |
| 幂等性 | 7/10 | ✅ |
| 可观测性 | 7/10 | ✅ |
| 可逆性 | 7/10 | ✅ (discourse undo) |
| 可扩展性 | 8/10 | ✅ (registry DI) |
| 确定性 | 7/10 | ✅ |
| 白盒性 | 8/10 | ✅ |

**加权: 7.5/10**

## 深度对象 (37/37 registry)

OCEAN · MetaCognition · Mind · ABC · StateMachine
StorageLayer · Tracer · EventLog · Decider · RAGBridge
FrameLibrary · BehaviorGraph · TopicTree · Inertia · KG
LearningSources · ContentFetcher · CredibilityEval · +19 more

## 缓存

HotStore (dict, LRU 1000): PERSIST auto-fill, CLI priority read
WarmStore (SQLite+WAL): EventLog
ColdStore (JSON + ChromaDB plug): annotations/corrections/discourse
