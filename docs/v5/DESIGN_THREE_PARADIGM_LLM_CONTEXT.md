# Three-Paradigm LLM Context Injection — 温度·距离·信息价值

> 2026-07-24 · 统一三个范式注入LLM提示词

---

## 一、三个范式的正交性

```
温度 (Temperature):    NOW ←→ PAST
  用户视角: 最近说的最重要
  系统信号: last_active_turn, access_count, recency decay

距离 (Distance):       FAMILIAR ←→ NOVEL
  系统视角: 系统独立发现的用户遗漏
  系统信号: topic_tree distance, entity overlap, domain shift

信息价值 (Info Value): COMMON ←→ RARE  
  统计视角: 低概率=高信息量
  系统信号: entity_rarity, intent_novelty, action_deviation
```

三者完全正交——同一块可以同时是: Hot·Near·Common (日常对话), Cold·Far·Rare (罕见但关键)。

## 二、三种注入模式

### 模式A: 结构化标签注入

```
每个块注入LLM时附带结构化标签:

[Block #3] temp:2(cold) dist:0.8(far) value:0.9(rare)
"上周AES密钥硬编码→紧急轮换→审计确认"

LLM自己决定: "虽然冷且远，但信息价值高，我应重视。"
```

### 模式B: 优先级排序注入

```
按综合优先级排序后注入:

P(block) = α·temperature + β·(1-distance) + γ·value

高P先注入 → LLM优先处理
低P后注入 → 可能被截断 (这才是正确的有损压缩)
```

### 模式C: 三元组自然语言注入 (推荐)

```
将三范式转化为自然语言元信息:

"以下是对话历史，按重要性排序。每个块标注了发生时间、领域相关性、信息价值。"

[★重要] 上周四: AES密钥硬编码被发现→紧急轮换→审计通过
  (3周前: 冷却中; 安全领域: 与当前话题远; 仅出现1次: 高信息量)

[一般] 昨天: Python函数重构完成
  (1天前: 温热; 编码领域: 相关; 出现多次: 低信息量)

[低] 上月: 日常数据库备份完成
  (30天前: 冻结; 运维领域: 不相关; 出现50次: 极低信息量)
```

**LLM自己决定关注哪些**——不是算法替LLM决定，是算法给LLM提供结构化的注意引导。

## 三、与现有系统集成

```
现有:
  SummaryEngine.build_context() → 按温度分组 → 截断

改为:
  SummaryEngine.build_context() → 计算三范式 → 排序 → LLM提示注入

具体:
  1. _temperature(block) → status映射
  2. information_value(block) → entity_rarity + intent_novelty + action_deviation
  3. distance(block) → TopicTree距离 + DiscourseBlockTree cohesion边界
  4. priority = 排序 → 按重要性注入 (最重要的最先, 最不重要的最后被截断)
```

## 四、LLM提示模板

```
System: 你是一个智能对话助手。以下是相关上下文，按重要性排序。
每个上下文标注了时间、领域相关性、信息稀缺度。请据此调整你的关注度。

Context blocks:
[Hot·Near·High] 服务器刚才崩溃了，日志显示OOM...
[Warm·Mid·High] 昨天发现AES密钥问题，已经修复...
[Cold·Far·Low]  30天前部署了v2.3版本...

User: 帮我排查为什么服务器崩溃
```

**价值**：LLM能区分"刚刚发生的日常日志检查"和"3天前的罕见安全事件"，前者可能被后者覆盖——不是因为算法决定了，而是因为LLM看到了标签，自己推理。

## 五、实现接口

```python
class ThreeParadigmContext:
    """统一三范式上下文构建器"""

    def __init__(self, summary_engine, topic_tree=None):
        self.engine = summary_engine
        self.topic_tree = topic_tree

    def build_prompt(self, blocks, current_text: str, max_tokens=3000) -> str:
        """构建带三范式标签的LLM提示上下文"""
        scored = []
        for b in blocks:
            temp = self.engine._temperature(b)           # 0-3
            value = self.engine.information_value(b)     # 0-1
            dist = self._estimate_distance(b)            # 0-1
            priority = 0.3 * (3-temp)/3 + 0.3 * value + 0.4 * (1-dist)
            scored.append((priority, b))
        
        scored.sort(key=lambda x: -x[0])  # highest priority first
        
        parts = []
        for pri, b in scored:
            tag = self._format_tag(b)
            text = self._get_block_text(b)
            parts.append(f"{tag} {text[:200]}")
        
        return "\n".join(parts)[:max_tokens]

    def _format_tag(self, block) -> str:
        t = {0: "Hot", 1: "Warm", 2: "Cold", 3: "Frozen"}[self.engine._temperature(block)]
        v = self.engine.information_value(block)
        v_star = "★" if v > 0.7 else ("●" if v > 0.4 else "○")
        return f"[{t}·{v_star}]"

    def _estimate_distance(self, block) -> float:
        """Estimate cognitive distance from current context."""
        # TODO: use TopicTree distance or entity overlap
        return 0.5  # neutral default
```
