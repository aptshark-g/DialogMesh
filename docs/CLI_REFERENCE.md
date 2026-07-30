# DialogMesh CLI 参考手册 v6.2

> 最后更新: 2026-07-30 · 128/173 命令 (74%)
> 测试: 28/28 green · v6 API: 17/17 200 OK · 子系统: 17/17 在线

## 架构概览

```
CLI (dm) ──→ 引擎属性 ──→ 内存缓存 (HotStore) ──→ 磁盘 (JSON/SQLite)
                │                                      │
                └── StateMachine 管线 ──→ 8 phases ──→ PERSIST
                                                         │
                                              ┌──────────┘
                                              ▼
                                        v6 API (:8000) ──→ 前端 (:5173)
```

## 数据流

```
写路径: StateMachine PERSIST
  → _persist_disk_file()  磁盘持久化
  → _cache_hot()          内存缓存 (sub-μs)

读路径: CLI _disk() / v6 API
  → HotStore.get()        内存命中 (sub-μs) 
  → 磁盘读取               未命中 (10ms) → 自动缓存
```

---

## 模块状态 (更新)

| 模块 | 设计 | 实际 | % | 数据源 | 状态 |
|------|:----:|:----:|:--:|--------|:----:|
| engine | 5 | 5 | 100 | _state | ✅ |
| session | 7 | 7 | 100 | v3_sessions.json | ✅ |
| discourse | 16 | 12 | 75 | _discourse_tree, disk | ✅ rich |
| pcr | 6 | 6 | 100 | _pcr_router | ✅ |
| intent | 7 | 7 | 100 | _last_intent | ✅ |
| context | 3 | 3 | 100 | _last_context | ✅ |
| subgraph | 2 | 2 | 100 | _subgraph | ✅ |
| blueprint | 16 | 7 | 43 | BlueprintEngine | 🟡 |
| decider | 3 | 3 | 100 | _decider | ✅ |
| behavior | 9 | 5 | 55 | _behavior_graph_adapter | ✅ rich |
| meta | 8 | 5 | 62 | _meta_cognition | ✅ rich |
| assoc | 8 | 5 | 62 | _l1_modifier, _l2_5_belief | ✅ rich |
| obs | 9 | 9 | 100 | _observation_pool | 🟡 light |
| profile | 11 | 6 | 54 | _ocean_analyst.profile | ✅ rich |
| engineering | 6 | 1 | 16 | _engineering_knowledge | ✅ rich |
| concepts | 5 | 1 | 20 | 磁盘 | 🟡 thin |
| mind | 8 | 1 | 12 | _mind | ✅ rich |
| rules | 10 | 3 | 30 | _abc, disk | 🟡 light |
| abc | 1 | 1 | 100 | _abc | ✅ rich |
| annotations | 12 | 5 | 41 | disk + HotStore | ✅ rich |
| corrections | 1 | 1 | 100 | disk + HotStore | ✅ rich |
| feedback | 1 | 1 | 100 | disk + HotStore | ✅ rich |
| inertia | 1 | 2 | 100 | _inertia | ✅ rich |
| metrics | 1 | 1 | 100 | _sla_watchdog | ✅ rich |
| knowledge | 9 | 5 | 55 | _rag_bridge, _frame_library | ✅ |
| task | 12 | 11 | 91 | _task_graph (disk) | ✅ |
| learning | 3 | 3 | 100 | _learning_sources | ✅ |

**总计: 128/173 (74%) · Rich: 13 模块 · Light: 4 模块**

---

## 深度引擎对象 (17/17 在线)

| 对象 | 用途 | 对应设计 |
|------|------|---------|
| `_ocean_analyst` | OCEAN 人格分析 | Runtime Kernel §3 |
| `_meta_cognition` | 元认知审查 | MetaCognition Runtime |
| `_inertia_graph` | 惰性权重图 | P5 Inertia |
| `_behavior_discovery` | 行为模式发现 | P3 Behavior |
| `_engineering_knowledge` | 工程知识图 | P4 Engineering |
| `_abc` | ABC 编排器 | P5 ABC |
| `_mind` | 统一认知结构 | P4 Mind |
| `_state_machine` | 状态机 (8 phases) | Global State Machine |
| `_storage` | Hot/Warm/Cold 三层 | Runtime Kernel §3.3 |
| `_tracer` | 管线追踪器 | Runtime Kernel §4 |
| `_event_log` | 事件日志 (SQLite) | EventBus V2 |
| `_decider` | 全局决策器 | Global State Machine |
| `_rag_bridge` | RAG 知识检索 | Knowledge |
| `_frame_library` | 框架库 | Knowledge |
| `_learning_sources` | 5源学习摄入 | Learning Ingestion |
| `_content_fetcher` | 内容抓取器 | Learning Ingestion |
| `_credibility_eval` | 可信度评估 | Learning Ingestion |

---

## 缓存架构

```
HotStore (Python dict, LRU 1000)
  ├── 写入: StateMachine PERSIST 自动填充
  ├── 读取: CLI _disk() 优先命中
  └── 特性: sub-μs, Per-Engine 隔离

WarmStore (SQLite+WAL)
  ├── EventLog 事件日志
  └── 特性: ms 读取, 事务安全

ColdStore (JSON disk + ChromaDB 插拔)
  ├── annotations/corrections/feedback
  ├── discourse tree state
  └── 特性: 10ms+ 读取, 持久化

Redis (Week 4, 插拔式)
  └── 分布式时才激活, 默认降级到 HotStore
```

## 版本历史

- v6.2 (2026-07-30): HotStore 缓存层, StateMachine 管线持久化, 7 深度对象接入
- v6.1 (2026-07-30): 128/173 命令审计, 引擎属性映射
- v6.0 (2026-07-28): 初始 CLI 设计
