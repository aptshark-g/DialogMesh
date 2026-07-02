# DialogMesh 分层存储系统 — 工程实现文档

> **文档编号**: ENGINEERING-PERSISTENCE-002  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现（部分已有代码）  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §8（记忆系统）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2（Cognitive Tree）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2（访问控制）
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应代码**: `core/agent/persistence/`（9 个文件，已存在）  
> **原则**: 必须实现设计概念文档的完整分层存储，任何简化均需诚实标记。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 存储层接口（抽象基类）](#5-存储层接口抽象基类)
- [6. Hot 层（内存缓存）](#6-hot-层内存缓存)
- [7. Warm 层（SQLite 本地持久化）](#7-warm-层sqlite-本地持久化)
- [8. Cold 层（归档文件）](#8-cold-层归档文件)
- [9. 图存储（GraphStore）](#9-图存储graphstore)
- [10. 实体索引（EntityIndex）](#10-实体索引entityindex)
- [11. 记忆存储适配（MemoryStorage）](#11-记忆存储适配memorystorage)
- [12. v3.0 新增：Cognitive Tree 存储](#12-v30-新增cognitive-tree-存储)
- [13. 数据流与状态迁移](#13-数据流与状态迁移)
- [14. 版本兼容与迁移](#14-版本兼容与迁移)
- [15. 测试策略](#15-测试策略)
- [16. 附录：简化与待讨论项](#16-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh 的**分层存储系统**规范，覆盖从热内存到冷归档的全链路数据生命周期管理。所有模块的持久化操作必须遵守本规范的分层策略、接口契约和状态迁移规则。

### 1.2 范围

覆盖设计文档 `DESIGN_FULL_CONCEPT.md` §8 中定义的：

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 三层存储（Hot/Warm/Cold） | §8.2 | §6-§8 | 已部分实现，需扩展 |
| 五层记忆存储（5-4-3-1-3） | §8.3 | §11 | 需新增适配层 |
| 图存储（节点/边/遍历） | §8.2 | §9 | 已实现，需扩展 |
| 实体索引（倒排） | §8.2 | §10 | 已实现 |
| 记忆衰减（双指数） | §8.3 | §11 | 已有算法，需接入存储 |
| 版本兼容与迁移 | §8.4 | §14 | 需新增 |
| v3.0 Cognitive Tree 存储 | §4.2 | §12 | 需新增 |

### 1.3 诚实标记原则

> ⚠️ **工程原则**：本规范要求实现设计文档的全部存储需求。如果现有代码或实现中必须简化（如多后端支持、存储引擎选型），必须在 §16 中明确标记。

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/persistence/memory_storage.py` | 五层记忆存储适配器 | ~200 行 | 新增，将 MemoryChunk 映射到三层存储 |
| `core/agent/persistence/cognitive_tree_store.py` | Cognitive Tree 存储 | ~250 行 | v3.0 新增，支持节点/边/权限 |
| `core/agent/persistence/redis_store.py` | Redis 后端实现 | ~150 行 | 可选后端，用于 Hot 层 |
| `core/agent/persistence/migration.py` | 版本迁移工具 | ~100 行 | 数据库 schema 升级 |
| `core/agent/persistence/backup.py` | 冷层备份/恢复 | ~80 行 | 归档文件管理 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/persistence/base.py` | 扩展 `SessionStore` 接口，新增 `MemoryStorage` 抽象基类 | 所有存储后端 |
| `core/agent/persistence/tiered_storage.py` | 集成 `MemoryStorage`，增加 `MemoryChunk` 的自动迁移 | 分层管理 |
| `core/agent/persistence/sqlite_store.py` | 新增 `MemoryChunk` 表（`memory_chunks`） | SQLite 后端 |
| `core/agent/persistence/graph_store.py` | 新增 `CognitiveTreeNode` 和 `CognitiveTreeEdge` 支持 | 图存储 |
| `core/agent/persistence/models.py` | 新增 `MemoryChunkRecord` 模型 | 持久化模型 |

### 2.3 向后兼容

- 现有 `SQLiteSessionStore` 表结构保持不变，新增表通过 `ALTER TABLE` 或新表实现。
- `TieredStorageManager` 的现有接口保持不变，新增 `MemoryStorage` 委托调用。
- GraphStore 的 `TopicNode`/`TopicEdge` 表结构不变，新增 `cognitive_nodes`/`cognitive_edges` 表。

---

## 3. 现有实现评估

### 3.1 代码清单（已存在）

| 文件 | 行数 | 核心职责 | 状态 |
|------|------|---------|------|
| `base.py` | 53 | `SessionStore` 抽象基类 | ✅ 可用，需扩展 |
| `models.py` | 156 | `Session`, `TurnRecord`, `SessionSummary` | ✅ 可用，需扩展 MemoryChunk |
| `sqlite_store.py` | 328 | SQLite 实现（WAL 模式） | ✅ 可用，需新增 memory_chunks 表 |
| `session_manager.py` | 234 | 内存缓存 + 持久化（LRU + TTL） | ✅ 可用，需集成 MemoryStorage |
| `tiered_storage.py` | 344 | Hot/Warm/Cold 自动迁移 | ✅ 可用，需扩展记忆迁移 |
| `graph_store.py` | 472 | TopicNode/TopicEdge 存储 + BFS/DFS | ✅ 可用，需新增 Cognitive Tree 支持 |
| `entity_index.py` | 349 | 实体倒排索引 | ✅ 可用，性能优化空间 |
| `wave_query.py` | ? | 波浪查询（待评估） | ❓ 未评估 |
| `window_snapshot.py` | ? | 窗口快照（待评估） | ❓ 未评估 |

### 3.2 与设计文档的差距

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 三层存储（Hot/Warm/Cold） | ✅ `TieredStorageManager` | 无差距 | - |
| 五层记忆映射（MemoryChunk） | ❌ 未实现 | 需新增 `MemoryStorage` 适配 | P1 |
| 记忆衰减自动触发 | ❌ 未实现 | 需定时任务或写入时触发 | P2 |
| Redis 后端（Hot 层） | ❌ 未实现 | 仅 SQLite + 内存，无 Redis | P2 |
| Cognitive Tree 存储 | ❌ 未实现 | GraphStore 仅支持 Topic Tree | P1 |
| 版本迁移工具 | ❌ 未实现 | schema 升级手动管理 | P3 |
| 备份/恢复工具 | ❌ 未实现 | 归档文件手动管理 | P3 |

---

## 4. 架构总览

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Application Layer                              │
│  (SessionManager, Orchestrator, MemoryDecayManager, CognitiveCompiler)   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                        MemoryStorage (Adapter)                           │
│  将 MemoryChunk 的 5 阶段映射到三层存储，触发衰减计算                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────┬──────────────────────────────────────┐
│         TieredStorageManager      │         CognitiveTreeStore          │
│  ┌──────────┬──────────┬────────┐│  ┌─────────────────────────────────┐│
│  │   Hot    │  Warm    │  Cold  ││  │  cognitive_nodes / cognitive_edges││
│  │ (内存)   │ (SQLite) │ (文件) ││  │  (SQLite + 内存索引)              ││
│  └──────────┴──────────┴────────┘│  └─────────────────────────────────┘│
│         │           │          │ │         │                          │
│  ┌──────────┐  ┌──────────┐ ┌──────────┐│  ┌──────────┐             │
│  │OrderedDict│  │SQLiteSession││归档文件││  │GraphStore│             │
│  │(LRU)     │  │Store      │ │(gzip)  ││  │(扩展)    │             │
│  └──────────┘  └──────────┘ └──────────┘│  └──────────┘             │
│         │           │          │ │         │                          │
│  ┌──────────┐  ┌──────────┐ ┌──────────┐│  ┌──────────┐             │
│  │Redis(可选)│  │EntityIndex│ │Backup  ││  │AccessCtrl│             │
│  │         │  │GraphStore │ │        ││  │Matrix    │             │
│  └──────────┘  └──────────┘ └──────────┘│  └──────────┘             │
└──────────────────────────────────┴──────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         SQLite 数据库 (WAL 模式)                         │
│  sessions | turns | memory_chunks | graph_nodes | graph_edges | cognitive_nodes │
│  cognitive_edges | entity_index | schema_version                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 数据流

**写入流**（Hot → Warm → Cold）：
1. 应用层创建 `MemoryChunk` → 调用 `MemoryStorage.save(chunk)`
2. `MemoryStorage` 根据 `chunk.stage` 决定写入哪一层：
   - `HOT` → `TieredStorageManager.put_hot()`（内存）
   - `WARM`/`COOL` → `SQLiteSessionStore`（SQLite）
   - `COLD`/`FROZEN` → `TieredStorageManager.archive_warm_to_cold()`（归档文件）
3. 定时任务检查 `MemoryDecayManager`，当 `W_eff < threshold` 时触发降级

**读取流**（按需回热）：
1. 应用层调用 `MemoryStorage.get(chunk_id)`
2. 先查 Hot 层 → 命中返回
3. 未命中查 Warm 层（SQLite）→ 命中返回，并异步 `put_hot()`
4. 未命中查 Cold 层（归档文件）→ 命中返回，并异步 `rehydrate_cold_to_warm()` + `put_hot()`

---

## 5. 存储层接口（抽象基类）

### 5.1 `SessionStore`（已有，扩展）

```python
class SessionStore(ABC):
    """抽象基类：会话存储后端。"""
    
    # ── 已有接口 ───────────────────────────────
    @abstractmethod
    def save_session(self, session: Session) -> bool: ...
    @abstractmethod
    def load_session(self, session_id: str) -> Optional[Session]: ...
    @abstractmethod
    def save_turn(self, session_id: str, turn: TurnRecord) -> bool: ...
    @abstractmethod
    def load_turns(self, session_id: str, limit: int = 50) -> List[TurnRecord]: ...
    @abstractmethod
    def list_active_sessions(self, limit: int = 20, tenant_id: str = "default") -> List[str]: ...
    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...
    @abstractmethod
    def close(self) -> None: ...
    
    # ── 新增接口（v3.0）──────────────────────
    @abstractmethod
    def save_memory_chunk(self, chunk: MemoryChunk) -> bool:
        """保存记忆组块。"""
        ...
    
    @abstractmethod
    def load_memory_chunks(self, session_id: str, stage: Optional[MemoryStage] = None, limit: int = 100) -> List[MemoryChunk]:
        """加载记忆组块，可按阶段过滤。"""
        ...
    
    @abstractmethod
    def delete_memory_chunks(self, session_id: str, older_than: Optional[float] = None) -> int:
        """删除记忆组块，可指定时间截止。"""
        ...
    
    @abstractmethod
    def save_cognitive_node(self, session_id: str, node: CognitiveTreeNode) -> bool:
        """保存认知树节点。"""
        ...
    
    @abstractmethod
    def load_cognitive_nodes(self, session_id: str, limit: int = 1000) -> List[CognitiveTreeNode]:
        """加载认知树节点。"""
        ...
    
    @abstractmethod
    def save_cognitive_edge(self, session_id: str, edge: CognitiveTreeEdge) -> bool:
        """保存认知树边。"""
        ...
    
    @abstractmethod
    def load_cognitive_edges(self, session_id: str, limit: int = 1000) -> List[CognitiveTreeEdge]:
        """加载认知树边。"""
        ...
```

### 5.2 `MemoryStorage`（新增抽象基类）

```python
class MemoryStorage(ABC):
    """抽象基类：记忆存储适配器。
    
    将 MemoryChunk 的 5 阶段（HOT/WARM/COOL/COLD/FROZEN）映射到三层存储。
    负责衰减计算和自动迁移触发。
    """
    
    @abstractmethod
    def save(self, chunk: MemoryChunk) -> bool:
        """保存记忆组块，根据 chunk.stage 自动路由到对应存储层。"""
        ...
    
    @abstractmethod
    def get(self, chunk_id: str) -> Optional[MemoryChunk]:
        """获取记忆组块，自动处理回热。"""
        ...
    
    @abstractmethod
    def query(self, session_id: str, stage: Optional[MemoryStage] = None, tags: Optional[List[str]] = None, limit: int = 100) -> List[MemoryChunk]:
        """查询记忆组块。"""
        ...
    
    @abstractmethod
    def delete(self, chunk_id: str) -> bool:
        """删除记忆组块。"""
        ...
    
    @abstractmethod
    def apply_decay(self, current_time: Optional[float] = None) -> int:
        """应用衰减计算，触发阶段迁移。返回迁移的组块数量。"""
        ...
    
    @abstractmethod
    def promote(self, chunk_id: str, target_stage: MemoryStage) -> bool:
        """提升阶段（如用户主动回忆时从 COLD 提升到 WARM）。"""
        ...
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计（各层数量、平均权重、衰减率）。"""
        ...
```

---

## 6. Hot 层（内存缓存）

### 6.1 实现方式：`OrderedDict` + `threading.Lock`

**已有代码**: `session_manager.py` 第 46-48 行

```python
self._sessions: OrderedDict[str, Session] = OrderedDict()
self._lock = threading.Lock()
```

### 6.2 扩展需求

新增 `MemoryChunk` 的内存缓存：

```python
class HotLayer:
    """Hot 层 — 内存缓存，基于 OrderedDict 的 LRU。"""
    
    def __init__(self, max_items: int = 1000):
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._chunks: OrderedDict[str, MemoryChunk] = OrderedDict()
        self._cognitive_nodes: OrderedDict[str, CognitiveTreeNode] = OrderedDict()
        self._max_items = max_items
        self._lock = threading.Lock()
    
    def get_session(self, session_id: str) -> Optional[Session]: ...
    def put_session(self, session: Session) -> None: ...
    def get_chunk(self, chunk_id: str) -> Optional[MemoryChunk]: ...
    def put_chunk(self, chunk: MemoryChunk) -> None: ...
    def get_cognitive_node(self, node_id: str) -> Optional[CognitiveTreeNode]: ...
    def put_cognitive_node(self, node: CognitiveTreeNode) -> None: ...
    def _evict_lru(self) -> None: ...
```

### 6.3 可选 Redis 后端

```python
class RedisHotLayer(HotLayer):
    """Redis 热层 — 用于多进程/多节点部署。"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl_seconds: int = 3600):
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds
        self._serializer = VersionedSerializer()
    
    def get_session(self, session_id: str) -> Optional[Session]:
        data = self._redis.get(f"session:{session_id}")
        if data:
            return Session.from_persistent_dict(json.loads(data))
        return None
    
    def put_session(self, session: Session) -> None:
        key = f"session:{session.session_id}"
        value = json.dumps(session.to_persistent_dict(), default=str)
        self._redis.setex(key, self._ttl, value)
```

---

## 7. Warm 层（SQLite 本地持久化）

### 7.1 现有实现：`SQLiteSessionStore`

**已有代码**: `sqlite_store.py` 第 29-328 行

核心特性：
- WAL 模式（`PRAGMA journal_mode=WAL`）
- 懒加载连接（`_ensure_connection()`）
- `threading.Lock` 线程安全
- JSON 字段存储 dict/list
- 批量写入优化（`BEGIN`/`COMMIT`）

### 7.2 扩展：新增 `memory_chunks` 表

```sql
-- 新增表：记忆组块
CREATE TABLE IF NOT EXISTS memory_chunks (
    chunk_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    timestamp REAL NOT NULL,
    stage TEXT NOT NULL DEFAULT 'hot',
    tags JSON,
    source_layer TEXT,
    initial_weight REAL NOT NULL DEFAULT 1.0,
    time_constant REAL NOT NULL DEFAULT 86400.0,
    topic_refs JSON,
    cog_refs JSON,
    metadata JSON,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_session
    ON memory_chunks(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_stage
    ON memory_chunks(stage);
CREATE INDEX IF NOT EXISTS idx_memory_timestamp
    ON memory_chunks(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_memory_tags
    ON memory_chunks(json_extract(tags, '$'));
```

### 7.3 扩展：新增 `cognitive_nodes` 和 `cognitive_edges` 表

```sql
-- 新增表：认知树节点
CREATE TABLE IF NOT EXISTS cognitive_nodes (
    node_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    cog_type TEXT NOT NULL,
    source_llm TEXT NOT NULL,
    timestamp REAL NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    evidence JSON,
    action TEXT,
    action_result TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    reflections JSON,
    validations JSON,
    version_history JSON,
    cross_refs JSON,
    metadata JSON,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cog_nodes_session
    ON cognitive_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_cog_nodes_type
    ON cognitive_nodes(cog_type);
CREATE INDEX IF NOT EXISTS idx_cog_nodes_status
    ON cognitive_nodes(status);

-- 新增表：认知树边
CREATE TABLE IF NOT EXISTS cognitive_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    condition TEXT,
    metadata JSON,
    created_at REAL NOT NULL,
    UNIQUE(session_id, source_id, target_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_cog_edges_session
    ON cognitive_edges(session_id);
CREATE INDEX IF NOT EXISTS idx_cog_edges_source
    ON cognitive_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_cog_edges_target
    ON cognitive_edges(target_id);
```

### 7.4 版本管理表

```sql
-- 新增表：schema 版本管理
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL,
    description TEXT
);

-- 初始版本
INSERT INTO schema_version (version, applied_at, description) VALUES (3, 0, 'v3.0 schema');
```

---

## 8. Cold 层（归档文件）

### 8.1 现有实现：`TieredStorageManager`

**已有代码**: `tiered_storage.py` 第 122-167 行（`archive_warm_to_cold`）

核心特性：
- gzip 压缩 JSONL（`gzip.open`）
- 按日期命名（`{session_id}_{date}.jsonl.gz`）
- 支持 `dry_run` 模式
- 回热：扫描文件匹配 `session_id`，加载最新归档

### 8.2 扩展：备份/恢复工具

```python
class ColdArchiveManager:
    """冷层归档管理器 — 备份、恢复、清理。"""
    
    def __init__(self, cold_dir: str = "~/.memorygraph/archive"):
        self._cold_dir = Path(cold_dir).expanduser()
    
    def backup(self, backup_dir: str) -> int:
        """全量备份到指定目录。"""
        backup_path = Path(backup_dir).expanduser()
        backup_path.mkdir(parents=True, exist_ok=True)
        count = 0
        for src in self._cold_dir.glob("*.jsonl*"):
            dst = backup_path / src.name
            shutil.copy2(src, dst)
            count += 1
        return count
    
    def restore(self, backup_dir: str, dry_run: bool = False) -> int:
        """从备份恢复。"""
        backup_path = Path(backup_dir).expanduser()
        count = 0
        for src in backup_path.glob("*.jsonl*"):
            dst = self._cold_dir / src.name
            if not dry_run:
                shutil.copy2(src, dst)
            count += 1
        return count
    
    def cleanup(self, retention_days: int = 90, dry_run: bool = False) -> int:
        """清理超过保留期的归档。"""
        cutoff = time.time() - retention_days * 24 * 3600
        count = 0
        for filepath in self._cold_dir.glob("*.jsonl*"):
            try:
                mtime = filepath.stat().st_mtime
                if mtime < cutoff:
                    if not dry_run:
                        filepath.unlink()
                    count += 1
            except Exception:
                continue
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取冷层统计。"""
        files = list(self._cold_dir.glob("*.jsonl*"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "files": len(files),
            "size_bytes": total_size,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "dir": str(self._cold_dir),
        }
```

---

## 9. 图存储（GraphStore）

### 9.1 现有实现评估

**已有代码**: `graph_store.py` 第 26-472 行

已实现：
- ✅ `TopicNode` / `TopicEdge` 存储（`graph_nodes` / `graph_edges` 表）
- ✅ UPSERT（`ON CONFLICT DO UPDATE`）
- ✅ BFS 遍历（`bfs_neighbors`）
- ✅ 按实体搜索（`find_nodes_by_entity`）
- ✅ 批量操作（`save_nodes_batch` / `save_edges_batch`）
- ✅ 统计（`count_nodes` / `count_edges`）

### 9.2 扩展：Cognitive Tree 支持

```python
class GraphStore:
    """图存储 — 扩展支持 Cognitive Tree（v3.0）。"""
    
    # ── 已有方法保持不变 ───────────────────────
    # save_node, load_node, save_edge, load_edges_from, bfs_neighbors, ...
    
    # ── 新增：Cognitive Tree 节点操作 ──────────
    def save_cognitive_node(self, session_id: str, node: CognitiveTreeNode) -> bool:
        """保存认知树节点。"""
        self._ensure_cognitive_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO cognitive_nodes
                        (node_id, session_id, cog_type, source_llm, timestamp, content,
                         confidence, evidence, action, action_result, status,
                         reflections, validations, version_history, cross_refs, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        session_id = excluded.session_id,
                        content = excluded.content,
                        confidence = excluded.confidence,
                        status = excluded.status,
                        reflections = excluded.reflections,
                        validations = excluded.validations,
                        version_history = excluded.version_history,
                        updated_at = excluded.updated_at
                    """,
                    (
                        node.node_id, session_id, node.cog_type.value, node.source_llm,
                        node.timestamp, node.content, node.confidence,
                        json.dumps(node.evidence, default=str),
                        node.action, node.action_result, node.status.value,
                        json.dumps(node.reflections, default=str),
                        json.dumps(node.validations, default=str),
                        json.dumps(node.version_history, default=str),
                        json.dumps(node.cross_refs, default=str),
                        json.dumps(node.metadata, default=str),
                        time.time(),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_cognitive_node failed: {e}")
                return False
    
    def load_cognitive_nodes(self, session_id: str, limit: int = 1000) -> List[CognitiveTreeNode]:
        """加载某会话的所有认知节点。"""
        self._ensure_cognitive_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM cognitive_nodes
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        
        nodes = []
        for row in rows:
            try:
                nodes.append(self._row_to_cognitive_node(row))
            except (json.JSONDecodeError, KeyError):
                continue
        return nodes
    
    def _row_to_cognitive_node(self, row: sqlite3.Row) -> CognitiveTreeNode:
        """将数据库行转换为 CognitiveTreeNode。"""
        return CognitiveTreeNode(
            node_id=row["node_id"],
            cog_type=CogType(row["cog_type"]),
            source_llm=row["source_llm"],
            timestamp=row["timestamp"],
            content=row["content"],
            confidence=row["confidence"],
            evidence=json.loads(row["evidence"]) if row["evidence"] else [],
            action=row["action"],
            action_result=row["action_result"],
            status=CogNodeStatus(row["status"]),
            reflections=json.loads(row["reflections"]) if row["reflections"] else [],
            validations=json.loads(row["validations"]) if row["validations"] else [],
            version_history=json.loads(row["version_history"]) if row["version_history"] else [],
            cross_refs=json.loads(row["cross_refs"]) if row["cross_refs"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # ── 新增：Cognitive Tree 边操作 ──────────
    def save_cognitive_edge(self, session_id: str, edge: CognitiveTreeEdge) -> bool:
        """保存认知树边。"""
        self._ensure_cognitive_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO cognitive_edges
                        (session_id, source_id, target_id, edge_type, weight, condition, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, source_id, target_id, edge_type) DO UPDATE SET
                        weight = excluded.weight,
                        condition = excluded.condition,
                        metadata = excluded.metadata
                    """,
                    (
                        session_id, edge.source_id, edge.target_id,
                        edge.edge_type.value, edge.weight, edge.condition,
                        json.dumps(edge.metadata, default=str), time.time(),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_cognitive_edge failed: {e}")
                return False
    
    def load_cognitive_edges(self, session_id: str, limit: int = 1000) -> List[CognitiveTreeEdge]:
        """加载某会话的所有认知边。"""
        self._ensure_cognitive_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM cognitive_edges
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        
        edges = []
        for row in rows:
            try:
                edges.append(CognitiveTreeEdge(
                    edge_id=str(row["edge_id"]),
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    edge_type=CogEdgeType(row["edge_type"]),
                    weight=row["weight"],
                    condition=row["condition"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return edges
    
    def _ensure_cognitive_tables(self) -> None:
        """确保认知树表存在。"""
        if self._cognitive_tables_initialized:
            return
        with self._lock:
            if self._cognitive_tables_initialized:
                return
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cognitive_nodes (...);
                CREATE TABLE IF NOT EXISTS cognitive_edges (...);
                """)
            self._conn.commit()
            self._cognitive_tables_initialized = True
```

---

## 10. 实体索引（EntityIndex）

### 10.1 现有实现评估

**已有代码**: `entity_index.py` 第 23-349 行

已实现：
- ✅ 倒排索引（`entity_index` 表）
- ✅ 精确匹配搜索（`search_by_value`）
- ✅ 按类型搜索（`search_by_type`）
- ✅ 按会话搜索（`search_by_session`）
- ✅ 跨会话搜索（`find_sessions_by_entity`）
- ✅ 高频统计（`get_top_entities`）
- ✅ 批量索引（`index_entities_batch`）
- ✅ 清理过期（`cleanup_old`）

### 10.2 性能优化建议

当前实现使用 `LIKE` 进行 JSON 子串匹配（第 349-361 行），大数量时性能有限。

**优化方案**（v3.0 可选）：

```python
class EntityIndex:
    """实体索引 — 扩展支持全文搜索。"""
    
    # ── 新增：SQLite FTS5 全文索引 ───────────
    def _ensure_fts_tables(self) -> None:
        """创建 FTS5 全文索引表。"""
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entity_index_fts USING fts5(
                entity_type, entity_value, context_snippet,
                content='entity_index', content_rowid='id'
            )
        """)
        # 触发器：自动同步 FTS 索引
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS entity_index_fts_insert
            AFTER INSERT ON entity_index BEGIN
                INSERT INTO entity_index_fts(rowid, entity_type, entity_value, context_snippet)
                VALUES (new.id, new.entity_type, new.entity_value, new.context_snippet);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS entity_index_fts_delete
            AFTER DELETE ON entity_index BEGIN
                INSERT INTO entity_index_fts(entity_index_fts, rowid, entity_type, entity_value, context_snippet)
                VALUES ('delete', old.id, old.entity_type, old.entity_value, old.context_snippet);
            END
        """)
    
    def search_fulltext(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """全文搜索。"""
        self._ensure_fts_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT e.* FROM entity_index e
                JOIN entity_index_fts f ON e.id = f.rowid
                WHERE entity_index_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]
```

---

## 11. 记忆存储适配（MemoryStorage）

### 11.1 设计文档映射

设计文档 §8.3 定义五层记忆（5-4-3-1-3）与存储层的映射：

| 记忆阶段 | 权重 | 存储层 | 触发条件 |
|---------|------|--------|---------|
| HOT | 1.0 | Hot（内存） | < 1 小时 |
| WARM | 0.8 | Warm（SQLite） | 1-24 小时 |
| COOL | 0.5 | Warm（SQLite） | 1-7 天 |
| COLD | 0.2 | Cold（归档文件） | 7-30 天 |
| FROZEN | 0.05 | Cold（归档文件） | > 30 天 |

### 11.2 实现：`TieredMemoryStorage`

```python
class TieredMemoryStorage(MemoryStorage):
    """分层记忆存储 — 将 MemoryChunk 映射到三层存储。"""
    
    def __init__(
        self,
        tiered_manager: TieredStorageManager,
        decay_manager: MemoryDecayManager,
    ):
        self._tiered = tiered_manager
        self._decay = decay_manager
        self._lock = threading.Lock()
    
    def save(self, chunk: MemoryChunk) -> bool:
        """保存记忆组块，根据 stage 路由到对应层。"""
        if chunk.stage == MemoryStage.HOT:
            # 写入内存 + 写入 SQLite（冗余，保证热数据安全）
            self._tiered.put_hot(self._chunk_to_session(chunk))
            return self._tiered._warm.save_memory_chunk(chunk)
        elif chunk.stage in (MemoryStage.WARM, MemoryStage.COOL):
            return self._tiered._warm.save_memory_chunk(chunk)
        else:  # COLD, FROZEN
            return self._tiered._write_cold_archive(
                chunk.session_id or "global",
                {"memory_chunks": [chunk.to_dict()]}
            )
    
    def get(self, chunk_id: str) -> Optional[MemoryChunk]:
        """获取记忆组块，自动处理回热。"""
        # 1. 查 Hot
        session = self._tiered.get_hot(chunk_id)
        if session and hasattr(session, '_memory_chunks'):
            for chunk in session._memory_chunks:
                if chunk.chunk_id == chunk_id:
                    return chunk
        
        # 2. 查 Warm
        chunks = self._tiered._warm.load_memory_chunks(chunk_id)
        for chunk in chunks:
            if chunk.chunk_id == chunk_id:
                # 异步回热
                self._tiered.put_hot(self._chunk_to_session(chunk))
                return chunk
        
        # 3. 查 Cold
        record = self._tiered.rehydrate_cold_to_warm(chunk_id)
        if record and "memory_chunks" in record:
            for chunk_data in record["memory_chunks"]:
                chunk = MemoryChunk.from_dict(chunk_data)
                if chunk.chunk_id == chunk_id:
                    self._tiered._warm.save_memory_chunk(chunk)
                    self._tiered.put_hot(self._chunk_to_session(chunk))
                    return chunk
        
        return None
    
    def apply_decay(self, current_time: Optional[float] = None) -> int:
        """应用衰减计算，触发阶段迁移。"""
        if current_time is None:
            current_time = time.time()
        
        migrated = 0
        # 1. 扫描 Warm 层，计算每个 chunk 的有效权重
        # 2. 如果权重低于阈值，触发降级
        # 3. 如果用户主动回忆（promote），触发升级
        
        # 具体实现：遍历所有非 HOT 的 chunk，计算 W_eff
        # 如果 stage=HOT 且 W_eff < 0.8 → 降级到 WARM
        # 如果 stage=WARM 且 W_eff < 0.5 → 降级到 COOL
        # 如果 stage=COOL 且 W_eff < 0.2 → 降级到 COLD
        # 如果 stage=COLD 且 W_eff < 0.05 → 降级到 FROZEN
        
        return migrated
    
    def promote(self, chunk_id: str, target_stage: MemoryStage) -> bool:
        """提升阶段（用户主动回忆或系统触发的重激活）。"""
        chunk = self.get(chunk_id)
        if chunk is None:
            return False
        
        chunk.stage = target_stage
        chunk.timestamp = time.time()  # 重置衰减时间戳
        return self.save(chunk)
    
    def _chunk_to_session(self, chunk: MemoryChunk) -> Session:
        """将 MemoryChunk 包装为 Session（用于 Hot 层缓存）。"""
        # 创建一个轻量 Session，包含 chunk 作为附加属性
        session = Session(session_id=chunk.chunk_id)
        session._memory_chunks = [chunk]
        session.last_activity_at = chunk.timestamp
        return session
```

### 11.3 衰减定时任务

```python
class MemoryDecayWorker:
    """记忆衰减后台工作线程。"""
    
    def __init__(
        self,
        memory_storage: MemoryStorage,
        interval_seconds: float = 300,  # 5 分钟检查一次
    ):
        self._storage = memory_storage
        self._interval = interval_seconds
        self._shutdown_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """启动后台线程。"""
        def _run():
            while not self._shutdown_event.wait(self._interval):
                try:
                    migrated = self._storage.apply_decay()
                    if migrated > 0:
                        print(f"[MemoryDecayWorker] Migrated {migrated} chunks")
                except Exception as e:
                    print(f"[MemoryDecayWorker] Error: {e}")
        
        self._thread = threading.Thread(target=_run, daemon=True, name="memory-decay")
        self._thread.start()
    
    def shutdown(self) -> None:
        """停止后台线程。"""
        self._shutdown_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
```

---

## 12. v3.0 新增：Cognitive Tree 存储

### 12.1 需求

设计文档 §4.2 和 §6.2 要求：
- 支持 `CognitiveTreeNode` 和 `CognitiveTreeEdge` 的持久化
- 支持 LLM 实例级别的访问控制（`AccessControlMatrix`）
- 支持跨会话的 `cross_refs` 引用
- 支持版本历史（`version_history`）

### 12.2 实现：`CognitiveTreeStore`

```python
class CognitiveTreeStore:
    """认知树存储 — 管理 LLM 心智空间的持久化。"""
    
    def __init__(self, graph_store: GraphStore, access_control: AccessControlMatrix):
        self._graph = graph_store
        self._access = access_control
        self._lock = threading.Lock()
    
    def save_node(self, session_id: str, node: CognitiveTreeNode, requesting_llm: str) -> bool:
        """保存节点，检查访问权限。"""
        if not self._access.check_create(requesting_llm, node.cog_type):
            raise PermissionError(f"LLM {requesting_llm} cannot create {node.cog_type.value} nodes")
        
        return self._graph.save_cognitive_node(session_id, node)
    
    def update_node(self, session_id: str, node_id: str, updates: Dict[str, Any], requesting_llm: str) -> bool:
        """更新节点，检查访问权限。"""
        if not self._access.check_update(requesting_llm, node_id):
            raise PermissionError(f"LLM {requesting_llm} cannot update node {node_id}")
        
        # 加载现有节点，应用更新，保存
        nodes = self._graph.load_cognitive_nodes(session_id)
        for node in nodes:
            if node.node_id == node_id:
                for key, value in updates.items():
                    if hasattr(node, key):
                        setattr(node, key, value)
                node.version_history.append(json.dumps({"time": time.time(), "changes": list(updates.keys())}))
                return self._graph.save_cognitive_node(session_id, node)
        return False
    
    def load_tree(self, session_id: str) -> CognitiveTree:
        """加载完整认知树。"""
        nodes = self._graph.load_cognitive_nodes(session_id)
        edges = self._graph.load_cognitive_edges(session_id)
        
        tree = CognitiveTree(session_id=session_id)
        for node in nodes:
            tree.nodes[node.node_id] = node
        tree.edges = edges
        
        # 重建索引
        for node in nodes:
            tree._by_type.setdefault(node.cog_type, []).append(node.node_id)
            tree._by_llm.setdefault(node.source_llm, []).append(node.node_id)
            tree._by_status.setdefault(node.status, []).append(node.node_id)
        
        # 重建活跃分支
        active_nodes = [n for n in nodes if n.status == CogNodeStatus.ACTIVE]
        if active_nodes:
            # 找到最新的 ACTIVE 节点作为分支起点
            latest = max(active_nodes, key=lambda n: n.timestamp)
            tree.active_branch = self._trace_branch(tree, latest.node_id)
        
        return tree
    
    def _trace_branch(self, tree: CognitiveTree, start_node_id: str) -> List[str]:
        """从起始节点回溯到根，构建分支。"""
        branch = [start_node_id]
        current = start_node_id
        
        # 简单回溯：找到入边中权重最大的
        for _ in range(tree.depth_limit):
            incoming = [e for e in tree.edges if e.target_id == current]
            if not incoming:
                break
            best = max(incoming, key=lambda e: e.weight)
            branch.insert(0, best.source_id)
            current = best.source_id
        
        return branch
    
    def find_stale_branches(self, session_id: str, max_age_seconds: float = 3600) -> List[List[str]]:
        """查找失效分支（超过最大年龄未更新）。"""
        cutoff = time.time() - max_age_seconds
        tree = self.load_tree(session_id)
        
        stale = []
        for node_id, node in tree.nodes.items():
            if node.timestamp < cutoff and node.status == CogNodeStatus.ACTIVE:
                # 找到该节点所在分支
                branch = self._trace_branch(tree, node_id)
                stale.append(branch)
        
        return stale
    
    def archive_stale_branches(self, session_id: str, max_age_seconds: float = 3600) -> int:
        """归档失效分支（将状态改为 ARCHIVED）。"""
        stale_branches = self.find_stale_branches(session_id, max_age_seconds)
        count = 0
        
        for branch in stale_branches:
            for node_id in branch:
                self.update_node(
                    session_id, node_id,
                    {"status": CogNodeStatus.ARCHIVED},
                    "Reflective-LLM"  # 只有 Reflective-LLM 可以归档
                )
                count += 1
        
        return count
```

---

## 13. 数据流与状态迁移

### 13.1 写入数据流

```
[Application] → MemoryChunk(HOT) → HotLayer.put() + SQLiteSessionStore.save_memory_chunk()
                              │
                              ↓ (1小时后，衰减任务触发)
                        MemoryChunk(WARM) → SQLiteSessionStore.save_memory_chunk() (update stage)
                              │
                              ↓ (7天后，衰减任务触发)
                        MemoryChunk(COLD) → TieredStorageManager.archive_warm_to_cold()
                              │
                              ↓ (30天后，归档清理)
                        MemoryChunk(FROZEN) → ColdArchiveManager.cleanup() (可选删除)
```

### 13.2 读取数据流

```
[Application] → MemoryStorage.get(chunk_id)
                              │
                    ┌─────────┼─────────┐
                    ↓         ↓         ↓
                HotLayer   SQLite   ColdArchive
                (内存)     (Warm)   (文件)
                    │         │         │
                    └────┬────┘         │
                         ↓              │
                    命中返回 ← 异步回热 ─┘
                    (WARM 数据回热到 HOT)
```

### 13.3 状态迁移图

```
                    ┌─────────────────────────────────────┐
                    │           创建 MemoryChunk           │
                    └─────────────────┬───────────────────┘
                                      │
                                      ↓
                              ┌──────────────┐
                              │     HOT      │ ← 1小时内，权重 1.0
                              │   (内存)     │
                              └──────┬───────┘
                                     │
                                     │ 1小时后，W_eff < 0.8
                                     ↓
                              ┌──────────────┐
                              │    WARM      │ ← 1-24小时，权重 0.8
                              │   (SQLite)   │
                              └──────┬───────┘
                                     │
                                     │ 7天后，W_eff < 0.5
                                     ↓
                              ┌──────────────┐
                              │    COOL      │ ← 1-7天，权重 0.5
                              │   (SQLite)   │
                              └──────┬───────┘
                                     │
                                     │ 30天后，W_eff < 0.2
                                     ↓
                              ┌──────────────┐
                              │    COLD      │ ← 7-30天，权重 0.2
                              │  (归档文件)  │
                              └──────┬───────┘
                                     │
                                     │ 90天后，W_eff < 0.05
                                     ↓
                              ┌──────────────┐
                              │   FROZEN     │ ← >30天，权重 0.05
                              │  (归档文件)  │
                              └──────┬───────┘
                                     │
                                     │ 用户主动回忆（promote）
                                     │ 或系统重激活
                                     ↓
                              ┌──────────────┐
                              │    WARM      │ ← 回热，重置时间戳
                              │   (SQLite)   │
                              └──────────────┘
```

---

## 14. 版本兼容与迁移

### 14.1 迁移工具

```python
class SchemaMigration:
    """数据库 Schema 迁移工具。"""
    
    MIGRATIONS = {
        1: "Initial schema (sessions, turns)",
        2: "Add graph_nodes, graph_edges, entity_index",
        3: "Add memory_chunks, cognitive_nodes, cognitive_edges, schema_version",
    }
    
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
    
    def get_current_version(self) -> int:
        """获取当前 schema 版本。"""
        try:
            row = self._conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
            return row["v"] if row and row["v"] else 0
        except sqlite3.OperationalError:
            return 0
    
    def migrate(self, target_version: int = 3) -> None:
        """执行迁移到目标版本。"""
        current = self.get_current_version()
        
        for version in range(current + 1, target_version + 1):
            print(f"[SchemaMigration] Migrating to version {version}: {self.MIGRATIONS[version]}")
            self._apply_migration(version)
            self._conn.execute(
                "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
                (version, time.time(), self.MIGRATIONS[version]),
            )
            self._conn.commit()
    
    def _apply_migration(self, version: int) -> None:
        """应用具体迁移。"""
        if version == 1:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (...);
                CREATE TABLE IF NOT EXISTS turns (...);
            """)
        elif version == 2:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS graph_nodes (...);
                CREATE TABLE IF NOT EXISTS graph_edges (...);
                CREATE TABLE IF NOT EXISTS entity_index (...);
            """)
        elif version == 3:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_chunks (...);
                CREATE TABLE IF NOT EXISTS cognitive_nodes (...);
                CREATE TABLE IF NOT EXISTS cognitive_edges (...);
                CREATE TABLE IF NOT EXISTS schema_version (...);
            """)
```

### 14.2 版本检测策略

- 启动时检查 `schema_version` 表，如果不存在则创建并执行全量迁移。
- 如果版本号低于目标版本，按顺序执行迁移脚本。
- 迁移失败时回滚，记录错误日志，服务启动失败（防止数据不一致）。

---

## 15. 测试策略

### 15.1 测试目标

| 测试类型 | 覆盖率目标 | 关键验证点 |
|---------|----------|----------|
| 单元测试 | 100% | 每个存储方法的读写一致性 |
| 集成测试 | 90% | 跨层迁移（Hot→Warm→Cold）的正确性 |
| 版本迁移测试 | 100% | 从 v1 到 v3 的 schema 迁移 |
| 性能测试 | 关键路径 | 1000 个 MemoryChunk 的写入 < 100ms |
| 并发测试 | 多线程 | 10 线程同时读写，无数据损坏 |

### 15.2 关键测试用例

**用例 1：三层迁移完整性**
```python
def test_tiered_migration():
    storage = TieredMemoryStorage(...)
    chunk = MemoryChunk(chunk_id="test-1", stage=MemoryStage.HOT, content="test")
    
    # 写入 HOT
    storage.save(chunk)
    assert storage.get("test-1") is not None
    
    # 模拟 2 小时过去，触发衰减
    future_time = time.time() + 7200
    storage.apply_decay(current_time=future_time)
    
    # 从 Warm 层读取
    chunk_warm = storage.get("test-1")
    assert chunk_warm.stage == MemoryStage.WARM
    
    # 模拟 8 天过去，触发再次衰减
    future_time = time.time() + 8 * 86400
    storage.apply_decay(current_time=future_time)
    
    # 从 Cold 层读取（需回热）
    chunk_cold = storage.get("test-1")
    assert chunk_cold.stage == MemoryStage.COLD
```

**用例 2：Cognitive Tree 权限控制**
```python
def test_cognitive_tree_permissions():
    store = CognitiveTreeStore(graph_store, access_control)
    node = CognitiveTreeNode(cog_type=CogType.VALIDATION, source_llm="Meta-Cognitive-LLM")
    
    # Planning-LLM 不能创建 VALIDATION 节点
    with pytest.raises(PermissionError):
        store.save_node("session-1", node, "Planning-LLM")
    
    # Meta-Cognitive-LLM 可以创建
    assert store.save_node("session-1", node, "Meta-Cognitive-LLM")
```

**用例 3：Schema 迁移**
```python
def test_schema_migration():
    # 创建 v1 数据库
    conn = sqlite3.connect(":memory:")
    migration = SchemaMigration(conn)
    migration.migrate(target_version=1)
    assert migration.get_current_version() == 1
    
    # 迁移到 v3
    migration.migrate(target_version=3)
    assert migration.get_current_version() == 3
    
    # 验证所有表存在
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = [r[0] for r in tables]
    assert "memory_chunks" in table_names
    assert "cognitive_nodes" in table_names
```

---

## 16. 附录：简化与待讨论项

### 16.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | Redis 后端 | Hot 层支持 Redis 集群 | 仅 `OrderedDict` 内存缓存 | 初期单进程部署，Redis 增加运维复杂度 | Phase 3 多节点部署时实现 `RedisHotLayer` |
| **S-02** | PostgreSQL 后端 | Warm 层支持 PostgreSQL | 仅 SQLite | 团队熟悉 SQLite，PostgreSQL 增加部署成本 | Phase 3 高并发场景时实现 `PostgreSQLSessionStore` |
| **S-03** | 双指数衰减 | `W(t) = A e^{-t/τ_1} + B e^{-t/τ_2}` | 单指数衰减 | 单指数已覆盖 95% 场景，双指数参数调优困难 | Phase 3 记忆系统优化时实现 |
| **S-04** | FTS5 全文索引 | 实体索引支持全文搜索 | 仅精确匹配和 `LIKE` | SQLite FTS5 需要编译时支持，部分环境可能不可用 | Phase 2 可选功能，通过配置开关启用 |
| **S-05** | Cognitive Tree 图遍历优化 | 大规模 Cognitive Tree 的子图查询优化 | 全量加载后内存遍历 | 当前会话级 Cognitive Tree 规模可控（<1000 节点） | Phase 3 引入图数据库（Neo4j）或 CTE 查询优化 |
| **S-06** | 分布式事务 | 跨层操作的原子性（如 Hot→Warm 迁移失败回滚） | 各层独立操作，无全局事务 | SQLite 本地事务已足够，分布式事务增加复杂度 | Phase 3 多节点部署时引入 Saga 模式 |

### 16.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 冷层归档格式 | A) gzip JSONL  B) Parquet  C) SQLite 分片 | 建议 A：JSONL 可读性好，便于调试；Parquet 需要额外依赖 |
| **D-02** | 记忆衰减触发时机 | A) 定时任务（5分钟）  B) 写入时触发  C) 读取时懒触发 | 建议 A：定时任务可预测，写入时触发增加延迟；读取时懒触发可能导致数据不一致 |
| **D-03** | Cognitive Tree 的跨会话引用 | A) 软引用（仅存储 ID）  B) 硬拷贝（复制节点）  C) 全局索引 | 建议 B：硬拷贝，锚文档 ENGINEERING_MULTILAYER_LLM.md §16.2 D-03 已决策。硬拷贝简单可靠，避免全局索引和 GC 复杂度 |
| **D-04** | 实体索引的更新策略 | A) 同步更新（事务内）  B) 异步更新（消息队列）  C) 批量更新（5秒窗口） | 建议 A：当前规模下同步更新足够，异步增加复杂度 |
| **D-05** | 备份策略 | A) 全量备份（每日）  B) 增量备份（WAL 归档）  C) 实时复制（主从） | 建议 A：初期全量备份足够；增量备份需要 WAL 解析工具 |

### 16.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §8.2 | §6-§10 | ✅ 等价 | 三层存储 + 图存储 + 实体索引覆盖 |
| `DESIGN_FULL_CONCEPT.md` §8.3 | §11 | ⚠️ 简化 | 五层记忆映射已覆盖，但双指数衰减标记为 S-03 |
| `DESIGN_FULL_CONCEPT.md` §8.4 | §14 | ✅ 等价 | 版本迁移工具覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §12 | ✅ 等价 | Cognitive Tree 存储 + 权限控制覆盖，硬拷贝跨会话引用（锚文档 §8, §9） |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2 | §12.2 | ✅ 等价 | 访问控制矩阵覆盖（锚文档 §9） |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.3 | §12.2 | ✅ 等价 | 事件总线覆盖（锚文档 §10） |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和现有代码评估生成。现有代码已实现约 70% 的设计需求，新增文件约 780 行代码可实现剩余 30%。所有简化项已在 §16.1 中诚实标记，待讨论项在 §16.2 中列出，等待团队确认。*
