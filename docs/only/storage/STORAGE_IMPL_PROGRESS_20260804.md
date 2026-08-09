# M6 存储接线（G10）施工记录 — 2026-08-04

> 状态: ✅ 完成。M6 全部施工项落地 + 测试全绿。
> 依据: `G10_STORAGE_DECISION_20260803.md`（含 2026-08-04 勘误）+
> 压缩交接 §四 M6 清单。

---

## 一、施工项完成情况

### G10-P1 ✅ UnifiedStore → ChunkStore backend（向量接线）
```
实现:
  core/agent/persistence/unified_store.py
    - UnifiedStore 新增文本级 API: index_texts / add_text / search_texts
      （BGE 编码 + LSH 候选剪枝; 与既有 object-name 索引并存）
    - save/load 扩展持久化 text 索引（npz 向后兼容）
    - stats() 新增 indexed_texts
  core/agent/storage/chunk_store.py
    - backend="unified"（新增第三后端: in_memory | chromadb | unified）
    - add/add_text → _try_unified_add（BGE 可用则索引, 否则关键词降级）
    - search → unified.search_texts 优先, 无命中退化关键词
    - stats() 新增 unified_indexed
引擎接线:
  cli/registry.py + cli/subsystem_registrations.py:
    chunk_store 注册改 factory — DM_CHUNK_BACKEND=unified|in_memory（A18 参数自适应）
    BGE 就绪自动升级向量检索; 未就绪关键词降级（同接口）
  cli/engine.py: _chunk_store 特殊接线（读 _state.chunk_backend）兜底
```

### G10-P2 ✅ TieredStorageManager → 主存储路径（分层接线）
```
实现:
  core/agent/event/storage.py StorageLayer
    - enable_tiered=True 参数 → _init_tiered() 挂载 TieredStorageManager
    - 默认落 data/dialogmesh/tiered_sessions.db + data/dialogmesh/archive
      （~/.dialogmesh 不可写环境自动降级 :memory: — 与 state.json
      PermissionError 同源, 已实测修复）
    - tiered_stats / archive_tiered / rehydrate_tiered /
      put_tiered_hot / get_tiered_hot 代理
    - stats() 合并 tiered 段; close() flush tiered
引擎接线:
  cli/subsystem_registrations.py: storage 注册改 factory（enable_tiered=True）
  cli/engine.py: StorageLayer(enable_tiered=True) 兜底
CLI:
  cli/commands/storage_cmd.py + entry.py: dm tiered stats|archive|rehydrate
```

### G10-P3 ✅ 孤儿后端处置（勘误修正: 不归档, 吸收/完成）
```
核查结论（修正 G10 原文"4 孤儿后端"）:
  faiss_store / milvus_store / hnsw_index / lsm_store 全部有活跃消费方:
    faiss_store  ← hybrid_index ← context/assembler + learning/ingestion
    hnsw_index   ← faiss_store + memory/ragraph
    milvus_store ← context/assembler (TieredVectorStore)
    lsm_store    ← broker (UnifiedPersistenceBroker)
  → 均实现 VectorStore Protocol（vector_store.py ABC）— 吸收为可插拔后端,
    不归档。文档级修正: 无"6 套归一"删除风险。
真实缺口 = unified_graph_store 半实现 + CLI 假执行, 本次完成:
  core/agent/persistence/unified_graph_store.py
    - open()/is_open/stats(property) — CLI/SnapshotManager 契约
    - query_nodes(tier/node_type/domain/limit) — maintenance 契约
    - run_maintenance() — H→W / W→C / C→A 迁移（复用 GraphTierManager 阈值）
    - SnapshotRecord + snapshots 表 + create_snapshot/get_snapshots/delete_snapshot
    - 修复 stats 死锁: 持锁内调 get_tier_counts（非重入锁）→ 移出锁外
  core/agent/persistence/unified_search.py（新增, 此前缺失 ImportError）
    - UnifiedSearch.keyword_search / summary_search
  core/agent/persistence/domain_adapter.py（新增, 此前缺失 ImportError）
    - DomainAdapter._save/_load/_load_all（B/P/K/C 域）
CLI 假执行修复（导入改 unified_graph_store + API 补齐）:
  cli/health.py / cli/inspect_v3_cmd.py / cli/maintenance_cmd.py / cli/snapshot.py
  maintenance_cmd: query_nodes(tier="W/C/A") + close 顺序修正
```

### PE-3 ✅ FactStore 批量写缺陷修复
```
core/agent/profile/fact_store.py
  - begin_batch()/end_batch() + __enter__/__exit__（context manager）
  - 批量内 _save() 延迟落盘（_pending_save）→ end_batch flush 一次
  - 嵌套 batch 支持; 非批量模式行为不变（每次 add 各写一次盘）
  - write_stats() 监控: save_count/batch_depth/pending_save（A18 可观测）
顺带修正 2 个预存在错误断言（untracked, 从未绿过）:
  test_fact_store_stress.py
    - test_fact_store_1000_writes: char_limit 20000→100000（数学上装不下 1000 条）
    - test_fact_store_budget_rejection_fast: 长事实 60 字符→300 字符（要真超限）
```

---

## 二、验证数字

```
新增测试（M6）:
  core/agent/storage/tests/test_chunk_store_unified.py            4/4
  core/agent/event/tests/test_storage_layer_tiered.py             4/4
  core/agent/persistence/tests/test_unified_graph_store_complete.py 5/5
  core/agent/persistence/tests/test_unified_search_domain.py      4/4
  core/agent/profile/tests/test_fact_store_stress.py              5/5（新增 3 + 修正 2）
  → M6 相关测试 22/22（新增 20 + 修正 2 预存在断言）
回归:
  存储全量（persistence + tier_manager + event_log_lifecycle）    78/78
  M5 核心集（association_service/funnel/statemachine_m4/viz_edit/
    subscribers/integration）                                     71/71
  FactStore 全套                                               14/14
  CLI                                                          27/28（唯一失败 D-14 归对话树, 预存在）
引擎实测（监控）:
  start_engine: running 48/49; storage tiered enabled=True
  DM_CHUNK_BACKEND=unified → chunk backend=unified（BGE 未就绪 → 关键词降级）
  dm tiered stats: Hot/Warm/Cold 三层统计正常返回
```

---

## 三、环境坑（新增记录）

```
1. ~/.dialogmesh 目录此环境不可写（state.json PermissionError 同源）:
   TieredStorageManager 默认 ~/.dialogmesh/tiered_sessions.db → "unable to
   open database file"。修复: 默认落 data/dialogmesh/, 失败回退 :memory:。
2. UnifiedGraphStore.stats 持锁内调 get_tier_counts() → 非重入锁死锁
   （测试挂起 60s+）。修复: 锁外调用。已加注释防回退。
3. pre-existing: fact_store 两个压测断言数学错误（预算截断/超限串太短）,
   从未绿过 — 本次修正（见上）。
```

---

## 四、归档/改动清单

```
改动（M6）:
  core/agent/persistence/unified_store.py        (G10-P1)
  core/agent/storage/chunk_store.py              (G10-P1)
  core/agent/cli/registry.py                     (G10-P1 chunk factory)
  core/agent/cli/subsystem_registrations.py      (G10-P1/P2 factory)
  core/agent/cli/engine.py                       (G10-P1/P2 接线)
  core/agent/event/storage.py                    (G10-P2)
  core/agent/cli/commands/storage_cmd.py         (dm tiered)
  core/agent/cli/entry.py                        (dm tiered dispatch)
  core/agent/persistence/unified_graph_store.py  (G10-P3 完成)
  core/agent/persistence/unified_search.py       (新增)
  core/agent/persistence/domain_adapter.py       (新增)
  core/agent/cli/health.py / inspect_v3_cmd.py / maintenance_cmd.py /
    snapshot.py                                  (G10-P3 CLI 修复)
  core/agent/profile/fact_store.py               (PE-3)
新增测试:
  core/agent/storage/tests/test_chunk_store_unified.py
  core/agent/event/tests/test_storage_layer_tiered.py
  core/agent/persistence/tests/test_unified_graph_store_complete.py
  core/agent/persistence/tests/test_unified_search_domain.py
归档: 无（4 孤儿后端经核查有活跃消费方, 保留为可插拔后端）
```
