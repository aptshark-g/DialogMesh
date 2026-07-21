# DialogMesh v6 — 业务链设计 · 第〇章：PCR (预认知路由器)

> 版本: v1.0 | 日期: 2026-07-21
> 
> 设计来源: design_layer0_pcr_and_layer1_intent_parser.md (v2.4) +
>          design_pcr_interface_v2_1.md + design_pcr_issues_discussion.md +
>          ENGINEERING_PCR.md + 噪声拓扑修正讨论
>
> 核心命题: PCR 不做过滤——做热力图标记。用局部 NoiseSpan 取代全局 noise_level。
>          期望/噪声/复杂度/画像 四个信号端到端调控下游 8 条链。

---

## 一、PCR 在 10 链中的位置

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────────┐
│  PCR (第〇章) — 所有链的输入网关                   │
│  ─────────────────────────────────            │
│  Stage 1: ExpectationIdentifier                │
│  Stage 2: NoiseSpanDetector (拓扑标记)          │
│  Stage 3: ComplexityEstimator                  │
│  Stage 4: CognitiveProfiler                    │
│  Stage 5: StrategyDeriver                      │
│                                                 │
│  输出: PCROutput_v1                             │
│    ├─ expectation    → 调控链01-04 (对话树策略)   │
│    ├─ noise_spans    → 调控链02 (LLM回复cleanup)  │
│    ├─ complexity     → 调控链01 (Context深度)     │
│    ├─ cognitive      → 调控链08 (画像更新)        │
│    └─ execution_mode → 调控链05 (行为预测开关)    │
└─────────────────────────────────────────────────┘
  │
  ▼  8 条下游链接收 PCR 信号
```

---

## 二、5 阶段 Pipeline

### Stage 1: ExpectationIdentifier (期望识别)

```
输入: user_text + history
输出: expectation ∈ {TOOL, ADVISOR, COMPANION, UNKNOWN} + confidence

三层级联:
  Tier 0 (0-2ms):   规则快路径 — 关键词模式匹配, 覆盖 90%+
  Tier 1 (0-1ms):   历史推断 — follow_markers + 主题连续性
  Tier 2 (100-200ms): LLM few-shot — 仅 confidence < 0.5 时触发

调控链路:
  TOOL → 链01 CompileContext: fast mode, depth=1, skip DomainSelector
  ADVISOR → 链01 CompileContext: deep mode, subgraph_expand=True
  COMPANION → 链01 CompileContext: conversational mode, 末尾追加 ask_user 节点
  UNKNOWN → 链09 MetaCognition: 触发 clarify 信号
```

### Stage 2: NoiseSpanDetector (噪声拓扑标记) ⚠️ 重设计

```
⚠️ 原设计缺陷: 压扁为全局 noise_level: float → 丢信息
✅ 修正方案: 输出 noise_spans: List[NoiseSpan]

NoiseSpan:
  start_char, end_char: int
  noise_type: TYPO | AMBIGUOUS_ANAPHORA | JARGON_ABUSE | 
              UNRELATED_FLUFF | LOGICAL_LEAP | PROMPT_INJECTION_SUSPECT
  severity: float (0-1)
  suggested_correction: Optional[str]
  reason: str

三维模型 (保留):
  N = α·Nsemantic + β·Nstructural + γ·Nreferential  (α=0.5, β=0.3, γ=0.2)
  但这是内部计算——输出是 NoiseSpan 列表, 不是压扁的标量

认知刷新豁免:
  时间/指代/描述三维判别: 正常话题切换 ≠ 噪声
  temporal_factor × (0.4·referential_dissonance + 0.6·discursive_shift)

调控链路:
  TYPO → 链02 LLM: input_corrections 字段, 自动纠偏实体提取
  AMBIGUOUS_ANAPHORA → 链01: 强制 CLARIFICATION mode
  PROMPT_INJECTION_SUSPECT → 链02 LLM: suppress标记, isolate span
  LOGICAL_LEAP → 链10 Subgraph: 触发水波扩展
```

### Stage 3: ComplexityEstimator (复杂度评估)

```
输入: user_text + expectation
输出: complexity_level: float (0-1)

规则推导:
  1. YAML 配置表匹配 (intent_complexity_map.yaml)
  2. 步骤计数: step_markers → step_count × 0.10
  3. 领域跨度: matched_domains × 0.15
  4. 期望调整: TOOL×0.8, COMPANION×1.2

调控链路:
  complexity > 0.8 → 链01: max_sub_intents ↑
  complexity < 0.2 → 链01: Fast Path 门控 (跳过 Stage 6-8)
```

### Stage 4: CognitiveProfiler (认知画像快速评估)

```
输出: CognitiveProfile_v1
  ├─ cognitive_level: float
  ├─ expertise_level: float
  ├─ preferred_detail: float
  └─ cognitive_traits: List[str]

更新方式: 滑动窗口 EMA (指数移动平均)
  EMA(t) = α·S(t) + (1-α)·EMA(t-1), α=0.3

调控链路:
  → 链08 Profile: 快速评估结果注入慢速完整评估
  → 链05 Behavior: 画像偏置 → 主题匹配权重 (OCEAN→topic_weight)
  → 链02 LLM: 控制系统指令风格
```

### Stage 5: StrategyDeriver (策略推导)

```
输入: expectation × noise × complexity × cognitive
输出:
  execution_mode: FAST_EXECUTE | CLARIFICATION | DEEP_RESEARCH | CONVERSATIONAL | BALANCED
  prompt_style: BRIEF | EXPLANATORY | TUTORIAL | BALANCED
  ambiguity_strategy: AGGRESSIVE_AUTO | CONSERVATIVE_ASK | BALANCED
  suggested_next_actions: List[str]
  should_attach_process: bool
  should_refresh_analysis: bool

决策矩阵 (可配置 YAML):
                 TOOL      ADVISOR   COMPANION   UNKNOWN
  低噪声低复杂  EXECUTE    RESEARCH  EXPLAIN     CLARIFY
  低噪声高复杂  EXECUTE    RESEARCH  TUTORIAL    CLARIFY
  高噪声低复杂  CLARIFY    BALANCED  BALANCED    CLARIFY
  高噪声高复杂  CLARIFY    BALANCED  BALANCED    CLARIFY
```

---

## 三、PCR → 8 链调控映射

```
链 01 (对话树):
  expectation → compile mode (fast/deep/conversational)
  complexity → Path 选择 (Fast/Async/Slow)
  noise_spans.AMBIGUOUS → 强制 CLARIFICATION → 不 fork 新分支

链 02 (LLM 回复):
  noise_spans.TYPO → input_corrections → 自动纠偏
  noise_spans.INJECTION → suppress 标记
  prompt_style → 系统指令
  execution_mode → max_tokens 调整

链 03 (用户编辑):
  (PCR 不参与编辑环节)

链 04 (元认知 + 持久化):
  expectation=UNKNOWN → 触发 clarify Signal
  noise_level 异常 → 触发 Audit Signal

链 05 (行为链):
  cognitive_profile → 画像偏置 → topic匹配权重
  execution_mode=FAST_EXECUTE → 跳过行为预测

链 06 (关联链):
  (PCR 不直接调控——关联链读对话树状态)

链 07 (工程链):
  complexity → max_sub_intents 映射

链 08 (画像):
  cognitive_profile → 快速评估结果注入慢速TrackA

链 09 (元认知审核):
  UNKNOWN + high_noise → 触发 reconsider Signal
  noise_source 分类 → 针对性复盘

链 10 (子图):
  LOGICAL_LEAP noise → 触发水波扩展
  DEEP_RESEARCH mode → subgraph_expand_all
```

---

## 四、生命周期

```
启动:
  PCRLifecycleManager.initialize()
    ├─ RuleBasedPCR 实例化
    ├─ warm_up() — 预热缓存, 加载 YAML
    ├─ FallbackEngine 启动
    └─ TelemetryCollector 启动

运行时 (每轮 on_event):
  PCRInput_v1(user_text, history, conversation_id)
    → RuleBasedPCR.evaluate()
    → PCROutput_v1

降级:
  规则失败 → FallbackEngine
    ├─ conservative: 返回 BALANCED 默认输出
    ├─ degraded: 跳过 Stage 2-4, 只做期望识别
    └─ pass_through: 全部跳过, BALANCED 直接通过

关闭:
  PCRLifecycleManager.shutdown()
    ├─ 后台健康检查线程停止
    └─ TelemetryCollector 落盘
```

---

## 五、性能约束

```
规则快路径: < 10ms (Tier 0 + Tier 1, 覆盖 95%)
LLM fallback: < 200ms (Tier 2, 仅 5% 触发)
端到端 (100轮对话): < 20ms

容错:
  ─ FallbackEngine 3级回退
  ─ 热加载配置 (YAML → 运行时, 无重启)
  ─ 健康检查 (30s 探针)
```

---

## 六、实现状态

```
✅ PCR 核心代码:      3500行 · 9模块 · 168/170 test PASS
❌ 接入 on_event:     0% — PCR.evaluate() 从未被调用
❌ 8链调控映射:       0% — PCROutput 信号从未流向任何链
❌ NoiseSpan 拓扑:    设计修正中 — 当前仍是全局 noise_level
❌ 生命周期管理:      代码存在 — PCRLifecycleManager 未被API使用
```

---

## 七、接入优先级

```
P0: on_event 接入 PCR.evaluate()
    └─ 5条核心调控信号流向链 01/02/08

P1: NoiseSpan 拓扑替换 noise_level
    └─ 6 种噪声类型 × 差异化下游处理

P2: FallbackEngine + 热加载 + Telemetry
    └─ 生产级多级回退 + 无重启配置更新
```
