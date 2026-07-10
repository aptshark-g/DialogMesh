# 交互模型设计：Event Layer + Multi-Projection

> 定义对话树、行为链、因果链、工程链与底层事件系统的关系。
> 解决的核心问题：四条链不应该嵌入对话树的边——它们应该是同一事件流的不同视图。

---

## 1. 核心原则：统一协议，不统一表现形式

Linux 不要求所有程序变成一种形式，只要求它们遵循系统调用接口。
DialogMesh 遵循同一原则：不同交互模态（文本、UI操作、图像、音频）产生不同类型的事件，但都通过统一的 Adapter 转化为底层 Event，然后由不同的 Projection 解释为各自的视图。

`
                Event Log (唯一事实源)
                      |
               Event Processor
                      |
        ┌─────────────┼─────────────┐
        |             |             |
  Conversation    Operation    Engineering
   Projection     Projection    Projection
   (对话树视图)   (操作树视图)   (工程图视图)
        |             |             |
        └─────────────┼─────────────┘
                      |
               Cognitive Layer
        (Memory / Planning / Behavior)
`

---

## 2. 三层架构

### 2.1 Event Layer（事件层：事实）

系统的唯一事实源。只追加，不可变。类比 Git commit / 数据库 WAL。

Event 只有两种类型：
- UserAction：用户做了什么（说话、点击、拖拽、上传图片）
- SystemAction：系统做了什么（生成回答、执行工具、注册模块）

重要约束：Event 不包含推断结果。TopicSwitch、ConstraintUpdate、ProfileUpdate 不是 Event——它们是 Projection 层的推断产物。

### 2.2 Projection Layer（投影层：解释）

从 Event Log 中生成的多种视图。同一组 Event 可以投影到不同的 Projection。
每个 Projection 有自己独立的数据结构和查询语义，互不冲突。

当前 Projection 类型：

**Conversation Projection（对话树）**
- 数据结构：树（DiscourseBlockTree），含跨分支指针
- 回答的问题：语段之间有什么语义连贯关系？
- 节点含义：语段块（DiscourseBlock），按话题聚合
- 边含义：follow_up（承接）、elaborate（细化）、switch_to（切换）
- 何时更新：每次对话轮次

**Operation Projection（操作树）**
- 数据结构：树
- 回答的问题：用户对系统做了什么操作？操作之间的时序关系？
- 节点含义：操作事件（点击、拖拽、配置变更、任务重组）
- 边含义：before/after（时序）、triggers（触发）
- 何时更新：每次非对话交互事件

**Engineering Projection（工程图）**
- 数据结构：图
- 回答的问题：系统自己的模块状态如何？哪些模块缺监控/缺翻译？
- 节点含义：模块、配置项
- 边含义：depends（依赖）、monitors（监控）、translates（翻译覆盖）
- 何时更新：模块注册/卸载/配置变更

### 2.3 Cognitive Layer（认知层：推理）

在所有 Projection 之上，执行跨视图推理。三链（行为链/因果链/工程链）统一为 Event Chain，通过 source 字段区分来源。

Event Chain 不是独立的数据结构——它是 Event Log 按 source 过滤后的逻辑视图：
- source=User：用户行为链
- source=AI：系统回答链
- source=System：系统内部操作链

---

## 3. Adapter 模式：多模态输入的统一入口

不同交互模态通过 Adapter 转化为统一的 Event：

`
文本输入  → TextAdapter    → UserAction Event
UI 操作   → UIAdapter      → UserAction Event
图片上传  → VisionAdapter  → UserAction Event
语音输入  → AudioAdapter   → UserAction Event
`

核心系统不感知输入模态。它只知道 Event。
新增交互模态 = 新增一个 Adapter——不影响核心 Pipeline。

---

## 4. 链与树的关系：注解层，不是嵌入层

之前的设计问题：行为链/因果链/工程链是不是对话树的边属性？

结论：不是。

正确的设计：
- 树的边只表示语义关系（follow_up、elaborate、switch_to）
- 链是对关系的注解（Annotation）——不是关系的属性
- 同一条关系可以有多个注解（行为注解、因果注解、工程注解）

`
关系 R（A follow_up B）：
  注解1（行为链）：用户倾向于在 B 之后追问细节
  注解2（因果链）：B 的引入是因为 A 中提到了性能问题
  注解3（工程链）：系统根据 A 自动创建了监控表
`

好处：
- 树的边保持简洁（只表达语义关系）
- 链可以独立演化，不膨胀树的边属性
- 新增链类型不影响现有树结构

---

## 5. 双轨制：时序 + 语义

对话树和 Event Log 是互补的双轨：

**第一轨（Event Log）：时序事实轨**
- 只记录发生了什么，不解释
- 永远按时间顺序排列
- 不可修改

**第二轨（Projection 层）：语义结构轨**
- 从 Event Log 生成，可按理解重组长
- 可以随着新理解变化（past reinterpretation）
- 不同 Projection 有不同的组织逻辑

这和人类记忆一致：经历（事件）不能修改，但对经历的解释可以变化。

---

## 6. 与现有设计的关系

| 现有模块 | 新模型中的位置 | 变化 |
|:---------|:---------------|:-----|
| DiscourseBlockTree | Conversation Projection | 不变 |
| TopicTreeManagerV2 | Conversation Projection 的管理器 | 不变 |
| BehaviorGraph | Behavior Model (Cognitive Layer) | 不再作为树的边属性 |
| CausalSubstrate | Cognitive Layer 的因果注解 | 不再作为树的边属性 |
| EngineeringGraph | Engineering Projection | 独立视图 |
| EventLog / session_recorder | Event Layer | 升级为唯一写入入口 |
| Predictor / Rewarder | Behavior Model 的可插拔组件 | 降级 |
