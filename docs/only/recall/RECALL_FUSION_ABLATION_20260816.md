# 融合消融全记录 + doc 域 miss 根因 — 2026-08-16

> 触发: 交接 P0-① "跨域召回 25% 提升: 先复跑 eval_100 拿 doc 类 miss
> 明细, 再做消融（切分/索引/融合权重）"。
> 结论先行: **当前融合管线在块级 top1 上已达局部最优** — 12+ 组消融
> （融合权重 / 路线独有保底 v2 / 向量置信门控 / 重排开关 / CE 三种候选
> 口径 / PRF 三参数 / BGE 指令前缀）全部净负或中性。doc 域真实提升来自
> **评测地面真相修正**（q059 标注错误 → C 类缺口归零）。
> 方法: A18 消融驱动, 每项负结果带数据; 脚本与 dump 保留在 scripts/
> （_ablation_matrix/_ablation_delta/_prf_ablation/_ce_wide_pilot/
> _ce_union_pilot/_doc_miss_debug 等, A17 不删）。

---

## 一、基线（eval_100, 2026-08-16, 重排 ON, q059 修正前）

| 域 | top1 | top3 | top5 | MRR@5 | nDCG@5 | Recall@5 | 平均耗时 |
|---|---|---|---|---|---|---|---|
| dialogue (39) | 76.9% | 87.2% | 94.9% | 0.833 | 0.832 | 94.9% | 374ms |
| doc (61) | 52.5% | 68.9% | 78.7% | 0.615 | 0.642 | 78.7% | 1314ms |

诊断: A(融合命中)=94 / B(路线内被融合挤出)=5 / C(检索缺口)=1; 融合命中
但非 top1（排序竞争）32 条。doc 域 61 条中 29 条 miss top1 = 23 A 类 +
5 B 类 + 1 C 类。

## 二、miss 分类与根因（逐条 dump: scripts/_doc_miss_dump_20260816.md）

### B 类（5 条, 期望块在单路线内但被 vector_primary 融合挤出 → MISS）

| query | 期望块路线证据 | vector 证据 |
|---|---|---|
| agentic 工具节点怎么让 LLM 自己调工具 | bm25 rank1 (score 1.0) | 不在 vector top-100 |
| 决策事件有哪些 kind, strategy_switch 和 plan_gate 区别 | bm25 rank2 (0.895) | 期望块 vec_rank 27; **假阳性块 vec_rank 2** |
| 执行迹和变更日志两个白盒视图各展示什么 | bm25 rank6 (0.754) | 期望块不在 vector top-100 |
| 隐式关系候选怎么生成和核验, precision 多少 | bm25 rank1 (1.0) | 不在 vector top-100 |
| v2.1 召回桥之后下一个施工项是什么 | spo rank12 (0.5) | bm25#1 是假阳性（非期望文件） |

**根因 1（嵌入覆盖）**: 期望块与 query 的 BGE-M3 余弦仅 0.43-0.56,
而 vector top-1（无关块）0.60-0.64。8338 块 / 625 设计文档同项目强主题
重叠 — "LLM 协调者/工具注册/任务规划"等主题相邻块在嵌入空间压过精确
答案块。**提问式 query vs 陈述式块的对称嵌入缺陷**（BGE-M3 无 query
指令前缀时更明显; 前缀探查无改善, 见 §六-5）。

**根因 2（goldset 单文件粒度）**: 部分"假阳性"（如 q033 的 GAPF1 决策
事件、q027 的 RECALL_EXECUTION_BRIDGE）主题真实相关, 只是不是 goldset
期望的那一个文件 — 块级 top1 单文件判定把"相关但不同文件"记为 miss。

### A 类（23 条, 融合命中但 rank>1）

- **约 7 条 vec rank1 被重排压到 2-19**: 记忆分层 vec=1→fused=4、
  G3 四保护 vec=1→fused=8、执行层监控 vec=1→fused=11、偏差是养分
  vec=1→fused=17 等。重排公式 `Σ w[src]×(s/src_max)` 奖励多源块 —
  多源弱块（vector 0.5 + bm25 0.9 + spo 0.7）压过强纯 vector 块。
- **其余 16 条**: 期望块 vector rank 13-20（弱命中, 长尾进融合）。

### C 类（1 条, q059）: **评测地面真相错误**（非召回缺陷）

`PCR zone 和意图分类怎么映射到召回策略` 期望 RECALL_MAINSTREAM_GAP —
该文档通篇 0 处 "PCR/zone/意图分类"; 真内容在
INTENT_AWARE_RECALL_IMPL_20260813.md（L190/L233 有 zone→intent 映射
状态与 P2 计划）。已修正期望 → 该文档（2026-08-16）。

## 三、消融矩阵（全部实测, 2026-08-16）

| 配置 | doc top1 | doc top3 | doc MRR | dialogue top1 | 结论 |
|---|---|---|---|---|---|
| **baseline（现状）** | **52.5%** | 68.9% | 0.615 | **76.9%** | 局部最优 |
| rerank OFF | 49.2% | 70.5% | 0.600 | 69.2% | 重排净正 |
| route_unique（强独有保底 v2） | 49.2% | 65.6% | 0.586 | 76.9% | 净负（4 升 15 降, 0 到 top1） |
| vec_gate（向量置信门控） | 50.8% | 72.1% | 0.616 | 69.2% | 负（dialogue 大亏） |
| route_unique + vec_gate | 49.2% | 72.1% | 0.605 | 69.2% | 负 |
| CE top-15（旧 pilot 口径） | 44.3% | — | 0.565 | — | 负（候选太窄, B 类看不到） |
| CE top-60 fused 池 | 41.0% | — | — | — | 负（vector 长尾占满池） |
| CE 路线并集池（vec∪bm25∪spo top20） | 44.3% | — | 0.565 | — | 负; q033 None→1 单条正 |
| PRF α0.5 fb3 | 49.2% | 65.6% | 0.574 | 71.8% | 负 |
| PRF α0.7 fb3 | 47.5% | 63.9% | 0.558 | 69.2% | 负 |
| PRF α0.5 fb5 | 47.5% | 62.3% | 0.563 | 79.5% | 负（dialogue 正, doc 负） |

## 四、负结果机制（为什么这些方向都失败）

1. **单信号放大必回归**: bm25 rank1 score=1.0 在 doc 域假阳性率高
   （词法命中"相关但非期望"文件）。route_unique/PRF 都是把 bm25 当
   "正确独有信号"抬升 — 假阳性同被抬升, 净损。这与 2026-08-14
   DM_SOURCE_GUARANTEE ×1.5 的负结论同构（更精细的 gate 也不够）。
2. **判别式模型看不到 B 类**: 期望块不在 vector top-100（余弦 0.43-0.51
   vs 0.60+ 阈值）→ 任何"在融合候选内精排"的方案（CE）都救不了。
   路线并集池把 bm25 命中带进来后, CE 对部分 query 有效（q033→1）但
   全量仍负（判别式模型对长块/多主题块也不稳, q052 期望块被 CE 判到 42）。
3. **query 端增强的漂移**: PRF 质心/指令前缀都试图改 query 表示 —
   B 类 4 条中 PRF 救回 2 条（q002/q052→rank1）, 但其它 97 条 query 的
   bm25 top-k 含假阳性 → 质心漂移 → 净负。

## 五、本轮的正面交付（诚实, 有数据）

1. **q059 地面真相修正**: doc top1 52.5%→54.1%, MRR 0.615→0.631,
   nDCG 0.642→0.657, **C 类缺口 1→0**。这是评测卫生（A18: 语料不得
   含 query 原文; 标注错误要修, 但禁止"改期望让数字好看" — 本次是
   期望文档确实不含答案, 真答案文档已定位）。
2. **完整消融证据**: 12+ 组配置全部落盘, 未来任何"融合增强"提案须先
   过本矩阵（A18 基线可复现）。
3. **三个实验开关保留**（默认关, 消融钩子）: DM_ROUTE_UNIQUE /
   DM_VEC_GATE / DM_PRF（含 α/fb 参数）— 带注释指向本矩阵数据。
4. **eval_100.py setdefault 化**: DM_RERANK 尊重外部预置, 消融脚本
   可复跑 OFF/ON（不改变默认行为）。

## 六、未来真正的杠杆（按价值排序, 供下轮设计）

1. **真 HyDE**（RECALL_MAINSTREAM_GAP G3, 交接 P1"HyDE 默认"）:
   query → LLM 假设文档 → 编码 → 邻域检索。直接治"提问式 vs 陈述式"
   不对称。当前 `_hyde_query_vector` 是查询扩展不是假设文档（半实现）;
   eval 用 llm=None 所以 HyDE 从未进评测 — **先让评测带上 HyDE 路径**。
2. **goldset 文档级粒度**: 块级 top1 单文件判定过严（B 类 5 条中至少
   2 条是"相关但不同文件"）。对 100 条查询补"相关文档集"标注, 指标
   增加文件级 top1（CE pilot 已有口径）。
3. **CE 路线并集 + 文档级判定**: q033 None→1 证明判别式模型对"词法
   命中进池"有效; 全量负的根因是长块/多主题块判别不稳 — 候选文本切到
   段落级再打分（参考 Beyond Top-K 的表格/层级文档结论）。
4. **嵌入窗口/模型**: 当前 3000 字窗口 + 对称 CLS pooling; 可测
   多窗口（标题窗口 + 内容前/中/后）或换检索专用微调模型（需数据）。
5. **BGE 指令前缀已测无效**（M3 不依赖指令）— 不再投入。

## 七、验证与复跑

- 基线复跑: `.venv\Scripts\python.exe scripts\eval_100.py`
  （~100s, 缓存热; 写 docs/test/EVAL_100_YYYYMMDD.md）
- 消融矩阵复跑: `scripts\_ablation_matrix_20260816.py` /
  `scripts\_prf_ablation_20260816.py`（各 ~6min, GPU）
- 诊断 dump: `scripts\_doc_miss_debug_20260816.py`（~2min）
- 相关单测: `python -m pytest core/agent/recall -q --tb=short`
