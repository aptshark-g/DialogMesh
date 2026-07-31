# DialogMesh v6 — Architecture Audit

> 日期: 2026-07-30 · 审计人: strict architect mode
> 原则: 不粉饰、不假设、不乐观。只记录可验证的事实。

---

## 一、代码规模

| 文件 | 行数 | 职责 | 健康度 |
|------|-----:|------|:------:|
| `core/agent/runtime/engine.py` | 3,721 | 认知运行时引擎 | 🔴 太胖 |
| `core/agent/api/api.py` | 1,919 | 全量 API 路由 | 🟡 可接受 |
| `core/agent/cli/entry.py` | 1,198 | CLI 入口+dispatch | 🟡 可接受 |
| `core/agent/event/handlers.py` | 281 | StateMachine 8个处理器 | 🟢 良好 |
| `core/agent/event/statemachine.py` | 176 | 状态机核心 | 🟢 良好 |
| `core/agent/api/v6_app.py` | 268 | v6 路由注册 | 🟢 良好 |
| `core/agent/cli/engine.py` | ~320 | CLI 引擎工厂 | 🟡 可接受 |

**风险**: `engine.py` 3721 行、180KB。改前必须 `git checkout`——是项目最脆的文件。

---

## 二、双轨架构 (P0 — 最高风险)

### 问题

系统有 **两条互不知道对方的事件处理路径**:

```
路径 A (legacy, 3,500+ 行):
  on_event() → serial NLP chain
  → discourse analysis → behavior recording
  → granular regulation → meta cognition

路径 B (new, 42 行):
  on_event_sm() → StateMachine.run_pipeline()
  → 8 phases, 12 transitions
  → PCR → Intent → Planning → LLM → Discourse → Behavior → Meta → Persist
```

### 风险

1. **路径 A 仍在 `on_event()` 中活跃**——从未删除
2. **路径 B 不知道路径 A 做了什么**——如果 A 改了 `_meta_cognition`，B 不知道
3. **两个初始化路径**: `start()` (660行,从不用) vs `_create_engine_instance()` (factory,手动重造)
4. **数据竞争**: 两个处理器可能同时写 `_behavior_graph_adapter`

### 证据

```
$ grep "def on_event" engine.py
def on_event(self, event_id, kind, payload, ...):   ← 第 197 行, 仍活跃
def on_event_sm(self, ...):                          ← 第 216 行, 新路径

$ grep "def start" engine.py  
def start(self, provider_config, ...):               ← 第 217 行, 660行,N E V E R 调用
```

### 修复方向

```
目标: on_event_sm 作为唯一入口
  Week 1: on_event → 只有路由,转发到 on_event_sm
  Week 2: engine.start() → 统一到 _create_engine_instance
  Week 3: 删除死代码 (逐步,每步验证)
```

---

## 三、设计文档 vs 代码实现 (P0 — 信任危机)

### 问题

23 个 `DESIGN_*.md` 文件，多个标 "100% ✅"。但代码实际状态不同。

| 设计文档 | 设计宣称 | 代码实际 | 差距 |
|----------|---------|---------|:----:|
| DESIGN_AUDIT.md | "可达性 24/24 100%" | /v6/objects → "No world objects" | ❌ |
| DESIGN_RUNTIME_KERNEL.md | "HotStore 自动填充" | 手动 `_cache_hot()` 调用 | ⚠️ |
| DESIGN_GLOBAL_STATE_MACHINE.md | "single entry point" | 两条路径都在跑 | ❌ |
| DESIGN_DISTRIBUTED.md | "EnginePool 4-slot" | pool.py 存在但未集成 | ⚠️ |
| DESIGN_METACOGNITION_RUNTIME.md | "workflow graph loop" | MetaCognition 对象在线但空 | ⚠️ |

### 根因

设计文档把 **"端点存在"** 和 **"数据存在"** 混淆了。`GET /v6/objects` 返回 200 但 `{"count": 0}`——设计标 ✅，用户看到空数据。

### 修复方向

```
每个设计文档末尾加 "实际状态" 表:
  - 端点: ✅ 存在
  - 数据: ⚠️ 空 (需 3 轮对话积累)
  - 测试: ❌ 无
```

---

## 四、死代码 (P1)

### 1. engine.start() — 660行未调用的代码

```python
# engine.py line 217
def start(self, provider_config, provider_type, engine_config):
    # 660 行创建 12 个深度对象
    # 从未在生产中被调用
    # _create_engine_instance() 手动重造了所有对象
```

**影响**: 两个初始化路径，不同步。改了 factory 忘记改 start() → 不一致。

### 2. on_event() — 3500行遗留

```python
# engine.py — 3500+ 行 serial NLP chain
# 仍在 on_event() 中活跃
# on_event_sm() 没有引用它,两者互不知
```

### 3. 导入错误变无声失败

```python
# api.py 有 4 个 import 包裹在 try/except:
try:
    from core.agent.v4.api_viz_edit import router as viz_edit_router
except ImportError:
    viz_edit_router = None  # ← 模块删了,import 还留着

try:
    from core.agent.v4.api_annotate import router as annotate_router
except ImportError:
    annotate_router = None  # ← 同上

# 类似的还有 v3_2.integration, v4.cognitive 等模块
```

**影响**: 功能静默丢失，无人知晓。

---

## 五、数据真实性 (P1)

### v6 API 端点数据审计

```
端点                    状态    数据内容
────────────────────────────────────────────
/v6/profile            ✅      OCEAN 10维 (mock 0.5)
/v6/sessions           ✅      44 sessions (JSON)
/v6/graph              ✅      节点+边
/v6/discourse-tree     ✅      63 blocks
/v6/behavior           🟡      edges=0 (无对话历史)
/v6/meta               ✅      reviewed:true
/v6/abc                ✅      rules=6
/v6/mind               ✅      subsystem list
/v6/objects            ⚠️      count=0
/v6/relations          ⚠️      count=0
/v6/causal             ⚠️      chains=0
/v6/pipeline           ⚠️      traces=0
/v6/extraction         ⚠️      tiers=0
/v6/perspectives       ⚠️      horizon=0
/v6/parameters         ⚠️      registry empty
/v6/engineering        🟡      KG 在线但空
/v6/annotations        ✅      12 entries (pipeline auto-fill)
/v6/corrections        ✅      12 entries
/v6/feedback           ✅      empty (无错误)
/v6/metrics            ✅      subsystem stats
/v6/audit              ✅      4 dimension report
```

**结论**: 17 端点返回真实数据, 7 端点返回空——需要对话积累或引擎填充。

---

## 六、测试缺口 (P2)

### 现状

```
单元测试: 76 (CLI 28 + Event 46 + Pluggable 2)
集成测试: 0
API 契约测试: 0
性能测试: 0
```

### 缺失

| 测试类型 | 应覆盖 | 现状 |
|----------|--------|:---:|
| 管线测试 | PCR→Intent→...→PERSIST 全链 | ❌ |
| API 合约 | 17 端点 200 + 正确 schema | ❌ |
| 并发测试 | EnginePool 4-slot 并发 | ❌ |
| 降级测试 | NATS down → memory fallback | ❌ |
| 回归测试 | on_event → on_event_sm 行为一致 | ❌ |

---

## 七、架构维度评分

| 维度 | 评分 | 关键问题 |
|------|:---:|----------|
| 凝聚度 | 4/10 | engine.py 3721行承担太多职责 |
| 耦合度 | 5/10 | 双轨导致隐式依赖 |
| 可扩展性 | 7/10 | SubsystemRegistry + ToolRegistry 到位 |
| 韧性 | 4/10 | 降级存在但未测试 |
| 可观测性 | 6/10 | Tracer+EventLog+HotStore 三层 |
| 可测试性 | 3/10 | 无集成测试, engine 启动依赖 37 子系统 |
| 性能 | 5/10 | HotStore sub-μs,但 start() 660行浪费 |
| 安全性 | N/A | 无 auth (localhost only) |
| 可部署性 | 4/10 | 无 Dockerfile, 无 CI/CD, 依赖外部 Gateway |
| 白盒性 | 7/10 | 75 端点,16/23 属性可见, CLI 全覆盖 |

**加权总评: 5.0/10**

---

## 八、修复路线图

### P0 — 本周 (结构性风险)

| 任务 | 文件 | 影响 | 成本 |
|------|------|------|:---:|
| on_event → 路由到 on_event_sm | engine.py | 消除双轨 | 2h |
| engine.start() → 合并到 factory | engine.py, cli/engine.py | 统一初始化 | 3h |
| 删除 api.py 4个死 import | api.py | 清理无声失败 | 30m |

### P1 — 下周 (代码质量)

| 任务 | 文件 | 影响 | 成本 |
|------|------|------|:---:|
| engine.py 拆分 | runtime/engine.py → 3-4文件 | 可维护性 | 4h |
| v6 空端点补齐 | stubs_api.py, engine.py | 数据真实性 | 3h |
| 设计文档校对 | docs/DESIGN_*.md | 信任修复 | 2h |

### P2 — 之后 (工程化)

| 任务 | 影响 | 成本 |
|------|------|:---:|
| 5条关键路径集成测试 | 防回归 | 3h |
| 设计文档瘦身 23→10 | 可读性 | 2h |
| CI/CD pipeline | 自动化 | 4h |

---

## 九、诚实结论

```
DialogMesh v6 是一个野心勃勃的项目。
设计文档覆盖度很高，但代码实现有显著差距。

能跑 —— CLI 166 命令、v6 75 端点、37 子系统全部在线。
不敢改 —— engine.py 3721行无测试覆盖，双轨遗留代码从未清理。

如果今天上线生产:
  - Mock 模式: ✅ 能跑
  - DeepSeek 模式: ⚠️ Gateway 需要健康
  - 高并发: ❌ 无 EnginePool 集成
  - 长时间运行: ⚠️ EventLog 无限增长未设上限
```


---

## 十、归档策略 — un_use/


---

## 十-B、注册表设计债 — SubsystemRegistry 从未接入

### 状态

```
SubsystemRegistry: 0 registered entries
代码库子系统级类: 295 个
引擎工厂: 手动 from X import Y; self._y = Y() (绕过 registry)

根因: 
  SubsystemRegistry 在 cli/registry.py 设计好了(拓扑排序、依赖注入)
  但 engine.py 的 _create_engine_instance() 从未调用 registry
  所有对象都是手动 import + 构造

  这个设计是对的——registry 不应该被滥用。
  不是每个类都需要注册,只有"跨模块依赖的核心子系统"才需要。
```

### 当前 DI 方式 (保留)

```python
# cli/engine.py — _create_engine_instance()
_engine._ocean_analyst = create_ocean_analyst()   # 手动构造
_engine._meta_cognition = MetaCognition()           # 手动构造
_engine._mind = Mind()                              # 手动构造
# ... 17 个对象,全部手动
```

### 何时接入 registry

```
P2 — 当子系统超过 30 个且跨模块依赖复杂时:
  1. 将 17 个核心对象注册到 registry
  2. factory 改为 registry.resolve() 链
  3. 测试改为 get_engine() 读取

当前手动 DI 对 17 个对象足够,registry 过度设计不必要。
```

### 历史上下文

```
SubsystemRegistry 在 v4 时期设计(当时有 40+ 子系统需要拓扑排序)
v6 精简到 17 个核心对象后,手动 DI 更简单
保留 registry.py 但不强制使用——设计 doc 标注即可
```


---

## 十、归档策略 — un_use/ (续) (不删除,安全退回)

### 原则

**不删除危险代码——归档到 `un_use/` 目录。**
- git log 永远可恢复
- `un_use/` 全文搜索快
- 出问题 → 10 秒找到原文

### engine.py 归档 (~3500 行移出)

```
保留 (~200 行):
  on_event_sm()              唯一入口
  _create_engine_instance()  统一初始化
  stop() / status()

移入 un_use/engine_legacy/:
  on_event()                      → legacy_on_event.py      (~3500 行)
  start()                         → legacy_start.py         (~660 行)
  _feed_profile / _retrospect     → legacy_cognitive.py
  _validate_* / _diff_*           → legacy_validation.py
```

### api.py 清理

```
删除 4 个 try/except ImportError 死 import
每个标注 git SHA 可恢复
```

### un_use/ 目录

```
un_use/
  ├── engine_legacy/
  │   ├── legacy_on_event.py
  │   ├── legacy_start.py
  │   ├── legacy_cognitive.py
  │   └── legacy_validation.py
  └── README.md  归档原因+恢复方法
```

### 恢复

```
git show <commit>:engine.py → 完整恢复
```

---

## 十一、实施策略 — 先覆盖,后迁移

### 原则

迁移前必须确保新代码完全覆盖旧代码。先验证 → 再路由 → 再归档。

### 阶段 A: 覆盖验证 (审计)

| 步骤 | 内容 | 产出 |
|:----:|------|------|
| A1 | 审计 `on_event()` 做什么 | coverage_map.md |
| A2 | 审计 `on_event_sm()` handler 覆盖 | gap_list.md |
| A3 | 标注 gap | 待修复清单 |

### 阶段 B: 补缺口

| 步骤 | 内容 | 文件 |
|:----:|------|------|
| B1 | 补齐缺失 handler | handlers.py |
| B2 | on_event → passthrough to on_event_sm | engine.py |
| B3 | 全量测试验证 | pytest 78/78 |

### 阶段 C: 归档

| 步骤 | 内容 |
|:----:|------|
| C1 | 创建 un_use/engine_legacy/ |
| C2 | on_event/start 移入 legacy 文件 |
| C3 | engine.py 瘦身 ~200行 |
| C4 | 清理 api.py 死 import |

### 阶段 D: 验证

| 步骤 | 内容 |
|:----:|------|
| D1 | 重启后端,验证 v6 端点 |
| D2 | 3轮对话验证管线持久化 |
| D3 | git tag pre-archive + post-migrate |

### 回退

任何阶段失败: `git checkout engine.py api.py` → 恢复 → 重新开始


---

## 十二、持久化存储架构设计 (2026-07-31 讨论)

### 当前问题

```
GranularityRegulator: 5 regex patterns 纯结构切分
  → 代码块/JSON/结构化数据被强行切碎
  → 无 "non-chunkable" 标记

AssociationChain: 事后处理已切好的块
  → 无法否决切分决策
  → 无法说"这块不该切"

检索: ContextAssembly 拿整块对话
  → 子图自己过滤,无索引加速
```

### 双层存储方案 (借鉴 Graph RAG)

```
写入层:

  raw conversation
        │
   ┌────┼────┐
   ▼    ▼    ▼
  DiscourseTree    ChunkStore (vector)    RelationGraph (association)
  (完整块+摘要)     (语义切分原子)         (实体+关系)
   block_id          atom_id              entity_id
   summary           embedding            edge
   parent/child      chunkable: T/F       strength
   heat              block_id ←──→        block_id

  非摘要化标记:
    code_block / exact_quote / config → chunkable=False
    → 不入 ChunkStore
    → 仅存 block_id 引用
    → 检索时直接返回 block_id → DiscourseTree 取全文

检索层:

  1. 向量搜索 → top-k atoms (细粒度,快速定位)
  2. atom.block_id → 图遍历找关联 entities
  3. entity → 找到所有关联 atoms (展开)
  4. block_id → DiscourseTree.get_context(block_id)
     → 返回完整对话块 + 关联摘要 (粗粒度,保结构)

  子图消费:
    - 需要摘要 → 拿 DiscourseTree block summary
    - 需要扩展 → 拿 ChunkStore atoms + RelationGraph edges
    - 需要全文 → 拿 DiscourseTree block raw text
```

### 元信息驱动的聚类压缩

**不重新切分内容——调整元信息。**

```python
class BlockMeta:
    block_id: str
    summary: str          # 摘要 (可调整)
    tags: List[str]       # 标签 (可调整)
    priority: float       # 优先级 (可调整)
    chunkable: bool       # 是否可切分 (可调整)
    cluster_id: str       # 聚类归属 (可调整)
    # ← 内容不变,只有这些元信息可调整

# 聚类压缩流程:
clusters = group_by_cluster_id(blocks)       # 按 cluster_id 分组
for cluster in clusters:
    summary = llm_summarize(cluster)          # 只读元信息
    update_meta(cluster, summary=summary)     # 写入元信息
    # ← 不碰原始 block 内容
```

**优势:**
- 每次调整只改元信息 (bytes,不是 KB)
- 内容不可变 = 安全 (聚类错误可随时回退)
- 多一次跳转 (元信息 → 内容, ~0.1ms) — 可忽略

**代价:**
- 元信息量表会增长 (~100B/block, 10K blocks = 1MB)
- 需要同步机制 (HotStore 缓存 + disk 持久化)

**设计对应已有基础设施:**
- HotStore → 元信息内存缓存
- ColdStore → 元信息 JSON 持久化
- BlockTree → 内容不可变存储
```

### 开元项目对照 (2026-07-31 读取)

**读取文件:**
1. `langchain/text_splitters/character.py` — RecursiveCharacterTextSplitter
2. `microsoft/graphrag/extract_graph.py` — Entity extraction
3. `llamaindex/ingestion/pipeline.py` — IngestionPipeline

**模式对照:**

| 模式 | 开源实现 | DialogMesh 已有 | 缺什么 |
|------|----------|:---:|------|
| 递归切分 | LangChain: ["\n\n"→"\n"→" "→""] 递归降级, chunk_size+overlap, 小块合并 | GranularityRegulator (5 regex) | **递归降级 + non-chunkable 标记** |
| 实体提取 | GraphRAG: LLM extract per unit → (entities, relations) df, max_gleanings 迭代, filter_orphans | AssociationChain L1→L3 | **orphan_relationships 清理 + max_gleanings** |
| 管线缓存 | LlamaIndex: hash-based IngestionCache, in_place 避免拷贝, TransformComponent 链 | HotStore LRU | **hash-based dedup (避免重复处理)** |
| 双层存储 | 无统一方案 | DiscourseTree + ChunkStore (设计阶段) | **实现向量+图双写** |

**三个补丁,不改变现有架构:**

```python
# 补丁 1: 递归切分 (嵌入 GranularityRegulator)
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]  # 递归降级
NON_CHUNKABLE_PATTERNS = [r'```[\s\S]*?```', r'> .*', r'^\s*\{.*\}\s*$']

# 补丁 2: orphan 清理 (嵌入 AssociationChain)
def filter_orphan_relationships(entities, relationships):
    entity_ids = set(entities['id'])
    return [r for r in relationships 
            if r['source'] in entity_ids and r['target'] in entity_ids]

# 补丁 3: hash-based dedup (嵌入 HotStore)
def should_process(text: str) -> bool:
    h = sha256(text.encode()).hexdigest()
    if hotstore.get(f"processed:{h}"):
        return False  # 已处理,跳过
    hotstore.set(f"processed:{h}", True)
    return True
```

### AssociationChain 重新定位 — 前置富化器 (2026-07-31 讨论)

**问题:** 当前 AssociationChain 在切分后运行,只能修碎片内部,无法恢复切分丢失的上下文。

**修正:** AssociationChain 作为 GranularityRegulator 的**前置处理器**——在切分前完成代词解析和上下文限定。

```
当前 (错误):
  raw → cut() → fragments → extract()
        ↑ 代词未解析          ↑ 事后补

修正:
  raw → resolve() → enriched → cut() → self-contained chunks
        ↑ L1 代词→对象  ↑ L2 加限定
```

**变换示例:**

```
输入: "auth模块要重构。它用JWT。token过期后需要刷新。"

阶段1 — 代词解析 (L1 Modifier):
  → "auth模块要重构。[auth模块]用JWT。[JWT token]过期后需要刷新。"

阶段2 — 上下文限定 (L2 Belief):
  → "auth模块要重构。[auth模块,依赖JWT]用JWT。[JWT token,需刷新机制]过期后需要刷新。"

阶段3 — 切分:
  chunk_1: "auth模块要重构。[auth模块,依赖JWT]用JWT。"
  chunk_2: "[JWT token,需刷新机制]过期后需要刷新。"
  → 每个 chunk 自包含,不丢信息
```

**对应已有基础设施:**

```
L1 ModifierExtractor → resolve_pronouns(text, context_window)
  - 已有: _last_concept + _conversation_tracker 跟踪上下文
  - 需加: pronoun→entity 映射表

L2 BeliefAccumulator → qualify(text, belief_graph)
  - 已有: evidence ingestion + confidence
  - 需加: dependency 注入 [entity, depends_on=X, confidence=Y%]

L3 Validator → cross_check(enriched_text, context)
  - 已有: multi-perspective validation
  - 需加: 限定质量检查 (过度限定? 限定正确?)
```

**收益:**
- 切分不丢信息 (代词已还原)
- chunk 可独立消费 (不需原始上下文)
- 聚类压缩直接用丰富文本 (不需回查)
- 非摘要化内容不受影响 (chunkable=False 跳过)

