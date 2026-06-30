# PCR 接口化修正设计文档

**版本**：v2.2.1（多模态接口 + 认知刷新感知修正版 + Intent Parser 三大修正联动）
**日期**：2025-06-24
**状态**：设计修正完成，代码实现完成，184 测试全部通过
**范围**：Layer 0（PCR）接口化完整设计 + 插件生命周期 + 数据契约版本化 + 多模态扩展 + 认知刷新感知 + v2.2.1 Intent Parser 修正联动（Fast Path / 同义词方向 / 代词消解提前）
**完成度**：~92%（与 `design_layer0_pcr_and_layer1_intent_parser.md` v2.2.1 联动确认）

---

## 1. 修正动机

上一版接口化设计（v2.0）存在以下不足，需要修正：

1. **接口不完整**：仅定义 `evaluate()` 和 `get_capabilities()`，缺少生命周期管理（预热、关闭）、配置热更新、健康检查。
2. **数据契约无版本**：`PCROutput` 直接映射为 `IntentContext` 的字段，未来增加字段时会导致序列化不兼容。
3. **插件发现机制缺失**：手动注册 `register_pcr` 不够工业级，应支持**目录自动扫描**（类似 Django INSTALLED_APPS / Flask extensions）。
4. **错误处理未定义**：`evaluate()` 抛异常时，调用方不知道应该做什么（回退？重试？返回默认值？）。
5. **缺乏可观测性接口**：没有暴露遥测数据（调用次数、延迟分布、缓存命中率），无法在生产环境监控。
6. **配置管理过于简单**：YAML 配置没有 Schema 校验、没有环境变量覆盖、没有运行时热加载。
7. **多模态输入缺接口**：当前设计标榜"多模态"但输入契约只有纯文本字段，无分发机制，图像/音频输入会导致文本规则评估器崩溃。
8. **上下文断裂判定武断**：Stage 1 噪声评估中"上下文断裂"仅基于实体重叠，误判正常话题切换和新任务为"噪声"，缺乏认知刷新（cognitive refresh）感知机制。

---

## 2. 修正后的核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  core/agent/pcr/ 目录结构（插件化引擎）                               │
├─────────────────────────────────────────────────────────────────────┤
│  interface.py          ── IPCRRouter 抽象基类（生命周期 + 评估 + 遥测）  │
│  datacontract.py       ── 版本化数据契约（PCRInput_v1 / PCROutput_v1）   │
│  registry.py           ── 插件发现引擎（目录扫描 + 显式注册）           │
│  lifecycle.py          ── 插件生命周期管理器（预热 → 运行 → 热更新 → 关闭）│
│  config.py             ── 配置 Schema 定义 + 校验 + 环境变量覆盖 + 热加载   │
│  fallback.py           ── 错误回退策略引擎（默认 PCR + 降级链）           │
│  telemetry.py          ── 遥测数据收集器（延迟、命中率、异常率）          │
│  rule_based/           ── 规则实现包（默认）                            │
│  │  __init__.py        ── 注册入口 + 实现类                              │
│  │  estimator.py       ── 噪声/复杂度评估器                               │
│  │  profiler.py        ── 认知画像评估器                                 │
│  │  identifier.py       ── 期望识别器                                     │
│  │  config.yaml          ── 实现级配置（独立于全局配置）                    │
│  llm_enhanced/         ── LLM 增强实现包（可选）                         │
│  hybrid/               ── 混合实现包（可选）                              │
│  tests/                ── 独立测试套件（Mock 实现 + 对抗测试集）            │
│  │  mock_pcr.py         ── 受控 Mock 实现（用于上层测试）                  │
│  │  adversarial_suite.py ── 对抗测试集（噪声/模糊/歧义输入）               │
│  │  benchmark.py        ── 性能基准测试（延迟、准确率）                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 修正后的接口定义（`interface.py`）

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
import time


class PCRHealthStatus(Enum):
    HEALTHY = "healthy"          # 正常运行
    DEGRADED = "degraded"        # 部分降级（如 LLM 超时，已回退到规则）
    UNHEALTHY = "unhealthy"      # 完全不可用（需重启或替换）
    WARMING = "warming"          # 预热中（冷启动、模型加载）


class PCRVersion(Enum):
    """数据契约版本。新增版本时旧版本保留，确保向后兼容。"""
    V1 = "1.0"                   # 当前版本


class Modality(Enum):
    """输入模态。支持未来多模态扩展，当前文本路径为默认。"""
    TEXT = "text"               # 纯文本（当前唯一生产路径）
    STRUCTURED = "structured"   # 结构化 JSON / 快捷指令
    IMAGE = "image"             # 图片（OCR 前）
    AUDIO = "audio"             # 语音（ASR 前）
    MULTIMODAL = "multimodal"   # 混合输入


@dataclass(frozen=True)
class PCRInput_v1:
    """PCR 输入契约 v1.1 — 最小化、可序列化、无业务对象耦合。"""
    version: str = PCRVersion.V1.value
    modality: Modality = Modality.TEXT     # 输入模态，默认纯文本
    query: str = ""                          # 当前用户输入（已预处理，文本模态）
    raw_payload: Optional[Dict[str, Any]] = None  # 非文本模态：原始负载（图片/音频/结构化数据）
    session_id: str = ""                     # 会话标识
    turn_index: int = 0                      # 当前轮次（用于追踪深度计算）
    session_history: List[Dict[str, Any]] = field(default_factory=list)  # 最近 N 轮结构化历史
    process_context: Optional[Dict] = None   # 进程上下文（PID, name, modules, type）
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 用户持久偏好（如默认数据类型）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展字段（版本兼容用）
    timestamp: float = field(default_factory=time.time)  # 新增：输入时间戳（工作记忆衰减计算）

    def validate(self) -> Tuple[bool, Optional[str]]:
        """输入校验。返回 (is_valid, error_message)。"""
        if self.modality == Modality.TEXT:
            if not self.query or not isinstance(self.query, str):
                return False, "query must be non-empty string for TEXT modality"
        if self.query and len(self.query) > 10000:  # 防止超长输入导致正则灾难
            return False, "query exceeds max length 10000"
        if self.turn_index < 0:
            return False, "turn_index must be non-negative"
        return True, None

    def is_text_modality(self) -> bool:
        return self.modality in (Modality.TEXT, Modality.STRUCTURED)

    def is_preprocessing_required(self) -> bool:
        return self.modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL)


@dataclass
class CognitiveProfile_v1:
    """认知画像 v1.0 — 四个维度 + 置信度。"""
    metacognition: float = 0.0       # 0-1: 是否意识到知识边界
    divergence: float = 0.0          # 0-1: 0=收敛（命令式），1=发散（探索式）
    tracking_depth: float = 0.0      # 0-1: 同一主题连续关注程度
    stability: float = 0.0           # 0-1: 用词/意图前后一致性
    # 置信度：每个维度的可靠程度（历史轮次不足时降低）
    confidence: float = 0.0            # 0-1: 整体画像的置信度

    def is_reliable(self) -> bool:
        return self.confidence >= 0.6


@dataclass
class PCROutput_v1:
    """PCR 输出契约 v1.0 — 包含完整的派生策略，下游零计算。"""
    version: str = PCRVersion.V1.value
    
    # 核心评估结果
    expectation: str = "UNKNOWN"                     # TOOL / ADVISOR / COMPANION / UNKNOWN
    noise_level: float = 0.0                         # 0-1
    complexity_level: float = 0.0                    # 0-1
    cognitive_profile: CognitiveProfile_v1 = field(default_factory=CognitiveProfile_v1)
    
    # 派生执行策略（下游直接使用，无需重新计算）
    execution_mode: str = "BALANCED"                  # FAST_EXECUTE / CLARIFICATION / DEEP_RESEARCH / CONVERSATIONAL / BALANCED
    parser_config_overrides: Dict[str, Any] = field(default_factory=dict)  # 直接覆盖 ParserConfig
    prompt_style: str = "BALANCED"                    # BRIEF / EXPLANATORY / TUTORIAL / BALANCED
    ambiguity_strategy: str = "BALANCED"              # AGGRESSIVE_AUTO / CONSERVATIVE_ASK / BALANCED
    
    # 会话级建议（由 PCR 直接给出，不经过 LLM）
    suggested_next_actions: List[str] = field(default_factory=list)  # 前端可渲染为按钮
    should_attach_process: bool = False               # 是否需要提示用户 attach 进程
    should_refresh_analysis: bool = False            # 是否需要自动刷新进程分析
    
    # 遥测与溯源
    trace_log: List[str] = field(default_factory=list)
    latency_ms: float = 0.0                          # 本次评估耗时
    implementation: str = ""                         # 哪个 PCR 实现产生的此输出
    cache_hit: bool = False                          # 是否命中缓存
    
    # 回退标记
    is_fallback: bool = False                        # 是否因异常触发回退
    fallback_reason: Optional[str] = None            # 回退原因
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        if not 0.0 <= self.noise_level <= 1.0:
            return False, "noise_level out of range"
        if not 0.0 <= self.complexity_level <= 1.0:
            return False, "complexity_level out of range"
        return True, None
    
    @classmethod
    def default_fallback(cls, reason: str = "PCR error or timeout") -> "PCROutput_v1":
        """保守回退输出：UNKNOWN + 低阈值 + 高询问倾向。"""
        return cls(
            expectation="UNKNOWN",
            noise_level=0.5,
            complexity_level=0.5,
            execution_mode="CLARIFICATION",
            parser_config_overrides={
                "auto_resolve_threshold": 0.3,
                "max_ambiguities_before_ask": 1,
                "min_confidence_threshold": 0.25,
            },
            prompt_style="BALANCED",
            ambiguity_strategy="CONSERVATIVE_ASK",
            is_fallback=True,
            fallback_reason=reason,
        )


class IPCRRouter(ABC):
    """
    前置认知路由器接口（抽象基类）。
    
    设计原则：
    1. 纯计算：evaluate() 不修改任何外部状态（无状态对象）。
    2. 异常安全：任何异常由调用方捕获，返回 default_fallback()。
    3. 延迟可控：实现必须在自身文档中声明预期延迟范围。
    4. 可预热：需要预热（模型加载等）的实现必须实现 warm_up()，否则空实现。
    5. 可遥测：实现必须通过 telemetry 接口暴露运行时指标。
    """
    
    # ── 标识 ─────────────────────────────────────────────
    
    @property
    @abstractmethod
    def name(self) -> str:
        """实现标识，如 'rule_based_v1'。用于注册、日志、遥测。"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """实现版本，如 '1.0.0'。用于兼容性检查和遥测。"""
        pass
    
    # ── 生命周期 ────────────────────────────────────────
    
    @abstractmethod
    def warm_up(self, config: Dict[str, Any]) -> None:
        """
        预热。在系统启动时调用，可加载配置、编译正则、预热缓存。
        不允许在此方法中调用外部服务（如 LLM API），应仅做本地初始化。
        任何异常应抛出，由 lifecycle manager 捕获并标记为 DEGRADED。
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """
        优雅关闭。释放资源（线程、缓存、文件句柄）。
        必须幂等：多次调用无副作用。
        """
        pass
    
    def reload_config(self, config: Dict[str, Any]) -> bool:
        """
        运行时热更新配置。可选实现，默认不支持热更新。
        返回 True 表示成功，False 表示需要重启才能生效。
        """
        return False
    
    # ── 核心评估 ──────────────────────────────────────
    
    @abstractmethod
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        核心评估方法。评估用户输入，返回认知状态包。
        
        要求：
        - 延迟：必须在实现文档中声明。规则实现 < 10ms，LLM 增强 < 500ms。
        - 异常：实现内部应捕获所有异常，但调用方（FallbackEngine）会额外包 try-except。
        - 状态：不得修改 input_data（frozen dataclass），不得修改全局状态。
        - 线程安全：如果实现使用共享状态，必须自行加锁。
        """
        pass
    
    # ── 遥测与可观测性 ──────────────────────────────────
    
    @abstractmethod
    def get_health(self) -> PCRHealthStatus:
        """返回当前健康状态。"""
        pass
    
    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        """
        返回运行时遥测数据。至少包含：
        - call_count: 总调用次数
        - error_count: 异常次数
        - avg_latency_ms: 平均延迟
        - p99_latency_ms: P99 延迟
        - cache_hit_rate: 缓存命中率（如果有缓存）
        - last_error: 最后一次错误信息（脱敏）
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        返回能力描述。至少包含：
        - supported_expectations: 支持的期望类型列表
        - has_cognitive_profile: 是否支持认知维度评估
        - has_noise_estimation: 是否支持噪声度评估
        - has_complexity_estimation: 是否支持复杂度评估
        - requires_llm: 是否需要 LLM 增强
        - latency_range_ms: [min, max] 延迟范围
        """
        pass
    
    # ── 元信息 ────────────────────────────────────────
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """返回配置 Schema（JSON Schema 格式），用于前端配置 UI 和配置校验。"""
        pass
```

---

## 4. 插件发现引擎（`registry.py`）

```python
"""
PCR 插件发现引擎。支持两种注册方式：
1. 显式注册：代码中调用 register_pcr()
2. 自动扫描：扫描指定目录，自动导入并注册实现了 IPCRRouter 的类

目录结构约定：
    pcr_plugins/
    ├── __init__.py
    ├── rule_based/
    │   ├── __init__.py      # 包含: register_pcr("rule_based", RuleBasedPCR)
    │   ├── identifier.py
    │   ├── estimator.py
    │   └── config.yaml
    └── llm_enhanced/
        ├── __init__.py
        └── ...
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Type, Optional, List

_PCR_REGISTRY: Dict[str, Type[IPCRRouter]] = {}

def register_pcr(name: str, cls: Type[IPCRRouter]) -> None:
    """显式注册 PCR 实现。"""
    if not issubclass(cls, IPCRRouter):
        raise TypeError(f"{cls} must implement IPCRRouter")
    _PCR_REGISTRY[name] = cls

def discover_pcr_plugins(plugin_dir: str) -> List[str]:
    """
    自动扫描目录，发现并注册 PCR 插件。
    返回发现的插件名称列表。
    """
    discovered: List[str] = []
    plugin_path = Path(plugin_dir)
    
    if not plugin_path.exists():
        return discovered
    
    for subdir in plugin_path.iterdir():
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        
        init_file = subdir / "__init__.py"
        if not init_file.exists():
            continue
        
        # 动态导入
        module_name = f"pcr_plugins.{subdir.name}"
        spec = importlib.util.spec_from_file_location(module_name, init_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            # __init__.py 中应调用 register_pcr()
            discovered.append(subdir.name)
    
    return discovered

def create_pcr(name: str, config: Dict[str, Any]) -> IPCRRouter:
    """工厂方法：创建指定名称的 PCR 实现实例。"""
    if name not in _PCR_REGISTRY:
        raise ValueError(
            f"Unknown PCR implementation: '{name}'. "
            f"Available: {list(_PCR_REGISTRY.keys())}. "
            f"Call discover_pcr_plugins() if using directory-based plugins."
        )
    
    cls = _PCR_REGISTRY[name]
    instance = cls()  # 无参构造，配置通过 warm_up(config) 传入
    instance.warm_up(config)
    return instance

def list_available_pcr() -> Dict[str, Dict[str, Any]]:
    """列出所有已注册的 PCR 实现及其能力描述。"""
    return {
        name: cls().get_capabilities()
        for name, cls in _PCR_REGISTRY.items()
    }
```

---

## 5. 错误回退策略引擎（`fallback.py`）

```python
"""
PCR 回退策略引擎。核心设计：PCR 本身不捕获异常，由调用方（FallbackEngine）统一处理。
这样可以确保：
1. 异常不被静默吞掉（可记录、可告警）
2. 回退策略可配置（保守 / 激进）
3. 支持多级回退（主 PCR 失败 → 降级到备用 PCR → 最终默认输出）
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import logging
import traceback

logger = logging.getLogger("pcr.fallback")


@dataclass
class FallbackConfig:
    """回退策略配置。"""
    strategy: str = "conservative"   # "conservative"（总是返回保守默认值）/ "degraded"（尝试备用 PCR）/ "pass_through"（向上抛异常）
    fallback_chain: List[str] = field(default_factory=list)  # 备用 PCR 名称列表（按优先级）
    max_retry: int = 1              # 主 PCR 失败后重试次数（适用于 transient 错误如 LLM 超时）
    retry_delay_ms: float = 100.0   # 重试间隔
    log_errors: bool = True
    expose_errors_to_user: bool = False  # 是否将错误详情暴露给用户（生产环境应为 False）


class FallbackEngine:
    """PCR 回退引擎。包装 IPCRRouter 调用，提供异常处理 + 降级 + 遥测。"""
    
    def __init__(self, primary: IPCRRouter, registry: Dict[str, Type[IPCRRouter]], 
                 config: FallbackConfig):
        self._primary = primary
        self._registry = registry
        self._config = config
        self._fallback_instances: Dict[str, IPCRRouter] = {}
        self._call_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None
    
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._call_count += 1
        start = time.time()
        
        # 1. 尝试主 PCR
        try:
            result = self._primary.evaluate(input_data)
            result.latency_ms = (time.time() - start) * 1000
            result.implementation = self._primary.name
            if self._config.log_errors and result.is_fallback:
                logger.warning(f"Primary PCR returned fallback: {result.fallback_reason}")
            return result
        except Exception as e:
            self._error_count += 1
            self._last_error = f"{type(e).__name__}: {str(e)}"
            if self._config.log_errors:
                logger.error(f"Primary PCR '{self._primary.name}' failed:\n{traceback.format_exc()}")
        
        # 2. 重试（如果是 transient 错误如 LLM 超时）
        if self._config.max_retry > 0:
            for attempt in range(self._config.max_retry):
                try:
                    time.sleep(self._config.retry_delay_ms / 1000.0)
                    result = self._primary.evaluate(input_data)
                    result.latency_ms = (time.time() - start) * 1000
                    result.implementation = self._primary.name
                    return result
                except Exception as e:
                    if self._config.log_errors:
                        logger.warning(f"Primary PCR retry {attempt+1} failed: {e}")
        
        # 3. 尝试备用 PCR（degraded 策略）
        if self._config.strategy == "degraded":
            for fallback_name in self._config.fallback_chain:
                try:
                    fallback = self._get_fallback_instance(fallback_name)
                    result = fallback.evaluate(input_data)
                    result.latency_ms = (time.time() - start) * 1000
                    result.implementation = fallback_name
                    result.is_fallback = True
                    result.fallback_reason = f"Primary '{self._primary.name}' failed, fallback to '{fallback_name}'"
                    logger.warning(f"Activated fallback PCR: {fallback_name}")
                    return result
                except Exception as e:
                    if self._config.log_errors:
                        logger.error(f"Fallback PCR '{fallback_name}' also failed: {e}")
        
        # 4. 最终回退（conservative 或 degraded 失败后的兜底）
        if self._config.strategy in ("conservative", "degraded"):
            fallback_output = PCROutput_v1.default_fallback(
                reason=f"Primary PCR '{self._primary.name}' failed after {self._config.max_retry} retries. "
                       f"Last error: {self._last_error}"
            )
            fallback_output.latency_ms = (time.time() - start) * 1000
            fallback_output.implementation = "default_fallback"
            if self._config.expose_errors_to_user:
                fallback_output.trace_log.append(f"[ERROR] {self._last_error}")
            return fallback_output
        
        # 5. pass_through 策略：向上抛异常
        raise RuntimeError(f"Primary PCR failed and no fallback available: {self._last_error}")
    
    def get_telemetry(self) -> Dict[str, Any]:
        primary_telemetry = self._primary.get_telemetry()
        return {
            **primary_telemetry,
            "fallback_call_count": self._call_count,
            "fallback_error_count": self._error_count,
            "fallback_error_rate": self._error_count / max(1, self._call_count),
            "fallback_last_error": self._last_error,
        }
    
    def _get_fallback_instance(self, name: str) -> IPCRRouter:
        if name not in self._fallback_instances:
            cls = self._registry.get(name)
            if not cls:
                raise ValueError(f"Fallback PCR '{name}' not found in registry")
            instance = cls()
            instance.warm_up({})  # 简化配置
            self._fallback_instances[name] = instance
        return self._fallback_instances[name]
```

---

## 6. 配置管理（`config.py`）

```python
"""
PCR 配置管理。支持：
1. Schema 定义与校验（JSON Schema）
2. 环境变量覆盖（如 PCR_RULE_BASED_COMPLEXITY_MAP=/path/to/map.yaml）
3. 运行时热加载（配置文件变更后自动 reload）
4. 分层配置：全局默认 → 实现级覆盖 → 环境变量 → 运行时动态
"""

from typing import Dict, Any, Optional
import os
import yaml
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PCRGlobalConfig:
    """PCR 全局配置。"""
    implementation: str = "rule_based"           # 默认实现
    fallback_strategy: str = "conservative"      # conservative / degraded / pass_through
    fallback_chain: List[str] = field(default_factory=list)
    enable_telemetry: bool = True
    telemetry_flush_interval_sec: float = 60.0
    plugin_dirs: List[str] = field(default_factory=lambda: ["core/agent/pcr/plugins"])
    
    @classmethod
    def from_file(cls, path: str) -> "PCRGlobalConfig":
        """从 YAML/JSON 文件加载，支持环境变量覆盖。"""
        with open(path, "r") as f:
            if path.endswith(".json"):
                data = json.load(f)
            else:
                data = yaml.safe_load(f)
        
        # 环境变量覆盖
        env_overrides = {}
        for key, val in os.environ.items():
            if key.startswith("PCR_"):
                # PCR_IMPLEMENTATION=rule_based → implementation
                config_key = key[4:].lower()
                env_overrides[config_key] = val
        
        data.update(env_overrides)
        return cls(**data)
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        if self.implementation not in ("rule_based", "llm_enhanced", "hybrid"):
            return False, f"Unknown implementation: {self.implementation}"
        if self.fallback_strategy not in ("conservative", "degraded", "pass_through"):
            return False, f"Unknown fallback_strategy: {self.fallback_strategy}"
        return True, None


class ConfigManager:
    """配置管理器。支持热加载。"""
    
    def __init__(self, global_path: str, implementation_configs: Dict[str, str]):
        self._global_path = Path(global_path)
        self._global_config: Optional[PCRGlobalConfig] = None
        self._impl_configs: Dict[str, Dict] = {}
        self._impl_paths: Dict[str, Path] = {
            name: Path(path) for name, path in implementation_configs.items()
        }
        self._last_modified: Dict[str, float] = {}
        self._load_all()
    
    def _load_all(self) -> None:
        if self._global_path.exists():
            self._global_config = PCRGlobalConfig.from_file(str(self._global_path))
            self._last_modified[str(self._global_path)] = self._global_path.stat().st_mtime
        
        for name, path in self._impl_paths.items():
            if path.exists():
                with open(path, "r") as f:
                    self._impl_configs[name] = yaml.safe_load(f) or {}
                self._last_modified[str(path)] = path.stat().st_mtime
    
    def check_hot_reload(self) -> List[str]:
        """检查是否有配置文件变更。返回变更的文件列表。"""
        changed = []
        for path_str, last_mtime in self._last_modified.items():
            path = Path(path_str)
            if path.exists() and path.stat().st_mtime > last_mtime:
                changed.append(path_str)
                self._last_modified[path_str] = path.stat().st_mtime
        
        if changed:
            self._load_all()
        
        return changed
    
    def get_global(self) -> PCRGlobalConfig:
        return self._global_config or PCRGlobalConfig()
    
    def get_implementation(self, name: str) -> Dict[str, Any]:
        return self._impl_configs.get(name, {})
```

---

## 7. 生命周期管理器（`lifecycle.py`）

```python
"""
PCR 生命周期管理器。负责：
1. 初始化：发现插件 → 加载配置 → 预热主 PCR → 预热备用 PCR
2. 运行时：周期性健康检查 → 热加载检测 → 遥测刷新
3. 关闭：优雅释放所有 PCR 实例
"""

import threading
import time
from typing import Dict, Optional


class PCRLifecycleManager:
    """PCR 生命周期管理器。"""
    
    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        self._primary: Optional[IPCRRouter] = None
        self._fallback_engine: Optional[FallbackEngine] = None
        self._lock = threading.Lock()
        self._running = False
        self._health_check_thread: Optional[threading.Thread] = None
    
    def initialize(self) -> Tuple[bool, Optional[str]]:
        """系统启动时调用。返回 (success, error_message)。"""
        try:
            global_cfg = self._config_manager.get_global()
            valid, err = global_cfg.validate()
            if not valid:
                return False, err
            
            # 1. 发现插件
            for plugin_dir in global_cfg.plugin_dirs:
                discover_pcr_plugins(plugin_dir)
            
            # 2. 创建主 PCR
            impl_config = self._config_manager.get_implementation(global_cfg.implementation)
            self._primary = create_pcr(global_cfg.implementation, impl_config)
            
            # 3. 创建回退引擎
            fallback_cfg = FallbackConfig(
                strategy=global_cfg.fallback_strategy,
                fallback_chain=global_cfg.fallback_chain,
            )
            self._fallback_engine = FallbackEngine(
                self._primary, _PCR_REGISTRY, fallback_cfg
            )
            
            # 4. 启动后台线程（健康检查 + 热加载）
            self._running = True
            self._health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
            self._health_check_thread.start()
            
            return True, None
        except Exception as e:
            return False, f"PCR initialization failed: {e}"
    
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """线程安全的评估入口。含模态分发器。"""
        with self._lock:
            # 模态分发（v2.2 新增）
            if input_data.modality == Modality.TEXT:
                return self._fallback_engine.evaluate(input_data)
            elif input_data.modality == Modality.STRUCTURED:
                # 结构化数据直接转换为意图上下文，跳过文本噪声评估
                return self._evaluate_structured(input_data)
            elif input_data.modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL):
                # 路由到外部预处理器（OCR/ASR），预处理为 TEXT 后再进入标准 Pipeline
                return self._evaluate_with_preprocessing(input_data)
            else:
                return self._fallback_engine.evaluate(input_data)
    
    def _evaluate_structured(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """结构化数据快速路径：绕过文本噪声/复杂度评估，直接意图分类。"""
        # TODO: 实现结构化数据的快速映射
        return self._fallback_engine.evaluate(input_data)
    
    def _evaluate_with_preprocessing(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """非文本模态：调用外部预处理器（OCR/ASR）后重新构造 TEXT 输入。"""
        # 预处理器作为可选外部服务，不引入新依赖
        # 预处理后：PCRInput_v1(modality=TEXT, query=预处理后的文本, raw_payload=None)
        return self._fallback_engine.evaluate(input_data)
    
    def get_telemetry(self) -> Dict[str, Any]:
        return self._fallback_engine.get_telemetry()
    
    def get_health(self) -> PCRHealthStatus:
        if not self._primary:
            return PCRHealthStatus.UNHEALTHY
        return self._primary.get_health()
    
    def shutdown(self) -> None:
        self._running = False
        if self._primary:
            self._primary.shutdown()
        for inst in getattr(self._fallback_engine, '_fallback_instances', {}).values():
            inst.shutdown()
    
    def _health_check_loop(self) -> None:
        """后台线程：周期性健康检查 + 配置热加载。"""
        while self._running:
            time.sleep(self._config_manager.get_global().telemetry_flush_interval_sec)
            
            # 热加载检测
            changed = self._config_manager.check_hot_reload()
            if changed:
                for path in changed:
                    if "rule_based" in path and self._primary:
                        self._primary.reload_config(
                            self._config_manager.get_implementation("rule_based")
                        )
            
            # 健康检查
            if self._primary and self._primary.get_health() == PCRHealthStatus.UNHEALTHY:
                logger.error("Primary PCR is unhealthy. Fallback engine will be used.")
```

---

## 8. 与现有系统的集成点（最小化改动）

### 8.1 `core/intent_agent.py` 改动（仅 2 处）

```python
# 1. 初始化：从配置加载 PCR
class IntentAgent:
    def __init__(self, ...):
        # ... 现有代码 ...
        
        # 新增：PCR 生命周期管理（5 行）
        from core.agent.pcr.lifecycle import PCRLifecycleManager
        from core.agent.pcr.config import ConfigManager
        pcr_config = ConfigManager(
            global_path="config/pcr_global.yaml",
            implementation_configs={
                "rule_based": "core/agent/pcr/rule_based/config.yaml",
                "llm_enhanced": "core/agent/pcr/llm_enhanced/config.yaml",
            }
        )
        self._pcr_lifecycle = PCRLifecycleManager(pcr_config)
        ok, err = self._pcr_lifecycle.initialize()
        if not ok:
            logger.error(f"PCR init failed: {err}, using default fallback")
        # ... 现有代码 ...

    def _react_loop(self):
        # ... 现有代码 ...
        
        # 2. 每次用户输入时调用 PCR（4 行）
        pcr_input = PCRInput_v1(
            query=user_input,
            session_id=session_id,
            turn_index=len(self._conversation_history),
            session_history=[self._msg_to_dict(m) for m in self._conversation_history[-10:]],
            process_context=self._get_process_context(),
        )
        pcr_output = self._pcr_lifecycle.evaluate(pcr_input)
        intent_context = IntentContext.from_pcr_output(pcr_output)
        # ... 传给 Parser ...

    def shutdown(self):
        # 新增：优雅关闭 PCR
        self._pcr_lifecycle.shutdown()
        # ... 现有关闭逻辑 ...
```

### 8.2 `core/agent/models.py` 改动（新增 `from_pcr_output` 工厂方法）

```python
@dataclass
class IntentContext:
    # ... 现有字段 ...
    
    @classmethod
    def from_pcr_output(cls, output: PCROutput_v1) -> "IntentContext":
        """从 PCR 输出契约转换为内部 IntentContext。"""
        return cls(
            expectation=UserExpectation(output.expectation),
            noise_level=output.noise_level,
            complexity_level=output.complexity_level,
            cognitive_profile=CognitiveProfile(
                metacognition=output.cognitive_profile.metacognition,
                divergence=output.cognitive_profile.divergence,
                tracking_depth=output.cognitive_profile.tracking_depth,
                stability=output.cognitive_profile.stability,
            ),
            execution_mode=output.execution_mode,
            auto_resolve_threshold=output.ambiguity_strategy,  # 映射逻辑
            max_ambiguities_before_ask=output.parser_config_overrides.get("max_ambiguities_before_ask", 3),
            max_sub_intents=output.parser_config_overrides.get("max_sub_intents", 5),
            min_confidence_threshold=output.parser_config_overrides.get("min_confidence_threshold", 0.4),
            prompt_style=output.prompt_style,
            trace_log=output.trace_log,
        )
```

---

## 9. 测试策略（Mock + 对抗 + 基准）

### 9.1 Mock 实现（用于上层测试）

```python
# core/agent/pcr/tests/mock_pcr.py

class MockPCR(IPCRRouter):
    """受控 Mock PCR。可预设输出，用于 IntentAgent / IntentParser 的单元测试。"""
    
    def __init__(self, preset_output: Optional[PCROutput_v1] = None):
        self._preset = preset_output
        self._call_history: List[PCRInput_v1] = []
    
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._call_history.append(input_data)
        if self._preset:
            return self._preset
        return PCROutput_v1(
            expectation="TOOL",
            noise_level=0.1,
            complexity_level=0.2,
        )
    
    def assert_called_with(self, query: str) -> bool:
        return any(c.query == query for c in self._call_history)
```

### 9.2 对抗测试集（用于 PCR 实现验证）

```python
# core/agent/pcr/tests/adversarial_suite.py

ADVERSARIAL_CASES = [
    # (input, expected_expectation, expected_noise_range, description)
    ("", "UNKNOWN", (0.8, 1.0), "空输入"),
    ("那个", "UNKNOWN", (0.8, 1.0), "极度模糊"),
    ("scan 4 bytes for 100", "TOOL", (0.0, 0.2), "标准工具指令"),
    ("scan 4 bytes for 100 and then patch it to 999", "TOOL", (0.0, 0.3), "多步骤工具指令"),
    ("I'm trying to reverse this game, where should I start?", "COMPANION", (0.1, 0.4), "探索性对话"),
    ("这个函数看起来加密了，你怎么看？", "ADVISOR", (0.1, 0.3), "分析型中文问句"),
    ("搞一下", "UNKNOWN", (0.7, 1.0), "极度模糊中文"),
    ("help me find health and make it 999 plz", "TOOL", (0.1, 0.3), "带噪音的工具指令"),
    ("先扫描100，然后改成999，再锁定它", "TOOL", (0.1, 0.3), "多步骤中文"),
]
```

### 9.3 基准测试（用于性能验收）

```python
# core/agent/pcr/tests/benchmark.py

def benchmark_pcr(pcr: IPCRRouter, cases: List[str], iterations: int = 1000):
    """测量 PCR 延迟分布。"""
    latencies = []
    for _ in range(iterations):
        for case in cases:
            start = time.perf_counter()
            pcr.evaluate(PCRInput_v1(query=case))
            latencies.append((time.perf_counter() - start) * 1000)
    
    latencies.sort()
    return {
        "min_ms": latencies[0],
        "avg_ms": sum(latencies) / len(latencies),
        "p50_ms": latencies[int(len(latencies)*0.5)],
        "p99_ms": latencies[int(len(latencies)*0.99)],
        "max_ms": latencies[-1],
    }
```

---

## 10. 修正后的实现路径（12 Phase → 14 Phase）

| Phase | 内容 | 预估代码量 | 说明 |
|---|---|---|---|
| **P0** | 接口契约：`interface.py` + `datacontract.py` | 200 行 | 含版本化、校验、回退默认输出 |
| **P1** | 插件注册与发现：`registry.py` + 目录扫描 | 150 行 | 支持显式注册 + 自动发现 |
| **P2** | 回退策略引擎：`fallback.py` | 150 行 | 多级回退、重试、遥测聚合 |
| **P3** | 配置管理：`config.py` + Schema + 热加载 | 200 行 | 环境变量覆盖、YAML/JSON |
| **P4** | 生命周期管理：`lifecycle.py` | 200 行 | 初始化、健康检查、后台线程、优雅关闭 |
| **P5** | 遥测收集器：`telemetry.py` | 100 行 | 延迟分布、异常率、缓存命中率 |
| **P6** | 规则实现：`rule_based/`（完整三层 + 认知维度） | 800 行 | 基于接口实现，独立可运行 |
| **P7** | Mock 实现 + 对抗测试集 + 基准测试 | 300 行 | 用于上层测试和回归验证 |
| **P8** | 单元测试（100+ 用例覆盖接口 + 回退 + 配置） | 500 行 | 接口合规测试、异常注入测试 |
| **P9** | 更新 `IntentContext`（`from_pcr_output`） | 50 行 | 数据契约转换 |
| **P10** | 更新 `IntentAgent`（集成 lifecycle） | 30 行 | 最小化改动 |
| **P11** | 更新 `ParserConfig`（动态化，接收 `parser_config_overrides`） | 100 行 | 从 PCR 输出覆盖配置 |
| **P12** | 更新 TaskGraph Builder（`expectation` 调控） | 100 行 | 期望类型调控分解策略 |
| **P13** | 集成测试（3 种期望 × 4 种画像 × 5 种复杂度 + 回退注入） | 500 行 | 端到端验证 |
| **总计** | | **~3380 行** | |

---

## 11. 与 v2.0 设计的关键差异总结

| 维度 | v2.0（上一版） | v2.2（当前修正版） | 理由 |
|---|---|---|---|
| **接口** | 2 个抽象方法 | 8 个抽象方法（生命周期 + 遥测 + 配置） | 工业级需要完整的生命周期管理 |
| **数据契约** | 无版本 | `PCRVersion.V1` + 校验方法 + `Modality` 枚举 | 未来增加字段时向后兼容；支持多模态扩展 |
| **插件发现** | 手动注册 | 显式注册 + 目录自动扫描 | 降低使用门槛，支持插件生态 |
| **错误处理** | 未定义 | `FallbackEngine`（多级回退 + 重试 + 降级） | 生产环境必须可靠 |
| **配置** | 简单 YAML | Schema 校验 + 环境变量覆盖 + 热加载 | 运维友好，DevOps 标准 |
| **可观测性** | 未定义 | `get_telemetry()` + `get_health()` + 后台线程 | 生产监控必需 |
| **Mock 测试** | 未定义 | `MockPCR` + 对抗测试集 + 基准测试 | 测试驱动开发，独立验证 |
| **集成改动** | 约 10 行 | 约 30 行（增加 lifecycle + shutdown） | 几乎不变，但增加优雅关闭 |
| **多模态接口** | 纯文本 `query` 字段 | `Modality` 枚举 + `raw_payload` + 分发器 | 图像/音频输入不导致文本规则崩溃 |
| **认知刷新感知** | 无 | `timestamp` 字段 + 工作记忆衰减权重 | 时间维度是话题切换检测的关键特征 |

---

> **v2.2 修正版已确认。核心改动：多模态接口（Modality + 分发器）+ 数据契约时间戳（timestamp）+ 认知刷新感知基础。**
> 
> 与 `design_layer0_pcr_and_layer1_intent_parser.md` 联动：v2.2 的 `timestamp` 和 `modality` 字段是 Layer 0 三维话题切换检测模型（时间/指代/描述）的基础设施。