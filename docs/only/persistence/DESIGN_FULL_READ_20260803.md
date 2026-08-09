# 持久化层设计文档全面精读（第二轮）

> 日期: 2026-08-03 | 精读对象（6 篇，4000 行）:
> `BUSINESS_CHAIN_04_META_PERSIST.md`（305）+ `v3.0/DESIGN_UNIFIED_PERSISTENCE.md`（174）+
> `v3.0/DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md`（241）+
> `project/design_persistence.md`（663）+ `v3.0/ENGINEERING_PERSISTENCE.md`（1184）+
> `v3.0/ENGINEERING_DATA_MODEL.md`（1433）
> 配套: `AUDIT_ENTRY_20260803.md`（一轮盘点）+ `DEEP_AUDIT_20260803.md`（实锤验证）
> 本文档 = 设计全貌凝练 + 设计↔代码对照 + 待讨论点。

---

## 一、业务链 04 章精读（BUSINESS_CHAIN_04_META_PERSIST.md，305 行）

### 1.1 定位（v1.1 修正）

```
本章仅覆盖对话树的持久化路径（+元认知内部修改器）。
行为链/关联链/工程链持久化另述（各链有自己的机制，不一定需要"修正网关"）。
```

### 1.2 对话树为什么需要"修正网关"

```
矛盾: 分类器进化（TieredActionResolver）vs 树节点标注创建时固定
  Session1: 分类器 v1 不认识 add_monitoring → 节点 N23 标注 action:"ask"
  Session2: 分类器 v2 已学会 → 直接保存 N23 标注仍错
修正网关: 持久化时用最新分类器重新解析 → 写出修正后的标注
其他链（图结构）可原地更新，不需要此机制
```

### 1.3 元认知（内部修改器，对话树视角）

```
修改权限表:
  重分类 action/topic ✅ 自动（Slow Path 分析后标记 stale）
  建议切分/合并节点 ⚠️ 建议（走链 03 用户确认）
  修正 L1/L2 摘要 ✅ 自动（检测漂移>0.3）
  标记"需人工审查" ✅ 自动（置信度过低）
  删除节点 ❌ 禁止
触发条件: 标注置信度<0.4+时间衰减 / 摘要与 EDU 漂移>0.3 / 兄弟节点相似度>0.9
```

### 1.4 持久化修正网关（树→图）

```
DialogueTreePersistenceAdapter:
  persist_node/persist_tree/load_node/load_tree（+结构校验 action_shift/merged_from 元数据边）
  "修正网关不改变树结构，只追加元数据边 + 更新标注"
  HCWA 分层: active→H(内存全量) / paused→C(持久化可按需) / cold→W(衰减) / frozen→A(压缩)
    迁移: 粘合度≥0.7 合并 <0.4 切换；10 轮无访问 paused→cold；50 轮 cold→frozen；
          BGE 匹配>0.8 回升
三修改源对比: 用户编辑(全部权限需确认) / 元认知(自动修正+建议) / 持久化网关(仅标注+元数据边)
```

### 1.5 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| DialogueTreePersistenceAdapter | `persistence/dialogue_tree_adapter.py` 11.0KB（LoadResult+adapter+_text_similarity）| ✅ 类实现 |
| NodeAnnotationStore | `persistence/annotation_store.py`（NodeAnnotation+NodeAnnotationStore）| ✅ |
| 修正网关（resolve_action）| 待核对（TieredActionResolver 现状）| ⚠️ |
| HCWA 分层 | `persistence/graph_tier_manager.py` + `tiered_storage.py`（TieredStorageManager）| ✅ 类实现 |
| UnifiedGraphStore | `persistence/unified_graph_store.py` 7.9KB | ✅ 类实现 |
| **生产接线** | 对话树 session end 是否调 adapter | ⚠️ 待确认（对话树审计联动）|

---

## 二、统一图存储精读（DESIGN_UNIFIED_PERSISTENCE.md，174 行）

### 2.1 设计核心

```
现状问题: GraphStore.graph_nodes 只接受 TopicNode → 全部域模型无持久化（进程退出即丢）
根本原则: 存储层不知道节点具体类型——只提供通用行，类型作为字段

通用节点表 graph_nodes:
  {node_id, node_type(T/E/B/K/P 五域), domain, session_id, data(JSON 自由),
   summary(L1), l2_summary(L2), activation_count(电容模型), importance(betweenness),
   tier(H/W/C/A), source_events(溯源), created_at, updated_at}

多粒度索引（RAG 大小块）: 全文 data / 摘要 summary / 极简 l2_summary
分层存储（JVM GC 模型）:
  H: Python dict, <1ms | W: SQLite, <10ms | C: SQLite 压缩, <50ms | A: JSONL 归档, <500ms
  升降: 连续 10 轮无访问 H→W；importance<0.3 W→C；C 保留索引可被 WaveQuery 检索

水波检索扩展: wave_from_node(anchor, max_depth, domain_filter, tier_filter, granularity)
  RAG 两阶段: Coarse scan(summary) → Full recall(data)

三种强化检索: 问题预生成(generated_questions) / HyDE(假设性文档嵌入) / 混合检索(语义 0.7+关键词 0.3)

性能优化:
  动态索引锚点(Python): HotIndex(activation>10 或 1h 内) → 先查 hot 后 warm，99% 命中热点
  主干染色(Rust): betweenness>0.6 边预计算 → O(depth^n)→O(backbone_hops+cluster_size)
  收益: 50000 节点 10s+ → 10-50ms(Python 锚点) / 2-5ms(+Rust 主干)
```

### 2.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 通用节点表 | `persistence/unified_graph_store.py`（save_node/load_node/tier 字段）| ✅ |
| 电容模型/importance | graph_store / entity_index（activation_count）| ✅ 部分 |
| HCWA 分层 | `graph_tier_manager.py` + `tiered_storage.py` | ✅ |
| 水波检索 | `wave_query.py`（wave_from_node/hybrid_query/BFS SQL）| ✅ |
| 问题预生成 | 待核对（memory/xml_cards?）| ⚠️ |
| HyDE | `hybrid_hyde.py`（HybridSearchEngine/HyDERetriever 1.7KB）| ⚠️ 轻量 |
| 混合检索 | `hybrid_index.py`（KeywordIndex+HybridIndex）| ✅ |
| **HotIndex 动态锚点** | 待核对 | ⚠️ |
| **Rust 主干染色** | `rust_bridge.py` 探测壳 | ❌ |

> 修正（AUDIT_ENTRY §四.4）: rust_bridge.py 确认为探测壳（无真实实现）。

---

## 三、对话树持久化适配器精读（DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md，241 行）

### 3.1 设计核心

```
问题: 树刚性（parent/child/拆分决策创建时固定）vs 分类器进化（TieredActionResolver 反馈闭环）
原则: 拆分决策（不可逆）只依赖 Tier0 规则；标注（可逆）允许 Tier1+2，但不存树节点内
方案: 修正网关 —— 持久化时用最新分类器重分类 + 结构校验，写入图（柔性）

数据分离:
  树节点: {node_id, parent, summary} ← 不可变
  标注索引: NodeAnnotationStore ← {action, version, source, stale} 随时可重分类覆盖
  图节点: 合并修正（action + action_version）

NodeAnnotationStore（多域共享）:
  put/get/mark_stale/get_stale/history + 版本化 + previous_versions
  联动: TieredActionResolver.on_new_action → mark_stale → 下次 get 自动重分类

结构校验（只追加元数据边，不改拓扑）:
  相邻节点 action+topic 相同 → merged_from/merged_to 引用边 + 标注 redundant
  action 漂移 topic 不变 → action_shift 边
```

### 3.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| DialogueTreePersistenceAdapter（persist/load）| `persistence/dialogue_tree_adapter.py`（LoadResult+adapter+_text_similarity）| ✅ 类实现 |
| NodeAnnotationStore（put/get/mark_stale/history）| `persistence/annotation_store.py`（NodeAnnotation+NodeAnnotationStore）| ⚠️ 需核对方法面 |
| 修正网关（resolve_action/重分类）| 待核对（TieredActionResolver 在 discourse/）| ⚠️ |
| 生产接线（session end 调用）| 待核对 | ⚠️ 对话树审计联动 |

---

## 四、会话持久化精读（project/design_persistence.md，663 行）

### 4.1 设计核心

```
背景: CLI v1 纯内存（进程退出即丢）/ 画像不累积 / 阈值重置 / 无法跨会话分析
方案: CLISessionPersistence 中间件 = 同步外壳 + 独立事件循环线程(asyncio.run_coroutine_threadsafe)
  + 复用 AsyncSessionManager + AsyncSQLiteSessionStore（service/ 已有）

目标: P0 恢复对话/画像累积/阈值持久化；P1 多会话管理；P2 导入导出/30 天清理
非功能: save_turn<50ms / 50 轮加载<100ms / 100 轮<1MB / 并发安全 / 降级回内存

批量保存: 画像/阈值 pending 缓存，每 5 轮或 session 关闭 flush（乐观锁版本号递增）
shutdown: flush pending → 关 SQLite → 等待 tasks(5s) → 停循环
```

### 4.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| CLISessionPersistence | `persistence/cli_middleware.py` 7.0KB（v3_common 桥主消费）| ✅ 实现+接线 |
| AsyncSessionManager/Store | `service/async_session_manager.py` + `service/stores/` | ✅ 复用 |
| TurnRecord 契约 | `persistence/models.py:93` | ✅ |
| 批量保存/乐观锁 | `cli_middleware.py`（pending+_flush_pending_updates）| ✅ |
| 降级可用 | 待核对 | ⚠️ |

> 结论: 本项目最"落地"的持久化设计之一（CLI 会话中间件 + v3_common 桥 + pcr intent_trace_cli 真消费）。

---

## 五、工程持久化精读: ENGINEERING_PERSISTENCE.md（1184 行）

### 5.1 设计核心

```
定位: 分层存储系统规范（Hot/Warm/Cold 全链路数据生命周期）
原则: "必须实现设计概念文档的完整分层存储，任何简化均需诚实标记"

MemoryStorage 适配（5 阶段 → 三层存储）:
  HOT(1.0, 内存) <1h / WARM(0.8, SQLite) 1-24h / COOL(0.5, SQLite) 1-7d /
  COLD(0.2, 归档) 7-30d / FROZEN(0.05, 归档) >30d
  save: 按 stage 路由；get: Hot→Warm→Cold 三级 + 异步回热
  apply_decay: W_eff = Importance × exp(-t/τ) × StageFactor
  MemoryDecayWorker: 后台线程 5 分钟检查

CognitiveTreeStore: cognitive_nodes/edges 表（含 AccessControlMatrix 权限 +
  cross_refs + version_history）；find_stale_branches/archive_stale_branches
SchemaMigration: 版本 1→2→3（sessions/turns → graph → memory+cognitive）
ColdArchiveManager: backup/restore/cleanup(90 天)
EntityIndex FTS5: 全文索引（触发器自动同步）
RedisHotLayer: 可选多进程热层
```

### 5.2 代码对照（实锤——文档新增部分全部未落地）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| TieredStorageManager（三层）| `persistence/tiered_storage.py` 13.3KB | ✅ 已有 |
| SQLiteSessionStore（WAL/懒连接/批量）| `persistence/sqlite_store.py` 12.1KB | ✅ 已有 |
| EntityIndex（倒排）| `persistence/entity_index.py` 12.8KB | ✅ 已有 |
| **MemoryStorage/TieredMemoryStorage** | 全库无类定义 | ❌ 未实现 |
| **MemoryChunk 表/衰减 Worker** | 无 memory_chunks 表 | ❌ 未实现 |
| **CognitiveTreeStore** | 仅 v3_0/cognitive_compiler/compiler.py:32（旧路径）| ⚠️ 未在 persistence/ |
| **SchemaMigration** | 无 | ❌ 未实现 |
| **ColdArchiveManager** | 无（tiered_storage 有 cleanup_cold 近似）| ❌ |
| **FTS5/RedisHotLayer** | 无 | ❌ |

> **实锤**: ENGINEERING_PERSISTENCE 声称"部分已有代码"，但实际只有三层/SQLite/图/实体索引
> 已有；文档要求的 MemoryStorage/CognitiveTree/SchemaMigration/FTS5/Redis/衰减 Worker
> **全部未落地**——持久化模块的"完整分层存储"仍是设计态。

---

## 六、数据模型精读: ENGINEERING_DATA_MODEL.md（1433 行）

### 6.1 设计原则（5 条）

```
纯数据容器（dataclass 无业务逻辑）/ 版本化字段(__version__="3.0") /
可空性策略（list/dict 用 default_factory 永不 None）/ 时间戳统一 float /
枚举优先（状态/类型用 Enum）
模型分层: models/layer0~3 + crosscutting + v3_llm
```

### 6.2 核心模型（各链对应）

```
Layer0: PCROutput{expectation, noise_level, complexity_level,
  cognitive_profile(4 维快照: 元认知/发散/稳定/信心), execution_mode(3 态), parser_config_overrides}
Layer1: Intent{category, raw/normalized_input, entities, ambiguities}
Layer1.5: TaskGraph/TaskNode/TaskEdge + ToolSchema + PlanningSkill
Layer2: DialogueState/TopicTree/ContextWindow
Layer3: UserInput/Session/ParseResult/ParseContext
横切: CognitiveProfileV2(Track A+B) / MemoryChunk+MemorySnapshot+StageTransition /
  TelemetryEvent+TraceSpan

MemoryChunk 衰减: W_eff = Importance × exp(-t/τ) × StageFactor
MemorySnapshot: 7 核心数据契约之一（补充模型）— chunks/weights/stage_transitions
```

### 6.3 代码对照

```
模型分散在 models_v3.py / v3_common/data_models.py / persistence/models.py /
pcr/datacontract.py 等——**无统一 core/agent/models/ 包**（设计 §3.2 的目录未建）
PCROutput: pcr/datacontract.py（已核对: 字段一致+超集）
MemoryChunk/MemoryStage/衰减: 未实现（与 §五 一致）
```

---

## 七、持久化模块设计精读完成度（6/6）

| # | 文档 | 核心结论 |
|---|--:|---|
| 1 | BUSINESS_CHAIN_04 | 对话树修正网关 + 元认知修改器 + HCWA 分层（adapter 类实现）|
| 2 | DESIGN_UNIFIED_PERSISTENCE | 通用图节点 + 分层 GC 模型 + 水波/问题预生成/HyDE/混合检索（部分实现）|
| 3 | DESIGN_DIALOGUE_TREE_ADAPTER | 标注索引 + 版本化 + 结构校验（annotation_store 类实现）|
| 4 | project/design_persistence | CLI 会话中间件（最落地设计，真消费）|
| 5 | ENGINEERING_PERSISTENCE | 五阶段 MemoryStorage/CognitiveTree/SchemaMigration **全部未落地** |
| 6 | ENGINEERING_DATA_MODEL | 统一 models/ 包未建，模型分散；MemoryChunk 衰减未实现 |

> 持久化模块两轮审计完成（AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ 七节）。
> 待拍板: 存储架构（六套体系收敛 / SQLite 拓展 / redis 热层 / MemoryStorage 落地）
> 与 FactStore 批量写缺陷（既有待办）。
