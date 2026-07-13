# DialogMesh v4

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Tests: 450+](https://img.shields.io/badge/tests-450%2B-green)](docs/v3.0/TEST_REPORT.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

**认知引擎** — 不是更好的 prompt，是让 LLM 能理解代码世界的关系结构。

---

## 30 秒上手

`ash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh
pip install -r requirements.txt

# 启动交互模式
python main.py
> add monitoring to gateway
> status
> quit

# 一键启动（Windows）
cli.bat

# 查看系统状态
python scripts/dialogmesh.py status
python scripts/dialogmesh.py inspect hypotheses
`

---

## CLI 命令大全

### 运行时
`ash
dialogmesh start                    # 启动认知引擎
dialogmesh status                   # 引擎状态统计
dialogmesh event "add monitoring"   # 发送事件
dialogmesh health                   # 系统健康检查
`

### 查看认知状态
`ash
dialogmesh inspect observations     # 查看观测池
dialogmesh inspect hypotheses       # 查看假设竞争
dialogmesh inspect knowledge        # 查看已冻结知识
dialogmesh inspect skills           # 查看蒸馏技能
dialogmesh inspect world            # 查看世界图结构
dialogmesh inspect context          # 查看上次上下文编译

# 详细模式
dialogmesh inspect hypotheses --detail --id hyp_001   # 7维信念状态全量
dialogmesh inspect observations --json                # JSON输出
`

### 流水线编排
`ash
dialogmesh pipeline default         # 生成默认v4流水线
dialogmesh pipeline show v4-default
dialogmesh pipeline export v4-default config/custom.yaml
`

### 运维
`ash
dialogmesh snapshot list            # 查看快照
dialogmesh config show              # 查看配置
dialogmesh maintenance stats        # 存储分层状态
dialogmesh events history           # 事件审计
dialogmesh search "gateway"         # 跨模块搜索
dialogmesh export knowledge         # 导出知识
`

**27 个命令，54 个测试，零失败。** 完整参考：[DESIGN_CLI_REFERENCE.md](docs/v3.0/DESIGN_CLI_REFERENCE.md)

---

## 是什么

DialogMesh v4 是一台认知引擎。它做的事不是"给 LLM 更好的 prompt"——
它把代码库、用户行为和工程约束建模为结构化关系图，让 LLM 看到一个"局部世界"。

`
Event -> Observation -> Hypothesis -> Knowledge -> Skill
(事实)   (候选解释)     (竞争信念)      (冻结共识)   (可复用能力)
`

**和 RAG / GraphRAG / AutoGPT 的区别：** v4 不替代它们。v4 做它们不做的那一层——
在检索到信息之后、LLM 推理之前的知识组织和信念形成。

---

## 快速开始

### 终端交互模式

`ash
python main.py
# 输入文本发送事件，输入 status 看统计，输入 checkpoint 触发慢路径
`

### 单次命令

`ash
python scripts/dialogmesh.py start
python scripts/dialogmesh.py status
python scripts/dialogmesh.py event "add monitoring to gateway"
python scripts/dialogmesh.py inspect hypotheses
`

### 程序化调用

`python
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.v4.event_ir import EventIR

engine = CognitiveRuntimeEngine()
engine.start()

event = EventIR(id="ev1", kind="dialog.message",
                payload={"text": "add monitoring", "source": "user"})
engine.on_event(event)
engine.trigger_checkpoint()

for name, stats in engine.stats.items():
    print(f"{name}: {stats.trigger_count} triggers")
engine.stop()
`

---

## 核心模块

| 模块 | 做什么 |
|:---|:---|
| Observation Compiler | 把用户事件投影到 5 个认知域（行为/工程/记忆/对话/用户） |
| Hypothesis Engine | 7 维信念状态 + 证据投票，假说自然竞争直到共识形成 |
| Knowledge Vault | 冻结稳定共识，从竞争假说中沉淀事实 |
| Skill Layer | 重复 Pattern 蒸馏为可执行能力蓝图 |
| Semantic World Model | 代码库建模为图（社区检测 + 骨干染色 + 分层重要性） |
| Context Engineering | DomainSelector → BudgetAllocator → CrossDomainContextIR |
| Cognitive Runtime | 四路径调度（Async/Slow/Deep）自动触发 |
| CLI + API | 27 命令 CLI + FastAPI REST 接口 + EventLog 审计 |

---

## 运行测试

`ash
python -m pytest core/agent/v4/ -q --noconftest
# 450+ tests, 0 failures
`

---

## 项目结构

`
core/agent/v4/
    runtime/           认知调度
    world/             语义世界模型
    observation_compiler/ 观测编译
    hypothesis_engine/ 假设引擎
    skill_layer/       技能层
    context/           上下文工程
    tiered/            多级管道
    persistence/       持久化
    optimizer/         贝叶斯优化
    cli/               CLI (27 命令)
`

---

## 设计文档

全部在 [docs/v3.0/](docs/v3.0/)：
DESIGN_OBSERVATION_COMPILER.md, DESIGN_HYPOTHESIS_ENGINE.md,
DESIGN_SKILL_LAYER.md, DESIGN_SEMANTIC_WORLD_MODEL.md,
DESIGN_COGNITIVE_RUNTIME.md, DESIGN_CLI_REFERENCE.md,
DESIGN_API_EVENT_LOG.md, DESIGN_CLI_INSPECT.md,
DESIGN_TUI.md 等 14 篇。

---

## 已知局限

- Python only, 单机部署, pre-1.0 API 可能变更
- 未做大规模 benchmark, 无 GPU 优化
- 对外依赖零（SQLite 默认, Neo4j/Milvus 预留接口）
- Fast Path (DomainSelector/BudgetAllocator) 未完成

## License

MIT
