# Information-Theoretic Summary Compression — Temperature × Value Dual-Axis

> 2026-07-24 · 信息论 × NLP 交叉设计
>
> 核心洞见: 温度是时间轴(最近≠重要), 信息价值是稀缺轴(罕见≠无关)。
> 当前只有温度维 → 损失"罕见但冷"的高价值信息。
> 修正: 温度×价值 二维决策矩阵 → 每块独立决定保留粒度。

---

## 一、信息论基础映射

### 1.1 Shannon 自信息

```
I(x) = -log₂ P(x)

稀有事件 → P(x)≈0 → I(x)高 → 信息价值高, 应保留
日常事件 → P(x)≈1 → I(x)低 → 信息价值低, 可压缩

例:
  "又日常写代码了"      出现100次 → P≈1.0 → I≈0 → 压缩
  "服务器崩了找不到根因" 出现1次   → P≈0.01 → I≈6.6 → 保留
  "忘记查SQL执行计划"    出现2次   → P≈0.02 → I≈5.6 → 保留
```

### 1.2 与温度的正交性

```
温度(时间轴):  新发生=Hot, 很久前=Cold
价值(稀缺轴):  罕见=High, 常见=Low

              High价值              Low价值
  Hot         ⚡ FULL TEXT          📝 V2 ENTITY
              "刚崩溃"              "日常检查"
              
  Warm        📌 V3 MILESTONE       📋 V2 ENTITY
              "昨天那个bug"         "昨天写代码"
              
  Cold        📌 V3 MILESTONE       🗜️ V4 COMPRESS
              "上周罕见加密问题"    "上周例行部署"
              
  Frozen      (索引保留, 检索可用)   (索引仅保留)
```

### 1.3 关键文献

| 文献 | 核心 | 映射 |
|------|------|------|
| Shannon 1948 | 自信息 I = -log P | 信息价值计算 |
| Rate-Distortion Theory | 有损压缩中保留高信息量 | 摘要粒度决策 |
| TF-IDF (IDF部分) | 稀有词=高区分度 | 词级信息价值 |
| Focus (2024) | relevance + novelty + age | 三维评分参考 |
| BM25 IDF | log((N-df)/df) | 术语稀缺度 |
| Perplexity-based Novelty | 低概率token序列=新奇 | 块级新颖度 |

---

## 二、信息价值量化

### 2.1 块级信息价值

```
I(block) = w₁·entity_rarity + w₂·intent_novelty + w₃·action_deviation

entity_rarity:   该块实体在全部对话历史中的出现频率倒数
  rarity = 1 - (出现次数 / 总块数)
  高: "zebra_algorithm" 从未出现过 → rarity=1.0
  低: "延迟" 出现50次 → rarity=0.02

intent_novelty:   该块的意图类别与近期意图的差异
  novelty = 1 - max(cos_sim(intent_emb, recent_intents_avg))
  高: 突然从"编码"切换为"安全审计"
  低: 连续10轮都是"编码"

action_deviation: 该块的动作链与典型行为模式偏离
  deviation = abs(actual_action_count - expected_from_history)
  高: 平时5步操作这次1步 (可能漏了关键步骤)
  低: 操作模式与历史一致
```

### 2.2 全局归一化

```python
def information_value(block, history_stats):
    entity_rarity = mean([
        1 - (history_stats.entity_freq.get(e, 0) / max(1, history_stats.total_blocks))
        for e in block.entities
    ]) if block.entities else 0.3

    intent_novelty = 1.0 if block.intent not in history_stats.recent_intents[-5:] else 0.2

    action_deviation = abs(
        len(block.actions) - history_stats.avg_actions_per_block
    ) / max(1, history_stats.avg_actions_per_block)

    return clamp(0.3 * entity_rarity + 0.35 * intent_novelty + 0.35 * action_deviation, 0, 1)
```

---

## 三、二维决策矩阵

### 3.1 温度×价值 → 保留策略

```
                HIGH VALUE (>0.6)              LOW VALUE (≤0.6)
HOT(t=0)      FULL_TEXT (原文全量)            V2_ENTITY (实体摘要)
WARM(t=1)     V3_MILESTONE (里程碑)           V2_ENTITY (实体摘要)
COLD(t=2)     V3_MILESTONE (里程碑保留)       V4_LLM_COMPRESS (压缩)
FROZEN(t=3)   INDEX_ONLY (检索引擎)           INDEX_ONLY (检索引擎)
```

### 3.2 build_context 输出格式

```
[Hot·High] 服务器崩溃, 三个模块同时挂了, 日志显示OOM... (全文)
[Warm·High] 昨天发现AES密钥硬编码 → 紧急轮换 → 审计确认 (里程碑)
[Cold·Low]  部署v2.3 → 验证通过 → 回滚v2.2 (LLM压缩为一句)
[Frozen]    (不注入, 仅索引检索)
```

---

## 四、实现接口

### 4.1 SummaryEngine 升级

```python
class SummaryEngine:
    def __init__(self, llm=None):
        self.llm = llm
        self._entity_freq: Dict[str, int] = {}
        self._total_blocks: int = 0

    def information_value(self, block) -> float:
        """Compute block information value from entity rarity + intent novelty."""
        ...

    def build_context(self, blocks, max_tokens=2000) -> str:
        """2D decision: temperature × information_value → retention level."""
        for b in blocks:
            t = self._temperature(b)
            v = self.information_value(b)
            b._retention = self._decide_retention(t, v)
        return self._serialize(blocks, max_tokens)

    def _decide_retention(self, temperature: int, value: float) -> str:
        if temperature == 0 and value > 0.6: return "full"
        if temperature <= 1 and value > 0.6: return "milestone"
        if value <= 0.6 and temperature >= 2: return "llm_compress"
        return "entity_summary"
```

### 4.2 与现有统计复用

已有的 entity_freq 信息从哪里来:
- DiscourseBlockTreeManager 维护全局 entity_freq (在 feed 时更新)
- TopicQuickMatcher 的 BM25 IDF 作为词级信息价值的快速近似
- L2.5 BeliefAccumulator 的 belief_7d.novelty 作为意图新颖度

---

## 五、验证场景

```
场景1: 日常+N次 → 低价值, 高温度 → v2压缩 ✅
  "又写了一天Python" → entities:[Python], freq=50/100 → value≈0.1 → v2

场景2: 罕见故障 → 高价值, 任意温度 → 保留
  "数据库突然死锁需要重启" → entities:[死锁,重启], freq=1/100 → value≈0.9 → full

场景3: 行为异常 → 高价值但冷 → 里程碑保留
  平时5步操作, 这次1步"直接重启" → deviation=0.8 → value高 → milestone

场景4: 日常但冷 → 低价值+低温 → LLM压缩
  30轮前的例行部署 → value≈0.1, temp=cold → v4: "v2.3部署→回滚"
```
