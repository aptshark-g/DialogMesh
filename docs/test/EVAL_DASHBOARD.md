# DialogMesh 评测面板 — 统一参数与指标（2026-08-11）

> 自动生成: `scripts/eval_dashboard.py`（读 docs/test/ 产物, 不重跑评测）
> 口径: RAGAS 标准 docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md
> 状态标注: ✅ 已实现 / ⚠️ 口径受限 / ❌ 未实现

---

## 记忆评测（会话黄金集）

- **query**: 82
- **blocks**: 360
- **mode**: rrf
- **top_k**: 5
- **top1**: 29.3
- **top3**: 42.7
- **top5**: 57.3
- **random_baseline**: 5.8
- **context_precision**: 0.375
- **cp_at**: 5

---

## 精细化消融（L0 粗召回 / L1 子图 / L2 LLM 选择）

- **query**: 15
- **top_k**: 10
- **L0_top1**: 53.3%
- **L1_top1**: 53.3%
- **L2_top1**: 20.0%
- **L0_avg_ms**: 2436.8
- **L1_avg_ms**: 0.049
- **L2_avg_ms**: 3912.8
- **note**: goldset 无图数据 → L1 实为 top-10 透传, 非真图搜索

---

## 精细化基准（粗召回 top1 vs LLM 挑选 top1）

- **query**: 15
- **top_k**: 10
- **coarse_top1**: 53.3%
- **refine_top1**: 20.0%
- **avg_select_ms**: 3171.2

---

## Agent 任务评测（真实 v3 链路）

- **n**: 5
- **success_rate**: 1.0
- **avg_latency_s**: 24.7
- **p95_latency_s**: 31.2
- **tokens_per_task**: 9460

---

## 文档域召回（docs/only 全量）

- **query**: 50
- **blocks**: 2444
- **random_baseline**: 0.2
- **top1_linear**: 44.0
- **mrr_linear**: 0.534

---

## 跨语言变体评测（BGE-M3 统一）

- **orig_top1**: 22.0
- **zh_syn_top1**: 18.0
- **en_top1**: 24.0
- **casual_top1**: 24.0
- **variant_all_top1**: 22.0

## 缺失/受限（诚实标注）

- ❌ **Context Recall**（claim 级, LLM）: 未实现 — memory_bench 只做块级命中
- ❌ **Faithfulness/幻觉率**（claim 级, LLM）: 未实现 — 需 v3 回复拆 claims 判定
- ⚠️ **L1 子图**在 goldset 无图数据下 = top-10 透传, 非真图搜索
- ⚠️ **AGENT_EVAL_SUMMARY** 中记忆指标为旧集（40 query/218 块）; 现为 82/360
- ⚠️ **REFINE_CHAIN_DUMP** LLM 返回空为网关缓存 bug（已修, 可重跑）
