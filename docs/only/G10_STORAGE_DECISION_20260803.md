# G10 存储架构选型 — 正式拍板建议（2026-08-03）

> 状态: 待全局确认。来源: GLOBAL_PHILOSOPHY_FILTER_FINAL G10 真决策 + 用户方向
> (向量图数据库直觉) + 双环境核查 + 引用数复核。

---

## 一、核查修正（相对 FINAL 文档 + 我的初版建议）

```
引用数复核 (用户): graph_store 实测 19 (我写 22) · unified_graph_store 8 (我写 10)
faiss 状态 (双环境实测): hermes venv (3.11) + .venv 均未装 → 我清单 ❌ 正确;
  用户"已装"为更早环境快照 → 最终结论: 阶段 1 可选 faiss (装后作 chromadb 替代), 非现状
壳 vs 实现核查 (新增):
  tiered_storage.py: 16 行壳 ✅ (要归)
  unified_store.py:  21 行壳 ✅ (要归)
  unified_graph_store.py: 148 行, 有真实 SQLite 建表逻辑 ⚠️ 半实现 (非纯壳)
  graph_store.py: 472 行真实实现 ✅ (保留)
  sqlite_store.py: 328 行真实实现 ✅ (保留)
```

---

## 二、选型结论（用户方向 + 三层细化整合）

### 核心原则: 拍分层策略 + 触发条件，不拍死一个数据库

GraphBackend Protocol 已存在（relation_graph.py:27）——换后端是配置项不是架构决策。

### 阶段 1（现在, 单用户 KB-MB 级）: 零新依赖

```
主存储:
  事实+事件 → sqlite_store (328行, 9 引用, 真实实现) ✅
  图        → graph_store (472行, 19 引用, 真实实现, SQLite 持久化) ✅
  向量      → chromadb (已装, 79MB 模型) 或 faiss (可选装, 都满足 Protocol)
归一: 收敛到 GraphBackend Protocol 之下的多个实现 — 不是"合并成 1 套"
  保留: sqlite_store / graph_store (真实消费方)
  归档: tiered_storage (16行壳) / unified_store (21行壳) / faiss_store / milvus_store
        / hnsw_index / lsm_store (1-2 引用孤儿)
  处置: unified_graph_store (148行半实现) — 吸收进 graph_store 或归档, 拍板
```

### 阶段 2（数据 >100MB 或 图节点 >10K 或 图扩散深度>2 跳延迟敏感）: Kuzu

```
Kuzu = 嵌入式向量图库, 无服务进程, 图+向量原生
迁移: 实现 GraphBackend Protocol 新后端即可替换 — 零侵入
保守替代: sqlite-vec (SQLite 生态内扩展, 渐进迁移)
```

### 阶段 3（多用户/多进程并发）: Neo4j / Milvus / 云

```
触发: 与 G5 分布式同一触发条件 — 多用户并发 + 跨进程共享
```

---

## 三、触发条件量化（用户补充的行为维度已纳入）

| 维度 | 阈值 | 类型 |
|------|------|:---:|
| 数据体量 | > 100MB | 体量 |
| 图规模 | > 10K 节点 | 体量 |
| 图扩散延迟 | 扩散深度 > 2 跳时 p95 延迟敏感 | **行为** (用户补充) |
| 向量召回退化 | chromadb 查询 p95 退化 > 2x 基线 | **行为** |
| 并发 | 多用户/多进程共享 | 架构 (与 G5 合并) |

> 行为维度（图扩散深度、向量召回退化）比纯体量更早触发——体量阈值是下限,
> 行为退化是实际信号。触发条件本身可配置（A18 参数自适应）。

---

## 四、哲学对齐

```
A2 递归缩放  → Kuzu 原生支持递归缩放 (阶段 2)
A5 树推理    → 图结构保持 (networkx → Kuzu 无痛, 同一 Protocol)
A25 级联召回 → 向量 (chromadb/faiss) + 图 (graph_store/Kuzu) 双通道
A18 参数自适应 → 触发条件可配置, 不锁死
A17 记录永不可删 → SQLite 事件日志保留 (阶段 1 已是)
```

---

## 五、拍板项（3 项）

```
G10-1 ✅ 阶段 1 = sqlite_store + graph_store + chromadb/faiss, 零新依赖
       (归一: 归档 6 个壳/孤儿, 保留 2 个真实实现 + Protocol 抽象)
G10-2 ✅ 阶段 2 = Kuzu (嵌入式向量图), 实现 Protocol 新后端
G10-3 ✅ 触发条件 = 体量 (100MB/10K) + 行为 (扩散深度/召回退化) + 并发 (与 G5)
```

> 关联: G10 与 I1-9 (三套 chroma 入口归一) 一并拍——chroma 入口收敛到
> ChunkStore backend 一个配置点。
