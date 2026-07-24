# L5 长期记忆架构 — 压缩分治 + RAG定位 + 启发凝练

> 2026-07-24 · 信息论 × 图检索 × 启发式推理

---

## 一、核心哲思

```
记忆不是"存什么"，是"什么时候用什么方式取"。

三层分治:
  高频平庸 → 压缩成规则 (DerivationCompressor)
  低频高价值 → RAG原样保留 (密码/密钥/罕见bug)
  思考过程 → 启发凝练 (元认知专属持久化)

不是存得全 — 是取得准。
```

## 二、信息论分治

### 2.1 二维决策矩阵

```
               高频 (P>0.3)              低频 (P≤0.3)

高价值        压缩成规则 + 快速索引         RAG 原样保留
(I>0.6)       "诊断→修复 成功率0.85"        "root密码: ****"

低价值        强压缩/丢弃                   仅索引
(I≤0.6)       "第204次日常检查"             "1年前的问候"
```

### 2.2 与现有系统对应

```
信息价值计算 (已实现):
  ThreeParadigmContext._information_value()
  = 0.3 × entity_rarity + 0.35 × intent_novelty + 0.35 × action_deviation

存储决策:
  P(高) + I(高) → RAG (直接存, 不分词)
  P(高) + I(低) → DerivationCompressor.compress()
  P(低) + I(高) → RAG (这是关键: 密码/密钥类)
  P(低) + I(低) → indexed only, no content
```

### 2.3 文献支撑

| 文献 | 核心 | 映射 |
|------|------|------|
| Shannon 1948 | I = -log P | 信息价值计算 |
| MemGPT (2023) | 分层记忆 + LLM管理 | 压缩/保留决策 |
| GraphRAG (2024) | 图社区 + RAG | 锚点定位+图扩散 |
| HippoRAG (2024) | 海马体启发检索 | 新皮层/海马体双存储 |
| MemoRAG (2024) | 记忆引导生成 | 长记忆→生成增强 |
| Letta (2024) | 状态化Agent记忆 | working/archival双区 |
| AriGraph (2024) | 图记忆+实体关系 | 图检索+语义扩展 |

## 三、图+RAG 两层检索

### 3.1 锚点定位

```
用户: "上次那个AES密钥的问题怎么解决的"

Step 1: RAG 语义检索
  "AES密钥" → embedding → nearest neighbor in vector DB
  → 定位到 EntityNode("AES_KEY_ROTATION_v2")
  
Step 2: 图扩散 (water-wave)
  从锚点出发, 沿 RelationSubstrate 边扩散:
    EntityNode → [RELATES_TO] → EntityNode("密钥轮换脚本")
    EntityNode → [CAUSED_BY] → EntityNode("PCI合规要求")
    EntityNode → [RESOLVED_BY] → EntityNode("自动化部署v3")
  → 2跳范围内召回相关实体 + 边上的证据链 (evidence)
```

### 3.2 与纯 RAG 的差异

```
纯RAG:
  embedding → top-K doc → 拼接上下文
  问题: 高维空间相似 ≠ 因果相关

图+RAG:
  embedding → 锚点实体 → 图遍历 → 因果相关实体
  优势: 2跳内召回的是"实际发生过关系"的实体, 不是"语义近似"
        EntityNode 自带 evidence_chain → LLM可回溯来源
```

### 3.3 现有代码映射

```
RAG层 (已有):
  persistence/hnsw_index.py (397L) — 向量检索
  persistence/faiss_store.py (205L) — FAISS后端
  persistence/milvus_store.py (262L) — Milvus后端
  embedding/nomic → 768d 向量 (LM Studio)

图层 (已有):
  compiler/relation_substrate.py (454L) — EntityNode + 9种边
  compiler/subgraph_compiler.py (327L) — water-wave 图扩散
  persistence/graph_store.py (472L) — 图持久化

需要连接: RAG检索 → 定位EntityNode → 图扩散 → 组装上下文
```

## 四、规则验证闭环

### 4.1 多视角调整

```
聚类 → 归纳规则 → 逆推验证 → 失败 → 多视角调整

视角1 (结构): "规则覆盖了所有正例吗?"
视角2 (语义): "规则的解释合理吗?"  
视角3 (时序): "规则在时间序列上稳定吗?"
视角4 (反例): "规则排除了所有反例吗?"

→ 主LLM合成: "结构调整聚类边界 + 语义更新规则表述"

和 MultiPerspectiveAnalyzer 同构 — 直接复用
```

### 4.2 启发式凝练 (元认知专属持久化)

```
不是存"用户做了什么"
是存"系统怎么想的"

HeuristicChain (已有, DerivationCompressor):
  条件 + 反例 + 验证路径 + 置信度

示例:
  Chain#42:
    条件: "用户连续3次接受诊断→修复预测"
    反例: "用户在第4次自己选择探索"
    路径: 发散(尝试将修复+探索聚类) → 收敛(诊断→{修复,探索}概率分布)
    置信度: 0.72

这些 chains 是元认知的持久记忆 — 系统对自己思考的反思
```

## 五、存储架构

### 5.1 四区存储

```
┌─────────────────────────────────────────────────────┐
│  Hot Memory (active block, Python dict)             │
│  当前轮次 — 全文保留                                │
├─────────────────────────────────────────────────────┤
│  Working Memory (DiscourseBlockTree, SQLite)        │
│  最近话题 — 渐进摘要 v1→v4                          │
├─────────────────────────────────────────────────────┤
│  Archived Memory (RAG, VectorDB)                    │
│  低频高价值 — 原样保留, embedding检索                │
├─────────────────────────────────────────────────────┤
│  Compressed Memory (DerivationCompressor, JSON)     │
│  高频信息 → 规则 → 启发链                           │
├─────────────────────────────────────────────────────┤
│  Meta-Cognitive Memory (HeuristicChain pool, Rust)  │
│  思考过程 → 凝练的启发 — 系统如何思考              │
└─────────────────────────────────────────────────────┘
```

### 5.2 检索优先级

```
查询: "AES密钥问题"

1. Working Memory (DiscourseBlockTree) — 最近话题是否匹配?
   → 命中 → 直接返回全文/摘要

2. Archived Memory (RAG) — HNSW检索 EntityNode
   → 命中 → 图扩散2跳 → 组装上下文

3. Compressed Memory (HeuristicChain) — 规则库检索
   → 命中 → 规则+条件+验证路径

4. Meta-Cognitive Memory — 启发链检索
   → "上次类似查询的思考路径是..."
```

## 六、实现路径

```
Phase 1: RAG + 图 连接 (P0, ~200行)
  连接: hnsw_index → EntityNode定位 → 图扩散 → 上下文组装

Phase 2: 压缩分治 (P1, ~300行)
  连接: information_value计算 → 存储决策 → 分流RAG/Compressor

Phase 3: 规则验证闭环 (P2, ~400行)
  复用: MultiPerspectiveAnalyzer → 聚类调整 → 规则更新

Phase 4: 启发凝练 (P2, ~200行)
  HeuristicChain 持久化 → 元认知检索接口

Phase 5: Rust 迁移 (P3)
  压缩循环 + 图扩散 + 索引 → Rust实现
```
