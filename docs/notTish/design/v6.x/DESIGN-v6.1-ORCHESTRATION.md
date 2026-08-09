# Literature Cortex v6.1 — 编排层设计文档

> **文档编号:** LC-DESIGN-v6.1-ORCHESTRATION
> **版本:** v6.1-rev1
> **状态:** 🚧 IMPLEMENTATION IN PROGRESS
> **日期:** 2026-06-25
> **核心目标:** 让 Agent 能够自主发现、配置、编排系统全部功能

---

## 1. 问题定义

当前系统各层硬编码耦合，Agent 无法：
- 发现系统有哪些功能
- 查看功能的输入/输出契约
- 运行时替换或跳过某层
- 自定义执行流程（如"跳过 CL2，加大 CL3 预算"）
- 追踪执行状态和中间结果

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  Agent                                                      │
│  - "列出所有验证类功能"                                      │
│  - "执行轻量级分析流程（跳过远迁移）"                         │
│  - "检查执行状态 #exec-001"                                  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Orchestration API (REST / Python SDK)                      │
│  - GET  /capabilities?tag=validation                        │
│  - GET  /capabilities/{id}/contract                         │
│  - POST /execute (YAML pipeline definition)                 │
│  - GET  /execute/{id}/state                                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator Engine                                        │
│  ├─ Pipeline Loader (YAML/JSON → DAG)                      │
│  ├─ Dependency Resolver (拓扑排序)                          │
│  ├─ Condition Evaluator (Jinja2)                           │
│  ├─ Hook Manager (pre/post/around)                         │
│  ├─ Budget Manager (token/time 配额)                        │
│  └─ State Journal (每步输入/输出/耗时持久化)                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Capability Registry                                        │
│  ├─ "cl0.validate" → CL0HardConstraintLayer                │
│  ├─ "cl1.reflect"  → CL1NearTransferReflection             │
│  ├─ "csm.evaluate" → CSMCognitiveFlow                      │
│  ├─ "cl2.think"    → CL2FarTransferThinking                │
│  ├─ "l5.arbitrate" → MetaCognitiveArbiter                  │
│  └─ ... (动态注册)                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心概念

### 3.1 Capability（功能单元）

系统最小可编排单元。每个 Capability 有：
- **唯一 ID**（如 `cl0.validate`）
- **输入/输出契约**（JSON Schema）
- **版本**
- **标签**（用于分类发现）
- **成本估算**（时间、token）
- **前置条件**

### 3.2 Pipeline Definition（流程定义）

声明式 YAML 定义执行流程：

```yaml
name: lightweight_analysis
version: "1.0"

capabilities:
  - id: layer2.parse
    alias: parse
  - id: cl0.validate
    alias: validate
  - id: cl1.reflect
    alias: reflect
    config:
      max_history: 10
  - id: cl3.challenge
    alias: question

flow:
  - step: parse
    input:
      text: "{{ input.raw_text }}"
    output: parse_result

  - step: validate
    input:
      sgf: "{{ steps.parse.output.sgf }}"
    output: validation
    on_failure: abort

  - step: reflect
    input:
      sgf: "{{ steps.parse.output.sgf }}"
    output: reflection
    condition: "{{ steps.validate.output.critical_count == 0 }}"

  - step: question
    input:
      cl0_report: "{{ steps.validate.output }}"
      cl1_report: "{{ steps.reflect.output | default(null) }}"
    output: questions

output:
  sgf: "{{ steps.parse.output.sgf }}"
  validation: "{{ steps.validate.output }}"
  questions: "{{ steps.question.output }}"
```

### 3.3 Execution Context（执行上下文）

每步执行时的上下文，包含：
- `execution_id`: 全局唯一执行 ID
- `step_results`: 已完成步骤的结果字典
- `budget`: 剩余 token / 时间配额
- `metadata`: 用户传入的自定义数据

---

## 4. 接口设计

### 4.1 Capability 注册接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class CapabilityContract:
    capability_id: str
    name: str
    version: str
    input_schema: dict          # JSON Schema
    output_schema: dict         # JSON Schema
    tags: list[str]
    cost_estimate: dict         # {"time_ms": 100, "tokens": 500}
    description: str = ""

class CapabilityHandler(ABC):
    @abstractmethod
    def execute(self, input_data: dict, context: ExecutionContext) -> dict:
        """执行功能，返回标准化输出字典。"""
        pass
    
    @abstractmethod
    def get_contract(self) -> CapabilityContract:
        pass
```

### 4.2 Orchestrator 核心接口

```python
class Orchestrator:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self.state_store = ExecutionStateStore()
    
    def list_capabilities(self, tags: list[str] = None) -> list[CapabilityContract]:
        """Agent 调用：发现系统功能。"""
        pass
    
    def get_contract(self, capability_id: str) -> CapabilityContract:
        """Agent 调用：查看功能契约。"""
        pass
    
    def execute(self, 
                definition: PipelineDefinition, 
                input_data: dict,
                budget: ExecutionBudget = None) -> ExecutionResult:
        """执行编排流程。"""
        pass
    
    def get_state(self, execution_id: str) -> ExecutionSnapshot:
        """查询执行状态。"""
        pass
    
    def cancel(self, execution_id: str) -> bool:
        """取消执行。"""
        pass
```

### 4.3 执行结果标准化

```python
@dataclass
class ExecutionResult:
    execution_id: str
    status: str              # "completed" | "failed" | "cancelled"
    steps: dict[str, StepResult]
    output: dict             # 最终输出
    metrics: ExecutionMetrics
    error: Optional[str] = None

@dataclass
class StepResult:
    step_alias: str
    capability_id: str
    status: str              # "completed" | "skipped" | "failed"
    input: dict
    output: dict
    started_at: str          # ISO timestamp
    completed_at: str        # ISO timestamp
    duration_ms: float
    tokens_used: int
    error: Optional[str] = None
```

---

## 5. 现有组件改造计划

### 5.1 CL0-CL4 改造

**当前问题：** CL4 内部硬编码实例化 CL0-CL3。

**改造方案：**

```python
# 改造前（硬编码）
class CL4CoordinationLayer:
    def __init__(self, ...):
        self.cl0 = CL0HardConstraintLayer()
        self.cl1 = CL1NearTransferReflection(db)

# 改造后（依赖注入）
class CL4CoordinationLayer:
    def __init__(self,
                 cl0: Optional[CL0HardConstraintLayer] = None,
                 cl1: Optional[CL1NearTransferReflection] = None,
                 cl2: Optional[CL2FarTransferThinking] = None,
                 cl3: Optional[CL3QuestioningLayer] = None,
                 budget: Optional[LayerBudget] = None):
        self.cl0 = cl0 or CL0HardConstraintLayer()
        self.cl1 = cl1 or CL1NearTransferReflection()
        self.cl2 = cl2 or CL2FarTransferThinking()
        self.cl3 = cl3 or CL3QuestioningLayer()
        self.budget = budget or LayerBudget()
```

### 5.2 Capability 包装器

为每个现有组件创建包装器：

```python
class CL0Capability(CapabilityHandler):
    def __init__(self, impl: Optional[CL0HardConstraintLayer] = None):
        self.impl = impl or CL0HardConstraintLayer()
    
    def execute(self, input_data: dict, context: ExecutionContext) -> dict:
        sgf = input_data["sgf"]
        report = self.impl.validate(sgf)
        return {
            "status": report.status.value,
            "is_valid": report.is_valid,
            "violations_count": len(report.violations),
            "critical_count": len([v for v in report.violations if v.severity == "critical"]),
            "checks_performed": report.checks_performed,
        }
    
    def get_contract(self) -> CapabilityContract:
        return CapabilityContract(
            capability_id="cl0.validate",
            name="CL0 Hard Constraint Validation",
            version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "sgf": {"$ref": "#/definitions/StandardGraphFormat"}
                },
                "required": ["sgf"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "is_valid": {"type": "boolean"},
                    "violations_count": {"type": "integer"},
                    "critical_count": {"type": "integer"},
                }
            },
            tags=["validation", "hard_constraint", "cl0"],
            cost_estimate={"time_ms": 0.06, "tokens": 0},
            description="硬约束验证层：字段完整性、环检测、量纲一致性、结构签名一致性"
        )
```

### 5.3 FormalizationPipeline 改造

**当前问题：** L1-L4 固定实例。

**改造方案：**

```python
class FormalizationPipeline:
    def __init__(self, 
                 layer1: Optional[Layer1Processor] = None,
                 layer2: Optional[Layer2Router] = None,
                 layer3: Optional[GraphComputationEngine] = None,
                 layer4: Optional[IsomorphismJudge] = None,
                 db_path: str = None):
        self.layer1 = layer1 or Layer1Processor()
        self.layer2 = layer2 or Layer2Router(...)
        self.layer3 = layer3 or GraphComputationEngine(max_depth=3)
        self.layer4 = layer4 or IsomorphismJudge()
```

---

## 6. 文件结构

```
lcortex/
└── orchestration/
    ├── __init__.py
    ├── capability.py              # CapabilityContract, CapabilityHandler ABC
    ├── registry.py                # CapabilityRegistry
    ├── orchestrator.py            # Orchestrator Engine
    ├── pipeline.py                # PipelineDefinition, DAG resolver
    ├── context.py                 # ExecutionContext, ExecutionBudget
    ├── state.py                   # ExecutionStateStore, ExecutionSnapshot
    ├── hooks.py                   # HookManager (pre/post/around)
    └── capabilities/              # 现有组件的 Capability 包装器
        ├── __init__.py
        ├── cl0_capability.py
        ├── cl1_capability.py
        ├── cl2_capability.py
        ├── cl3_capability.py
        ├── cl4_capability.py
        ├── csm_capability.py
        ├── l5_capability.py
        ├── layer2_capability.py
        └── factory.py             # 自动注册所有 Capability
```

---

## 7. 使用示例

### 7.1 Agent 发现功能

```python
from lcortex.orchestration import Orchestrator, CapabilityRegistry

orch = Orchestrator(CapabilityRegistry())
caps = orch.list_capabilities(tags=["validation"])
# [
#   CapabilityContract(id="cl0.validate", name="CL0 Hard Constraint Validation", ...),
#   CapabilityContract(id="cl3.challenge", name="CL3 Questioning Layer", ...),
# ]

contract = orch.get_contract("csm.evaluate")
# 完整输入/输出 JSON Schema
```

### 7.2 Agent 编排执行

```python
from lcortex.orchestration import PipelineDefinition

pipeline = PipelineDefinition.from_yaml("""
name: quick_check
flow:
  - step: parse
    capability: layer2.parse
    input:
      text: "{{ input.text }}"
  - step: validate
    capability: cl0.validate
    input:
      sgf: "{{ steps.parse.output.sgf }}"
    on_failure: abort
output:
  valid: "{{ steps.validate.output.is_valid }}"
""")

result = orch.execute(pipeline, {"text": "thermal system..."})
print(result.output["valid"])  # True
```

### 7.3 Agent 查询状态

```python
state = orch.get_state(result.execution_id)
for step_alias, step_result in state.steps.items():
    print(f"{step_alias}: {step_result.status} ({step_result.duration_ms}ms)")
```

---

## 8. 实施计划

### Phase 1: 基础设施（1-2 天）

- [ ] 创建 `lcortex/orchestration/` 包结构
- [ ] 实现 `CapabilityContract` + `CapabilityHandler` ABC
- [ ] 实现 `CapabilityRegistry`
- [ ] 实现 `ExecutionContext` + `ExecutionBudget`
- [ ] 实现 `ExecutionStateStore`（内存版，后续加 SQLite）

### Phase 2: 组件改造（1-2 天）

- [ ] 改造 CL4 为依赖注入模式
- [ ] 改造 FormalizationPipeline 为依赖注入模式
- [ ] 为 CL0-CL4、CSM、L5、Layer2 创建 Capability 包装器
- [ ] 实现 `CapabilityFactory` 自动注册

### Phase 3: 执行引擎（2-3 天）

- [ ] 实现 `PipelineDefinition`（YAML/JSON 解析）
- [ ] 实现 DAG 依赖解析器
- [ ] 实现 Jinja2 条件表达式求值
- [ ] 实现 `Orchestrator.execute()` 核心循环
- [ ] 实现 `on_failure` 处理（abort/skip/continue）

### Phase 4: 高级特性（2 天）

- [ ] 实现 Hook Manager（pre/post/around）
- [ ] 实现 Budget Manager（token/time 配额追踪）
- [ ] 实现执行日志持久化（SQLite）
- [ ] 实现取消/暂停机制

### Phase 5: 测试与文档（1-2 天）

- [ ] 编写编排层完整测试
- [ ] 更新 AGENTS.md 提供 Agent 调用示例
- [ ] 编写编排层使用手册

---

## 9. 验收标准

1. Agent 可以通过 `list_capabilities()` 发现系统全部功能
2. Agent 可以通过 YAML 定义并执行自定义流程
3. Agent 可以运行时替换任何层的实现
4. Agent 可以查询任意执行的完整状态和中间结果
5. 所有现有测试继续通过
6. 新编排层测试覆盖率 > 90%

---

## 10. 与 v6.0 的关系

v6.0 实现认知引擎的核心算法层。
v6.1 在 v6.0 之上增加编排层，不改变任何现有算法实现，只做：
- 依赖注入改造（可选参数）
- 标准化包装器（不改变内部逻辑）
- 声明式编排（新增层）

**零破坏升级。**
