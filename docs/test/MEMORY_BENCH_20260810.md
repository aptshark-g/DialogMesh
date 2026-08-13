# 记忆评测 — 检索准确率 + 幻觉率（2026-08-10）

- 数据: data/recall_goldset.json（39 query / 181 块）
- 层: all（coarse=粗召回 / scene=情景再现 / all=全部）
- 融合: rrf; top-5

## 指标

| 指标 | 值 | 随机基线 |
|---|---|---|
| top1 命中率 | 69.2% | 11.8% |
| top3 命中率 | 92.3% | - |
| top5 命中率 | 94.9% | - |
| Context Precision@5 | 0.771 | - |
| MRR@5 | 0.797 | - |
| nDCG@5 | 0.824 | - |
| Recall@5 | 94.9% | - |
| Recall@10 | 97.4% | - |
| Recall@20 | 97.4% | - |

## 幻觉率（Faithfulness, 待 LLM claim 判定）

- 定义: 回复中被检索上下文支持的 claim 占比（RAGAS）
- 需在 v3 任务评测里对回复逐条拆 claim 判定, 与召回无关率区分
- 待接入: agent_bench.py 扩展（回复 → claims → 上下文支持判定）

## 说明

- Context Precision: 相关块越靠前分越高（分母=相关项数）
- 口径依据: docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md
- 与 DOC_RECALL_BENCH 互补: 那是文档域 top1 命中, 这是会话域
- 复跑: `.venv\Scripts\python.exe scripts/memory_bench.py --mode rrf`
