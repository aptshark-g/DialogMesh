# V4/Cognitive Architecture Integration

> 2026-07-24 · v4认知层 ↔ 当前感知执行层 协同设计

---

## 一、金字塔架构

```
Layer 3: 元认知 (自省 + 回顾)
  v4/metacognition.py (328L)
  → MetacognitiveTrigger 事件驱动 → 元认知审查 → 修正信号

Layer 2: 认知融合 (多源信号 → LLM上下文)
  v4/fusion.py (105L)           Track A(动态) + Track B(先验)
  v4/belief_map.py (305L)       信念图 + 结构信号
  v4/mind/*.py (375L)           注意力/错误/关系

Layer 1: 认知画像 (用户理解)
  v4/ocean_profile.py (265L)    OCEAN人格
  v4/bfi_calibrator.py (201L)   BFI-10校准
  v4/behavior_discovery.py (242L) 行为模式发现
  v4/pattern_learner.py (183L)  模式学习器
  v4/correction_journal.py (156L) 用户修正日志
  v4/simulation_engine.py (238L) 行为仿真
  v4/memory_extractor.py (288L) 记忆提取
  v4/tag_layer.py (319L)        标签层

Layer 0: 感知+执行 (已完成)
  PCR → Intent → Discourse → L4 → Behavior → Planner
```

## 二、6 个桥接点

### Bridge 1: PCR → OceanProfile
```
PCR (x,y,z坐标 + zone) → ocean_profile 输入
  高x值(novel domain) → OCEAN Openness 权重上调
  低z值(mirror) → OCEAN Neuroticism 权重上调
  
ocean_profile 输出 → PCR Z轴调制
  C>0.7(高尽责) → shift toward PRECISION
  N>0.7(高神经质) → shift toward PSYCHE
```

### Bridge 2: Behavior Edges → Pattern Learner
```
BehaviorEdge[success_rate, correction_count] 
  → pattern_learner 输入
  → 发现: "诊断→修复→correction→诊断 循环"
  → 更新: ColdStart 种子 + Edge权重

pattern_learner 输出 → behavior_discovery
  → 新行为模式 → BehaviorEdge 创建
```

### Bridge 3: Discourse Blocks → Memory Extractor + Tag Layer
```
DiscourseBlock[v3_summary, entities, intent]
  → memory_extractor 提取关键记忆
  → tag_layer 生成标签: {domain, urgency, familiarity}
  → SubgraphCompiler 上下文物建
```

### Bridge 4: L4 Temporal → Belief Map
```
L4 转移矩阵 + 漂移检测 → belief_map 输入
  transition: "诊断→修复" P=0.8
  drift: JSD=0.45 → belief_map 标记为"不确定"
  
belief_map 输出 → L4 调参
  信念累积 > 0.85 → L4 transition 权重调整
```

### Bridge 5: PCR + Discourse + Behavior → Fusion
```
Track A (动态):
  PCR route (当前坐标)
  L4 prediction (下步预测)
  Discourse cohesion (话题连贯性)

Track B (先验):
  OceanProfile (长期人格)
  BehaviorEdge history (行为历史)
  BeliefMap (信念状态)

→ fusion 融合 → 结构化LLM上下文
```

### Bridge 6: MetacognitiveTrigger → Metacognition
```
MetacognitiveTriggerEngine 事件:
  belief_entropy_high → metacognition.review_queue
  intent_drift → metacognition.retrospection 
  correction_rate_high → metacognition.hint_review

metacognition 决策:
  auto (0.85+ confidence): 自动修正
  assisted (0.50-0.85): LLM审查
  manual (<0.50): 用户确认
```

## 三、实现优先级

```
P0 (已有基础设施): Bridge 1, 5, 6
  PCR/Ocean/Trigger 存在 → 直接接线

P1 (需适配): Bridge 2, 4  
  Behavior/L4 存在 → pattern_learner/belief_map 需适配数据格式

P2 (需激活): Bridge 3  
  Discourse 存在 → memory_extractor/tag_layer 需激活
```
