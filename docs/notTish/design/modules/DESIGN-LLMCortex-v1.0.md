# Literature Cortex — LLMCortex 多层 LLM 协同架构设计

> 版本: v1.0
> 日期: 2026-06-23
> 作者: 合作 + 用户洞察驱动

---

## 一、核心洞察

### 1.1 问题

当前系统（A/B 阶段）存在根本性缺陷：

- **LLM 被当作模糊语义的 if-else**：给 LLM 一个 prompt，期待它"聪明地"做决策。
- **LLM 未被分层**：所有 LLM 调用混在一起，没有远近迁移、自由反思的区分。
- **claw 代码被盲目信任**：硬约束代码被当作绝对正确，没有质疑层。
- **缺少统筹协调**：各层 LLM 输出之间没有整合，没有最终拍板。

### 1.2 用户洞察

> LLM 本身是统计概率的算法。要通过准确的算法去协调控制 LLM，防止出问题。LLM 不是 if-else，而是需要精确接口约束的知识引擎。
>
> — 用户，2026-06-22

这个洞察推翻了"LLM 做单层精确契约"的设计，提出了**多层 LLM 架构**：

| 迁移类型 | 特征 | 适用 LLM 层级 |
|---|---|---|
| 近迁移 | 贴着形式化约束，精确映射 | Layer 1 |
| 远迁移 | 读持久化层，自由联想 | Layer 2 |
| 自由反思 | 纯发散，无硬约束 | Layer 3 |
| 质疑 | 质疑硬约束代码的输出 | Layer 0 |
| 协调 | 统筹各层，最终拍板 | Layer 4 |

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMCortex 引擎                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Coordination 协调层                                │
│  ├─ 算力分配回顾                                             │
│  ├─ 各层置信度加权整合                                        │
│  └─ 最终拍板: pass / warning / reject / 回退                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Free Reflect 自由反思层                             │
│  ├─ 反事实假设 ("如果公理4不成立？")                          │
│  ├─ 深层质疑 ("这个体系真的自洽吗？")                         │
│  └─ 创造性洞察 ("与混沌边缘理论的隐性关联")                    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Far Transfer 远迁移层                               │
│  ├─ 读持久化层 (graph.db 历史系统)                            │
│  ├─ 深层跨域联想 (非显而易见的类比)                            │
│  └─ 新颖度评估                                               │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Near Transfer 近迁移层                              │
│  ├─ 贴着形式化约束做精确映射                                   │
│  ├─ 维度一一对比 (源域 vs 目标域)                             │
│  └─ 同构/同态/类比判定                                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Challenge 质疑层                                    │
│  ├─ 质疑 claw 输出质量 (遗漏？误判？)                         │
│  ├─ 质疑演绎链条完整性                                        │
│  └─ 质疑形式化定义一致性                                      │
├─────────────────────────────────────────────────────────────┤
│  输入: claw Pipeline 输出 (P1-P7 结构化数据)                    │
│  持久化: graph.db 历史系统 (Layer 2 读取)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、各层详细设计

### 3.1 Layer 0: Challenge 质疑层

**定位**：claw 不是绝对正确。正则提取、图计算、同构判定都可能出错。Challenge 层是第一道防线。

**输入**：claw Pipeline 全部产出（entities, relations, constraints, scores）

**任务**：
1. 检查实体提取是否遗漏关键概念
2. 检查关系网络是否有逻辑断裂
3. 检查层级分类是否合理
4. 检查形式化定义是否一致

**输出**：
```json
{
  "issues": [
    {
      "severity": "critical|warning|minor",
      "type": "遗漏|错误|逻辑断裂|不一致",
      "location": "P1|P2|P3|P4",
      "description": "...",
      "suggested_fix": "..."
    }
  ],
  "overall_assessment": "..."
}
```

**判定规则**：
- `critical` > 2 → verdict = reject，Pipeline 回退或终止
- `critical` = 1-2 → verdict = warning，继续但标记风险
- 无 critical → verdict = pass

**温度**：0.1（最严格，最少自由发挥）

---

### 3.2 Layer 1: Near Transfer 近迁移层

**定位**：贴着形式化约束做精确映射。不是"我觉得像"，而是"这个维度在数学上等价"。

**输入**：
- 源域的形式化定义（如认知惯性的 C_inertia 公式）
- 源域的约束条件（如 C_max ≥ C_inertia）
- 目标域的形式化定义（如控制系统的 J = ∫(u² + xᵀQx)dt）
- 目标域的约束条件（如 Q ≥ 0, R > 0）

**任务**：
1. 逐维度对比（变量、约束、优化目标）
2. 判定映射类型：同构 / 同态 / 类比
3. 给出置信度和数学依据

**输出**：
```json
{
  "mappings": [
    {
      "source_dimension": "惯性成本 C_inertia",
      "target_dimension": "状态切换代价 J",
      "mapping_type": "同构|同态|类比",
      "confidence": 0.85,
      "justification": "两者都是标量代价函数，满足非负性，优化目标均为最小化"
    }
  ],
  "unmappable": [
    {
      "dimension": "自我否认代价",
      "reason": "控制系统无主观认知维度，无法映射"
    }
  ]
}
```

**判定规则**：
- 平均置信度 > 0.7 → pass
- 平均置信度 0.5-0.7 → warning（需要远迁移层补充）
- 平均置信度 < 0.5 → reject（映射不成立）

**温度**：0.2（严格，需要精确推理）

---

### 3.3 Layer 2: Far Transfer 远迁移层

**定位**：不贴形式化约束，而是从持久化层读取历史数据，做深层跨域联想。

**输入**：
- 当前体系的结构签名（SGF graph_id, 节点类型分布）
- 持久化层历史系统（graph.db 中存储的过往分析结果）
- Layer 1 的近迁移输出（哪些维度已映射，哪些未映射）

**任务**：
1. 在历史系统中寻找结构相似的体系
2. 对 Layer 1 未映射的维度，尝试从其他领域找到类比
3. 评估类比的新颖度（是否之前从未被发现）

**输出**：
```json
{
  "analogies": [
    {
      "target_system": "热力学第二定律",
      "similarity_dimension": "动力学行为",
      "reasoning": "两者都涉及不可逆过程的能量耗散。认知惯性成本可类比熵增。",
      "novelty": 0.8,
      "historical_precedent": "无" // 或引用持久化层中的历史记录
    }
  ]
}
```

**判定规则**：
- 有 analogy 且 novelty > 0.5 → pass（有价值的新联想）
- 有 analogy 但 novelty < 0.5 → warning（可能是已知类比）
- 无 analogy → warning（远迁移失败）

**温度**：0.4（需要一定开放性，但不能太发散）

**持久化层读取**：
```sql
-- Layer 2 查询 graph.db
SELECT graph_id, title, type, structure_template 
FROM nodes 
WHERE type IN ('meta_control', 'paper') 
ORDER BY created_at DESC 
LIMIT 50;
```

---

### 3.4 Layer 3: Free Reflect 自由反思层

**定位**：纯发散。没有硬约束，没有必须输出的格式。这是 LLM 最像"人"的一层。

**输入**：
- 当前体系的所有公理、定理
- 前面三层（Challenge, Near, Far）的输出
- 用户的原始文本

**任务**：
1. 反事实假设："如果某条公理不成立？"
2. 深层质疑："这个体系是否有隐藏的循环论证？"
3. 创造性洞察："这个体系与某个看似无关的领域的深层联系"

**输出**：
```json
{
  "hypotheses": [
    {
      "type": "反事实|深层联系|创造性",
      "content": "如果惯性成本为负，系统会自发寻求变化，这与混沌边缘理论一致",
      "impact": "high|medium|low",
      "testability": "可验证|不可验证"
    }
  ],
  "contradictions_found": [
    {
      "between": ["公理2", "定理7"],
      "description": "公理2假设情绪稀缺度与情绪单调度正相关，但定理7的负向循环似乎暗示反比关系"
    }
  ]
}
```

**判定规则**：
- 不 reject。自由反思的输出不用于终止 Pipeline，只用于丰富报告。
- `high` impact 假设 > 2 → 增加协调层的权重
- `contradictions_found` > 0 → 回流 Challenge 层重新审查

**温度**：0.7（最自由，允许发散）

---

### 3.5 Layer 4: Coordination 协调层

**定位**：不是简单的加权平均，而是基于各层特征做差异化整合。

**输入**：
- Layer 0-3 的全部输出
- 各层的置信度、verdict、reasoning

**任务**：
1. 根据各层 verdict 决定 Pipeline 命运
2. 根据各层置信度分配最终权重
3. 生成 action items

**整合规则**：
```python
def coordinate(layers):
    # Layer 0 有一票否决权
    if layers[0].verdict == "reject":
        return "reject", ["回退P1重提取"]
    
    # Layer 1 是核心质量指标
    near_conf = layers[1].confidence
    
    # Layer 2 的权重取决于新颖度
    far_weight = layers[2].metadata.get("novelty", 0.5)
    
    # Layer 3 的权重取决于高影响假设数量
    reflect_weight = sum(1 for h in layers[3].suggestions if h.get("impact") == "high") * 0.1
    
    overall = near_conf * 0.5 + far_weight * 0.3 + reflect_weight * 0.2
    
    if overall > 0.8:
        return "pass", []
    elif overall > 0.5:
        return "warning", ["增加验证", "补充实验数据"]
    else:
        return "reject", ["回退P4发散层", "重新设计约束条件"]
```

**输出**：
```json
{
  "overall_quality": 0.72,
  "final_verdict": "warning",
  "layer_weights": {
    "challenge": 0.25,
    "near_transfer": 0.35,
    "far_transfer": 0.25,
    "free_reflect": 0.15
  },
  "actions": ["增加远迁移验证", "检查定理7与公理2的一致性"]
}
```

**温度**：0.2（需要收敛到明确决策）

---

## 四、数据流

```
┌──────────────┐
│  claw Pipeline │
│  (P1-P7)       │
└──────┬─────────┘
       │ 结构化输出
       ▼
┌──────────────────────────────────────┐
│  Layer 0: Challenge                   │
│  "claw 有没有错？"                     │
└──────┬───────────────────────────────┘
       │ reject → 终止/回退
       │ pass/warning → 继续
       ▼
┌──────────────────────────────────────┐
│  Layer 1: Near Transfer               │
│  "贴着约束做精确映射"                   │
└──────┬───────────────────────────────┘
       │ confidence < 0.5 → 需要 L2 补充
       │ confidence >= 0.7 → L2 可减少 token
       ▼
┌──────────────────────────────────────┐
│  Layer 2: Far Transfer                │
│  "读持久化层，自由联想"                 │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Layer 3: Free Reflect                │
│  "纯粹发想，无约束"                     │
└──────┬───────────────────────────────┘
       │ contradictions → 回流 L0
       │ high impact → 增加 L4 权重
       ▼
┌──────────────────────────────────────┐
│  Layer 4: Coordination                │
│  "拍板"                               │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  最终报告 (JSON + Markdown)            │
└──────────────────────────────────────┘
```

---

## 五、与 Pipeline 的集成点

### 5.1 集成位置

LLMCortex 不替换 Pipeline 的任何阶段，而是**在 Pipeline 外部做增强分析**。

```
Pipeline P1-P7 ──→ 生成结构化报告 ──→ LLMCortex 分析
                                          ↓
                                   质疑 / 映射 / 反思 / 拍板
                                          ↓
                                   回流修改建议（可选）
```

### 5.2 回流机制

Layer 0 或 Layer 4 发现严重问题时，可以生成"修改建议"回流到 Pipeline：

```json
{
  "feedback": {
    "target_phase": "P1_DeepTransform",
    "issue": "定理13缺少演绎依据",
    "suggested_action": "在提取规则中增加对【演绎依据】标记的强制检查"
  }
}
```

注意：回流是**建议性**的，不是自动执行的。需要用户确认。

---

## 六、LLM 后端

### 6.1 支持的后端

| 后端 | 用途 | 配置 |
|---|---|---|
| Kimi Code API | 主后端 | `KIMI_API_KEY` + `https://api.kimi.com/coding/v1` |
| Moonshot API | 备选 | `https://api.moonshot.cn/v1` |
| Mock Backend | 无 key 时测试 | 预定义响应 |
| 用户对话层 | 特殊场景 | 用户作为 LLM 介入 |

### 6.2 调用策略

- **L0 Challenge**：temperature=0.1，max_tokens=500（严格、简短）
- **L1 Near**：temperature=0.2，max_tokens=800（精确、结构化）
- **L2 Far**：temperature=0.4，max_tokens=1000（联想、适度开放）
- **L3 Reflect**：temperature=0.7，max_tokens=1200（自由、发散）
- **L4 Coord**：temperature=0.2，max_tokens=500（收敛、决策）

---

## 七、待决策项

| 问题 | 选项 | 建议 |
|---|---|---|
| L0 的 reject 是否自动终止 Pipeline？ | A: 是（全自动）<br>B: 否（用户确认） | B：质疑层是建议，最终决策权在用户 |
| L3 的 contradictions 是否自动回流 L0？ | A: 是<br>B: 否，仅标记 | A：矛盾发现应触发重新审查 |
| Layer 2 读取持久化层的方式 | A: 直接 SQL<br>B: 通过 GraphStore API | B：保持抽象，不直接依赖 schema |
| 协调层权重是否可配置？ | A: 固定算法<br>B: 用户可调 | B：不同场景需要不同权重 |

---

## 八、版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1 | 2026-06-22 | 单层 LLM 精确契约设计（已废弃） |
| v1.0 | 2026-06-23 | 多层 LLM 架构（用户洞察驱动） |

---

## 九、下一步

1. **确认本设计** → 用户 review
2. **接入 Pipeline** → 在 P7 之后调用 LLMCortex
3. **接入真实 LLM** → 等 Kimi Code key
4. **接入持久化层** → Layer 2 读取 graph.db
