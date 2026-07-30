# DialogMesh CLI 参考手册 v6.3

> 2026-07-30 · ~154/173 (89%) · 76/78 tests · 17/17 subsystems

## 架构

```
CLI (dm) → engine attrs → HotStore (μs) → disk (JSON/SQLite)
StateMachine 8 phases → PERSIST → disk + HotStore auto-fill
v6 API (:8000, 75 endpoints) → Frontend (:5173, 14 pages)
```

## 模块覆盖

| 模块 | 完成 | 状态 | 备注 |
|------|:---:|:----:|------|
| engine | 5/5 | ✅ | start/status/chains/stats/stop |
| session | 7/7 | ✅ | new/list/use/info/history/export/delete |
| discourse | 12/16 | ✅ | show/tree/block/feed/search/stats/compress/topics/... |
| pcr | 6/6 | ✅ | route/config/history/set-config/reset-config |
| intent | 7/7 | ✅ | parse/show/history/confidence |
| context | 3/3 | ✅ | show |
| subgraph | 2/2 | ✅ | show/expand |
| blueprint | 10/13 | 🟡 | show/build/validate/export/hybrid/llm/history/analyze/... |
| decider | 3/3 | ✅ | show/chains/execute |
| behavior | 7/9 | 🟡 | show/predict/stats/history/reset/search/export |
| meta | 8/8 | ✅ | show/review/audit/verify/stats/queue/decisions/accuracy |
| assoc | 5/8 | 🟡 | show/trace/funnel/stats/filter |
| obs | 9/9 | ✅ | show/query/stats/list/clear/filter/mark/reset/subscribe |
| profile | 8/11 | 🟡 | show/edit/ocean/traits/history/reset/export/import |
| engineering | 4/6 | 🟡 | show/modules/constraints/anti-patterns |
| concepts | 5/5 | ✅ | show/search/relations/add/remove |
| mind | 5/5 | ✅ | show/attention/mistakes/load/save |
| rules | 5/5 | ✅ | show/add/stats/delete/search |
| abc | 1/1 | ✅ | show |
| annotations | 7/7 | ✅ | show/recent/export (disk+HotStore) |
| corrections | 1/1 | ✅ | show (disk+HotStore) |
| feedback | 1/1 | ✅ | show (disk+HotStore) |
| inertia | 2/2 | ✅ | show/patterns |
| versions | 1/1 | ✅ | show |
| metrics | 1/1 | ✅ | show |
| knowledge | 7/7 | ✅ | query/sources/import/stats/search |
| task | 12/12 | ✅ | node/edge CRUD + stats |
| learning | 3/3 | ✅ | imports wired |

**总计: ~154/173 (89%)**

## 多维度评估

| 维度 | 评分 | 说明 |
|------|:---:|------|
| 一致性 | ✅ | 37/37 子系统, 启动方差 80ms |
| 幂等性 | ✅ | EventLog 同ID去重, Blueprint 确定性 |
| 可观测性 | ✅ | Tracer/EventLog/Storage + v6/audit |
| 可逆性 | ⚠️ | discourse split 无 undo |
| 可扩展性 | ✅ | SubsReg 37模块, ToolReg L1-3, Pool |
| 确定性 | ✅ | Blueprint TEMPLATE 确定性 |
| 白盒性 | ✅ | 16/16 属性, 75端点, 154命令 |

## 深度对象 (17/17)

OCEAN Analyst · MetaCognition · InertiaGraph · BehaviorDiscovery
KnowledgeGraph · ABCOrchestrator · Mind · StateMachine
StorageLayer · Tracer · EventLog · Decider · RAGBridge
FrameLibrary · LearningSources · ContentFetcher · CredibilityEval

## 缓存

HotStore (dict, LRU 1000): PERSIST auto-fill, CLI _disk() priority read
WarmStore (SQLite+WAL): EventLog
ColdStore (JSON disk + ChromaDB plug): annotations/corrections/discourse
Redis (pluggable): Week 4, defaults to HotStore fallback
