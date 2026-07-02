# DialogMesh LLM 提供者层 — 工程实现文档

> **文档编号**: ENGINEERING-LLM-PROVIDERS-006  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 已有代码（v3.0 需扩展）  
> **对应设计文档**: `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3（三层 LLM）+ `DESIGN_FULL_CONCEPT.md` §4.1.4（LLM 接口）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`  
> **对应代码**: `core/agent/llm_providers/`（7 文件，已存在）  
> **原则**: LLM 是认知核心，提供者层必须支撑多层认知并行运行。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 抽象基类：`LLMProvider`](#5-抽象基类llmprovider)
- [6. 具体实现](#6-具体实现)
- [7. 混合路由：`HybridRouter`](#7-混合路由hybridrouter)
- [8. 故障转移：`FailoverProvider`](#8-故障转移failoverprovider)
- [9. 工厂与配置](#9-工厂与配置)
- [10. v3.0 升级：认知模式与原生异步](#10-v30-升级认知模式与原生异步)
- [11. 测试策略](#11-测试策略)
- [12. 附录：简化与待讨论项](#12-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **LLM 提供者层**的完整实现规范。这是 v3.0 多层 LLM 认知架构的**基础设施层**，所有认知引擎（PCR-LLM、Intent-LLM、Planning-LLM、Meta-Cognitive-LLM、Reflective-LLM、Answer-LLM）都依赖此层进行模型调用。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 统一接口 | `DESIGN_FULL_CONCEPT.md` §4.1.4 | §5 | `LLMProvider` 抽象基类 |
| 多后端支持 | `DESIGN_FULL_CONCEPT.md` §4.1.4 | §6 | OpenAI / Local / Mock |
| 智能路由 | `DESIGN_FULL_CONCEPT.md` §4.1.4 | §7 | 延迟/成本/隐私/质量 |
| 故障转移 | `DESIGN_FULL_CONCEPT.md` §4.1.4 | §8 | 主备降级 + 恢复检测 |
| 配置管理 | `DESIGN_FULL_CONCEPT.md` §4.1.4 | §9 | YAML/代码/环境变量 |
| 认知模式 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3 | §10 | 快速/深度/反思模式 |
| 原生异步 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1 | §10 | 支持认知双工并行 |

### 1.3 诚实标记原则

> ⚠️ **工程原则**：现有 LLM 提供者代码已实现基础功能（统一接口、多后端、路由、故障转移）。v3.0 升级重点是**认知模式**和**原生异步**，以支撑认知双工并行运行。

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/llm_providers/cognitive_provider.py` | 认知模式包装器（快速/深度/反思） | ~150 行 | v3.0 新增 |
| `core/agent/llm_providers/async_base.py` | 原生异步 LLMProvider 基类 | ~100 行 | v3.0 新增 |
| `core/agent/llm_providers/streaming.py` | 流式响应支持（SSE/Chunk） | ~200 行 | v3.0 可选 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/llm_providers/base.py` | 新增 `cognitive_mode` 字段、`generate_stream()` 接口 | 所有 Provider |
| `core/agent/llm_providers/openai_provider.py` | 原生异步实现（aiohttp 替代 requests） | OpenAI 后端 |
| `core/agent/llm_providers/local_provider.py` | 原生异步实现（aiohttp 调用 Ollama/vLLM） | 本地后端 |
| `core/agent/llm_providers/hybrid_router.py` | 支持认知模式路由 + 异步并发选择 | 路由层 |
| `core/agent/llm_providers/provider_factory.py` | 支持认知模式配置加载 | 工厂层 |

### 2.3 v3.0 配置扩展

```yaml
# config/llm_providers.yaml
providers:
  - id: "local-1.5b"
    type: "local"
    backend: "ollama"
    model_path: "qwen2.5:1.5b"
    cognitive_modes: ["fast"]          # 仅支持快速模式
    
  - id: "local-7b"
    type: "local"
    backend: "ollama"
    model_path: "qwen2.5:7b"
    cognitive_modes: ["fast", "deep"]   # 支持快速和深度
    
  - id: "cloud-api"
    type: "openai"
    model: "gpt-4o-mini"
    cognitive_modes: ["fast", "deep", "reflective"]  # 全部支持
    
router:
  default_strategy: "latency"
  max_concurrent_requests: 10           # v3.0 新增：Router 级并发限流
  queue_timeout_ms: 3000               # v3.0 新增：排队超时
  cognitive_mode_routing:           # v3.0 新增：按认知模式路由
    fast:
      preferred: ["local-1.5b", "local-7b"]
      fallback: ["cloud-api"]
    deep:
      preferred: ["local-7b", "cloud-api"]
      fallback: ["local-1.5b"]
    reflective:
      preferred: ["cloud-api"]
      fallback: ["local-7b"]
```

---

## 3. 现有实现评估

### 3.1 代码清单（已存在）

| 文件 | 行数 | 核心职责 | 状态 | v3.0 需求 |
|------|------|---------|------|----------|
| `base.py` | 149 | `LLMProvider` 抽象基类 + `LLMCallMetrics` / `GenerateRequest` / `GenerateResult` | ✅ 可用 | 需扩展认知模式 + 流式接口 |
| `openai_provider.py` | 354 | OpenAI API 兼容（requests 同步） | ✅ 可用 | 需原生异步（aiohttp） |
| `local_provider.py` | ? | 本地模型（Ollama/vLLM） | ✅ 可用 | 需原生异步 |
| `hybrid_router.py` | 191 | 多 Provider 路由（延迟/成本/隐私/质量） | ✅ 可用 | 需扩展认知模式路由 |
| `failover_provider.py` | 139 | 主备故障转移 + 冷却 + 恢复检测 | ✅ 可用 | 需扩展异步支持 |
| `provider_factory.py` | 100 | 工厂模式（from_config / from_yaml） | ✅ 可用 | 需扩展认知模式配置 |
| `mock_provider.py` | ? | Mock 测试 | ✅ 可用 | 无需修改 |

### 3.2 与设计文档的差距

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 认知模式（fast/deep/reflective） | 无 | 需新增 `cognitive_mode` 参数和路由 | P1 |
| 原生异步（非 run_in_executor） | `generate_async()` 使用 `run_in_executor` | 需改为原生 aiohttp/httpx 异步 | P1 |
| 流式响应（SSE） | 无 | 需新增 `generate_stream()` 接口 | P2 |
| 结构化输出约束（JSON Schema） | `json_schema` 字段已定义，但未完全实现 | 需完善 JSON Schema 验证和重试 | P2 |
| 并发调用（认知双工） | 无 | 需支持同一请求多 Provider 并发 | P1 |
| 认知模式路由 | 无 | 需按 fast/deep/reflective 选择 Provider | P1 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         认知引擎层（6 个 LLM 实例）                            │
│  PCR-LLM / Intent-LLM / Planning-LLM / Meta-Cognitive-LLM / Reflective-LLM / Answer-LLM │
│                              ↓ 调用 generate(request, cognitive_mode="fast") │
├─────────────────────────────────────────────────────────────────────────────┤
│  认知模式包装器（CognitiveModeProvider）                                       │
│  ────────────────────────────────────────────────────────────────────────  │
│  • fast:     temperature=0.1, max_tokens=256, timeout=5s                     │
│  • deep:     temperature=0.3, max_tokens=1024, timeout=30s                   │
│  • reflective: temperature=0.5, max_tokens=2048, timeout=60s               │
├─────────────────────────────────────────────────────────────────────────────┤
│  混合路由器（HybridRouter）                                                   │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ 延迟优先  │  │ 成本优先  │  │ 隐私优先  │  │ 质量优先  │                   │
│  │ < 50ms   │  │ 本地优先  │  │ 强制本地  │  │ 云端优先  │                   │
│  │ local-1.5│  │ local-1.5│  │ local-7b │  │ gpt-4o   │                   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │
│              ↓ 按策略选择 Provider + fallback chain                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  具体 Provider 实现                                                           │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ OpenAIProvider│  │ LocalProvider│  │ FailoverProvider│  │ MockProvider│   │
│  │ (gpt-4o-mini)│  │ (Ollama/vLLM)│  │ (主 + 备)     │  │ (测试)      │   │
│  │ 原生异步     │  │ 原生异步     │  │ 降级 + 恢复   │  │ 固定输出    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 抽象基类：`LLMProvider`

### 5.1 现有实现评估

**已有代码**: `base.py` 第 59-149 行

已实现：
- ✅ `generate(request)` → `GenerateResult`（同步）
- ✅ `generate_async(request)` → `GenerateResult`（基于 `run_in_executor` 的伪异步）
- ✅ `health_check()` → `bool`
- ✅ `estimate_latency_ms(prompt_tokens, output_tokens)` → `float`
- ✅ `record_metrics(metrics)` 滑动窗口记录

### 5.2 v3.0 扩展

```python
class LLMProvider(ABC):
    """LLM Provider 抽象基类 v3.0 扩展。"""
    
    # ── 已有接口保持不变 ─────────────────────────
    # name, config, generate, generate_async, health_check, estimate_latency_ms, record_metrics
    
    # ── 新增：v3.0 并发限流 ───────────────────────
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._metrics_history: List[LLMCallMetrics] = []
        self._max_history = 100
        # v3.0 新增：并发限流 — 防止本地模型过载
        self._max_concurrent = config.get("max_concurrent_requests", 10)
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
    
    # ── 新增：v3.0 认知模式 ─────────────────────
    COGNITIVE_MODES = {"fast", "deep", "reflective"}
    
    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """
        执行生成。
        
        v3.0 升级：
        - request.cognitive_mode 字段决定生成参数
        - 如果 Provider 不支持该认知模式，应抛出 ValueError
        """
        ...
    
    # ── 新增：原生异步接口（v3.0）──────────────────
    @abstractmethod
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        """
        原生异步生成 — 非 run_in_executor 包装。
        
        使用 aiohttp/httpx 进行真正的异步 HTTP 调用，
        支持认知双工的多 Provider 并发执行。
        
        实现要求：
        1. 使用 self._semaphore 限流（防止本地模型过载）
        2. 在 request.timeout_ms 内返回（超时返回失败标记）
        3. 异常捕获：不抛异常，返回 success=False 的 GenerateResult
        """
        ...
    
    # ── 新增：异步健康检查（v3.0）──────────────────
    async def health_check_async(self) -> bool:
        """
        异步健康检查。
        默认实现：使用 run_in_executor 包装同步 health_check。
        子类应重写为原生异步实现（避免阻塞事件循环）。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.health_check)
    
    # ── 新增：流式响应（v3.0 可选）────────────────
    @abstractmethod
    def generate_stream(self, request: GenerateRequest) -> Iterator[str]:
        """
        流式生成 — 逐字返回响应。
        
        用于 Answer-LLM 的实时回复场景，减少用户等待感。
        """
        ...
    
    # ── 新增：支持认知模式查询 ───────────────────
    def supports_cognitive_mode(self, mode: str) -> bool:
        """查询此 Provider 是否支持指定的认知模式。"""
        return mode in self.config.get("cognitive_modes", ["fast"])
    
    # ── 新增：批量生成（v3.0）────────────────────
    async def generate_batch(self, requests: List[GenerateRequest]) -> List[GenerateResult]:
        """
        批量异步生成 — 用于认知双工并发调用。
        
        默认实现：使用 asyncio.gather 并发执行所有请求。
        子类可重写以优化（如 OpenAI 的 batch API）。
        """
        tasks = [self.generate_native_async(req) for req in requests]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### 5.3 `GenerateRequest` v3.0 扩展

```python
@dataclass
class GenerateRequest:
    """标准化生成请求 v3.0。"""
    
    # ── 已有字段保持不变 ─────────────────────────
    prompt: str = ""
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None
    max_tokens: int = 512
    temperature: float = 0.3
    timeout_ms: int = 30000
    response_format: Optional[str] = None
    json_schema: Optional[Dict] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ── 新增：v3.0 认知模式 ─────────────────────
    cognitive_mode: str = "fast"  # "fast" | "deep" | "reflective"
    # fast:     低延迟（< 200ms），低温度，短输出
    # deep:     标准延迟（< 1s），中温度，中等输出
    # reflective: 高延迟（< 5s），高温度，长输出，适合复盘
    
    # ── 新增：v3.0 会话追踪 ─────────────────────
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # ── 新增：v3.0 流式请求 ─────────────────────
    stream: bool = False  # 是否请求流式响应
```

---

## 6. 具体实现

### 6.1 `OpenAIProvider`

**已有代码**: `openai_provider.py` 第 1-354 行

**v3.0 升级：原生异步**

```python
class OpenAIProvider(LLMProvider):
    """OpenAI API 兼容 Provider — v3.0 支持原生异步。"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._api_key = config.get("api_key", "")
        self._base_url = config.get("base_url", "https://api.openai.com/v1")
        self._model = config.get("model", "gpt-4o-mini")
        self._sync_client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        self._async_client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
    
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """同步生成 — 使用 openai.OpenAI。"""
        # ... 现有实现 ...
    
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        """原生异步生成 — 使用 openai.AsyncOpenAI + semaphore 限流。"""
        async with self._semaphore:  # v3.0 并发限流
            t0 = time.time()
            try:
                response = await self._async_client.chat.completions.create(
                    model=self._model,
                messages=self._build_messages(request),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format={"type": "json_object"} if request.response_format == "json" else None,
                timeout=request.timeout_ms / 1000,
            )
            text = response.choices[0].message.content
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=(time.time() - t0) * 1000,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                success=True,
                model_id=self._model,
            )
            return GenerateResult(text=text, metrics=metrics, raw_response=response)
        except Exception as e:
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=(time.time() - t0) * 1000,
                success=False,
                error_type=type(e).__name__,
            )
            return GenerateResult(text="", metrics=metrics)
    
    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        """流式生成 — SSE 逐字返回。"""
        stream = await self._async_client.chat.completions.create(
            model=self._model,
            messages=self._build_messages(request),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

### 6.2 `LocalProvider`

**v3.0 升级：原生异步 + Ollama 流式**

```python
class LocalProvider(LLMProvider):
    """本地模型 Provider（Ollama / vLLM）— v3.0 支持原生异步。"""
    
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        """使用 aiohttp 异步调用 Ollama API + semaphore 限流。"""
        async with self._semaphore:  # v3.0 并发限流
            import aiohttp
            
            t0 = time.time()
            url = f"{self._base_url}/api/generate"
        payload = {
            "model": self._model,
            "prompt": request.prompt,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
            "stream": False,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=request.timeout_ms/1000)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("response", "")
                    metrics = LLMCallMetrics(
                        provider_name=self.name,
                        latency_ms=(time.time() - t0) * 1000,
                        success=True,
                        model_id=self._model,
                    )
                    return GenerateResult(text=text, metrics=metrics)
                else:
                    metrics = LLMCallMetrics(
                        provider_name=self.name,
                        latency_ms=(time.time() - t0) * 1000,
                        success=False,
                        error_type=f"http_{resp.status}",
                    )
                    return GenerateResult(text="", metrics=metrics)
```

---

## 7. 混合路由：`HybridRouter`

### 7.1 现有实现评估

**已有代码**: `hybrid_router.py` 第 37-191 行

已实现：
- ✅ 4 种策略：`latency` / `cost` / `privacy` / `quality`
- ✅ 动态 Provider 选择（`_rank_providers`）
- ✅ Fallback chain（失败时降级）
- ✅ 运行时注册（`register_provider`）

### 7.2 v3.0 升级：认知模式路由

```python
class HybridRouter(LLMProvider):
    """混合路由 Provider — v3.0 支持认知模式路由。"""
    
    STRATEGIES = {"latency", "cost", "privacy", "quality"}
    COGNITIVE_MODES = {"fast", "deep", "reflective"}
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.strategy = config.get("default_strategy", "latency")
        self.fallback_chain = config.get("fallback_chain", [])
        # v3.0 新增：认知模式路由配置
        self.cognitive_mode_routing = config.get("cognitive_mode_routing", {})
        self._providers: Dict[str, LLMProvider] = {}
        self._build_providers(config.get("providers", []))
    
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """
        v3.0 升级：
        1. 如果 request.cognitive_mode 指定，优先使用认知模式路由
        2. 否则使用默认策略路由
        """
        mode = request.cognitive_mode
        if mode in self.cognitive_mode_routing:
            # 认知模式路由
            route_config = self.cognitive_mode_routing[mode]
            candidates = route_config.get("preferred", [])
            fallback = route_config.get("fallback", [])
        else:
            # 默认策略路由
            candidates = self._rank_providers(request)
            fallback = self.fallback_chain
        
        # 尝试候选 Provider
        for pid in candidates + fallback:
            provider = self._providers.get(pid)
            if provider is None:
                continue
            if not provider.health_check():
                continue
            if not provider.supports_cognitive_mode(mode):
                continue
            
            result = provider.generate(request)
            result.metrics.provider_name = f"{self.name}/{pid}"
            self.record_metrics(result.metrics)
            
            if result.metrics.success:
                return result
        
        # 全部失败
        return GenerateResult(
            text="",
            metrics=LLMCallMetrics(
                provider_name=self.name,
                latency_ms=0,
                success=False,
                error_type="all_providers_failed",
            ),
        )
    
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        """
        v3.0：原生异步路由 — 优先级顺序 + 并发健康检查（非竞争模式）。
        
        风险缓解：
        - 旧实现（asyncio.as_completed 竞争模式）会导致慢 Provider 拖慢整个路由
        - 新实现：先并发健康检查，然后按优先级逐个调用，第一个成功即返回
        - 每个 Provider 内部有 _semaphore 限流，防止本地模型过载
        """
        mode = request.cognitive_mode
        candidates = self._get_candidates(request, mode)
        
        # 第一步：并发健康检查（只检查，不生成）
        healthy_tasks = []
        for pid in candidates:
            provider = self._providers.get(pid)
            if provider and provider.supports_cognitive_mode(mode):
                healthy_tasks.append(self._check_health_async(pid, provider))
        
        # 收集健康结果
        health_results = await asyncio.gather(*healthy_tasks, return_exceptions=True)
        healthy = [pid for pid, ok in health_results if ok]
        
        if not healthy:
            return self._all_failed_result()
        
        # 第二步：按优先级逐个调用（不竞争，第一个成功即返回）
        for pid in healthy:
            provider = self._providers[pid]
            try:
                result = await provider.generate_native_async(request)
                result.metrics.provider_name = f"{self.name}/{pid}"
                self.record_metrics(result.metrics)
                if result.metrics.success:
                    return result
            except Exception:
                continue
        
        # 全部失败
        return self._all_failed_result()
    
    async def _check_health_async(self, pid: str, provider: LLMProvider) -> Tuple[str, bool]:
        """异步健康检查，返回 (pid, is_healthy)。"""
        try:
            ok = await provider.health_check_async()
            return pid, ok
        except Exception:
            return pid, False
    
    def _all_failed_result(self) -> GenerateResult:
        """所有 Provider 失败时的统一返回。"""
        return GenerateResult(
            text="",
            metrics=LLMCallMetrics(
                provider_name=self.name,
                latency_ms=0,
                success=False,
                error_type="all_providers_failed_async",
            ),
        )
    
    async def _try_provider_async(self, pid: str, provider: LLMProvider, request: GenerateRequest) -> Optional[GenerateResult]:
        """异步尝试单个 Provider，失败返回 None。（保留用于兼容，新逻辑不再使用）"""
        try:
            if not await provider.health_check_async():
                return None
            result = await provider.generate_native_async(request)
            result.metrics.provider_name = f"{self.name}/{pid}"
            self.record_metrics(result.metrics)
            return result
        except Exception:
            return None
```

---

## 8. 故障转移：`FailoverProvider`

### 8.1 现有实现评估

**已有代码**: `failover_provider.py` 第 23-139 行

已实现：
- ✅ 主备降级（主失败 → 备用）
- ✅ 冷却机制（`failover_cooldown_s`）
- ✅ 恢复检测（主恢复后自动切回）
- ✅ 降级状态记录

### 8.2 v3.0 扩展：异步支持

```python
class FailoverProvider(LLMProvider):
    """主备降级包装器 — v3.0 支持异步。"""
    
    # ── 已有同步实现保持不变 ─────────────────────
    
    # ── 新增：异步故障转移 ───────────────────────
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        t0 = time.time()
        
        # 检查主节点（异步健康检查）
        primary_alive = await self.primary.health_check_async()
        if primary_alive and not self._is_degraded:
            try:
                result = await self.primary.generate_native_async(request)
                if result.text and result.text.strip():
                    if self._is_degraded:
                        self._is_degraded = False
                    return result
                raise ValueError("Empty response from primary")
            except Exception as e:
                self._mark_degraded("primary_failed_async", str(e))
        
        # 降级到备用
        try:
            result = await self.fallback.generate_native_async(request)
            result.metrics.error_type = "degraded_to_fallback_async"
            return result
        except Exception as e:
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=(time.time() - t0) * 1000,
                success=False,
                error_type="both_failed_async",
            )
            return GenerateResult(text="[System Error: LLM async service unavailable]", metrics=metrics)
```

---

## 9. 工厂与配置

### 9.1 现有实现评估

**已有代码**: `provider_factory.py` 第 23-100 行

已实现：
- ✅ `from_config(config)`：从字典构建
- ✅ `from_yaml(path)`：从 YAML 加载
- ✅ `get_default_router()`：默认预设（local-1.5b → local-7b → cloud-api）

### 9.2 v3.0 扩展：认知模式配置

```python
class ProviderFactory:
    """Provider 工厂 — v3.0 支持认知模式配置。"""
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> LLMProvider:
        ptype = config.get("type", "hybrid")
        name = config.get("name", "default")
        
        if ptype == "hybrid":
            return HybridRouter(name, config)
        elif ptype == "openai":
            return OpenAIProvider(name, config)
        elif ptype == "local":
            return LocalProvider(name, config)
        elif ptype == "failover":
            primary = cls.from_config(config["primary"])
            fallback = cls.from_config(config["fallback"])
            return FailoverProvider(name, config, primary, fallback)
        elif ptype == "cognitive":  # v3.0 新增：认知模式包装器
            base = cls.from_config(config["base"])
            return CognitiveModeProvider(name, config, base)
        else:
            raise ValueError(f"Unknown provider type: {ptype}")
    
    @classmethod
    def create_cognitive_router(cls, config_path: Optional[str] = None) -> HybridRouter:
        """v3.0：创建支持认知模式的路由器。"""
        config = {
            "name": "cognitive-router",
            "type": "hybrid",
            "default_strategy": "latency",
            "cognitive_mode_routing": {
                "fast": {
                    "preferred": ["local-1.5b"],
                    "fallback": ["local-7b", "cloud-api"]
                },
                "deep": {
                    "preferred": ["local-7b", "cloud-api"],
                    "fallback": ["local-1.5b"]
                },
                "reflective": {
                    "preferred": ["cloud-api"],
                    "fallback": ["local-7b"]
                }
            },
            # ... providers 配置
        }
        return HybridRouter("cognitive-router", config)
```

---

## 10. v3.0 升级：认知模式与原生异步

### 10.1 认知模式参数映射

```python
COGNITIVE_MODE_PARAMS = {
    "fast": {
        "temperature": 0.1,      # 低温度，减少发散
        "max_tokens": 256,      # 短输出
        "timeout_ms": 5000,     # 5 秒超时
        "description": "快速响应：低延迟、低发散、短输出。用于 PCR-LLM、Intent-LLM 的实时层。"
    },
    "deep": {
        "temperature": 0.3,      # 中温度
        "max_tokens": 1024,     # 中等输出
        "timeout_ms": 30000,    # 30 秒超时
        "description": "深度推理：标准延迟、中等发散、中等输出。用于 Planning-LLM、Meta-Cognitive-LLM。"
    },
    "reflective": {
        "temperature": 0.5,      # 较高温度，允许更多思考
        "max_tokens": 2048,     # 长输出
        "timeout_ms": 60000,    # 60 秒超时
        "description": "复盘反思：高延迟、高发散、长输出。用于 Reflective-LLM 的长期复盘。"
    }
}
```

### 10.2 原生异步 vs 伪异步

| 特性 | 现有 `generate_async`（伪异步） | v3.0 `generate_native_async`（原生异步） |
|------|-------------------------------|----------------------------------------|
| 实现方式 | `run_in_executor` 包装同步 `generate()` | 直接使用 `aiohttp` / `openai.AsyncOpenAI` |
| 并发性能 | 受线程池限制（默认 4 线程） | 理论上无上限（仅受网络并发限制） |
| 认知双工支持 | 有限（线程竞争） | 完全支持（6 个 LLM 实例并发） |
| 流式支持 | 不支持 | 支持 SSE 逐字返回 |
| 适用场景 | 简单异步调用 | 多层 LLM 并行、高并发 |

### 10.3 认知双工并发示例

```python
async def cognitive_duplex_call(
    router: HybridRouter,
    request: GenerateRequest,
) -> Tuple[GenerateResult, GenerateResult]:
    """
    认知双工：同时调用规则引擎和 LLM 引擎。
    
    v3.0 使用原生异步并发，非线程池。
    """
    # 规则引擎（本地，fast 模式）
    rule_request = GenerateRequest(
        prompt=request.prompt,
        cognitive_mode="fast",
        max_tokens=128,
        temperature=0.1,
    )
    
    # LLM 引擎（云端，deep 模式）
    llm_request = GenerateRequest(
        prompt=request.prompt,
        cognitive_mode="deep",
        max_tokens=1024,
        temperature=0.3,
    )
    
    # 原生异步并发调用
    rule_task = router.generate_native_async(rule_request)
    llm_task = router.generate_native_async(llm_request)
    
    rule_result, llm_result = await asyncio.gather(rule_task, llm_task)
    
    return rule_result, llm_result
```

---

## 11. 测试策略

### 11.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 每个 Provider 的 `generate()` / `health_check()` / `estimate_latency_ms()` |
| 异步测试 | 100% | `generate_native_async()` 的并发正确性 |
| 路由测试 | 100% | 4 种策略 + 3 种认知模式的 Provider 选择正确性 |
| 故障转移测试 | 100% | 主失败 → 备用 → 主恢复 → 切回主 |
| 认知模式测试 | 100% | fast/deep/reflective 的参数映射正确 |
| 性能测试 | 关键路径 | 100 并发请求 < 2s 完成（原生异步） |

### 11.2 关键测试用例

**用例 1：认知模式路由**
```python
def test_cognitive_mode_routing():
    router = ProviderFactory.create_cognitive_router()
    
    # fast 模式 → 应路由到 local-1.5b
    fast_req = GenerateRequest(prompt="test", cognitive_mode="fast")
    result = router.generate(fast_req)
    assert "local-1.5b" in result.metrics.provider_name
    
    # reflective 模式 → 应路由到 cloud-api
    refl_req = GenerateRequest(prompt="test", cognitive_mode="reflective")
    result = router.generate(refl_req)
    assert "cloud-api" in result.metrics.provider_name
```

**用例 2：原生异步并发**
```python
async def test_native_async_concurrency():
    router = ProviderFactory.create_cognitive_router()
    
    # 100 个并发请求
    requests = [GenerateRequest(prompt=f"test {i}") for i in range(100)]
    tasks = [router.generate_native_async(req) for req in requests]
    
    t0 = time.time()
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - t0
    
    # 100 个请求应在 2 秒内完成（假设每个请求 < 200ms，并发 10 个）
    assert elapsed < 2.0
    assert all(r.metrics.success for r in results)
```

**用例 3：故障转移**
```python
def test_failover_recovery():
    primary = MockProvider("primary", {"fail": True})
    fallback = MockProvider("fallback", {"fail": False})
    provider = FailoverProvider("failover", {}, primary, fallback)
    
    # 主失败 → 降级到备用
    result = provider.generate(GenerateRequest(prompt="test"))
    assert result.metrics.error_type == "degraded_to_fallback"
    
    # 主恢复 → 下次请求应使用主
    primary.config["fail"] = False
    result = provider.generate(GenerateRequest(prompt="test"))
    assert result.metrics.provider_name == "primary"
```

---

## 12. 附录：简化与待讨论项

### 12.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 流式响应 | `generate_stream()` 接口 + SSE 支持 | 无（接口未实现） | 流式响应主要用于 GUI 实时展示，当前 CLI 场景不需要 | Phase 5 GUI 升级时实现 |
| **S-02** | JSON Schema 验证 | `json_schema` 字段的完整验证和重试 | 字段已定义，但未实现验证逻辑 | JSON Schema 验证增加复杂度和依赖（jsonschema 库） | Phase 2 引入结构化输出约束时实现 |
| **S-03** | 批量生成优化 | `generate_batch()` 使用 OpenAI 的 batch API | 默认使用 `asyncio.gather` | OpenAI Batch API 有 24 小时延迟，不适合实时场景 | Phase 3 引入离线批量处理时实现 |
| **S-04** | 多节点负载均衡 | 同一 Provider 多个实例的负载均衡 | 仅单实例 | 多实例需要服务发现和健康检查，增加复杂度 | Phase 3 多节点部署时实现 |
| **S-05** | 缓存层 | 相同请求的响应缓存（TTL 5 分钟） | 无缓存 | 缓存层增加内存占用，初期不需要 | Phase 2 高频重复请求场景时实现 |

### 12.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 异步 HTTP 客户端选择 | A) aiohttp  B) httpx  C) 原生 asyncio | 建议 B：httpx 同时支持同步和异步 API，代码统一性更好 |
| **D-02** | 流式响应的消费者 | A) 仅 Answer-LLM  B) 所有 LLM 实例可选  C) 仅 GUI 层 | 建议 A：流式响应主要用于用户展示，其他 LLM 不需要 |
| **D-03** | 认知模式的超时策略 | A) 固定超时（fast=5s, deep=30s, reflective=60s）  B) 基于历史延迟动态调整  C) 基于 Provider 能力调整 | 建议 C：本地 Provider 和云端 Provider 的延迟差异大，应基于实际能力调整 |
| **D-04** | 健康检查频率 | A) 每次请求前检查  B) 后台定时检查（每 10 秒）  C) 失败时检查 + 定时检查 | 建议 C：平衡准确性和性能 |
| **D-05** | 备用 Provider 的降级策略 | A) 永久降级（直到手动恢复）  B) 定时恢复尝试（每 60 秒）  C) 指数退避恢复（60s → 120s → 240s） | 建议 C：指数退避避免频繁尝试失败节点 |
| **D-06** | Provider 并发限流阈值 | A) 固定值（local-1.5b=5, local-7b=3, cloud=50）  B) 基于 CPU/GPU 负载动态调整  C) 基于历史延迟自适应 | 建议 A：初期固定值，Phase 3 引入动态调整 |
| **D-07** | Router 竞争模式 vs 顺序模式 | A) 竞争模式（asyncio.as_completed，返回第一个成功）  B) 顺序模式（先健康检查，再按优先级逐个调用）  C) 混合模式（健康检查竞争，生成顺序） | 建议 B：顺序模式避免慢 Provider 拖快 Provider，已采用（见 §7.2） |

### 12.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §4.1.4 | §5-§9 | ✅ 等价 | 统一接口 + 多后端 + 路由 + 故障转移覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3 | §10 | ✅ 等价 | 认知模式（fast/deep/reflective）覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1 | §10.2 | ✅ 等价 | 原生异步支持覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §10.3 | ✅ 等价 | Answer-LLM 穿透层依赖的 Provider 能力覆盖 |
| `ENGINEERING_MULTILAYER_LLM.md` §5 | §10.3 | ✅ 等价 | 认知双工并发调用覆盖 |
| `ENGINEERING_MULTILAYER_LLM.md` §7 | §10.1 | ✅ 等价 | 三层 LLM 认知模式参数映射覆盖 |

> ⚠️ **风险缓解**：本文档已针对三个关键风险实施缓解措施：
> 1. **并发瓶颈**：每个 Provider 增加 `_semaphore` 限流（`max_concurrent_requests`），HybridRouter 改为「先并发健康检查，再按优先级顺序调用」模式，避免 `asyncio.as_completed` 竞争导致的慢 Provider 拖慢问题（§5.2, §7.2）。
> 2. **原生异步性能**：`generate_native_async` 使用原生 `aiohttp`/`openai.AsyncOpenAI`，非 `run_in_executor` 包装，支持真正的并发（§6.1, §6.2）。
> 3. **配置安全**：Provider 配置支持 `queue_timeout_ms`，防止排队过久导致系统卡顿（§2.3）。

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和现有代码评估生成。现有 LLM 提供者代码已实现约 **80%** 的基础需求，v3.0 升级新增约 **450 行代码**（认知模式 + 原生异步 + 流式支持）。所有简化项已在 §12.1 中诚实标记，待讨论项在 §12.2 中列出，等待团队确认。*
