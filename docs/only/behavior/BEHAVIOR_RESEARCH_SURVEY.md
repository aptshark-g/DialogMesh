# 行为预测 / 主动式助手 文献与项目调研（2026-08-01）

> 目的: 为"v4 如何接预测/奖励引擎 + 显式承诺"提供外部成熟方案参照
> 方法: arxiv API + GitHub API 检索（2026-08-01）
> 结论先行: 行为链的四层决策树/预测/奖励设计在学术和工业界均有成熟对应——主动式对话（策略规划+评测）、用户模拟器（冷启动 LLM 模拟的直接对应）、行为序列建模（DIN/BST 是"行为链→预测"的深度模型形态）

---

## 一、主动式对话（Proactive Dialogue）

| 文献/项目 | 核心 | 与我们的对应 |
|-----------|------|-------------|
| Survey on Proactive Dialogue Systems（arXiv:2305.02750） | 主动式对话综述：策略规划、用户建模、何时主动 | 行为链"预测+建议"的理论全景 |
| PRINCIPLES（arXiv:2509.17459） | **合成策略记忆**：为主动对话 agent 存储/检索策略 | **显式承诺的"策略记忆"形态**——触发条件→策略，接近 standing intents |
| ProactiveEval（arXiv:2508.20973 + liutj9/ProactiveEval ★5） | 主动对话统一评测框架 | **显式承诺/预测的评测标准**（何时主动/是否打断/价值） |
| TACT（HYU-NLP/TACT，主动转换感知） | 任务型↔闲聊主动切换 | 行为链 zone 切换的预测 |
| giansha/Global-Workspace-Agents ★15 | 全局工作空间 + 主动发起对话 | A12 约束空间 + 主动式（我们已有融合器全局工作空间简化版） |

## 二、用户模拟器（User Simulation）——冷启动 LLM 模拟的直接对应

| 文献/项目 | 核心 | 与我们的对应 |
|-----------|------|-------------|
| Seq2Seq 用户模拟（arXiv:1607.00070） | 用户模拟器生成训练数据 | 冷启动时"模拟用户行为"的学术源头 |
| State2Seq（arXiv:1909.04448 + AtmaHou/UserSimulator ★7） | **无语料用户模拟**，状态→序列 | **冷启动零数据模拟** = 我们的 LLM 模拟用户前瞻 |
| MUST（kiseliu/must ★9，ACL23） | 多用户模拟器（单模拟器无法代表所有人） | 画像驱动的多态用户模拟（OCEAN→模拟风格） |
| DuetSim（suntea233/DuetSim ★8，LREC-COLING24） | **双 LLM 模拟器**（用户+系统交互） | 共塑造式（LLM 回复反向塑造用户）的模拟器形态 |
| 情绪感知用户模拟（arXiv:2011.09696） | 情绪影响用户模拟 | Z 轴情绪温度进入模拟 |

## 三、行为序列建模（Behavior Sequence）——"行为链→预测"的深度模型形态

| 文献/项目 | 核心 | 与我们的对应 |
|-----------|------|-------------|
| DIN（Deep Interest Network，阿里） | 注意力加权历史行为 → CTR 预测 | 行为链→下一步预测的注意力形态（替代纯频率） |
| DIEN（Deep Interest Evolution Network） | **兴趣演化**时序建模 | 行为链的时间演化维度（A15 温度的时间轴） |
| BST（Behavior Sequence Transformer，arXiv:1905.06874 + jiwidi 实现 ★178） | Transformer 编码行为序列 | 行为链→预测的 Transformer 形态 |
| DSIN（IJCAI19，shenweichen/DSIN ★450） | 深度会话兴趣网络 | 会话级行为建模（对话树话题内行为） |

## 四、主动式个人助手（产品）

| 项目 | 核心 | 与我们的对应 |
|------|------|-------------|
| gaia（theexperiencecompany/gaia ★251） | 主动式个人 AI 助手 | 行为预测 + 主动建议的产品形态 |
| kirie（khaterdev/kirie ★6） | Telegram/Discord 主动助手 | 多通道 + 主动（openclaw 同类） |

---

## 五、对我们的直接启示（按行为链设计三块）

### 5.1 显式承诺（讨论 2 拍板）
- **PRINCIPLES 合成策略记忆**：策略记忆 = 触发条件→策略的存储检索——正是显式承诺的学术形态（比 openclaw standing intents 更系统）
- **ProactiveEval**：提供"何时主动/是否打断/价值"的评测维度——显式承诺的触发质量评测可借鉴
- **TACT**：任务↔闲聊的主动切换——行为链 zone 切换的预测目标

### 5.2 隐式预测（v4 接线 predictor/rewarder）
- **MUST**：多用户模拟器——我们的冷启动"LLM 模拟用户"应该按画像分多态（OCEAN→模拟风格），不是单一样本
- **DuetSim**：双 LLM 模拟——共塑造式（LLM 回复塑造用户）的模拟器验证
- **DIN/BST/DIEN**：行为链的下一步预测如果要做深度模型，DIN（注意力）+ DIEN（演化）+ BST（Transformer）是三条可选路线——但**我们的四层决策树（成本/风险/冷启动/CI）是调度层，深度模型是预测层**，两者不冲突，可叠加

### 5.3 评测
- **ProactiveEval**：统一评测框架——显式承诺+预测的黄金样例集设计可对齐（何时主动/价值/打断成本）

---

## 六、待深入（下一轮可选）

- [ ] 读 ProactiveEval 的评测维度设计（arXiv:2508.20973）
- [ ] 读 PRINCIPLES 的策略记忆存储/检索结构（arXiv:2509.17459）
- [ ] 读 MUST 多用户模拟器的画像分解方法（ACL23）
- [ ] 读 BST 的实现（jiwidi/Behavior-Sequence-Transformer-Pytorch ★178）评估行为链深度模型的工程成本


---

## 七、深读结果（2026-08-01）

### 7.1 MUST 多用户模拟器（kiseliu/must，ACL23）——冷启动模拟的直接参照

**核心机制**（`simulator/env_multi_users.py`）：
- **多用户 = 状态转移概率参数化**：不同用户 profile → 不同状态转移矩阵（`prev_state_trans_probs`）——模拟器用转移概率决定用户下一步行为
- **reward = 分布差距**：`KL 散度 + Wasserstein 距离` 衡量"模拟用户行为分布" vs "真实用户行为分布"的差距；rank 惩罚（动作排名越靠后惩罚越重 -1/-3/-5/-8）
- **关键启示**：我们的冷启动"LLM 模拟用户前瞻"应该按画像分多态——**OCEAN 维度 → 状态转移概率/行为风格**，而不是单一样本；模拟质量用"模拟分布 vs 真实行为分布"的 KL 距离评估（对应 A18 真实验证）

### 7.2 ProactiveEval（liutj9/ProactiveEval）——显式承诺评测的直接参照

**核心机制**（`eval/target_planning_eval.py`）：
- **评测对象**：主动 agent 的目标规划质量（generated target/sub_target vs ground truth）
- **评测方式**：LLM-as-judge（judge_model），带 6 领域 few-shot（persuasion / ambiguous_instruction / long-term_follow_up / system_operation / glasses_assistant / recommendation）
- **关键输入结构**：`environment = {user_information, trigger_factor}`——**user_information（画像）+ trigger_factor（触发条件）**正是显式承诺的两个核心字段！
- **评测输出**：score + reason（打分 + 理由）——可解释评测

**对我们的直接启示**：
1. 显式承诺的**评测基准**可直接套 ProactiveEval 结构：给定（用户画像 + 触发因子）→ 评估生成的"目标/子目标"是否合理（LLM-as-judge + 领域 few-shot）
2. 六个领域场景（劝说/模糊指令/长期跟进/系统操作/助手/推荐）可作显式承诺的**黄金样例集领域模板**
3. `trigger_factor` 概念 = 显式承诺的触发条件——学术上已有标准定义

### 7.3 PRINCIPLES（arXiv:2509.17459）——策略记忆（已深读 arxiv HTML，重大映射）

**核心机制**：合成策略记忆（Synthetic Strategy Memory）——离线 self-play 模拟推导，推理时作为可复用知识，免训练免标注

**结构**：`when [situation], you should [successful strategy], rather than [failed strategies], because [reason]`
- **触发条件 → 成功策略 vs 失败策略 + 原因**
- rather than 子句（成功 vs 失败对比）显式避免偏好偏差

**构造流程**（新）：成功检测 → 失败检测 → 策略修订（回退到失败起点）→ 重模拟直到成功 → 原则推导

**三个优势**：覆盖（扩大策略空间）/ 偏差（对比子句缓解偏好偏差）/ 免训练（非参数挖掘 LLM 隐式知识）

**评估**：ESConv（情感支持）+ P4G（劝说）两个域；扩展到 ExTES + P4G 扩展版仍稳健

---

### 7.4 PRINCIPLES 与行为链的重大映射（这是本轮调研最重要发现）

| PRINCIPLES | 行为链/显式承诺 | 映射类型 |
|-----------|----------------------|------------------|
| `when [situation], you should [strategy]` | 显式承诺（触发条件→行为） | 直接对应 |
| `rather than [failed strategies]` | 负知识库（NegativeKB）——显式承诺的反面教材 | 直接对应 |
| 回退重模拟（失败后回退到起点修订再重模拟） | 冷启动 LLM 模拟 + 共塑造式的升级版（模拟→失败→回退→修订→重模拟→成功） | **升级路径** |
| 成功/失败双经验推导 | 纠错即训练（A6/A9）+ 信息增益奖励（BC05 §6） | 哲学同源 |
| 免训练非参数 | ADR-014（行为权重不 fine-tune LLM） | 工程同源 |

**最重要启示**：显式承诺可以升级为“原则记忆”形态——不只是用户声明的“当X做Y”，而是系统从模拟/真实经验蒸馏“当X应该Y而非Z，因为W”。这正好是“显式分解出隐式，隐式显式化”的学术实现：PRINCIPLES = 从 self-play 经验蒸馏出可复用的显式原则的机制。

**落地路径（行为链改造可直接借鉴）**：
1. 显式承诺存储格式改为 `when(situation) -> should(strategy) + rather_than(failed) + because(reason)`（融合 NegativeKB）
2. 冷启动模拟升级为“回退重模拟”：失败后回退修订再模拟，直到成功或预算耗尽（对应温度/cooldown）
3. 原则推导入行为链：行为图稳定模式 + 元认知审核通过 → 蒸馏为显式原则（隐式→显式）

---

## 八、设计映射总结（行为链改造的外部支撑）

| 行为链改造块 | 外部参照 | 借鉴点 |
|------------|---------|--------|
| 显式承诺触发 | ProactiveEval trigger_factor + PRINCIPLES 策略记忆 | 触发条件定义 + 评测（LLM-as-judge） |
| 显式承诺评测 | ProactiveEval | environment={user_info, trigger} → score+reason |
| 冷启动 LLM 模拟 | MUST 多用户模拟器 | OCEAN → 状态转移概率参数化；KL 距离评估模拟质量 |
| 隐式预测升级（可选） | DIN/DIEN/BST | 深度模型形态（P2，非当前必需） |
| 共塑造式验证 | DuetSim 双 LLM | 用户-系统交互模拟 |
