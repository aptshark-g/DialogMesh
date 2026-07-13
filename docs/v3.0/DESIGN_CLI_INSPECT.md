# DESIGN_CLI_INSPECT.md -- CLI 状态查看系统

> 版本: v1.1 | 日期: 2026-07-13
>
> 为 v4 CLI 增加 inspect 命令族，提供类似 Linux ps/	op/ls 的文本表格查看能力。
> 所有 inspect 命令只读，不修改系统状态。

---

## 1. 命令体系

`
dialogmesh inspect observations [--limit N] [--domain X]
dialogmesh inspect hypotheses   [--status active|frozen|all] [--limit N]
dialogmesh inspect knowledge    [--limit N]
dialogmesh inspect skills       [--domain X] [--status candidate|verified|all]
dialogmesh inspect world        [--community|--backbone|--stats]
dialogmesh inspect context      [--last]
dialogmesh inspect store        [--stats|--nodes|--edges|--snapshots]
`

### v3.2 模块

\dialogmesh inspect behavior     [--user X] [--limit N]     # v3.2 行为图谱
dialogmesh inspect causal       [--source X] [--limit N]   # v3.2 因果链
dialogmesh inspect constraints  [--domain X]               # 工程约束 (v3.2)
dialogmesh inspect discourse    [--node X] [--depth N]     # 对话树结构 (v3.2)
dialogmesh inspect fusion       [--status]                 # 融合引擎 (v3.2)
dialogmesh inspect summary      [--level l1|l2] [--topic]  # L1/L2 摘要 (v3.2)
\
### v3 持久化与基础设施

\dialogmesh inspect store        [--stats|--tiers|--gc]     # 图存储分层 + GC
dialogmesh inspect pcr          [--params|--trace]         # 参数注册表 + 审计
dialogmesh inspect topics       [--tree]                   # 话题树
\
## 2. 输出格式 (v4)



统一文本表格，字段按命令不同：

### observations

| ID | Domain | Summary | Time |
|:---|:---|:---|:---|
| obs_001 | engineering | Gateway monitoring | 12:34 |

### hypotheses

| ID | Statement | Status | Support | Conflict | Stability | Consensus |
|:---|:---|:---|:---|:---|:---|:---|
| hyp_001 | User developing Gateway | active | 12 | 3 | 0.81 | 2 domains |

### knowledge

| ID | Statement | Domain | Score | Frozen |
|:---|:---|:---|:---|:---|
| k_001 | Gateway needs monitoring | engineering | 0.88 | 12:30 |

### skills

| Name | Domain | Status | Usage | Success Rate |
|:---|:---|:---|:---|:---|
| middleware_monitor | engineering | verified | 5 | 95% |

### world --stats

`
Graph: code (342 nodes, 891 edges)
Communities: 12
Backbone nodes (>0.7): gateway.main, gateway.auth, gateway.logger
Last extracted: 2026-07-13 12:30:00
`

### context --last

`
Intent: "add monitoring to gateway"
Total entries: 15 (850 tokens)

[observation]   3 items (relevance: 0.50-0.65)
[knowledge]     5 items (relevance: 0.72-0.91)
[skill]         2 items (relevance: 0.60-0.73)
[world]         5 items (relevance: 0.45-0.82)
`

### store --stats

`
Nodes: 342 (warm: 200, cold: 100, archive: 42)
Edges: 891
Snapshots: 5 (latest: snap_20260713_120000)
DB path: data/dialogmesh.db
`

## 3. 实现映射

每个 inspect 命令从 CognitiveRuntimeEngine 获取数据，没有间接层：

| 命令 | 数据源 | 模块 | 版本 |
|:---|:---|:---|:---|
| observations | ObservationPool | v4/observation_compiler | v4 |
| hypotheses | HypothesisPipeline | v4/hypothesis_engine | v4 |
| knowledge | DecayResolveEngine | v4/hypothesis_engine | v4 |
| skills | SkillPool | v4/skill_layer | v4 |
| world | StructuralWorldGraph | v4/world | v4 |
| context | CrossDomainContextIR | v4/context | v4 |
| behavior | BehaviorGraph | v3_2/behavior_graph | v3.2 |
| causal | CausalSubstrate | v3_2/causal_substrate | v3.2 |
| constraints | EngineeringChain | v3_2/engineering_chain | v3.2 |
| discourse | DiscourseBlockTree | v3_2/discourse_block_tree | v3.2 |
| fusion | FusionEngine | v3_2/fusion | v3.2 |
| summary | SummaryBuilder | v3_2/l1_summary, l2_summary | v3.2 |
| store | TieredGraphStore | persistence | v3+ |
| pcr | PCRRegistry | pcr | v3+ |
| topics | TopicTreeManager | topic_tree | v3+ |
|:---|:---|:---|
| observations | _engine._observation_pool | observation_compiler/pool.py |
| hypotheses | lazy import HypothesisPipeline | hypothesis_engine/pipeline.py |
| knowledge | lazy import DecayResolveEngine | hypothesis_engine/decay_resolve.py |
| skills | lazy import SkillPool | skill_layer/skill_pool.py |
| world | _engine._world_graph (if loaded) | world/schema.py |
| context | _engine._last_context | context/cross_domain_ir.py |
| store | lazy import UnifiedGraphStore | persistence/unified_store.py |

## 4. 文件规划

`
core/agent/v4/cli/
├── main.py              # 扩展: 注册 inspect 子命令 (v4 + v3)
├── inspect.py           # 新增: v4 inspect 命令实现
├── inspect_v3.py        # 新增: v3.2 / v3 inspect 命令实现
├── builder.py           # 已有: pipeline DAG builder
├── __init__.py
└── tests/
    ├── test_main.py
    ├── test_builder.py
    ├── test_inspect.py
    └── test_inspect_v3.py
`

## 5. 完整命令列表 (15 个 inspect)

\dialogmesh inspect observations  [--limit N] [--domain X]       # v4
dialogmesh inspect hypotheses    [--status] [--limit N]         # v4
dialogmesh inspect knowledge     [--limit N]                    # v4
dialogmesh inspect skills        [--domain X] [--status]        # v4
dialogmesh inspect world         [--community|--stats]          # v4
dialogmesh inspect context       [--last]                       # v4
dialogmesh inspect behavior      [--user X] [--limit N]         # v3.2
dialogmesh inspect causal        [--source X] [--limit N]       # v3.2
dialogmesh inspect constraints   [--domain X]                   # v3.2
dialogmesh inspect discourse     [--node X] [--depth N]         # v3.2
dialogmesh inspect fusion        [--status]                     # v3.2
dialogmesh inspect summary       [--level l1|l2] [--topic]      # v3.2
dialogmesh inspect store         [--stats|--tiers|--gc]         # v3+
dialogmesh inspect pcr           [--params|--trace]             # v3+
dialogmesh inspect topics        [--tree]                       # v3+
\
## 6. 设计原则

- **只读**: inspect 不修改任何系统状态
- **薄壳**: 每个命令 <15 行，直接委托给对应模块
- **文本优先**: 输出是文本表格，不是 JSON
- **容错**: 引擎未启动时打印提示，不抛异常
