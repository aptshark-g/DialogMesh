# Literature Cortex v5.3 设计方案：算力比例协调器

> **文档编号:** LC-DESIGN-v5.3
> **版本:** v5.3-DRAFT
> **状态:** 📋 DRAFT
> **完成度:** 100%（设计）/ 0%（实现）
> **日期:** 2026-06-20
> **依赖:** v5.2 元认知双核心 + 发散层 v0.1
> **注册表:** 参见 `DESIGN-REGISTRY.md`
> **核心目标:** 将元认知仲裁从 binary 触发升级为连续比例控制

---

## 1. 问题陈述

### 1.1 v5.2 仲裁层的 binary 局限

v5.2 的 `MetaCognitiveArbiter.process_node()` 本质是一个状态机：

```
收敛运行中 → 停滞检测触发 → 暂停收敛 → 调用发散 → 发散结束 → 恢复收敛
```

**问题：** 协调器是跷跷板——同一时间只有一个网络在运行。当收敛陷入局部最优时，系统"切换"到发散；当发散预算耗尽时，系统"切换"回收敛。这种 binary 模式导致：

1. **边界任务空转**：某些任务既需要结构验证又需要跨域联想，binary 模式下必须串行，无法并行
2. **负载峰值集中**：发散触发后，短期内算力全部涌向发散层，收敛层空转
3. **无渐进式融合**：收敛层的演绎结果无法实时注入发散层的假设生成，反之亦然

### 1.2 比例控制的本质

用户提出的"比例控制"不是简单的"资源分配"，而是**认知流的连续调制**：

> 人脑不会在"专注验证"和"胡思乱想"之间硬切换。而是同时运行两条轨道，根据任务需求动态调整它们的相对强度。

**核心洞察：** 收敛和发散不是互斥的 CPU 进程，而是并行运行的神经网络。元认知层的作用不是"开关"，而是"调光器"。

---

## 2. 核心架构：三因素比例模型

### 2.1 三轨道制（修订 v5.2 双层为三层）

| 轨道 | 职能 | 资源特征 | 典型耗时 |
|------|------|---------|---------|
| **收敛轨** (Convergent) | 分类、验证、规则校验、正向演绎 | CPU 密集型，确定性 | 毫秒-秒级 |
| **发散轨** (Divergent) | 跨域类比、假设生成、约束调整、反事实破坏 | LLM/IO 密集型，概率性 | 秒-分钟级 |
| **协调轨** (Coordinative) | 比例分配、质量审查、概念健康、系统维护 | 状态维护，低算力 | 毫秒级 |

**关键修订：** v5.2 将协调层放在"双网络之上"，比例控制将其改为"渗透层"——协调轨不替代收敛/发散，而是在两者之间实时调制算力比例。

### 2.2 比例控制核心公式

```python
class ProportionController:
    """算力比例控制器 —— 将 binary 触发升级为连续调制。"""
    
    def __init__(self):
        # 三因素权重
        self.w_stage = 0.40      # 任务阶段因子
        self.w_confidence = 0.35  # 置信度反馈因子
        self.w_budget = 0.25      # 资源预算硬上限
    
    def compute_ratio(self, ctx: ArbitrationContext) -> ConvergeDivergeRatio:
        """计算收敛/发散比例。
        
        返回值：(converge_ratio, diverge_ratio)，满足 converge + diverge = 1.0
        """
        # Factor 1: 任务阶段
        stage_ratio = self._stage_factor(ctx.phase)
        
        # Factor 2: 置信度反馈
        conf_ratio = self._confidence_factor(ctx.history)
        
        # Factor 3: 资源预算
        budget_ratio = self._budget_factor(ctx.budget_remaining, ctx.budget_total)
        
        # 加权融合
        converge = (self.w_stage * stage_ratio.converge +
                   self.w_confidence * conf_ratio.converge +
                   self.w_budget * budget_ratio.converge)
        
        diverge = 1.0 - converge
        
        # 硬边界：不允许极端比例（保留最低 5% 给任一轨道）
        converge = clamp(converge, 0.05, 0.95)
        diverge = 1.0 - converge
        
        return ConvergeDivergeRatio(converge=converge, diverge=diverge)
```

### 2.3 三因素详解

#### Factor 1: 任务阶段因子 (Task Stage Factor)

| 阶段 | converge | diverge | 说明 |
|------|----------|---------|------|
| Phase A 搜索 | 0.20 | 0.80 | 初始化阶段，需要大量探索 |
| Phase B 评分 | 0.70 | 0.30 | 收敛验证为主，发散用于边界case |
| Phase C 深读 | 0.50 | 0.50 | 深度阅读需要双线并行 |
| Phase D 局限 | 0.30 | 0.70 | 找gap需要发散 |
| Phase E 合成 | 0.80 | 0.20 | 整合阶段，收敛为主 |
| 用户 query "explore" | 0.10 | 0.90 | 强制发散 |
| 用户 query "confirm" | 0.90 | 0.10 | 强制收敛 |

#### Factor 2: 置信度反馈因子 (Confidence Feedback Factor)

基于 v5.2 `ValidationFeedbackLoop` 的历史数据：

```python
def _confidence_factor(self, history: DirectionHistory) -> Ratio:
    """基于验证历史动态调整比例。
    
    逻辑：
    - 如果最近 5 次发散假设验证通过率高 (>0.6)：提高发散比例（说明发散有价值）
    - 如果最近 5 次收敛演绎停滞频繁：提高发散比例（说明收敛走到头了）
    - 如果发散假设连续失败：提高收敛比例（说明发散在空转）
    """
    divergent_pass_rate = history.divergent_pass_rate(window=5)
    convergent_stagnation_rate = history.convergent_stagnation_rate(window=5)
    
    # 发散有效 → 给发散更多算力
    if divergent_pass_rate > 0.6:
        return Ratio(converge=0.3, diverge=0.7)
    
    # 收敛停滞 → 给发散更多算力
    if convergent_stagnation_rate > 0.5:
        return Ratio(converge=0.4, diverge=0.6)
    
    # 发散无效 → 回收算力给收敛
    if divergent_pass_rate < 0.2:
        return Ratio(converge=0.8, diverge=0.2)
    
    # 默认平衡
    return Ratio(converge=0.5, diverge=0.5)
```

#### Factor 3: 资源预算硬上限 (Resource Budget Factor)

```python
def _budget_factor(self, remaining: int, total: int) -> Ratio:
    """根据剩余预算调整比例。
    
    逻辑：
    - 预算充足 (>50%)：允许高发散
    - 预算紧张 (<20%)：强制高收敛，完成当前任务
    - 预算耗尽：100% 收敛，只输出已验证内容
    """
    ratio = remaining / total if total > 0 else 0
    
    if ratio > 0.5:
        return Ratio(converge=0.4, diverge=0.6)
    elif ratio > 0.2:
        return Ratio(converge=0.6, diverge=0.4)
    else:
        return Ratio(converge=0.9, diverge=0.1)
```

---

## 3. 比例控制下的双轨并行模型

### 3.1 从串行到并行

**v5.2 binary 模式：**
```
时间轴:  [====收敛====][====发散====][====收敛====]
算力:    [████████████][░░░░░░░░░░░░][████████████]
```

**v5.3 比例模式：**
```
时间轴:  [==========并行区间==========]
收敛:    [████████████████░░░░░░░░░░░░]
发散:    [░░░░░░░░░░░░░░░░████████████████]
比例:      70:30 → 50:50 → 30:70
```

### 3.2 任务队列模型

```python
class ParallelTaskQueue:
    """双轨并行任务队列。"""
    
    def __init__(self, ratio_controller: ProportionController):
        self.convergent_queue = PriorityQueue()
        self.divergent_queue = PriorityQueue()
        self.ratio_controller = ratio_controller
        self.worker_pool = ThreadPoolExecutor(max_workers=4)
    
    def dispatch(self, task: Task) -> Future:
        """根据当前比例动态调度任务。"""
        ratio = self.ratio_controller.compute_ratio(task.context)
        
        # 计算当前队列负载
        conv_load = self.convergent_queue.qsize()
        div_load = self.divergent_queue.qsize()
        total_load = conv_load + div_load + 1  # +1 for current task
        
        # 目标负载比例
        target_conv = int(total_load * ratio.converge)
        target_div = total_load - target_conv
        
        # 根据目标比例决定入队
        if conv_load < target_conv:
            self.convergent_queue.put(task)
            return self.worker_pool.submit(self._run_convergent, task)
        else:
            self.divergent_queue.put(task)
            return self.worker_pool.submit(self._run_divergent, task)
    
    def rebalance(self):
        """周期性重新平衡队列（每 5 秒或每次比例变化时）。"""
        ratio = self.ratio_controller.compute_ratio(global_context())
        
        # 如果比例变化超过阈值，迁移任务
        # ...
```

### 3.3 中间结果实时注入

比例控制的核心价值在于**双轨可以互相注入中间结果**：

```python
class CrossInjection:
    """收敛/发散中间结果实时注入。"""
    
    def on_convergent_partial(self, result: ConvergentPartial):
        """收敛层产生中间结果时，实时注入发散层。
        
        例如：收敛层验证到 depth=2 时发现 A→B 成立，
        发散层可以立即对 A→B 启动反事实破坏，不需要等收敛层全部跑完。
        """
        if result.confidence > 0.8 and result.depth >= 2:
            # 高置信度中间链路 → 值得怀疑
            divergent_task = CounterfactualTask(
                path=result.path,
                priority=result.confidence * 0.5  # 比例调制优先级
            )
            divergent_queue.put(divergent_task)
    
    def on_divergent_hypothesis(self, hypothesis: Hypothesis):
        """发散层产生假设时，实时注入收敛层验证。
        
        例如：发散层生成 A→D→C 假设，
        收敛层立即启动验证，不需要等发散层全部预算耗尽。
        """
        if hypothesis.total_value > 0.6:
            convergent_task = ValidationTask(
                hypothesis=hypothesis,
                priority=hypothesis.total_value * 0.5
            )
            convergent_queue.put(convergent_task)
```

---

## 4. 与 v5.2 元认知层的集成

### 4.1 保留 v5.2 的所有组件

比例控制不替代 v5.2 的四个组件，而是将其嵌入比例框架：

| v5.2 组件 | 在比例控制中的角色 |
|-----------|------------------|
| `AntiBloatController` | 在 diverge_ratio > 0 时生效，控制发散预算上限 |
| `ConvergenceMonitor` | 实时输入到 Factor 2（置信度反馈），影响比例动态 |
| `PerspectiveArbiter` | 在 converge_ratio > 0.5 时主导，选择验证视角 |
| `ValidationFeedbackLoop` | 持续更新 Factor 2 的历史数据 |

### 4.2 新增组件：ProportionController

```python
class MetaCognitiveArbiterV2:
    """v5.3 元认知仲裁器 —— 比例控制版本。"""
    
    def __init__(self, ...):
        # v5.2 组件保留
        self.anti_bloat = AntiBloatController(store)
        self.convergence_monitor = ConvergenceMonitor()
        self.perspective_arbiter = PerspectiveArbiter(store)
        self.feedback = ValidationFeedbackLoop(store)
        
        # v5.3 新增
        self.proportion = ProportionController()
        self.parallel_queue = ParallelTaskQueue(self.proportion)
        self.cross_injection = CrossInjection()
    
    async def process_node_v2(self, node_id: str, query_context: str = "") -> ProcessingResult:
        """比例控制下的节点处理流程。"""
        
        # Step 1: 初始化比例
        ctx = ArbitrationContext(phase=self._detect_phase(query_context))
        ratio = self.proportion.compute_ratio(ctx)
        
        # Step 2: 启动双轨并行
        convergent_future = self.parallel_queue.submit_convergent(
            ConvergentTask(node_id, query_context, weight=ratio.converge)
        )
        divergent_future = self.parallel_queue.submit_divergent(
            DivergentTask(node_id, query_context, weight=ratio.diverge)
        )
        
        # Step 3: 中间结果实时注入（通过 CrossInjection 自动触发）
        
        # Step 4: 周期性比例重调（每 5 秒）
        while not (convergent_future.done() and divergent_future.done()):
            await asyncio.sleep(5)
            new_ratio = self.proportion.compute_ratio(ctx.update(
                conv_progress=convergent_future.progress,
                div_progress=divergent_future.progress,
                history=self.feedback.get_recent(window=5)
            ))
            self.parallel_queue.adjust_ratio(new_ratio)
        
        # Step 5: 结果聚合
        conv_result = convergent_future.result()
        div_result = divergent_future.result()
        
        return AggregatedResult(
            convergent=conv_result,
            divergent=div_result,
            final_ratio=ratio,
            cross_validated=self._cross_validate(conv_result, div_result)
        )
```

---

## 5. 降级策略

### 5.1 单轨降级

如果某一层不可用（如 LLM API 超时），比例控制自动将算力全部分配给可用层：

```python
def compute_ratio(self, ctx) -> Ratio:
    base = self._compute_base_ratio(ctx)
    
    # 发散层不可用
    if not ctx.divergent_available:
        return Ratio(converge=1.0, diverge=0.0)
    
    # 收敛层不可用（罕见）
    if not ctx.convergent_available:
        return Ratio(converge=0.0, diverge=1.0)
    
    return base
```

### 5.2 资源紧张降级

当系统资源（内存/CPU）紧张时，优先保证收敛层：

```python
if ctx.memory_pressure > 0.8:
    # 内存压力 > 80%：收敛层优先（确定性，内存可控）
    return Ratio(converge=0.8, diverge=0.2)
```

---

## 6. 与现有设计的兼容性

| 版本 | 兼容性 |
|------|--------|
| v5.2 | 完全兼容。ProportionController 是 MetaCognitiveArbiter 的扩展，不修改原有接口 |
| v5.2a 对偶器 | 兼容。对偶器作为收敛层任务，受比例控制调度 |
| 发散层 v0.1 | 兼容。四层发散机制作为发散层任务，受比例控制调度 |
| v5.2f 形式化转译 | 兼容。形式化转译是收敛层的子任务 |

---

## 7. 风险与边界

| 风险 | 缓解措施 |
|------|---------|
| 比例震荡 | 比例变化速率限制：每次调整不超过 ±0.15，防止抖动 |
| 并发竞争 | 收敛/发散同时修改同一节点 → 乐观锁 + 冲突仲裁器（v5.2 已有） |
| 交叉注入死循环 | 注入深度限制：同一链路最多被交叉注入 3 次 |
| 比例计算开销 | ProportionController 本身是 O(1)，不引入额外瓶颈 |
| 调试复杂度 | 比例日志：每次比例变化记录原因（stage/confidence/budget） |

---

## 8. 一句话总结

**v5.2 的元认知层是"法官决定何时开庭"——binary 的开关。v5.3 的比例控制是"交响乐团指挥"——同时让所有乐器发声，只是动态调整谁的音量更大。**

---

*设计方案版本: v5.3-DRAFT*
*撰写日期: 2026-06-20*
*作者: 合作 (OpenClaw)*
*基于: v5.2 元认知双核心 + 用户"比例控制"需求*
