# DialogMesh — 三层混合架构设计

> 2026-07-24 · 微服务冷路径 + 异步并行模块 + 网状热路径

---

## 一、三层全景

```
┌─────────────────────────────────────────────────────────────────┐
│  三层 = 同一系统的三个视角, 不是三个独立子系统                      │
│                                                                 │
│  微服务层 (冷路径)      后台异步, 防广播风暴, EventBus pub/sub    │
│  异步并行层 (模块内)    并发搜索/LLM/策略, ThreadPool效率         │
│  网状层 (热路径)        Decider串行化, 10链网状拓扑              │
│                                                                 │
│  连接: 热路径 publish 事件 → EventLog → EventBus → 冷路径订阅     │
│        冷路径 produce 修正 → 热路径下一次 Tick 消费               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、微服务层 — 冷路径 (Event Sourcing + CQRS)

### 2.1 架构

```
                        EventLog (SQLite, append-only, SHA256链)
                              │
                              ▼
                    EventBus (环形缓冲, pub/sub)
                     ╱          │          ╲
                    ▼           ▼           ▼
            Meta Subscriber  Assoc Subscriber  (未来: 更多)
            (8事件订阅)       (6事件订阅)
               │                 │
               ▼                 ▼
            MetaDecision     CausalChain
            Correction       TemporalPattern
               │                 │
               └──── 冷→热回写 ──┘
                      │
                      ▼
            下一次 Tick 的 Observe/Interpret
```

### 2.2 Meta Subscriber

```python
class MetaSubscriber:
    """冷路径微服务 — 订阅 8 种事件, 异步审核"""
    
    订阅: PCR_COMPUTED, ROUTE_GENERATED, INTENT_PARSED, REPLY_GENERATED,
          PROFILE_UPDATED, BEHAVIOR_RECORDED, ABC_EVALUATED, MIND_LEARNED
    
    触发: 每 5 ticks 或事件累积 > 10
    产出: META_REVIEWED (verdict + recommendation)
          ANOMALY_DETECTED (drift + source)
    
    回写: MetaDecision → Intent 重解析 (anomaly→re-parse)
          MetaDecision → Profile 重新校准 (drift→recalibrate)
    
    现有代码: ✅ meta_subscriber.py(63L), 13 subscribers, 96/96 tests
```

### 2.3 Association Subscriber

```python
class AssociationSubscriber:
    """冷路径微服务 — 订阅 6 种事件, 异步关联发现"""
    
    订阅: PCR_COMPUTED, ROUTE_GENERATED, INTENT_PARSED, REPLY_GENERATED,
          BEHAVIOR_RECORDED, MIND_LEARNED
    
    触发: 每 3 ticks 或事件累积 > 5
    产出: RELATION_DISCOVERED (new entity relation)
          CAUSAL_CHAIN (evidence-based)
          TEMPORAL_PATTERN (sequence→prediction)
    
    回写: hidden_relation → Context 追加
          causal_chain → LLM 推理增强
          temporal_pattern → Behavior 模式学习
    
    现有代码: ✅ association_subscriber.py, EventBus已就绪
```

---

## 三、异步并行层 — 模块内部

### 3.1 联邦索引 — 6源并发搜索

```python
class FederatedAnchorIndex:
    """模块内异步并行: 6源同时搜索"""
    
    源: RAG向量 | Discourse话题 | Behavior模式 | Association实体 | Engineering工具 | Meta启发链
    
    with ThreadPoolExecutor(max_workers=6):
        futures = {
            pool.submit(rag_search):    "rag",
            pool.submit(discourse_search): "discourse",
            pool.submit(behavior_search):  "behavior",
            pool.submit(assoc_search):     "association",
            pool.submit(engineering_search): "engineering",
            pool.submit(meta_search):       "meta",
        }
    
    合并: 温度×价值排序 + 去重 + 截断
    
    现有代码: ✅ federated_index.py + Rust版
```

### 3.2 多视角 LLM — 4视角并发

```python
class MultiPerspectiveAnalyzer:
    """4个DeepSeek实例并发分析"""
    
    perspectives: discourse / profile / association / pcr
    
    with ThreadPoolExecutor(max_workers=4):
        results = [pool.submit(llm, prompt, perspective) for perspective in ...]
    
    共识: 投票(≥3/4) → 锁定 | 分歧(<3/4) → AmbiguityBridge → L2.5信念
    
    现有代码: ✅ multi_perspective.py(210L), 未接入
```

### 3.3 策略联邦 — 多策略并发验证

```python
class StrategyFederation:
    """同一聚类的多种策略并行验证"""
    
    策略: LLM策略 | 蓝图策略 | 贪心 | 马尔可夫 | 动态规划
    
    with ThreadPoolExecutor(max_workers=5):
        [pool.submit(strategy, data) for strategy in strategies]
    
    元编排器: 记录各策略成功率 → 上下文感知选择
    
    现有代码: ✅ strategy_federation.py(276L)
```

### 3.4 RAG 并行图检索

```python
class RAGraphBridge:
    """多锚点并行 2-hop 图扩展"""
    
    with ThreadPoolExecutor(max_workers=4):
        [pool.submit(_expand_anchor, anchor, score) for anchor in anchors]
    
    合并: 分数加权 + 去重
    
    现有代码: ✅ ragraph.py(176L)
```

---

## 四、网状层 — 热路径

### 4.1 Decider 串行化

```
不是线性管道 PCR→Intent→L4→Behavior→LLM
不是广播风暴 36条push路径

而是 Decider 串行化:

Tick 1: PCR     → Event(PCR_COMPUTED)
Tick 2: Intent  → Event(INTENT_PARSED)  
Tick 3: Plan    → Event(PLAN_GENERATED)
Tick 4: Context → Event(CONTEXT_COMPILED)   ← 读 PCR+Intent+Discourse+Behavior
Tick 5: Subgraph→ Event(SUBGRAPH_COMPILED)   ← 读全部6域
Tick 6: LLM     → Event(REPLY_GENERATED)
Tick 7: Profile/Bhv/ABC/Mind → Events

每 Tick: 1 Command → Decider → 1 Event → evolve State → 下一 Tick
```

### 4.2 网状拓扑 — 不是线性

```
        PCR ────────→ Intent ────────→ Plan
         │               │               │
         │               ▼               │
         │          Discourse            │
         │               │               │
         └───────┬───────┴───────┬───────┘
                 ▼               ▼
              Context ←──── Subgraph ←──── Engineering
                 │               │
                 ▼               ▼
               LLM ←──── Profile + Behavior + Mind
                 │
                 ▼
             Meta (冷路径, 异步消费 Transition)
```

### 4.3 agent_native 接入点

```python
class AgentOrchestrator:
    def process(self, text, session_id):
        # 热路径: Decider 串行化
        for tick in [PCR, INTENT, PLAN, CONTEXT, SUBGRAPH, LLM]:
            result = tick.execute()
            # ⬇ 这一行是当前的 gap
            self._event_log.append(tick.event_type, result)
        
        # 冷路径: Subscriber 异步消费 (已建成, 自动触发)
        # Meta.Subscriber._on_event() 每 5 ticks 自动审核
        
        return llm_response
```

---

## 五、当前 gap → 只需接3根线

```
线1: agent_native 每个步骤后 → EventLog.append()
     代码: ✅ EventLog(api_event_log.py) 已就绪
     差距: agent_native.process() 缺少 append 调用

线2: Context 接入 ContextAssembler
     代码: ✅ context/ + context_manager/ (两套, ~8,000L)
     差距: agent_native 的 Context tick 未调用

线3: Subgraph 接入 SubgraphCompiler
     代码: ✅ subgraph_compiler.py(176L)
     差距: agent_native 的 Subgraph tick 未调用

Meta + Assoc Subscriber 自动运转:
     代码: ✅ 已建成, 96/96 tests
     差距: 无 — 只要 EventLog 有事件就会自动消费
```

---

## 六、实现优先级

```
P0 (今天): agent_native 加 EventLog.append() → 冷路径自动激活
P0 (今天): Context + Subgraph 接入 → 热路径网状
P1 (本周): 异步并行层全部接入 (联邦索引/多视角/策略联邦/RAG)
P2: Cold→Hot 回写 (Meta修正→Intent, Assoc→Context)
P3: Blueprint 系统 (编排器动态选蓝图)
```
