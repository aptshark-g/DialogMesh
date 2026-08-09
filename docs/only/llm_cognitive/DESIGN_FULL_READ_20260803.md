# LLM 认知层设计文档全面精读（第二轮）

> 日期: 2026-08-03 | 精读对象:
> `ENGINEERING_MULTILAYER_LLM.md`（1570 行，认知双工锚文档）+
> `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（798）+
> `ENGINEERING_LLM_PROVIDERS.md`（791）+
> `design_cognitive_compiler.md`（1735）+
> `ENGINEERING_COGNITIVE_COMPILER.md` + `DESIGN_COGNITIVE_DYNAMICS_V6.md`（305）
> 配套: `AUDIT_ENTRY_20260803.md`（一轮盘点）
> 本文档 = 设计全貌凝练 + 设计↔代码对照 + 待讨论点。

---

## 一、认知双工架构精读（ENGINEERING_MULTILAYER_LLM.md，1570 行）

### 1.1 核心命题与 ADR

```
核心命题: Agent = "以 LLM 为认知核心、算法为神经加速层的多认知体系统"
  （不是"带 LLM 的规则系统"）

ADR-010 LLM 是认知核心（融合时 LLM 置信度权重 >= 0.5）
ADR-011 三层 LLM（Layer15/Layer25/Layer3 独立类）
ADR-012 Cognitive Tree 独立于 Topic Tree
ADR-013 共享树通信（create/read/update_status/fork/link/subscribe/query）
ADR-014 穿透式 Answer LLM（直读 DialogueState + CognitiveTree + 各层输出）
ADR-015 幻觉三层防御（SchemaGuard→HallucinationDetector→BiasDetector）
ADR-016 渐进启用（配置开关，算法引擎始终 fallback）

诚实标记（§1.4/§16）: "v3.0 架构大量模块尚未实现；本文档是从零设计的施工蓝图"——
  但 §16.1 S-01 显示 LLM 引擎错误处理/重试/降级已按修复专家实现完成（✅）。
```

### 1.2 认知双工（HybridEngine）

```
算法引擎 ∥ LLM 引擎并行（ThreadPoolExecutor）:
  策略1: 算法先完成且置信度>0.9 → 立即输出（LLM 后台继续，回调更新认知状态）
  策略2: 算法置信度<0.6 → 必须等 LLM
  策略3: 都完成 → FusionEngine 加权融合

LLMEngine 基类流程: 构建 Prompt（模板+上下文+活跃分支）→ 调用 Provider →
  解析结构化输出 → 在 Cognitive Tree 创建节点 → 返回 LLMResult
6 个 LLM 实例: PCR(语义噪声/期望/认知快照) / Intent(深层意图/隐含实体) /
  Planning / Meta-Cognitive / Reflective / Answer
```

### 1.3 Cognitive Tree（§8，思考树本体）

```
API: add_node/get_node/update_status(权限: Meta 可改任何, 其他只能改自己)/
  fork_node(旧版本 SUPERSEDED, 继承边)/add_edge/find_by_type/find_by_llm/
  find_active_branch/find_stale_branches/traverse_dfs/bfs/subscribe/
  add_cross_ref(跨会话硬拷贝)/to_dict/from_dict
存储: CognitiveTreeStore（内存缓存 + SQLite，10000 上限，30 天归档）

AccessControlMatrix（§9）: 6 LLM 权限矩阵
  PCR: PERCEPTION/HYPOTHESIS | Intent: HYPOTHESIS/REASONING |
  Planning: REASONING/DECISION/ALTERNATIVE | Meta: VALIDATION/REFLECTION(update all) |
  Reflective: LEARNING/REFLECTION(update none) | Answer: HYPOTHESIS

EventBus（§10）: NODE_CREATED/STATUS_CHANGED/CONFLICT_DETECTED/
  BRANCH_SWITCHED/USER_FEEDBACK/SESSION_ENDED（后台线程队列+订阅过滤）
```

### 1.4 幻觉三层防御（§12）

```
Layer1 实时拦截: SchemaGuard（工具存在/参数 Schema/必填/类型）
Layer2 跨轮验证: HallucinationDetector 7 类型（factuality/consistency/plausibility）
  HallucinationRisk = α(1-F) + β(1-C) + γ(1-P)，>0.7 红色告警
Layer3 长期复盘: BiasDetector（过度规划/保守/Skill 依赖/画像偏见）
```

### 1.5 渐进启用 + 成本模型（§13-14）

```
五阶段: Hybrid(PCR+Intent) → Planning+Tree → Meta → Reflective → Answer 全面替代
延迟预算: 310-1200ms/轮，4K-12K tokens
成本优化: 小模型(7-13B)做 Hybrid / 大模型(70B+)做 Meta+Reflective / 缓存 / 异步 / 智能降级
FeatureToggle: 运行时切换 + emergency_rollback
```

### 1.6 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| CognitiveTree | `v3_0/cognitive_tree/manager.py`（add_node/edge/DFS/BFS/active/stale 全实现）| ✅ |
| AccessControlMatrix | `v3_0/cognitive_tree/models.py:340` | ✅ |
| 6 LLM 实例 | `llm_providers/llm_instances/`（answer/intent/meta/pcr/planning/reflective 6 文件）| ✅ |
| LLM 错误处理/重试（S-01）| `base.py` LLMProvider_v3.generate_async（指数退避 max3）| ✅ 已实现 |
| HybridEngine（并行）| `orchestrator/hybrid_engine.py` + `cognitive_duplex/`（7.9KB 根级）| ⚠️ 类存在，需核对 |
| FusionEngine | `orchestrator/fusion_engine.py` + `association/fusion_engine.py` | ⚠️ 多处 |
| HallucinationDetector | `security/hallucination_detector.py`（消费思考树）| ✅ |
| BiasDetector | `security/bias_detector.py` | ✅ |
| CognitiveTreeStore（SQLite）| 根级 cognitive_compiler/compiler.py → v3_0 CognitiveTreeStore | ⚠️ 薄 |
| **v6 主路径接线** | runtime/cli engine 不消费 cognitive_tree | ❌ |

> 结论: 认知双工设计的核心组件（Tree/ACM/6LLM/重试/幻觉防御）**v3 路径已实现**；
> v6 主路径未接；HybridEngine/FusionEngine 多处实现需归一（orchestrator/
> cognitive_duplex/association 三处）。

---

## 二、待精读

```
下一篇: DESIGN_MULTILAYER_LLM_COGNITIVE.md（798）→ ENGINEERING_LLM_PROVIDERS.md（791）
       → design_cognitive_compiler.md（1735）→ ENGINEERING_COGNITIVE_COMPILER.md
       → DESIGN_COGNITIVE_DYNAMICS_V6.md（305）

---

## 二、多层 LLM 认知设计精读（DESIGN_MULTILAYER_LLM_COGNITIVE.md，798 行）

### 2.1 核心范式: 双树认知架构

```
架构演进: v2.0 算法主/LLM 仆（主从式）→ v3.0 认知双工（算法=神经加速层, LLM=认知核心）
为什么 LLM 需要独立 Tree of Thought:
  ① 认知主权区分（Topic Tree=用户世界模型 / Cognitive Tree=LLM 心智模型）
  ② 通信载体（LLM 间交换"我怎么理解/置信度 X"，非用户说了什么）
  ③ 反思闭环（Meta 反思的是 LLM 推理过程，不污染用户对话）
  ④ 幻觉可追溯（在推理节点找错误，不在用户话题找）

双树定义:
  TopicTree = (V_topic, E_topic, W_topic)（用户世界模型）
  CognitiveTree = (V_cog, E_cog, M_cog, T_cog)
    V_cog: {node_id, cog_type, source_llm, timestamp, content, confidence, evidence, action, status, metadata}
    E_cog: {source, target, edge_type, weight, condition}
    M_cog: {reflections, validations, version_history, cross_refs}
    T_cog: {root, active_branch, stale_branches, depth_limit=10}

CogType 10 类: PERCEPTION/HYPOTHESIS/REASONING/DECISION/ACTION/OBSERVATION/
  REFLECTION/VALIDATION/LEARNING/COMMUNICATION
EdgeType 8 类: DERIVES/SUPPORTS/CONTRADICTS/CONDITIONAL/ALTERNATIVE/REFINES/
  SUMMARIZES/CROSS_REF
交叉引用: 单向（Cognitive 可引用 Topic；Topic 删除不影响 Cognitive 生命周期）
```

### 2.2 三层 LLM（系统 1/2/3 类比）

```
Layer 1.5 Hybrid（每轮必达, 50-200ms, 系统1）:
  算法引擎 ∥ LLM 引擎并行 → 融合器
  融合公式: c_A>0.85 且 c_B<0.6→A / c_A<0.6 且 c_B>0.85→B /
    c_A≈c_B→weighted(c_A·A+c_B·B)/(c_A+c_B) / 都低→ask_user
  冲突检测: A≠B 且 c_A>0.5 且 c_B>0.5 → CONTRADICTS 边 + Meta 快速检查 +
    保守策略（max(c)×0.8）
  PCR-LLM(PERCEPTION+HYPOTHESIS) / Intent-LLM(HYPOTHESIS+REASONING) /
  Planning-LLM(REASONING+DECISION+ALTERNATIVE)

Layer 2.5 Meta-Cognitive（跨轮异步, 系统2）:
  触发: 冲突/低置信(<0.6)/用户异常/定期(5轮)/会话结束/手动
  三层验证: 事实性(FactualityScore=VerifiedFacts/TotalClaims, <0.8 告警) /
    一致性(ConsistencyScore=1-Conflicts/CrossChecks) / 合理性(LLMJudge)
  幻觉 6 类型: 事实/逻辑/引用/参数/策略/自我
  HallucinationRisk = α(1-F)+β(1-C)+γ(1-P), >0.7 红色告警
  算法调优建议: 一致性得分累积 → 统计报告（盲区/误判/模式选择）

Layer 3 Reflective（跨会话, 系统3）:
  偏见检测 Bias = (Observed-Expected)/Expected（过度规划/保守/Skill 依赖/画像偏见）
  结构健康度 TreeHealth = 0.25·Balance+0.25·Coverage+0.25·Traceability+0.25·Reuse
  画像深度更新 Profile_new = α·Profile_current + (1-α)·Profile_session
  系统级学习策略: 参数/规则/Skill/LLM/架构策略 → 影子模式验证 M 轮 → 自动应用
```

### 2.3 LLM 间通信协议（共享认知树）

```
通信模型: 非消息传递——通过读写 Cognitive Tree 节点交换信息
协议 = (CognitiveTree, AccessControl, EventBus, Schema)
操作: CREATE/READ/UPDATE/FORK/LINK/SUBSCRIBE/QUERY
节点生命周期: CREATED→ACTIVE→{VALIDATED|INVALIDATED|SUPERSEDED}→ARCHIVED
版本控制: 不覆盖，FORK 新版本（v1 INVALIDATED → v2 VALIDATED）
一致性维护: Topic 变化 → 标记 needs_revalidation → Meta 快速验证 → 失败则 INVALIDATED+上游重推
```

### 2.4 Answer LLM（穿透层）

```
唯一直接面对用户; 双重身份（客服 + 认知网络成员）
输入 AnswerContext: 用户层(画像+Topic) + 系统层(算法+LLM+融合模式) +
  认知层(活跃分支+置信度+已知不确定性) + 约束层(风格/结构/诚实声明) + 记忆层
幻觉缓解: 置信度<0.7 必须声明不确定性 / Skill 模板约束结构 / Cognitive Tree 回溯
  （无法找到推理链必须说"不知道"）/ Meta 预审高风险回复
```

### 2.5 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| CognitiveTree（节点/边/分支/版本）| `v3_0/cognitive_tree/manager.py`（CogType/Edge/active/stale 全实现）| ✅ |
| AccessControlMatrix | `v3_0/cognitive_tree/models.py:340` | ✅ |
| 6 LLM 实例 | `llm_providers/llm_instances/`（6 文件）| ✅ 薄封装 |
| FusionEngine 融合公式 | `orchestrator/fusion_engine.py` + `association/fusion_engine.py` | ⚠️ 多处待归一 |
| HallucinationDetector（6 类型）| `security/hallucination_detector.py` | ✅ |
| BiasDetector（TreeHealth）| `security/bias_detector.py` | ✅ |
| Meta-Cognitive 三层验证 | `v3_0/cognitive_compiler/meta_cognitive.py`（4.3KB）| ⚠️ 需核对 |
| Reflective 分析 | `v3_0/cognitive_compiler/reflective.py`（3.6KB）| ⚠️ |
| **LLM 间通信（共享树）** | llm_instances 是否真写树（llm_engine.py:12 有 CognitiveTreeNode）| ⚠️ 需核对写入路径 |
| **v6 主路径接线** | runtime/cli 不消费 | ❌ |

> 结论: 双树设计完整；v3 路径实现了树+ACM+6LLM+幻觉/偏见检测；融合器/元认知验证器
> 需核对真实实现深度；v6 未接。

### 2.6 代码深读补证（2026-08-03）

```
❌ 实锤: LLMEngine.process() 从不调用 build_cog_node()
  llm_engine.py: build_cog_node 已实现（构造 CognitiveTreeNode），
  但 process() 返回 LLMEngineResult 时 node_id=None，从不写树
  → 6 个 LLM 实例的思考从不进入 Cognitive Tree
  → 双树设计的核心"LLM 间通过共享树通信"在代码层断裂
  （与 _meta_consumer/_trace_v3 同型: 组件齐备、接线断）

✅ Meta 三层验证器已实现:
  v3_0/cognitive_compiler/meta_cognitive.py
    FactualChecker / ConsistencyChecker / ReasonablenessChecker /
    HallucinationDetector / MetaCognitiveValidator

⚠️ FusionEngine 三处并存:
  orchestrator/fusion_engine.py（完整版: FusionSource/FusionStrategy/
    FusionResult/ConflictDetector/FusionEngine+_fallback_to_algorithm）
  association/fusion_engine.py（简化版: stage_mgr/resolver/workspace）
  cognitive_duplex/fusion.py（另一份）

---

## 三、LLM Provider 工程精读（ENGINEERING_LLM_PROVIDERS.md，791 行）

### 3.1 设计核心

```
定位: 6 个认知引擎（PCR/Intent/Planning/Meta/Reflective/Answer）的模型调用基础设施
现有（7 文件）: base(LLMProvider ABC) / openai / local / hybrid_router(4 策略+
  fallback) / failover(主备+冷却+恢复) / provider_factory / mock

v3.0 升级（4 项）:
  ① 认知模式: fast(0.1/256/5s) / deep(0.3/1024/30s) / reflective(0.5/2048/60s)
     → request.cognitive_mode + supports_cognitive_mode()
  ② 原生异步: generate_native_async（aiohttp/AsyncOpenAI + semaphore 限流，
     非 run_in_executor 伪异步）
  ③ 流式: generate_stream（SSE 逐字）
  ④ 认知模式路由: cognitive_mode_routing{fast: [local-1.5b, local-7b, cloud],
     deep: [...], reflective: [cloud, ...]}；异步先并发健康检查再按优先级调用
     （非竞争模式——避免慢 Provider 拖累）
  + CognitiveModeProvider 包装器 / create_cognitive_router

测试目标: 各 Provider 单测/异步并发/4 策略+3 模式路由/故障转移/认知模式参数映射/100 并发<2s
```

### 3.2 代码对照（实锤——v3.0 升级全部未落地）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| base.py（LLMProvider + v3 generate_async 重试 S-01）| ✅ | 已实现 |
| ProviderManager（配置/路由/统计）| `provider_manager.py` 14.5KB | ✅ |
| CircuitBreaker | `circuit_breaker.py` 16.2KB | ✅ |
| HybridRouter（4 策略）| `hybrid_router.py` 7.6KB | ✅ 基础 |
| FailoverProvider | `failover_provider.py` 6.6KB | ✅ |
| StreamingAggregator/SSE/WebSocket | `streaming.py` 10.8KB | ✅（被 v3_0/llm_providers 消费）|
| **cognitive_mode / generate_native_async** | 根级 llm_providers **零实现**（rg 无结果）| ❌ |
| **CognitiveModeProvider** | 不存在 | ❌ |
| **cognitive_mode_routing** | 不存在 | ❌ |
| **v3_0/llm_providers/** | 旧版另套（5 文件，消费根级 streaming）| ⚠️ 双套并存 |

> 实锤: ENGINEERING_LLM_PROVIDERS 的 v3.0 升级（认知模式/原生异步/模式路由）**全部未落地**；
> 且根级与 v3_0 两套 Provider 并存（同型"多代演进→分裂"）。llm_providers 零测试
> （AUDIT_ENTRY §三）。

### 3.3 待讨论点

1. 认知模式（fast/deep/reflective）是否落地为本次 LLM 认知层施工的第一优先。
2. 双套 Provider（根级 vs v3_0）归一。
3. 走网关 vs 直连（蓝图 P0-2 llm_reply 不调 LLM 联动）。

---

## 四、认知编译器工程精读（ENGINEERING_COGNITIVE_COMPILER.md，913 行）

### 4.1 设计核心

```
定位: "Cognitive Tree 是 LLM 的共享心智空间，认知编译器是信息进入该空间的唯一入口"
核心枢纽: 将 6 个 LLM 实例的推理结果编译为 Cognitive Tree 节点

六大组件:
  CognitiveCompiler.compile()（统一编译入口: 权限检查+事件触发）
  NodeLifecycleManager（创建→验证→采纳→归档→版本）
  EdgeManager（DERIVES/SUPPORTS/CONTRADICTS/...）
  AccessControlMatrix（运行时检查: 6 LLM 权限矩阵）
  EventBus（异步通知: 订阅/发布/过滤）
  Querier（按类型/LLM/状态查询 + DFS/BFS）

6 LLM 读写模式（设计 §11）:
  PCR: PERCEPTION+HYPOTHESIS（改自己）| Intent: HYPOTHESIS+REASONING（改自己）|
  Planning: REASONING+DECISION+ALTERNATIVE（改自己）| Meta: VALIDATION+REFLECTION（改所有）|
  Reflective: LEARNING+REFLECTION（只读）| Answer: HYPOTHESIS+ACTION（改自己）
集成示例: PCR 创建 → Intent 引用父节点(DERIVES) → Meta 验证(status) → Meta 建 CONTRADICTS 边
```

### 4.2 代码对照（实锤——实现完整、调用断裂）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| CognitiveCompiler.compile() | `v3_0/cognitive_compiler/compiler.py` 11.6KB | ✅ |
| NodeLifecycleManager | `v3_0/cognitive_compiler/lifecycle.py` 6.0KB | ✅ |
| EdgeManager | `v3_0/cognitive_compiler/edge_manager.py` 6.1KB | ✅ |
| AccessControlMatrix（运行时）| `v3_0/cognitive_compiler/access_control.py` + tree/models | ✅ |
| EventBus | `v3_0/cognitive_compiler/event_bus.py` 7.5KB | ✅ |
| Querier | `v3_0/cognitive_compiler/querier.py` 7.3KB | ✅ |
| orchestrator 接线 | `orchestrator/bootstrap.py:255-293` + `orchestrator.py:42-45` | ✅ v3 路径 |
| **6 LLM 实例调用 compiler** | `llm_engine.py` process() 不写树不调 compiler | ❌ **断裂** |

> **核心实锤（LLM 认知层最大断点）**: 认知编译器（唯一入口）完整实现且 v3 orchestrator
> 接线，但 **6 个 LLM 实例（llm_engine.py）从不调用它**——LLMEngine.process()
> 返回时 node_id=None，不写树。设计 §11 的"PCR 创建→Intent 引用→Meta 验证"链路
> **从未在代码中发生**。+ 持久化侧 CognitiveTreeStore（ENGINEERING_PERSISTENCE §12）
> 也未落地（持久化审计 §五）。

---

## 五、待精读

```
最后一篇: DESIGN_COGNITIVE_DYNAMICS_V6.md（305）——认知动力学（思考树上层哲学）
  注: design_cognitive_compiler.md（1735 行）= 意图前置解析层（SyntacticDecomposer/
  HeaderInjector/CohesionScorer/DualStructure）——对话树/意图审计已覆盖，非 LLM 认知层核心。

---

## 六、认知动力学精读（DESIGN_COGNITIVE_DYNAMICS_V6.md，305 行）

### 6.1 设计核心（思考树上层哲学）

```
四范式层级: Object("有什么")→State("是什么状态")→Transition("为什么变")→
  Dynamics("变化的规律", 远景)
核心洞察: "真正的智能不在状态——在状态的变化。"

StateObject 统一状态体系: Snapshot(1s)/Workspace(1 对话)/Mind(1 月)/Knowledge(永久)
  生命周期升级: Snapshot→(accumulate)→Workspace→(reflect)→Mind→(commit)→Knowledge

Transition = v6 一等公民（独立对象）:
  {id, from_state, to_state, reason, evidence, effects(StateDelta), confidence}
  TransitionReason 14 种: 观察(OBSERVE/NEW_EVIDENCE) | 推理(INFER/COMPARE/ANALOGIZE) |
    冲突(CONTRADICT/REJECT/RESOLVE) | 整合(MERGE/FREEZE/GENERALIZE) |
    反思(REFLECT/REVISE/STRENGTHEN/WEAKEN) | 视角(CHANGE_PERSPECTIVE/SHIFT_ATTENTION)

Contextual Learning: 从"策略总效果"→"什么 Context 下什么策略好"
  StrategyContext{perspective, depth, domain, time_of_day, discussion_mode, user_cognitive_state}

Interaction Graph: Relation(静态)→Interaction(动态影响传播)
  InteractionEdge{propagation_rule, influence_weight, activation_threshold}

ExecutionTraceV3: State→Transition(reason+evidence)→State（每变化有原因）
```

### 6.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| StateObject/StateDelta/Transition/TransitionReason | `state/state_object.py`（33/153/171）| ✅ |
| ExecutionTraceV3（snapshot/record_transition/meta_analyze）| `state/execution_trace.py:17` | ✅ |
| ContextualStrategy | `v4/cognitive/contextual_strategy.py`（8KB）| ✅ 类存在 |
| InteractionGraph | `state/interaction_graph.py`（13.5KB）| ✅ |
| **引擎接线** | `_trace_v3` 恒 None（元认知 DEEP_AUDIT M3）| ❌ 未实例化 |

> 印证: 认知动力学（Transition 一等公民）的实现 = state/ 包（执行层审计已覆盖）；
> ExecutionTraceV3 类完整但引擎未接线（与元认知 M3 同断点）。

---

## 七、LLM 认知层设计精读完成度（6/6）

| # | 文档 | 核心结论 |
|---|--:|---|
| 1 | ENGINEERING_MULTILAYER_LLM（1570）| 认知双工 ADR-010~016；Tree/6LLM/幻觉防御 v3 已实现 |
| 2 | DESIGN_MULTILAYER_LLM_COGNITIVE（798）| 双树架构/CogType 10/Edge 8/LLM 间通信协议（共享树）|
| 3 | ENGINEERING_LLM_PROVIDERS（791）| v3.0 升级（cognitive_mode/native_async/模式路由）**全未落地** + 双套 Provider |
| 4 | ENGINEERING_COGNITIVE_COMPILER（913）| 编译器唯一入口**完整实现但 6 LLM 从不调用**（最大断点）|
| 5 | design_cognitive_compiler（1735）| 意图前置解析层——对话树/意图审计已覆盖（非核心）|
| 6 | DESIGN_COGNITIVE_DYNAMICS_V6（305）| Transition 一等公民 → state/ 包实现，引擎未接线 |

> **LLM 认知层核心结论**:
> 1. 思考树体系（Tree + Compiler + ACM + EventBus + 6 LLM）v3 路径**组件全实现**，
>    但 LLMEngine 从不写树 → "LLM 间共享树通信"全链路断（与 _meta_consumer 同型）
> 2. LLM Provider v3.0 升级全未落地 + 双套并存 + 零测试
> 3. 根级 cognitive_compiler 4 孤儿 + cognitive_tree CrossRef async 9 测试失败
> 4. v6 主路径（runtime/cli）不消费认知层（但 tiered/ 活跃在对话树 A 路径）
```
```
```
