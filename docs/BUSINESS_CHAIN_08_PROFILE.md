# DialogMesh v6 — 业务链设计 · 第八章：Profile (认知画像)

> 版本: v1.0 | 日期: 2026-07-21
> 接入: ExecutionTraceV3 ✅ · OCEAN Analyst ✅ · TrackB TagLayer ❌ · PCR 信号 ❌

---

## 一、Profile 在 10 链中的位置

```mermaid
graph TD
    PCR["PCR · cognitive_profile (快速)"]
    LLM["LLM 回复"]
    USER["用户反馈"]

    subgraph PROFILE["链08: Cognitive Profile"]
        direction TB
        TRACE["ExecutionTraceV3<br/>STRENGTHEN/WEAKEN/REJECT"]
        TRACKA["Track A · 认知动力学<br/>inertia/cog_resource/attention/emotion/self_value/expectation_bias"]
        TRACKB["Track B · 标签层<br/>tag_layer.infer_from_trace()"]
        OCEAN["OCEAN 映射<br/>BFI-10 支撑"]
        CONV["ConvergenceEngine<br/>收敛系数推算"]
        STORE["ProfileStore<br/>持久化"]
    end

    PCR -->|"快速评估→EMA 注入"| TRACKA
    LLM -->|"回复质量→ExecutionTrace"| TRACE
    USER -->|"反馈→STRENGTHEN/WEAKEN"| TRACE

    TRACE --> TRACKA
    TRACE --> TRACKB
    TRACKA --> OCEAN
    TRACKB --> OCEAN
    TRACKA --> CONV
    OCEAN --> STORE

    PROFILE -->|"OCEAN10维"| BEHAVIOR["链05 行为链<br/>画像偏置"]
    PROFILE -->|"标签"| LLM2["链02 LLM<br/>风格调控"]
```

---

## 二、双 Track 架构

```mermaid
graph TD
    subgraph TRACK_A["Track A: 认知动力学 (7维 EMA)"]
        A1["inertia         · 认知惯性"]
        A2["cog_resource     · 认知资源"]
        A3["attention_anchor · 注意力锚点"]
        A4["emotion_entropy  · 情绪熵"]
        A5["self_value      · 自我价值"]
        A6["expectation_bias · 期望偏差"]
        A7["convergence_alpha · 收敛系数"]
    end

    subgraph TRACK_B["Track B: 标签化信息"]
        B1["personality_trait   · 人格特质 · INTJ/INFJ/..."]
        B2["domain_expertise    · 领域专长"]
        B3["communication_style · 沟通风格 · CS=0.78"]
        B4["temporal_context    · 时间上下文"]
    end

    TRACE["ExecutionTrace<br/>STRENGTHEN/WEAKEN/REJECT"] --> TRACK_A
    TRACE --> TRACK_B
```

**实现**: `v4/state/execution_trace.py` (131行) · `v4/cognitive/tag_layer.py` · `v4/cognitive/ocean_profile.py`

---

## 三、ExecutionTrace → Profile 信号流

```mermaid
graph TD
    EVENT["on_event 每次对话"]

    EVENT --> PRE["pre_state snapshot()"]
    EVENT --> RECORD["record_transition(pre, post, metrics)"]

    RECORD -->|"latency<2s + success"| STRENGTHEN["STRENGTHEN<br/>信任↑ · inertia↑"]
    RECORD -->|"latency>10s or fail"| WEAKEN["WEAKEN<br/>信任↓"]

    EVENT --> REJECT_DETECT["REJECT: 用户输入含否定词<br/>'不对'/'错了'/'不是这样'"]
    REJECT_DETECT --> REJECT["REJECT<br/>触发标签重新评估"]

    STRENGTHEN --> TRACKA["TrackA<br/>EMA(t) = 0.3·S + 0.7·EMA(t-1)"]
    WEAKEN --> TRACKA
    REJECT --> TRACKB["TrackB<br/>LLM 1-shot 标签再分析"]
```

---

## 四、接入 Engine 现状

```
✅ ExecutionTraceV3      — pre/post snapshot + record_transition
✅ PCR → TrackA EMA       — _call_llm 后调用 (本轮已接,信号在)
✅ OCEAN Analyst 初始化    — lazy init
✅ ProfileStore           — 持久化

⚠️ TrackB infer_from_trace — 代码完整未调用
⚠️ REJECT 检测             — 只检测了部分否定词
❌ OCEAN → Behavioral     — 画像→行为链偏置 未接
❌ ConvergenceEngine      — 收敛系数推算 未调用
```

---

## 五、接入计划

```python
# engine.on_event() — after LLM call
if self._cognitive_profile and pcr_output:
    self._update_profile_from_trace(pcr_output, llm_response)

def _update_profile_from_trace(self, pcr, response):
    # TrackA: PCR fast profile → EMA
    if pcr.cognitive_profile:
        alpha = 0.3
        self._cognitive_profile.track_a.cog_resource = (
            alpha * pcr.cognitive_profile.cognitive_level +
            0.7 * self._cognitive_profile.track_a.cog_resource
        )
    
    # TrackB: infer tags from ExecutionTrace
    if self._tag_layer:
        self._tag_layer.infer_from_trace(self._trace_v3, self._cognitive_profile)
    
    # OCEAN mapping
    if self._ocean_analyst:
        self._ocean_analyst.update(self._cognitive_profile)
    
    # Convergence
    if self._convergence_engine:
        self._convergence_engine.update(self._cognitive_profile.track_a)
```

**有效实现率: ~50% → 待接入约 20 行**
