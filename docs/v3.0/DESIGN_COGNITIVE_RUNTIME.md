# DESIGN_COGNITIVE_RUNTIME v2.0

> **版本**: 2.0  
> **状态**: 设计讨论  
> **v1.0 → v2.0 变化**: StateMachine → CognitiveScheduler, Stack → WorkspaceGraph, +ExecutionTrace, +OS 类比  
> **前置**: [DESIGN_COGNITIVE_WORKSPACE](DESIGN_COGNITIVE_WORKSPACE.md)

---

## 1. v1.0 → v2.0 核心修订

| v1.0 | v2.0 | 原因 |
|------|------|------|
| 12 状态线性 Pipeline | CognitiveScheduler 优先级调度 | 真实推理不是 A→B→C，是 Retrieve ⇄ Reason ⇄ Reflect 循环 |
| Workspace Stack | WorkspaceGraph (Stack ⊂ Graph) | 并行子任务需要 Graph，Stack 只是单 child 特例 |
| Observer 包含 Workspace | Observer = CPU, Workspace = Process | OS 类比：Observer 调度资源，Workspace 执行任务 |
| 无 | ExecutionTrace | trace→replay→debug→meta-learn |

---

## 2. CognitiveScheduler（替代线性 State Machine）

### 2.1 任务定义

```python
@dataclass
class CognitiveTask:
    """一个可调度的认知操作。"""
    type: str                    # "PERCEIVE" | "RETRIEVE" | "EXPAND" | "REASON" | "REFLECT" | "VERIFY" | "COMMIT"
    priority: float = 0.5        # 0-1，高优先级先执行
    dependency: List[str] = field(default_factory=list)  # 等待这些 task ids 先完成
    retry: int = 0
    max_retry: int = 2
    timeout_ms: int = 30000
    reason: str = ""             # 为什么触发（可追踪）
```

### 2.2 调度器

```python
class CognitiveScheduler:
    """优先级调度——不是固定状态机的 A→B→C→D。"""

    def next(self, observer: Observer) -> CognitiveTask:
        ws = observer.workspace

        # 按需生成任务——由当前 workspace 状态驱动
        if ws.state == "INIT":
            return CognitiveTask("LOAD", priority=1.0, reason="startup")

        if ws.state == "LOADED":
            return CognitiveTask("PERCEIVE", priority=0.9, reason="需要视角")

        # 动态判断——没有固定顺序
        if ws.confidence < 0.3:
            if not ws.active_relations:
                return CognitiveTask("RETRIEVE", priority=0.9, reason="confidence low, need more relations")
            return CognitiveTask("EXPAND", priority=0.8, reason="confidence low, need deeper objects")

        if len(ws.hypotheses) == 1:
            return CognitiveTask("EXPAND", priority=0.7, reason="single hypothesis, need alternatives")

        if ws.reasoning_tree is None:
            return CognitiveTask("REASON", priority=0.6, reason="no reasoning yet")

        if not ws.reflection_log:
            return CognitiveTask("REFLECT", priority=0.5, reason="need reflection")

        if ws.confidence > 0.7 and ws.hypotheses:
            return CognitiveTask("COMMIT", priority=0.4, reason="ready to commit")

        return CognitiveTask("DESTROY", priority=0.1, reason="done")


    def execute(self, observer: Observer, task: CognitiveTask) -> ExecutionTrace:
        """执行一个任务，返回 trace step。"""
        t0 = time.time()
        step = TraceStep(
            step_id=f"{observer.id}_{task.type}_{int(t0)}",
            state=task.type,
            observer_snapshot=observer.snapshot(),
            workspace_snapshot=observer.workspace.snapshot() if observer.workspace else {},
        )

        handler = {
            "LOAD": self._load,
            "PERCEIVE": self._perceive,
            "RETRIEVE": self._retrieve,
            "EXPAND": self._expand,
            "REASON": self._reason,
            "REFLECT": self._reflect,
            "COMMIT": self._commit,
            "VERIFY": self._verify,
            "DESTROY": self._destroy,
        }
        handler[task.type](observer, task)

        step.latency_ms = (time.time() - t0) * 1000
        step.decision = f"{task.type} completed (reason: {task.reason})"
        return step
```

### 2.3 调度循环

```python
def run(observer: Observer, scheduler: CognitiveScheduler) -> List[TraceStep]:
    """主循环：取出下一个任务→执行→记录 trace→判断是否结束。"""
    trace = []
    while observer.active:
        task = scheduler.next(observer)
        if task.type == "DESTROY":
            break
        step = scheduler.execute(observer, task)
        trace.append(step)
        observer.workspace.token_used += 100  # 每个任务约 100 token 开销
    return trace
```

---

## 3. WorkspaceGraph（替代 Stack）

### 3.1 图定义

```python
@dataclass
class WorkspaceNode:
    """WorkspaceGraph 中的一个节点。"""
    workspace: CognitiveWorkspace
    children: List[str] = field(default_factory=list)       # 子节点 ids
    dependencies: List[str] = field(default_factory=list)    # "需要等谁完成才能 merge"
    merge_strategy: str = "weighted"                         # "concat" | "weighted" | "vote"
    status: str = "pending"                                  # "pending" | "running" | "done" | "failed"


class WorkspaceGraph:
    """有向图——Stack 只是单 child 的特例。"""

    def __init__(self):
        self.nodes: Dict[str, WorkspaceNode] = {}
        self.root_id: Optional[str] = None

    def add(self, node: WorkspaceNode, parent_id: str = None):
        self.nodes[node.workspace.id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node.workspace.id)
        if self.root_id is None:
            self.root_id = node.workspace.id

    def can_merge(self, node_id: str) -> bool:
        """所有依赖的子节点都完成了？"""
        node = self.nodes[node_id]
        for dep_id in node.dependencies:
            if self.nodes[dep_id].status != "done":
                return False
        return True

    def merge_results(self, node_id: str, observer: Observer):
        """合并所有子节点的 hypotheses 到父节点。"""
        node = self.nodes[node_id]
        merged = []
        confidences = []
        for child_id in node.children:
            child = self.nodes[child_id]
            merged.extend(child.workspace.hypotheses)
            confidences.append(child.workspace.confidence)
        node.workspace.hypotheses = merged
        node.workspace.confidence = sum(confidences) / len(confidences) if confidences else 0.5
```

### 3.2 Stack vs Graph 对比

```
Stack (v1.0):
  Main
    └── Observation
          └── Normalizer
  只能表达递归

Graph (v2.0):
  Main
    ├── Observation  ─┐
    ├── Scheduler   ──┤ parallel
    └── Knowledge   ──┘
          ↓
        Merge
  支持递归 + 并行
```

---

## 4. OS 类比：Observer = CPU, Workspace = Process

| 操作系统 | Cognitive Runtime |
|---------|-------------------|
| CPU | Observer (调度、资源、视角) |
| Process | Workspace (推理任务、隔离执行) |
| Address Space | Workspace.workspace_graph (作用域隔离) |
| Scheduler | CognitiveScheduler (优先级调度) |
| Context Switch | Observer 切换 perspective |
| Syscall | Commit to Knowledge Space |
| Core Dump | ExecutionTrace |
| fork() | push_workspace() |
| wait() | merge_results() |

```python
@dataclass
class Observer:
    """认知 CPU——永远只有一个实例，调度所有 Workspace。"""
    
    id: str
    
    # ── 调度状态 ──
    perspective: str = "architecture"
    attention: Dict[str, float] = field(default_factory=dict)
    token_budget: int = 4000
    token_used: int = 0
    max_depth: int = 3
    
    # ── 工作空间管理 ──
    workspace_graph: WorkspaceGraph = field(default_factory=WorkspaceGraph)
    current_workspace_id: Optional[str] = None
    
    # ── 生命周期 ──
    active: bool = True
    created_at: float = field(default_factory=time.time)


    @property
    def workspace(self) -> Optional[CognitiveWorkspace]:
        """当前活跃的 workspace。"""
        if self.current_workspace_id and self.current_workspace_id in self.workspace_graph.nodes:
            return self.workspace_graph.nodes[self.current_workspace_id].workspace
        return None

    def pull_workspace(self, goal: str, focus: List[str]) -> CognitiveWorkspace:
        """fork()：创建子 Workspace。"""
        ws = CognitiveWorkspace(
            id=f"ws_{self.id}_{len(self.workspace_graph.nodes)}",
            goal=goal,
            focus_objects=focus,
            state="INIT",
            parent_id=self.current_workspace_id,
        )
        node = WorkspaceNode(workspace=ws)
        self.workspace_graph.add(node, self.current_workspace_id)
        self.current_workspace_id = ws.id
        return ws

    def snapshot(self) -> dict:
        return {
            "perspective": self.perspective,
            "attention": self.attention,
            "token_used": self.token_used,
            "current_workspace": self.current_workspace_id,
            "graph_size": len(self.workspace_graph.nodes),
        }
```

---

## 5. Execution Trace

### 5.1 定义

```python
@dataclass
class TraceStep:
    """单次调度执行的可重放记录。"""
    step_id: str
    state: str                    # PERCEIVE | RETRIEVE | REASON | ...
    observer_snapshot: dict       # perspective, attention, budget
    workspace_snapshot: dict      # active_objects, hypotheses, confidence  
    decision: str = ""            # "expand Observation" | "commit hypothesis #3"
    llm_input_tokens: int = 0
    llm_output: str = ""
    latency_ms: float = 0.0
    parent_step: Optional[str] = None  # 用于递归推理链


class ExecutionTrace:
    """完整的一次推理会话 trace。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.steps: List[TraceStep] = []
        self.final_answer: str = ""
        self.final_confidence: float = 0.0

    def add(self, step: TraceStep):
        self.steps.append(step)

    def replay(self, observer: Observer, scheduler: CognitiveScheduler) -> bool:
        """按 trace 重放——验证一致性。"""
        for step in self.steps:
            task = scheduler.next(observer)
            if task.type != step.state:
                return False  # 调度路径不一致
            scheduler.execute(observer, task)
        return True

    def debug_path(self, step_id: str) -> List[TraceStep]:
        """回溯到指定 step——用于诊断。"""
        for i, step in enumerate(self.steps):
            if step.step_id == step_id:
                return self.steps[:i+1]
        return []

    def summary(self) -> str:
        states = [s.state for s in self.steps]
        total_latency = sum(s.latency_ms for s in self.steps)
        return (
            f"Trace {self.session_id}: {len(self.steps)} steps, "
            f"{total_latency:.0f}ms, "
            f"path: {' → '.join(states)}, "
            f"confidence: {self.final_confidence:.2f}"
        )
```

### 5.2 Trace 的三个用途

| 用途 | 操作 | 示例 |
|------|------|------|
| **replay** | `trace.replay(observer, scheduler)` | 同 question 是否产生同 path？ |
| **debug** | `trace.debug_path(step_id)` | "为什么 commit 了错误的 hypothesis？" → 回溯到 RETRIEVE 时发现缺证据 |
| **meta-learn** | 多 session trace 聚合 | Pattern: "每次 confidence<0.3 时，RETRIEVE 比 REASON 更有效" |

---

## 6. 完整架构

```
User Question
    │
    ▼
┌─────────────────────────────────────┐
│         CognitiveScheduler           │
│         (优先级调度)                  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         Observer (CPU)               │
│  perspective | attention | budget    │
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐┌────────┐┌────────┐
│Workspace││Workspace││Workspace│  ← Graph
│   A    ││   B    ││   C    │
│Reason  ││Reason  ││Reason  │
└───┬────┘└───┬────┘└───┬────┘
    │         │         │
    └────Merge──────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         Commit Protocol              │
│  confidence>0.7 + 0 conflict → freeze│
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────────┐
    ▼          ▼              ▼
┌────────┐┌──────────┐┌──────────────┐
│Knowledge││Execution ││Reflection Log│
│ Space  ││Trace     ││              │
└────────┘└──────────┘└──────────────┘
```

---

## 7. 实现计划

| Phase | 内容 | 代码量 | 现有接口变化 |
|-------|------|--------|------------|
| R1 | Observer + Workspace + WorkspaceNode + WorkspaceGraph | ~80 行 | 0 |
| R2 | CognitiveTask + CognitiveScheduler | ~60 行 | 0 |
| R3 | TraceStep + ExecutionTrace | ~50 行 | 0 |
| R4 | Commit Protocol (can_commit, should_rollback, commit_to_knowledge) | ~40 行 | 0 |
| R5 | 现有模块接入 (PerspectivePlanner → observer.perspective) | ~100 行 | 5个模块微调 |
| R6 | run() 主循环 | ~30 行 | engine.on_event 包装 |

**总计 ~360 行，0 个现有接口破坏。**
