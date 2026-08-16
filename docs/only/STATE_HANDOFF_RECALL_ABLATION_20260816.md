# 压缩交接 — 融合消融全记录 + doc 域 miss 根因 + 评测地面真相修正（2026-08-16）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: docs/only/STATE_HANDOFF_V1_STABILIZE_20260816.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN（顶部已指向）→ 读 AGENTS.md +
>  追踪矩阵 + RECALL_FUSION_ABLATION_20260816.md（§七 复跑命令）
> 环境: 8000（.venv API）+ 8080（网关）+ 4173（前端）在跑; 全量 pytest
>  ~4:21 可复跑（2068 绿）

## 〇、本轮主线（交接 P0-① 跨域召回）

1. **复跑 eval_100 拿 doc 域 miss 明细**（交接建议的第一步）→ 29 条
   miss 全量归因: A(融合命中但非top1)=23 / B(路线内被挤出)=5 /
   C(检索缺口)=1
2. **12+ 组融合消融矩阵** → **基线局部最优**（每项负结果带数据,
   完整记录: docs/only/recall/RECALL_FUSION_ABLATION_20260816.md）
3. **q059 评测地面真相修正** → doc top1 52.5%→54.1%, C 类 1→0

## 一、doc 域 miss 根因（三句话）

1. **B 类（5 条）**: 期望块与 query 的 BGE-M3 余弦仅 0.43-0.56, 不在
   vector top-100; bm25 rank1-2 强命中（score 0.89-1.0）被 vector_primary
   长尾埋掉 → fused MISS。根因 = 625 设计文档同项目强主题重叠 + 提问式
   query vs 陈述式块的对称嵌入缺陷。
2. **A 类（23 条）**: 约 7 条 vec rank1 被重排归一化压到 2-19（多源弱块
   压过强纯 vector 块）; 其余 16 条期望块 vector rank 13-20 弱命中。
3. **C 类（1 条, q059）**: **标注错误非召回缺陷** — 期望文档
   RECALL_MAINSTREAM_GAP 通篇无 "PCR/zone/意图" 内容, 真内容在
   INTENT_AWARE_RECALL_IMPL（L190/L233）。已修正期望。

## 二、消融矩阵（全部实测, 细节见设计文档 §三）

| 配置 | doc top1 | dialogue top1 | 结论 |
|---|---|---|---|
| **baseline** | **52.5%** | **76.9%** | 局部最优 |
| rerank OFF | 49.2% | 69.2% | 重排净正 |
| route_unique v2 | 49.2% | 76.9% | 4 升 15 降, 0 到 top1 |
| vec_gate | 50.8% | 69.2% | dialogue 大亏 |
| CE top-15 / top-60 / 路线并集 | 44.3% / 41.0% / 44.3% | — | 判别式全负（q033→1 单条正） |
| PRF α0.5/0.7, fb3/5 | 49.2% / 47.5% / 47.5% | 71.8% / 69.2% / 79.5% | 质心漂移净负 |
| BGE 指令前缀 | 无改善（probe） | — | M3 不依赖指令 |

**机制（为什么全失败）**: 单信号放大必回归（bm25 rank1 假阳性率高,
与 08-14 source_guarantee 同构）; 判别式模型看不到 B 类（不在 vector
top-100）; PRF 质心对 97 条正常 query 漂移。

## 三、本轮正面交付

1. **q059 地面真相修正**（评测卫生, 非改数字）: doc top1 52.5→54.1%,
   MRR 0.615→0.631, nDCG 0.642→0.657, C 类 1→0。最终基线写入
   docs/test/EVAL_100_20260816.md。
2. **消融证据链落盘**（A18）: 设计文档 + 全部脚本/dump（scripts/_
   20260816*）, 未来融合提案必须先过本矩阵。
3. **三个实验开关**（默认关, 消融钩子）: DM_ROUTE_UNIQUE /
   DM_VEC_GATE / DM_PRF（α/fb 可调）— recall_service.py 带注释指向
   消融数据。
4. **eval_100.py setdefault 化**: DM_RERANK 尊重外部预置, OFF/ON 消融
   可复跑（默认行为不变）。

## 四、待办（下轮, 按消融结论排的优先级）

### P0
1. **真 HyDE 进评测**: `_hyde_query_vector` 是查询扩展不是假设文档
   （半实现）; eval 用 llm=None 所以 HyDE 从未被测 — 先让评测带 HyDE
   路径, 再谈"HyDE 默认"。这是治"提问式 vs 陈述式"不对称的正解。
2. **goldset 文档级粒度**: 块级 top1 单文件判定过严（B 类至少 2 条是
   "相关但不同文件"）; 补"相关文档集"标注 + 文件级 top1 指标（CE pilot
   已有口径, 可直接复用）。

### P1
3. **CE 路线并集 + 段落级打分**: q033 None→1 证明判别式对词法命中进池
   有效; 全量负的根因是长块/多主题块判别不稳 — 候选文本切段落再打分
   （Beyond Top-K 结论）。
4. **嵌入窗口/模型**: 多窗口嵌入（标题 + 内容前/中/后）或检索专用微调
   （需数据与训练基建）。

### 已否决（不返工）
- BGE 指令前缀（M3 不依赖, probe 无改善）
- 简单路线独有保底 / 向量置信门控 / 全量 PRF（消融全负, 开关保留为
  钩子, 不做默认）

## 五、环境坑（续用）

- 8000 必须 .venv 起（anaconda torch 死锁）; 沙箱进程无出网
- PowerShell 管道 GBK 乱码 → 中文脚本写 UTF-8 文件执行
- 全量跑: `.venv\Scripts\python.exe -m pytest core/agent -q --tb=short
  -p no:cacheprovider`（~4:21, 默认排除 slow）
- CE 模型: `models/bge-reranker-v2-m3`（2.3GB, GPU, ~30ms/对）
- 缓存热后 eval_100 ~100s; 首次会触发全量 embedding（~13min 一次性）

## 六、关键文档

- docs/only/recall/RECALL_FUSION_ABLATION_20260816.md（消融全记录）
- docs/test/EVAL_100_20260816.md（修正后基线）
- scripts/_doc_miss_dump_20260816.md（29 条 miss 逐条 dump）
- scripts/_ce_wide_delta_20260816.md / _ce_union_delta_20260816.md
  （CE 两种候选口径逐条）
- 上轮: STATE_HANDOFF_V1_STABILIZE_20260816.md
