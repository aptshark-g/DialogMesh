# Agent-Native Multi-Intent Architecture — Frontier Design Patterns

> 2026-07-24 · 对标前沿 agent 设计, LLM 为中心的协同架构

---

## 一、前沿 Agent 设计范式

### 1.1 ReAct (Reasoning + Acting) — Yao 2022 ⭐⭐⭐

```
Thought → Action → Observation → Thought → Action → ...

核心: LLM 交替推理和行动, 观察环境反馈后调整
适用: 工具调用、多意图分解
```

**对标我们**: 拆分器应该是 ReAct 循环的一部分——LLM 推理"是否多意图"→行动"拆分"→观察"链验证"→推理"是否修正"。

### 1.2 Plan-and-Execute — Wang 2023 ⭐⭐

```
LLM 先做全局计划 → 逐步执行计划 → 执行失败时重规划
```

**对标我们**: 意图拆分 = Plan 阶段。LLM 先识别所有子意图(计划), 然后逐条执行。

### 1.3 Reflexion — Shinn 2023 ⭐⭐

```
执行 → 失败 → LLM 反思失败原因 → 改进策略 → 重新执行
```

**对标我们**: 分歧→收敛的模式就是 Reflexion。链验证不通过 → LLM 反思 → 修正拆分。

### 1.4 Multi-Agent Debate — Du 2023 ⭐⭐

```
多个 LLM 实例各自推理 → 汇总辩论 → 达成共识
```

**对标我们**: 五条链 = 五个视角的 LLM 实例。并行推理后融合。不是简单投票——是 each LLM reasons independently, then converges。

### 1.5 Tool-Augmented LLM (Anthropic/OpenAI) ⭐⭐⭐

```
LLM 决定何时调用工具、调用哪个工具、如何解释结果
核心理念: LLM 是协调者, 工具只是执行者
```

**对标我们**: 意图拆分器是 LLM 的工具链。LLM 决定"要不要拆分", Stnaza 只提供结构提示——不是决策者。

---

## 二、我们的架构映射

```
                   ┌─────────────┐
    用户输入 ──────→│   LLM       │← ReAct 循环的核心
                   │  (协调者)    │
                   └──┬──┬──┬──┬─┘
                      │  │  │  │
          ┌───────────┼──┼──┼──┼───────────┐
          │   Tool-Augmented LLM           │
          │                                │
          │  ┌─ Stanza (结构提示)           │
          │  ├─ Profile (画像上下文)         │
          │  ├─ Association (关联链证据)     │
          │  ├─ Discourse (对话历史)         │
          │  └─ Engineering (环境约束)       │
          │                                │
          │  工具只是提供数据——LLM 做决策     │
          └────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │  Multi-Agent Debate   │
          │  (五链并行推理)        │
          │  Profile LLM debates  │
          │  Association LLM      │
          │  Discourse LLM        │
          │  Literal LLM          │
          │  Engineering LLM      │
          └───────────┬───────────┘
                      │
          ┌───────────┴───────────┐
          │  Reflexion (收敛)     │
          │  分歧 → LLM 反思      │
          │  → 修正拆分 → 重验证  │
          └───────────────────────┘
```

---

## 三、关键设计原则

### 3.1 LLM 是协调者, 不是工具

❌ 错误: 算法预判 → LLM 确认
✅ 正确: LLM 决定 → 工具提供数据 → LLM 修正

### 3.2 每一条链 = 一个 LLM 视角

不是简单的特征提取——每个链是 LLM 从特定视角的推理:

```
Literal LLM:     "从句法结构看, 这句话包含两个独立动作..."
Profile LLM:     "从用户画像看, 高C用户倾向于结构化拆分..."
Association LLM: "从关联链看, 这两个实体不在同一关系簇中..."
Discourse LLM:   "从对话历史看, 上一个话题已经切换..."
```

### 3.3 Reflexion 是收敛机制

当五链分歧时:
1. LLM 看到所有链的推理
2. LLM 反思: "为什么关联链 reject 但字面链 accept?"
3. LLM 修正拆分方案
4. 重新验证
5. 达到共识 or 降级为 ask_user

### 3.4 ReAct 循环贯穿整个流程

```
Thought: "这句话可能有多个意图"
Action: 调用字面链 → 返回 2 个子句
Observation: 画像链 accept, 关联链 reject
Thought: "关联链 reject 是因为实体在同一个簇中"
Action: 调整拆分为单意图
Observation: 所有链 accept
→ 最终输出
```

---

## 四、与现有方案对比

| | 我们的方案 | 规则式 agent | 纯 LLM agent |
|---|---|---|---|
| 多意图检测 | LLM 决定 + 工具辅助 | 关键词/正则 | LLM 推理 |
| 准确性 | 高 (多视角验证) | 低 (无法泛化) | 中 (单视角) |
| 延迟 | 中 (并行 LLM 调用) | 低 | 低 |
| 可解释性 | 高 (每链输出 reasoning) | 高 | 低 |
| 泛化 | ✅ LLM 自然泛化 | ❌ 硬编码 | ✅ |
| 纠错 | ✅ Reflexion 循环 | ❌ | ❌ |

---

## 五、实施路线 (Agent-Native)

```
Phase 1: ✅ Literal LLM chain (ReAct 循环基础)
Phase 2:    Profile + Association + Discourse LLM chains (Multi-Agent Debate)
Phase 3:    Fusion with Reflexion (LLM 反思收敛)
Phase 4:    Tool-augmented context injection (Stanza/Profile/Substrate as tools)
Phase 5:    Full ReAct loop integration into engine
```
