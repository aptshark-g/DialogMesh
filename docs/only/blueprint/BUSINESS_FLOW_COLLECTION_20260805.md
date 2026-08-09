# 业务流收集 — 蓝图模板 = 业务链（2026-08-05）

> 目的: 从设计文档系统化收集"业务链"素材，作为蓝图模板重构的依据。
> 结论: 蓝图模板 = 业务流。现有 5 模板只取了"名字"，丢了"内容"
> （工具映射 / 安全约束 / Tick 并行语义）。以下为完整收集。

---

## 一、素材来源（设计文档）

| 文档 | 提供的素材 | 用途 |
|------|-----------|------|
| `DESIGN_BLUEPRINT_SYSTEM.md` | 5 任务级技能 × 工具映射 × 安全约束 | 业务链内容层 |
| `DESIGN_BLUEPRINT_ORCHESTRATION.md §14.3` | 8 subject 订阅表 × Tick 分组 | 业务链执行层 |
| `DESIGN_BLUEPRINT_ORCHESTRATION.md §15` | node_type 协议（Blueprint 层 + TaskGraph 层） | 统一可视化 |
| `BUSINESS_CHAIN_11_BLUEPRINT.md` | 11 链定位图 + 阶段 + 下游调控 | 链路全貌 |
| `DESIGN_EXECUTION_LAYER.md` | 7 树并行 + 查询驱动 + 等待策略 | 执行形态 |
| `DESIGN_GLOBAL_STATE_MACHINE.md` | Command→Event→State 三阶段 | 状态底座 |
| `DESIGN_EVENTBUS_V2.md` | subject 路由 + queue group + req-reply | 事件语义 |

---

## 二、业务链全集（技能层 — DESIGN_BLUEPRINT_SYSTEM §三）

### 2.1 五个内置技能 + generic 兜底

| 技能 | 触发意图 | 工具映射 | 安全约束 |
|------|---------|---------|---------|
| `code_analysis` | analyze/security/bug/vulnerability | read + grep + write | 只读 + 写报告 |
| `code_fix` | fix/patch/edit | read + edit + bash | **require_review**（写操作须审核） |
| `test_run` | test/run/check | bash + write | 沙箱执行 |
| `config_update` | config/setup | read + edit | **require_review** + **forbidden:/etc/** |
| `data_search` | search/find/grep | grep + glob + read | **read_only** |
| `generic` | 无匹配 fallback | read + write | 默认 |

### 2.2 TaskDecomposer 结构（模板→具体步骤）

```
意图 "analyze auth.py for security"
  → Step 0: read auth.py
  → Step 1: grep security pattern in auth.py
  → Step 2: write report.md
  依赖: S0→S1→S2（拓扑序）
```

### 2.3 AgentAllocator（步骤→子 Agent）

```
read/grep（轻量）→ agent_0 共享
edit/bash（重量级）→ agent_1 独立子 Agent（安全隔离）
```

---

## 三、链级订阅表（执行层 — DESIGN_BLUEPRINT_ORCHESTRATION §14.3）

| Subject | 订阅链 | Tick | 说明 |
|---------|-------|------|------|
| `dm.{req}.pcr.route` | 00 PCR | **0** | 路由分析 |
| `dm.{req}.intent.split` | 03 Intent | **0** | 意图拆分（与 PCR 并行） |
| `dm.{req}.context.assemble` | 02 Context | **1** | 上下文组装（依赖 PCR+Intent） |
| `dm.{req}.subgraph.compile` | 10 Subgraph | **1** | 子图编译（依赖 Context） |
| `dm.{req}.profile.load` | 08 Profile | **1** | 画像加载（与 Context 并行） |
| `dm.{req}.llm.reply` | LLM Reply | **2** | LLM 最终回复（依赖全部） |
| `dm.{req}.meta.audit` | 09 Meta | **async** | 异步审计 |
| `dm.{req}.behavior.learn` | 05 Behavior | **async** | 行为学习 |

> 设计语义: **同 Tick 内并行，跨 Tick 串行**（依赖保证）。
> 现状: `StateMachine.run_dag` Kahn 拓扑串行 → 只实现了"跨 Tick 串行"，
> 未实现"同 Tick 并行"。

---

## 四、11 链定位（BUSINESS_CHAIN_11_BLUEPRINT §一）

```
用户输入 → 00 PCR → 03 Intent → 11 Blueprint → BlueprintDAG
  → EventBus → 00 PCR / 01 Discourse / 02 Context / 03 Intent /
               08 Profile / 10 Subgraph / LLM Reply / 09 Meta audit
```

阶段: Intent→SkillRegistry.match → 策略（TEMPLATE/HYBRID/LLM_DRIVEN）
  → 构建 DAG → ConstraintCheck → EventBus 执行 → Meta 异步审计

下游调控: EventBus 10 链状态 → Meta 评分 → SkillRegistry 权重调整
  连续 3 次低分 → LLM_DRIVEN→HYBRID→TEMPLATE（降级）
  连续 5 次高分 → 升级策略

---

## 五、node_type 协议（DESIGN_BLUEPRINT_ORCHESTRATION §15）

### Blueprint 层（业务链节点）

| node_type | 层级 | 说明 |
|-----------|------|------|
| `pcr` | Blueprint | PCR 路由（输入域分析） |
| `intent` | Blueprint | 意图拆分 |
| `context` | Blueprint | 上下文组装 |
| `subgraph` | Blueprint | 子图编译 |
| `profile` | Blueprint | 画像注入 |
| `llm_reply` | Blueprint | LLM 最终回复 |

### TaskGraph 层（执行节点）

| node_type | 层级 | 说明 |
|-----------|------|------|
| `scan` | TaskGraph | 扫描/收集 |
| `read` | TaskGraph | 读取 |
| `write` | TaskGraph | 写入/修改 |
| `analyze` | TaskGraph | 分析 |
| `ask_user` | TaskGraph | 询问用户 |
| `explain` | TaskGraph | 解释/文档 |
| `fallback` | TaskGraph | 兜底 |

> Blueprint 层节点可展开为子 task_graph（嵌套树结构）。

---

## 六、执行形态（DESIGN_EXECUTION_LAYER + GLOBAL_STATE_MACHINE）

### 7 树并行

```
DiscourseBlockTree (基类)
  ├── DiscourseTree    对话内容
  ├── ExecutionTree    任务分解/执行（最活跃）
  ├── ConstraintTree   EngineeringChain 约束
  ├── AssociationTree  RelationSubstrate 实体关系
  ├── BehaviorTree     用户偏好/修正历史
  ├── MetaTree         元认知仲裁
  └── ProfileTree      用户画像
```

### 查询驱动（非通知）

```
树 A 需要信息 → query → 目标树活跃节点 → 找到 → 读取
  → 未找到 → 双方案并行（子 Agent 探索 ∥ 持久化搜索）→ LLM 融合去重
  → 目标计算中 → 不阻塞，下次 Tick 重新 query
```

### Command→Event→State

```
用户 Command / LLM 输出 / 系统事件
  → Decider.decide()（唯一决策入口，每次 1 Event，防广播风暴）
  → Event（不可变日志）
  → evolve → State（派生视图）
```

---

## 七、现状差距（模板 vs 设计）

| 维度 | 设计要 | 现状 | 差距 |
|------|--------|------|------|
| 模板内容 | 技能×工具×安全约束 | 只有链名 | 丢工具/约束 |
| 执行语义 | 同 Tick 并行 | Kahn 串行拓扑 | 无并行 |
| async 段 | meta/behavior 事件广播 | deferred stub | 未接 |
| 模板数 | 5 技能 + generic | 5 模板（名同内容异） | 内容缺失 |
| 约束层 | 安全/资源/依赖/权限 | 只有资源+依赖 | 缺安全/权限 |
| PlanGate | checkpoint 暂停 | checkpoint 字段无执行 | 未接 |
| Meta 闭环 | 评分→权重→降级 | 零调用方 | 未接 |

---

## 八、重构方向（模板 = 订阅表语义）

### 每个模板 = Tick 分组的 DAG

```
code_analysis（重构后）:
  Tick0: pcr ∥ intent          （并行）
  Tick1: context ∥ subgraph ∥ profile （并行，依赖 Tick0）
  Tick2: llm_reply              （依赖全部）
  async: meta.audit / behavior.learn（事件广播）
  params: tools=[read,grep,write], safety=read_only_report
```

### 工具/安全约束进 node.params

```python
BlueprintNode(
  node_id="subgraph_3", chain="subgraph", priority=1,
  params={"tools": ["read", "grep"],
          "safety": {"mode": "read_only"},
          "checkpoint": False},
)
```

### 执行器对齐

```
run_dag 按 Tick 分组:
  同 Tick 节点 → ThreadPoolExecutor 并行（依赖满足后）
  跨 Tick → 等待上一 Tick 完成
  async 段（meta/behavior）→ 发事件广播（EventBus）
```

---

## 九、验收门槛

1. 5 模板全部带工具映射 + 安全约束参数
2. `run_dag` 同 Tick 并行实测（node_latency 显示并行耗时 < 串行和）
3. async 段（meta/behavior）真实发事件，非 deferred
4. 全链测试用真实模板 + bootstrap，断言并行语义
5. 全量测试收集 0 错误
