# 跨域上下文编译系统

> 定义 Context Compiler 如何将多个知识域（工程链/对话树/用户画像/行为链/因果链）编译为统一的、带跨域引用的子图，
> 通过 Context IR 传递给 LLM。
>
> 这是 DialogMesh 对 Prompt Engineering 的特化回答：不是写更好的 prompt，而是构建更好的 Context。

> 版本: v1.0 | 日期: 2026-07-10

---

## 目录

1. 问题定义
2. 设计原则
3. 事件流：跨域粘合剂
4. 意图感知的域选择策略
5. 预算分配模型
6. 跨域引用格式规范
7. Context IR v2 格式
8. 实现路线
9. 与现有模块的关系

## 1. 问题定义

### 1.1 现状

## 1. 问题定义

### 1.1 现状

当前 DialogMesh 传给 LLM 的是扁平对话历史加 system prompt。
对话树、行为图、因果链、工程链、用户画像各自正确运行
但它们产出的认知资产从不流入 LLM 的视野。
结果：LLM 在蒙眼状态下推理。

### 1.2 更深层的问题

即使把所有域的信息都传给 LLM，如果它们是各自独立传递的孤立段落，
LLM 仍然无法利用跨域关联。

例如当前孤立段落的模式：
对话历史说模块延迟飙升
工程状态说该模块恰好缺少监控
用户画像说偏好可视化调试

LLM 看到的是三个无关的信息块。
LLM 应该看到的是一个统一的叙事：
用户发现延迟飙升，该模块恰好缺少监控所以无法看时间线，
且用户偏好可视化调试所以应建议加监控而非加日志，
前几轮用户也在调这个模块参数说明这是持续性优化。

### 1.3 核心命题

跨域上下文编译系统要回答的核心问题：
如何从事件流出发，识别当前意图，选择最相关的域组合，
并将它们编译为一个带内部指针的统一信息网络，
让 LLM 像系统的一部分一样思考。

## 2. 设计原则

### 2.1 单一源头，多域投影

所有域的信息都源自 Event Chain。不分别查询工程链、对话树、用户画像、行为链
Context Compiler 从 Event Chain 出发，沿 Event ID 做多跳扩展，自然覆盖所有相关域。

### 2.2 意图感知，非平均分配

不同意图需要不同的域组合。工程操作以工程链为主域，思路讨论以用户画像为主域。
Context IR 的信息密度取决于意图匹配度，而非所有域的平均覆盖。

### 2.3 带指针的子图，非独立段落

传给 LLM 的不是多个独立的 SECTION 段落，而是一个有内部引用的信息网络。
每条信息标注它与其他域中什么信息相关（cross_ref 指针）。
LLM 收到的不是一个文档，而是一个有导航结构的子图。

### 2.4 预算约束下的信息选择

总预算 500 tokens。不是每个域都传一点，而是基于意图的优先级分配。
主域拿大头（60%），辅助域拿关键关联（40%）。未被选择的域不在 Context IR 中出现。

### 2.5 LLM 是推理引擎，Context Compiler 是认知编译引擎

LLM 的职责是推理，不是信息检索。信息选择和跨域关联的编译工作在进入 LLM 之前完成。

## 3. 事件流：跨域粘合剂

### 3.1 为什么事件流是天然的跨域索引

一条 Event（例如用户修改了 ModuleA 的 timeout 参数）在被写入 Event Log 时，
已经携带了其所属的所有上下文信息：
- session_id: 属于哪个会话
- turn_number: 发生在第几轮对话
- source: User/AI/System
- payload: 具体的操作数据

当 Memory Compiler 把这条 Event 转化为 Knowledge 时，保留 Event ID。
当 Context Compiler 需要做跨域关联时，通过 Event ID 反向索引，
自然就能知道这条 Event 在对话树中的位置（话题）、
在工程链中的影响（哪个模块）、在行为链中的模式（用户习惯）。

### 3.2 跨域扩展流程

Context Compiler 的跨域嵌入过程：

1. 从 Event Chain 选取锚点 Event（最近 N 条）
2. 从锚点 Event 出发，沿 Event ID 多跳扩展：
   - 对话树方向：Event 所属的 DiscourseBlock -> Block 的父/子/兄弟节点
   - 工程链方向：Event 影响的模块 -> 模块的依赖/监控/翻译状态
   - 行为链方向：Event 前后的同类事件 -> 用户行为模式
   - 用户画像方向：Event 反映的认知特征 -> 已有的画像维度
3. 在同一 Event 的不同域投影之间建立 cross_ref 指针
4. 基于意图优先级做裁剪和预算分配

### 3.3 与传统多源聚合的对比

传统方式：分别查询 UserProfile DB、查询 ModuleRegistry、查询 ConversationHistory，
然后拼在一起。问题：三个查询之间不知道彼此的关系。

事件流方式：只查 Event Chain + Event ID 索引，所有域的信息天然带着关联关系。
不需要专门写跨域 JOIN 逻辑——Event ID 就是那个 JOIN 键。

这在工程上对应一个关键决策：Event Log 不只是审计日志，
它是系统的**唯一权威索引（Single Source of Truth Index）**。

## 4. 意图感知的域选择策略

### 4.1 域定义

五个可选的上下文域：

域E (Engineering): 工程链。模块状态、依赖关系、监控/翻译/测试覆盖率。
域C (Conversation): 对话树。话题结构、DiscourseBlock 层次、当前话题锚点。
域P (Profile): 用户画像。八维认知特征、操作偏好、修正习惯。
域B (Behavior): 行为链。最近操作序列、高频行为模式、纠正模式。
域K (Causal): 因果链。已建立的因果边、因果骨架匹配结果。

### 4.2 意图分类与域选择矩阵

意图类型由 IntentParser 在 Layer 1 确定：

| 意图类别 | 主域(60%) | 辅助域1(25%) | 辅助域2(15%) | 策略名 |
|:-----|:-----|:-----|:-----|:-----|
| task (工程操作) | E | B (相关操作) | P (操作偏好) | 深度聚焦 |
| query (信息查询) | C (相关话题) | E (相关模块) | P (知识水平) | 话题锚定 |
| correction (纠正) | B (之前操作) | E (受影响模块) | K (可能因果) | 因果回溯 |
| discussion (思路讨论) | P (认知风格) | C (相关对话) | E (相关模块概况) | 广度发散 |
| casual (闲聊) | C (话题结构) | P (兴趣偏好) | — | 轻量组织 |
| topic_switch (话题切换) | C (全话题树) | B (切换模式) | P (主题偏好) | 结构重建 |

### 4.3 域选择不是硬编码

意图类别的域选择策略是默认推荐。用户画像中的修正历史可以覆盖：
- 如果一个用户连续 3 次纠正了工程操作中缺少因果链的问题，
  系统在下次 task 意图时自动将 K 从非选提升为辅助域
- AdaptiveParameter 机制调节意图-域选择的映射权重

## 5. 预算分配模型

### 5.1 三层预算

| 层 | 预算 | 内容 |
|:---|:-----|:-----|
| 必要层 | 200 tokens | 用户消息本身。不可裁剪。 |
| 策略层 | 300 tokens | 跨域编译子图。意图感知分配。 |
| 弹性层 | 200 tokens | 溢出预算。仅在子 token 预算充足时使用。 |

总预算: 500-700 tokens。推荐 500 为默认上限。

### 5.2 策略层分配算法

策略层 300 tokens 按意图类别分配：

1. 主域: 300 x 0.6 = 180 tokens
   取该域中优先级最高的节点/边/交叉引用，直到填满预算
2. 辅助域1: 300 x 0.25 = 75 tokens
   取与主域有 cross_ref 关联的信息，优先关联度高的
3. 辅助域2: 300 x 0.15 = 45 tokens
   仅取锚点信息，不做深度扩展

### 5.3 预算耗尽处理

如果某个域填不满预算，剩余量分配给下一优先级的域。
如果所有域都填不满，剩余预算返还给必要层（加长用户消息的上下文窗口）。
如果整个策略层都无法满足，降级到摘要模式（仅传主域摘要 + 用户消息）。

## 6. 跨域引用格式规范

### 6.1 核心概念

cross_ref 是嵌在 Context IR 中的域间指针。
它告诉 LLM：信息 A 和信息 B 来自不同的域，
但它们指向同一个事实。

### 6.2 引用格式

每条信息条目包含：

[DOMAIN:TYPE] content
  ^ref: DOMAIN.event_id = 关联说明
  source: event_123 (confidence: 0.9)

DOMAIN 取值: E/C/P/B/K

### 6.3 实际示例（意图: task）

[E:MODULE] ModuleA
  status: monitor_missing, translation_ok, tests_3of5
  ^ref: B.event_87 = 用户在前3轮连续调整此模块
  ^ref: P.profile = 偏好可视化调试而非日志

[C:TOPIC] 性能优化讨论
  depth: 3 (根话题 -> 延迟问题 -> ModuleA)
  ^ref: E.ModuleA = 当前讨论的核心目标

[B:ACTION] 最近操作序列
  turn_12: set_timeout(ModuleA, 5000)
  turn_16: query_latency(ModuleA)
  ^ref: E.ModuleA = 最近3轮中的2轮关联此模块

cross_ref 是双向的。LLM 收到的是可导航的子图网络。

## 7. Context IR v2 格式

### 7.1 结构定义

`
CrossDomainContextIR {
  intent_category: task | query | correction | discussion | casual | topic_switch
  domain_allocation: [
    { domain: E, role: primary, budget_pct: 60 }
    { domain: B, role: auxiliary, budget_pct: 25 }
    { domain: P, role: auxiliary, budget_pct: 15 }
  ]
  entries: [
    {
      domain: E
      type: MODULE
      content: text
      cross_refs: [{ target_domain: B, target_event_id: evt_87, note: text }]
      source_events: [evt_89]
      confidence: 0.95
      estimated_tokens: 120
    }
    ...
  ]
  total_estimated_tokens: 480
  compile_strategy: primary_deep | balanced | summary_fallback
}

### 7.2 编译策略选择

Context Compiler 根据实际预算填充情况选择编译策略：

primary_deep (主域深入): 主域成功填满 60% 预算，辅助域正常关联。
balanced (均衡): 多个域都有足够信息，按默认比例分配。
summary_fallback (摘要降级): 主域信息不足或预算紧张，仅传各域摘要锚点。

### 7.3 与 ContextSerializer 的关系

Context IR v2 是语言无关的结构化数据。ContextSerializer 负责将其转为 LLM prompt。
Serializer 的职责：保持 cross_ref 的可读性，标注 domain 来源，控制最终 token 数。
不同 LLM 可使用不同 Serializer（OpenAI 格式、DeepSeek 格式、本地模型格式）。

## 8. 实现路线

### Phase 1: Context IR v2 + Intent-Aware Domain Selector（核心）

1. 实现 CrossDomainContextIR 数据结构
2. 在 IntentParser 输出中增加 intent_category 枚举
3. 实现 DomainSelector: 基于意图类别的域选择矩阵
4. 实现 BudgetAllocator: 三层预算分配算法
5. 更新 ContextSerializer 支持 cross_ref 格式

### Phase 2: Event Stream 跨域索引（粘合剂）

1. Event Log 增加 event_id 索引机制
2. 实现 CrossDomainExpander: Event ID -> 多域投影的扩展逻辑
3. 实现 CrossRefBuilder: 自动生成域间 cross_ref

### Phase 3: 自适应域选择（进化）

1. AdaptiveParameter 接入 DomainSelector 的权重调整
2. 用户修正历史影响域选择（反馈闭环）
3. 复杂度评估动态调整预算上限（500-700 tokens 浮动）

### 预计代价

Phase 1: ~500 行（数据结构 + 选择器 + 分配器 + Serializer 更新）
Phase 2: ~400 行（索引 + 扩展器 + 引用构建器）
Phase 3: ~200 行（自适应权重 + 复杂度评估）

## 9. 与现有模块的关系

### 9.1 依赖关系

| 现有模块 | 在跨域编译中的角色 | 变化 |
|:---------|:-------------------|:-----|
| IntentParser | 提供 intent_category（已有能力，输出格式扩展） | 微调 |
| EventLog | 提供跨域索引的基础设施（Event ID 索引） | 增强 |
| TopicBoundaryDetector | 提供当前话题锚点 -> 域C 信息 | 不变 |
| BehaviorGraph | 提供行为模式 -> 域B 信息 | 不变 |
| CausalSubstrate | 提供因果边 -> 域K 信息 | 不变 |
| EngineeringGraph | 提供模块状态 -> 域E 信息 | 不变 |
| UserProfile | 提供认知画像 -> 域P 信息 | 不变 |
| ContextCompiler | 新增 DomainSelector/BudgetAllocator/CrossRefBuilder | 核心变化 |
| ContextSerializer | 支持 cross_ref 格式 + 意图感知的串行化 | 增强 |

### 9.2 这对当前 Pipeline 意味着什么

当前: 扁平历史 -> 窗口过滤 -> PCR -> LLM

目标: Event Chain -> IntentParser -> DomainSelector -> CrossDomainExpander ->
      CrossRefBuilder -> BudgetAllocator -> ContextSerializer -> LLM

对话树、行为图、因果链、工程链、用户画像不再各自孤立运行。
它们全部作为 Context Compiler 的数据源，输出的认知资产通过 cross_ref 编织在一起。

---

> 这份设计定义了 DialogMesh 对 Prompt Engineering 的特化回答。
> 不是写更好的 prompt，而是构建更好的 Context。
> 不是让 LLM 更聪明地读文本，而是让系统把 LLM 真正需要的信息，
> 在 LLM 看到它之前，就已编译、关联、预算优化完毕。

## 10. 用户可定制的预算体系

此前定义的预算分配模型（第5节）是工程师替用户做的固定决策。
实际生产环境中，token 成本在不同 Provider 之间差异极大——DeepSeek 输入成本极低，
本地模型免费，OpenAI 则较贵。预算应该是一个用户可感知、可调节的变量。

### 10.1 三层优先级体系

`
用户显式设置（最高优先级）
    | 未设置时
用户习惯推断（从历史行为学习）
    | 无历史时
Provider 默认（根据模型成本自动适配）
`

### 10.2 第一层：Provider 自适应

系统根据当前使用的 LLM Provider 自动选择预算策略：

| Provider 类型 | 输入 token 成本 | 推荐默认预算 | 策略 |
|:---|:---|:---|:---|
| DeepSeek | 极低 | 800-1000 tokens | 慷慨——多传工程链完整状态 |
| OpenAI GPT-4 | 中高 | 400-500 tokens | 标准——严格预算控制 |
| 本地模型 (Ollama) | 免费 | 1500+ tokens | 不受限——传全量子图 |
| 统一输入输出定价 | 正常 | 500-700 tokens | 平衡 |

### 10.3 第二层：用户习惯推断

从用户行为中学习预算偏好，作为 UserProfile 的第九维 context_budget_preference：

| 用户行为信号 | 推断 | 系统响应 |
|:---|:---|:---|
| 频繁追问细节（缺少上下文） | 预算太低 | 逐步上调 +50 tokens/次 |
| 从未抱怨 / 无追问 | 预算合适 | 维持 |
| 显式说太啰嗦 | 预算太高 | 逐步下调 -50 tokens/次 |
| 切换了 Provider | 对成本敏感 | 重置为 Provider 默认 |

### 10.4 第三层：用户显式设置

用户可在配置文件中直接控制预算行为和策略偏好：

`yaml
context:
  budget:
    mode: auto | manual | provider_default
    manual_limit: 800
    min: 200
    max: 2000
    strategy: quality_first | cost_first | balanced
`

strategy 直接影响域选择权重：

| strategy | 主域预算 | 辅助域1 | 辅助域2 | 效果 |
|:---|:---|:---|:---|:---|
| quality_first | 70% | 20% | 10% | 完整关联，预算消耗大 |
| balanced（默认） | 60% | 25% | 15% | 当前默认策略 |
| cost_first | 50% | 25% | 舍弃 | 仅保留主域核心+辅助域锚点 |

### 10.5 UserProfile 第九维

`
UserProfile.context_budget_preference:
  inferred_strategy: quality_first
  avg_budget_used: 780
  provider_sensitivity: low
  explicit_override: None
  overflow_followup_rate: 0.15
  confidence: 0.72
`

overflow_followup_rate: 用户在被压缩后追问了被压缩节点/话题的比例。
高频则说明预算设置偏低。

## 11. 子图溢出修剪与话题切换重组

### 11.1 问题定义

当编译出的跨域子图超过 token 预算时，子图不能像扁平文本那样直接截断前 N 条。
子图的修剪需要保留结构的完整性——切断一个节点可能切断多条 cross_ref 指针。

同时，话题切换时旧话题子图和新话题子图可能叠加超预算。
需要一种保留结构完整性的压缩策略。

### 11.2 三维节点保留评分

单维的电容模型（activation_count）不足以决定修剪。引入三维评分：

`
节点保留优先级 = alpha * frequency(activation_count)
                 + beta * recency(last_accessed)
                 + gamma * structural_importance(betweenness)
`

alpha/beta/gamma 不全局常量——它们挂在 DomainSelector 的意图类别上：

| 意图 | alpha(频率) | beta(时序) | gamma(结构) | 逻辑 |
|:---|:---|:---|:---|:---|
| task(工程操作) | 0.3 | 0.2 | 0.5 | 结构最重要：跨域连接器不能丢 |
| discussion(思路讨论) | 0.2 | 0.5 | 0.3 | 时序最重要：新想法优先 |
| correction(纠正) | 0.5 | 0.3 | 0.2 | 频率最重要：反复被纠正的节点 |
| topic_switch | 0.1 | 0.6 | 0.3 | 时序最重要：刚切换的话题 |
| casual(闲聊) | 0.4 | 0.4 | 0.2 | 均衡 |
| query(信息查询) | 0.3 | 0.3 | 0.4 | 结构稍高：关联知识需要完整 |

### 11.3 四轮修剪流程

当 Context IR tokens 超过预算时触发：

**第一轮：电容排序**
- 对所有节点的 activation_count 排序
- 标记后 30% 为修剪候选（不活跃的节点优先候选）

**第二轮：结构保护**
- 对候选节点检查 betweenness（结构介数）
- betweenness > 阈值(0.6) 的节点从候选列表中移除
- 逻辑：这些节点是跨域连接器——删除会导致子图断裂

**第三轮：时序修复**
- 对候选节点检查 last_accessed
- last_accessed < 3 轮（新引入但使用少的节点）从候选列表移除
- 逻辑：新节点可能因为样本不足而 activation_count 偏低，但不应过早修剪

**第四轮：摘要压缩**
- 对最终候选节点执行压缩：
  - DiscourseBlock(域C) -> L2 Summary（话题级摘要）
  - ModuleState(域E) -> 只保留模块名+状态标记（去详细信息）
  - UserProfile(域P) -> 只保留与当前意图相关的维度
  - BehaviorPattern(域B) -> 只保留最近 N 条操作（去模式分析）
  - CausalEdge(域K) -> 只保留置信度 > 0.8 的因果边
- 检查预算 -> 仍超标则扩大候选范围（后 50%）并重复压缩

### 11.4 话题切换时的结构重组（三步降落法）

话题切换时，存在两组子图——旧话题子图和新话题子图。
不能让旧话题子图直接消失（会丢失上下文连续性），也不能让它完整保留（预算爆炸）。

三步降落法：

**Step 1: 旧话题摘要压缩**
- 旧话题的 DiscourseBlock -> L2 Summary（保留话题锚点：主题是什么、讨论到了哪个深度）
- 旧话题的 cross_ref 指针保留（指向新话题中与之相关的节点）
- 代价：旧话题从完整内容变为 1-2 句摘要（约 50 tokens/话题）

**Step 2: 结构保活**
- 保留连接器节点：betweenness > 0.6 的节点不做摘要压缩
- 即使它们属于旧话题（结构完整性优先于时效性）
- 代价：这些节点保持完整内容（约 30-50 tokens/节点）

**Step 3: 新话题展开**
- 新话题的子图按默认策略展开（2-3 跳）
- 保留与新话题关联的旧话题 cross_ref 指针
- 检查预算：如果新话题展开后仍超预算，对新话题自身执行四轮修剪(11.3)

### 11.5 与 ColdIndexer 回升机制的关系

四轮修剪是 ColdIndexer 回升机制的镜像逻辑：
- 回升：把冷存储节点拉回热图（因被访问而激活）
- 修剪：把热图节点压缩为冷锚点（因预算限制而降级）

二者共用同一套 importance/activation/recency 评分体系。
区别仅在于阈值方向——回升是低->高，修剪是高->低。

### 11.6 用户可察觉性

修剪不是对用户透明的——用户可能注意到某些旧话题被压缩了。

处理方式：

1. 预算紧张时，在回答末尾追一条系统标记：
   由于上下文预算限制，已压缩 3 个旧话题节点。如需展开某话题，可以说详细说说XX。
2. 用户画像记录 context_overflow_behavior：
   用户在被压缩后追问被压缩话题的比例。
   高频 -> 自动提升该用户的默认预算上限。
