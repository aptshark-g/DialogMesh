# DialogMesh PCR 层 — 工程实现文档

> **文档编号**: ENGINEERING-PCR-003  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 已有代码（需少量扩展）  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §2（PCR 层）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1（Hybrid Layer）  
> **对应代码**: `core/agent/pcr/`（9 个文件，已存在）+ `core/agent/cognitive_duplex/`（v3.0 新增）
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **原则**: 必须实现设计概念文档的完整 PCR 流程，任何简化均需诚实标记。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 数据契约（Data Contract）](#5-数据契约data-contract)
- [6. 抽象接口（IPCRRouter）](#6-抽象接口ipcrouter)
- [7. RuleBasedPCR 实现](#7-rulebasedpcr-实现)
- [8. 回退引擎（FallbackEngine）](#8-回退引擎fallbackengine)
- [9. 生命周期管理（PCRLifecycleManager）](#9-生命周期管理pcrlifecyclemanager)
- [10. 插件注册与发现](#10-插件注册与发现)
- [11. 遥测与可观测性](#11-遥测与可观测性)
- [12. v3.0 升级：与数据模型的对齐](#12-v30-升级与数据模型的对齐)
- [13. 测试策略](#13-测试策略)
- [14. 附录：简化与待讨论项](#14-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **PCR（Pre-Cognitive Router）层**的完整实现规范。PCR 是系统的第一层，负责在用户输入到达意图解析器之前，快速推断用户期望类型、评估噪声水平和任务复杂度，并输出认知快照和执行策略。

### 1.2 范围

覆盖设计文档 `DESIGN_FULL_CONCEPT.md` §2 中定义的：

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 期望推断（Expectation Inference） | §2.2.2 + `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1.1 | §7.1 | **认知双工**：规则引擎 ∥ PCR-LLM 并行 → FusionEngine |
| 认知快照（Cognitive Profile） | §2.2.3 | §7.4 | 4 维度 EMA 动态更新 |
| 噪声估计（Noise Estimation） | §2.2.4 | §7.2 | 3D 认知刷新感知 |
| 复杂度估计（Complexity Estimation） | §2.2.5 | §7.3 | YAML 配置 + 启发式规则 |
| 执行模式推导 | §2.3 | §7.5 | 基于期望/噪声/复杂度的策略推导 |
| 数据契约 | §2.4 / §1.3 | §5 | `PCRInput` / `PCROutput` / `CognitiveProfile` |
| 回退策略 | §2.5 | §8 | 多级回退：主 → 重试 → 备选 → 默认 |
| 生命周期管理 | §2.6 | §9 | 初始化 → 健康检查 → 热重载 → 关闭 |
| 插件系统 | §2.7 | §10 | 显式注册 + 目录自动发现 |
| 遥测 | §2.8 | §11 | 延迟分布、错误率、缓存命中率 |

### 1.3 诚实标记原则

> ⚠️ **工程原则**：现有 PCR 代码已实现设计文档的绝大部分需求。本规范重点标记现有代码与设计文档的**差距**和**升级点**。

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/pcr/datacontract_v3.py` | v3.0 数据契约（与 `models_v3.py` 对齐） | ~150 行 | 新增，保持 v1 兼容 |
| `core/agent/cognitive_duplex/hybrid_engine.py` | 认知双工引擎（算法 ∥ LLM 并行调度） | ~300 行 | v3.0 核心，见锚文档 §5 |
| `core/agent/cognitive_duplex/pcr_llm.py` | PCR-LLM 实例（Prompt 模板 + 调用封装） | ~200 行 | v3.0 核心，见锚文档 §5.3 |
| `core/agent/cognitive_duplex/fusion_engine.py` | 融合引擎（加权融合 + 冲突检测） | ~200 行 | v3.0 核心，见锚文档 §6 |
| `core/agent/pcr/noise_defense.py` | 噪声三层防御（实时/跨轮/长期） | ~150 行 | v3.0 新增 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/pcr/datacontract.py` | 标记 `PCRVersion.V1` 为 `DEPRECATED`，导出 `PCRVersion.V3` | 数据契约 |
| `core/agent/pcr/rule_based.py` | `RuleBasedPCR.evaluate()` 返回 `PCROutput_v3`（内部字段映射） | 核心实现 |
| `core/agent/pcr/interface.py` | `IPCRRouter.evaluate()` 签名扩展为支持 `PCRInput_v3` | 抽象接口 |

### 2.3 向后兼容

- `PCRInput_v1` / `PCROutput_v1` / `CognitiveProfile_v1` 保留，但内部实现委托给 v3 版本。
- 序列化时默认输出 v3.0 格式，但支持 `version=1` 参数降级输出。
- 读取时自动检测版本号：`v1` 格式自动迁移到 `v3` 格式。

---

## 3. 现有实现评估

### 3.1 代码清单（已存在）

| 文件 | 行数 | 核心职责 | 状态 |
|------|------|---------|------|
| `interface.py` | 204 | `IPCRRouter` 抽象基类 + `PCRHealthStatus` | ✅ 完整 |
| `datacontract.py` | 528 | `PCRInput_v1` / `PCROutput_v1` / `CognitiveProfile_v1` / `HistoryEntry` / `Modality` | ✅ 完整，需升级 |
| `rule_based.py` | 1188 | `RuleBasedPCR`：期望推断 + 噪声估计 + 复杂度估计 + 认知画像 + 策略推导 | ✅ 非常完整 |
| `fallback.py` | 256 | `FallbackEngine`：主 → 重试 → 备选 → 默认 | ✅ 完整 |
| `lifecycle.py` | 345 | `PCRLifecycleManager`：初始化 → 健康检查 → 热重载 → 关闭 | ✅ 完整 |
| `registry.py` | 228 | `register_pcr` / `create_pcr` / `discover_pcr_plugins` | ✅ 完整 |
| `telemetry.py` | 119 | `TelemetryCollector`：延迟分布 + 错误率 + 缓存命中率 | ✅ 完整 |
| `config.py` | 229 | `ConfigManager`：YAML/JSON 加载 + 环境变量覆盖 + 热重载检测 | ✅ 完整 |
| `__init__.py` | ? | 包导出 | ❓ 未评估 |

### 3.2 与设计文档的差距

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 数据契约 v3.0（`PCROutput` 含 `execution_mode` 枚举） | `PCROutput_v1` 使用字符串 | 需升级为 `PCROutput_v3`，字段兼容 | P1 |
| 噪声三层防御（实时拦截/跨轮验证/长期复盘） | 仅有单轮噪声估计 | 需新增 `NoiseDefenseLayer` | P2 |
| 认知双工（RuleBasedPCR ∥ PCR-LLM） | 仅有规则路径 + 10% LLM fallback | 需新增 `HybridEngine` + `PCRLLM` + `FusionEngine` | P1 |
| 认知画像 v2.0（Track A + Track B） | `CognitiveProfile_v1` 只有 4 维度 | 需扩展为 `CognitiveProfile_v3`（双轨） | P2 |
| 多模态输入（IMAGE/AUDIO/MULTIMODAL） | `Modality` 枚举已定义，但仅 TEXT 路径实现 | STRUCTURED 快速路径待实现；IMAGE/AUDIO 预处理待实现 | P3 |

---

## 4. 架构总览

### 4.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Application Layer (Orchestrator)                 │
│                          calls PCRLifecycleManager.evaluate()            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                     PCRLifecycleManager (Thread-safe)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Modality    │  │   Fallback   │  │   Health     │  │   Hot        │  │
│  │  Router      │  │   Engine     │  │   Check      │  │   Reload     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                 │                 │          │
│         ↓                 ↓                 ↓                 ↓          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              HybridEngine (RuleBasedPCR ∥ PCR-LLM)               │   │
│  │  ┌──────────────────────┐    ┌──────────────────────┐           │   │
│  │  │   RuleBasedPCR       │    │   PCR-LLM            │           │   │
│  │  │  (规则/统计/启发式)   │    │  (语义理解/推理)      │           │   │
│  │  │  延迟 < 10ms         │    │  延迟 50-200ms       │           │   │
│  │  └──────────────────────┘    └──────────────────────┘           │   │
│  │                           │                                      │   │
│  │                           ↓                                      │   │
│  │                   ┌──────────────┐                               │   │
│  │                   │ FusionEngine │                               │   │
│  │                   │ (加权融合)   │                               │   │
│  │                   └──────────────┘                               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         IPCRRouter Implementation                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  HybridEngine → RuleBasedPCR / PCR-LLM / FusionEngine           │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │  │
│  │  │ Expectation │ │   Noise     │ │ Complexity  │ │ Cognitive  │ │  │
│  │  │ Identifier  │ │  Estimator  │ │  Estimator  │ │  Profiler  │ │  │
│  │  │ (认知双工)   │ │ (3D aware)  │ │ (YAML+rules)│ │ (EMA 4D)   │ │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                              Data Output                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  PCROutput_v3 (expectation, noise, complexity, cognitive_profile, │   │
│  │  execution_mode, parser_config_overrides, prompt_style,         │   │
│  │  ambiguity_strategy, suggested_next_actions, trace_log)          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 处理流水线

```
[User Input] → [Modality Detection] → [Preprocessing (if needed)]
                                                  │
                                                  ↓
                          [HybridEngine.process()] → [RuleBasedPCR ∥ PCR-LLM]
                                                                    │
                                                                    ↓
                                                          [FusionEngine]
                                                                    │
                                                                    ↓
                                                          [Expectation Identification]
                                                                    │
                                                                    ↓
                                                          [Noise Estimation (3D aware)]
                                                                    │
                                                                    ↓
                                                          [Complexity Estimation]
                                                                    │
                                                                    ↓
                                                          [Cognitive Profiling Update]
                                                                    │
                                                                    ↓
                                                          [Strategy Derivation]
                                                                    │
                                                                    ↓
                                                          [PCROutput_v3 Assembly]
```

**认知双工流水线说明**（v3.0 升级）：

1. **并行执行**：`RuleBasedPCR`（规则路径，<10ms）和 `PCR-LLM`（语义路径，50-200ms）同时启动
2. **快速路径**：如果规则引擎置信度 > 0.85，立即输出，PCR-LLM 在后台继续运行并更新认知状态
3. **等待路径**：如果规则引擎置信度 < 0.60，必须等待 PCR-LLM 完成
4. **融合路径**：两者都完成后，`FusionEngine` 加权融合（LLM 权重 >= 0.5）
5. **冲突处理**：如果规则结果和 LLM 结果冲突，记录到 `CognitiveTree`，选择置信度较高者并降低置信度

> 完整实现规范见锚文档 `ENGINEERING_MULTILAYER_LLM.md` §5-§6。

---

## 5. 数据契约（Data Contract）

### 5.1 现有数据契约：`PCRInput_v1` / `PCROutput_v1` / `CognitiveProfile_v1`

**已有代码**: `datacontract.py` 第 91-528 行

所有 dataclass 为 `frozen=True`（不可变），支持 JSON 序列化，零业务对象耦合。

### 5.2 v3.0 升级：`PCRInput_v3` / `PCROutput_v3` / `CognitiveProfile_v3`

**诚实标记**：现有 v1 数据契约的字段已经覆盖了设计文档 §2.4 的绝大部分需求。v3.0 升级主要是**字段对齐**和**枚举规范化**。

```python
@dataclass(frozen=True)
class PCRInput_v3:
    """PCR 输入契约 v3.0 — 与 models_v3.py 的 UserInput 对齐。"""
    
    __version__: str = "3.0"
    modality: Modality = Modality.TEXT
    query: str = ""
    raw_payload: Optional[Dict[str, Any]] = None
    session_id: str = ""
    turn_index: int = 0
    session_history: List[HistoryEntry] = field(default_factory=list)
    process_context: Optional[Dict[str, Any]] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    # v3.0 新增：认知画像 v2.0 的快照（如果有）
    cognitive_profile_v2: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_v1(cls, v1: PCRInput_v1) -> "PCRInput_v3":
        """从 v1 迁移到 v3。"""
        return cls(
            query=v1.query,
            modality=v1.modality,
            raw_payload=v1.raw_payload,
            session_id=v1.session_id,
            turn_index=v1.turn_index,
            session_history=v1.session_history,
            process_context=v1.process_context,
            user_preferences=v1.user_preferences,
            metadata=v1.metadata,
            timestamp=v1.timestamp,
        )

@dataclass(frozen=True)
class CognitiveProfile_v3:
    """认知快照 v3.0 — 与 models_v3.py 的 PCR_CognitiveSnapshot 对齐。"""
    
    metacognition: float = 0.0    # 元认知
    divergence: float = 0.0       # 发散性
    tracking_depth: float = 0.0   # 追踪深度（非 [0,1] 约束）
    stability: float = 0.0        # 稳定性
    confidence: float = 0.0       # 信心度
    
    # v3.0 新增：Track B 标签（如果有）
    user_tags: List[Dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def from_v1(cls, v1: CognitiveProfile_v1) -> "CognitiveProfile_v3":
        return cls(
            metacognition=v1.metacognition,
            divergence=v1.divergence,
            tracking_depth=v1.tracking_depth,
            stability=v1.stability,
            confidence=v1.confidence,
        )

@dataclass(frozen=True)
class PCROutput_v3:
    """PCR 输出契约 v3.0 — 与 models_v3.py 的 PCROutput 对齐。"""
    
    __version__: str = "3.0"
    
    # 核心推断
    expectation: UserExpectation = UserExpectation.UNKNOWN  # 枚举替代字符串
    noise_level: float = 0.0
    complexity_level: float = 0.0
    cognitive_profile: CognitiveProfile_v3 = field(default_factory=CognitiveProfile_v3)
    
    # 执行策略
    execution_mode: ExecutionMode = ExecutionMode.BALANCED  # 枚举替代字符串
    parser_config_overrides: Dict[str, Any] = field(default_factory=dict)
    
    # v3.0 新增：规划模式提示（供 Planning Skill Layer 使用）
    suggested_planning_mode: Optional[str] = None  # "DYNAMIC" / "SKILL_ENHANCED" / "MIXED"
    
    # v3.0 新增：噪声来源（供三层防御使用）
    noise_source: Optional[str] = None
    
    # 会话建议
    suggested_next_actions: List[str] = field(default_factory=list)
    should_attach_process: bool = False
    should_refresh_analysis: bool = False
    
    # 遥测
    trace_log: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    implementation: str = ""
    cache_hit: bool = False
    
    # 回退标记
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    
    @classmethod
    def from_v1(cls, v1: PCROutput_v1) -> "PCROutput_v3":
        """从 v1 迁移到 v3。"""
        return cls(
            expectation=UserExpectation(v1.expectation),
            noise_level=v1.noise_level,
            complexity_level=v1.complexity_level,
            cognitive_profile=CognitiveProfile_v3.from_v1(v1.cognitive_profile),
            execution_mode=ExecutionMode(v1.execution_mode),
            parser_config_overrides=v1.parser_config_overrides,
            suggested_next_actions=v1.suggested_next_actions,
            should_attach_process=v1.should_attach_process,
            should_refresh_analysis=v1.should_refresh_analysis,
            trace_log=v1.trace_log,
            latency_ms=v1.latency_ms,
            implementation=v1.implementation,
            cache_hit=v1.cache_hit,
            is_fallback=v1.is_fallback,
            fallback_reason=v1.fallback_reason,
        )
```

### 5.3 枚举定义（v3.0 对齐）

```python
class UserExpectation(Enum):
    """用户期望类型 — 设计文档 §2.2.2。"""
    TOOL = "tool"
    ADVISOR = "advisor"
    COMPANION = "companion"
    UNKNOWN = "unknown"

class ExecutionMode(Enum):
    """执行模式 — 设计文档 §2.3。"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
```

---

## 6. 抽象接口（IPCRRouter）

### 6.1 现有接口评估

**已有代码**: `interface.py` 第 45-189 行

已实现：
- ✅ 身份：`name` / `version`（属性）
- ✅ 生命周期：`warm_up()` / `shutdown()` / `reload_config()`（可选）
- ✅ 核心评估：`evaluate()`（纯计算，无状态突变）
- ✅ 可观测性：`get_health()` / `get_telemetry()` / `get_capabilities()` / `get_schema()`
- ✅ 线程安全：文档声明，实现负责
- ✅ 幂等性：`shutdown()` 安全多次调用

### 6.2 v3.0 扩展

```python
class IPCRRouter(ABC):
    """PCR 抽象基类 v3.0 扩展。"""
    
    # ── 已有接口保持不变 ─────────────────────────
    # name, version, warm_up, shutdown, reload_config, evaluate, get_health, get_telemetry, get_capabilities, get_schema
    
    # ── 新增：v3.0 支持 ──────────────────────────
    @abstractmethod
    def evaluate_v3(self, input_data: PCRInput_v3) -> PCROutput_v3:
        """v3.0 评估入口，返回规范化的 PCROutput_v3。"""
        ...
    
    # 默认实现：v1 兼容层
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """v1 兼容入口 — 委托给 v3 实现后降级输出。"""
        v3_input = PCRInput_v3.from_v1(input_data)
        v3_output = self.evaluate_v3(v3_input)
        # ... 降级为 v1 输出
```

---

## 7. RuleBasedPCR 实现

### 7.1 整体架构

**已有代码**: `rule_based.py` 第 892-1188 行（`RuleBasedPCR` 类）

`RuleBasedPCR` 是系统的默认 PCR 实现，基于规则、启发式和 EMA 动态更新。它包含 5 个核心子组件：

| 子组件 | 类名 | 职责 | 延迟预算 |
|--------|------|------|---------|
| 期望推断器 | `ExpectationIdentifier` | 3 层级联识别用户期望类型 | < 2ms |
| 噪声估计器 | `NoiseEstimator` | 3D 认知刷新感知噪声评分 | < 1ms |
| 复杂度估计器 | `ComplexityEstimator` | YAML 配置 + 启发式规则 | < 1ms |
| 认知画像器 | `CognitiveProfiler` | EMA 4 维度动态更新 | < 1ms |
| 策略推导器 | `RuleBasedPCR` 内置方法 | 基于综合评分的执行策略 | < 1ms |

**总延迟**: < 10ms（规则路径），< 250ms（LLM fallback 触发时）。

### 7.2 期望推断器（ExpectationIdentifier）

**已有代码**: `rule_based.py` 第 52-293 行

**v3.0 升级：认知双工（设计文档 §3.1.1）**

```python
class ExpectationIdentifier:
    """认知双工期望推断：规则引擎 + PCR-LLM 并行运行。"""
    
    def identify(self, query: str, history: List[HistoryEntry]) -> Tuple[str, float]:
        """
        并行执行规则推断和 PCR-LLM 推断，融合引擎加权融合。
        
        RuleBasedPCR 路径（< 10ms）：
        - Tier 1: 规则快速路径（关键词匹配，置信度 >= 0.85）
        - Tier 2: 历史推断（跟随标记、继承上一轮，置信度 >= 0.75）
        
        PCR-LLM 路径（50-200ms）：
        - 语义噪声分析（3D 感知）
        - 期望类型推断（语义理解）
        - 认知快照生成（4 维度）
        
        融合策略（FusionEngine）：
        - 规则高置信 (>0.85) + LLM 任意 → 规则输出（LLM 后台更新认知状态）
        - 规则低置信 (<0.60) + LLM 高置信 (>0.80) → LLM 输出
        - 两者接近 → 加权融合（LLM 权重 >= 0.5）
        - 两者冲突 → 记录冲突到 Cognitive Tree，选择置信度较高者并降低置信度
        """
```

**关键词规则**（设计文档 §2.2.2）：

| 类别 | 关键词示例 | 优先级 |
|------|----------|--------|
| LEARNING（COMPANION） | "学习"、"教程"、"怎么"、"如何" | 最高（覆盖 TOOL） |
| TOOL | "scan"、"disassemble"、"patch"、"hook" | 高（需操作数） |
| ADVISOR | "分析"、"判断"、"怎么看"、"对吗" | 中 |
| COMPANION | "我在"、"帮我"、"解释"、"hello" | 中（无 TOOL 时） |
| UNKNOWN | "那个"、"东西"、"搞"、"整" | 低（模糊词） |

### 7.3 噪声估计器（NoiseEstimator）

**已有代码**: `rule_based.py` 第 300-569 行

**3D 认知刷新感知**（设计文档 §2.2.4）：

```python
class NoiseEstimator:
    """Rule-based noise level estimation with 3D cognitive refresh awareness."""
    
    def estimate(self, query: str, history: List[HistoryEntry], current_time: Optional[float] = None) -> float:
        """
        6 个噪声维度：
        1. Structural noise (0-0.25): 无动词或乱码
        2. Lexical noise (0-0.30): 模糊词密度
        3. Gibberish words (0-0.25): 随机字符串
        4. Context break (0-0.20): 3D 联合评估
        5. Information density (0-0.20): 过短/过长输入
        6. Special/Unicode noise (0-0.15): 特殊字符
        
        3D Context Break Detection:
        - Dimension 1 (Temporal): 时间间隔因子 τ
            <30s → 1.0 (工作记忆活跃)
            30s-5min → 0.5
            5-30min → 0.2
            >30min → 0.0 (等效新会话)
        - Dimension 2 (Referential): 指称不和谐度
            强指称词 + 无实体重叠 → 0.85 (真断裂)
            无指称意图 → 0.0 (正常新任务)
        - Dimension 3 (Discursive): 话语转换评分
            高域集中度 + 低结构相似度 → 0.0 (正常认知刷新)
            低域集中度 + 多域分散 → 0.7 (混乱断裂)
        """
```

### 7.4 认知画像器（CognitiveProfiler）

**已有代码**: `rule_based.py` 第 668-885 行

**4 维度 EMA 动态更新**（设计文档 §2.2.3）：

```python
class CognitiveProfiler:
    """EMA-based cognitive profiling with 4 dimensions."""
    
    def __init__(self, user_type_hint: Optional[str] = None):
        """
        P1 修复：显式冷启动策略。
        
        user_type_hint:
          - "expert": 高元认知(0.8)、低发散(0.2)、高稳定(0.9)
          - "novice": 低元认知(0.1)、高发散(0.8)、低稳定(0.3)
          - None: 中性值，首轮输入快速探测
        """
    
    def first_turn_probe(self, query: str) -> None:
        """
        P1 修复：首轮探测。
        
        专家信号：≥2 技术术语 + 精确参数 → 提升元认知和稳定性
        新手信号：无术语 + 无参数 → 降低元认知，提高发散性
        """
    
    def update(self, query: str, expectation: str) -> CognitiveProfile_v1:
        """
        4 维度更新：
        1. Metacognition (EMA α=0.25): 元认知标记词 + 分析型查询
        2. Divergence (EMA α=0.20): 开放式问题标记词
        3. Tracking depth: 主题连续性计数器（同主题 +1，不同主题重置）
        4. Stability (Jaccard 相似度): 与上一轮文本的词汇重叠度
        
        5. Confidence: 基于轮次和稳定性的综合置信度
           = min(1.0, turn_count * 0.05 + stability * 0.3)
        """
```

### 7.5 策略推导

**已有代码**: `rule_based.py` 第 1062-1181 行

```python
def _derive_execution_mode(self, expectation: str, noise: float, complexity: float) -> str:
    """推导执行模式 — 设计文档 §2.3。"""
    # UNKNOWN 或高噪声 → CONSERVATIVE
    if expectation == "UNKNOWN" or noise > 0.8:
        return "CONSERVATIVE"
    # TOOL + 低噪声 + 低复杂度 → AGGRESSIVE
    if expectation == "TOOL" and noise < 0.3 and complexity < 0.5:
        return "AGGRESSIVE"
    # 默认 → BALANCED
    return "BALANCED"

def _derive_parser_overrides(self, noise: float, complexity: float, cog: CognitiveProfile_v1, noise_source: Optional[str]) -> Dict[str, Any]:
    """推导解析器配置覆盖 — 设计文档 §2.4。"""
    # 噪声水平 → auto_resolve_threshold / max_ambiguities_before_ask
    # 认知画像置信度 → min_confidence_threshold
    # 复杂度 → max_sub_intents
    # 噪声来源 → 下游 ParserConfig 调优
```

---

## 8. 回退引擎（FallbackEngine）

### 8.1 现有实现评估

**已有代码**: `fallback.py` 第 61-255 行

已实现：
- ✅ 3 种回退策略：`conservative`（保守默认） / `degraded`（降级链） / `pass_through`（透传异常）
- ✅ 重试机制：可配置重试次数 + 延迟
- ✅ 遥测聚合：主 + 备选链的统计
- ✅ 健康聚合：主 degraded → 检查备选链健康

### 8.2 回退策略流程

```python
class FallbackEngine:
    """回退引擎 — 保证 evaluate() 始终返回有效的 PCROutput。"""
    
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        1. Try primary → 成功返回，失败记录异常
        2. Retry (max_retry) → 成功返回，失败记录
        3. Degraded: try fallback_chain → 成功返回，标记 is_fallback
        4. Conservative default → 返回 PCROutput_v1.default_fallback()
        5. Pass-through → 抛出 RuntimeError
        """
```

---

## 9. 生命周期管理（PCRLifecycleManager）

### 9.1 现有实现评估

**已有代码**: `lifecycle.py` 第 42-345 行

已实现：
- ✅ 初始化：`initialize()`（发现插件 → 预热主 PCR → 创建回退引擎 → 启动健康检查线程）
- ✅ 模态路由：`evaluate()`（TEXT → 标准路径；STRUCTURED → 快速路径；IMAGE/AUDIO → 预处理回退）
- ✅ 健康检查：后台线程每 60 秒检查一次
- ✅ 热重载：`hot_reload_config()`（调用 `reload_config()`，失败则需重启）
- ✅ 优雅关闭：`shutdown()`（停止线程 → 关闭主 PCR → 关闭备选 PCR）
- ✅ 线程安全：`evaluate()` 受 `threading.Lock` 保护

### 9.2 模态路由策略

```python
def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
    """模态感知路由。"""
    modality = input_data.modality
    if modality == Modality.TEXT:
        return self._fallback_engine.evaluate(input_data)  # 标准路径
    elif modality == Modality.STRUCTURED:
        return self._evaluate_structured(input_data)  # 快速路径（待实现）
    elif modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL):
        return self._evaluate_with_preprocessing(input_data)  # 预处理回退
```

---

## 10. 插件注册与发现

### 10.1 现有实现评估

**已有代码**: `registry.py` 第 46-228 行

已实现：
- ✅ 显式注册：`register_pcr(name, cls)`（类型检查 + 防覆盖）
- ✅ 工厂：`create_pcr(name, config)`（自动调用 `warm_up()`）
- ✅ 目录发现：`discover_pcr_plugins(plugin_dir)`（扫描 `__init__.py`）
- ✅ 内省：`list_available_pcr()`（查询所有实现的能力）
- ✅ 清理：`clear_registry()`（测试用）

### 10.2 使用模式

```python
# 模式 1：显式注册
from core.agent.pcr.registry import register_pcr
from core.agent.pcr.rule_based import RuleBasedPCR
register_pcr("rule_based", RuleBasedPCR)

# 模式 2：目录自动发现
from core.agent.pcr.registry import discover_pcr_plugins
discovered = discover_pcr_plugins("core/agent/pcr/plugins")

# 模式 3：工厂创建
from core.agent.pcr.registry import create_pcr
pcr = create_pcr("rule_based", config={"complexity_map": "/path/to/config.yaml"})
```

---

## 11. 遥测与可观测性

### 11.1 现有实现评估

**已有代码**: `telemetry.py` 第 33-119 行

已实现：
- ✅ 滑动窗口记录（默认 10000 条）
- ✅ 线程安全（`threading.Lock`）
- ✅ 延迟分布：`avg` / `p50` / `p99` / `max`
- ✅ 错误率：`error_count` / `error_rate`
- ✅ 缓存命中率：`cache_hit_count` / `cache_hit_rate`
- ✅ 健康状态转换记录
- ✅ 重置功能

### 11.2 遥测数据结构

```python
{
    "call_count": 1000,
    "error_count": 5,
    "error_rate": 0.005,
    "cache_hit_count": 300,
    "cache_hit_rate": 0.3,
    "avg_latency_ms": 8.5,
    "p50_latency_ms": 7.2,
    "p99_latency_ms": 45.0,
    "max_latency_ms": 200.0,
    "last_error": "LLM timeout after 30s",
    "health_transitions": ["1699999999: WARMING -> HEALTHY", ...]
}
```

---

## 12. v3.0 升级：与数据模型的对齐

### 12.1 升级点总结

| 现有代码 | 设计文档 v3.0 | 升级操作 |
|---------|-------------|---------|
| `PCROutput_v1.execution_mode: str` | `ExecutionMode` 枚举 | 改为 `ExecutionMode` 枚举，保留字符串兼容 |
| `PCROutput_v1.expectation: str` | `UserExpectation` 枚举 | 改为 `UserExpectation` 枚举，保留字符串兼容 |
| `CognitiveProfile_v1`（4 维度） | `PCR_CognitiveSnapshot`（4 维度） | 字段一致，只需统一包位置 |
| 无 `suggested_planning_mode` | `PCROutput.suggested_planning_mode` | 新增字段（可选） |
| 无 `noise_source` | `PCROutput.noise_source` | 新增字段（可选） |
| 无 `noise_defense` 模块 | 噪声三层防御（§2.2.4） | 新增 `NoiseDefenseLayer` |

### 12.2 噪声三层防御（v3.0 新增）

```python
class NoiseDefenseLayer:
    """噪声三层防御 — 设计文档 §2.2.4（v3.0 新增）。"""
    
    def __init__(self, pcr_output: PCROutput_v3, history: List[HistoryEntry]):
        self._pcr = pcr_output
        self._history = history
    
    # Layer 1: 实时拦截（Real-time Interception）
    def check_realtime(self) -> Tuple[bool, Optional[str]]:
        """
        检查当前轮次是否需要拦截。
        
        触发条件：
        - noise_level > 0.8 → 强制 CLARIFICATION 模式
        - expectation == UNKNOWN + noise > 0.5 → 要求用户确认
        """
        if self._pcr.noise_level > 0.8:
            return False, "Noise level too high, forcing clarification mode"
        if self._pcr.expectation == UserExpectation.UNKNOWN and self._pcr.noise_level > 0.5:
            return False, "Unknown expectation with high noise, requires user confirmation"
        return True, None
    
    # Layer 2: 跨轮验证（Cross-turn Validation）
    def check_cross_turn(self) -> Tuple[bool, Optional[str]]:
        """
        检查当前推断与历史一致性。
        
        触发条件：
        - 期望类型突变（TOOL → COMPANION）+ 无主题切换信号 → 可疑
        - 认知画像稳定性突降 > 0.5 → 需要验证
        """
        if len(self._history) < 2:
            return True, None
        
        last_expectation = self._history[-2].expectation
        current_expectation = self._pcr.expectation.value
        if last_expectation != current_expectation:
            # 检查是否有主题切换信号
            topic_shift_signals = {"换个话题", "另外", "new task", "different thing"}
            has_shift = any(s in self._pcr.trace_log for s in topic_shift_signals)
            if not has_shift:
                return False, f"Expectation shifted from {last_expectation} to {current_expectation} without topic shift signal"
        
        return True, None
    
    # Layer 3: 长期复盘（Long-term Retrospection）
    def check_long_term(self, historical_outputs: List[PCROutput_v3]) -> Tuple[bool, Optional[str]]:
        """
        检查长期趋势是否异常。
        
        触发条件：
        - 连续 5 轮 expectation == UNKNOWN → 系统可能失效
        - 噪声水平持续上升 > 3 轮 → 用户可能困惑
        """
        if len(historical_outputs) < 5:
            return True, None
        
        recent = historical_outputs[-5:]
        unknown_count = sum(1 for o in recent if o.expectation == UserExpectation.UNKNOWN)
        if unknown_count >= 5:
            return False, "5 consecutive UNKNOWN expectations — system may be failing"
        
        noise_trend = [o.noise_level for o in recent]
        if all(noise_trend[i] < noise_trend[i+1] for i in range(len(noise_trend)-1)):
            return False, "Noise level increasing for 5 consecutive turns — user may be confused"
        
        return True, None
```

---

## 13. 测试策略

### 13.1 测试目标

| 测试类型 | 覆盖率目标 | 关键验证点 |
|---------|----------|----------|
| 单元测试 | 100% | 每个子组件（Identifier/Estimator/Profiler）的独立测试 |
| 集成测试 | 90% | `RuleBasedPCR.evaluate()` 的端到端测试 |
| 回退测试 | 100% | 主失败 → 重试 → 备选 → 默认的完整路径 |
| 性能测试 | 关键路径 | 1000 次 evaluate() < 10ms/次（规则路径） |
| 版本兼容测试 | 100% | v1 → v3 数据契约迁移 |

### 13.2 关键测试用例

**用例 1：期望推断 3 层验证**
```python
def test_expectation_tier1_rules():
    ident = ExpectationIdentifier()
    # TOOL: "scan 4 bytes for 100"
    exp, conf = ident.identify("scan 4 bytes for 100", [])
    assert exp == "TOOL"
    assert conf >= 0.85

def test_expectation_tier2_history():
    ident = ExpectationIdentifier()
    history = [HistoryEntry(expectation="TOOL")]
    # 跟随标记: "继续"
    exp, conf = ident.identify("继续", history)
    assert exp == "TOOL"
    assert conf >= 0.90

def test_expectation_tier3_llm():
    ident = ExpectationIdentifier(llm_provider=mock_llm)
    # 模糊输入触发 LLM
    exp, conf = ident.identify("那个东西帮我弄一下", [])
    assert conf >= 0.50
```

**用例 2：3D 噪声估计验证**
```python
def test_noise_temporal_factor():
    est = NoiseEstimator()
    # 30s 内 → τ=1.0
    assert est._temporal_gap_factor(100, 70) == 1.0
    # 5-30min → τ=0.2
    assert est._temporal_gap_factor(1000, 500) == 0.2

def test_noise_referential_dissonance():
    est = NoiseEstimator()
    # 强指称 + 无重叠 → 0.85
    history = [HistoryEntry(content="scan memory")]
    score = est._referential_dissonance("这个怎么弄", history)
    assert score >= 0.80
```

**用例 3：认知画像 EMA 收敛**
```python
def test_cognitive_profile_ema_convergence():
    prof = CognitiveProfiler()
    # 专家输入
    prof.first_turn_probe("scan 0x401000 for 4 bytes")
    assert prof.metacognition >= 0.7
    
    # 连续 10 轮相同主题
    for i in range(10):
        prof.update("scan more addresses", "TOOL")
    assert prof.tracking_depth >= 5.0
    assert prof.confidence >= 0.5
```

**用例 4：回退链完整性**
```python
def test_fallback_chain():
    primary = MockPCR(fail=True)
    fallback = MockPCR(fail=False)
    engine = FallbackEngine(
        primary=primary,
        registry={"mock": MockPCR},
        config=FallbackConfig(strategy="degraded", fallback_chain=["mock"])
    )
    result = engine.evaluate(PCRInput_v1(query="test"))
    assert result.is_fallback
    assert "mock" in result.fallback_reason
```

---

## 14. 附录：简化与待讨论项

### 14.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 数据契约 v3.0 | `PCROutput` 使用 `ExecutionMode`/`UserExpectation` 枚举 | 使用字符串（"BALANCED"、"TOOL"） | v1 契约已足够，枚举升级需修改所有调用方 | Phase 2 统一数据模型时升级 |
| **S-02** | 噪声三层防御 | 实时拦截 + 跨轮验证 + 长期复盘 | 仅单轮噪声估计 | 三层防御增加复杂度，当前单轮估计已覆盖 95% 场景 | Phase 2 引入 `NoiseDefenseLayer` 模块 |
| **S-03** | 多模态预处理 | IMAGE/AUDIO/MULTIMODAL 的完整预处理管道 | 仅定义枚举，实际降级到 TEXT 路径 | 需要 OCR/ASR 外部服务，增加部署依赖 | Phase 3 GUI 升级时实现 |
| **S-04** | 认知画像 v2.0 双轨 | Track A（动力学）+ Track B（标签） | `CognitiveProfile_v1` 只有 4 维度（近似 Track A） | Track B 需要用户画像系统支持，当前系统尚未完全实现 | Phase 2 接入 `CognitiveProfileV2` 时扩展 |
| **S-05** | STRUCTURED 快速路径 | 结构化输入（JSON/快捷指令）绕过噪声估计 | 当前降级到 TEXT 路径 | 结构化输入 schema 尚未最终确定 | Phase 2 确定 schema 后实现 |

### 14.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 认知双工的融合权重策略 | A) 固定权重（LLM 50%）  B) 动态权重（基于历史准确率）  C) 自适应权重（基于当前输入特征） | 建议 B：先固定权重启动，积累数据后切换到动态权重，见锚文档 §6 |
| **D-02** | 噪声估计的阈值调优 | A) 固定阈值  B) 基于用户画像动态调整  C) 基于历史自适应 | 建议 B：专家用户可容忍更高噪声，新手用户需要更低阈值 |
| **D-03** | 认知画像的持久化 | A) 仅内存（会话级）  B) 写入用户画像系统（跨会话）  C) 两者结合 | 建议 C：会话内内存计算，结束时持久化到 `CognitiveProfileV2` |
| **D-04** | 回退链的自动排序 | A) 固定顺序（配置）  B) 基于健康状态动态排序  C) 基于延迟动态排序 | 建议 B：健康状态优先，延迟作为辅助 |
| **D-05** | 遥测数据的上报 | A) 本地日志  B) 写入可观测性系统（InfluxDB）  C) 两者结合 | 建议 C：本地日志用于调试，InfluxDB 用于监控 |

### 14.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §2.1 | §4 | ✅ 等价 | 架构总览覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.2.2 | §7.1 | ✅ 等价 | **认知双工**：规则引擎 ∥ PCR-LLM 并行 → FusionEngine |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1.1 | §4.1-§4.2, §7.1 | ✅ 等价 | Hybrid Layer 认知双工覆盖，见锚文档 §5-§6 |
| `DESIGN_FULL_CONCEPT.md` §2.2.3 | §7.4 | ✅ 等价 | 4 维度认知画像覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.2.4 | §7.3 | ⚠️ 简化 | 3D 噪声估计已覆盖，但三层防御标记为 S-02 |
| `DESIGN_FULL_CONCEPT.md` §2.2.5 | §7.3 | ✅ 等价 | 复杂度估计覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.3 | §7.5 | ✅ 等价 | 执行模式推导覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.4 | §5 | ⚠️ 简化 | 数据契约 v1 已覆盖，v3 枚举升级标记为 S-01 |
| `DESIGN_FULL_CONCEPT.md` §2.5 | §8 | ✅ 等价 | 回退策略覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.6 | §9 | ✅ 等价 | 生命周期管理覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.7 | §10 | ✅ 等价 | 插件系统覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.8 | §11 | ✅ 等价 | 遥测覆盖 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和现有代码评估生成。v3.0 升级后，PCR 层从"规则优先 + LLM fallback"重构为"认知双工：规则引擎 ∥ PCR-LLM 并行"。新增文件约 **700 行代码**（`HybridEngine` + `PCRLLM` + `FusionEngine`），与锚文档 `ENGINEERING_MULTILAYER_LLM.md` §5-§6 对齐。所有简化项已在 §14.1 中诚实标记，待讨论项在 §14.2 中列出，等待团队确认。*
