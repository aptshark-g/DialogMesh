# DialogMesh v6 — 设计全貌合成 (从13篇核心设计提取)

> 2026-07-24 · 读完: 10条BLINE链设计 + 3条v5专项设计 + HYBRID_ARCHITECTURE + INFO_THEORETIC_COMPRESSION

---

## 一、核心公式

```
Agent = 编排系统(Everything is Behavior)

不是: Agent = LLM + 上下文 + 工具  (这是LLM视角)
而是: Agent = 行为网络                    (这是系统视角)

每个操作 = 一次行为(Behavior)
  LLM → call(规则)    = 行为
  规则 → trigger(LLM)   = 行为
  用户 → edit(节点)     = 行为
  算法 → notify(LLM)    = 行为
```

## 二、10条链 × 双速通道

每条链独立消费事件、独立决策——不是线性管道。

| 链 | 快路径(<10ms) | 慢路径(LLM) | 决策门控 |
|----|--------------|-------------|----------|
| 00 PCR | 结构特征(S/V/O/问号数) | LLM分类 | conf<0.6→LLM |
| 01 对话树 | LCseg+BM25 | LLM块分割 | cohesion |
| 02 上下文 | DomainSelector+BudgetAllocator | LLM压缩 | token预算 |
| 03 意图 | Tier0结构+Tier1 BGE/SVO | Tier2 LLM few-shot | conf<0.6→LLM |
| 04 元认知持久 | EventLog追加 | Snapshot+Replay | — |
| 05 行为 | 贝叶斯+频率 | LLM推理 | conf 0.4-0.7→LLM |
| 06 关联 | L1句法+L1.5补全 | L2-L5 LLM | 每层可选LLM |
| 07 工程 | tree-sitter解析 | 约束推理 | 约束匹配 |
| 08 画像 | TrackA(动力学)+TrackB(标签) | LLM分析师 | 漂移>阈值→LLM |
| 09 元认知 | 规则触发器(7条) | LLM审查+回顾 | 冷却期控制 |
| 10 子图 | 对话树子图(窄深) | 元认知子图(宽浅) | 双视角 |

## 三、统一的共享数据层

所有链读同一数据池，不同视角解释：

```
共享数据层:
  对话树     ← 链01写入, 链02/03/05/06/10读取
  行为链     ← 链05写入, 链06/08/09/10读取
  关联链     ← 链06写入, 链03/05/09/10读取
  工程链     ← 链07写入, 链10读取
  用户画像   ← 链08写入, 链00/02/03/05读取
  元认知日志 ← 链09写入, 链08/10读取
  版本控制   ← 链09写入, 全部读取
```

## 四、蓝图系统——编排器的核心

```
蓝图 = 约束模板 (不是固定流程)

Blueprint {
  "max_llm_calls": 3,
  "min_confidence": 0.7,
  "hot_path_first": true,
  "allowed_callers": ["LLM", "user"],
  "fallback": "blueprint_3"
}

5种预定义蓝图:
  蓝图1: 规则直连 (0次LLM)       — 会员号查询、简单事实
  蓝图2: LLM+规则协同 (1次LLM)    — 意图分类、实体消歧
  蓝图3: LLM多步推理 (2-5次LLM)   — 复杂分解、多意图
  蓝图4: 联邦并行 (多次LLM并行)   — 跨域检索、多视角决策
  蓝图5: 用户交互 (LLM暂停)       — 歧义消解、关键决策
```

## 五、子图——跨链通信织物

```
子图 = 相同数据池 × 不同视角 × 不同预算分配

对话树子图 (生成回复):
  D域(对话):40% + B域(行为):15% + A域(关联):25% + P域(画像):10% + E域(工程):10%

元认知子图 (审核):
  M域(操作历史):15% + V域(版本diff):25% + E域(多链证据):30% + I域(惯性):15% + P域(画像):10% + Q域(问题):5%

子图编译器:
  compile_dialogue() → 对话视角 → LLM回复
  compile_meta()     → 元认知视角 → LLM审核
```

## 六、状态机——Decider模式

```
Command → Decider → Event → State → evolve → 下一Tick

不是: 链间直接push (广播风暴)
而是: Decider串行化 → Tick 1(PCR) → Tick 2(Intent) → Tick 3(Plan) → ...
```

## 七、信息论内核

```
温度(时间轴) ⟂ 距离(空间轴) ⟂ 信息价值(稀缺轴)

压缩 ≠ 聚类:
  聚类 ❌: BGE聚类→主题群→摘要 → 丢失因果推导链
  推导 ✅: 状态转移(a→b→c)→规则归纳→可逆推
  
同一信号, 不同约束 → 相反结论:
  卡尔曼滤波: 低概率=低权重 (追求准确性)
  信息论:     低概率=高价值 (追求信息量)
```

## 八、Agent-Native设计对标

| 范式 | 来源 | DialogMesh应用 |
|------|------|----------------|
| ReAct | Yao 2022 | 拆分→验证→修正循环 |
| Plan-Execute | Wang 2023 | 意图拆分=Plan阶段 |
| Reflexion | Shinn 2023 | 分歧→收敛=Reflexion |
| Multi-Agent Debate | Du 2023 | 5链=5个LLM视角 |
| Tool-Augmented | OpenAI/Anthropic | LLM是协调者,工具是执行者 |

## 九、关键发现：设计一致性

从13篇设计文档提取的共性规律：

1. **每条链都独立** — 不依赖其他链的完成，只读共享数据
2. **决策门控统一** — conf<0.6进入LLM, conf<0.3询问用户
3. **子图是核心抽象** — 共享数据×视角×预算=子图
4. **蓝图是编排中枢** — 预设约束模板, LLM在约束内操作
5. **状态转移>当前状态** — 元认知分析Transition, 不是分析State
6. **双速通道贯穿全部** — 不是"LLM-first"或"规则优先", 是"根据置信度路由"

---

> 待读: 105篇 v3.0设计, 6篇 merge归档, ~80篇其他
> 以上从已读的13篇核心设计提取
