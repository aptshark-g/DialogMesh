# DESIGN_COGNITIVE_SCHEDULER.md — 认知调度器

> 版本: v1.0 | 日期: 2026-07-12
>
> Cognitive Scheduler 不是 Executor，不是 Worker Pool。
> 它是决定"谁、什么时候、跑多久、以什么优先级"的调度层。
> 不负责思考——只负责调度思考的时机。

---

## 目录

1. [定位：调度而非执行](#1-定位调度而非执行)
2. [三条线架构](#2-三条线架构)
3. [核心组件](#3-核心组件)
4. [Task 抽象](#4-task-抽象)
5. [Policy：快慢系统的归宿](#5-policy快慢系统的归宿)
6. [Worker：不知道自己在跑什么](#6-worker不知道自己在跑什么)
7. [Monitor + Runtime Advisor 钩子](#7-monitor--runtime-advisor-钩子)
8. [Schema 定义](#8-schema-定义)
9. [集成面：与已有 v4 模块的关系](#9-集成面与已有-v4-模块的关系)
10. [实现计划](#10-实现计划)

---

## 1. 定位：调度而非执行

### 1.1 已有的：各自为政的调度

当前每个模块都有自己的"运行时"：

| 模块 | 自管调度 |
|:---|:---|
| HypothesisPipeline | `start_background()` + `decay_interval_sec` |
| DecayResolveEngine | 周期 decay |
| GraphTierManager | 周期 GC |
| DistillationEngine | 按需扫描 |
| MultiTierPipeline | 内部三级级联 |

这些调度互不感知。没有统一的"现在应该先跑什么"的决策层。

### 1.2 应该的：统一的 Cognitive Scheduler

```
Task 队列
    │
    ▼
Cognitive Scheduler
    ├── Policy: 决定哪个 Task 优先
    ├── Worker: 分配执行
    ├── Monitor: 跟踪状态
    └── Advisor: 洞察 + 建议 (预留)
```

Scheduler 不执行任何认知任务。它只决定**调度什么、什么时候**。

### 1.3 不是 Runtime——是 Cognitive OS

Runtime 暗示"执行引擎"（JVM、Python Interpreter）。
Cognitive Scheduler 更像操作系统的进程调度器：
决定什么时候运行什么、优先级、取消、重试、资源预算。

---

## 2. 三条线架构

v4 完成后自然浮现的三层结构：

```
Cognitive Scheduler (调度层)
    ├── Policy (Fast/Async/Slow/Deep)
    ├── Queue + Dispatcher
    ├── Monitor
    └── Runtime Advisor (预留)

    │ 调度
    ▼
Cognitive Pipeline (认知流水线)
    Event → Observation → Hypothesis → Knowledge → Skill

    │ 消费
    ▼
Context Engine (内容层)
    ├── Code Context Graph
    ├── Document Context Graph
    └── External Knowledge Context
```

- **Scheduler** 决定"什么时候处理"
- **Pipeline** 执行"怎么处理"
- **Context Engine** 提供"处理什么内容"

---

## 3. 核心组件

```
                  ┌─────────────────────────┐
                  │    Cognitive Scheduler   │
                  │                          │
  Task Queue ──→  │  Policy ──→ Worker Pool  │
                  │    │                     │
                  │    ├── Fast (主请求)      │
                  │    ├── Async (观察)       │
                  │    ├── Slow (假设)        │
                  │    └── Deep (蒸馏)        │
                  │                          │
                  │  Monitor ←── Stats       │
                  │  Advisor Hook ←──预留     │
                  └─────────────────────────┘
```

| 组件 | 职责 |
|:---|:---|
| **Task Queue** | 优先级队列，按 Policy 排序 |
| **Policy** | 决定 Task 的优先级和执行时机 |
| **Worker Pool** | 线程池，执行 `Task.execute()` |
| **Monitor** | 收集各 Task 的执行统计 |
| **Runtime Advisor** | (预留) 根据 Monitor 数据建议调度策略调整 |

---

## 4. Task 抽象

### 4.1 为什么要有 Task

Worker 不应该知道自己在跑 Observation Compiler 还是 Hypothesis Engine。
Worker 只知道 `Task.execute()`。

### 4.2 Task 接口

```python
class Task(ABC):
    task_id: str
    priority: int = 0            # 越高越优先
    created_at: float
    status: str = "pending"      # pending | running | done | failed | cancelled
    max_retries: int = 3
    timeout_ms: int = 30000

    @abstractmethod
    def execute(self) -> Any: ...

    def on_complete(self, result: Any) -> None: ...
    def on_failure(self, error: Exception) -> None: ...
    def on_cancel(self) -> None: ...
```

### 4.3 四类 Task

| Task | 对应模块 | Policy 路径 | 典型耗时 |
|:---|:---|:---|:---|
| `ObservationTask` | Observation Compiler | Fast / Async | 5-50ms |
| `HypothesisTask` | Hypothesis Engine (Match+Vote) | Async / Slow | 10-500ms |
| `KnowledgeTask` | Hypothesis Engine (Decay+Resolve) | Slow / Deep | 100ms-2s |
| `SkillTask` | DistillationEngine + Evaluation | Deep | 1-10s |

```python
class ObservationTask(Task):
    def __init__(self, event, compiler):
        super().__init__(priority=8)
        self._event = event
        self._compiler = compiler

    def execute(self):
        return self._compiler.compile(self._event)

class HypothesisTask(Task):
    def __init__(self, evidence, engine):
        super().__init__(priority=5)
        self._evidence = evidence
        self._engine = engine

    def execute(self):
        return self._engine.submit(self._evidence)
```

---

## 5. Policy：快慢系统的归宿

### 5.1 之前的快慢系统

MultiTierPipeline 的 8 个 tiered wrapper + TierHeatBridge 已经实现了"同一输入的多级精度处理"。
但**精度 ≠ 调度**。

Policy 做的是：按照系统负载和 Task 优先级，决定哪个 Task 进入 Worker。

### 5.2 SchedulerPolicy 接口

```python
class SchedulerPolicy(ABC):
    @abstractmethod
    def select_task(self, queue: List[Task]) -> Optional[Task]: ...
    @abstractmethod
    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]: ...
    @abstractmethod
    def should_delay(self, task: Task) -> bool: ...
    @abstractmethod
    def should_merge(self, a: Task, b: Task) -> bool: ...

class PriorityFIFOPolicy(SchedulerPolicy):
    """默认: 优先级高者先出, 同优先级 FIFO."""
    def select_task(self, queue):
        return max(queue, key=lambda t: (t.priority, -t.created_at)) if queue else None

    def assign_worker(self, task, pool):
        return pool.next_idle()

    def should_delay(self, task):
        return False

    def should_merge(self, a, b):
        return False
```

### 5.3 Policy 与 MultiTierPipeline 的关系

MultiTierPipeline 的 rule→embedding→LLM 级联是**执行层的精度策略**，不是调度策略。
Policy 决定"Observation 队列太长了，暂停 Deep，把 Worker 分配给 Async"。
这两层互不干扰——以后换 Policy 完全不影响 MultiTierPipeline。

---

## 6. Worker：不知道自己在跑什么

```python
class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.status = "idle"
        self.current_task: Optional[Task] = None
        self.stats = WorkerStats()

    def run(self, task: Task) -> Any:
        self.status = "running"
        self.current_task = task
        try:
            result = task.execute()
            task.on_complete(result)
            self.stats.success += 1
            return result
        except Exception as e:
            task.on_failure(e)
            self.stats.failures += 1
            if task.max_retries > 0:
                task.max_retries -= 1
                task.status = "pending"
            raise
        finally:
            self.status = "idle"
            self.current_task = None

class WorkerPool:
    def __init__(self, size: int = 4):
        self._workers = [Worker(f"w{i}") for i in range(size)]
        self._idle = list(self._workers)

    def next_idle(self) -> Optional[Worker]:
        return self._idle.pop(0) if self._idle else None

    def release(self, worker: Worker):
        self._idle.append(worker)

    def stats(self) -> dict:
        return {
            "total": len(self._workers),
            "idle": len(self._idle),
            "success": sum(w.stats.success for w in self._workers),
            "failures": sum(w.stats.failures for w in self._workers),
        }
```

---

## 7. Monitor + Runtime Advisor 钩子

### 7.1 Monitor

```python
class SchedulerMonitor:
    def __init__(self):
        self._queue_snapshots: List[QueueSnapshot] = []
        self._task_stats: Dict[str, TaskStats] = {}

    def snapshot(self, scheduler: CognitiveScheduler) -> QueueSnapshot:
        snap = QueueSnapshot(
            pending=len(scheduler.queue),
            running=len([w for w in scheduler.pool._workers if w.status == "running"]),
            by_type={"observation": 0, "hypothesis": 0, "knowledge": 0, "skill": 0},
        )
        for t in scheduler.queue:
            if "observation" in t.task_id: snap.by_type["observation"] += 1
            elif "hypothesis" in t.task_id: snap.by_type["hypothesis"] += 1
            elif "knowledge" in t.task_id: snap.by_type["knowledge"] += 1
            elif "skill" in t.task_id: snap.by_type["skill"] += 1
        self._queue_snapshots.append(snap)
        return snap

    def suggest(self) -> List[str]:
        """Generate insights for Runtime Advisor."""
        suggestions = []
        if len(self._queue_snapshots) >= 3:
            last_3 = self._queue_snapshots[-3:]
            obs_growth = last_3[-1].by_type["observation"] - last_3[0].by_type["observation"]
            if obs_growth > 50:
                suggestions.append("Observation queue growing: consider more Async workers")
            hyp_growth = last_3[-1].by_type["hypothesis"] - last_3[0].by_type["hypothesis"]
            if hyp_growth > 20:
                suggestions.append("Hypothesis backlog: consider pausing Deep tasks")
        return suggestions
```

### 7.2 Runtime Advisor 钩子

```python
class RuntimeAdvisor:
    """Future: policy self-adjustment based on Monitor data."""
    def __init__(self, monitor: SchedulerMonitor):
        self._monitor = monitor

    def recommend(self) -> List[AdvisorSignal]:
        hints = self._monitor.suggest()
        return [AdvisorSignal(hint=h, severity="info") for h in hints]

@dataclass
class AdvisorSignal:
    hint: str
    severity: str  # "info" | "warning" | "critical"
```

---

## 8. Schema 定义

### 8.1 CognitiveScheduler

```python
class CognitiveScheduler:
    def __init__(self, policy: SchedulerPolicy = None,
                 pool: WorkerPool = None,
                 monitor: SchedulerMonitor = None):
        self.policy = policy or PriorityFIFOPolicy()
        self.pool = pool or WorkerPool(size=4)
        self.monitor = monitor or SchedulerMonitor()
        self.queue: List[Task] = []
        self._running = False

    def submit(self, task: Task) -> None:
        self.queue.append(task)

    def tick(self) -> List[Any]:
        """Single scheduling cycle. Returns results of completed tasks."""
        results = []
        task = self.policy.select_task(self.queue)
        if not task: return results

        if self.policy.should_delay(task):
            return results  # put back in queue

        worker = self.policy.assign_worker(task, self.pool)
        if not worker: return results  # no idle worker

        self.queue.remove(task)
        try:
            result = worker.run(task)
            results.append(result)
        except Exception:
            pass  # failure logged in worker
        finally:
            self.pool.release(worker)

        self.monitor.snapshot(self)
        return results

    def run_loop(self, max_ticks: int = -1, interval_ms: int = 100):
        self._running = True
        ticks = 0
        while self._running and (max_ticks < 0 or ticks < max_ticks):
            self.tick()
            ticks += 1
            time.sleep(interval_ms / 1000.0)

    def stop(self):
        self._running = False

    def stats(self) -> dict:
        return {
            "queue_size": len(self.queue),
            "workers": self.pool.stats(),
            "monitor": {
                "snapshots": len(self.monitor._queue_snapshots),
                "suggestions": self.monitor.suggest(),
            },
        }
```

### 8.2 参数纳入 ParameterRegistry

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `scheduler.default_workers` | 4 | Worker Pool 大小 |
| `scheduler.tick_interval_ms` | 100 | 调度循环间隔 |
| `scheduler.max_task_timeout_ms` | 30000 | Task 默认超时 |
| `scheduler.queue_max_size` | 1000 | 队列最大容量 |
| `scheduler.advisor.obs_queue_warn` | 50 | Observation 队列增长警告阈值 |
| `scheduler.advisor.hyp_queue_warn` | 20 | Hypothesis 队列增长警告阈值 |

---

## 9. 集成面

| 现有模块 | 集成方式 |
|:---|:---|
| Observation Compiler | 包装为 ObservationTask |
| Hypothesis Engine (MatchVote) | 包装为 HypothesisTask |
| Hypothesis Engine (DecayResolve) | 包装为 KnowledgeTask |
| DistillationEngine | 包装为 SkillTask |
| MultiTierPipeline | 在 Task.execute() 内部调用（是执行策略，不是调度策略） |
| TierHeatBridge | Monitor snapshot → GC 热度调整 |
| ParameterRegistry | 所有调度参数统一管理 |
| EventBus | Task 提交的入口 |

---

## 10. 实现计划

| Phase | 内容 | 依赖 |
|:---|:---|:---|
| Phase 1 | Task + Worker + WorkerPool Schema | 无 |
| Phase 2 | CognitiveScheduler + PriorityFIFOPolicy | Phase 1 |
| Phase 3 | ObservationTask / HypothesisTask / KnowledgeTask / SkillTask | Phase 1-2, 各认知模块 |
| Phase 4 | SchedulerMonitor + Advisor 钩子 | Phase 2 |
| Phase 5 | ParameterRegistry 集成 + 参数锚定 | Phase 2, ParameterRegistry |
| Phase 6 | TierHeatBridge 联动 (Monitor → GC) | Phase 4, TierHeatBridge |

---

> Cognitive Scheduler 不负责思考。
> 它负责决定谁、什么时候、以什么优先级思考。
> 它是分配认知时序的系统，不是执行认知任务的系统。
