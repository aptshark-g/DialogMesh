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

```mermaid
graph TD
    USER["用户输入"]

    subgraph PCR["第〇章: PCR 预认知路由器"]
        S1["Stage 1<br/>ExpectationIdentifier"]
        S2["Stage 2<br/>NoiseSpanDetector<br/>⚠️ 拓扑标记"]
        S3["Stage 3<br/>ComplexityEstimator"]
        S4["Stage 4<br/>CognitiveProfiler"]
        S5["Stage 5<br/>StrategyDeriver"]

        S1 --> S2 --> S3 --> S4 --> S5

        OUT["PCROutput_v1<br/>expectation/noise_spans/complexity/cognitive/execution_mode"]
        S5 --> OUT
    end

    USER --> S1

    OUT -->|"expectation"| CH01["链01 对话树<br/>compile mode"]
    OUT -->|"noise_spans"| CH02["链02 LLM回复<br/>input_corrections"]
    OUT -->|"complexity"| CH01_SUB["链01 Context深度"]
    OUT -->|"cognitive"| CH08["链08 画像<br/>TrackA注入"]
    OUT -->|"execution_mode"| CH05["链05 行为链<br/>预测开关"]
    OUT -->|"ambiguity"| CH09["链09 元认知<br/>Reconsider Signal"]
    OUT -->|"logical_leap"| CH10["链10 子图<br/>水波扩展"]
```

---

## 二、5 阶段 Pipeline

```mermaid
flowchart LR
    INPUT["PCRInput_v1<br/>user_text + history"]

    subgraph S1["Stage 1: ExpectationIdentifier"]
        T0["Tier 0: 规则快路径<br/>0-2ms · 90%+"]
        T1["Tier 1: 历史推断<br/>0-1ms · 5%"]
        T2["Tier 2: LLM few-shot<br/>100-200ms · 5%"]
        T0 -->|"confidence≥0.5"| EXP["TOOL/ADVISOR/<br/>COMPANION/UNKNOWN"]
        T1 -->|"follow_markers"| EXP
        T2 -->|"仅低conf触发"| EXP
    end

    subgraph S2["Stage 2: NoiseSpanDetector ⚠️ 重设计"]
        NSEM["N_semantic<br/>填充词·情绪密度"]
        NSTR["N_structural<br/>语法异常·格式"]
        NREF["N_referential<br/>三维:时间/指代/描述"]
        NSEM --> FUSE["融合<br/>N=0.5Ns+0.3Nt+0.2Nr"]
        NSTR --> FUSE
        NREF --> FUSE
        FUSE --> SPANS["NoiseSpan[]<br/>start_char/end_char<br/>type/severity/correction"]
    end

    subgraph S3["Stage 3: ComplexityEstimator"]
        YAML["YAML 配置表匹配"]
        STEPS["步骤计数<br/>step_markers"]
        DOMAINS["领域跨度<br/>matched_domains"]
        YAML --> COMP["complexity_level<br/>0-1"]
        STEPS --> COMP
        DOMAINS --> COMP
    end

    subgraph S4["Stage 4: CognitiveProfiler"]
        COG["cognitive_level"]
        EXP_LEV["expertise_level"]
        PREF["preferred_detail"]
        TRAITS["cognitive_traits"]
    end

    subgraph S5["Stage 5: StrategyDeriver"]
        MODE["execution_mode<br/>FAST_EXECUTE/CLARIFY/DEEP_RESEARCH"]
        STYLE["prompt_style<br/>BRIEF/EXPLAIN/TUTORIAL/BALANCED"]
        AMB["ambiguity_strategy<br/>AUTO/CONSERVATIVE/BALANCED"]
        SUGG["suggested_next_actions"]
    end

    INPUT --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> OUT["PCROutput_v1"]
```

---

## 三、NoiseSpan 拓扑 (替代全局 noise_level)

```mermaid
graph TD
    INPUT["用户输入: '帮我写个脚本dddd懂的都懂'"]
    
    INPUT --> S2["NoiseSpanDetector"]

    S2 --> SPAN1["NoiseSpan<br/>start=8 end=12<br/>type=TYPO<br/>severity=0.7<br/>correction='ddd'"]
    S2 --> SPAN2["NoiseSpan<br/>start=13 end=17<br/>type=AMBIGUOUS_ANAPHORA<br/>severity=0.85<br/>reason='懂的都懂'指向不明"]

    SPAN1 -->|"TYPO"| FIX1["链02 LLM<br/>自动纠偏 'ddd'→clear"]
    SPAN2 -->|"AMBIGUOUS"| FIX2["链01 对话树<br/>强制 CLARIFICATION<br/>列出3个可能目标"]
    
    SPAN2 --> NOPE["❌ 旧方案<br/>noise_level=0.3<br/>下游无法区分处理"]
```

### NoiseSpan 类型 × 处理策略

```mermaid
graph LR
    subgraph TYPES["6种噪声类型"]
        TYPO["TYPO<br/>输入错字"]
        AMB["AMBIGUOUS_ANAPHORA<br/>模糊指代"]
        JARGON["JARGON_ABUSE<br/>过度术语"]
        FLUFF["UNRELATED_FLUFF<br/>无关赘述"]
        LEAP["LOGICAL_LEAP<br/>逻辑跳跃"]
        INJECTION["PROMPT_INJECTION<br/>注入攻击"]
    end

    subgraph ACTIONS["差异化下游处理"]
        A1["suppress标记<br/>input_corrections"]
        A2["强制CLARIFY mode<br/>列出候选目标"]
        A3["简化系统指令<br/>plain language"]
        A4["剪枝<br/>不送入LLM上下文"]
        A5["触发Subgraph<br/>水波扩展"]
        A6["isolate span<br/>XML转义隔离"]
    end

    TYPO --> A1
    AMB --> A2
    JARGON --> A3
    FLUFF --> A4
    LEAP --> A5
    INJECTION --> A6
```

---

## 四、PCR → 8 链调控映射

```mermaid
graph TD
    PCR["PCR Output<br/>expectation/noise_spans/complexity<br/>cognitive/execution_mode"]

    subgraph CHAINS["8 条下游链"]
        C01["链01 对话树<br/>compile_depth · fork策略"]
        C02["链02 LLM回复<br/>系统指令 · corrections"]
        C04["链04 元认知+持久化<br/>clarity signal · audit"]
        C05["链05 行为链<br/>预测开关 · 偏置权重"]
        C07["链07 工程链<br/>max_sub_intents"]
        C08["链08 画像<br/>快速评估注入TrackA"]
        C09["链09 元认知审核<br/>reconsider · 针对性复盘"]
        C10["链10 子图<br/>水波扩展触发"]
    end

    PCR -->|"expectation:TOOL"| C01
    PCR -->|"expectation:DEEP_RESEARCH"| C01
    PCR -->|"expectation:UNKNOWN"| C04
    PCR -->|"noise_spans:TYPO"| C02
    PCR -->|"noise_spans:INJECTION"| C02
    PCR -->|"noise_spans:LOGICAL_LEAP"| C10
    PCR -->|"complexity > 0.8"| C01
    PCR -->|"complexity < 0.2"| C01
    PCR -->|"execution_mode"| C05
    PCR -->|"complexity"| C07
    PCR -->|"cognitive_profile"| C05
    PCR -->|"cognitive_profile"| C08
    PCR -->|"noise_source:context_break"| C09
```

---

## 五、决策矩阵 (StrategyDeriver)

```mermaid
graph TD
    subgraph INPUTS["输入信号"]
        EXP["expectation<br/>TOOL/ADVISOR/COMPANION/UNKNOWN"]
        NZ["noise (聚合)<br/>low: <0.3 · high: ≥0.3"]
        CX["complexity<br/>low: <0.5 · high: ≥0.5"]
    end

    subgraph MATRIX["策略推导矩阵"]
        T1["EXECUTE"]; T2["CLARIFY"]; T3["RESEARCH"]
        T4["EXECUTE"]; T5["CLARIFY"]; T6["RESEARCH"]
        T7["CLARIFY"]; T8["BALANCED"]; T9["BALANCED"]
    end

    EXP --> MATRIX
    NZ --> MATRIX
    CX --> MATRIX

    MATRIX --> MODE["execution_mode"]
    MATRIX --> STYLE["prompt_style"]
    MATRIX --> AMB["ambiguity_strategy"]
```

| | TOOL | ADVISOR | COMPANION | UNKNOWN |
|---|---|:---:|:---:|---|
| **低噪声·低复杂** | FAST_EXECUTE | DEEP_RESEARCH | EXPLAIN | CLARIFY |
| **低噪声·高复杂** | FAST_EXECUTE | DEEP_RESEARCH | TUTORIAL | CLARIFY |
| **高噪声·低复杂** | CLARIFY | BALANCED | BALANCED | CLARIFY |
| **高噪声·高复杂** | CLARIFY | BALANCED | BALANCED | CLARIFY |

---

## 六、生命周期

```mermaid
sequenceDiagram
    participant API as API Startup
    participant LM as PCRLifecycleManager
    participant PCR as RuleBasedPCR
    participant FE as FallbackEngine
    participant TEL as TelemetryCollector

    API->>LM: initialize()
    LM->>PCR: RuleBasedPCR()
    LM->>PCR: warm_up()
    Note over PCR: 加载YAML配置<br/>预热规则缓存
    LM->>FE: start()
    LM->>TEL: start()
    LM-->>API: ready

    Note over PCR,TEL: === 运行时 ===

    loop 每轮 on_event
        API->>PCR: evaluate(PCRInput_v1)
        alt 成功
            PCR-->>API: PCROutput_v1
        else 规则失败
            PCR->>FE: fallback
            FE-->>API: BALANCED default
        end
    end

    Note over PCR,TEL: === 关闭 ===

    API->>LM: shutdown()
    LM->>TEL: flush() + stop()
    LM->>FE: stop()
    LM->>PCR: shutdown()
    LM-->>API: done
```

---

## 七、三级降级回退

```mermaid
graph TD
    REQ["PCR.evaluate()"] --> OK{"成功?"}
    
    OK -->|"✅"| OUTPUT["PCROutput_v1<br/>完整5阶段输出"]

    OK -->|"❌"| F1["FallbackEngine<br/>Level 1: conservative"]
    
    F1 --> F1OK{"成功?"}
    F1OK -->|"✅"| OUT1["BALANCED默认<br/>expectation=UNKNOWN"]
    F1OK -->|"❌"| F2["Level 2: degraded<br/>跳过Stage 2-4<br/>只做期望识别"]

    F2 --> F2OK{"成功?"}
    F2OK -->|"✅"| OUT2["简化输出<br/>仅 expectation"]
    F2OK -->|"❌"| F3["Level 3: pass_through<br/>全部跳过<br/>BALANCED直接通过"]

    F3 --> OUT3["最小输出<br/>noise=0, complexity=0<br/>execution_mode=BALANCED"]
```

---

## 八、实现状态

```mermaid
graph LR
    subgraph DONE["✅ 已完成"]
        CODE["代码 3500行<br/>9模块"]
        TEST["测试 168/170"]
        DESIGN["设计 17篇"]
    end

    subgraph TODO["❌ 待实现"]
        HOOK["接入 on_event"]
        REG["8链调控映射"]
        TOPO["NoiseSpan拓扑"]
        LIFE["LifecycleManager"]
    end

    DONE --> TODO
```

---

## 九、接入优先级

```mermaid
gantt
    title PCR 接入路线
    dateFormat  YYYY-MM-DD
    section P0 核心
    on_event 接入 PCR.evaluate    :p0, 2026-07-21, 2d
    5条核心调控信号流向链01/02/08   :p0b, after p0, 2d
    section P1 噪声
    NoiseSpan 拓扑替换 noise_level :p1, after p0b, 3d
    6种噪声类型差异化下游处理        :p1b, after p1, 2d
    section P2 生产
    FallbackEngine + 热加载        :p2, after p1b, 2d
    Telemetry 集成                 :p2b, after p2, 1d
```
