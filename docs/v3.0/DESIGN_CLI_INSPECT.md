# DESIGN_CLI_INSPECT.md -- CLI 状态查看系统

> 版本: v1.0 | 日期: 2026-07-13
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

## 2. 输出格式

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

| 命令 | 数据源 | 模块 |
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
├── main.py              # 扩展: 注册 inspect 子命令
├── inspect.py           # 新增: inspect 命令实现 (所有输出逻辑)
├── builder.py           # 已有: pipeline DAG builder
├── __init__.py
└── tests/
    ├── test_main.py      # 已有
    ├── test_builder.py   # 已有
    └── test_inspect.py   # 新增: inspect 命令测试
`

## 5. 设计原则

- **只读**: inspect 不修改任何系统状态
- **薄壳**: 每个命令 <15 行，直接委托给对应模块
- **文本优先**: 输出是文本表格，不是 JSON
- **容错**: 引擎未启动时打印提示，不抛异常
