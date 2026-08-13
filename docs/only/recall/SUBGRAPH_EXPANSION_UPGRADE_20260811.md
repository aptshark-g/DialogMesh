# 子图扩展增强设计 — 多锚点 / 导向搜索 / 全局社区 / 异步（2026-08-11）

> 触发: 用户 "子图扩展这个有没有看到相关的 graph rag 的内容？" +
> "我们是分层的吧？先粗召回确立锚点再跑图搜索，全局的速度怎么样？是独立的吧？
> 那异步跑怎么样？我们是多锚点一起跑子图扩展的，bfs 会不会爆？用 ida 会好的吗？"
> 依据: GraphRAG (2404.16130) / VDGR-RAG (2608.07994) / Beyond Top-K (2608.06305)
> 现状代码: core/agent/v4/cognitive/subgraph_compiler.py +
> core/agent/context/graph_source.py（ConceptGraph）
> **2026-08-11 追加（用户拍板升级）: 全文改为"查询导向局部扩展"流水线设计
> —— 不跑全图; 粗召回多方向命中集天然是 DAG 子图; 在子图邻域分层扩展 +
> 同步剪枝 + 流式拼接; 并行子问题分解（LLM 增强）。**

---

## 一、现状核查（代码实测, 2026-08-11）

### 分层链路（已存在 ✅）
```
recall() 粗召回锚点（vector+bm25+spo+assoc RRF）
  → compile_from_anchors(anchors[:8]) 三路合并:
      1. R 锚点条目（text[:300], 带 path → 执行层精确查阅）
      2. _expand_from_event（同 trace 生产轨迹, max_hops=2 BFS）
      3. expand_from_graph → ConceptGraph.compile_context（局部实体遍历）
```

### 三个真问题（代码证据）

| # | 问题 | 证据 |
|---|------|------|
| P1 | **多锚点共享预算, 单锚点语义稀释** | compile_from_anchors 取 anchors[:8], 但 expand_from_graph 的 query = "前 3 个锚点文本拼接"（subgraph_compiler.py:265）; compile_context max_nodes=8 是**全体共享**额度 |
| P2 | **BFS 无导向扩散, 边 confidence 未参与剪枝** | expand_subgraph 是纯 k-hop BFS（graph_source.py:283）; 边 confidence 只在 edge 记录里, 不影响扩展顺序/剪枝 |
| P3 | **无全局层（社区摘要）** | expand_from_graph 只做局部实体遍历; GraphRAG 的社区摘要（全局问题正解）完全缺失 |

---

## 二、回答用户 5 问（设计判断）

1. **分层?** ✅ 已是"粗召回定锚点 → 图搜索", 无需重构分层, 只增强各层。
2. **全局速度/独立性?** 社区摘要是**预生成**（建索引慢, 查询快）, 与查询路径
   独立 → 天然可异步。我们应: 图构建/社区摘要后台异步做, 查询只读。
3. **异步跑?** ✅ 合理。图搜索与粗召回无依赖（锚点定好后图扩展独立）;
   异步结果以 `SubgraphContext` 增量并入（先给 R 锚点, 图结果到了再补）。
4. **多锚点 BFS 会爆?** 有 max_nodes 上限不会无限爆, 但共享预算稀释单锚点。
   → 改 **per-anchor 独立预算 + best-first**, 而非全体共享 BFS。
5. **IDA\* 更好?** 概念图非树, A\*/IDA\* 需可采纳启发式（难保证）;
   **best-first（优先级队列按 confidence×relevance）** 是更实际选择:
   导向性 > BFS, 实现复杂度 < A\*。边 confidence 参与优先级 = 自然剪枝。

---

## 三、增强设计（v2.2, 定案 — 查询导向局部扩展流水线）

### 核心洞察（用户, 2026-08-11 拍板）

1. **不跑全图**: 完整概念图社区检测/遍历 O(N²)/O(N·E), 大量节点与 query
   无关 → 无用成本。GraphRAG 的 local query 本质也是查询导向局部遍历。
2. **粗召回多方向命中集 = 天然 DAG 子图**: vector/bm25/spo/hyde/assoc 各
   方向都从 query 发散, 合并命中集天然是以 query 为根的展开结构; 边是
   转化投影（因果/时序导向）→ 大概率无环。
3. **DAG 无环 = 无重复访问 = 不会爆**: 有拓扑序, 扩展沿拓扑序走, 复杂度
   O(锚点数 × 平均邻域度), 与全图 N 无关 — "归并大幅减量级"的数学依据。
4. **时序渐入拼接**: 每层扩展结果就是拼接的一个切片, 白盒天然可见。

### 设计 1: DAG 分层局部扩展 + 同步剪枝（改 P1/P2）
```
# 输入: 粗召回锚点集 A（多方向命中, 天然 DAG 子图）
# 分层扩展（拓扑序）:
layer = A                                    # 第 0 层 = 锚点
for depth in 0..max_hops:
    frontier = 边界节点(layer)                # 本层外沿（邻域）
    for node in frontier:
        for rel in node.relations:            # 邻接表 O(1) 取邻域
            prio = rel.confidence × node.relevance
            if prio < θ: continue             # 同步剪枝（低置信边丢弃）
            add(rel.target, prio)             # 纳入下一层候选
    layer = top_k(候选, budget_per_depth)     # 每层预算, 剪枝后进下层
    emit(layer)                               # 时序渐入: 每层结果即切片
```
- 邻接表索引化邻域查询: 每跳 O(1) 取邻域, 而非扫全图（用户陷阱点 ①）
- 跨锚点桥接: 每层扩展后检查局部子图间桥接边（用户陷阱点 ②）,
  防"锚点 A 经中间节点连到 B"被漏
- 权重归一: 同一节点被多锚点扩展 → 分数合并规则
  （max/sum/归一, 定 max + 记录命中锚点数, 白盒可见）
- 复杂度: O(锚点 × 邻域度 × hop), 与全图 N 无关

### 设计 2: 并行子问题分解（LLM 增强, 用户 2026-08-11 追加）

现状缺口（代码实测）: `_expand_questions` 已有 LLM 展开 2-3 子问题,
但: ① 只走 vector 路（不走 bm25/spo/assoc）; ② for 循环串行; ③ 无失败
反馈/跳过。

```
query → LLM 分解为 3-5 子问题（含原 query）
  → 每子问题并行粗召回（threading/asyncio; LLM 调用是 I/O 密集, GIL 无碍）
  → 每子问题锚点集并入 DAG 子图（设计 1 的层 0）
  → 子问题级失败处理: 某子问题召回为空 → 记录 miss + 反馈
     （标记"该角度找不到", 不阻塞整体; 供元认知复盘）
  → 各子问题 DAG 结果流式拼接（时序渐入）
```

- 并行: LLM 分解调用 + 各子问题召回全是 I/O 密集 → threading 足够
  （.venv = Python 3.13.13, free-threading 可用; 无需等新版本）
- 失败反馈: 子问题 miss 不阻塞, 记录后跳过; 汇总时标注"未覆盖角度"
- 与 A18 反馈闭环: miss 子问题 = 学习信号（query 分解质量可改进）

### 设计 3: 全局社区层（改 P3, 对齐 GraphRAG, 排后）
```
图构建期（异步, 后台）:
  LLM 提取实体 → 关系图 → Leiden/Louvain 社区检测
  → 每社区生成摘要（LLM, 预生成）
查询期（同步, 快）:
  query → 社区摘要向量库 top-k（轻量）
  → 命中社区的实体节点作为额外 seed 并入 best-first 扩展
```
- 解决全局性问题（"这套系统主要做什么"）— 局部遍历答不了
- 查询期只做向量 top-k + 摘要选择, 毫秒级; 建索引成本在后台

### 设计 4: 流水线总览（三条并行）
```
粗召回流（同步, 毫秒级）:
  query → LLM 分解（设计 2）→ 各子问题四路召回 → 锚点 DAG
图搜索流（异步, 沿锚点 DAG 分层扩展）:
  锚点 DAG 邻域扩展（设计 1）→ 同步剪枝 → 跨锚点桥接
拼接流（时序渐入）:
  每层结果 emit → SubgraphContext 增量并入 → 执行层白盒可见
```
- 粗召回先到, 图结果后补 → 首 token 延迟不因图搜索增加
- 与 SAGE (2608.08237) 动态预算思路一致: 难查询自动多检
- 用户 2026-08-11 判断: "整个流程是并行的, 效率不会低"

### 性能/并行说明（用户问: py 是不是没多线程?）

- **LLM 子问题分解 + 各子问题召回 = I/O 密集**（网络等待）: threading/
  asyncio 足够, GIL 不阻塞 I/O 等待
- **向量编码已有 GPU**（torch cu124, RTX3080）: 批量 encode 不占 GIL
- **图搜索计算核心**（余弦/BM25/邻域扩展）若成 CPU 热点 → rust + rayon
  （RECALL_RUST_DESIGN 已定: pyo3 + rayon, 无状态纯函数可并行）
- 结论: 不需要等 Python 版本; 3.13 free-threading 是加分项非依赖

---

## 四、与 GraphRAG 的差距（诚实）

| GraphRAG 能力 | 我们现状 | 设计后 |
|---|---|---|
| 实体图构建（LLM 两阶段） | ConceptGraph 有, 但构建源窄（观测文本） | 保持, 扩源 |
| 局部查询（实体遍历） | ✅ find_seeds + expand_subgraph (BFS) | ✅ 设计 1（DAG 分层扩展） |
| **全局查询（社区摘要）** | ❌ 无 | ✅ 设计 3 |
| 社区检测 | ❌ 无 | ✅ Leiden/Louvain |
| 摘要预生成 | ❌ 无 | ✅ 异步后台 |

---

## 五、施工顺序建议

1. **设计 2（并行子问题分解）**: 纯增量, 改 `_expand_questions` +
   `_hyde_anchors`（并行 + 全路 + 失败反馈）, 立刻可评测验证（四路对比）
2. **设计 1（DAG 分层局部扩展 + 同步剪枝）**: 改 `expand_subgraph` 为
   邻接表 + 分层扩展（拓扑序）, 无新依赖; 用文档图/DOC_RECALL 验证
3. **设计 4 拼接流（异步时序渐入）**: 独立, 解决首 token 延迟 + 白盒
4. **设计 3（社区层）**: 依赖图规模, 排最后; 先确认概念图数据量再定

> 关联: RECALL_MAINSTREAM_GAP_20260811.md（整体差距）;
> RECALL_RUST_DESIGN（性能热点: 邻接表/余弦/BM25 可 Rust 化 + rayon）;
> 并行 I/O 用 threading 即可（.venv Python 3.13, free-threading 可选）

---

## 六、施工记录（2026-08-11 完成）

### 已实现（代码 + 测试全绿）

1. **开关字段**（RecallService `__init__`）:
   - `parallel_decompose`（默认 False）: LLM 并行子问题分解
   - `decompose_subqueries`（默认 3）/ `decompose_max_workers`（默认 4）
   - `dag_layer_expand`（默认 False）: DAG 分层局部扩展
   - `dag_max_hops` / `dag_prune_threshold`（0.3）/ `dag_budget_per_layer`（12）/
     `dag_bridge_check`（True）
2. **并行子问题分解**（recall_service.py）:
   - `_expand_questions`: 子问题数可配, 失败记录 `_decompose_misses` 兜底
   - `_expand_questions_legacy`: 旧 2-3 子问题行为（开关关闭时）
   - `_hyde_anchors`: 并行（ThreadPoolExecutor, I/O 密集）每子问题走
     vector+bm25+spo **全路**（旧: 串行只 vector）; 空召回 → miss 记录
   - `recall()` 按开关选择展开方式
3. **DAG 分层局部扩展**（graph_source.py `expand_subgraph`）:
   - 开关开启 → `_expand_subgraph_layered`: 分层边界扩展 + confidence×
     relevance 同步剪枝 + 每层预算截断 + 跨锚点桥接; 边带 `prio` 字段
   - 开关关闭 → 旧 BFS（行为不变）
4. **蓝图线路注册**（tools/builtin.py）: `recall_decompose` 工具进
   ToolRegistry（category=parse, 中文关键词）, 蓝图 tool 节点 /
   tool_loop 经 ToolRegistry.execute 可调, 与 /v6/recall 同源
5. **测试**: recall +8（分解计数/失败记录/并行全路/空召回 miss）;
   graph +3（剪枝/预算/回退 BFS）; 修 2 个预存在测试基建缺陷
   （conftest assertrepr dict 崩溃 + test_write_index 缓存目录未隔离 +
   异步 flush 未同步）

### 验证
- recall 套件: 27 passed（2 个预存在失败不变: bm25/diffusion）
- graph 套件: 3 passed; tools 套件: 71 passed
- 相关全量: 96 passed / 2 failed（预存在）
- `recall_decompose` 工具注册验证通过（ToolRegistry.resolve 成功）

### 遗留
- `dag_layer_expand` / `parallel_decompose` 默认 False（开关关闭,
  不改变既有行为）; 需评测对比开/关后拍板默认值
- ~~全局社区层（设计 3）未施工~~ ✅ 已施工（见下）
- ~~拼接流异步（设计 4）未施工~~ ✅ 已施工（见下）

### 2026-08-11 追加施工（设计 3 + 设计 4）

**设计 3 全局社区层**（graph_source.py, 对齐 GraphRAG）:
- `build_communities()`: networkx greedy_modularity 社区检测（无新依赖）;
  每社区聚合节点+观测生成摘要（`_community_summaries`）; 小图/无边跳过
- `community_top_k(query)`: 查询期社区摘要向量 top-k（有嵌入）/
  关键词兜底（无嵌入）; 命中社区节点可并入局部扩展 seed
- `build_from_pool` 尾部自动调 build_communities（图构建期完成）

**设计 4 异步拼接流**（subgraph_compiler.py）:
- `async_graph_expand(query, max_nodes, on_result)`: 后台 daemon 线程跑
  expand_from_graph, 完成回调 on_result(entries) — 粗召回先回 R 锚点,
  图结果后补（首 token 延迟不因图搜索增加）
- `merge_incremental(ctx, new_entries)`: 时序渐入拼接 — (domain,content)
  去重 + 预算超限按 confidence 裁剪

**新增测试**: graph +3（社区检测/查询 top-k/小图跳过）; subgraph +3
（增量去重+预算/空安全/无引擎异步返回 None）; 全量 108 passed /
2 failed（预存在 bm25/diffusion, 与本轮无关）
