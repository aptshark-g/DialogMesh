# 持久化层（04）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/persistence/`（32 源码 + 2 测试文件）+
> `core/agent/event/storage.py` + `core/agent/api/api_event_log.py` + `core/agent/v4/persistence/` +
> 相关接线（context / learning / v3_common / cli）
> 结论先行: **持久化层是「组件最全、统一最差」的模块** —— 33+ 个存储实现分属
> 至少 6 个体系（会话/图/向量/事件/分层/统一），`UnifiedGraphStore` 是 CLI 运维主消费，
> `CLISessionPersistence` 是 v3_common 集成桥主消费，**但两者互不相通**；`event/storage.py`
> 的 StorageLayer 与 `persistence/` 各 Store 零关联。测试 45/45 绿但全是孤立单测。

---

## 一、文件清单与体系分类（32 源码文件）

### A. 会话/图存储体系（session + graph）
| 文件 | 体量 | 定位 |
|---|--:|---|
| `models.py` | 5.7KB | Session / TurnRecord / SessionSummary（v3_common 桥主契约）|
| `session_manager.py` | 9.0KB | SessionManager |
| `sqlite_store.py` | 12.1KB | SQLiteSessionStore（会话+turn 持久化）|
| `graph_store.py` | 17.9KB | GraphStore（节点/边/实体/向量混合）|
| `unified_graph_store.py` | 7.9KB | UnifiedGraphStore（~/.memorygraph 图库）|
| `graph_tier_manager.py` | 4.0KB | GraphTierManager（分层图）|
| `dialogue_tree_adapter.py` | 11.0KB | DialogueTreePersistenceAdapter（对话树适配）|
| `topic_tree_adapter.py` | 1.7KB | TopicTreeAdapter（主题树适配）|

### B. 向量/混合检索体系
| 文件 | 体量 | 定位 |
|---|--:|---|
| `vector_store.py` | 6.5KB | VectorStore ABC + SQLiteVectorStore + MilvusVectorStore |
| `faiss_store.py` | 7.1KB | FaissVectorStore |
| `milvus_store.py` | 9.2KB | MilvusVectorStore（独立重复实现）|
| `hnsw_index.py` | 14.4KB | HNSWIndex（磁盘图索引）|
| `hybrid_index.py` | 7.2KB | HybridIndex（关键词+向量混合）|
| `hybrid_hyde.py` | 1.7KB | HybridSearchEngine + HyDERetriever |
| `fts5_index.py` | 6.9KB | FTS5Index（SQLite FTS5）|
| `entity_index.py` | 12.8KB | EntityIndex（实体索引）|

### C. 事件/日志体系
| 文件 | 体量 | 定位 |
|---|--:|---|
| `unified_event_log.py` | 5.0KB | UnifiedEventLog |
| `chained_event_log.py` | 4.8KB | ChainedEventLog（链式事件）|
| `broker.py` | 8.6KB | UnifiedPersistenceBroker（统一入口）|
| `audit_trail.py` | 5.2KB | AuditTrail |
| `snapshot.py` | 4.8KB | SnapshotManager |

### D. 分层/窗口体系
| 文件 | 体量 | 定位 |
|---|--:|---|
| `tiered_storage.py` | 13.3KB | TieredStorageManager（热/温/冷）|
| `window_snapshot.py` | 13.1KB | WindowSnapshotStore（窗口快照+历史）|
| `wave_query.py` | 11.4KB | WaveQueryEngine（波查询/BFS）|

### E. 统一/安全/桥接体系
| 文件 | 体量 | 定位 |
|---|--:|---|
| `unified_store.py` | 9.9KB | AnnotationStore + UnifiedStore（BGE 向量）|
| `unified_graph_store.py` | 7.9KB | UnifiedGraphStore（见 A）|
| `store_safety.py` | 3.3KB | SafeUnifiedStore / SafeUnifiedSearch |
| `cli_middleware.py` | 7.0KB | CLISessionPersistence（v3_common 桥主消费）|
| `base.py` | 1.6KB | 基础类型 |
| `multi_domain_adapters.py` | 3.5KB | Behavior/UserProfile/Causal 适配 |
| `rust_bridge.py` | 2.0KB | Rust 桥（探测）|
| `lsm_store.py` | 12.4KB | LSMStore（LSM 日志结构）|
| `annotation_store.py` | 4.1KB | NodeAnnotationStore |

---

## 二、消费矩阵（全库 rg 实证）

### 2.1 主消费链路（真实接线）
```
v3_common/integration_bridge.py:34     from core.agent.persistence import CLISessionPersistence, TurnRecord
pcr/tests/intent_trace_cli.py:58       同上（pcr 意图追踪 CLI）
→ CLISessionPersistence = v3 主会话持久化桥

cli/health.py:35 / maintenance_cmd.py:8,27 / snapshot.py:8,32-33 / inspect_v3_cmd.py:97,102
→ UnifiedGraphStore + SnapshotManager + TieredGraphStore = CLI 运维主消费

context/assembler.py:22-24              SQLiteVectorStore + MilvusVectorStore + HybridIndex + KeywordIndex
learning/ingestion.py:155               HybridIndex（延迟导入）
learning/chroma_store.py:291            TurnRecord（延迟导入）
```

### 2.2 间接/门面消费
```
engineering/persistence.py + persistence_full.py:5   UnifiedGraphStore（工程链，见工程链审计）
v4/persistence/__init__.py                           PersistenceWiring.wire(engine)（AnnotationStore + UnifiedStore + 迁移）
v4/cognitive_scheduler/tasks.py:47                   TieredGraphStore（延迟导入）
v4/cognitive/*                                       AnnotationStore（mind/patterns/rules 迁移）
```

### 2.3 event/storage.py（StorageLayer 热/温/冷）
```
→ 生产消费方：未在 rg 中发现（StorageLayer 无 import 方）—— 与 persistence/ 各 Store 零关联。
```

---

## 三、测试现状（实锤）

```
core/agent/persistence/tests/   ✅ 45 passed（4.41s）
  test_persistence.py      16 passed
  test_persistence_graph.py 29 passed
```

**性质:** 全为孤立类单测（自建 store/临时目录），**无一条验证生产接线**；
无并发/压测/真实数据测试；`test_persistence.py:180` 仅覆盖 profile JSON 往返。
`event/tests/test_storage.py` 21 passed（HotStore/WarmStore/ColdStore 单测）。

---

## 四、实锤线索（第一轮）

1. **至少 6 套存储体系并存且互不相通**:
   会话（SQLiteSessionStore/CLISessionPersistence）| 图（GraphStore/UnifiedGraphStore）|
   向量（SQLiteVectorStore/Faiss/Milvus/HNSW/HybridIndex）| 事件（UnifiedEventLog/ChainedEventLog）|
   分层（TieredStorage/WindowSnapshot）| 统一（UnifiedStore/UnifiedGraphStore/Broker）。
2. **两套「统一」互相打架**: `unified_store.py`（AnnotationStore+UnifiedStore，v4 用）
   vs `unified_graph_store.py`（图库，CLI 用）——「统一」名不副实。
3. **MilvusVectorStore 重复实现**（vector_store.py + milvus_store.py 各一份）。
4. **event/storage.py StorageLayer 是孤儿**（无生产消费）。
5. **rust_bridge.py 是探测壳**（无真实 Rust 实现证据）。
6. **v3_common 主链路与 CLI 运维链路不互通**（CLISessionPersistence vs UnifiedGraphStore）。
7. **存储架构拍板未决**（SQLite WAL/FTS5/sqlite-vec/PG 抽象/redis 热层，见 STATE_HANDOFF 待办）。

---

## 五、待第二轮确认清单

- [ ] 设计文档: `BUSINESS_CHAIN_04_META_PERSIST.md` + `project/design_persistence.md` +
  `v3.0/DESIGN_UNIFIED_PERSISTENCE.md` + `v3.0/ENGINEERING_PERSISTENCE.md` +
  `v3.0/ENGINEERING_DATA_MODEL.md` + `v3.0/DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md` 精读
- [ ] 6 套体系的实际能力矩阵（哪个能用、哪个是壳）
- [ ] event/storage.py StorageLayer 设计意图 vs 现状（关联执行层/StateMachine）
- [ ] UnifiedStore 的 BGE 依赖是否可用（环境坑：numpy 坏 → stanza/BGE 静默降级）
- [ ] GraphStore vs UnifiedGraphStore vs graph_tier_manager 的关系图
- [ ] 持久化 ↔ 元认知（meta 状态）/行为链（记录）接口现状

---

## 六、勘误（深层次复核后）

> 见 `docs/only/persistence/DEEP_AUDIT_20260803.md`。修正 1 处: `event/storage.py` StorageLayer
> **并非孤儿**——cli/engine.py:247 挂载 `_engine._storage` + StateMachine PERSIST handler 使用
> （hot/cold 文件缓存）。但**与 persistence/ 各 Store 零关联**的结论不变（两条主干并存）。
> 新实锤: `v4/persistence` PersistenceWiring.wire 零调用方（死代码）。
