# 架构审计报告：9 个关键设计问题分析与修复方案

> 审计日期：基于 v2.5 代码快照
> 审计范围：core/agent/ 全量代码（Layer 0→4）
> 审计方法：代码走查 + 设计文档交叉验证 + 反事实推演

---

## 问题 1：PCR 决策闭环 — 噪声/复杂度/画像是否真正影响决策？

### 现状分析

**PCR 输出确实被下游消费，但消费方式是"前馈"而非"闭环"：**

| 消费点 | 文件 | 代码 | 作用 |
|--------|------|------|------|
| Gate-0 快速通过 | `gates.py:111` | `noise < 0.3 and confidence > 0.8` | 低噪声高置信度 → 跳过 LLM |
| Gate-1 轨道选择 | `gates.py:119` | 同上 | 决定 Track-0（规则）还是 Track-1（LLM） |
| Orchestration 蓝图选择 | `gates.py:208-221` | `noise > 0.7` → fast path; `metacognition < 0.3` → tutorial | 从 3 个预置蓝图中选择 |
| Router LLM 输入 | `gates.py:234-241` | 将 noise/complexity/metacognition 打包给 LLM | 影响 LLM 的蓝图选择 |

**问题诊断：**

1. **阈值是硬编码的**（0.3, 0.5, 0.7），没有根据历史准确率动态调整。如果 `noise=0.29` 总是导致误判，系统不会自动把阈值降到 0.25。
2. **没有反馈回路**：用户点击"这个推荐不对"或"需要澄清"后，这些信号没有回流到 PCR 的阈值调整。
3. **认知画像的维度被浪费了**：`divergence`（发散性）和 `tracking_depth`（追踪深度）在 Gate 逻辑中完全未被使用，只有 `metacognition` 和 `stability` 被消费。

### 反事实推演

假设一个场景：
- 用户连续 5 轮输入都是高噪声（`noise > 0.6`），但 Gate 每次都将其判定为 Track-0（因为 expectation 不是 UNKNOWN）。
- 结果：5 轮中有 3 轮意图识别错误，用户不得不反复澄清。
- **系统学到了什么？** 什么都没有。下一次同样高噪声的输入，系统还是会走同样的路径。

### 修复方案：引入 Feedback Loop

```python
# 在 GateResult 中增加 feedback 字段，用于闭环学习
dataclass
class GateResult:
    track: str
    blueprint_id: str
    pcr_output: PCROutput_v1
    trace: List[str]
    # 新增：反馈链路
    was_accurate: Optional[bool] = None  # 用户反馈：这次决策是否正确
    required_clarification: bool = False  # 是否触发了澄清
    
# 在 Session 中增加 PCR 阈值自适应状态
@dataclass
class Session:
    # ... 现有字段
    # 新增：阈值自适应（每个会话独立，保护隐私）
    adaptive_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "noise_fast_path": 0.3,   # 默认阈值，可自适应调整
        "confidence_min": 0.8,
        "complexity_tutorial": 0.5,
    })
    _threshold_feedback_buffer: List[Tuple[float, bool]] = field(default_factory=list)  # (noise, was_accurate)

# 在 AgentService.process_message 的末尾，根据结果反馈调整阈值
# 如果触发了澄清 → 降低 noise_fast_path 阈值（更谨慎）
# 如果直接成功 → 保持或略微提高阈值（更激进）
```

**修复优先级**：P0（高）—— 没有反馈闭环，PCR 的价值减半。

---

## 问题 2：CognitiveProfiler 冷启动 — 新用户的初始画像值

### 现状分析

```python
# rule_based.py:673-679
class CognitiveProfile:
    def __init__(self):
        self.metacognition = 0.0      # ← 问题 1：所有新用户被判定为"低元认知"
        self.divergence = 0.5           # ← 中性值，但首次对话就判定为"中等发散"
        self.tracking_depth = 0.0
        self.stability = 1.0          # ← v2.3.1 已修正首轮，但 metacognition 未修正
        self.confidence = 0.0
        self.last_topic = None
        self.last_text = ""
        self.turn_count = 0
```

**问题诊断：**

1. **metacognition = 0.0**：在 `OrchestrationGate._select_blueprint` 中，条件 `metacognition < 0.3 and complexity > 0.5` 对新用户几乎总是成立（因为 0.0 < 0.3）。这意味着**所有新用户的第一轮复杂请求都会被路由到 Tutorial 模式**，即使他们是专家。
2. **stability = 1.0（虽然首轮已修正）**：v2.3.1 的修正只处理了 `stability`，但 `confidence` 的计算 `min(1.0, turn_count * 0.05 + stability * 0.3)` 在第一轮时只有 `0.3`（如果 stability 被修正为 0.7），仍然偏低。
3. **没有用户类型预设**：系统无法区分"新用户但可能是专家"和"新用户且是新手"。

### 反事实推演

- 专家用户第一次使用，输入"扫描 Game.exe 的 .text 段并反汇编 0x00401000 处的函数"。
- 系统判定：complexity=0.8（因为涉及多个技术术语），metacognition=0.0（冷启动）。
- 结果：路由到 `LLM_TUTORIAL` 蓝图，生成大量解释性文本，专家用户感到被 patronizing。
- **专家流失。**

### 修复方案：显式冷启动策略

```python
class CognitiveProfile:
    # 冷启动策略：不再假设所有新用户都是新手
    def __init__(self, user_type_hint: Optional[str] = None):
        """
        user_type_hint: "expert" | "novice" | None（未知，需探测）
        """
        self.user_type_hint = user_type_hint
        
        if user_type_hint == "expert":
            # 专家预设：高元认知，低发散（目标明确），高稳定性
            self.metacognition = 0.8
            self.divergence = 0.2
            self.stability = 0.9
        elif user_type_hint == "novice":
            # 新手预设：低元认知，高发散（可能探索性提问），低稳定性
            self.metacognition = 0.1
            self.divergence = 0.8
            self.stability = 0.3
        else:
            # 未知：使用中性值，但通过首轮输入快速探测
            self.metacognition = 0.5  # 中性，不偏不倚
            self.divergence = 0.5
            self.stability = 0.5
        
        self.tracking_depth = 0.0
        self.confidence = 0.5  # 中性置信度
        self.turn_count = 0

    def first_turn_probe(self, query: str) -> None:
        """
        首轮探测：根据输入特征快速调整初始画像。
        如果输入包含多个技术术语 + 精确参数 → 可能是专家
        如果输入模糊（"帮我看一下"）+ 无参数 → 可能是新手
        """
        technical_terms = {"基址", "偏移", "OEP", "IAT", "EAT", "RVA", "VA", "PE", "ELF", "hook", "patch", "dump"}
        has_precise_params = bool(re.search(r'0x[0-9a-fA-F]+|\d+\.exe|PID\s*\d+', query))
        term_count = sum(1 for t in technical_terms if t in query.lower())
        
        if term_count >= 2 and has_precise_params:
            # 专家信号强烈
            self.metacognition = 0.8
            self.stability = 0.9
            self.divergence = 0.2
        elif term_count == 0 and not has_precise_params:
            # 新手信号
            self.metacognition = 0.1
            self.divergence = 0.8
            self.stability = 0.3
        # 否则保持中性，让后续轮次自然收敛
```

**前端接口**：`CreateSessionRequest` 中增加 `user_type_hint` 字段（可选，用户可在首次使用时声明自己的水平）。

**修复优先级**：P1（高）—— 直接影响用户体验，专家用户流失风险。

---

## 问题 3：21 条规则的维护成本与冲突检测

### 现状分析

```python
# intent_parser.py:70-102
@dataclass
class IntentRule:
    pattern: re.Pattern
    category: IntentCategory
    base_confidence: float = 0.8
    priority: int = 0  # ← 只有优先级，没有冲突声明

_RULES.sort(key=lambda r: -r.priority)  # ← 按优先级排序，高优先级覆盖低优先级
```

**问题诊断：**

1. **没有冲突检测机制**：两条规则可能同时匹配同一输入，但只有 `priority` 决定哪个胜出。如果高优先级规则错误匹配，低优先级规则即使正确也无法被选中。
2. **没有 `conflicts_with` 声明**：规则 A（`"扫描"` → 内存扫描）和规则 B（`"扫描"` → 端口扫描）在 medical 领域可能冲突，但代码中没有显式声明这种冲突。
3. **消解策略是隐式的**：高 priority 覆盖低 priority，但 priority 是人工设定的，没有客观依据。

### 反事实推演

- 新增一条规则：`"扫描"` → 影像检查（medical 领域），priority=90。
- 现有规则：`"扫描"` → 内存扫描（reverse engineering），priority=100。
- 结果：medical 领域的输入"扫描肺部 CT"被错误匹配到内存扫描（priority 100 > 90）。
- **系统没有检测到这个冲突**，因为没有运行时冲突检测脚本。

### 修复方案：显式冲突检测 + 分层规则结构

```python
@dataclass
class IntentRule:
    pattern: re.Pattern
    category: IntentCategory
    base_confidence: float = 0.8
    priority: int = 0
    # 新增：冲突声明
    conflicts_with: List[str] = field(default_factory=list)  # 冲突的规则名列表
    domain: Optional[str] = None  # 领域标签（"reverse_engineering", "medical", "network"）
    
    def matches(self, text: str) -> bool:
        return self.pattern.search(text) is not None

# 运行时冲突检测（每次规则注册时）
class IntentRuleRegistry:
    def __init__(self):
        self._rules: List[IntentRule] = []
        self._conflict_graph: Dict[str, Set[str]] = {}  # 规则名 -> 冲突的规则名集合
    
    def register(self, rule: IntentRule) -> None:
        # 1. 检查与已有规则的冲突
        for existing in self._rules:
            if self._has_overlap(rule, existing):
                # 记录冲突
                self._conflict_graph.setdefault(rule.name, set()).add(existing.name)
                self._conflict_graph.setdefault(existing.name, set()).add(rule.name)
                logger.warning(
                    "Rule conflict detected: '%s' (domain=%s) vs '%s' (domain=%s). "
                    "Overlapping pattern may cause misclassification. "
                    "Priority: %d vs %d",
                    rule.name, rule.domain, existing.name, existing.domain,
                    rule.priority, existing.priority
                )
        self._rules.append(rule)
        self._rules.sort(key=lambda r: -r.priority)
    
    def _has_overlap(self, a: IntentRule, b: IntentRule) -> bool:
        """判断两条规则是否可能在同一输入上同时匹配。"""
        if a.domain and b.domain and a.domain != b.domain:
            return False  # 不同领域不冲突
        # 更严格的检测：生成测试用例，检查是否同时匹配
        return True  # 简化：同领域即视为潜在冲突
    
    def classify(self, text: str, context_domain: Optional[str] = None) -> List[IntentMatch]:
        """
        分类时，先按 domain 过滤，再按优先级排序，最后返回所有匹配（不单选）。
        如果有多条匹配，标记为歧义，触发澄清。
        """
        matches = []
        for rule in self._rules:
            if context_domain and rule.domain and rule.domain != context_domain:
                continue  # 领域不匹配，跳过
            if rule.matches(text):
                matches.append(IntentMatch(rule=rule, confidence=rule.base_confidence))
        
        # 冲突检测：如果最高优先级的匹配有冲突，且低优先级的也匹配了 → 歧义
        if matches:
            top = matches[0]
            conflicting = [m for m in matches[1:] if m.rule.name in self._conflict_graph.get(top.rule.name, set())]
            if conflicting:
                # 歧义：需要澄清
                return matches  # 返回所有匹配，让歧义检测器处理
        
        return matches[:1]  # 单选最高优先级
```

**CI 集成**：在 CI 中运行冲突检测脚本，输出规则冲突报告：

```bash
python -m core.agent.intent_parser --check-conflicts
# 输出：
# CONFLICT: scan_memory (domain=reverse_engineering, priority=100) 
#        vs scan_medical (domain=medical, priority=90)
#        Overlap: "扫描" matches both
# SUGGEST: Add domain context or increase pattern specificity
```

**修复优先级**：P1（高）—— 规则膨胀是必然趋势，没有冲突检测机制不可持续。

---

## 问题 4：蓝图的粒度 — 原子操作 vs 嵌套子蓝图

### 现状分析

```python
# blueprints.py:26-33
@dataclass(frozen=True)
class Blueprint:
    id: str
    description: str
    sequence: List[str]          # 工具名列表，按序执行
    gate: str                    # 准入条件
    latency_budget_ms: int
    requires_llm: bool = False
    fallback_id: Optional[str] = None
```

**问题诊断：**

1. **sequence 是扁平的 `List[str]`**，每个元素是工具名。没有子蓝图嵌套。
2. **工具粒度不均匀**：`"pcr_evaluate"` 是一个原子操作，但 `"intent_parser_full_pipeline"` 本身就是一个完整的 pipeline（包含预处理、实体提取、规则分类、歧义检测等）。
3. **边界模糊**：蓝图到底是"策略级"（选择执行路径）还是"任务级"（定义具体步骤）？

### 反事实推演

- 场景：用户请求"扫描进程 A 的内存，找到基址，然后修改血量值"。
- 现有蓝图：
  - `RULE_FAST_PATH`：只包含 `"pcr_evaluate"` + `"intent_parser_full_pipeline"`（一次完整解析）
  - `LLM_DEEP`：包含多个步骤，但没有嵌套
- 问题：这个请求需要"扫描 → 读取 → 修改"三步，但每个蓝图只定义了一个高层策略。实际执行时，Executor 需要把蓝图展开为多个工具调用，但蓝图本身没有定义这种展开逻辑。
- **结果**：蓝图变成了"标签"而非"计划"，Executor 承担了过多的编排逻辑。

### 修复方案：定义蓝图边界 + 引入子蓝图

```python
# 蓝图的边界定义：蓝图是"策略选择器"，不是"执行计划"
# 它的职责是：决定走哪条执行路径，而不是定义每一步的细节

# 方案 A：保持当前粒度（策略级），但显式声明边界
@dataclass(frozen=True)
class Blueprint:
    id: str
    description: str
    strategy: str  # 策略描述，而非工具序列
    # sequence 改为可选的"示例步骤"，而非强制执行序列
    example_sequence: List[str] = field(default_factory=list)  # 参考实现，可 override
    gate: str
    latency_budget_ms: int
    requires_llm: bool = False
    fallback_id: Optional[str] = None
    # 新增：子蓝图（用于复杂策略的分解）
    sub_blueprints: List[str] = field(default_factory=list)  # 子蓝图 ID 列表
    is_composite: bool = False  # 是否是组合蓝图

# 方案 B：引入子蓝图（保持 frozen，但允许组合）
@dataclass(frozen=True)
class Blueprint:
    id: str
    description: str
    # 步骤可以是工具名或子蓝图 ID
    steps: List[Union[str, "Blueprint"]]  # 支持嵌套
    gate: str
    latency_budget_ms: int
    requires_llm: bool = False
    fallback_id: Optional[str] = None
    max_nesting_depth: int = 3  # 限制嵌套深度，防止无限递归

# 限制：子蓝图必须是已注册的，防止循环依赖
class BlueprintLibrary:
    def validate(self) -> None:
        # 1. 检查循环依赖
        # 2. 检查所有工具名已注册
        # 3. 检查嵌套深度不超过 max_nesting_depth
        pass
```

**推荐**：方案 A（策略级）+ 方案 B（子蓝图）的组合。当前系统使用方案 A 的语义（策略选择），但代码中 `sequence` 的名字暗示了方案 B（执行计划）。**建议重命名 `sequence` 为 `strategy_steps` 并添加文档说明其边界**。

**修复优先级**：P2（中）—— 不影响当前功能，但影响长期可维护性。

---

## 问题 5：同步版本的 RLock — 分布式扩展

### 现状分析

```python
# agent_service.py:65
self._lock = threading.RLock()
```

**问题诊断：**

1. `threading.RLock` 是**进程内锁**，只在当前 Python 进程内有效。
2. 如果服务层水平扩展（多进程 / 多节点），每个进程有自己的锁，**锁失效**。
3. 当前 `SessionManager` 使用内存 Dict（`self._sessions`），如果多进程，每个进程的内存是独立的，会话数据不一致。

### 反事实推演

- 部署：使用 Gunicorn 启动 4 个 worker 进程。
- 用户 A 的会话在 worker-1 中创建。
- 用户 A 的第二次请求被路由到 worker-2。
- 结果：worker-2 中没有用户 A 的会话数据，`get_session` 返回 `None`，系统判定会话过期。
- **用户困惑："为什么每次刷新页面会话都丢失？"**

### 修复方案：设计分布式锁接口（提前预留）

```python
from abc import ABC, abstractmethod
from typing import Optional

class DistributedLock(ABC):
    """
    分布式锁抽象接口。
    
    当前实现：threading.RLock（单机）
    未来实现：Redis Redlock / etcd / ZooKeeper
    
    接口兼容 threading.Lock，可无缝替换。
    """
    
    @abstractmethod
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        raise NotImplementedError
    
    @abstractmethod
    def release(self) -> None:
        raise NotImplementedError
    
    @abstractmethod
    def __enter__(self):
        raise NotImplementedError
    
    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError

class ThreadingLockAdapter(DistributedLock):
    """单机版：包装 threading.RLock。"""
    
    def __init__(self):
        self._lock = threading.RLock()
    
    def acquire(self, blocking=True, timeout=-1):
        return self._lock.acquire(blocking=blocking, timeout=timeout)
    
    def release(self):
        self._lock.release()
    
    def __enter__(self):
        self._lock.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._lock.__exit__(exc_type, exc_val, exc_tb)

class RedisLockAdapter(DistributedLock):
    """分布式版：基于 Redis Redlock（未来实现）。"""
    
    def __init__(self, redis_client, lock_key: str, ttl_ms: int = 10000):
        self._redis = redis_client
        self._key = lock_key
        self._ttl_ms = ttl_ms
        self._token = None
    
    def acquire(self, blocking=True, timeout=-1):
        # Redlock 实现
        pass
    
    def release(self):
        # Lua 脚本释放锁
        pass

# 在 AgentService 中注入锁
class AgentService:
    def __init__(self, ..., lock: Optional[DistributedLock] = None):
        self._lock = lock or ThreadingLockAdapter()
```

**同时，会话存储必须外置化**：当前 `SessionManager` 的内存 Dict 不能用于多进程。必须将 `store`（Redis / PostgreSQL）作为**唯一真实数据源**，内存 Dict 只作为缓存。

**修复优先级**：P2（中）—— 当前单机部署不受影响，但需要在设计文档中明确标注为"已知限制"。

---

## 问题 6：异步版本的并发模型 — LLM 调用是否阻塞事件循环

### 现状分析

```python
# llm_providers/base.py:74
@abstractmethod
def generate(self, request: GenerateRequest) -> GenerateResult:
    """执行生成。"""
    raise NotImplementedError

# async_agent_service.py:170
# 在 async 方法中调用同步的 LLM Provider
def _llm_router_fn(self, pcr_output: Dict[str, Any]) -> str:
    res = self.llm_provider.generate(req)  # ← 同步调用！
    return res.text if res.metrics.success else ""
```

**问题诊断：**

1. `LLMProvider.generate()` 是**同步方法**（`def` 而非 `async def`）。
2. 在 `AsyncAgentService` 中，它被直接调用，没有 `await` 或 `asyncio.to_thread()` 包装。
3. 如果 LLM 是**本地模型**（如 Ollama 在本地运行 7B 模型），`generate()` 可能是 CPU 密集型（推理耗时 200ms-2s），这会**阻塞整个 asyncio 事件循环**。
4. 如果 LLM 是**远程 API**（如 OpenAI），`generate()` 内部可能使用 `requests.post()`，这是 IO 阻塞，但不会阻塞 asyncio 事件循环（除非使用 `aiohttp`）。

### 反事实推演

- 场景：AsyncAgentService 使用本地 LLM（Ollama/LM Studio）。
- 用户 A 发送请求 → 触发 LLM Fallback → `generate()` 耗时 2s。
- 在这 2s 内，用户 B 发送请求 → 事件循环被阻塞 → 用户 B 的请求无法处理。
- **结果：看似 async 的服务，实际上变成了单线程串行处理。**

### 修复方案：为 LLM Provider 增加异步接口

```python
# base.py
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """同步接口。"""
        raise NotImplementedError
    
    async def generate_async(self, request: GenerateRequest) -> GenerateResult:
        """
        异步接口。默认实现：在线程池中运行同步 generate()。
        子类可 override 以提供原生异步实现（如 aiohttp 调用 OpenAI）。
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate, request)

# openai_provider.py
class OpenAIProvider(LLMProvider):
    async def generate_async(self, request: GenerateRequest) -> GenerateResult:
        # 使用 aiohttp 原生异步调用
        async with aiohttp.ClientSession() as session:
            async with session.post(...) as resp:
                return self._parse_response(await resp.json())

# async_agent_service.py
class AsyncAgentService:
    def _llm_router_fn(self, pcr_output: Dict[str, Any]) -> str:
        # 同步版本，不需要修改
        ...
    
    async def _llm_router_fn_async(self, pcr_output: Dict[str, Any]) -> str:
        # 异步版本，使用 generate_async
        req = GenerateRequest(...)
        res = await self.llm_provider.generate_async(req)
        return res.text if res.metrics.success else ""
```

**修复优先级**：P1（高）—— 如果用户配置本地 LLM，AsyncAgentService 会阻塞事件循环。

---

## 问题 7：FSM 7 状态 — 是否必要？

### 现状分析

```
START → PARSING → ACTIONABLE/CLARIFYING → RE_PARSING → ... → EXPIRED/CLOSED
```

状态列表：START, PARSING, ACTIONABLE, CLARIFYING, RE_PARSING, EXPIRED, CLOSED（7 个）

**问题诊断：**

1. **START 和 PARSING 是否可以合并？** 
   - START：用户刚发消息，系统尚未开始处理。
   - PARSING：系统正在处理（PCR / Intent Parser 运行中）。
   - **不能合并**：START 是等待状态，PARSING 是执行状态。前端需要区分"已发送，等待响应"和"正在解析"。

2. **RE_PARSING 和 PARSING 是否可以合并？**
   - RE_PARSING：收到澄清回复后，重新解析。
   - PARSING：首次解析。
   - **可以合并？** 从执行角度，两者都是"解析中"，但从业务角度，RE_PARSING 意味着用户已经提供了澄清，系统应该展示"已收到澄清，重新分析"。如果合并，前端无法区分首次解析和重新解析，用户体验不同。
   - **建议保留**：但可以在 trace_log 中简化，不暴露给前端。

3. **EXPIRED 和 CLOSED 是否可以合并？**
   - EXPIRED：澄清超时，系统使用默认策略继续。
   - CLOSED：用户主动关闭会话或会话 TTL 到期。
   - **不能合并**：EXPIRED 是业务状态（继续执行），CLOSED 是生命周期状态（终止）。

### 验证：7 个状态在真实对话中是否都会出现？

| 状态 | 出现场景 | 频率 |
|------|---------|------|
| START | 每轮对话开始 | 100% |
| PARSING | 每轮对话处理中 | 100% |
| ACTIONABLE | 解析无歧义 | ~80% |
| CLARIFYING | 解析有歧义 | ~15% |
| RE_PARSING | 澄清后重新解析 | ~10% |
| EXPIRED | 澄清超时 | ~2% |
| CLOSED | 会话结束 | 100%（最终） |

**结论：7 个状态都是必要的**，但可以将内部状态（PARSING, RE_PARSING）对外暴露为统一的"processing"状态，减少前端的复杂度。

### 修复方案：状态分层（内部状态 vs 外部状态）

```python
class ClarificationState:
    # 内部状态（7 个）
    START = "START"
    PARSING = "PARSING"
    ACTIONABLE = "ACTIONABLE"
    CLARIFYING = "CLARIFYING"
    RE_PARSING = "RE_PARSING"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    
    # 外部状态（映射到前端展示）
    EXTERNAL_STATE_MAP = {
        START: "idle",
        PARSING: "processing",
        ACTIONABLE: "idle",
        CLARIFYING: "clarifying",
        RE_PARSING: "processing",  # 对外统一为 processing
        EXPIRED: "idle",
        CLOSED: "closed",
    }
    
    @classmethod
    def to_external(cls, internal_state: str) -> str:
        return cls.EXTERNAL_STATE_MAP.get(internal_state, "unknown")
```

**修复优先级**：P3（低）—— 当前设计是合理的，但可以增加外部状态映射，简化前端集成。

---

## 问题 8：WebSocket 事件类型 — 扩展性

### 现状分析

```python
# websocket_events.py:28-36
class EventType:
    """事件类型常量。"""
    INTENT_RESULT = "intent_result"
    CLARIFICATION = "clarification"
    PROGRESS = "progress"
    TASKGRAPH_UPDATE = "taskgraph_update"
    ERROR = "error"
    STATE_CHANGE = "state_change"
    PONG = "pong"
```

**问题诊断：**

1. 这是**类常量**（class constants），不是 `Enum`。新增类型需要修改这个类。
2. 事件类型是**硬编码**的，没有注册机制。如果第三方想扩展自定义事件（如 `CUSTOM_ANALYTICS`），需要修改核心代码。
3. 前端事件解析通常是 `switch(event_type)` 或 `if/elif` 链，新增类型时容易遗漏处理。

### 修复方案：事件注册表 + 向后兼容

```python
class EventTypeRegistry:
    """
    事件类型注册表，支持第三方扩展。
    
    核心事件预注册，第三方可通过 register() 添加自定义事件。
    未知事件类型不会导致系统崩溃，而是转发给前端处理。
    """
    
    _CORE_EVENTS = {
        "intent_result": {"version": "1.0", "required_fields": ["expectation"]},
        "clarification": {"version": "1.0", "required_fields": ["clarification_id", "ui_schema"]},
        "progress": {"version": "1.0", "required_fields": ["stage", "status"]},
        "taskgraph_update": {"version": "1.0", "required_fields": ["task_graph_id"]},
        "error": {"version": "1.0", "required_fields": ["code", "message"]},
        "state_change": {"version": "1.0", "required_fields": ["new_state"]},
        "pong": {"version": "1.0", "required_fields": []},
    }
    
    _custom_events: Dict[str, Dict] = {}
    
    @classmethod
    def register(cls, event_type: str, schema: Dict[str, Any]) -> None:
        """注册自定义事件类型。"""
        if event_type in cls._CORE_EVENTS:
            raise ValueError(f"Cannot override core event type: {event_type}")
        cls._custom_events[event_type] = schema
        logger.info("Registered custom event type: %s", event_type)
    
    @classmethod
    def is_valid(cls, event_type: str) -> bool:
        return event_type in cls._CORE_EVENTS or event_type in cls._custom_events
    
    @classmethod
    def validate_payload(cls, event_type: str, payload: Dict) -> List[str]:
        """验证 payload 是否包含必需字段。返回错误列表（空列表表示有效）。"""
        schema = cls._CORE_EVENTS.get(event_type) or cls._custom_events.get(event_type)
        if not schema:
            return [f"Unknown event type: {event_type}"]
        errors = []
        for field in schema.get("required_fields", []):
            if field not in payload:
                errors.append(f"Missing required field: {field}")
        return errors

# EventBuilder 使用注册表验证
class EventBuilder:
    @staticmethod
    def build(event_type: str, session_id: str, payload: Dict) -> WebSocketEvent:
        errors = EventTypeRegistry.validate_payload(event_type, payload)
        if errors:
            raise ValueError(f"Invalid event payload: {errors}")
        return WebSocketEvent(event_type=event_type, session_id=session_id, payload=payload)
```

**修复优先级**：P2（中）—— 不影响当前功能，但限制第三方扩展。

---

## 问题 9：MCP 是否为必需层？

### 现状分析

```python
# mcp/client.py:26-44
try:
    from mcp.client import Client
    HAS_MCP = True
except ImportError:
    ...
    HAS_MCP = False
    Client = None
```

**问题诊断：**

1. **核心代码不依赖 MCP**：`HAS_MCP` 为 `False` 时，所有 MCP 功能被优雅降级，核心引擎（PCR + Intent Parser）完全不受影响。
2. **没有 MCP 的 fallback 工具**：如果系统依赖 MCP 工具（如外部代码执行服务），但 MCP 不可用，系统会静默跳过这些工具，可能导致功能缺失。
3. **部署文档没有明确标注**：设计文档说 MCP 是可选层，但没有说明"哪些功能在 MCP 不可用时不可用"。

### 验证：核心能力是否依赖 MCP

| 能力 | 依赖 MCP？ | MCP 作用 |
|------|-----------|---------|
| 意图识别（PCR + Intent Parser） | ❌ 否 | 核心引擎，完全独立 |
| 多轮澄清（FSM + UI Schema） | ❌ 否 | 前端协议层，完全独立 |
| 任务图可视化 | ❌ 否 | 前端协议层，完全独立 |
| 会话管理 | ❌ 否 | 服务层，完全独立 |
| 限流/审计 | ❌ 否 | 复用现有基础设施 |
| 外部工具调用（如执行代码、查数据库） | ⚠️ 部分 | MCP Client 可以消费外部工具，但核心工具（scan_memory 等）是内置的 |
| Claude Desktop 集成 | ✅ 是 | 必须通过 MCP Server 暴露 |

**结论：MCP 是"锦上添花"而非"必需"**。核心能力（意图识别、澄清、会话管理）完全不依赖 MCP。MCP 只在两种场景下使用：
1. 作为 MCP Server 被外部消费（Claude Desktop 集成）
2. 作为 MCP Client 消费外部工具（扩展系统能力）

### 修复方案：明确标注 MCP 依赖边界

在文档中增加：

```markdown
## MCP 依赖声明

### 核心能力（无 MCP 也可完整运行）
- ✅ 意图识别（PCR + Intent Parser）
- ✅ 多轮澄清（Clarification FSM）
- ✅ 任务图可视化（TaskGraph）
- ✅ 会话管理（Session Manager）
- ✅ 限流与审计（Rate Limiter / Audit Logger）
- ✅ 内置工具（scan_memory, read_memory, write_memory 等 7 个）

### 扩展能力（需要 MCP）
- ⚠️ 外部工具调用（如数据库查询、代码执行）：需要 MCP Client 连接外部 Server
- ⚠️ Claude Desktop 集成：需要 MCP Server 暴露工具

### 部署建议
- **最小部署**：`pip install cognitive-router`（无需 MCP，无外部依赖）
- **完整部署**：`pip install cognitive-router[mcp]`（包含 MCP 协议层）
- **Claude Desktop 集成**：`pip install cognitive-router[server,mcp]` + Claude Desktop 配置
```

**修复优先级**：P3（低）—— 当前代码已正确处理，只需文档补充。

---

## 总结与修复优先级

| 问题 | 优先级 | 影响 | 修复工作量 | 代码变更 |
|------|--------|------|-----------|---------|
| 1. PCR 决策闭环 | **P0** | 高：PCR 价值减半 | 中等 | 是：增加 feedback loop 和阈值自适应 |
| 2. 冷启动策略 | **P1** | 高：专家用户流失 | 小 | 是：增加 user_type_hint 和首轮探测 |
| 3. 规则冲突检测 | **P1** | 高：规则膨胀不可持续 | 中等 | 是：增加冲突检测机制 |
| 4. 蓝图粒度 | **P2** | 中：影响长期可维护性 | 小 | 是：重命名 + 文档 |
| 5. RLock 分布式 | **P2** | 中：限制水平扩展 | 中等 | 是：增加分布式锁接口 |
| 6. 异步 LLM 阻塞 | **P1** | 高：本地 LLM 阻塞事件循环 | 小 | 是：增加 `generate_async` 接口 |
| 7. FSM 7 状态 | **P3** | 低：设计合理 | 小 | 否：仅增加外部状态映射（可选） |
| 8. WebSocket 扩展 | **P2** | 中：限制第三方扩展 | 小 | 是：增加事件注册表 |
| 9. MCP 依赖声明 | **P3** | 低：代码已处理 | 小 | 否：仅文档补充 |

**建议修复顺序**：P0 → P1（冷启动、异步 LLM） → P1（规则冲突） → P2（蓝图、分布式锁、事件扩展） → P3（FSM、MCP 文档）。
