# 工程链设计完整记录 — 约束空间与执行层

> 日期: 2026-08-03 | 性质: 设计精读完整记录（非审计）
> 组织框架（用户定义）: 工程链本质 = **约束空间**，与执行层强相关 ——
> 在回答/执行等内容产出时保证 LLM 契合具体约束情况。
> 配套: `AUDIT_ENTRY_20260803.md`（一轮现状）+ `DESIGN_IMPL_AUDIT_20260803.md`（二轮对照）

---

## 一、设计文档全景

| 文档 | 层级 | 核心内容 |
|---|---|---|
| `docs/BUSINESS_CHAIN_07_ENGINEERING.md` | v6 链规范 | 递归地图 + 七类节点 + 约束推理 + 白盒化 |
| `docs/v3.0/DESIGN_ENGINEERING_CHAIN.md` | RFC | 工程链定位、七类节点、边类型、推理引擎、Pattern 库 |
| `docs/v3.0/DESIGN_ENGINEERING_ONTOLOGY.md` | 本体层 | 类型/来源/生命周期/边规则权限矩阵/白盒接口/学习闭环 |
| `docs/v3.0/ENGINEERING_API_DOC_PREPROCESSOR.md` | 工程实现 | API 文档 → ToolSchema 的 6 组件管线 |
| `docs/DESIGN_EXECUTION_LAYER.md` | 执行层 | **七棵树并行，工程链 = ConstraintTree** |
| `docs/DESIGN_GLOBAL_STATE_MACHINE.md` | 状态机 | 工程链约束变化 → Event 驱动（防广播风暴）|
| `docs/DESIGN_CLI.md` §13 | 白盒 CLI | `dm engineering constraint/impact/propagate` 命令族 |
| `docs/BUSINESS_CHAIN_10_SUBGRAPH.md` | 子图 | 对话树子图 K 域（工程约束）占 20% token |
| `docs/DESIGN_RUNTIME_KERNEL.md` | 运行时 | P0 实时路径含安全约束检查（<10ms）|

---

## 二、工程链本质：约束空间

### 2.1 定位（三份文档一致的表述）
```
对话树: 描述事实 (发生了什么)
行为链: 描述操作 (用户做了什么)
因果链: 描述原因 (为什么这样)
工程链: 描述不变量 (什么必须成立)
```
- 「工程链回答: 如果系统变化, 什么必须跟着变?」
- **不是代码索引、不是模块关系图、不是依赖树** —— 是可演化的工程知识库。
- 其他链是认知链（描述事实），工程链是**约束推理链**（描述不变量）。
- 约束空间含义: 所有工程操作的合法域。当 LLM 执行工程操作时，
  不是检索提示词，而是**沿约束空间做推理**: 这个修改触发什么约束？应套什么模式？
  影响哪些质量属性？哪些历史决策需要重审？

### 2.2 与执行层的强关联（DESIGN_EXECUTION_LAYER）
- 执行层 = **七棵树并行**: Discourse / Execution / Constraint / Association / Behavior / Meta / Profile。
- **ConstraintTree = EngineeringChain**（规则、约束、文件/命令限制，轻量）。
- 七棵树共享: 节点格式、分支结构、渐进式摘要、归档机制；继承自 DiscourseBlockTree 基板。
- 树间通信是**查询驱动**（不是通知）: 需要约束时，ExecutionTree 主动 query ConstraintTree，
  类似多头注意力的 Q 向量；找不到时双方案并行（开子 Agent 探索 / 持久化层搜索）。
- **约束验证在管线主路径**: `ExecutionEngine — 7工具, 约束验证`（§8 管线完整路径）；
  PlanGate → ExecutionEngine → 子 Agent 完成 → MetaTree 归约 → LLM Answer。

### 2.3 约束空间如何保证 LLM 契合（回答时）
- 子图层: 对话树子图 K 域 = 工程约束 + 模式，占 20% token（BUSINESS_CHAIN_10）。
- 执行层: 每个执行动作先过约束验证（7 工具 + 约束验证）；违反 → MetaTree 回退插入。
- 元认知子图: E 域（Evidence）= 多链证据汇总，含「工程约束的一致性」，占 30% token。
- 状态机: `ConstraintViolated` 是 Event 层一等事件（E4），命令→Event→State 三阶段驱动。
- 白盒: 用户修改约束 → `dm engineering constraint add/remove` → Event Log → 学习管线。

---

## 三、七类节点（完整规格）

| 节点类型 | 判别属性 | 生命周期 | 来源 | 是否允许 LLM 自动创建 |
|---|---|---|---|:---:|
| Module | 事实性, 有 status, 可注册/卸载 | 无 | manual/auto | ✅ |
| Constraint | 强制性, 有 evidence 列表 | candidate→verified→deprecated | manual/derived/verified/core | ✅（learned 需人工确认）|
| Rule | 顺序性, 描述 pipeline 位置 | derived→verified→deprecated | manual/derived | ✅ |
| Pattern | 可复用性, 有 template 结构 | candidate→suggested→verified→deprecated | derived/learned（从重复实例蒸馏）| ✅ |
| AntiPattern | 禁止性, 有 correct_path | 无 | manual/core | **❌ 禁止 LLM 创建** |
| Decision | 追溯性, 有 tradeoff+benefit+context | 无（仅 manual/verified）| manual | **❌ 禁止自动生成** |
| QualityAttribute | 量化性, 有 impact_score | 无（随 Module 变化）| manual/derived | ✅ |
| Skill | 执行性, 可缓存可丢弃 | draft→verified→core→deprecated | derived（从 Pattern 蒸馏）| ✅ |

**关键约束**: AntiPattern 与 Decision 是人工领地 —— 前者因误判代价高，后者因需要追溯性。

---

## 四、边类型 + 权限矩阵（完整规格）

### 4.1 正边/负边
```
正边: requires / depends_on / implements / improves / derived_from / generated_by / extends
      / follows / precedes / influences / justifies / supersedes / instantiates / contains
      / references
负边: violates（禁止连接）
```

### 4.2 权限矩阵（部分关键行）
| from \ to | Module | Constraint | Pattern | Rule | Decision | Quality | AntiPattern | Skill |
|---|---|---|---|---|---|---|---|---|
| Module | depends_on | implements | implements | follows | NI | improves | **violates** | generated_by |
| Constraint | requires | NI | NI | NI | NI | NI | NI | NI |
| Pattern | derived_from | NI | extends | NI | NI | NI | NI | generates |
| Decision | influences | justifies | NI | NI | supersedes | NI | NI | NI |
| AntiPattern | NI | NI | NI | NI | NI | NI | related_to | NI |

NI = Not Implemented（不允许连接）。核心原则:
- Constraint 只能连 Module；Pattern 之间可 extends；AntiPattern 只能被 Module violates；
- Decision 可 justifies Constraint（解释约束来源）。

---

## 五、约束推理引擎（5 个核心接口 + 推理链）

```
① get_constraints_for(module_type)    输入"Provider" → [必须 Metrics, 必须 Health, 必须 API]
② get_pattern_for(operation)          输入"add_plugin" → Plugin Pattern {Interface+Factory+Registry}
③ get_impact_of_change(module)        输入"RateLimiter" → {affected_modules, violated_constraints, suggested_patterns}
④ check_violations(module, connection)输入(Controller, Database) → violates AntiPattern
⑤ get_related_decisions(module)       输入"Gateway" → 影响该模块的历史架构决策

推理链示例（LLM 加 RateLimiter）:
  add module RateLimiter(type=Middleware)
  → Constraint: Every Middleware must expose Metrics → 加 Metrics
  → Pattern: Middleware Pattern (config+lifecycle) → 按模板
  → Rule: Middleware must be before Auth → 位置正确
  → AntiPattern: Middleware cannot bypass Auth → 不要跳过
  → Quality: Performance +0.2, Observability +0.5 → 展示代价/收益
```

触发时机: Fast Path = 新建模块时 `get_constraints_for`；Async Path = 修改模块时
`get_impact_of_change`；Slow Path = Pattern 蒸馏（重复实例→Candidate→Verified）。

---

## 六、递归地图模型（多颗粒度）

```
叶节点 (颗粒度=0): import/function/class 签名 → 暴露给关联链的 API 契约
聚合层 (颗粒度=1): 模块/文件级 → Public API + 约束
顶层   (颗粒度=2): 系统/架构级 → 架构图

特性: 高耦合区域展开到细颗粒度；低耦合/高聚合折叠到粗颗粒度
      → 自适应: 根据关联链的强度决定展开程度

解析流程: 文档/代码 → tree-sitter/heading 解析 → DocumentTree
  → 识别 Module/Import/Function/Constraint/Pattern → 绑定 file:line
  → ObservationBundle → ObservationPool → Engineering Analyzer 消费
```

---

## 七、本体层（元层）

### 7.1 来源分类（source → 初始置信度 → 升级路径）
| source | 谁写入 | 初始 confidence | 可升级到 |
|---|---|:---:|---|
| manual | 用户显式定义 | 0.90 | verified |
| derived | Analyzer 推断 | 0.40 | verified |
| learned | LLM 从 Observations 提取 | 0.30 | derived → verified |
| verified | 实际使用验证 | 0.85 | core |
| core | 系统预置，不可删除 | 1.00 | (不可变) |

只有 manual 和 core 可直接进 Graph；derived/learned 必须先入 Hypothesis Pool。

### 7.2 白盒化接口（OntologyEditor）
```
OntologyEditor.add_edge_rule(from, to, edge_type)
OntologyEditor.add_lifecycle_state(type, state, before)
OntologyEditor.add_node_type(Convention, discriminator)
OntologyEditor.set_source_confidence(source, new_value)
```
- 每次修改产生 EngineeringChain Event (source=User) → Event Log → 学习管线。
- 修改后立即生效，无需重启。核心本体（core）不可删除、不可降级。
- 操作记忆: OntologyEditEvent（turn/user_id/target/action/before/after/reason），
  同一修改跨会话累积到阈值（默认 3 次）→ 系统主动提示提升为 suggested。

### 7.3 三层架构
```
Layer 1: Artifact Graph（工程对象图）— 系统里有什么
Layer 2: Knowledge Graph（工程知识图）— 什么应该成立/什么不该做
Layer 3: Reasoning Engine（约束推理）— 影响/推荐/违规检测
```

---

## 八、执行层集成（完整规格）

### 8.1 七棵树并行（DESIGN_EXECUTION_LAYER）
```
DiscourseBlockTree (基类) → Discourse/Execution/Constraint/Association/Behavior/Meta/Profile
活跃度: ExecutionTree ████████ > Discourse ██████ > Meta ████ > Behavior ███ > Association ██ > Constraint █ > Profile ▏
```

### 8.2 ConstraintTree 的职责
- 存储: 规则、约束、文件/命令限制（轻量，仅在约束命中时活跃）。
- 触发回退插入（§3.2）: MetaTree 发现 ExecutionTree 产出违反 ConstraintTree、
  任务完成但约束检查不通过、用户修改了约束规则 → 回退到决策节点 → 插入新分支 → 重新派生。

### 8.3 管线主路径中的约束验证
```
Compass → PCR → Intent → L4 → Context → LLM Plan
  → PlanGate.create() / auto_approved
  → ExecutionEngine (7工具, 约束验证) → 子Agent 完成
  → MetaTree 归约 → LLM Answer → PlanGate.learn → CorrectionJournal
```

---

## 九、API 文档预处理（ENGINEERING_API_DOC_PREPROCESSOR 完整规格）

### 9.1 6 组件管线
```
APIDocParser (openapi3/swagger2/graphql/markdown, auto-detect, URL 下载, parse_safe)
  → OpenAPI3Parser (paths/endpoints/schemas/security 提取)
  → SchemaExtractor (提取 + simplify 深度控制 + to_markdown)
  → EndpointExtractor (提取 + simplify + to_tool_definition)
  → DocNormalizer (HTML 清理/空行/截断/字段限制)
  → ContextBuilder (概览 + 按标签分组端点 + 关键 Schema, max_tokens 截断)
```

### 9.2 与 ToolRegistry 集成
```
auto_register_from_openapi(registry, openapi_url):
  parse → EndpointExtractor.simplify → to_tool_definition(base_url) → registry.register
```

### 9.3 与 6 LLM 实例的场景映射（v3 架构）
| LLM | 使用场景 | 上下文类型 |
|---|---|---|
| PCR-LLM | 是否涉及 API 调用 | 工具名称列表 |
| Intent-LLM | 意图是否需要 API | 工具描述 |
| Planning-LLM | 生成调用计划 | 完整端点 + Schema |
| Meta-Cognitive-LLM | 验证参数 | 参数 Schema |
| Reflective-LLM | 调用模式分析 | 历史调用记录 |
| Answer-LLM | 解释返回结果 | 响应 Schema |

### 9.4 已知简化项（S-01~S-05）
GraphQL 解析 / 文档缓存 / 增量更新 / 认证解析 / 代码示例生成 —— 均 Phase 2。

---

## 十、全局状态机中的工程链（防广播风暴）

```
旧问题: 画像更新 quality_centric 惯性 → 推送工程链 → 工程链约束变化 → 推送对话树 → ...
         一轮修改触发 6 链连锁反应 = 指数级放大 = 广播风暴

新模型: Command → Decider(唯一决策入口, 每次只产生 1 个 Event) → Event 层(不可变日志)
  → evolve(纯函数) → State 层(派生视图) → 下一 tick 再决策

工程链相关事件: ConstraintViolated (E4) — 一等事件
工程链状态: S4 "工程链当前状态" — State 层一等成员
```

---

## 十一、白盒 CLI（DESIGN_CLI §13 完整规格）

```
dm engineering constraint check                          # 约束检查
dm engineering constraint add <type> <target> <spec>    # 添加约束
dm engineering constraint remove <id>                   # 删除约束
dm engineering constraint list                          # 所有约束
dm engineering propagate                                # 变更传播
dm engineering impact <change>                          # 影响分析
```

---

## 十二、设计要点摘录（供讨论）

1. **约束空间 vs 普通知识库的本质区别**: 其他链是认知链（记录发生了什么），
   工程链是约束推理链（推导什么必须成立）—— 这是「约束空间」的哲学内核。
2. **执行层强相关的三个落点**: ExecutionEngine 约束验证 / MetaTree 违反回退 /
   子图 K 域约束注入（20% token）—— 保证 LLM 产出契合约束。
3. **人工领地原则**: AntiPattern 与 Decision 禁止 LLM 自动创建 —— 安全护栏的体现。
4. **递归地图**: 同一结构多尺度表示，展开程度由关联链强度驱动（自适应颗粒度）。
5. **白盒即治理**: 约束可增删改查，修改进入 Event Log → 学习管线 → 本体自演化。
6. **约束空间的可演化性**: manual 0.90 / derived 0.40 / learned 0.30 → verified 0.85，
   与贝叶斯信念统一（AdaptiveParameter 锚点+区间+reward_signal）。

---

# 补充记录（第二轮精读）— 工具注册 / 执行约束 / 统一持久化 / 约束补全编译器

> 本部分追加于 2026-08-03，补齐以下设计文档: `DESIGN_TOOL_REGISTRY.md`、
> `ENGINEERING_TOOL_REGISTRY.md`、`FLOW_EXECUTION_INTERNAL.md`、`FLOW_EXECUTION_OVERALL.md`、
> `DESIGN_UNIFIED_PERSISTENCE.md`、`ENGINEERING_PERSISTENCE.md`、`ENGINEERING_V3_3_COMPILER.md`。

---

## 十三、工具注册（Tool Registry）— 工程链约束校验的落点

### 13.1 定位与对比（DESIGN_TOOL_REGISTRY v2.0）
```
目标: LLM 作为协调者，自选工具、自判不足、自动扩容。
对比: OpenAI/LangChain/CrewAI 都是手动注册；我们是 自动发现 + 懒加载 + 缺失自动装 + 自写工具。

三级自主:
  Level 1: 工具已注册 → 直接调用（<1s）
  Level 2: 工具不存在 → pip install → 注册 → 执行（~30s）
  Level 3: 装不了 → LLM 自写 ToolAdapter → Sandbox 验证 → 注册 → 执行
           → 成功: 持久化为 Skill + TriggerRule；失败: 告知用户
```

### 13.2 ToolAdapter / ToolResult / ToolRegistry（3 行注册）
```
ToolAdapter: name / description（LLM 判断匹配）/ category / dependencies（自动 pip install）/
             handler / input_schema（JSON Schema）/ enabled / auto_install
ToolResult:  tool_name / success / data / error / latency_ms / artifact_path
ToolRegistry: register / unregister / get / query(tags, keyword) / list_all / get_schema_for_llm

LLM 工具调用协议: 系统提示词注入所有工具 description+input_schema；
  输出 <tool_call name="..."> JSON </tool_call> → parse_tool_calls → 执行 → 结果注入上下文
```

### 13.3 工具绑定引擎（ToolBindingEngine — 4 策略，工程规范标注 ❌ 缺失）
```
占位符 → 实际工具绑定，策略优先级:
  1. 精确匹配（去 _tool 后缀）→ 2. 标签匹配（tool_hints ∩ tags）→
  3. 语义匹配（embedding 余弦）→ 4. 参数兼容（启发式: 参数越多越兼容）
低置信度（<0.6）→ fallback_to_ask_user
bind_task_graph: 批量绑定 TaskGraph 占位符 → 更新 node.tool_name
文档诚实标记: "4 策略绑定 ❌ 缺失 — 仅工程规范，无实际实现代码"
```

### 13.4 工具 → 工程约束的关系
- `MCPIntegrationHub`（mcp/integration.py）设计为: MCP 发现 → ToolRegistryBridge →
  **EngineeringChain 约束校验** → PlanningBridge 工具选择 → LLM 执行。
- `validate_against_constraints(tool_name, params)` → `{"allowed", "warnings", "blocking"}`。
- 实现审计结论（见 AUDIT）: `engineering_chain` 恒 None → 校验空转。
- 白盒 CLI（DESIGN_CLI §13）: `dm engineering constraint check/add/remove/list` +
  `dm engineering propagate/impact` —— 约束操作是用户可见的一等命令族。

---

## 十四、执行流中的约束验证（FLOW_EXECUTION_INTERNAL / OVERALL）

### 14.1 内部流（ExecutionEngine + PlanGate）
```
LLM Plan → PlanGate.create_checkpoint（逐步骤风险评估: read=LOW / edit=MEDIUM first_use→requires_review）
  → 用户审批 → ExecutionEngine.execute_batch
  → 每步: 约束检查 → 执行 → 产出 → 归约

约束拦截: Step edit /etc/nginx.conf → ConstraintTree 检查 forbidden_paths → BLOCKED → 不执行
DRY_RUN 模式: 约束检查 + 工具验证，不产生副作用
```

### 14.2 整体流（七棵树协同 — 子 Agent 查询约束）
```
子Agent a2 "edit auth.py" → pointer → ConstraintTree.security_rules
  → 命中: "auth模块修改必须加注释"（活跃节点直接返回，1ms）
  → 未命中 → 双方案并行: ① 子 Agent 搜索持久化层 ② L5 Memory 搜索 → LLM 去重
执行时: _edit → ConstraintTree 实时验证 → 通过

跨树冲突裁决（流五）: ExecutionTree 完成 edit /etc/hosts vs ConstraintTree forbidden:/etc/*
  → RelationSubstrate 发现冲突 → MetaTree 裁决（查 BehaviorTree 历史批准 + ProfileTree 技术级别）
  → notify PlanGate → 用户确认 → 批准则 BehaviorTree 记录例外 + ConstraintTree 添加白名单
```

### 14.3 时间线（约束在每阶段的活跃度）
```
T0 Plan:    Constraint ██   （约束进入计划）
T1 派生:    Constraint ████ （子Agent pointers → ConstraintTree）
T2 执行:    Constraint ████ （实时验证）
T3 归约:    Constraint ██   （约束状态更新）
```

---

## 十五、统一持久化（Unified Graph Store）— 工程链 E 域存储

### 15.1 通用节点表（存储层不知道类型）
```
graph_nodes { node_id, node_type, domain(T/E/B/K/P), session_id, data JSON,
              summary(L1), l2_summary(L2), activation_count, importance, tier(H/W/C/A),
              source_events, created_at, updated_at }
```

### 15.2 E 域映射
| 域模型 | node_type | 存储内容 | 粒度策略 |
|---|---|---|---|
| Artifact | artifact | 名称+类型+状态 | summary=模块名+状态摘要 |
| KnowledgeNode | constraint/pattern/decision/quality/antipattern | 名称+描述+模板 | summary=规则摘要, l2_summary=模式简介 |

### 15.3 分层（JVM GC 模型）
```
H (Hot)  内存 dict         完整 data+summary+l2  <1ms
W (Warm) SQLite            完整                  <10ms  跨会话命中→升级
C (Cold) SQLite+压缩       summary+l2+索引,data移除 <50ms
A (Archive) gzip JSONL     仅 node_id+l2+source_events <500ms
GC: H>1000 → 降最不活跃；每小时 importance<0.3 的 W→C；C 保留索引可被 WaveQuery 检索
```

### 15.4 检索扩展
```
wave_from_node(anchor, max_depth, domain_filter, tier_filter, granularity=coarse)
两阶段: Coarse scan(summary/l2 快速匹配) → Full recall(data 精确加载)
三种强化: 问题预生成(generated_questions) / HyDE(假设文档嵌入) / 混合检索(语义0.7+关键词0.3)
性能: 动态索引锚点(HotIndex partial index, ~30行SQL) / 主干染色(Rust petgraph betweenness)
```

### 15.5 与工程链的关系
- 工程链节点（constraint/pattern/decision/antipattern/artifact）应存 graph_nodes，
  与对话树/行为/因果/画像同图分层 —— 这正是「约束空间可演化」的持久化底座。
- 实现审计（AUDIT）: `persistence.py` 已写 `save_node(domain="E")` 适配器，
  但生产从未实例化；`persistence_full.py` 是重复文件。

---

## 十六、约束补全编译器（ENGINEERING_V3_3_COMPILER）— 约束空间的句子级应用

### 16.1 三步流水线
```
输入: sentence + ParseContext
  Step1 LLMPseudoParser: NL → {slot: {value, confidence}}（只回显不推理）
  Step2 RuleConstraintEngine: 规则选择性深挖 low-confidence 槽位
  Step3 StabilityScorer: stability = mean(ci) × (1 - var(ci))
降级: LLM 可用→三步；LLM 不可用→纯规则；连续 3 次失败→纯规则模式
```

### 16.2 规则引擎（RuleConstraintEngine + FrameLibrary）
```
ConstraintRule: frame_name / slot_name / candidates / incompatible_with / priority / condition
标准槽位: agent / action / patient / result / cause（非标准槽位保留不过滤）
四步消解: FrameLibrary 匹配 → 候选约束 → 互斥消除 → 优先级裁决
```

### 16.3 与工程链的衔接
- 这是「约束」在 **NL 解析层**的应用（句子级约束补全），
  与工程链的 **工程对象层**（模块/约束/模式）是同一约束哲学的两个粒度：
  句子级（V3_3）与系统级（BUSINESS_CHAIN_07）。
- 设计文件路径为 `core/agent/v3_2/compiler/`，实现审计显示已迁移到
  `core/agent/compiler/rule_engine.py`（RuleConstraintEngine 存在，见工程链审计线索）。

---

## 十七、补充记录小结（工程链）

1. **约束空间的三层落地**: 系统级（ConstraintTree/七棵树）、执行级（工具约束校验/路径拦截）、
   句子级（V3_3 约束补全编译器）—— 工程链是贯穿这三层的「不变量」体系。
2. **工具是约束校验的第一现场**: ToolRegistry + MCP 集成设计上必须过 EngineeringChain，
   这是约束空间与执行层的最近触点。
3. **统一持久化是约束演化的底座**: 约束/模式/决策/反模式与所有域同图分层存储，
   支持跨会话检索、回升、水波扩展 —— 与递归地图的颗粒度思想呼应。
