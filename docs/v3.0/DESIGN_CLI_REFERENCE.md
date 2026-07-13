# DESIGN_CLI_REFERENCE.md — CLI 命令大全

> 版本: v3.0 | 日期: 2026-07-14
>
> DialogMesh v4 CLI 完整命令参考。覆盖运行时控制、流水线编排、系统查看、运维管理。

---

## 1. 命令总览 (27 个命令)

`
运行时:
  start     [--config PATH]             启动 Cognitive Runtime
  stop                                  停止 Runtime
  status                                引擎状态统计
  event     TEXT                        发送用户事件
  health                                系统健康检查 [NEW]

编排:
  pipeline create   NAME                创建流水线
  pipeline add      NAME MODULE TYPE    添加模块
  pipeline connect  NAME FROM TO        连接模块
  pipeline param    NAME MOD KEY VAL    设置参数
  pipeline show     NAME                查看流水线
  pipeline list                         列出所有流水线
  pipeline export   NAME PATH           导出 YAML
  pipeline default                      生成默认 v4 DAG

查看 (摘要):
  inspect observations [--page N --page-size M]
  inspect hypotheses   [--page N --page-size M]
  inspect knowledge
  inspect skills       [--page N --page-size M]
  inspect world
  inspect context
  inspect behavior     [v3.2] inspect causal [v3.2]
  inspect constraints  [v3.2] inspect discourse [v3.2]
  inspect fusion       [v3.2] inspect summary [v3.2]
  inspect store        [v3+]  inspect pcr [v3+]
  inspect topics       [v3+]

查看 (详情):
  inspect X --detail [--id ID]         单条钻取 (7-dim BeliefState 全量)
  inspect X --detail --page N           分页全量展开
  inspect X --json                       JSON 输出 [NEW]

审计:
  event history [--limit N] [--kind X]  事件历史
  event replay [--unconsumed]           重放未消费事件

运维:
  maintenance gc                        手动触发 GC + 冷热迁移
  maintenance stats                     存储分层状态

搜索:
  search KEYWORD [--module X]           跨模块搜索

导出:
  export knowledge [--output PATH]      导出 Knowledge
  export skills [--output PATH]         导出 Skills
  import skills PATH                    导入 Skills [FUTURE]

监控:
  inspect X --watch [--interval SEC]    实时刷新

会话:
  session list                          列出活跃会话
  session show ID                       查看会话详情

自动补全:
  completion bash/zsh/powershell        生成 Shell 补全脚本
  inspect X --detail [--id ID]         单条钻取 (7-dim BeliefState 全量)
  inspect X --detail --page N           分页全量展开
  inspect X --json                       JSON 输出 [NEW]

运维 [NEW]:
  snapshot list                        列出快照
  snapshot restore SNAPSHOT_ID        恢复快照
  config show                          查看当前配置
  config set KEY VALUE                 修改配置项
  maintenance gc                       手动触发 GC + 冷热迁移 [FUTURE]
  search KEYWORD                       跨模块搜索 [FUTURE]
`

## 2. 运行时命令

### start
`
dialogmesh start [--config PATH]
`
启动 Cognitive Runtime Engine。加载 runtime.yaml 配置，实例化所有适配器。
--config: 可选，指定自定义配置文件路径。默认 config/runtime.yaml。

### stop
`
dialogmesh stop
`
停止 Runtime，清理适配器、ObservationPool、定时器。

### status
`
dialogmesh status
`
显示四路径统计：触发次数、成功/失败数、总延迟。

### event
`
dialogmesh event "add monitoring to gateway"
`
发送一个用户事件。触发 Async Path (Observation Compiler)。

### health [NEW]
`
dialogmesh health
`
全面健康检查：
- 所有 v4 模块可导入性
- SQLite 数据库连接状态
- 磁盘空间 (data/ 目录)
- Runtime 引擎状态 (如已启动)

## 3. 流水线编排命令

### pipeline create
`
dialogmesh pipeline create my-pipeline
`
创建一个空流水线。

### pipeline add
`
dialogmesh pipeline add my-pipeline obs observation_compiler
dialogmesh pipeline add my-pipeline hyp hypothesis_engine --path slow
`
向流水线添加模块。--path 指定运行路径 (async/slow/deep)，默认 async。
可用类型: observation_compiler, hypothesis_engine, skill_distiller, world_model。

### pipeline connect
`
dialogmesh pipeline connect my-pipeline obs hyp
`
连接两个模块。

### pipeline param
`
dialogmesh pipeline param my-pipeline hyp min_support 8
`
设置模块参数。

### pipeline show
`
dialogmesh pipeline show my-pipeline
`
显示流水线 DAG：节点列表 + 边列表。

### pipeline list
`
dialogmesh pipeline list
`
列出所有已创建的流水线。

### pipeline export
`
dialogmesh pipeline export my-pipeline config/custom.yaml
`
导出流水线为 YAML 配置。

### pipeline default
`
dialogmesh pipeline default
`
生成默认 v4 三阶段流水线：Observer -> Hypothesis -> Skill。

## 4. 查看命令 — 摘要模式

### inspect observations
`
dialogmesh inspect observations [--page 1 --page-size 10]
`
显示 Observation 池中的最近观测。支持分页。

输出示例:
`
ID              Domain        Summary                         Time
obs_001         engineering   Gateway monitoring pattern      12:34
obs_002         behavior      User editing pipeline config    12:33
`

### inspect hypotheses
`
dialogmesh inspect hypotheses [--page 1 --page-size 10]
`
显示 Hypothesis 竞争状态。

输出示例:
`
ID          Statement                           Status  Support Conflict Stability
hyp_001     User developing Gateway             active  12      3        0.81
hyp_002     User learning Gateway               active  4       6        0.35
`

### inspect knowledge
`
dialogmesh inspect knowledge
`
显示冻结的 Knowledge 节点。

### inspect skills
`
dialogmesh inspect skills [--page 1 --page-size 10]
`
显示蒸馏出的 Skill。

### inspect world
`
dialogmesh inspect world
`
显示 World Graph 统计：节点数、边数、社区数、Top 骨干节点。

### inspect context
`
dialogmesh inspect context
`
显示上次编译的 CrossDomainContextIR：intent、各域条目数、relevance 范围。

### v3.2 查看命令
`
dialogmesh inspect behavior     # 行为图谱
dialogmesh inspect causal       # 因果链
dialogmesh inspect constraints  # 工程约束
dialogmesh inspect discourse    # 对话树
dialogmesh inspect fusion       # 融合引擎
dialogmesh inspect summary      # L1/L2 摘要
`

### v3+ 查看命令
`
dialogmesh inspect store        # 分层存储状态
dialogmesh inspect pcr          # 参数注册表
dialogmesh inspect topics       # 话题树
`

## 5. 查看命令 — 详情模式

### --detail + --id: 单条钻取
`
dialogmesh inspect hypotheses --detail --id hyp_001
`
显示单个 Hypothesis 的完整 7 维 BeliefState：
`
ID:        hyp_001
Statement: User developing Gateway
Domain:    engineering
Status:    active
Belief State:
  support:   12
  conflict:  3
  stability: 0.81
  coverage:  0.72
  recency:   1.00
  novelty:   0.12
  entropy:   0.05
Domain Signals: {'behavior': 'support', 'engineering': 'support'}
`

### --detail + --page: 分页全量展开
`
dialogmesh inspect observations --detail --page 1 --page-size 10
`
每页显示 10 条 Observation 的详细内容，包括 interpretations 和 evidence 列表。

### --json: JSON 输出 [NEW]
`
dialogmesh inspect hypotheses --json
dialogmesh inspect hypotheses --detail --id hyp_001 --json
`
输出 JSON 格式，供外部脚本消费。

## 5.5 --json 输出标志 [NEW]

### 全局 JSON 输出
`
dialogmesh inspect hypotheses --json
dialogmesh inspect knowledge --json
dialogmesh inspect world --json
`
所有 inspect 子命令支持 --json 标志。当指定时，输出为 JSON 而非文本表格。

输出格式：
`json
{
  "command": "inspect hypotheses",
  "data": [
    {"id": "hyp_001", "statement": "...", "status": "active", ...},
    {"id": "hyp_002", "statement": "...", "status": "frozen", ...}
  ],
  "count": 2
}
`

## 5.6 事件审计命令 [NEW]

### event history
`
dialogmesh event history [--limit N] [--kind X]
`
查看事件历史。从 EventLog (SQLite) 读取。支持按 kind 过滤（dialog.message / ui.drag / git.commit）。

### event replay
`
dialogmesh event replay [--unconsumed]
`
重放事件。--unconsumed 只重放未消费事件。用于 crash recovery / 回放测试。

## 5.7 存储维护命令 [NEW]

### maintenance gc
`
dialogmesh maintenance gc
`
手动触发 GC：热→温→冷→归档分层迁移 + 旧事件清理。

### maintenance stats
`
dialogmesh maintenance stats
`
显示分层存储状态：每层节点数、磁盘使用量、上次 GC 时间。

## 5.8 跨模块搜索 [NEW]

### search
`
dialogmesh search "gateway monitoring" [--module X]
`
跨所有认知模块搜索关键词。匹配 Observation、Hypothesis、Knowledge、Skill。
--module 可限定搜索范围（observations / hypotheses / knowledge / skills）。

## 5.9 导出导入 [NEW]

### export knowledge / export skills
`
dialogmesh export knowledge --output data/knowledge.json
dialogmesh export skills --output data/skills.json
`
导出冻结 Knowledge 或 Skill 为 JSON 文件。用于备份、迁移、分析。

### import skills [FUTURE]
`
dialogmesh import skills data/skills.json
`
从 JSON 文件导入 Skill。需要验证格式和去重逻辑。

## 5.10 实时监控 [NEW]

### --watch 标志
`
dialogmesh inspect observations --watch --interval 5
dialogmesh inspect hypotheses --watch
`
实时刷新显示。类似 Linux watch 命令。默认间隔 2 秒。

## 5.11 会话管理 [NEW]

### session list / session show
`
dialogmesh session list
dialogmesh session show <session_id>
`
列出活跃会话或查看单个会话详情。

## 5.12 Shell 自动补全 [NEW]

### completion
`
dialogmesh completion bash > ~/.bash_completion.d/dialogmesh
dialogmesh completion zsh  > ~/.zfunc/_dialogmesh
dialogmesh completion powershell > dialogmesh.ps1
`
生成 Shell 自动补全脚本。

## 6. 运维命令 [NEW]

### snapshot list
`
dialogmesh snapshot list
`
列出所有快照：snapshot_id、时间、节点数、边数。

### snapshot restore
`
dialogmesh snapshot restore snap_20260713_120000
`
验证快照存在并可用。完整恢复通过 UnifiedGraphStore 实现。

### config show
`
dialogmesh config show
`
显示当前配置 (WorldParams + runtime.yaml 合并视图)。

### config set
`
dialogmesh config set world.importance.strategy pagerank
`
修改配置项。持久化到 runtime.yaml。

### maintenance gc [FUTURE]
`
dialogmesh maintenance gc
`
手动触发 GC：热→温→冷→归档分层迁移 + 旧快照清理。

### search [FUTURE]
`
dialogmesh search "gateway monitoring"
`
跨所有模块搜索关键词，返回匹配的 Observation/Hypothesis/Knowledge/Skill。

## 7. 输出格式约定

| 模式 | 用途 | 示例 |
|:---|:---|:---|
| 文本表格 (默认) | 人类阅读 | inspect hypotheses |
| 文本详情 (--detail) | 单条深入 | inspect hypotheses --detail --id H1 |
| JSON (--json) | 脚本消费 | inspect hypotheses --json |

## 8. 文件规划

`
core/agent/v4/cli/
├── main.py              # CLI入口: argparse + 命令路由
├── inspect.py           # v4 查看命令 (摘要 + 详情 + JSON)
├── inspect_v3.py        # v3.2/v3 查看命令
├── builder.py           # 流水线 DAG 构建器
├── snapshot.py          # 快照管理命令
├── config_cmd.py        # 配置管理命令
├── health.py            # 健康检查命令
├── event_cmd.py         # 事件审计命令 [NEW]
├── maintenance_cmd.py   # 存储维护命令 [NEW]
├── search_cmd.py        # 跨模块搜索命令 [NEW]
├── export_cmd.py        # 导出命令 [NEW]
├── session_cmd.py       # 会话管理命令 [NEW]
├── __init__.py
└── tests/
    ├── test_main.py
    ├── test_builder.py
    ├── test_inspect.py
    ├── test_ops.py
    ├── test_event_cmd.py [NEW]
    ├── test_maintenance.py [NEW]
    ├── test_search.py [NEW]
    └── test_export.py [NEW]
├── main.py              # CLI入口: argparse + 命令路由
├── inspect.py           # v4 查看命令 (摘要 + 详情 + JSON)
├── inspect_v3.py        # v3.2/v3 查看命令
├── builder.py           # 流水线 DAG 构建器
├── snapshot.py          # 快照管理命令 [NEW]
├── config_cmd.py        # 配置管理命令 [NEW]
├── health.py            # 健康检查命令 [NEW]
├── __init__.py
└── tests/
    ├── test_main.py
    ├── test_builder.py
    ├── test_inspect.py
    └── test_snapshot.py, test_config.py, test_health.py [NEW]
`

## 9. CLI 完成度

| 状态 | 命令数 | 内容 |
|:---|:---|:---|
| ✅ 已实现 | 21 | start/stop/status/event/health + pipeline(8) + inspect(6 v4 + 9 v3) + snapshot/config |

| 优先级 | 命令 | 用途 | 工作量 |
|:---|:---|:---|:---|
| 🔴 | --json 输出 | TUI/脚本消费 | 小 |
| 🔴 | event history/replay | 审计和回放 | 小 |
| 🔴 | maintenance gc/stats | 存储管理 | 小 |
| 🔴 | search | 跨模块搜索 | 中 |
| 🟡 | export knowledge/skills | 备份迁移 | 小 |
| 🟡 | --watch (监控) | 实时刷新 | 小 |
| 🟢 | session list/show | 会话管理 | 小 |
| 🟢 | completion | Shell 补全 | 小 |

| 优先级 | 命令 | 依赖 | 工作量 |
|:---|:---|:---|:---|
| 🔴 | snapshot list/restore | UnifiedGraphStore + SnapshotManager | 小 |
| 🔴 | config show/set | WorldParams + runtime.yaml | 小 |
| 🟡 | health | 模块导入 + SQLite 连接检查 | 小 |
| 🟡 | --json 输出 | json.dumps | 小 |
| 🟢 | maintenance gc | TieredGraphStore | 中 |
| 🟢 | search | 跨模块查询 | 中 |
