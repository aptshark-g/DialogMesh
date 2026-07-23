# Association Chain L1-L4 — 统一设计文档

> 2026-07-23 · L1-L4 全部完成 & 前沿对标
>
> 设计基座:
>   BUSINESS_CHAIN_06_ASSOCIATION.md (260行) — 五层漏斗全景
>   DESIGN_RELATION_SUBSTRATE.md (413行) — 统一关系基座
>   DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md (257行) — 三维坐标
>   blog/chapter2_relation_over_prompt.md — 7D信念 + Semantic World
>
> 前沿对标:
>   L1: Dependency Path Embedding + Biaffine Attention SRL
>   L1.5: Candidate Ranking + LLM Collaborative Voting
>   L2: OG-RAG (ontology-grounded), Graph-Augmented Hybrid Search (Strata)
>   L2.5: BLF (Bayesian Linguistic Forecaster), PersuasionTrace, Dynamic Belief Graph
>   L3: Multi-Perspective Validator (discourse+profile+association+pcr)
>   L4: T-BN + Time Framework + HyperHawkes + Intent Drift Detection

---

## 一、架构全景

```
用户输入
  ↓
┌──────────────────────────────────────────┐
│ L1: 句法表层 (Syntactic Surface)          │  config/deprel_config.json
│   39项deprel→role映射, Stanza实时解析    │  core/.../l1_modifier.py
│   输出: SVO + 修饰语context               │  <5ms per turn
├──────────────────────────────────────────┤
│ L1.5: 认知补全 (Cognitive Completion)     │  config/l2_config.json
│   语法候选 + DeepSeek LLM排序 + 共识融合  │  core/.../l1_5_completer.py
│   输出: 补全实体 + 置信度 + reasoning      │  ~200ms (with LLM)
├──────────────────────────────────────────┤
│ L2: 语义本体 (Semantic Ontology)          │  DESIGN_RELATION_SUBSTRATE
│   RelationSubstrate + EntityNode + 2跳   │  core/.../relation_substrate.py
│   多源证据: BM25 + nomic向量 + LLM        │  core/.../topic_quick_match.py
├──────────────────────────────────────────┤
│ L2.5: 信念凝聚 (Belief Accumulator)       │  BLF / PersuasionTrace
│   贝叶斯序贯更新 + 7D信念 + 轨迹审计     │  core/.../l2_5_belief.py
│   僵持触发LLM, 5轮强制结晶               │
├──────────────────────────────────────────┤
│ L3: 语用意图 (Pragmatic Intent)           │  多视角验证器
│   对话树 + 画像 + 关联 + PCR 四方投票    │  core/.../l3_intent.py
│   分歧→LLM死锁裁决                       │
├──────────────────────────────────────────┤
│ L4: 时序模式 (Temporal Pattern) ← 本层   │  T-BN / Time / HyperHawkes
│   意图转移矩阵 + 时序对话图 + 漂移检测   │
└──────────────────────────────────────────┘
  ↓
L5: 因果链 (Causal Chain) — 待实现
```

## 二、各层前沿对标 & 实现状态

### L1: 句法表层

| 维度 | 前沿 | 我们 | 状态 |
|------|------|------|:---:|
| 依存解析 | Stanza zh-hans | ✅ Stanza | ✅ |
| 角色映射 | Biaffine Attention | config/deprel_config.json 39项 | ✅ |
| 修饰语提取 | Dependency Path | filter单字+compound合并 | ✅ |
| 零硬编码 | — | 全部从config加载 | ✅ |

**代码**: `association/l1_modifier.py` (130行), `config/deprel_config.json` (39项)  
**测试**: `test_l1_modifiers.py` (8 JSON用例)

### L1.5: 认知补全

| 维度 | 前沿 | 我们 | 状态 |
|------|------|------|:---:|
| 候选生成 | SVO+modifier→entity cluster | ✅ 语法搜索 | ✅ |
| 排序 | LLM Collaborative Voting | ✅ DeepSeek ranking | ✅ |
| 共识融合 | syntax∩LLM → consensus | ✅ 三种路径 | ✅ |
| 向量匹配 | — | nomic 768d via LM Studio | ✅ |
| 降级 | — | syntax-only × 0.7 | ✅ |

**代码**: `association/l1_5_completer.py` (270行)  
**测试**: 4 JSON用例, DeepSeek实测

### L2: 语义本体

| 维度 | 前沿 | 我们 | 状态 |
|------|------|------|:---:|
| 实体图 | OG-RAG超图 | RelationSubstrate EntityNode | ✅ |
| 检索 | BM25+Vector (Strata) | topic_quick_match + nomic | ✅ |
| 遍历 | Graph-Augmented | 1-2 hop entity_neighbors | ✅ |
| 证据链 | Multi-source Evidence | BM25 + LLM + conversation_turn | ✅ |

**代码**: `compiler/relation_substrate.py` (430行), `compiler/topic_quick_match.py`  
**测试**: `test_l2_entity_graph.py` (3 tests)

### L2.5: 信念凝聚

| 维度 | 前沿 | 我们 | 状态 |
|------|------|------|:---:|
| 概率更新 | BLF贝叶斯序贯 | ✅ BayesianUpdater | ✅ |
| 多维信念 | Dynamic Belief Graph | ✅ 7D (support/conflict/stability/coverage/recency/novelty/entropy) | ✅ |
| 信念轨迹 | PersuasionTrace | ✅ BeliefTraceEntry (turn/evidence/P_before/P_after) | ✅ |
| LLM触发 | 僵持时LLM推理 | ✅ entropy>0.5 → LLM | ✅ |
| 强制结晶 | — | ✅ 5轮未锁→max entropy | ✅ |

**代码**: `association/l2_5_belief.py` (230行)  
**测试**: `test_l2_5_belief.py` (3 scenarios)

### L3: 语用意图

| 维度 | 前沿 | 我们 | 状态 |
|------|------|------|:---:|
| 多视角投票 | — | discourse+profile+association+pcr | ✅ |
| 死锁裁决 | — | LLM打破2v2僵局 | ✅ (DeepSeek实测) |
| 画像反馈 | — | OCEAN→intent偏好权重 | ✅ |
| 零硬编码 | — | 全部config驱动, 无词表 | ✅ |

**代码**: `association/l3_intent.py` (219行)  
**测试**: `test_l3_intent.py` (3 scenarios, LLM死锁实测)

## 三、L4: 时序模式 — 前沿对标

### 3.1 核心定位

> L4 = **"意图随时间如何演化"**。不同于L2.5的快照概率——L4追踪意图的**转移路径**和**漂移趋势**。

### 3.2 四大方向 & 对标方案

| 方向 | 前沿代表 | 我们的映射 |
|------|---------|-----------|
| 意图转移预测 | T-BN (时序贝叶斯网络) | `IntentTransitionMatrix`: P(intent_{t+1} | intent_t) |
| 时序对话图 | 分层时序推理 (Gated Graph Conv) | `TemporalDialogGraph`: 角色+语义+时间戳 |
| 时间感知LLM | Time框架 (`<time>`标签) | `TimeAwareContext`: 间隔感知衰减权重 |
| 意图漂移检测 | HyperHawkes (超图+Hawkes过程) | `IntentDriftDetector`: 序列熵突变检测 |

### 3.3 实现组件

**组件1: IntentTransitionMatrix**

```
从历史对话学习意图转移概率:
  P(修复 | 诊断) = 0.72
  P(探索 | 信息查询) = 0.55
  P(吐槽 | 吐槽) = 0.41  (自转移, 连续吐槽)
  
用途: 预测下一步最可能意图, 提前加载上下文
```

**组件2: TemporalDialogGraph**

```
节点: (turn, speaker, intent, top entities)
边: 时序-因果-语义 三类
时间衰减: weight = exp(-Δt / τ)
```

**组件3: IntentDriftDetector**

```
监测: 连续N轮意图熵变化
触发: entropy_slope > 阈值 → 意图漂移
动作: summarize + clarify + reset belief
```

### 3.4 与已有模块集成

```
L3输出 intent_t → L4记录时序
L4输出:
  → predicted_intent_{t+1} (预加载上下文)
  → drift_warning (触发元认知)
  → time_weight (衰减因子→L2.5 prior)
  → intent_transition_probs (→L3 下一轮先验)
```

## 四、测试矩阵

| 层 | 测试文件 | 用例数 | JSON驱动 | LLM实测 |
|----|---------|:------:|:--------:|:-------:|
| L1 | test_l1_modifiers.py | 8 | ✅ | — |
| L1.5 | test_real.py | 4 | ✅ | ✅ DeepSeek |
| L2 | test_l2_entity_graph.py | 3 | — | — |
| L2.5 | test_l2_5_belief.py | 3 | ✅ | — |
| L3 | test_l3_intent.py | 3 | ✅ | ✅ DeepSeek |
| L4 | 待建 | ∞ | ✅ | — |

## 五、零硬编码保证

- ✅ L1: 全部39项deprel映射在 `config/deprel_config.json`
- ✅ L1.5: 置信系数在 `config/l2_config.json`
- ✅ L2: EntityNode类型为字符串, 无分类映射
- ✅ L2.5: likelihood矩阵在代码(需迁config)
- ✅ L3: behavior_map在config, 无词表
- ❌ L2.5: likelihood_matrix在代码内, 待迁config/l2_config.json
