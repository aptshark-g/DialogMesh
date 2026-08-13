# 压缩交接 — 召回体系完整化（切分/评测/Rust/内容→图/蓝图, 2026-08-12）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: STATE_HANDOFF_20260809（§十二）→ 本轮延续
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN → 按待办优先级开工

---

## 一、本轮完成（全部实测）

### 1. 评测集清理 + 统一 100 条
- goldset 去重清噪音: 82 → **39 条**（去掉 27 重复竞态 + 乱码/hello world/问候）
- 文档 query: 50 → **61 条**（新增 11 条: graph/execution/storage/frontend/意图域）
- **统一查询集**: `docs/test/recall_queries_100.md`（39 对话 + 61 文档, md 表格格式）
- `scripts/query_set.py`: md/json 双格式加载 + 去重（软拓展, 直接编辑 md 加行）

### 2. 量化指标（清理后真实水平）
- **块级（39 条对话）**: top1 **69.2%** / R@5 **94.9%** / R@10 97.4% /
  MRR 0.797 / nDCG 0.824（随机基线 11.8%）
- **Context Recall**（claim 级, batch 判定稳定）: 18 条样本 **0.562**
- 消融: parallel_decompose 开 → **R@5 +9.5pp**（LLM 分解有效, top1 略降, 成本 +3x）
- 融合负增益定位: RRF 对多源共现通用块过度加权（9 条 vector 命中被挤掉, 未修）

### 3. 切分修复（StructurePreSplitter）
- `core/agent/discourse_block_tree/structure_pre_splitter.py`（新建）:
  代码/JSON 整体保留（non_chunkable 不截断）、标题+正文同块、列表/引用成组、
  空壳标题/装饰线/空代码过滤、短块并入前块
- 两级粒度（设计 12.2）: 每块带 summary, vector/bm25 优先对摘要打分（Coarse scan）
- goldset 重建: `---`/`###` 开头 0、空代码 0、7 字符残块消除
- `chunk_document` 走生产链路（ToolRegistry 注册）

### 4. 评测基建
- memory_bench 加 MRR/nDCG/Recall@5/10/20 + 分层（coarse/scene）
- claim_eval: Context Recall（batch 判定 + 重试稳定化）+ Faithfulness 骨架
- eval_100: 100 条无 LLM 全指标脚本（评估后 61 doc query ~25 分钟, 未全量跑完）
- eval_dashboard: 统一 6 类评测产物面板
- 修复 conftest assertrepr dict 崩溃 + test_write_index 缓存隔离 + 异步 flush 同步

### 5. 内容→图（CONTENT_TO_GRAPH）
- **WikilinkParser**: frontmatter + 双链解析（Obsidian vault 35 篇）
- **UnifiedGraphStore.delete_domain**: 幂等重建
- vault 图落盘: **110 节点 / 159 边**（35 vault + 75 docs 映射,
  wikilink 30 + cross_ref 117 + inferred_verified 12）
- 隐式关系发现: 108 候选 → LLM 核验 12 真关系（precision 11%,
  高相似段 33%）
- **图导航 API**: neighbors/callers/path（BFS）
- **文档↔代码桥**: 图节点 metadata.doc → cross_refs file: path → file_read
- 图构建耗时: 解析 9ms / 落盘 2477ms / 加载 355ms

### 6. 子图扩展增强（SUBGRAPH_EXPANSION_UPGRADE 设计 1-5）
- DAG 分层局部扩展 + 同步剪枝 + 跨锚点桥接（开关 dag_layer_expand）
- 并行子问题分解（开关 parallel_decompose, LLM 分解 + 全路并行召回）
- 全局社区层（networkx greedy_modularity + 社区摘要）
- 异步图扩展 + 增量拼接（async_graph_expand / merge_incremental）
- 蓝图模板注册: `recall_pipeline`（pcr→intent→recall_anchor 工具→subgraph→llm_reply）
- `recall_decompose` 工具进 ToolRegistry

### 7. Rust 内核（recall_rs）
- cosine_topk / bm25 / coarse 三函数 + rayon 并行 + 规模感知
- **PyBuffer 零拷贝**: 378 块 10.3ms → 2.03ms（与 numpy 持平）; 10969 块 1.7x
- `recall_rust_bridge.py`: Rust 优先 + Python 回退（四级回退链）
- recall_service `_vector_anchors` 接入 Rust 批量余弦
- **缓存持久化 bug 修复**: 缓存只写 hash 不写 spo/vector → 每次全量重算
  140s; 修复后 SPO 全命中; hot 路径 pre_vec 透传缺失 → 8526 块重编码
  340s; 修复后 21s（可再优化: batch_vecs list→array 拷贝）

### 8. 蓝图模板
- recall_pipeline 模板 + 意图"记忆召回"映射 + 3 测试（149 蓝图套件全绿）

---

## 二、待办（优先级排序）

### P0（正确性/评测可信）
- [ ] **eval_100 全量跑完**（100 条, 当前 ~25 分钟; BM25 接 Rust 后应大幅提速）
- [ ] **Faithfulness 幻觉率实现**（claim_eval faithful 骨架已写, 需 8000 API）
- [ ] **BM25 接 Rust**（bm25_scores 已编译未接, Python 循环 8.6-10s/query）
- [ ] vector batch_vecs list→array 拷贝优化（21s → 应 <2s）

### P1（召回增强）
- [ ] **RRF 通用块降权**（融合负增益: 多源共现块过度加权, 9 条 vector 命中被挤）
- [ ] 意图分析接 recall（intent 参数死参数; PCR zone → 召回策略映射设计已写
  RECALL_MAINSTREAM_GAP）
- [ ] 任务类 query 走执行层轨（task 意图 → 蓝图 recall_pipeline 模板）
- [ ] HyDE 真实现（生成假设文档, 非扩展查询词）
- [ ] 图检索进主链路（domain G 参与 RRF, 需图评测集）

### P2（工程/后续）
- [ ] LLM 章节摘要（9750 章, 成本高）
- [ ] C-MTEB / BEIR 公开基准
- [ ] Rust f32 + SIMD（记录在 RECALL_RUST_OPTIMIZATION_NOTES）
- [ ] 博客 chapter4 / 前端 B / 跨域召回 / trace_id §11.2

---

## 三、环境坑（必读, 防复发）

1. **PowerShell 管道传中文必变 ?** — 中文脚本/输入一律写文件执行
2. **网关 8080**: Bearer dm-client; provider=deepseek; model=deepseek-v4-flash;
   **max_tokens < 256 空返回**（拆 claims/判定用 128-2048）
3. **网关限流**: DM_GATEWAY_RATE_LIMIT=0 关闭（已改 switch + 编译 gateway.exe）
4. **pyo3 0.21 不支持 3.13** — 用 0.22 + abi3-py311（buffer 模块在
   abi3+Py<3.11 被禁用）
5. **PYO3_PYTHON 必须指向 .venv 3.13**（否则 cargo 用 anaconda 3.9 编译报错）
6. **cargo 联网下载需提权**（沙箱挡 crates.io）; cdylib 需复制 .pyd
7. **persistence_rs .pyd 从未成功导入** — rust_bridge 一直回退 Python
8. **VEC_CACHE 累积式缓存**（只加不删）— 块 id 变化后新块无向量, 需重跑
   prepare_vectors 补全
9. **conftest assertrepr hook** 对 dict 崩溃（已修）; state.json 权限坑

---

## 四、关键设计论断（用户拍板）

1. **评测分层**: 粗召回（RAG 语义）/ 任务规划（资源感知+模板）/ 记忆恢复
   （情景再现）各用各的指标
2. **任务类 query 的正解** = 执行层精确查阅（recall 定位候选 → file_read 读真）
3. **信息内容才是召回核心**: 文档语料（8.7MB/702 篇）+ Obsidian 图需进统一语料
4. **内容→图**: Obsidian 双链/INDEX/frontmatter 是现成图（extracted）;
   召回式关联发现 + LLM 核验补隐式边（inferred_verified）
5. **摘要索引 + 全文懒加载**（三级粒度, 非全量索引）
6. **Rust 规模感知**: <2000 块 numpy, ≥2000 Rust（小池 Rust 曾负优化,
   零拷贝后持平）

---

## 五、git 状态

- 改动未提交（按惯例压缩前不提交）; 143 项（M + ??）
- 新增关键文件: structure_pre_splitter / wikilink_parser / recall_rust_bridge /
  query_set / eval_100 / build_vault_graph / recall_rs（crate）/
  CONTENT_TO_GRAPH / SUBGRAPH_EXPANSION_UPGRADE / RECALL_RUST_OPTIMIZATION_NOTES /
  RECALL_MAINSTREAM_GAP / RECALL_MAINSTREAM_REFS / recall_queries_100.md
- 数据: data/unified_graph.db（vault 图 110/159）; scripts/.recall_vec_cache.json
  （8594 条文档向量）
