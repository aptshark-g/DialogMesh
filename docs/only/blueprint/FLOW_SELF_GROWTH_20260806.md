# 业务流自增长 — LLM 生成 × 工具执行 × 模板沉淀（2026-08-06）

> 触发讨论：业务流（查论文→找爬虫→爬→分析→改造→获取）是组合爆炸的，
> 人工枚举永远补不完。结论：业务流不靠"补"，靠"生"——
> 内置模板 = 种子，LLM_DRIVEN = 生成，元认知 = 沉淀。
> 状态：设计定案，待施工。前置：META_ARBITER P0 已完成（决策事件/RECOVERY/Meta 副作用）。

---

## 一、核心论断：业务流的三个来源（不是一层）

```
业务流来源:
  ① 内置模板（5 个）= 冷启动种子（只覆盖最常见）
  ② LLM_DRIVEN 动态生成 = 覆盖无穷新场景（说不完的组合）
  ③ 元认知学习沉淀 = 跑成功的动态 DAG 自动变新模板

用户角色收敛为:
  提供新工具（爬虫/查论文 adapter）+ 新意图种子模板（可选）
  在 LLM_DRIVEN 生成高风险图时 approve/reject（PlanGate）
  不写流程 — 系统自己长出新业务流
```

### 你的例子（业务流如何被"生"出来）

```
用户: "去查一下最近关于 X 的论文"
  → 蓝图判断新场景（无匹配模板）→ LLM_DRIVEN
  → diverge: LLM 提假设 [查论文]→[找爬虫]→[爬]→[分析]→[改造]→[获取]
  → learn: 找 github 爬虫工具（ToolRegistry）
  → converge: 约束过滤（安全/工具可用/预算）
  → 生成 DAG: [pcr]→[intent]→[tool:查论文]→[tool:爬虫]→[llm_reply]
  → 执行 → 元认知复盘（成功/失败）→ 成功路径沉淀为新模板
  → 下次同意图 → 直接命中模板（不用再生成）
```

---

## 二、现状核实（2026-08-06 调研结论）

| 能力 | 现状 | 缺口 |
|------|------|------|
| LLM 动态建图（diverge→learn→converge） | ✅ `llm_dag_builder.py` 已实现 | LLM_DRIVEN 四保护缺三 |
| 工具注册（查论文/爬虫等） | ✅ `ToolRegistry` + builtin | tool 节点接入 DAG 执行 |
| 成功路径沉淀模板 | ⚠️ `suggest_blueprints` 实现但零调用方 | 接线：执行成功 → 沉淀 |
| 权重学习 | ⚠️ `update_strategy_weights` 部分 | P1-5 权重公式已修（base×rate） |
| 决策事件（P0） | ✅ `decision_event.py` | 无 |
| RECOVERY 执行期切换（P0） | ✅ `executor.py` | 无 |

**断的是"生成→执行→沉淀"闭环**：
- LLM 能生成 DAG，但 tool 节点不能真执行（查论文/爬虫是 dead 节点）
- 执行了没有沉淀机制（suggest_blueprints 零调用方）

### 调研细节（代码实测）

| 项 | 实测 | 位置 |
|---|------|------|
| ToolRegistry 完整 | register/categories/discover(query)/execute + auto-install 三级 + LLM self-authoring | `tools/registry.py` |
| builtin 工具已注册 | arxiv_search / web_fetch / pdf_extract / file_read / file_write（正是"查论文→爬→分析"场景工具） | `tools/builtin.py` |
| discover(query) 现成 | "有没有搜论文的工具?" → 匹配 arxiv_search（LLM 找工具接口已存在） | `tools/registry.py` L108+ |
| CHAIN_IDS 无 tool | `{pcr,intent,context,subgraph,profile,llm_reply,behavior,meta,discourse,association,engineering,metap}` | `blueprint/models.py` L16 |
| learn 阶段硬编码 | `reference_map` 写死 5 模板, **未用 ToolRegistry.discover** | `llm_dag_builder.py` L215-225 |
| suggest_blueprints 零调用方 | 实现完整但无人调 | `meta_feedback.py` |
| MetaFeedback P0-3 已副作用化 | degrade/promote 真实改权重 + 决策事件 | `meta_feedback.py` |

**结论**: 工具层地基完整（用户要的"查论文/爬虫"工具都在），
缺的是三处接线: ① tool 链节点 ② learn→discover ③ 成功→沉淀。

---

## 三、施工规划（三件事，不靠人工补业务流）

### G1. tool 节点真实执行（让动态生成可跑）

```
BlueprintNode.chain = "tool" 新增:
  params: {tool: "fetch_papers" | "github_search" | ..., args: {...}}
  executor._handle_tool → ToolRegistry.execute(tool, **args)
  → 输出: {tool_result: {...}, status: "ok" | "error"}

ToolRegistry 扩展:
  register 工具带 metadata（category: 论文/爬虫/搜索/代码）
  DAG builder 的 learn 阶段能列出可用工具（生成时才知道有啥工具）
```

### G2. 模板进化闭环（业务流自增长的核心）

```
执行成功（llm_reply 产出 + 无 error）:
  → MetaFeedback.suggest_blueprints 接线
  → 新意图出现 N 次 + 成功 → 生成新模板入 BUILTIN_TEMPLATES
  → 模板带 provenance（from: dynamic_learn, source_dag_id）

执行失败:
  → update_strategy_weights 降权（该路径下次不选）
  → 失败 DAG 进"负样本库"（RECOVERY 参考）

模板注册表（动态区）:
  BUILTIN_TEMPLATES（种子, 只读） + LEARNED_TEMPLATES（动态, 可增）
  match 顺序: LEARNED 优先（成功经验 > 通用种子）
```

### G3. LLM_DRIVEN 四保护（让生成可安全跑）

```
PlanGate:  生成图后高风险节点 → 用户 approve/reject（P1 已有决策事件基础）
Budget:    节点 ≤ 7（ConstraintChecker 已有 MAX_NODES=7）
LoopDetector: 重访节点 3 次 → 强制 checkpoint（新增）
QualityGate: 执行后元认知评分 → 低分降级 HYBRID（P0-3 已副作用化）
```

---

## 四、验收门槛

1. `tool` 节点真执行: DAG 含 tool 节点 → ToolRegistry.execute 被调用 → 结果入上下文
2. 成功沉淀: 执行成功的动态 DAG → 自动生成新模板 → 下次命中
3. 失败降权: 失败路径 → 权重下降 → 不再选
4. 用户不补流程: 新场景首次 LLM 生成, 二次模板命中
5. LLM_DRIVEN 保护齐备: PlanGate/Budget/LoopDetector/QualityGate

---

## 五、与既有设计的关系

| 本设计 | 既有出处 | 关系 |
|-------|---------|------|
| G1 tool 节点 | DESIGN_BLUEPRINT_SYSTEM §三（技能带工具映射） | 接线（工具映射已有概念） |
| G2 模板进化 | DESIGN_BLUEPRINT_ORCHESTRATION §14.5（模板建议/节点修正） | 接线（suggest_blueprints 零调用方） |
| G3 四保护 | DESIGN_BLUEPRINT_ORCHESTRATION §十一（四保护） | 补全（Budget 有, 缺三） |
| 决策事件/异步介入 | META_ARBITER_ASYNC_INTERVENTION | 前置（P0 已完成） |

---

## 五点五、行业调研：Hermes / pi (OpenClaw) 工具调度机制（2026-08-06）

> 触发：用户质疑"纯匹配是否合理？应该是语义+匹配混合触发调用"。
> 调研：联网读 Hermes-Function-Calling + OpenClaw agent-core 源码。

### 调研结论（三对比）

| 维度 | Hermes (Nous) | pi / OpenClaw | DialogMesh 现状 |
|------|--------------|---------------|-----------------|
| 工具触发 | LLM schema-based function calling（模型按工具 schema 生成调用 JSON） | LLM toolCall 消息块（`agent-loop.ts` filter `c.type==="toolCall"`） | ⚠️ 关键词匹配 discover |
| 工具发现 | 预注册 schema 注入 prompt | descriptor + availability signal（auth/config/env/plugin 条件可见性） | ⚠️ 手动 discover 子串 |
| 调用前校验 | — | `validateToolCallForBatchAdmission`（参数准备/校验） | ❌ 无 |
| 介入/批准 | — | `beforeToolBatch` 钩子（执行前可中断/修改/批准） | ⚠️ PlanGate 概念未接工具 |
| 失败恢复 | — | `toolLoopRecoveryState`（循环失败恢复，超阈值终止） | ✅ RECOVERY（P0-2 已做） |
| 结果回灌 | — | 结果推回 `currentContext.messages` 继续 LLM | ⚠️ 只 summary 进 llm_reply |

### 核心结论

**Hermes/OpenClaw 都是"LLM 语义决策 + 校验 + 恢复 + 介入"，不是匹配。**
匹配只是"发现工具"的辅助（descriptor 注入让 LLM 看到），
真正"选哪个工具、传什么参数"是 LLM 语义决策。

**DialogMesh 正确架构（按 OpenClaw 模式重构）:**
```
发现（descriptor/匹配注入）→ LLM 语义决策（选工具+参数）
  → 调用前校验 → 执行 → 失败恢复（RECOVERY）
  → 结果完整回灌 LLM 上下文（不止 summary）
```

**当前缺的**: ① LLM 决策工具（tool 节点 params 硬编码）
② 调用前校验 ③ 工具结果完整回灌。
