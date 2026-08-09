# 规划设计文档全面精读（第二轮）

> 日期: 2026-08-03 | 精读对象（8 篇，5655 行）:
> `BUSINESS_CHAIN_1.5_PLANNING.md`（212）+ `BUSINESS_FLOW_TASK_PLANNING.md`（216）+
> `v3.0/DESIGN_PLANNING_SKILL_LAYER.md`（1594）+ `v3.0/DESIGN_TASK_PLANNING_DYNAMIC.md`（1343）+
> `v3.0/ENGINEERING_PLANNING_SKILL.md`（1501）+ `v3.0/DESIGN_PERSPECTIVE_PLANNER.md`（355）+
> `v5/PLANNER_CONTEXT_AND_REST.md`（185）+ `v5/PLANNING_GAP.md`（28）
> 配套: `AUDIT_ENTRY_20260803.md`（一轮盘点）+ `DEEP_AUDIT_20260803.md`（实锤验证）
> 本文档 = 设计全貌凝练 + 设计↔代码对照 + 待讨论点。

---

## 一、业务链 1.5 章精读（BUSINESS_CHAIN_1.5_PLANNING.md，212 行）

### 1.1 定位与核心命题

```
位置: 链 1.5（PCR/意图之后，执行之前）
核心命题: IntentParser 告诉你"用户想要什么"——
          Planning 告诉你"系统应该怎么给"。
          不是选模板——是 LLM 自主生成可执行的 TaskGraph。

数据流: PCR(expectation→execution_mode, cognitive→偏置) + Intent(ParseResult/entities)
  → SkillMatcher(意图→Capability Blueprint) → SkillEngine → Planner(策略·TaskGraph)
  → ToolShortList → DynamicPlanner(LLM) → CognitiveScheduler(谁·何时·优先级)
  → 任务图 → 链02 LLM 执行；DistillationEngine → SkillRegistry（长期记忆）
```

### 1.2 5 个核心组件 + 5 策略

```
组件: SkillMatcher / Planner / CognitiveScheduler / DistillationEngine / ToolShortlister
策略（StrategySelector 动态选择）:
  RULE_BASED(固定模板, 0-2ms) / TEMPLATE(Blueprint 匹配, 2-5ms) /
  HYBRID(规则+LLM, 10-50ms) / LLM_DRIVEN(LLM 自主生成, 100-500ms) / RECOVERY(降级上一条)
PCR 调控: execution_mode=FAST_EXECUTE → RULE_BASED；DEEP_RESEARCH → LLM_DRIVEN

Capability Blueprint: {Goal, Constraints(引用工程链), Strategy, Action Graph(语义动作序列,
  独立于执行器), Verification(引用约束引擎), Reflection(引用假设引擎)}

CognitiveScheduler: Fast(<10ms 规则/缓存) / Slow(100-500ms LLM/工具, 异步) /
  Background(秒级 蒸馏/清理, 后台线程) → Worker Pool

Skill Lifecycle（双轨蒸馏）:
  External Track: API Doc(OpenAPI/Swagger) → 导入 → Capability Blueprint
  Internal Track: 运行记录 → 重复模式 → Candidate Pool → 多维评估(success_rate≥95%,
    usage_count≥10) → Verified → Core(默认启用) → Deprecated(技术过时)
```

### 1.3 代码↔设计映射与接入现状（设计自述）

```
设计 20 篇完整；代码 ~10000 行 · 6 包 · 30+ 文件
引擎已接入: ✅ PerspectivePlanner + ✅ CausalPlanner
引擎未接入（代码完备）: ❌ Planner(5策略) / SkillMatcher / SkillEngine /
  CognitiveScheduler / DistillationEngine / DeciderState+WAL
有效实现率: ~5%（仅 PerspectivePlanner 被引擎使用）
PCR 信号未流入: expectation→strategy, cognitive→skill 偏置
```

### 1.4 与 2026-08-03 审计的印证

```
✅ 印证: 设计自述"核心未接 + 5% 有效实现率" = 审计发现（_planner 恒 None、
  20 测试失败、orchestrator 仅用 PlanningSkill）
⚠️ 新增: 设计声称的 v4/skill_layer（8 文件·481 行）实际只有 models+__init__（断链壳）；
  distillation_engine.py 在 core/agent/planner/（v4 下不存在）——设计文档自己引用了错路径
```

---

## 二、BUSINESS_FLOW_TASK_PLANNING.md 精读（216 行，前端溯源）

### 2.1 性质

```
非规划本体设计，是 TaskPlanningPage（前端 React Flow）业务流溯源：
核心 = 前端双状态 bug 根因分析 + 修复方案。
```

### 2.2 问题根因矩阵

```
致命问题: TaskPlanningPage.nodes（从 store 重算, useEffect 覆盖）vs
          TaskFlow 内部 useNodesState（用户操作）——两组 nodes 互不同步
1. 拖动松手回弹: useEffect#2 每次 rfNodes 变化覆盖位置（357 行）
2. 添加节点不显示: store 更新→rfNodes 重算→useEffect#2 覆盖（357+432）
3. 连线无效: handleConnect 只更新 store 不更新 TaskFlow 内部 edges（397）
4. 删除偶尔有效: Backspace 同时更新 store+内部状态（时序竞争）
5. "瞬间可用": useEffect#2 两次触发窗口期（时序）
6. 切页数据丢失: taskStore 不持久化 + PUT 可能未保存（架构）

修复方案: 删 useEffect#2，nodes 仅在首次加载设置一次，之后完全由 ReactFlow 内部状态管理
```

### 2.3 后端链路（规划相关）

```
GET/PUT /v3/session/{id}/task-graph → data/task_graphs/{id}.json
POST /v3/session/{id}/message → Phase 5: BlueprintEngine.build() → task_graph（另存）
→ 后端 task-graph 产出方 = BlueprintEngine（蓝图），非 planner/（规划包）
```

> 待讨论: 前端 task-graph 的产出方是 BlueprintEngine（v3_session_api Phase 5），
> 而规划包（planner/）的 TaskGraph 从未产出到前端——两套任务图体系并存。

---

## 三、待精读（4 篇大文档 + 2 篇 v5）

```
下一批: DESIGN_PLANNING_SKILL_LAYER.md（1594）→ DESIGN_TASK_PLANNING_DYNAMIC.md（1343）
       → ENGINEERING_PLANNING_SKILL.md（1501）→ DESIGN_PERSPECTIVE_PLANNER.md（355）
       → v5/PLANNER_CONTEXT_AND_REST.md（185）→ v5/PLANNING_GAP.md（28）

---

## 四、主设计精读: DESIGN_PLANNING_SKILL_LAYER.md（1594 行）

### 4.1 核心命题与动机

```
核心命题: Planning ≠ Tools——任务规划方法与工具集是独立正交的抽象层。
动机（v1.0 DynamicPlanner 失效场景）:
  工具孤岛（20 零散 API 无业务关联）/ 业务领域知识缺失（电商流程漏步骤）/
  复杂认知模式缺失（论文写作线性化）/ 合规约束（金融顺序）/ 零工具场景
用户核心诉求: 爬取大量 skill 抽象为通用规划逻辑 → 其他用户只提供 API+功能 →
  LLM 按通用逻辑+自我判断+API 信息规划任务

文献支撑: ReAct/CoT/ToT/Plan-and-Solve/Reflexion（原语）| AutoGPT/LangGraph/CrewAI/
  OpenAI Assistant（工程）| "Understanding Planning of LLM Agents"（五维分类）
```

### 4.2 正交分层（规划层 / 工具层 / 绑定层）

```
规划层: 通用原语(17个) + 领域 Skill(30-50个) + 混合编排引擎 → TaskGraph 拓扑（工具名=占位符）
工具层: Built-in / API Doc / MCP Tools → "有哪些工具、如何调用"
绑定层: 占位符 → 实际工具（语义相似+标签匹配+参数兼容）
设计原则: Planning 不依赖工具 / Skill 不依赖工具 / 工具可独立替换 / 运行时动态绑定
```

### 4.3 通用规划原语（17 个，五维分类）

```
分解: SequentialDecomposition / HierarchicalDecomposition / DivideConquer
分配: SingleAgent / ParallelMap / RoleBasedCollaboration
排序: SequentialFlow / ConditionalBranch / LoopUntil / PriorityQueue
资源: SearchRetrieve / SearchVerifyExecute / MemoryAugmented
反思: PlanExecuteReflect / TreeOfThought / ReflectRetry / EarlyTermination
每个原语 = {元信息, 拓扑模板, 参数化接口(占位符), 约束规则} + generate_skeleton()
（P1/P2/P3/P4/P5 有完整代码级定义，其余以清单形式）
```

### 4.4 PlanningSkill 定义 + 预置 Skill

```
PlanningSkill = {skill_id, name, description, domain_tags, intent_categories,
  primitives(原语组合), step_templates(占位符 TaskNode), tool_hints(推荐标签),
  constraints(前序/不变量), level(SKELETON/STANDARD/DETAILED), usage_count, success_rate}
match_intent: 意图类别 0.4 + 领域标签 0.3 + 关键词 0.3
预置 Skill 示例: 电商下单(7 步, DETAILED) / 数据分析(6 步, STANDARD) /
  代码生成调试(8 步, DETAILED, 含条件分支)
Skill 生态: 系统预置 30-50 + 开源社区 + 用户自定义 + LLM 自动生成 + 工作流导入
```

### 4.5 Mixed Planning Engine（三模式 + 决策树 + 回退）

```
三模式:
  DYNAMIC: 无 Skill，LLM 用原语库自主规划（自由度高，可能漏步骤）
  SKILL_ENHANCED: Skill 骨架 + LLM 可调步骤（领域知识+灵活性）
  MIXED: Skill 严格骨架(不可修改) + LLM 只填工具名/参数（合规最强）

决策树: 高匹配>0.8 → DETAILED→MIXED / 其他→SKILL_ENHANCED
        中匹配>0.5 → 高元认知(>0.7)→DYNAMIC / 低→SKILL_ENHANCED
        无匹配 → DYNAMIC
画像调优: 高元认知→DYNAMIC / 高发散→SKILL_ENHANCED / 低g→SKILL_ENHANCED /
  domain 标签精确匹配→强制 SKILL_ENHANCED
回退链: MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK

ToolBindingEngine 5 策略: 精确名(0.9) / tool_hints(0.7) / 语义相似(>0.7) /
  参数兼容 / 人工确认（失败→ask_user）
EnhancedToolShortlister: Skill tool_hints 提升工具排名(+0.15)
```

### 4.6 画像联动（7 维度）

```
元认知→模式偏好 | 发散性→原语选择 | 追踪深度→Skill 匹配阈值 |
技术标签→原语复杂度 | 领域标签→Skill 匹配 | g 因子→计划复杂度容错 |
时间衰减→Skill 使用频率 boost
```

### 4.7 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 17 原语库 | `planner/` 无 PrimitiveLibrary 类（rg 未见）| ❌ 未实现 |
| MixedPlanningEngine | 无对应类 | ❌ 未实现 |
| ToolBindingEngine | `tool_registry/binding.py`（有 bind/shortlist 雏形）| ⚠️ 部分（需核对）|
| PlanningSkill 数据模型 | `v4/skill_layer/models.py`（CapabilityBlueprint 近似）| ⚠️ 断链（见 DEEP_AUDIT）|
| 三模式执行 | `planner/planner.py`（5 策略: RULE/TEMPLATE/HYBRID/LLM/RECOVERY）| ⚠️ 语义对应但结构不同 |
| 预置 Skill | 未发现（skill_registry 为空注册表？）| ❌ |

> 结论: 主设计（原语库/混合引擎/绑定）整体未落地；现有 `planner/` 是 v1.0 风格的
> 5 策略实现（业务链 1.5 章映射），v1.5 正交分层设计停留在文档层。

---

## 五、动态规划精读: DESIGN_TASK_PLANNING_DYNAMIC.md（1343 行，v1.0）

### 5.1 问题诊断与目标

```
问题: 静态 Blueprint 是瓶颈
  ① Blueprint(frozen dataclass, 预定义工具序列, 启动校验, LLM 只能选不能发明)
  ② _map_atomic_intent 固定字典（新增工具需改代码）
  ③ _build_task_graph 预设模板（无法动态调整）
用户痛点: "给一个 API 接口文档，系统就能自动规划任务，不需要改代码，即插即用"

目标: "从静态编排到动态发现——LLM 看到什么工具，就能规划什么任务"
  API 文档即注册 / 意图驱动筛选 / LLM 动态规划 / Schema 守卫执行
文献: ToolACE(ICLR2025) / ToolRegistry / MCP / OpenAPI-to-MCP / Tool Shortlisting /
  "Understanding Planning of LLM Agents"(561 引用)
```

### 5.2 五大核心模块（v1.0 体系）

```
① ToolRegistry（单例）: 运行时注册/注销/热更新；ToolSchema（name/description/parameters/
  required/source/type/endpoint/method/latency/cost/auth/destructive）；tag/source 双索引；
  schema_hash 变更检测；EMA 统计（call_count/success_rate/avg_latency）
② APIDocPreprocessor: OpenAPI3.1→Swagger2→JSON Schema→Natural Language→curl 五格式；
  参数扁平化；工具名前缀 source_id+operation；语义增强（POST/PUT/DELETE→destructive+领域标签）
③ ToolShortlister: 多级漏斗（意图标签粗筛→语义精排→历史 boost→容量截断(32)→兜底 ask_user/finish）
  boost 公式: success_rate * min(1, call_count/10) * 0.1
④ DynamicPlanner: LLM 自主生成 JSON TaskGraph（3 候选 temperature 0.2/0.5/0.8 →
  4 维反思评分: 工具存在/参数完整/DAG 有效/意图覆盖 → 白名单+循环检测验证 → fallback ask_user）
⑤ SchemaGuard + ToolExecutor: 必填参数/类型/枚举验证；LOCAL/HTTP/MCP 三后端分发 + 统计记录

集成: IntentParser._build_task_graph 改动态优先（use_dynamic_planning 开关），
  静态 Blueprint 保留为 fallback
```

### 5.3 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| ToolRegistry | `tool_registry/`（permission/binding/models 等）| ✅ 实现（部分核对）|
| APIDocPreprocessor | `engineering/api_doc_preprocessor.py` | ✅ 实现（工程链审计已验: 基础解析可用）|
| ToolShortlister | `planner/strategy_selector.py`（近似）| ⚠️ 语义对应（复杂/置信/成本评分，非标签漏斗）|
| DynamicPlanner | `planner/llm_planner.py`（2.7KB 轻量）+ planner.py _plan_llm_driven | ⚠️ 简化版 |
| SchemaGuard/Executor | `execution/engine.py`（工具执行）+ `tool_registry/binding.py` | ⚠️ 分散 |
| IntentParser 动态集成 | `_build_task_graph` 现状待核对（v3_common/intent_parser.py 3000 行）| ⚠️ |

> 结论: v1.0 动态规划设计的组件有分散实现，但**主链路（API 文档→注册→筛选→LLM 规划→执行）
> 未在 runtime/engine 或 orchestrator 中串起来**（与业务链 1.5 章"核心未接"一致）。

---

## 六、工程文档精读: ENGINEERING_PLANNING_SKILL.md（1501 行）

### 6.1 六组件实现规范（v3.0 规划层）

```
PlanningSkillEngine（中央控制器）:
  plan_and_execute 六步: 技能匹配 → 任务分解 → 依赖 DAG → 智能体分配 → 执行调度 → 结果编译 CT
  replan 三类型: skill_mismatch(重匹配) / dependency_error(重解析) / execution_error(重试/降级)
SkillMatcher: 关键词 0.4 + 语义 0.4 + 上下文 0.2；模板阈值 0.5
  → use_template=True 快路径(<50ms, 80% 场景) / False 慢路径(2-5s, 20% 场景)
SkillTemplate: {name, keywords, tags, domain_tags, intent_categories, primitives,
  tool_hints, constraints, level, decomposition_pattern, subtasks, dependencies,
  retry_policy, timeout, fallback_skill}
SubtaskTemplate / RetryPolicy(max_retries=3, backoff=2.0) / Task(worker_type/input_data/deps)

PrimitiveLibrary: 17 原语中 7 个已实现（P1 SequentialDecomposition / P3 DivideConquer /
  P8 ConditionalBranch / P9 LoopUntil / P12 SearchVerifyExecute / P14 PlanExecuteReflect /
  P15 TreeOfThought），10 个占位（工程文档自述）
DecompositionEngine: LLM 分解 1s 超时 → 超时回退单任务(direct_execution, Answer-LLM)
AgentAllocator / DependencyResolver(DAG+拓扑+循环检测+关键路径) / ExecutionScheduler(并行/串行/重试/超时)
```

### 6.2 代码对照（实锤，含 P0 升级）

| 设计组件 | 代码 | 状态 |
|---|---|:--:|
| PlanningSkillEngine | `planner/skill_engine.py` 23.9KB | ✅ 类存在 |
| SkillMatcher | `planner/skill_matcher.py` 8.6KB | ✅ 类存在 |
| SkillRegistry | `planner/skill_registry.py` 13.8KB | ✅ 类存在 |
| DecompositionEngine | `planner/decomposition.py` 11.0KB | ✅ 类存在 |
| AgentAllocator | `planner/agent_allocator.py` 7.1KB | ✅ 类存在 |
| DependencyResolver | `planner/dependency_resolver.py` 8.5KB | ✅ 类存在 |
| ExecutionScheduler | `planner/scheduler.py` 14.0KB | ✅ 类存在 |
| **模型底座 models.py** | `planner/models.py` **0.7KB（本应 1197L）** | ❌ **被重导出壳覆盖 → 7 模块全炸** |
| **PrimitiveLibrary/7 原语** | `v3_0/planning/__init__.py` 引用但**全库无定义** | ❌ 断裂 |

> **P0（DEEP_AUDIT §一点五）**: `planner/models.py` 从 1197L 缩到 0.7KB =
> 原 20+ 模型丢失 → AgentAllocator/Planner/SkillEngine/Executor/Scheduler/
> SkillRegistry/StrategySelector 7 模块 import 全炸 → v3_0/planning 门面连带炸。

---

## 七、v5 库存文档精读（PLANNER_CONTEXT_AND_REST.md + PLANNING_GAP.md）

### 7.1 PLANNER_CONTEXT_AND_REST.md（185 行，2026-07-24 全模块库存）

```
planner/ 库存: 28f, 7,908L（models.py 1,197L 标注"核心"）
当时结论: "v6 当前用 llm_planner.py(66L) 仅薄封装，这个完整系统未接入"

十个未接入重量级系统（2026-07-24 快照）:
  1. planner/ 7,908L（仅 llm_planner 薄层在用）
  2. context/ 5,418L（未用，全走 discourse_block_tree.build_context）
  3. topic_tree/ 2,120L（未用）
  4. cognitive_scheduler/ 1,659L（未用）
  5. causal_substrate/ 270L（未用）
  6. 6LLM 实例（仅 DeepSeek 在用）
  7. v3_0/cognitive_tree 8,909L（未迁移）
  8. v3_0/observability 1,982L（telemetry/tracer 丢失）
  9. v4/world 42L stub
  10. engineering/ 知识图谱 812L（基础版在用）

重叠表: 规划+技能 → 选 planner/(7,908L)；上下文 → context/；话题树 → topic_tree/ 或 discourse 二选一
```

### 7.2 PLANNING_GAP.md（28 行，2026-07-21 已修复声明）

```
当时声称: 7 项全部修复，有效实现率 ~70%
  ✅ async plan 修复 / SkillMatcher 接入 / Scheduler 接入 / PCR 信号流入 /
     SkillRegistry 加载 DEFAULT_BLUEPRINTS
  ⚠️ DistillationEngine / ToolShortlister（下一轮）
```

### 7.3 时间线重构（包断裂是近期回归）

```
2026-07-21  PLANNING_GAP: 规划 70% 有效实现（Planner+SkillMatcher+Scheduler 已接入 on_event）
2026-07-24  库存文档: planner/ 28f 7,908L 完整（models.py 1,197L）
2026-08-xx  models.py 被替换为 v4 skill_layer 重导出壳（0.7KB）→ 7 模块 import 全炸
2026-08-03  审计实锤: 包断裂 + _planner 恒 None + orchestrator v3 路径连带炸

→ 规划模块的断裂不是"一直没接入"，而是"曾接入（70%）后被 v4 skill_layer
  迁移覆盖 models.py 导致整体回归"——与 PCR/行为链同型的"多代演进→分裂"。
```

---

## 八、规划模块设计精读完成度（8/8）

| # | 文档 | 核心结论 |
|---|--:|---|
| 1 | BUSINESS_CHAIN_1.5 | 定位/5 组件/5 策略/双轨蒸馏；自述 5% 有效实现率 |
| 2 | BUSINESS_FLOW_TASK_PLANNING | 前端双状态 bug + 后端 task-graph 由 BlueprintEngine 产出 |
| 3 | DESIGN_PLANNING_SKILL_LAYER | v1.5 正交分层/17 原语/三模式引擎 → 整体未落地 |
| 4 | DESIGN_TASK_PLANNING_DYNAMIC | v1.0 动态规划五模块 → 分散实现未串主链路 |
| 5 | ENGINEERING_PLANNING_SKILL | 六组件实现规范 → 类全部存在但 models.py 断裂 |
| 6 | DESIGN_PERSPECTIVE_PLANNER | 第三套规划（策略视角）独立存在 |
| 7 | PLANNER_CONTEXT_AND_REST | 库存: planner/ 7,908L 完整曾未接入；models.py 1,197L |
| 8 | PLANNING_GAP | 07-21 曾 70% 实现 → 08-xx 被 models.py 覆盖回归 |

> 规划模块两轮审计完成（AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ 八节）。
> P0 清单: ① models.py 恢复（git 找回）② v4 skill_layer 壳清理 ③ 三套规划归一。
```
