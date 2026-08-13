# 召回评测标准统一 — RAGAS 官方口径（2026-08-10）

> 来源: RAGAS docs（explodinggradients/ragas）context_precision / context_recall / faithfulness
> 目的: 纠正此前"幻觉率 = 1 - precision@k(固定分母)"的错误口径, 统一业界标准

---

## 一、三个核心指标（RAGAS 标准）

### 1. Context Precision（检索排序质量）
$$CP@K = \frac{\sum_{k=1}^{K} Precision@k \times v_k}{相关项总数 in top-K}$$
- Precision@k = 前 k 中相关项占比
- v_k ∈ {0,1} 位置相关指示
- **关键: 分母是相关项数, 不是固定 k** —— 加权平均, 越相关越靠前分越高

### 2. Context Recall（不遗漏 / 检索准确率正解）
$$CR = \frac{被检索上下文支持的参考 claim 数}{参考 claim 总数}$$
- LLM 把参考答案拆成 claims, 逐条判定能否从检索上下文推出
- **claim 级语义召回, 不是块级命中** —— 记忆检索准确率的正确度量

### 3. Faithfulness（幻觉率正确定义）
$$F = \frac{响应中被检索上下文支持的 claim 数}{响应 claim 总数}$$
- LLM 把生成回复拆成 claims, 判定是否忠于检索上下文
- **JD 要的"幻觉率" = 1 - Faithfulness**, 不是召回无关率

---

## 二、错误口径复盘（已纠正）

- 此前: "幻觉率 = 1 - precision@5(命中/5)" → 黄金集 73%
- 问题: 期望块通常 1-3 个, 固定分母 5 → 即使全对也只有 0.6
- 正确: 用 RAGAS 加权公式 + claim 级判定

---

## 三、应用映射（我们的评测）

| 指标 | 我们怎么测 | 数据源 |
|---|---|---|
| Context Precision | 黄金集加权(相关项数分母) | data/recall_goldset.json |
| Context Recall | claim 级判定(LLM) | 黄金集 query→reply |
| Faithfulness | 回复 claim 级判定(LLM) | v3 任务评测的回复 |
| top-k 命中率 | 已有(粗召回) | DOC_RECALL_BENCH / goldset |

分层记录（用户拍板 2026-08-10）:
- 粗召回（本地, 通用 agent）: top-k 命中率 + Context Precision/Recall
- 精细化（图搜索 + LLM 选择）: 选择提升率（单独记录, 选择比生成快得多）
- 生成层: Faithfulness（幻觉率）
