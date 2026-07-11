# RFC: EngineeringChain — 工程约束推理系统

> 定义工程链的七类节点、边类型、约束推理机制。
> 工程链不记录历史——它回答：如果系统发生变化，还有哪些地方必须跟着变化。

> 版本: v1.0 | 日期: 2026-07-10

---

## 目录

1. 定位：工程链和其他链的本质区别
2. 七类节点
3. 边类型（正边 + 负边）
4. 约束推理引擎
5. Pattern Library（工程模式库）
6. 与 ContextCompiler E 域的对接
7. 实现计划

## 1. 定位：工程链和其他链的本质区别

| 链 | 回答的问题 | 节点是什么 | 边的语义 |
|:---|:---|:---|:---|
| 对话树 | 当前在聊什么话题 | 话语块 | 承接/细化/切换 |
| 行为链 | 用户做了什么 | 操作事件 | 时序/模式 |
| 因果链 | 为什么这个关联存在 | 因果边 | reason/corrects |
| **工程链** | **如果系统变化，什么必须跟着变** | **约束/模式/决策/质量** | **requires/improves/violates** |

核心区别：其他链是认知链（描述事实）。工程链是约束推理链（描述不变量）。

它不是代码索引，不是模块关系图，不是依赖树。
它是一个可演化的工程知识库：记录约束、设计决策、模式、反模式和架构代价。

当 LLM 需要执行工程操作时，它不是去检索提示词——而是沿工程链做推理：
这个修改触发什么约束？应套用什么模式？会影响什么质量属性？哪些历史决策需要重审？

## 2. 七类节点

### 2.1 Constraint（约束——不变量）

定义：描述一类组件必须满足的条件。不是代码实现的属性，是工程级别的强制要求。

`
Constraint: Every Provider must expose Metrics
  evidence: OpenAIProvider(v), ClaudeProvider(v), GeminiProvider(v)
  violates: []
`

当新模块属于 Provider 类型时，LLM 沿 Constraint 边自动推断：该模块也需要 Metrics。

### 2.2 Rule（管道规则）

定义：描述组件在流程中的位置约束。不是依赖关系——是顺序约束。

`
Rule: RateLimit must be placed before Auth
  applies_to: Gateway pipeline
  reason: Prevent unauthorized requests from consuming rate quota
`

和普通边不同——depends_on 只说谁依赖谁。Rule 说的是谁必须在谁前面。

### 2.3 Pattern（工程模式）

定义：可复用的架构模板。描述完成某类工程操作需要的标准组件组合。

`
Pattern: Plugin Pattern
  template: Interface + Factory + Registry + Lifecycle
  derived_modules: [OpenAIProvider, ClaudeProvider, GeminiProvider]
`

当 LLM 需要新增 Plugin 时，不是猜——是沿 Pattern 找到模板，按模板生成。

### 2.4 AntiPattern（反模式——禁止边）

定义：明确不能建立的连接。用负边表示。

`
AntiPattern: Controller must NOT directly access Database
  violates: [UserController->Database, OrderController->Database]
  correct_path: Controller -> Service -> Repository -> Database
`

这是工程知识中最有价值但最容易被忽略的一类——知道什么不能做。

### 2.5 Decision（架构决策记录）

定义：记录一个工程决策及其上下文、权衡和影响。

`
Decision: Use Event Bus for module communication
  reason: Loose Coupling
  tradeoff: Latency +1, Debug Difficulty +2
  benefit: Scalability +4
  context: [applies_to: Gateway, influenced_by: ScalingPlan]
`

### 2.6 QualityAttribute（质量属性）

定义：量化每个模块对系统质量维度的影响。

`
QualityAttribute: RateLimiter
  Performance: +0.4 (prevents overload)
  Complexity:  +0.2 (adds config surface)
  Reliability: +0.3 (circuit-break integration)
`

### 2.7 Module（模块——实际系统组件）

定义：实际存在于工程中的模块。和其他六类节点通过边关联。

`
Module: Gateway
  status: monitor_missing, translation_ok, tests_3of5

## 3. 边类型（正边 + 负边）

| 边类型 | 方向 | 含义 | 示例 |
|:---|:---|:---|:---|
| requires | A -> B | A 必须满足 B | Provider -> Metrics(Constraint) |
| depends_on | A -> B | A 依赖 B | RateLimiter -> Auth |
| implements | A -> B | A 实现了 B | Gateway -> Health(Constraint) |
| violates | A -> B | A 违反了 B | Controller -> Database(AntiPattern) |
| improves | A -> B | A 提升了 B | RateLimiter -> Reliability +0.3 |
| derived_from | A -> B | A 衍生自 B | DeepSeekProvider -> PluginPattern |
| generated_by | A -> B | 自动生成边 | Module -> Decision 自动演进 |

正边：requires, depends_on, implements, improves, derived_from
负边：violates（禁止连接）

## 4. 约束推理引擎

核心查询接口（供 CrossDomainExpander E 域使用）：

1. get_constraints_for(module_type):
   给定模块类型 -> 返回所有 applicable Constraints
   例: get_constraints_for(Provider) -> [must have Metrics, must implement Health]

2. get_pattern_for(operation):
   给定操作类型 -> 返回匹配的 Pattern
   例: get_pattern_for(add_plugin) -> Plugin Pattern

3. get_impact(change):
   评估一个变更对 QualityAttribute 的影响
   例: 添加 RateLimiter -> Performance +0.4, Complexity +0.2

4. check_anti_patterns(proposed_connection):
   检测提议的新连接是否违反 AntiPattern
   例: Controller -> Database -> violated (must go through Service)

5. get_related_decisions(module):
   查询影响该模块的历史架构决策

推理链示例（LLM 加 RateLimiter）：

`
Operation: add module RateLimiter(type=Middleware)
  -> Constraint: Every Middleware must expose Metrics -> add Metrics
  -> Pattern: Middleware Pattern includes config, lifecycle -> follow template
  -> Rule: Middleware must be before Auth -> place correctly
  -> AntiPattern: Middleware cannot bypass Auth -> do NOT skip
  -> Quality: Performance +0.2, Observability +0.5 -> show cost/benefit
`

## 5. Pattern Library（工程模式库）

预置的工程模式集合，随 Observation -> Knowledge -> Skill 蒸馏演化。

初始预置（来自常见工程实践）：

| Pattern | 模板组件 | 触发条件 |
|:---|:---|:---|
| Plugin Pattern | Interface + Factory + Registry + Lifecycle | add_plugin |
| Middleware Pattern | Config + Metrics + Health + Retry | add_middleware |
| Service Pattern | Interface + Impl + Repository + Tests | add_service |
| Pipeline Pattern | RateLimit + Auth + Business + Logger | add_gateway_module |

演化机制：用户连续 N 次以相同模式执行操作 -> 自动蒸馏为 Pattern ->
进入 Candidate -> 经使用验证 -> 提升为 Verified Pattern。

## 6. 与 ContextCompiler E 域的对接

Domain E (Engineering) 通过以下查询向 ContextCompiler 提供数据：

1. 模块状态快照（Module 节点 + 完整性检测）
2. 约束推理结果（get_constraints_for 的输出）
3. Pattern 匹配结果（get_pattern_for 的输出）
4. 质量影响评估（get_impact 的输出）

这些信息通过 CrossDomainExpander 编译到 Context IR 的 E 域条目中。

## 7. 实现计划

| 文件 | 内容 | 预估行数 |
|:---|:---|:---|
| engineering_chain/models.py | 七类节点 + 边类型定义 | ~150 行 |
| engineering_chain/registry.py | 模块注册/卸载 + 约束检查 | ~120 行 |
| engineering_chain/constraint_engine.py | 约束推理查询接口 | ~100 行 |
| engineering_chain/pattern_library.py | Pattern 预置库 + 匹配查询 | ~100 行 |
| engineering_chain/monitor.py | Pipeline Trace 日志 | ~50 行 |
| Total | | ~520 行 |

---

> 工程链和其他链的本质区别：它不是描述发生什么，
> 而是描述如果变了什么必须跟着变的约束推理链。
