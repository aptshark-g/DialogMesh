# Chapter 2：关系不是提示词能给的

> 提示词可以告诉 Agent 一条规则。
> 但它无法告诉 Agent：这条规则和谁相关、从哪来、什么时候会变。
>
> 关系是一种比文本更难传递、却更稀缺的上下文资源。

---

## 一、一个让 Agent 尽职但不尽责的瞬间

你在做一个网关项目。模块链路很简单：

`
Gateway → Auth → Logger
`

每个模块都有监控埋点。你让 Agent 在 Auth 和 Logger 之间加一个新模块
RateLimiter。Agent 写好了代码，测试通过，提交了。

一周后你发现：Auth 和 Logger 都有监控，但 RateLimiter 没有。

Agent 完美执行了你的指令。它不知道的不是 Prometheus 怎么用。它不知道
的是：

`
在这个项目里，
  Auth 有监控
  Logger 有监控
→ 新模块也该有监控
`

这条约束不在 Auth 的代码里，不在 Logger 的文档里。它在 Auth 和 Logger
之间那条看不见的关系里。

**Agent 没有被要求做错事。它只是没有被告诉：这个世界上有哪些关系。**

## 二、提示词的边界

你当然可以把这条约束写进 system prompt：

  项目规则：所有模块都需要添加监控埋点。

这能解决问题吗？能，这一次。

下一次加新模块，你又要重复。下一次换了会话，约束丢了。下一次换了一个
表达方式，Agent 可能识别不出来这是同一条规则。

提示词持续化不是一个技术难题。Cursor Rules、Project Instructions、
System Prompts 都在做这件事。规则可以持久化。

但关系不行。

为什么？

提示词适合描述的是：所有模块都需要监控。一条全局规则。

但当系统复杂到 100 个模块时：A 依赖 B，B 继承 C 的规范，D 是例外，
E 需要特殊处理。这些规则文本被平铺在 system prompt 里，
LLM 需要在每次推理时重新从文本中读出关系。

规则可以写。关系需要长出来。

一个模块加了监控之后，这条模块到监控的依赖不是一段文本。它是一个关系
边。它不随对话结束而消失。下次加任何模块，系统自动看到：它的左右邻居
都有监控。

你不需要再写一次规则。因为关系的存在本身就是规则。

## 三、让 LLM 看到关系

第一章我们讲了我们用树而不是图来组织对话记忆。这一章要讲的是：
组织好了，然后怎么给 LLM？

目前的事实是：对话树建好了，行为图建好了，因果链建好了，用户画像建好了。
它们各自正确运行。但它们从来不进入 LLM 的视野。

LLM 收到的，始终是扁平化的对话文本。扁平文本没有指针，没有域边界，
没有关系。

DialogMesh v4 的方向是：把多个域的信息编译为一个带跨域引用的子图，
再传给 LLM。

不是让 LLM 自己去图上走。那不是 Transformer 的运作方式。

是把原本隐含在系统结构中的关系显式化，转换成 LLM 可消费的上下文表示。

以前，LLM 看到的：添加 RateLimiter 模块，放在 Auth 和 Logger 之间。

以后，LLM 看到的：

  RateLimiter
    位置: Auth 和 Logger 之间
    工程约束: 上下游都有监控
    行为约束: 过去3次加模块都手动补了监控
    结构约束: 链路中间节点继承两端规范

区别在哪？不是 LLM 被提醒了要加监控。是它收到了足够稠密的关系信息，
自己走到了那个结论。减少了它推断关系的成本。

---

## 四、关系可以迁移

文本的另一个局限：不可泛化。

你给 Gateway 写了加监控的规则。但这条规则和 Gateway 这个词绑死了。
给 Database 加模块时，同样需要监控，但文本规则不会自动迁移。

关系可以。今天的 Gateway 需要监控。明天的 Database 需要监控。
泛化之后：Component 需要 Observability。

关系描述的不是这个模块的规则，是这类组件的约束。
这是文本本质上做不到的事：文本描述实例，关系抽象模式。

## 五、关系链的白盒化

还有一个更深的问题。

如果 LLM 这次漏了监控。在提示词方案里，你只能去改 system prompt。
改完之后你不知道它是不是真的学会了。

换个思路：用户在关系图里直接加一条边：
RateLimiter requires Monitoring。
这条边被持久化。下一次加任何模块，系统知道链路上游有它，下游有它，
新节点也该有它。

这比改 prompt 强在哪？
- 改一次永久生效，不需要每个会话重复
- 可以被审计，可以看这个模块缺哪条边
- 可以泛化，Gateway 的监控规则自动适用于 Database
- 可以被 LLM 之外的其他组件消费

这不是替代 prompt。提示词依然有自己的职责。
但关系图告诉 Agent：世界现在是什么结构。
它们是互补的。

## 六、还没实现，但方向确定了

坦诚说：这是 DialogMesh v4 的设计，部分概念正在验证，代码还没写完。

但写这篇文章的目的，不是因为代码写完了。是因为我们认为方向确定
比代码先行更重要。

如果方向是用更好的 prompt 弥补信息的碎片化，那 v3 就够了。
如果方向是把关系作为一等公民传给 LLM，那需要重新设计上下文编译管线。

我们选后者。

这不是 Prompt Engineering。
这是 Context Engineering。

---

## 附录：技术细节与设计思路

### 一、为什么关系不是文本擅长表达的对象

提示词持续化不是一个未解决的问题。Cursor Rules、Project Instructions、
System Prompts 都能将规则持久化并注入每次对话。

但关系有三个文本难以承载的特性：

**1. 关系的存在本身就是约束。** 当 Auth 和 Logger 都有监控时，
它们之间没有文本在说中间节点也该有监控。但关系图天然携带了这个拓扑约束。
文本需要你显式写出每一条规则。关系图不需要：结构本身在传递约束。

**2. 关系可以泛化。** Gateway 的监控规则写成文本是关联到 Gateway 的。
Database 不会自动继承它。但关系图可以提取模式：Component requires
Observability。这是 Prompt 做不到的抽象迁移。

**3. 关系随时间演化。** 一个项目开始只有 3 个模块。写了 3 条规则。
半年后 50 个模块了。3 条规则膨胀为 300 行上下文。LLM 需要在每次推理时
从 300 行文本中重新理解结构。关系图不需要：它只需要加载当前操作附近
k 跳的子图。

### 二、我们传给 LLM 的不是图，是经过编译的子图

一个常见误解：给 LLM 传图结构，意味着 LLM 需要能理解图。

不需要。Transformer 吃的是 token 序列。我们做的事：

1. 从多个信息域（工程链/对话树/用户画像/行为链/因果链）中选择与当前
   意图最相关的域
2. 在每个域中裁剪出当前任务需要的信息片段
3. 在片段之间建立跨域指针（cross_ref）
4. 序列化为 LLM 可消费的文本

LLM 收到的仍然是一段文本。但这段文本里每个信息片段都标注了它来自哪个
域、和哪些其他片段相关、以及关联的置信度。

### 三、五个上下文信息域

| 域 | 代号 | 回答的问题 |
|:---|:---|:---|
| 工程链 | E | 系统现在有什么模块、状态如何、依赖关系是什么？ |
| 对话树 | C | 当前话题是什么、讨论到了哪一层、还有什么相关话题？ |
| 行为链 | B | 用户最近做了什么操作、有什么操作模式？ |
| 因果链 | K | 为什么这个模块需要监控？和什么历史事件因果关系？ |
| 用户画像 | P | 用户的认知风格是什么、偏好什么交互方式？ |

### 四、当前实现状态

| 模块 | 状态 | 说明 |
|:---|:---|:---|
| 对话树 | 已实现 | DiscourseBlockTree，按话题组织对话 |
| 工程图 | 设计中 | EngineeringGraph，模块状态自检与依赖跟踪 |
| 用户画像 | 已实现 | CognitiveProfile 八维画像 |
| 行为图 | 已实现 | BehaviorGraph，四因子权重 |
| 因果链 | 部分实现 | CausalSubstrate 骨架匹配，do-calculus待补 |
| **跨域编译** | **设计中** | DomainSelector + BudgetAllocator + ContextSerializer |

当前传给 LLM 的仍是扁平对话文本。对话树只用于内部路由和话题切换检测。
跨域上下文编译管线是 v4 的核心目标。

### 五、已知局限

1. 跨域编译管线的性能开销尚未测量。多域索引、子图裁剪、跨域指针生成的
   端到端延迟没有基准数据。
2. Context IR 的序列化策略因 LLM 不同可能需要不同的适配格式。
3. 跨域信息的来源追溯（每段信息标注来自哪个 Event）已设计但未在输出层暴露。
4. 当子图超预算时，修剪策略（四轮电容+结构+时序+摘要）尚未在生产环境验证。

### 参考文献

1. Lewis et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 2020.
2. Packer et al. MemGPT: Towards LLMs as Operating Systems. arXiv 2023.
3. Microsoft. GraphRAG: Graph-based Retrieval-Augmented Generation. 2024.
4. Prathap, B. VeritasGraph: A Sovereign GraphRAG Framework for Enterprise-Grade AI. ICASF 2025.
5. M-FLOW: Cognitive Memory Engine. https://m-flow.ai/
6. Nous Research. Hermes Agent: Autonomous AI Agent with Persistent Memory. 2026.
7. Chen et al. MemWalker: Walking Down the Memory Maze. arXiv 2310.05029.
8. Xu et al. MRAgent: Automated Causal Knowledge Discovery via Mendelian Randomization. 2025.

---

> Chapter 2 结束。
>
> 下一章预告：当五个信息域的子图拼在一起，怎么决定每个域占多少预算？
> 什么样的意图匹配什么样的域组合？跨域指针如何让 LLM 看到一个统一的
> 信息网络而不是五个独立段落？
