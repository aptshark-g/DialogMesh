# DialogMesh v6 — 系统设计 (System Design)

> 2026-07-24 · 从 230 篇设计中凝练的一张完整系统蓝图
> 默认策略: 混合模式 (Hybrid), 模块懒加载, 冷路径异步

---

## 一、启动序列

### 1.1 bootstrap() 执行流程

```
bootstrap()
  │
  ├─ 1. LLM 自动检测
  │     DEEPSEEK_API_KEY 环境变量
  │     → 有: DeepSeekProvider, 6 LLM 实例就绪 (MultiLayerLLMEngine)
  │     → 无: 结构模式运行 (PCR+Intent 用算法, LLM 合成跳过)
  │
  ├─ 2. EventLog 初始化  (SQLite, append-only, SHA256 链)
  │     data/event_log.db → 冷路径写入就绪
  │
  ├─ 3. UnifiedContext 懒加载
  │     context/ pipeline (Assembler + Budget + Prune)  ← 默认启用
  │     SubgraphCompiler (v4/cognitive, 双视角编译)     ← 默认启用
  │     DiscourseManager (v3 遗留)                      ← 跳过
  │
  ├─ 4. CognitionHub 懒加载
  │     HypothesisEngine (Match→Vote→Decay→Resolve)
  │     BeliefAccumulator (7维Belief, 投票锁定)
  │     RelationClusterer (LLM-native 谓词聚类)
  │
  ├─ 5. FeedbackBridge 初始化  (环形缓冲, 64 slots)
  │     Layer 1: urgent_correction
  │     Layer 2: belief_update
  │     Layer 3: parameter_shift
  │
  ├─ 6. Compass 初始化  (默认 2 lens)
  │     NoiseSpanLens → 7 种噪声检测
  │     Coordinate3DLens → 3D 认知坐标
  │     + LLM 可自选切换 lens
  │
  └─ 7. V4 Cognitive Bridge 懒加载  (13/13 模块, bridge wired)

总耗时: ~200ms (无 LLM) / ~500ms (含 LLM 探测)
```

### 1.2 模块依赖图

```
EventLog ────────────────────────────────────────────┐
                                                     │
UnifiedContext ──────────────────┐                   │
                                 │                   │
CognitionHub ────────────────┐   │   FeedbackBridge  │
                             │   │   │               │
Compass ────────────────┐    │   │   │   V4 Bridge   │
                        │    │   │   │   │           │
                        ▼    ▼   ▼   ▼   ▼           ▼
               AgentOrchestrator.process()  ←  ←  ←  ← EventLog.append()
                        │
                        ▼
                    用户响应
```

---

## 二、请求生命周期 (一次 process() 调用)

### 2.1 同步热路径 (全部在一个函数内完成)

```
用户文本 → process(text, session_id)

阶段  模块              耗时      产出                    冷路径事件
─────────────────────────────────────────────────────────────────────
 0    Comapss            <1ms     {noise_span, coordinate_3d}       —
 0.5  Cold→Hot Layer1    <1ms     消费上次 Meta 紧急修正           —
 1    PCR V2             <5ms     {zone, x, y, z}                 PCR_COMPUTED
 2    DualTrack Intent   <800ms   {multi, segments, confidence}    INTENT_PARSED
       热路径: 单 LLM split                                     (cold_enqueued
       冷路径: conf<0.7 → 每3次触发 MultiPerspective)            → 异步)
 3    L4 Temporal        <2ms     {predictions, drift}            L4_PREDICTED
 4    Behavior           <1ms     {available}                     BEHAVIOR_RECORDED
 5    UnifiedContext     <10ms    {dialogue_context, meta_context} CONTEXT_COMPILED
       Assembler → Budget → SubgraphCompiler → Prune
 6    Engineering        <5ms     {total, matching, feasible}     TOOLS_CHECKED
 7    LLM Synthesis      <1500ms  {steps, self_check}             PLAN_GENERATED
       (仅当 LLM 可用, 否则跳过)
 8    Cognition Converge <5ms     {active_beliefs, resolved}      —
 9    Cold→Hot 消费      <1ms     Layer2 belief + Layer3 drift    —
 10   record_turn        <1ms     → UnifiedContext (Discourse 历史)

总耗时: ~150ms (无 LLM) / ~2,500ms (含 LLM)
```

### 2.2 异步冷路径 (后台运行, 不阻塞 process())

```
热路径 process() 返回 → 用户得到回答
                         │
冷路径 (异步, 独立生命周期):
  EventLog.append() 事件 → EventBus 环形缓冲
    │
    ├─ Meta Subscriber (每 5 tick)
    │     订阅: PCR_COMPUTED, ROUTE_GENERATED, INTENT_PARSED,
    │           REPLY_GENERATED, PROFILE_UPDATED, BEHAVIOR_RECORDED,
    │           ABC_EVALUATED, MIND_LEARNED
    │     → MetaDecision {urgent_correction, parameter_shift}
    │     → FeedbackBridge.post_decision()
    │
    ├─ Association Subscriber (每 3 tick)
    │     订阅: PCR_COMPUTED, ROUTE_GENERATED, INTENT_PARSED,
    │           REPLY_GENERATED, BEHAVIOR_RECORDED, MIND_LEARNED
    │     → hidden_relation, causal_chain, temporal_pattern
    │     → FeedbackBridge (belief_update)
    │
    └─ DualTrack 冷路径 (conf <0.7 时, 每 3 次触发)
         MultiPerspectiveAnalyzer → 4 视角 DeepSeek 并发
         → DerivationCompressor → HeuristicChain 学习
         → 优化下次热路径的 split 精度
```

### 2.3 冷→热 回写时序

```
Tick N:
  process() → MetaSubscriber 收到事件 → 开始审核
  
Tick N+1 ~ N+4:
  MetaSubscriber 积累证据, 不产出
  
Tick N+5:
  MetaSubscriber → MetaDecision → FeedbackBridge
  process() 开始时 → consume() → PCR override
  → 热路径感知修正

总延迟: 最大 5 ticks, 不阻塞任何一次用户的即时回答
```

---

## 三、默认蓝图: Hybrid (混合模式)

### 3.1 策略: 复杂感知 → 策略选择 → 全链路

```
复杂度评估 (PCR + Comapss):
  complexity < 0.3  → RULE_BASED     (算法直出, 0 次 LLM)
  complexity < 0.6  → TEMPLATE       (模板匹配, 1 次 LLM 可选)
  complexity < 0.8  → HYBRID         (算法+LLM 协同, 2-5 次 LLM)
  complexity >= 0.8 → LLM_DRIVEN     (LLM 主导, 6 次 LLM)

默认: HYBRID = 算法做所有结构检测, LLM 只在 conf<0.7 时介入
      规则→嵌入→LLM 三级递进, 每级不足时才升级
```

### 3.2 LLM 调用次数 (默认 Hybrid)

```
算法处理结构特征, LLM 处理语义推理。两者互补, 不是替代。

场景                  LLM 调用                 说明
────────────────────────────────────────────────────────────
简单确定性            1-2 (Answer, 可选 PCR)    "今天天气怎么样"
中等任务              2-3 (PCR+Intent+Answer)   "帮我写一个 Python 函数"
复杂多步              4-5 (+Planning+Meta)      "先定位延迟, 再修复它"
高度开放              6 (全部 6 实例)            "设计一个新功能的架构"
用户歧义              1 (Answer: 反问澄清)       "那个...你知道的"

最小 LLM 调用 = 1 (Answer LLM 不可省略)
算法覆盖: 结构特征/噪声检测/句法分解/SVO抽取/嵌入检索
LLM 覆盖: 意图理解/规划生成/元认知审核/最终回答/反思学习
```

---

## 四、优雅降级

### 4.1 降级路径

```
LLM 不可用:
  PCR → 结构特征 (无 LLM 审查)
  Intent → MultiIntentSplitter (算法分句, 无 LLM)
  Planning → PlanningBridge (策略选择, 无 LLM 生成)
  Synthesis → 跳过 (result["plan"] = {})
  → 管线仍然运行, 产出结构性上下文

DeepSeek 超时:
  → LM Studio local fallback (nemotron 3B)
  → 仍不可用 → 结构模式

EventLog 写入失败:
  → 丢弃 + 计数, 不影响热路径

Context 装配失败:
  → fallback_assemble (线性拼接), 无预算无裁剪

Cognition 收敛失败:
  → 跳过本轮, 下轮继续
```

### 4.2 无 LLM 时管线的产出

```
无 LLM 时, process() 仍然产出:
  compass:    {lenses, signal}                       ← 罗盘信号
  route:      {zone, x, y, z}                        ← PCR 路由
  intents:    {multi, segments[texts], confidence}   ← 算法分句
  temporal:   {predictions, drift}                   ← L4 预测
  behavior:   {available}                            ← 行为标志
  context:    {dialogue_context, meta_context}        ← 编译上下文
  cognition:  {active_beliefs, resolved}             ← 信念收敛
  plan:       {}                                     ← 无 LLM, 空
```

---

## 五、关闭序列

```
shutdown():
  1. EventLog.close()     → 关闭 SQLite 连接
  2. FeedbackBridge 清空   → 丢弃未消费的决策 (下次启动重新评估)
  3. CognitionHub 清空     → 信念缓冲丢弃 (持久化层保存)
  4. MetaSubscriber 停止   → EventBus 退订

关闭后状态:
  EventLog 持久化 → data/event_log.db (SHA256 链完整)
  UnifiedContext → 内存态丢失 (设计选择: 不持久化上下文)
  Cognition → 信念缓冲丢失 (下次从 BeliefAccumulator 冷启动)
```

---

## 六、关键设计决策记录

| 决策 | 原因 | 替代方案 |
|------|------|---------|
| 模块全部懒加载 | 避免 v3 遗留模块拖慢启动 | eager init (需要完整依赖图) |
| DiscourseManager 跳过 | v3 遗留, 1,988L 不可用 | 修复 MacroDimensions, 完整接入 |
| Cold→Hot 最大 5 tick 延迟 | Meta 需要多 Tick 证据积累 | 同步审核 (阻塞热路径) |
| 冷路径 fire-and-forget | 不阻塞用户即时回答 | 同步等待 (类似传统 React) |
| 蓝图默认 Hybrid | 平衡精度与成本 | RULE_BASED (更快) / LLM_DRIVEN (更准) |
| SHA256 事件链 | 不可变, 可审计, 可 replay | 无链式验证 (更简单, 不可审计) |
