# Constraint-Driven Derivation Compression — 元认知压缩内核

> 2026-07-23 · 哲学基座 + 算法框架
>
> 前置:
>   v4 哲学: "任何东西之间都存在状态转化，区别是约束和转化"
>   topic_quick_match.py: BM25+kurtosis 递归收敛
>   discourse_block_tree.py: 3-stage compiler pipeline

---

## 一、哲学内核: 同一信号, 不同约束 → 相反结论

```
同一事实: 低概率信息

卡尔曼滤波:     低概率 = 低权重 (丢弃)
  约束: 正态分布, 追求准确性(accuracy)
  哲学: 自动化控制——误差最小化

信息论:          低概率 = 高价值 (放大)  
  约束: log分布, 追求信息价值(information value)
  哲学: 通信/密码学——意外性最大化

结论: 不是"低概率"本身, 是"约束框架"决定了它的意义。
      约束内 → 互化 (同一框架下可互相转换)
      约束间 → 不可直接比较, 需通过转换层
```

**启示**: 压缩不是"内容达到阈值就压"——是**在正确的约束框架下做推导归纳**。

---

## 二、压缩 ≠ 聚类: 推导链 vs 主题群

```
错误方案: 聚类压缩
  对话内容 → BGE聚类 → 主题群 → 每个群摘要
  问题: "延迟飙升" + "监控缺失" → 主题="系统问题"
        丢失了【监控缺失导致延迟难定位】的因果推导链
        摘要变成了主题词袋, 不是可逆推的规则

正确方案: 推导链压缩
  对话内容 → 提取状态转移 (a→b→c) → 归纳推导规则 → 压缩为规则集
  规则: {if entity_relations contain "causes" chain → intent=诊断}
  逆推: 打开规则 → "监控缺失 → 延迟飙升" → 符合原始对话 ✓
```

---

## 三、四步压缩算法

### Step 1: 提取状态转移 (Extract)

```
从L2实体图 + L2.5信念轨迹中提取:
  state_t → state_{t+1} 转移对

示例:
  (延迟, 未知) → (延迟, 诊断)   [evidence: "监控缺失"]
  (监控, 缺失) → (延迟, 飙升)   [relation: causes]
```

### Step 2: 归纳推导规则 (Induce)

```
从N个转移对中归纳规则:

模式A: entity_pair + relation_type → intent_shift
  例: (X, missing) + causes → intent → 诊断

模式B: belief_7d.stability drop → intent_drift
  例: stability < 0.4 for 2 turns → drift_warning

模式C: entity_cluster_size > 3 + recency < 5 → topic_lock
  例: 短期大量同簇实体 → 用户沉浸此话题
```

### Step 3: 压缩为规则集 (Compress)

```
不是存摘要文本, 是存推导规则:

rules = [
  {pattern: {entity_relation: "causes", confidence: >0.7},
   predict: {intent_next: "诊断", confidence: 0.82},
   evidence_count: 12,
   last_fired: turn_47},
  ...
]

每条规则 < 200 tokens, 可覆盖数百轮对话
```

### Step 4: 逆推验证 (Verify)

```
新对话 → 规则集预测 intent → 实际 intent
  匹配: 规则置信 +0.01
  不匹配: 规则置信 -0.05, 记录反例
  置信 < 0.3 → 规则失效, 从规则集中移除, 等待新归纳
```

---

## 四、子图↔LLM 混合格式上下文

子图到 LLM 之间不应用单一格式——不同语义密度用不同表示：

```
高结构/确定性 → XML:
  <entity id="e1" type="现象" cluster="latency">
    <modifier role="determiner">这</modifier>
    <modifier role="nominal_modifier">模块</modifier>
    <relation target="e2" type="causes" confidence="0.85"/>
  </entity>

中结构/量化 → JSON:
  {"belief": {"诊断": 0.82, "修复": 0.15},
   "transition": {"from": "探索", "to": "诊断", "confidence": 0.78}}

低结构/模糊 → Natural Language:
  "用户似乎从探索性的问题转向了诊断性的问题，
   可能是'延迟飙升'这个实体触发了意图转变。
   但'监控'相关证据较少，建议确认。"

混合注入 LLM prompt:
  [XML section]   ← 确定性实体关系
  [JSON section]  ← 量化信念/转移概率
  [NL section]    ← 模糊推理/元认知建议
```

**格式选择规则** (非硬编码——从子图语义密度自动判定):

```
entity_count > 5 + relation_confidence > 0.8  → XML
quantitative_distribution_present              → JSON  
ambiguous_or_low_confidence                    → Natural Language
```

---

## 五、与现有模块集成

```
L2 RelationSubstrate  → 实体状态转移对
L2.5 BeliefAccumulator → 信念轨迹
    ↓
DerivationCompressor:
  extract: L2 edge history + L2.5 trace
  induce: pattern matching on transitions
  compress: ruleset
  verify: inverse check against new turns
    ↓
输出:
  → ruleset (替代原始摘要, 用于上下文注入)
  → drift_warning (触发元认知)
  → format_recommendation (XML/JSON/NL)
```

---

## 六、核心公式

```
压缩率 = |ruleset| / |原始对话 tokens|
目标: 压缩率 < 5% (20轮对话 → 1个规则)

规则质量 = 逆推覆盖率
  coverage = |可逆推的转移对| / |总转移对|
目标: coverage > 80%

规则新鲜度 = 1 - (last_fired / current_turn)
  高新鲜度 → 规则活跃, 维持
  低新鲜度 → 规则休眠, 降低权重
```

---

## 七、总结

| 维度 | 错误方案 | 正确方案 |
|------|---------|---------|
| 触发 | 内容超阈值→压 | 推导链出现→归纳 |
| 方法 | 聚类→主题摘要 | 提取状态转移→规则归纳→逆推验证 |
| 存储 | 摘要文本 | 推导规则 + 证据计数 |
| 质量 | 自动评估 | 逆推覆盖率 |
| 失败 | 信息丢失 | 规则置信衰减→重新归纳 |

**核心哲学**: 
  "压缩不是让信息变小——是让信息的**约束结构**显式化。
   聚类压缩的是内容, 丢失了推导。
   推导压缩的是规则, 保留了因果。
   逆推验证: 如果打开规则不能还原原始推导链, 这个压缩是失败的。"
