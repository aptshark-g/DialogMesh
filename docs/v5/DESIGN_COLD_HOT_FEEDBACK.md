# DialogMesh — Cold→Hot 三层回写设计

> 2026-07-24 · 非修正原则: 多面决策，不是对错判断

---

## 一、核心哲学

```
传统 React: 请求 → 尝试 → 判断对错 → 不对就重来 → 对了才给出
             ├── 阻断当前回答 ──┤

DialogMesh: 请求 → 多视角竞争 → 给最优回答 → Meta异步审视 → 修正未来
            ├── 用户立即得到回答 ─[不阻断]──┤ ├── 学习式演进 ──┤

关键:
  - 不阻断: Meta修正不影响当前已给出的回答
  - 不二值: 不是"对/错"，是"置信度在哪个区间"
  - 学习式: 修正不是重试，是调整下次Tick的参数
```

## 二、三层通道

### Layer 1 — 确定信号 → 同步修正 ✅ 直接施工

```
触发条件: hallucination >0.7 | bias >0.8 | confidence <0.1
动作: 附加 CorrectionMark 到结果、不覆盖已给用户的回答
数据流:
  MetaDecision  →  agent_native 消费  →  result["correction"] = {...}
  下次 Tick → Observe 的 PCR 被告知"上次可能出错"
```

### Layer 2 — 证据积累 → 异步裁决 ✅ 直接施工 (CognitionHub已有)

```
触发条件: confidence 0.3-0.6 | MultiPerspective 分歧
动作: Belief Accumulator 积累 → 跨Tick证据收敛 →
      达到阈值 → 触发行动(自动修正/询问用户/LLM选择)
数据流:
  CognitionHub.converge() → active_beliefs → 
  置信度突破阈值 → 触发action
  置信度不足 → 维持累积 → 下次Tick继续收敛
```

### Layer 3 — 模式漂移 → 参数调整 ✅ 直接施工

```
触发条件: OCEAN 惯性变化 >0.15 | BehaviorPattern 持续异常
动作: 不直接修正 → 调整 Blueprint 参数 →
      OCEAN 权重微调 | ε-greedy ε调整 | 蓝图选择偏置
数据流:
  Dynamics.tick() → drift_detected → 
  CorrectionJournal.record() → 
  BlueprintSelector.adapt() → 下次Tick生效
```

## 三、数据契约

```python
MetaDecision = {
    "tick": int,           # 产生决策的 Tick 号
    "confidence": float,   # 决策置信度
    
    # Layer 1 fields
    "urgent_correction": {     # 仅在高置信+高风险时非空
        "type": "hallucination | bias | intent_misparse",
        "severity": float,
        "suggested_action": str,
        "evidence": [...],
    },
    
    # Layer 2 fields
    "belief_update": {          # 累积后的信念修正
        "intent_id": str,
        "old_confidence": float,
        "new_confidence": float,
        "evidence_chain": [...],
        "action": "auto_correct | ask_user | llm_decide",
    },
    
    # Layer 3 fields
    "parameter_shift": {        # 权重微调, 不紧急
        "target": "ocean | epsilon | blueprint",
        "direction": float,
        "magnitude": float,
        "reason": str,
    },
}

ColdToHotResult = {
    "correction": MetaDecision | None,   # Layer 1 产出
    "belief": dict | None,               # Layer 2 产出
    "drift": dict | None,                # Layer 3 产出
}
```

## 四、通道实现

### Layer 1 — agent_native 消费

```python
# Meta 异步产出 MetaDecision → 写入 State
# agent_native 在下一 Tick 的 Observe 阶段检查
if state.pending_correction:
    pcr_input.override(state.pending_correction)
    state.pending_correction = None
```

### Layer 2 — CognitionHub 积累

```python
# 每 Tick: converge() 累积证据
# 达到阈值 → 注入 action 到 result
# 阈值不足 → 保持累积, 下 Tick 继续
cog_result = cognition_hub.converge()
if cog_result["action"]:
    result["cognition_action"] = cog_result["action"]
```

### Layer 3 — BlueprintSelector 适配

```python
# Meta 异步产出 parameter_shift → 调整 BlueprintSelector 权重
if decision.parameter_shift:
    BlueprintSelector.adjust(decision.parameter_shift)
```

## 五、现有代码基础

```
✅ MetaSubscriber       — 订阅8种事件, 每5 Tick 审核 (63L)
✅ MetaCognition        — 审查+回顾+自审 (328L, bridge wired)
✅ CognitionHub         — Hypothesis+Belief+Cluster (120L, 刚建成)
✅ CorrectionJournal    — 用户修正+漂移 (156L, bridge wired)
✅ Dynamics             — 惯性/注意力/情绪计算 (172L, bridge wired)

⚪ 缺: MetaDecision 生产 → agent_native 消费的产消合同
⚪ 缺: BlueprintSelector.adjust() (等待Blueprint系统)
```
