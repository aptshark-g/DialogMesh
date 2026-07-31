# DialogMesh 深度核查 — 第二轮

> 2026-08-01 · 方法: 逐批次追踪真实行为, 非数端点
> 状态: 🔍 进行中 (Batch 4 剩余命令)

## 核查方法 (升级版)

```
每批核查 = 真实调用 + 检查返回数据 + 判断是否简化/存根
  1. 启动引擎 (mock) — 引擎未启动时命令必然 "not loaded"
  2. 调用 CLI 命令 / API 端点
  3. 检查返回的是真实数据还是空壳/error
     ⚠️ rc=0 + 输出非空 ≠ 通过 — 必须检查输出内容!
     ⚠️ {"error": ...} 是失败, 不是通过
  4. 连锁问题找根因 — "not loaded" 可能是上游失败
  5. 标记: ✅ 真实行为 / ⚠️ 部分简化 / ❌ 存根或失败
```

## 核查批次清单

| 批次 | 范围 | 状态 |
|------|------|:---:|
| Batch 1 | 引擎启动 + 管线 + 持久化 | ✅ 19/19 (verify_round1.py) |
| Batch 2 | v6 API 89 端点 | ✅ 5 存根已补 (前端可绑定) |
| Batch 3 | CLI 核心命令 | ✅ 根因修复 (inspect 遮蔽) |
| Batch 4 | CLI 剩余命令 (引擎启动态) | 🔍 |
| Batch 5 | 存储层深度 (ChunkStore/RelationGraph/BlockMeta) | ⏳ |
| Batch 6 | 关联链深度 (L1/L2/L3/coref) | ⏳ |
| Batch 7 | 模型层 (stanza/st) | ⏳ |

## 核查结果汇总

| 批次 | ✅ | ⚠️ | ❌ | 备注 |
|------|:--:|:--:|:--:|------|
| Batch 1 | 19 | 0 | 0 | 引擎+管线+落盘全通 |
| Batch 2 | 84 | 0 | 5→0 | 5 存根已补真实实现 |
| Batch 3 | 22 | 0 | 0 | inspect.py 遮蔽修复后全通 |
| Batch 4 | 37 | 32 | 3→0 | 引擎启动态, 3 命令崩溃已修 |
| Batch 5 | 5 | 4 | 1→0 | 存储层, 2 深层修复 (registry 缺注册 + 搜索) |

---

## 全局深层根因 (最重要发现)

**`core/agent/cli/inspect.py` 遮蔽标准库 `inspect`**

```
根因链:
  inspect.py (业务模块) 与标准库同名
  → python core/agent/cli/entry.py 时 sys.path[0] = cli/ 目录
  → import inspect 解析到业务模块 (无 signature 属性)
  → dataclasses._process_class 崩溃 (inspect.signature)
  → engine start 失败 → 所有命令 "not loaded"

修复: inspect.py → inspect_cmd.py, inspect_v3.py → inspect_v3_cmd.py
验证: engine start → 37/37 loaded, 0 failed, 115ms

教训: "not loaded" 是连锁反应 — 引擎起不来一切不工作
      rc=0 + 输出非空 ≠ 通过 — 必须检查输出内容
```

---

## Batch 2 — v6 API 深度核查

### 深层根因 (2026-08-01 复盘)

**`core/agent/cli/inspect.py` 遮蔽标准库 `inspect`** — 本次核查最重要的发现:

```
根因链:
  inspect.py (业务模块, CLI inspect 命令) 与标准库同名
  → python core/agent/cli/entry.py 时 sys.path[0] = cli/ 目录
  → import inspect 解析到业务模块 (无 signature 属性)
  → dataclasses._process_class 调用 inspect.signature 崩溃
  → engine start 失败 (所有 dataclass 定义崩)
  → 所有依赖引擎的命令返回 "not loaded"

修复: inspect.py → inspect_cmd.py, inspect_v3.py → inspect_v3_cmd.py
验证: engine start → 37/37 loaded, 0 failed, 115ms

教训: "not loaded" 是连锁反应 — 引擎起不来, 一切都不工作
      表面核查 (rc=0 + 输出非空) 会误判 error 响应为通过
```

### 修复后真实状态 (引擎启动后)

```
✅ rules show       → ABC orchestrator loaded
✅ abc show         → ABCOrchestrator
✅ metrics show     → 5 subsystems
✅ behavior show    → behavior_graph + discovery
✅ meta show        → meta_subscriber + meta_cognition
✅ assoc show       → L1 modifier loaded=True
✅ profile show     → OCEAN 5 维真实值
✅ profile ocean    → 完整 5 维
✅ discourse stats  → 1 block
✅ knowledge stats  → rag=True
✅ event-log        → 真实 log entries
```

### 发现的问题 (全部修复)

1. **get_engine() sentinel bug** — `isinstance(_engine, object)` 永远 True
   → get_engine 永远返回 None → 所有 CLI 命令假阴性
   → 修复: 模块级 `_ENGINE_SENTINEL` + identity 比较

2. **5 个 dispatch 函数缺失** (entry.py 引用但模块无定义):
   - p3_cmd: cmd_obs_reset
   - p4_cmd: cmd_profile_export, cmd_profile_import
   - knowledge_cmd: cmd_knowledge_stats, cmd_knowledge_search

3. **argparse 冲突 (subparser 重复注册)**:
   - rules ×2 (p5_cmd 内部) → 合并
   - inertia ×2 (p5_cmd 内部) → 合并
   - meta (p3_cmd vs storage_cmd) → storage 改名 blockmeta
   - graph (entry main vs storage_cmd) → storage 改名 rgraph
   - knowledge (entry main vs knowledge_cmd) → main 独占, knowledge_cmd skip

4. **k_op vs subcommand 字段不匹配** — knowledge 用 k_op, dispatch 取 subcommand
   → _dispatch_p3 兼容两者

5. **cmd_metrics_show 无 None 防御** — 引擎未启动时崩溃
   → 加 get_engine None 检查

### 结果

```
25 条命令验证: 20 ✅ 5 ⚠️ 0 ❌

✅ 真实数据: session list (真实4轮), annotations recent/export (33条),
             session new, task show
✅ 诚实空:   engine off 时 chunk/rgraph/blockmeta/metrics/knowledge
             → 明确报 "not available"/"engine not running" (非存根)
⚠️ 空 dict:  behavior/meta/assoc/profile show + engine chains
             → 引擎未启动返回 {}, 可优化为显式 "not running"

28 tests green
```

### 结论

- "192 命令" 此前是虚数 — 多个 dispatch 指向不存在函数或 None
- 本轮让 P3/P4/P5/P8/storage 命令真实可执行
- 28 个 CLI 测试只覆盖入口, 不覆盖命令真实执行路径 → 需要本核查
```

### 真实数据端点 (示例)

| 端点 | 返回 | 判断 |
|------|------|:---:|
| /v6/profile | OCEAN 8 维度真实值 | ✅ |
| /v6/abc | 6 条 neuro_symbolic 规则 (修复后) | ✅ |
| /v6/graph | 真实 graph nodes | ✅ |
| /v6/discourse-tree | 真实 block (session b84e1b45) | ✅ |
| /v6/objects | 真实 concept objects | ✅ |
| /v6/parameters | 真实参数配置 | ✅ |
| /v6/sessions | 真实 session 文件列表 | ✅ |
| /v6/context | assembler/budget/pruner | ✅ |

### 发现的问题

1. **/v6/abc 字段名 bug (已修复)** — 代码取 `antecedent`, 数据是 `premise`
   → 返回 5 个空串。修复: `_rule_summary` 用 name/premise。
   → 教训: "有查询逻辑" ≠ "字段对得上", 必须验真实输出。

2. **7 个空数据端点 (待深查)**:
   - /v6/pipeline → {}
   - /v6/extraction → {}
   - /v6/perspectives → {}
   - /v6/subgraph → {}
   - /v6/versions → {}
   - /v6/persistence/graphs → []
   - /v6/session/{filename} → empty (路径参数未替换)

3. **/v6/providers active 全空** — `{"name":"","display_name":"",...}` 
   → gateway 未配置 active provider (真实空, 非简化)

4. **/v6/chat + /v6/checkpoint/respond 慢** — 需 ~14s (加载 embedding 模型)
   → 首次加载开销, 非 bug

### 简化检测

- [x] /v6/abc: 曾有字段错位 (修复)
- [x] **5 个纯存根端点 (实锤)** — `return {}`:
  - /v6/pipeline → `return {}` (注释 V6PipelineResponse, 模型不存在)
  - /v6/extraction → `return {}`
  - /v6/perspectives → `return {}`
  - /v6/subgraph → `return {}`
  - /v6/versions → `return {}`
  → 这些不是"真实空数据"——是根本没有实现。前端调用会收到 `{}`。
  → 修复策略: 需要设计文档定义响应结构 (V6*Response 类不存在), 再接入真实数据源。

- [ ] /v6/providers: active 全空 — 待查 gateway 初始化 (api_gateway 模块存在?)
- [ ] 14 个 POST 422 — 测试方法问题, 非端点问题 (已确认 schema)
- [x] /v6/parameters, /v6/context: stubs 是回退, 真实实现在 pipeline_api.py ✅

### Batch 2 结论

```
66/89 真实数据 (74%)
5 个纯存根 → 已全部替换为真实实现 (2026-08-01):
  ✅ /v6/pipeline     → StateMachine snapshot (running/current_phase/turns/errors)
  ✅ /v6/extraction   → EntityExtractor stats + HybridCoref metrics
  ✅ /v6/perspectives → ContextWindow stats (items/tokens/block_ids)
  ✅ /v6/subgraph     → RelationGraph domains/entries (V6SubgraphResponse schema)
  ✅ /v6/versions     → EventLog + corrections journal → V6VersionCommit[]

  数据源对照 (来自 frontend/src/types/api.ts):
    V6PipelineResponse:  自由结构 → state machine snapshot
    V6ExtractionResponse:自由结构 → entity extractor stats
    V6PerspectivesResponse: 自由结构 → context window
    V6SubgraphResponse:  {perspective, domains, entries, total_tokens, budget}
    V6VersionsResponse:  {target, commits: V6VersionCommit[]}
      V6VersionCommit:   {id, ts, author, before, after, reason, verify}

+18 端点来自真实 router 模块
API 基础可用, 5 个存根已补

前端绑定判断: ✅ 可绑定 (5 存根已补真实实现)
  剩余待查: /v6/providers active 空 (gateway 配置)
          14 个 POST 422 (测试方法, 非端点问题)

### 新发现 (2026-08-01 补充)

**10 个 api_* 模块死引用** — `_try_include` 尝试加载但不存在:
```
SKIP api_parameters, api_context, api_pipeline, api_metrics,
     api_persistence, api_meta, api_abc, api_mind,
     api_versions, api_subgraph
```
→ 这些路径设计时计划拆分, 但从未创建模块
→ 实际由 stubs_api.py (prefix /v6) 提供全部端点
→ 真实存在的 api_* 模块: 仅 4 个 (annotate/event_log/gateway/viz_edit)
→ 不是 bug, 但说明"路由分层"设计未落地 — 记录为 P2 设计债

**RelationGraph 纯 Python 化** — 移除 pandas 硬依赖:
- list[dict] 替代 DataFrame (entities/relationships)
- pandas → 可选 (to_dataframe() 视图)
- networkx → 可选 (try_build_graph())
- 修复 /v6/subgraph 端点适配 list backend
```

---

## 简化/存根检测清单

遇到以下模式必须记录:

- [ ] 返回空列表/dict 但应有数据
- [ ] `except: pass` 吞错
- [ ] 硬编码值而非真实计算
- [ ] 未实现的函数体 (pass/NotImplementedError)
- [ ] 假数据 (mock 返回但没标注)
- [ ] 重复实现 (两处代码做同一件事)

---

## Batch 5 — 存储层深度核查

### 关键发现

**1. `build_dialogmesh_registry` 缺 Phase 1-3 注册 (已修复)**
```
start_engine() 用 build_dialogmesh_registry (registry.py)
_create_engine_instance() 用 subsystem_registrations._registry
→ 两个 registry 不同步 — Phase 1-3 组件只在后者
→ CLI (start_engine 路径) 永远拿不到 _chunk_store 等

修复: build_dialogmesh_registry 补 12 个注册 (Tier 9)
验证: start_engine → 49/49 loaded, 12/12 组件 attach
```

**2. ChunkStore 搜索多词失败 (已修复)**
```
search("auth 认证") → 0 hits (旧: 整串 substring 检查)
修复: 多词 OR 匹配 (任一 term 命中即返回)
验证: auth→b1, 认证→b1, "token 刷新"→b2, 不存在→[]
```

### 验证结果

```
✅ ChunkStore      add/dedup/search 全工作 (in_memory, 3 atoms)
✅ SemanticSplitter 切分 + non-chunkable (code block → 1 chunk, chunkable=False)
✅ ContextWindow   5 items, 62 tokens, FIFO
✅ RelationGraph   entities+rels, orphan 清理 (1 removed), BFS traverse
✅ BlockMeta       tags/cluster/non-chunkable 元信息操作
```
