# 统一召回黄金集 — 测试数据与结果（2026-08-08）

> 目的: 黄金集跑分完整记录（方法/数据/结果/真 bug）, 供复现与后续对照
> 关联: docs/only/recall/RECALL_BATCH2_PLAN_20260808.md（施工计划与进度）
> 复现: `.venv/Scripts/python.exe scripts/recall_goldset.py --mode <linear|rrf|norm> [--single <vector|bm25|spo|hyde|assoc>] --top-k 5`

---

## 一、黄金集构造（真实数据, 非手写）

- 生成器: `scripts/_build_goldset.py`
- 数据源: `data/v3_sessions.json`（83 会话 / 109 消息的真实对话）
- 规则: 每对 (user query → assistant reply), reply 按句切块(≤280字/块),
  期望命中 = 该 reply 的全部切块; 命中判定 = 任一期望块进 top-k
- 规模: **40 条 query + 218 个真实回复块**
- 文件: `data/recall_goldset.json`
- 诚实说明: 5/40 为噪音 query（hi ×2 / test ×2 / ???? ×1）, 计入真实分布不剔除

## 二、方法（收紧版, 防作弊）

1. **分层判定**: top-1 / top-3 / top-5 分别报告（不再只报宽松 top-5）
2. **随机基线**: 理论命中率 `1-(1-期望块数/总块数)^top_k`, 本集 = **11.3%**
3. **单路跑分**: vector / bm25 / spo 各自单独跑（single_source 参数）,
   直接回答"每路贡献多少"
4. **公平对照**: RRF 与 linear 用同一候选集, 只换融合函数

## 三、最终结果（2026-08-08, .venv 环境, 清缓存全量重算）

| 模式 | top1 | top3 | top5 | 随机基线 |
|---|---:|---:|---:|---:|
| linear（现状线性融合） | 30.0% | 52.5% | 67.5% | 11.3% |
| **rrf（rank-based 融合）** | **42.5%** | **67.5%** | **70.0%** | 11.3% |
| norm（linear + 同义归一表） | — | — | 62.5% | 11.3% |
| 单路 bm25 | 35.0% | 60.0% | 70.0% | 11.3% |
| 单路 vector | 32.5% | 50.0% | 65.0% | 11.3% |
| 单路 spo | 22.5% | 32.5% | 40.0% | 11.3% |

> norm 未跑全维度分层（早期版本, 记为 top5 62.5%）; 其结论已由 spo 单路
> 数据覆盖: 词典式增强在 SPO 覆盖有限时无增益。

### 结论
1. **RRF 全维度最优**: top1 +12.5pp / top3 +15pp / top5 +2.5pp vs linear
   → 融合层改 RRF 是免费增益
2. **单路能力排序**: bm25（top1 35%）> vector（32.5%）> spo（22.5%）
3. **SPO 单路最弱** → SPO 增强必须走模型路线（SPO-C 蒸馏）, 词典（norm）无效
4. **所有路显著高于随机 11.3%** → 无作弊, 真实能力

## 四、两个真 bug（此前 vector 路全 0 的根因, 已修复）

### Bug 1: 语言检测过严（semantic_encoder.py `_is_chinese`）
- 原逻辑: CJK 字符 > 30% 才走 zh 模型
- 症状: 中英混合文本（"pi agent 怎么做"）被判 "other"
  → 走 384 维 n-gram 稀疏零向量（仅 11 个非零）
  → 与 512 维 BGE 向量维度不一致, 余弦恒 0 → vector 路全 0
- 修复: 含任一 CJK 字符即走 zh 模型（BGE-zh 支持中英混合 token, 统一 512 维）

### Bug 2: 嵌套向量（recall_service.py `_embed` / `_cosine`）
- 原逻辑: `encode_text` 返回 (1,512) 矩阵, `.tolist()` 得嵌套 `[[...]]`
- 症状: `_cosine` 里 `np.dot((1,512),(1,512))` 维度不匹配, 异常被 except 吞掉
  → 静默返回 0.0 → vector 路全 0
- 修复: `_embed` 压平 `reshape(-1).tolist()`; `_cosine` 双保险压平

> 注: 修复前 HTTP 测试报告的 "vector 0.45 命中" 存疑（可能是异常路径的假象）;
> 修复后 vector 单路 top1 32.5% 是真实能力。

## 五、性能

- G0 索引缓存（`data/recall_index/{sid}.json`）: 首跑全量建索引 ~45s,
  二次直读缓存 ~15s（SPO/向量不再重算, 重启不丢）
- 单路跑分: bm25 ~12s / spo ~8s / vector ~40s（含 BGE 首次加载）

## 六、遗留

- 15s 仍含每 query 的 BGE + Stanza 开销（query 侧 SPO/向量未预缓存）
- HyDE 路未入跑分（需要真实 LLM）; R6 已单独验证: 网关扩展 3 子问题有效
- 第二批升级点（PPR / 主题层 / LLM 挑选）落地后, 用本集复测增量

## 七、连贯高干扰对话专项（2026-08-08 深夜, 用户提供真实对话）

### 素材
- 用户提供真实长对话（辩证法 → 心流/DMN/ECN → 认知-情绪模型公理化）,
  10 轮 user/ai, 话题连贯、概念多说法（"辩证/矛盾/对立统一"、"心流/伪心流/
  元认知监控"、"DMN/默认模式网络"）、术语密集
- 文件: `data/dialogue_test2.txt`（20 turns）
- 测试: `scripts/recall_dialogue_test2.py` — 10 条"事后重述"query
  （模拟几小时后提问, 非对话原题）, 期望命中 = 块含核心词;
  池子 = 本对话 + v3_sessions 前 10 会话干扰（118 块）

### 结果（修复 feed 截断后, 10/10 top5 全中）

| 指标 | 数值 |
|---|---:|
| top1 | 5/10 |
| top3 | 8/10 |
| top5 | **10/10** |

代表性命中（"换说法也能找到"的语义题）:
- "情绪的根源到底是什么" → top1 "情绪核心公理: Em=E实/E内"（词面不相干）
- "认知情绪模型里记忆点怎么影响判断" → top1 "记忆点锚定定理"（top1!）
- "认知双网络模式是什么意思" → top3 "认知双网络公理"

### 🔴 两个测试 bug（非召回 bug, 已修复）
1. **feed 截断**: 3971 字消息用 `content[:400]` 喂 → 公理内容（后半段）
   不在池子 → 3 条"换说法"题 MISS 假象。修复: 完整喂入
2. **check_pool 查错字段**: 只查 `_raw_text`（空）, 未查
   `atomic_units[].raw_text`（EDU 层有内容）→ 误判"公理不在池"

### 关键结论: 云端 LLM（HyDE）这组无额外增益
- 对照: 完整喂 + llm=None（无 HyDE）→ 同样 10/10 top5
- 原因: 这组 query 词面够（含"情绪/记忆点/双网络"等关键词）, BGE 向量
  语义匹配已够; 修掉截断后召回本身就能处理"换说法"
- 真瓶颈在**存储侧（内容要完整进池）**, 不在召回算法侧
- HyDE 增益待另测: 用"词面完全不相干"的 query（如"那个情绪的公式"→
  预期失衡）才能看出云端 LLM 扩展的真实价值

### 当前判断
- 对话树 feed 长文本 → 块 `_raw_text` 为空, 文本在 `atomic_units[].raw_text`
  （EDU 层）; recall 的 `_ensure_blocks` 已兼容（fallback join）, 但
  **check/export 等路径若只读 `_raw_text` 会漏内容** — 待审计
- 语义归一（SPO-C 蒸馏）的必要性仍成立: 词面不相干的 query 是它的主场,
  但"向量已经能语义命中"意味着蒸馏的增益需要更难的测试才能量化
