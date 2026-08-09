# 行为链改造准备 — 三块依据汇总（2026-08-01）

> 目的: 行为链改造前的讨论锚点——设计全貌 + 代码审计 + 外部方案三块依据
> 配套: BEHAVIOR_CHAIN_DIGEST（通读摘要）/ BEHAVIOR_DEEP_INVESTIGATION（深度审计）/ BEHAVIOR_RESEARCH_SURVEY（文献调研）
> 结论先行: 行为链"记录面"已接线（v4 adapter），"大脑"（预测+奖励+训练闭环）未接线（V32Pipeline 断链）；显式承诺零现状；三块外部方案齐备，可开始设计

---

## 一、三块依据

### 1.1 设计文档全貌（11/11 已读）

- **行为链 = 预测引擎**（BC05）：四层决策树（成本/风险/冷启动/CI）+ ε-greedy + 信息增益奖励
- **在线训练闭环**（BEHAVIOR_SUMMARY §5）：预测→验证→修正→回流；ADR-013 预测不参与当前轮决策
- **发现→审核→吸收**（SUPPLEMENT）：统计发现零 LLM + 元认知审核 + 关联链双向
- **LLM 协同**（LLM_COLLABORATIVE）：漂移解释 + 异常发现 + DPO 偏好学习
- **参数三层范式**（ALGORITHM §0）：文献锚点/安全区间/语义对齐自适应
- **思想源头**（THOUGHT_IMPRINT + LITERATURE_CORTEX）：纠错即训练、二合一架构、因果是约束投射

### 1.2 代码审计（26 文件全读 + 测试 + import 实测）

**已接线（v4 记录面）**:
- `behavior/` 13 文件全实现；adapter 8/8 测试通过
- v4 主链路（runtime/engine + cli/engine + v4/behavior_graph 门面）用 adapter/causal/runtime_hook/llm_collaborative

**未接线（v4 大脑）**:
- `BehaviorPredictor/BehaviorRewarder/TrainingFeedbackLoop` 唯一调用方 = `integration.py`（V32Pipeline）
- **V32Pipeline 断链实证**：import `behavior_graph.*` → ModuleNotFoundError（P0）；`__init__.py` try/except 吞掉 → AgentPipeline=None 静默

**设计-代码差距**:
- BC05 四层决策树（成本/风险/冷启动/CI）未落地——只有四模式回退
- predictor 四维权重硬编码（0.4/0.3/0.2/0.1）——A18 未接入
- ValueRanker 未传 load_est/prof_matcher——认知负载/画像两维度恒 0
- 候选 prompt 写死"系统管理员/开发者"
- predictor/rewarder 零专属测试

### 1.3 外部方案（文献 + 项目调研）

- **PRINCIPLES（2509.17459）**：合成策略记忆 = 显式承诺的学术化身（when→should+rather_than+because）；回退重模拟 = 冷启动模拟升级；免训练 = ADR-014
- **ProactiveEval（2508.20973）**：显式承诺评测模板（environment={user_info, trigger_factor} → LLM-as-judge score+reason）
- **MUST（ACL23）**：多用户模拟器（OCEAN→转移概率参数化；KL 距离评估模拟质量）
- **DIN/DIEN/BST**：行为序列深度模型（P2 可选升级路径）
- **openclaw**：standing intents（显式承诺的工程形态，前身对比）

---

## 二、核心问题清单（按优先级）

| # | 问题 | 级别 | 证据 |
|---|------|:---:|------|
| 1 | V32Pipeline 断链（behavior_graph.* 不存在 + v3_2.integration 不存在） | **P0** | import 实测 ModuleNotFoundError |
| 2 | 预测/奖励/训练闭环未接入 v4 主链路 | **P0** | 唯一调用方是断链 |
| 3 | BC05 四层决策树未落地 | P1 | 关键词全局搜索无命中 |
| 4 | 显式承诺零现状（讨论 2 拍板的新增） | P1 | standing/cron/trigger 全无 |
| 5 | predictor 权重硬编码 + ValueRanker 两维度恒 0 | P2 | 源码 |
| 6 | predictor/rewarder 零测试 | P2 | 测试目录仅 adapter |

---

## 三、显式承诺设计方向（讨论 2 拍板 + PRINCIPLES 映射）

```
行为链 = 行为认知系统（显式+隐式一体）
├── 隐式层: BehaviorGraph 权重 + 四层决策树预测（ADR-013 不参与当前轮）
├── 显式层: 用户声明承诺 + 系统蒸馏原则
│     └── 存储格式: when(situation) -> should(strategy) + rather_than(failed) + because(reason)
│           ├── 用户声明 → 显式承诺（生命周期状态机）
│           └── 行为图稳定模式 + 元认知审核 → 蒸馏为显式原则（隐式→显式）
└── 双向转换（A24 可逆推性）
      ├── 显式→隐式: 承诺创建/触发/完成/取消 = 行为事件 → 行为图学习（触发本身不算信号）
      └── 隐式→显式: 稳定模式 + 审核 → 原则（PRINCIPLES 机制）
```

三个实现边界（已确认）:
1. 存储: 行为图节点/边加 explicit 标记 + 生命周期字段，共享图结构
2. 调度: 显式承诺命中 → 确定性匹配 → 隐藏上下文块（每轮≤3），不参与隐式预测竞争
3. 回流: 承诺完成/取消回流学习，但触发本身不算学习信号（防自我强化）

---

## 四、待讨论/待拍板

1. **v4 怎么接预测/奖励引擎**：
   - 方案 A: 复用现有 predictor/rewarder（修断链 + 接 runtime/engine）
   - 方案 B: 按 BC05 四层决策树重做调度层（predictor 作为预测层，叠加四层调度）
   - 方案 C: A + B 组合（四层决策树调度 + 现有 predictor 预测 + 奖励闭环）
2. **断链处理**：integration.py（V32Pipeline）是修复还是归档（v4 已替代其职责）
3. **显式承诺落点**：进 behavior/（新文件）还是 v4/behavior_graph 门面扩展
4. **四层决策树的成本/风险/冷启动/CI 是否全部实现**（P1 完整版 vs 先做成本+风险两个硬约束）
5. **predictor 权重参数化**（A18）与外部参数系统的关系（ParameterRegistry 还是独立）

---

## 五、下一步

讨论 §四 的 5 个拍板点 → 产出行为链改造设计（类似 DESIGN_PCR）→ 落盘 docs/only/behavior/DESIGN_BEHAVIOR.md
