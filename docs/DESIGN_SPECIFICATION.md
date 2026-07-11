# DialogMesh 设计规格书

> 架构规范（RFC 级），不含实现代码。
> 基于 ~80 篇设计/工程/审查文档提炼重构。
> 版本: v2.0 | 日期: 2026-07-09

---

## 目录

1. [世界模型：四种核心对象](#1)
2. [生命周期：四种对象的转化流](#2)
3. [数据模型：概念层定义](#3)
4. [运行时：核心 Pipeline](#4)
5. [核心算法](#5)
6. [安全与交互](#6)
7. [基础设施](#7)
附录A. [模块清单](#A)
附录B. [术语映射表](#B)
附录C. [设计演化路径](#C)

## 1. 世界模型：四种核心对象

DialogMesh 的核心不是模块列表，而是四种对象及其转化关系。
所有模块的职责都可以还原为在这四种对象之间做转化。

### 1.1 Information（信息）

定义：来自外部世界、未经系统处理的原始输入。
来源：用户消息、LLM 输出、外部工具返回、系统日志。
属性：客观存在、无内部结构、高噪声。形态：自然语言文本、结构化数据。

### 1.2 Event（事件）

定义：被系统识别并记录的状态变化。绝对客观，不含推断。

唯一来源：UserAction（用户说了什么/做了什么操作）、SystemAction（系统生成了什么回答/执行了什么操作）。

重要约束：Event 不包含推断结果。TopicSwitch、ConstraintUpdate、ProfileUpdate 不是 Event——它们是 Compiler 对 Event 的解释产物。Event Log 是系统的 WAL，是所有下游处理的唯一事实源。

### 1.3 Knowledge（知识）

定义：从 Event 中提取、结构化、可跨会话持久化的认知资产。

Knowledge 的核心特征：类型化关系（Typed Relation）。价值不在于存了多少文本，而在于文本之间捕捉到了什么类型的关系（因果、依赖、修正、扩展）。

### 1.4 Reasoning（推理）

定义：基于 Knowledge 和当前 Information，生成新结论的认知过程。

推理结果有三种去向：输出给用户（对话回答）、回流入 Knowledge（新发现的关系）、转化为新的 SystemAction Event。

### 1.5 四种对象的统一视角

Information: 发生了什么（瞬时、不变）
Event: 系统记录了什么（时间点、不可变）
Knowledge: 从中总结出什么（跨时段、可修订）
Reasoning: 基于知识能推出什么（即时、一次性）

## 2. 生命周期：四种对象的转化流

四种对象不是并列的——它们之间存在单向转化流：

Information -> Event -> Knowledge -> Reasoning

### 2.1 第一段：Information -> Event（采集）

触发器：用户发送消息 / 系统生成回答 / 外部工具返回结果。

转化逻辑：将原始信息包装为 Event 并追加到 Event Log。不解析、不推断，只记录。
O(1) 操作，无外部依赖。

### 2.2 第二段：Event -> Knowledge（沉淀）

触发器：Checkpoint（事件数达到阈值、时间窗口到期、会话结束、用户触发）。

执行者：Memory Compiler。（注意：Compiler 是 pipeline 调度器，不是 God Object。具体转化由 ConflictResolver、GraphMerger、SummaryBuilder、Indexer 子模块完成。）

转化内容：
1. 从 Event 中提取实体和关系
2. 检测冲突（同一实体的多个 patch 是否矛盾）
3. 合并节点（同概念去重）
4. 融合关系边（同类型同方向加权合并）
5. 计算重要性和激活计数
6. 热/冷分层（低重要性下沉，跨会话检索回升）
7. 生成摘要（节点级 L1 + 话题级 L2）

### 2.3 第三段：Knowledge -> Reasoning（推理）

触发器：每次用户输入。

执行者：Context Compiler。

转化内容：
1. 定位当前话题（TopicBoundaryDetector）
2. 从 Knowledge 中裁剪相关子图（锚点出发 k 跳水波扩展）
3. 信息选择（在 token 预算内最大化推理路径+约束+历史覆盖）
4. 生成 Context IR
5. 由 Context Serializer 转化为 LLM-readable prompt

### 2.4 第四段：Reasoning 的回流

推理完成后，结果有三条路径：
- 输出给用户（直接）
- 回流入 Knowledge（修正关系、更新置信度）
- 转化为新的 SystemAction Event（回到生命周期起点）

### 2.5 事件链统一模型

不区分行为链/工程链——它们是同一种东西：Event Chain。

区别仅在于 source 字段：User（用户操作）/ AI（系统回答）/ System（系统内部操作，如模块注册）。

元认知、Context Compiler、Memory Compiler 都从统一的 Event Chain 读取数据，按 source 过滤所需维度。

## 3. 数据模型：概念层定义

本章定义系统处理的核心数据结构的概念模型，不涉及具体实现技术（Graph/Tree/Python/Rust）。

### 3.1 Event（事件记录）

单一事实记录。不可变。包含：id, timestamp, source(User/AI/System), type(UserSaid/SystemGenerated/ModuleRegistered), payload。

存储：Event Log，追加式，按 session 分文件。

### 3.2 Patch（增量更新）

对 Knowledge 中某个实体或关系的一次更新。不是直接修改，而是追加式的增量记录。

Memory Compiler 在 Checkpoint 时 apply 所有 patch 生成新状态。
类比：Git 的 commit。好处：每次追加 O(1)、可回放撤销审计、冲突延迟到 Checkpoint 解决。

### 3.3 Conversation Projection（对话投影）

概念：Event Log 的一个视图。对话树不是独立的数据孤岛——它是从底层事件流生成的语义解释层。

三层模型：
1. Event Layer（事实）：Event Log 是唯一事实源。对话内容以 UserAction/SystemAction Event 形式记录。
2. Projection Layer（解释）：Conversation Projection 从 Event 中生成，按话题组织语义块。
3. Cognitive Layer（推理）：三链统一为 Event Chain，按 source 过滤维度。

核心特征：
- 每个节点 = 一个语义完整的对话块（DiscourseBlock）
- 树向下 = 收敛聚焦（深挖话题），树向外 = 发散联想（切换话题）
- 跨分支指针（Tree-Graph Hybrid）：解决纯树结构的主题割裂问题
- 定位：推理的工作台（在内存中），持久化层是 Event Log + Knowledge Layer

多投影共存：同一组 Event 可以投影到多个视图——Conversation Projection（对话树）、Operation Projection（操作树）、Engineering Projection（工程图）。

双轨制：
- 时序轨道（Event Log）：不可变的、按时序排列的事实记录
- 语义轨道（Projection 层）：可随理解重组的语义结构

与链的关系：行为链/因果链/工程链不是树的边属性——它们是关系的注解。树的边只表达语义关系，链作为独立注解层叠加在关系上。

### 3.4 Knowledge Layer（知识层）

概念：所有跨会话持久化知识的载体。Property Graph（节点和边都有属性）+ Typed Edge（边类型是枚举而非自由文本）。

节点类型：Topic（话题）、Concept（概念）、Action（行为）、Constraint（约束）、Entity（实体）。

边类型：depends（依赖）、creates（创建）、updates（更新）、constrains（约束）、reason（推理——最核心）、corrects（修正）、extends（扩展）。

核心属性：activation_count（电容模型）、importance_score、confidence、source_events（溯源）。

存储模式：Patch Chain（base state + patch sequence），周期性 snapshot。

### 3.5 Context IR（上下文中间表示）

概念：Context Compiler 的输出。为当前任务定制的、最优的信息组织方式。

两层架构：ContextModel（语言无关的数据结构：节点列表、边列表、优先级分数、约束清单）+ ContextSerializer（将 Model 序列化为 LLM-readable prompt）。

设计约束：ContextModel 不含自然语言段落——它是一组关系型的结构化数据。
Serializer 负责 prompt 适配（不同 LLM 用不同 Serializer）。

### 3.6 Summary（摘要）

两级摘要：L1 节点级（单个 Knowledge 节点的压缩描述）、L2 话题级（一个话题子树的整体概要，LLM 生成）。

### 3.7 Behavior Model（行为模型）

概念：从 Event Chain 中学习的行为模式。四因子权重制：LLM 因果概率 + 频率统计 + 画像匹配 + 结构先验。

重要：行为模式不是对话树边的属性——它们是对关系的注解（Annotation）。同一条语义关系可以有多个维度的注解（行为注解、因果注解、工程注解）。树的边只表达语义关系。

子组件（非核心，降级为可插拔）：Predictor（行为预测）、Rewarder（奖励信号计算）。两者作为 Behavior Model 的用户，不独立存在。

## 4. 运行时：核心 Pipeline

运行时定义系统的执行模型。分为两条 Pipeline：一条实时（每轮触发）、一条后台（Checkpoint 触发）。

### 4.1 实时 Pipeline（每轮对话）

触发器：用户消息到达。

步骤：
1. Information 采集：用户消息 -> 包装为 UserAction Event -> 追加到 Event Log
2. Context Compiler 执行（pipeline 调度器）：
   a. TopicLocator：定位当前话题在 Knowledge 中的锚点
   b. SubgraphExtractor：从锚点出发 k 跳水波扩展，沿 typed edge 按权重裁剪
   c. InformationSelector：贪心+ILP 在 token 预算内选择最优子图
   d. ContextModelBuilder：构建语言无关的 ContextModel
   e. ContextSerializer：将 ContextModel 序列化为 LLM-readable prompt
3. LLM 推理：Context + 用户消息 -> 回答
4. 回答 -> 包装为 SystemAction Event -> 追加到 Event Log

### 4.2 后台 Pipeline（Checkpoint）

触发器：Checkpoint（Event 数>=N、时间>=T、会话结束、用户触发、CPU 空闲）。

Memory Compiler 执行（pipeline 调度器）：
1. ConflictResolver：同一实体的多个 patch 是否矛盾 -> 规则引擎+LLM仲裁
2. GraphMerger：同概念节点去重、同类型边加权合并
3. SummaryBuilder：L1 节点级 + L2 话题级摘要生成
4. ImportanceScorer：基于 activation_count + 结构位置重算重要性
5. ColdIndexer：低重要性下沉到冷存储，跨会话检索命中 -> 回升

### 4.3 Compiler 的设计约束

Compiler 只负责 Pipeline 调度——不直接调用算法、不持有状态、不维护数据结构。
每个子模块（ConflictResolver、GraphMerger 等）可独立测试、独立替换。

### 4.4 元认知（Meta-Cognition）

定义：系统对自身推理和行为的反思评估层。

输入：统一的 Event Chain（按 source 过滤所需维度）+ Knowledge Layer 的当前状态。

功能：
- 质量评估：对回答质量评分
- 模式识别：从交叉数据中发现系统性偏差
- 策略调整：基于长期反馈调整系统参数（通过 AdaptiveParameter 接口）

触发：自适应触发（token 数阈值/变化检测）+ 后台循环评估。不每轮启用。

## 5. 核心算法

### 5.1 阈值自适应三层范式

定义：解决全系统阈值参数的统一框架。

第一层：文献锚点。从公开基准/论文中查到参数的参考值作为初始值（合理起点，非最优值）。

第二层：上下界区间。基于参考值和场景特点设浮动范围（安全网——在此范围内系统不会崩溃）。

第三层：在线自适应。随实际使用数据调整参数，方向取决于奖励信号。

范式：锚点给方向 -> 区间给安全网 -> 自适应给个性化。

### 5.2 编译器阈值：Bradley-Terry 竞争模型

场景：LLM 子模型和规则子模型在相同维度上竞争判断权。

机制：记录两个子模型在每个槽位类型上的胜场数。胜率高的方向 -> 阈值向该方向微调。
步长：0.02。最小样本数：10。区间：[0.65, 0.85]。

### 5.3 Behavior Model 四因子自适应

锚点：[0.25, 0.30, 0.05, 0.05]（无数据先验下的合理起点）。

区间保护：alpha[0.15,0.35], beta[0.20,0.40], gamma[0.05,0.25], delta[0.01,0.15]。

自适应信号：Predictor 预测命中率（实际 vs 预测对比）。

### 5.4 电容模型：激活计数替代时间衰减

原理：人脑遗忘像电容放电（不消耗能量），计算机模拟时间衰减消耗算力。

方案：不计衰减，只计使用。每次访问 -> activation_count + 1。不用的边自然低计数。

效果等同于时间衰减，但零额外算力开销。

### 5.5 因果骨架匹配

定义：从统计关联中区分结构性因果的推理层。

三步映射：
1. 约束条件提取：从 Event 中提取约束语义
2. 候选骨架匹配：从预定义因果模式库中找最匹配的模板
3. structural_prior 加权：基于匹配度调整因果置信度

### 5.6 三层时间尺度

即时（每轮）：Behavior Model 边权重更新、话题检测温度缓存。
短期（每10轮）：Predictor 预测权重调整。
长期（每100轮）：Rewarder 奖励值微调、知识层重要性重算。

## 6. 安全与交互

### 6.1 PCR：预处理、约束、规则

三层安全架构：

Layer 0（规则引擎预处理器）：输入消毒（注入检测、格式校验）、schema 校验。

Layer 1（意图解析器）：分类输入意图类型（task/query/correction/casual）+ 填充语义槽位。

约束引擎：在 LLM 输出上施加神经符号约束（类型检查、范围验证、一致性校验）。

### 6.2 NegativeKB：负面经验库

三级分类 + 熔断：

Level A（明确禁止）：硬约束，检测命中 -> 立即阻止，不进入 LLM。

Level B（高概率负面）：软约束，标记风险 -> 需要人工确认或额外验证。

Level C（低频但严重）：标记警告，不阻止执行 -> 记录到审计日志。

熔断机制：同类型负面触发计数器达到阈值 -> 自动关闭对应的行为路径，防止级联失败。

### 6.3 HallucinationDetector（幻觉检测）

在 LLM 输出后检测：语义一致性（回答与 Knowledge 是否一致）、事实对照（声称的事实是否在 Knowledge 中有支撑）、实体一致性（引用的实体是否匹配）。

### 6.4 用户画像（Cognitive Profile）

八维认知画像：人格特质、知识水平、交互风格、修正习惯、兴趣领域、情绪模式、推理偏好、表达风格。

数据来源（交互优先原则）：行为数据权重高于语言推断——用户实际做的比用户说的更可信。

- LLM 文本分析：从聊天内容推断认知特征
- 行为数据：用户实际修正行为（频率、类型、时机）
- 工程修正记录：用户在系统配置上的手动修改

### 6.5 TopicBoundaryDetector（话题边界检测）

六信号融合：词法信号、句法信号、语义信号（embedding 相似度）、意图信号、行为信号（操作类型变化）、显式信号（用户声明切换话题）。

## 7. 基础设施

### 7.1 语言分工（长期方向）

Python：LLM 交互、API/Orchestrator、轻量推理、Prompt 组装。
Rust：Knowledge Layer 原生存储、Memory Compiler 批处理、子图检索、向量嵌入。
通信：PyO3（嵌入式）或 gRPC（独立服务），初期用 PyO3 验证。

### 7.2 LLM Provider

统一抽象接口，支持 OpenAI API、本地模型（LM Studio）、Mock。
关键机制：多级重试、故障转移、熔断器、流式输出。

### 7.3 持久化

三存储后端：SQLite（会话元数据、Event Log）、SQLite/Sled（ColdIndexer 冷热索引）、自建存储（Knowledge Layer 长期方向）。

### 7.4 可观测性

三层监控：Metrics（计数器/直方图）、Logging（结构化日志）、Tracing（链路追踪，每轮输出完整模块调用链）。

### 7.5 服务层

FastAPI + WebSocket 实时通信。会话管理。异步请求队列。健康检查。

### 7.6 MCP 协议

Model Context Protocol 集成，作为独立 MCP Server。支持工具注册与发现、权限控制、多模态输入。

---

## 附录 A：模块清单 {#A}

核心模块（按运行时 Pipeline 顺序）：

| 模块 | Pipeline 位置 | 功能 |
|:-----|:---------------|:-----|
| EventLog | 实时 Step 1 | 唯一写入入口，追加事件 |
| TopicLocator | 实时 Step 2a | 话题锚点定位 |
| SubgraphExtractor | 实时 Step 2b | 子图裁剪 |
| InformationSelector | 实时 Step 2c | Token 预算优化选择 |
| ContextModelBuilder | 实时 Step 2d | 构建语言无关 ContextModel |
| ContextSerializer | 实时 Step 2e | 序列化为 LLM prompt |
| ConflictResolver | 后台 Step 1 | Patch 冲突检测与解决 |
| GraphMerger | 后台 Step 2 | 节点去重 + 边融合 |
| SummaryBuilder | 后台 Step 3 | L1/L2 摘要生成 |
| ImportanceScorer | 后台 Step 4 | 重要性重算 |
| ColdIndexer | 后台 Step 5 | 冷热分层 + 回升 |
| PCR | 实时 Step 0 | 预处理+约束+规则 |
| NegativeKB | 实时 Step 0 | 负面经验库 + 熔断 |
| IntentParser | 实时 Step 0 | 意图分类+槽位填充 |
| HallucinationDetector | 实时 Step 3 后 | 幻觉检测 |
| TopicBoundaryDetector | 实时 Step 2a | 六信号话题边界检测 |
| MetaCognition | 后台 | 三链交叉的元认知评估 |
| UserProfile | 后台 | 八维认知画像 |
| AdaptiveParameter | 全系统 | 阈值自适应 |

非核心模块（可插拔）：

| 模块 | 所属 | 功能 |
|:-----|:-----|:-----|
| Predictor | Behavior Model | 用户行为预测 |
| Rewarder | Behavior Model | 奖励信号计算 |
| FoA | 注意力 | 注意力焦点激活传播 |
| do-calculus | 推理 | 因果验证（Phase3） |
| CausalSubstrate | 推理 | 因果骨架匹配 |
| EngineeringGraph | 工程链 | 模块状态自检 |

## 附录 B：术语映射表 {#B}

设计规格书中的概念名称与工程实现中的模块名称对应关系：

| 概念名称 | 工程名称 | 说明 |
|:---------|:---------|:-----|
| Knowledge Layer | PersistentGraph | 对外用概念层，对内保留图实现 |
| Behavior Model | BehaviorGraph | 同上 |
| Topic Tree | DiscourseBlockTree | 对话块树 = 话题树的实现形态 |
| Event Chain | BehaviorChain + EngineeringChain | 统一为一个概念 |
| Compiler | 多个模块的集合 | Compiler 是调度器，子模块独立 |
| Context IR | ContextModel + ContextSerializer | 两层架构 |

## 附录 C：设计演化路径 {#C}

| 版本 | 核心贡献 | 文档 |
|:-----|:---------|:-----|
| v3.0 | 多层 LLM 认知架构、Planning/Skill Layer、Topic Tree、PCR 设计 | DESIGN_* v3.0 系列 |
| v3.1 | 行为总结、BehaviorGraph 初版 | DESIGN_V3_1_BEHAVIOR_SUMMARY.md |
| v3.2 | 编译器 + 因果基地 + 预测/奖励 + 负知识库 + FoA + L1Summary + 融合器（12模块蓝图） | DESIGN_V3_2.md |
| v3.3 | 算法范式（阈值分层自适应、在线训练、Bradley-Terry） | DESIGN_V3_3_ALGORITHM.md |
| v4（当前） | Context Engineering 转向、双 Compiler + Event Log、Context IR、事件链统一、四态世界模型 | DESIGN_V4_CONTEXT_ENGINEERING.md + 本文档 |

---

> 本文档不含任何实现代码，仅定义设计概念、模块边界、算法范式和数据流动路径。
> 具体实现细节请参见对应的 ENGINEERING_ 文档系列。设计决策记录见 ADR- 系列。
> 关联文档索引见 ARCHITECTURE_INDEX.md。
