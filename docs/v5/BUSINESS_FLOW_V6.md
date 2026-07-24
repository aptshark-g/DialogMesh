# DialogMesh v6 — 网状业务流 (Event-Driven Mesh)

> 2026-07-24 · 当前实现 · 事件驱动微服务

---

## 核心拓扑

```
不是: Layer 1 → Layer 2 → Layer 3 → ...
而是: EventBus ← 多链并行消费 ← 每个链是独立微服务

                        ┌──────────────────────┐
                        │     EventBus          │
                        │  环形缓冲 pub/sub     │
                        └──────┬───────────────┘
                               │
        ┌──────────┬───────────┼───────────┬──────────┬──────────┐
        ▼          ▼           ▼           ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Chain01 │ │ Chain02 │ │ Chain05 │ │ Chain06 │ │ Chain08 │ │ Chain09 │
   │对话树   │ │上下文   │ │行为链   │ │关联链   │ │认知画像 │ │元认知   │
   │Hot Path │ │Hot Path │ │Async    │ │Fast+Async│ │Slow    │ │Tick延迟 │
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │          │           │           │           │          │
        │  发布新Event          │           │           │          │
        └──────────────────────┴───────────┴───────────┴──────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │  StateGraph │
                        │ 对话树+关联链│
                        │   网状结构   │
                        └─────────────┘
```

## 事件类型与消费关系

```
MessageReceived
  → Chain01(对话树): feed block, update cohesion
  → Chain06(关联链): L1 modifier → L1.5 completer → L2 substrate → L2.5 belief
  → Chain04(PCR V2): coordinate routing → zone decision
  → Chain03(MultiIntent): split → segments

IntentLocked (L3 置信度 ≥ 0.85 或 死锁→L2.5累积→锁定)
  → Chain01: update DiscourseBlock.intent
  → Chain06: L3 locked → L4 temporal update
  → Chain08(认知画像): ocean_profile update
  → Chain07(工程链): constraint check

PatternDiscovered (BehaviorEdge 稳定模式 或 LLM发现)
  → Chain06: L4 A↔B edge weight update
  → Chain05: cold_start seed update
  → Chain08: pattern→profile modulation

MetaVerified (元认知审查通过)
  → Chain06: L5 伪因果→实因果 晋升
  → Chain05: edge.is_stable = True
  → Chain09: review_queue.pop
```

## 10条链当前实现状态

```
链01 对话树主线 🟢 完成
  消费: MessageReceived
  实现: DiscourseBlockTree (917L)
        HeaderInjector → SyntacticDecomposer → MacroMicroQuantizer
        BM25+jieba → LLM双轨 → PosteriorCorrector
        SummaryEngine v1→v4 → ThreeParadigmContext
  路径: Hot (<10ms) / Warm (entity摘要) / Cold (llm压缩)

链02 上下文编译 🟢 完成
  消费: DiscourseBlock变化
  实现: ContextManager + temperature_patch + ThreeParadigmContext
  输出: 结构化LLM上下文 [Hot·★★★·Near] 标签

链03 意图解析 🟢 完成
  消费: MessageReceived + PCR route
  实现: MultiIntentSplitter (热<1s) + MultiPerspective (冷后台)
        AmbiguityBridge → L2.5 (死锁→贝叶斯)
  输出: IntentLocked Event

链04 PCR认知路由 🟢 完成
  消费: MessageReceived
  实现: PCR V2 (600L) — nomic X轴 + STC Y轴 + nomic Z轴
        LLMReview + LLMEntity补全 + ModelSize检测
  输出: Zone路由 + ExecutionMode

链05 行为链 🟢 完成
  消费: MessageReceived 后行为记录
  实现: BehaviorEdge→自适应学习
        LLMCollaborator→解释+发现+调参
        ColdStart种子
  路径: Async Path (后台)

链06 关联链 (微服务) 🟢 完成
  消费: MessageReceived → IntentLocked → PatternDiscovered
  实现: L1 modifier → L1.5 completer → L2 substrate → 
        L2.5 BeliefAccumulator → L3 validator → L4 temporal
  路径: Fast Path (L1-L2 <5ms) / Async Path (L1.5 LLM)
        Slow Path (L5因果晋升, 事件驱动)

链07 工程链 🟡 部分完成
  消费: IntentLocked → PatternDiscovered
  实现: EngineeringChain (136L) — MCP桥接 + 工具可行性
  缺失: ConstraintViolated → 元认知推送
  路径: Hot Path (查询) / Async Path (约束推理)

链08 认知画像 🔗 桥接就绪
  消费: IntentLocked → PatternDiscovered → MetaVerified
  实现: v4/cognitive/* (ocean_profile, bfi_calibrator, behavior_discovery)
        V4CognitiveBridge (6桥接)
  路径: Slow Path (多轮累积后更新)

链09 元认知 (微服务) 🔗 部分桥接
  消费: PatternDiscovered → MetaVerified (每Tick, 延迟消费)
  实现: MetacognitiveTriggerEngine (7规则)
        v4/metacognition.py (328L, review queue / retrospection)
  路径: Tick延迟 (积累多个事件后批量处理)

链10 执行编排 🟢 完成
  消费: 所有链事件 → 综合上下文
  实现: AgentOrchestrator + LLMPlanner + BlueprintExecutor
  输出: 分步执行计划 + LLM回答
```

## StateGraph：网状核心

```
对话树 (Chain01)                  关联链 (Chain06)
    │                                  │
    │  DiscourseBlock                  │  EntityNode
    │  cohesion edges                  │  Relation edges (9种)
    │  summary v1-v4                   │  belief_pool (7D)
    │                                  │
    └──────────┬───────────────────────┘
               │
    ┌──────────▼─────────────────────────┐
    │         StateGraph                 │
    │  对话树 + 关联链 = 统一网状结构      │
    │                                     │
    │  block.entities → substrate.nodes   │
    │  block.intent → belief_pool.posterior│
    │  block.cohesion → transition.weight │
    └─────────────────────────────────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
 Chain08   Chain09     Chain10
 认知画像   元认知      执行
```

## 路径分类

```
Hot Path (<50ms, 同步):
  PCR V2 route | Discourse feed | BM25 match | L1 modifier
  → 用户即时响应需要这些

Fast Path (<5ms, 同步):
  L2 substrate | Context build | Tool feasibility
  → 不阻塞, 在Hot之后立即完成

Async Path (~500ms, 异步):
  L1.5 completer (LLM) | BM25→LLM verify | Behavior update
  → 后台并行, 不阻塞响应

Slow Path (>1s, Tick延迟):
  OceanProfile update | Pattern learning | Simulation
  → 积累多轮后批量处理

Tick Path (每Tick, 事件驱动):
  MetacognitiveTrigger.check → MetaVerified
  L5 causal promotion → PatternDiscovered
  → 状态机: Command → Decider → Event → evolve → next Tick
```
