# 未实现设计点 —— 前沿方案对标 & 落地路径

> 2026-07-22 · 18 未实现分 5 组

---

## 第一组：Subgraph + Engineering + Cold→Hot 回写（跨链通信）

### 设计
```
Subgraph: 每条链从 EventLog 投射自己的"视角子图"
Engineering: "如果 X 变了, 什么必须跟着变？" 约束传播
Cold→Hot: Meta 审核结果 → Intent 重解析, Assoc 发现 → Context 追加
```

### 对标方案
| 项目 | 对应 | 核心机制 |
|------|------|---------|
| **Materialize** | Subgraph 投射 | 增量物化视图, SQL→持续更新的内存表 |
| **Rete Algorithm** (Drools/CLIPS) | Engineering 约束 | 规则网络, 前向链式推理, 增量匹配 |
| **Datalog/Soufflé** | Engineering 约束 | 声明式约束, 增量计算, 天然支持递归 |
| **Apache Flink** Dynamic Tables | Subgraph | 事件流→动态表, changelog 模式 |

### 落地路径
```
Subgraph = EventLog.tail() → filter + aggregate → SubgraphSnapshot
Engineering = Rete-like constraint network: 文件树→约束图→增量传播
Cold→Hot = Meta/Assoc publish event → EventBus → hot chain subscriber
```
**复杂度**: 中 · **依赖**: EventLog 已有 · **耗时**: 2-3天

---

## 第二组：Topic Tree 分支切换 + 双层摘要

### 设计
```
分支切换: fork(新分支) / merge(合入主枝) / switch(上下文回收) / resume
双层摘要: L1 = 单分支摘要 (DiscourseBlockTree 边界), L2 = 跨分支摘要
```

### 对标方案
| 项目 | 对应 | 核心机制 |
|------|------|---------|
| **Git DAG** | 分支模型 | DAG of commits, branch = ref pointer, merge = join |
| **RAG 摘要技术** (LangChain) | L1 摘要 | Map-Reduce, Refine, 滑动窗口摘要 |
| **GraphRAG** (Microsoft) | L2 摘要 | 社区检测→社区摘要, 跨社区全局摘要 |
| **MemGPT / Letta** | 上下文回收 | 核心记忆+归档记忆, 层级上下文管理 |

### 落地路径
```
分支 = DiscourseBlockTree 的 branch pointer + branch_id
fork = create_branch(from_node)  
merge = merge_branches(branch_a, branch_b) → 冲突标注
switch = 保存当前上下文 → 加载目标分支上下文
resume = 从 checkpoint 恢复 → 注入摘要
L1 摘要 = Map-Reduce over block nodes
L2 摘要 = GraphRAG 社区检测 over branches
```
**复杂度**: 中 · **依赖**: DiscourseBlockTree 已有 · **耗时**: 2天

---

## 第三组：Knowledge Pipeline（博客 v4 五阶段）

### 设计
```
Observation Compiler → Hypothesis Engine → Knowledge → Skill
Event→多域投影  →  7D信念竞争  → 共识冻结  →  能力蓝图
```

### 对标方案
| 项目 | 对应 | 核心机制 |
|------|------|---------|
| **Multi-Agent Debate** (Du et al. 2023) | Hypothesis 竞争 | 多Agent辩论→共识, 投票机制 |
| **CrewAI / AutoGen** | Observation 多域 | 不同role的Agent生成不同视角 |
| **Dempster-Shafer 理论** | 7D信念 | 多证据融合, 冲突处理 |
| **Evidence-Based Reasoning** | Knowledge冻结 | 证据累积→阈值判定→知识固化 |
| **LangChain Skill** | Skill 蓝图 | 可执行能力模板 |

### 落地路径
```
Observation = 已有 observation_compiler/ (22f, 1378行), 需接入 event
Hypothesis = 已有 hypothesis/ (11f, 753行), 需接入 BeliefState
Knowledge = 冻结: support≥3 ∧ conflict≤2 ∧ stability≥0.6
Skill = 已有 planner/skill_engine.py, 需接 Distillation
```
**复杂度**: 高 · **依赖**: observation + hypothesis 代码已有 · **耗时**: 3-5天

---

## 第四组：PCR NoiseSpan + Runtime Paths

### 设计
```
NoiseSpan: 替代 scalar noise_level, 输出 [(start,end,type,severity)]
Slow Path: 50事件/30min → Hypothesis Engine → Knowledge
Deep Path: 5同模式 → Skill Distillation
```

### 落地路径
```
NoiseSpan = StructuralFeatures 基础上加 span 标记
Slow Path = trigger_checkpoint() 已存在, 需接入 Hypothesis
Deep Path = trigger_deep() 框架存在, 需接 Distillation
```
**复杂度**: 低 · **依赖**: 框架已建 · **耗时**: 1-2天

---

## 第五组：ABC + Mind + Soft Config

### 设计
```
ABC: learn_from_feedback() 每轮, 空壳
Mind: 长期心智, Attention/Prediction/Preference/Strategy/Common Mistakes
Soft Config: 全量配置外置, 目前只有 mood_profiles.yaml
```

### 对标方案
| 项目 | 对应 | 核心机制 |
|------|------|---------|
| **Mem0 / MemGPT** | Mind 长期记忆 | 层级记忆, 自动归档, 检索增强 |
| **RLHF 反馈** | ABC | 偏好学习, 奖励模型 |
| **Hydra / OmegaConf** | Soft Config | 结构化配置, 组合覆盖 |

### 落地路径
```
ABC = 接入 EventBus, 消费 REPLY_GENERATED + USER_FEEDBACK
Mind = v3_legacy 中的 Attention/Prediction 模型 → 迁入 agent/mind/
Soft Config = 逐模块迁移 (先从 PCR config 开始)
```
**复杂度**: 中 · **耗时**: 2-3天

---

## 实施优先级

| 优先级 | 组 | 原因 |
|:---:|------|------|
| **P0** | 第二组 Topic Tree | 代码已有 70%, 缺最后 30% |
| **P0** | 第四组 NoiseSpan | 设计完整, 框架已有, 最快 |
| **P1** | 第一组 Subgraph+Engineering | 跨链通信基础设施 |
| **P1** | 第五组 ABC+Mind+Config | 反馈闭环 |
| **P2** | 第三组 Knowledge Pipeline | 最大工作量, 代码已有, 需接入 |
