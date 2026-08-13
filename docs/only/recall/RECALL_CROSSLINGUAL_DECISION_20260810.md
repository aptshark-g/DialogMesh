# 跨语言召回决策 + 符号注入施工项（2026-08-10）

## 一、变体评测结论（已落盘 docs/test/DOC_RECALL_VARIANT_BENCH_20260810.md）

- en top1 0% → 24%（MRR 0.063→0.355）: BGE-M3 统一 1024 维 + 向量粗筛 + BM25 跨语言保护
- 中文 tradeoff: 原查询 22% vs bge-small-zh 32%（-10pp）

## 二、拍板（用户 2026-08-10）

1. **保 bge-m3 统一**（接受中文 -10pp, 换取跨语言统一空间）
   - 环境: DM_BGE_M3=1 / 配置 use_bge_m3
   - 模型: models/models/BAAI--bge-m3/snapshots/master（2.27GB, ModelScope 快照）
   - semantic_encoder: bge-m3 模式统一 1024 维, 无语言路由, CLS pooling
   - 注: bge-m3 单语中文弱于 bge-small-zh → 后续若要中文单语提升, 走双语双索引（A 方案）待命
2. **下一施工项: 执行迹 → 符号图注入 tool_loop 上下文**
   - 参考: TencentDB Agent Memory 的 MMD 符号注入（token -61% 实证）
   - 分析: docs/only/reference/TENCENTDB_AGENT_MEMORY_ANALYSIS_20260810.md

## 三、符号注入施工项（设计要点）

### 现状（已核查 tool_loop）
- 已有结构: 蓝图任务图（nodes/edges）+ 执行迹 trace（steps）
- 但注入 tool_loop 上下文的是**原文**: 每轮 tool 结果 json.dumps(...)[:4000] 直接进 messages
- 工具调多 → 上下文膨胀 → token 浪费（TencentDB 实证可省 61%）

### 三层缺口
1. **提炼层**: 已完成步骤 → 状态转换摘要（"已写 X → 已运行 Y → 结果 Z"）
2. **注入层**: tool_loop 上下文放紧凑符号图（几百 token），非原文
3. **offload + node_id**: 原文落盘文件, 符号节点带 id, 需要细节按 id 取原文

### 与既有定案的关系
- 呼应"蓝图=任务地图 + 执行层微观": 执行时把任务状态符号图注入上下文
- 检索侧结构化（文本→SPO/块→混合锚点）已有; 注入侧结构化（文本→符号图→上下文）是补缺

### 开放问题（施工前再议）
- 符号格式: Mermaid / 自定义紧凑 DSL / JSON 摘要?
- 提炼器: LLM 提炼（每 N 步一次） vs 规则提炼（trace 已有结构）?
- 注入时机: 每轮 / 每 N 轮 / 超阈值时?
- 原文 offload 位置: 沿用 trace_store / 新 refs 目录?
