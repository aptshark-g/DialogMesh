# 持久化层深层次复核（第二轮·实锤验证）

> 日期: 2026-08-03 | 对象: `persistence/`（32 源码）+ `event/storage.py` +
> `v4/persistence/__init__.py` + `cli/engine.py` + 环境依赖
> 方法: 源码精读 + 全库 rg（消费/赋值点）+ 运行时探针（依赖可用性）
> 结论: **第一轮 1 处说法修正（StorageLayer 非孤儿但零关联）；新实锤
> `PersistenceWiring.wire` 零调用方（v4 持久化门面是死代码）；环境依赖三分：
> faiss/jieba 可用、chromadb/sentence_transformers/stanza/hnswlib/pymilvus 不可用**。

---

## 一、第一轮修正

### 1.1 「event/storage.py StorageLayer 孤儿」→ 非孤儿，但与 persistence/ 零关联
```
cli/engine.py:246-247  _engine._storage = StorageLayer()（start_engine 挂载）
event/handlers.py:44    _persist_disk_file → store.hot.set(...)（StateMachine PERSIST 阶段写热缓存）
cli/commands/p5_cmd.py:19,36  诊断/写热缓存
event/tests/test_storage.py    21 passed
→ StorageLayer 被 CLI 挂载 + StateMachine PERSIST handler 使用
```
**修正后的准确表述**:
```
StorageLayer（event/storage.py）与 persistence/ 各 Store 之间零关联：
StateMachine PERSIST 阶段只写 _storage 的 hot/cold 文件缓存，
不经 persistence/ 的 SQLite/图/向量体系 —— 两条持久化主干并存但互不相通。
```

---

## 二、新实锤: v4/persistence 门面是死代码

```
v4/persistence/__init__.py:17  class PersistenceWiring: wire(engine) → 挂 AnnotationStore/UnifiedStore + 迁移
全库 rg: PersistenceWiring / .wire(engine) 零调用方（仅定义）
→ v4 宣称的 P2 持久化接线（Mind→AnnotationStore / PatternLearner / Neuro-symbolic 规则）
  从未被任何引擎路径调用
```

---

## 三、六套存储体系能力矩阵（复核后）

| 体系 | 代表实现 | 生产消费 | 依赖 | 可用性 |
|---|---|:--:|---|:--:|
| 会话 | CLISessionPersistence / SQLiteSessionStore | v3_common 桥 ✅ | sqlite3 | ✅ 45 测试绿 |
| 图 | GraphStore / UnifiedGraphStore / GraphTierManager | CLI 运维 ✅ | sqlite3 | ✅ |
| 向量 | SQLiteVectorStore / Faiss / HybridIndex | context/assembler ✅ | numpy/faiss | ✅(SQLite/faiss) |
| 向量(重) | Milvus / HNSW / chromadb | 无生产消费 | pymilvus/hnswlib 未装 | ❌ |
| 事件 | UnifiedEventLog / ChainedEventLog / api_event_log | 关联链服务 ✅ | sqlite3 | ✅ |
| 分层 | TieredStorage / WindowSnapshot / WaveQuery | 无生产消费（延迟导入）| sqlite3 | ✅(单测) |
| 统一 | UnifiedStore / v4 PersistenceWiring | 零调用 | BGE(sentence_transformers) | ❌ 断链+降级 |

**关键:**
- 真正在生产的: CLISessionPersistence（v3 桥）、UnifiedGraphStore（CLI 运维）、
  SQLiteVectorStore/HybridIndex（context 组装）、api_event_log（关联链 Event Sourcing）。
- 「统一」体系（UnifiedStore/v4 PersistenceWiring）零调用 + BGE 依赖不可用。
- HNSW/Milvus/chromadb 全部不可用（依赖缺失）→ 向量体系实际只有 SQLiteVectorStore/Faiss/HybridIndex。

---

## 四、环境依赖（探针实证）

```
numpy 2.0.2 OK | faiss 1.13.0 OK | jieba OK | nats OK | sqlite3 内置
chromadb FAIL（pydantic_settings 缺失）→ ChromaBridge available=False
sentence_transformers FAIL（numpy 版本比较 ValueError）→ BGE 不可用 → UnifiedStore 向量检索失效
stanza FAIL（同上）→ StanzaCorefResolver 降级
hnswlib / pymilvus 未安装 → HNSWIndex / MilvusVectorStore 不可用
```

---

## 五、FactStore 批量写缺陷（既有待办，复核确认仍在）

```
画像审计遗留: FactStore 每次 add 全量落盘 = 磁盘 thrash
修复方向已记录（内存脏标记 + apply_batch + 显式 save），未实施
```

---

## 六、待拍板/待修复清单（持久化）

| # | 级别 | 事项 | 方向 |
|---|---|---|---|
| D1 | P0 | v4 PersistenceWiring 零调用（P2 接线未落地）| 接引擎启动路径或归档 |
| D2 | P1 | 两套持久化主干（StorageLayer vs persistence/）归一 | 存储架构拍板（SQLite WAL/FTS5/vec 抽象/PG/redis 热层）|
| D3 | P1 | 依赖治理（stanza/sentence_transformers numpy 比较 bug）| 修 numpy 版本或降级 BGE 实现 |
| D4 | P2 | HNSW/Milvus/chromadb 未装 | 按存储架构拍板决定去留 |
| D5 | P2 | FactStore 批量写缺陷 | 按已记录方向实施 |
| D6 | P2 | 6 套体系收敛 | 全局讨论（复用 tiered/window/wave 中可用件）|
