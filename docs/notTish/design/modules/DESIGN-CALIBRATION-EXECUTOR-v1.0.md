# Calibration Executor — 通用校准执行器设计方案 v1.0

> **文档编号**: LC-DESIGN-CALIBRATION-v1.0  
> **日期**: 2026-06-29  
> **依赖**: LC-DESIGN-MCT-v1.0, LC-DESIGN-v6.0-UNIFIED-rev5  
> **状态**: 设计阶段

---

## 1. 核心问题

认知智流的假设校准不能绑定到单一工具（MATLAB）或单一领域（机床）。需要一个**领域无关的校准接口**，后端可插拔不同执行器。

**关键洞察**：校准的不是"假设内容"，而是**假设的可计算形式**。只要一个假设能被转译为**可执行的形式化描述**，它就能被校准。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **形式化即校准资格** | 不能转译为可计算形式的假设，只能做交叉验证，不能仿真校准 |
| **后端可插拔** | 同一接口，不同领域用不同执行器 |
| **降级优雅** | 无可用后端时，自动降级到文献交叉验证 + 预测追踪 |
| **结果可对比** | 不同后端的结果必须能映射到统一的 `CalibrationResult` 格式 |

---

## 3. 通用架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    CalibrationExecutor                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  输入解析器  │  │  形式化转译  │  │      后端路由器          │  │
│  │  (Parser)   │→ │ (Translator)│→ │    (Backend Router)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                            ↓                    │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐           │
│  │ MATLAB  │ Python  │  Unity  │  BioSim │ EconSim │ ...       │
│  │ Bridge  │ Bridge  │ Bridge  │ Bridge  │ Bridge  │           │
│  └────┬────┴────┬────┴────┬────┴────┬────┴────┬────┘           │
│       └─────────┴─────────┴─────────┴─────────┘                 │
│                          ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              CalibrationResult (统一输出)                 │   │
│  │  {status, predicted, observed, deviation, confidence}    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心接口设计

### 4.1 假设描述格式（HypothesisSpec）

领域无关的假设描述。不是自然语言，而是**结构化声明**。

```python
@dataclass
class HypothesisSpec:
    """假设的通用描述格式。"""
    
    # 身份
    hypothesis_id: UUID
    source_decision_node: UUID  # 来自 MCT 的决策节点
    
    # 内容（多模态）
    natural_language: str       # 原始自然语言描述
    formalization: Optional[Formalization]  # 形式化转译结果
    
    # 领域标识（用于路由到正确后端）
    domain_tags: List[str]      # e.g., ["control_system", "thermal", "mechanical"]
    
    # 可计算形式（后端特定）
    computable_form: Optional[ComputableForm]
    
    # 验证需求
    validation_type: ValidationType  # SIMULATION | CROSS_REF | PREDICTION_TRACKING
    required_precision: float        # 要求的精度阈值（如 0.1 = 10%）
    max_latency_seconds: float       # 最大等待时间


@dataclass
class Formalization:
    """形式化结构。"""
    formal_language: str        # "bond_graph" | "ode" | "pde" | "finite_state" | "bayesian_network"
    expressions: List[str]      # 形式化表达式列表
    variables: Dict[str, VarDef]  # 变量定义
    constraints: List[str]      # 约束条件


@dataclass
class ComputableForm:
    """可计算形式——后端可直接消费的代码/模型。"""
    backend_type: str           # "matlab" | "python" | "unity" | "sbml" | "netlogo" | ...
    code_or_model: str          # 可执行代码或模型文件路径
    input_schema: Dict          # 输入参数 schema
    output_schema: Dict         # 预期输出 schema
    execution_env: str          # 执行环境描述（Docker 镜像/conda env/...）
```

### 4.2 校准结果格式（CalibrationResult）

所有后端必须输出统一格式。

```python
@dataclass
class CalibrationResult:
    """统一校准结果。"""
    
    hypothesis_id: UUID
    backend_used: str           # 实际使用的后端
    
    # 执行状态
    status: CalibrationStatus   # VALIDATED | FALSIFIED | INCONCLUSIVE | ERROR | TIMEOUT
    
    # 数值结果
    predicted: Optional[Dict]   # 假设预测的值 {"frequency_hz": 120.5, ...}
    observed: Optional[Dict]    # 实际观测/仿真结果
    deviation: Optional[Dict]   # 偏差 {"frequency_hz": {"abs": 5.2, "rel": 0.043}}
    
    # 质量指标
    confidence: float           # 校准置信度 [0,1]
    precision_achieved: float   # 实际达到的精度
    
    # 诊断
    diagnostics: List[str]      # 诊断信息
    raw_output: str             # 后端原始输出（日志/stdout）
    execution_time_ms: float
    
    # 回填指针
    decision_node_id: UUID      # 回填到 MCT 的目标节点
```

---

## 5. 后端插件系统

### 5.1 基类

```python
class CalibrationBackend(ABC):
    """校准后端基类。"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def supported_domains(self) -> List[str]: ...
    
    @property
    @abstractmethod
    def supported_formalizations(self) -> List[str]: ...
    
    @abstractmethod
    def can_execute(self, spec: HypothesisSpec) -> bool:
        """判断此后端能否执行该假设。"""
        ...
    
    @abstractmethod
    def execute(self, spec: HypothesisSpec) -> CalibrationResult:
        """执行校准。"""
        ...


class BackendRegistry:
    """后端注册表。"""
    
    def __init__(self):
        self._backends: Dict[str, CalibrationBackend] = {}
    
    def register(self, backend: CalibrationBackend) -> None:
        self._backends[backend.name] = backend
    
    def select(self, spec: HypothesisSpec) -> Optional[CalibrationBackend]:
        """为假设选择最合适的后端。"""
        candidates = [
            b for b in self._backends.values()
            if b.can_execute(spec)
        ]
        # 优先级：精确匹配 > 部分匹配
        # 未来可扩展为基于历史成功率的选择
        return candidates[0] if candidates else None
```

### 5.2 内置后端

#### A. MATLAB Bridge（工程/控制/热力学基线）

```python
class MatlabBackend(CalibrationBackend):
    """MATLAB/Simulink 执行后端。"""
    
    name = "matlab"
    supported_domains = ["control_system", "thermal", "mechanical", "signal_processing"]
    supported_formalizations = ["ode", "transfer_function", "state_space", "bond_graph"]
    
    def can_execute(self, spec: HypothesisSpec) -> bool:
        return (
            spec.computable_form and
            spec.computable_form.backend_type == "matlab"
        ) or (
            spec.formalization and
            spec.formalization.formal_language in self.supported_formalizations
        )
    
    def execute(self, spec: HypothesisSpec) -> CalibrationResult:
        # 1. 生成 MATLAB 脚本（从 formalization 或 computable_form）
        script = self._generate_script(spec)
        
        # 2. 调用 MATLAB Engine / 命令行
        # 支持两种模式：
        #   - 本地 MATLAB（matlab.engine）
        #   - 无头模式（matlab -batch）
        result = self._run_matlab(script, timeout=spec.max_latency_seconds)
        
        # 3. 解析输出
        return self._parse_result(result, spec)
```

**覆盖领域**：
- 控制系统（传递函数、状态空间、频域分析）
- 热力学（热传导、对流、相变）
- 结构力学（模态分析、应力应变）
- 信号处理（滤波、谱分析、时频变换）

**局限性**：
- 非工程领域（如纯数学定理、社会学假设）无法直接仿真
- 需要形式化转译器将自然语言假设转为 MATLAB 代码

#### B. Python SciPy Backend（通用数学/统计）

```python
class PythonSciPyBackend(CalibrationBackend):
    """Python 科学计算后端。"""
    
    name = "python_scipy"
    supported_domains = ["mathematics", "statistics", "optimization", "machine_learning"]
    supported_formalizations = ["ode", "pde", "optimization_problem", "probabilistic_model"]
```

**覆盖领域**：
- 数学（微分方程、优化、图论）
- 统计（假设检验、贝叶斯推断、蒙特卡洛）
- 机器学习（模型训练、交叉验证、超参搜索）

#### C. Unity/PhysX Backend（空间物理/多体动力学）

```python
class UnityPhysXBackend(CalibrationBackend):
    """Unity + PhysX 物理仿真后端。"""
    
    name = "unity_physx"
    supported_domains = ["spatial_physics", "robotics", "mechanical_assembly", "collision"]
    supported_formalizations = ["rigid_body", "cad_model", "motion_profile"]
```

**覆盖领域**：
- 空间推理（碰撞检测、干涉检查）
- 机器人学（运动学、路径规划）
- 装配验证（公差分析、配合检查）

#### D. 生物仿真后端（SBML/BioNetGen）

```python
class BioSimBackend(CalibrationBackend):
    """生物系统仿真后端。"""
    
    name = "biosim"
    supported_domains = ["biochemistry", "systems_biology", "pharmacokinetics"]
    supported_formalizations = ["sbml", "ode", "stochastic_simulation"]
```

**覆盖领域**：
- 生化反应网络
- 药物代谢动力学
- 基因调控网络

#### E. 经济仿真后端（Agent-Based Modeling）

```python
class EconSimBackend(CalibrationBackend):
    """经济/社会系统仿真后端。"""
    
    name = "econsim"
    supported_domains = ["economics", "social_science", "game_theory"]
    supported_formalizations = ["agent_based_model", "game_theory", "dynamical_system"]
```

**覆盖领域**：
- 市场动态
- 博弈论策略验证
- 社会网络传播

---

## 6. 形式化转译器（关键依赖）

校准执行器的前置条件是**假设可被形式化**。需要一个通用的形式化转译管道。

```python
class FormalizationPipeline:
    """假设 → 可计算形式的转译管道。"""
    
    def __init__(self):
        self.translators: Dict[str, Translator] = {
            "control_system": ControlSystemTranslator(),
            "thermal": ThermalTranslator(),
            "mechanical": MechanicalTranslator(),
            "biochemical": BiochemicalTranslator(),
            # ... 可扩展
        }
    
    def translate(self, hypothesis: str, domain: str) -> Optional[Formalization]:
        """将自然语言假设转译为形式化结构。"""
        translator = self.translators.get(domain)
        if not translator:
            return None
        
        # 两步转译：
        # 1. 语义提取（LLM / 规则）→ 结构化中间表示
        # 2. 形式化生成（模板 + 约束求解）→ 可执行代码
        ir = translator.extract_semantics(hypothesis)
        formal = translator.generate_formalization(ir)
        
        return formal
```

**重要**：形式化转译器的准确性直接决定校准的可靠性。错误的形式化 → 正确的仿真 → 错误的结论。

---

## 7. 降级路径

不是所有假设都能被形式化/仿真。

```
假设 H
    ↓
能否形式化？
    ├── 能 → 有可执行后端？
    │           ├── 有 → 执行仿真校准
    │           └── 无 → 降级到文献交叉验证
    └── 不能 → 降级到预测追踪

降级策略：
- 文献交叉验证：多源一致性检查 + 溯源信任度加权
- 预测追踪：记录假设的预测，等待未来数据验证
- 人工标注：进入待审队列，人工确认
```

---

## 8. 与 MCT 的集成

```python
# 在 MCT 的决策节点中，actual_outcome 的注入流程

class CalibrationOrchestrator:
    """校准编排器。"""
    
    def __init__(self, executor: CalibrationExecutor, mct: MetaCognitiveTree):
        self.executor = executor
        self.mct = mct
    
    def calibrate(self, decision_node_id: UUID) -> None:
        """对指定决策节点执行校准。"""
        node = self.mct.get_node(decision_node_id)
        
        # 从决策节点提取假设
        hypothesis = self._extract_hypothesis(node)
        
        # 尝试形式化
        formalization = self.formalization_pipeline.translate(
            hypothesis.natural_language,
            hypothesis.domain_tags[0] if hypothesis.domain_tags else "general"
        )
        
        # 构建假设规格
        spec = HypothesisSpec(
            hypothesis_id=uuid4(),
            source_decision_node=decision_node_id,
            natural_language=hypothesis.natural_language,
            formalization=formalization,
            domain_tags=hypothesis.domain_tags,
            computable_form=self._to_computable(formalization) if formalization else None,
            validation_type=self._determine_validation_type(formalization),
            required_precision=0.1,  # 默认 10%
            max_latency_seconds=60.0,
        )
        
        # 执行校准
        result = self.executor.execute(spec)
        
        # 回填到 MCT
        self.mct.update_outcome(decision_node_id, result)
        
        # 如果验证失败，触发重评估
        if result.status == CalibrationStatus.FALSIFIED:
            self.mct.trigger_reassessment(decision_node_id, reason=f"Calibration failed: {result.diagnostics}")
```

---

## 9. 当前阶段交付优先级

| 优先级 | 后端 | 理由 |
|--------|------|------|
| P0 | MATLAB Bridge | 你有现成模型，最快打通闭环 |
| P0 | Python SciPy | 零成本，覆盖统计/优化/ML |
| P1 | Unity/PhysX | 五轴项目的空间验证需求 |
| P2 | BioSim/EconSim | 扩展领域，后续按需添加 |

---

## 10. 关键风险

| 风险 | 缓解 |
|------|------|
| 形式化转译错误 | 转译结果必须经过 CL0 语法检查 + 人工抽检 |
| 后端执行超时 | 超时后标记为 INCONCLUSIVE，不阻塞主线 |
| 多后端结果冲突 | 记录冲突，进入 CL3 质疑队列 |
| 校准成为瓶颈 | 异步执行 + 队列 + 缓存（相同假设不重复校准） |

---

## 11. 文件清单

| 文件 | 说明 |
|------|------|
| `lcortex/calibration/executor.py` | CalibrationExecutor 主类 |
| `lcortex/calibration/backends/base.py` | 后端基类 |
| `lcortex/calibration/backends/matlab.py` | MATLAB 桥接 |
| `lcortex/calibration/backends/python_scipy.py` | Python 桥接 |
| `lcortex/calibration/formalization/` | 形式化转译器 |
| `lcortex/calibration/schema.py` | HypothesisSpec / CalibrationResult |
| `tests/test_calibration_executor.py` | 测试 |

---

*校准执行器是认知智流从"思辨系统"进化为"可证伪系统"的关键基础设施。*
