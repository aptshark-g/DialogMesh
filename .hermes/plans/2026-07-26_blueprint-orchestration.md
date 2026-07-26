# Blueprint Orchestration — 实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> **Design doc:** `docs/DESIGN_BLUEPRINT_ORCHESTRATION.md` (15 sections, complete)

**Goal:** Build the Blueprint orchestration layer — LLM 动态构建执行 DAG → EventBus 并行跑图 → Meta 异步学习回写。

**Architecture:** 新增 `core/agent/blueprint/` 包 (3模块) + 改造 agent_native 管线从线性→EventBus + 前端 DAG 可视化。

**Tech Stack:** Python 3.11+ (dataclass, asyncio), FastAPI (API routes), React/TS (TaskPlanningPage), switch Gateway (LLM proxy)

**Quality bar:** 每步逐行对齐 DESIGN_BLUEPRINT_ORCHESTRATION.md 的 schema/协议/时序。不猜, 不对齐即返工。

---

## Phase 0: 基础数据层

### Task 0.1: BlueprintDAG + BlueprintNode + BlueprintEdge dataclass

**文件:** 创建 `core/agent/blueprint/__init__.py` + `core/agent/blueprint/models.py`

完全对齐 §14.2 schema:
- `BlueprintDAG`: nodes, edges, strategy(TEMPLATE|HYBRID|LLM_DRIVEN|RULE_BASED|RECOVERY), confidence, design_rationale
- `BlueprintNode`: node_id, chain(pcr|intent|context|subgraph|profile|llm_reply|behavior|meta), params, priority, checkpoint
- `BlueprintEdge`: from_node, to_node, data_key, required
- `ExecutionAudit` (§14.4): request_id, blueprint_id, strategy, dag_quality_score, anomalies

验证: `python -c "from core.agent.blueprint.models import BlueprintDAG; print(BlueprintDAG(nodes=[],edges=[],strategy='TEMPLATE',confidence=1.0))"`

### Task 0.2: SkillRegistry + 5 内置 Blueprint 模板

**文件:** 创建 `core/agent/blueprint/skill_registry.py`

5 个内置模板 (对齐 §十 三种策略):
```python
TEMPLATES = {
    "code_analysis": BlueprintDAG(  # TEMPLATE
        nodes=[BlueprintNode("pcr_0","pcr",...), BlueprintNode("intent_1","intent",...),
               BlueprintNode("context_2","context",...), BlueprintNode("llm_3","llm_reply",...)],
        edges=[...], strategy="TEMPLATE", confidence=1.0),
    "general_chat": ...,     # HYBRID
    "task_planning": ...,    # HYBRID
    "data_search": ...,      # TEMPLATE
    "causal_reasoning": ..., # LLM_DRIVEN (空壳, LLM 填充)
}
```

`SkillRegistry.match(intent: str) → (strategy, blueprint)`:
- 基于关键词+历史成功率加权
- 返回策略类型 + 对应模板

验证: `python -c "from core.agent.blueprint.skill_registry import SkillRegistry; sr = SkillRegistry(); print(sr.match('代码分析'))"`

---

## Phase 1: LLM 动态 DAG 构建

### Task 1.1: 发散 LLM — 无约束探索

**文件:** 创建 `core/agent/blueprint/llm_dag_builder.py`

`LLMDAGBuilder.diverge(text, intent) → List[Hypothesis]`:
- 调用 switch LLM (T=0.8, 无上下文约束)
- 要求输出: 多种可能的执行路径 + 每种的推导原因
- 格式: JSON 数组 `[{path: [{chain, params, reason}], confidence}]`

### Task 1.2: 学习检索 — 外部信息摄入

**文件:** 同上文件

`LLMDAGBuilder.learn(hypotheses) → enriched_hypotheses`:
- 对每条假设, 并行检索:
  - arXiv 搜索 (curl arxiv API)
  - 本地 EventLog 查询 (历史相似意图的执行记录)
  - 内置参考 (DESIGN 文档中的方案对比表)
- 评估: 来源权威性 × 相关性 × 时效性

### Task 1.3: 收束 LLM — 约束过滤

**文件:** 同上文件

`LLMDAGBuilder.converge(hypotheses, full_context) → BlueprintDAG`:
- 调用 switch LLM (T=0.1, 完整上下文)
- 输入: 发散假设 + 学习结果 + 完整约束
- 输出: 最终 BlueprintDAG (含 design_rationale)
- 失败 → 回退到 TEMPLATE

### Task 1.4: BlueprintEngine — 三种策略的入口

**文件:** 创建 `core/agent/blueprint/engine.py`

`BlueprintEngine.build(text, intent, strategy) → BlueprintDAG`:
```python
if strategy == TEMPLATE or strategy == RULE_BASED:
    return SkillRegistry.match(intent).blueprint  # 直接返回模板
elif strategy == HYBRID:
    template = SkillRegistry.match(intent).blueprint
    dag = LLMDAGBuilder.build_from_template(template, text)
    return ConstraintChecker.validate(dag)
elif strategy == LLM_DRIVEN:
    hypotheses = LLMDAGBuilder.diverge(text, intent)
    enriched = LLMDAGBuilder.learn(hypotheses)
    dag = LLMDAGBuilder.converge(enriched)
    dag.strategy = "LLM_DRIVEN"
    return ConstraintChecker.validate(dag)
```

验证: 单元测试覆盖三种策略路径

---

## Phase 2: 约束 + 执行

### Task 2.1: ConstraintChecker — DAG 约束验证

**文件:** `core/agent/blueprint/engine.py` (同文件)

`ConstraintChecker.validate(dag) → BlueprintDAG`:
- 安全: is_destructive 节点前必须有 checkpoint
- 资源: 节点数 ≤ 7, 总深度 ≤ 3
- 依赖: 拓扑排序, 无环检查, 依赖的 data_key 必须在前置节点产出
- 权限: Capability check (reduce-only)
- 失败 → 回退到 TEMPLATE 重试 1 次

### Task 2.2: EventBus — 8 链订阅 + Decider 发射

**文件:** 改造 `core/agent/event/event_bus.py`

对齐 §14.3 订阅表:
- 新增 `BlueprintSubjectRouter` — 根据 BlueprintDAG 动态注册 subject
- 改造 Decider: 按 Tick 批处理 → 同 Tick 并行发射, 跨 Tick 串行
- 每 Tick: 检查所有节点的依赖就绪 → 发射 Task → 收集 Result

### Task 2.3: agent_native → EventBus 桥接

**文件:** 改造 `core/agent/orchestrator/agent_native.py`

替换线性 `process()` 为:
```python
def process(self, text: str) -> dict:
    intent = self.intent.split(text)
    strategy, _ = SkillRegistry.match(intent)
    dag = BlueprintEngine.build(text, intent, strategy)
    results = Decider.execute(dag)  # EventBus 跑图
    return self.synthesize(results)  # 汇聚结果
```

---

## Phase 3: API + 学习闭环

### Task 3.1: v3_session_api 接入 BlueprintEngine

**文件:** 改造 `core/agent/api/v3_session_api.py`

`send_message()` 改造:
- 替换直接的 switch LLM 调用为 `BlueprintEngine.build() → Decider.execute()` 管线
- task_graph 字段直接返回 BlueprintDAG 的 nodes (前端统一 schema)
- 保持向后兼容: 原 response 格式不变

### Task 3.2: MetaFeedback — 异步学习回写

**文件:** 创建 `core/agent/blueprint/meta_feedback.py`

对齐 §14.4-14.5:
- `MetaFeedback.consume(event_log)` — EventBus 异步订阅
- `MetaFeedback.audit(execution_audit)` — 评分 + 异常检测
- `MetaFeedback.update_weights()` — 回写 SkillRegistry 权重
- `MetaFeedback.suggest_blueprint()` — 建议新增模板
- 降级触发: 连续 3 次低分 → strategy 权重降到 0 → 自动退到 HYBRID

---

## Phase 4: 前端统一 DAG 可视化

### Task 4.1: TaskPlanningPage 支持 Blueprint 层节点

**文件:** 改造 `frontend/src/pages/TaskPlanningPage.tsx`

对齐 §十五:
- node_type 新增: pcr, intent, context, subgraph, profile, llm_reply
- Blueprint 层节点蓝色边框, TaskGraph 层绿色边框
- 节点可展开: Blueprint 节点 → 展示子 task_graph

### Task 4.2: TaskGraphNode type 扩展

**文件:** 改造 `frontend/src/types/api.ts`

新增字段: params, checkpoint (可选)

---

## Phase 5: 文档 + 测试

### Task 5.1: Business Chain 文档

**文件:** 创建 `docs/BUSINESS_CHAIN_11_BLUEPRINT.md`

对齐 10 节标准格式: 位置/阶段/算法/下游/代码映射/集成状态/Gantt

### Task 5.2: Engineering 规格

**文件:** 创建 `docs/ENGINEERING_BLUEPRINT.md`

数据模型 + 组件依赖 + 启动序列 + 部署

### Task 5.3: E2E 测试

**文件:** `tests/test_blueprint_e2e.py`

完整流程测试: 输入文本 → SkillRegistry → BlueprintEngine → EventBus → 响应

---

## 优先级与预估

| Phase | 文件数 | 估时 | 内容 |
|-------|:-----:|------|------|
| 0 基础数据层 | 2 新 | 0.5天 | dataclass + 5 Blueprint 模板 |
| 1 LLM 构建 DAG | 2 新 | 1.5天 | 发散/学习/收束 + Engine |
| 2 约束+执行 | 2 改 | 1.5天 | ConstraintChecker + EventBus |
| 3 API+学习 | 2改1新 | 1天 | v3接入 + MetaFeedback |
| 4 前端可视化 | 2 改 | 1天 | TaskPlanningPage 统一渲染 |
| 5 文档+测试 | 3 新 | 0.5天 | Business Chain + Engineering + E2E |

**总估时: 5-6 天** (按每天 4-6 小时)

**Phase 0-1 做完即可 demo**: 对话 → LLM 构建 DAG → JSON 输出 (现有 task_graph 字段已有)
**Phase 2-3 做完**: 完整闭环 (EventBus 执行 + Meta 学习)
**Phase 4**: 前端可视化 (已对齐 schema, 改动最小)
