# DialogMesh 量化评测汇总 — 第一轮（2026-08-10）

> 目的: 用量化数据回答"我们到底行不行", 对齐 JD 高频指标
> 口径: RAGAS 标准（docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md）
> 分层记录（用户拍板）: 粗召回（本地通用）/ 精细化（图搜索+LLM 选择）/ 生成层

---

## 一、Agent 任务评测（真实 v3 链路, N=5）

- 方法: POST /v3/session → message（走真实链路, 编码类自动进 tool_loop）
- 任务: simple（写 hello.py 并运行）+ code（质数求和脚本并运行）

| 指标 | 值 | 说明 |
|---|---|---|
| 成功率 | 10/10 (100%) | 偶发 1/6 空回复（前一轮, 需跟踪） |
| 端到端延迟 avg | 24.7s | 绝大多数是 LLM 生成（~20s/次） |
| 端到端延迟 p95 | 31.2s | 工具调用额外 2-5s |
| Token/任务 | ~4.7K | prompt 为主（含系统提示+工具 schema） |
| 成本/任务 | ¥0.009 | deepseek-v4-flash |

> 注: 延迟与召回无关（召回本地毫秒级）; 瓶颈是云端 LLM 生成时间。
> 详情: docs/test/AGENT_BENCH_20260810.md（JSON 原始数据）

---

## 二、记忆评测（会话黄金集 40 query / 218 块, RAGAS 口径）

- 数据: data/recall_goldset.json（真实对话自动生成, 非手写）
- 随机基线: top-k 理论命中 11.3%

| 指标 | linear | rrf | 随机基线 |
|---|---|---|---|
| top1 命中率 | 37.5% | **52.5%** | 11.3% |
| top3 命中率 | 65% | 72.5% | - |
| top5 命中率 | 75% | 80% | - |
| **Context Precision@5** | 0.492 | **0.603** | - |

- RRF 融合全面优于 linear（+15pp top1, +0.11 CP）
- Context Precision 0.603 = 相关块排序质量（加权, 分母=相关项数）
- 详情: docs/test/MEMORY_BENCH_20260810.md

---

## 三、文档域召回（DOC_RECALL_BENCH, 2026-08-09 基线 + 2026-08-10 变体）

- 2444 块文档, 50 query, top1 44.0%（随机 0.2%）— 8/9 基线
- 变体评测（BGE-M3 统一后, 10969 块）: 原 22% / zh_syn 18% / en 24% / casual 24%
- en 0%→24% 修复（跨语言）; 中文 -10pp（bge-m3 tradeoff, 已拍板）
- 详情: docs/test/DOC_RECALL_BENCH_20260809.md + DOC_RECALL_VARIANT_BENCH_20260810.md

---

## 四、分层记录（用户拍板, 对外展示口径）

```
粗召回（本地, 通用 agent）   top-k 命中率 + Context Precision/Recall
  ↓ 锚点
精细化（图搜索 + LLM 选择）   选择提升率（单独记录; 选择 ~1-2s << 生成 ~20s）
  ↓ 上下文
生成层（LLM 回复）            Faithfulness（幻觉率 = 1-F, claim 级判定）
```

---

## 五、待补（下一步）

1. Faithfulness（幻觉率正解）: agent_bench 扩展 — 回复拆 claims → 检索上下文支持判定（LLM）
2. Context Recall（claim 级）: 黄金集 reference 拆 claims → 检索上下文覆盖判定
3. 并发吞吐: 网关压测（8080, 独立任务）
4. 延迟构成拆分: LLM 调用次数 × 单次耗时（定位 24.7s 里的真正大头）
5. 偶发空回复跟踪: tool_loop 空 content 分支深挖

---

## 六、对外展示建议（数字口径）

- 任务成功率 100%（10 次样本）; 诚实标注样本量
- 召回: top1 52.5%（rrf, 随机 11.3%）+ Context Precision 0.603
- 跨语言: en 24% top1（BGE-M3 统一, 修复 0%）
- 延迟 24.7s: 标注"LLM 生成主导, 召回本地毫秒级"
- 成本 ¥0.009/任务: 标注模型单价
