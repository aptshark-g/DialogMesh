# 执行层多树图（7 树体系）深审 — tree_manager + pipeline + closure + sandbox/permissions 接线实锤

> 日期: 2026-08-03 | 对象: `core/agent/execution/`（9 文件 122.4KB）
> 触发: 用户核查新增「执行层多树图（7 树体系）全部定义但零消费」——**部分成立，部分不成立，需勘误**。
> 方法: 全库 rg 消费矩阵 + import 探针（anaconda 3.9）+ bootstrap() 实测 + 源码精读。

---

## 〇、结论先行（勘误用户线索）

1. **树的数量是 7，不是 8**：discourse / execution / constraint / association /
   behavior / meta / profile（tree_manager.py 头部 docstring 自述 "7 trees"）。
2. **"ExecutionTree.create_task/spawn_sub_agent/complete_node 全库无调用方" 不成立**——
   这三个方法被 `ExecutionPipeline.run()` 真实调用（pipeline.py:338/386/388），
   `ConstraintTree.check` 也被调用（pipeline.py:354）。
3. **"全部零消费" 修正为「5/7 死树 + 1 条条件触发链路 + B 路径零接触」**：
   - 真消费（A 路径，条件触发）: ExecutionTree、ConstraintTree（仅 pipeline 内）、
     AgentTreeManager.get_node_by_pointer / archive_all_completed / get_all_stats
   - 死树（定义无消费）: DiscourseTree、AssociationTree、BehaviorTree、ProfileTree
   - 假消费（传参但从不调用）: MetaTree（pipeline 传给 ReActRetryEngine 但方法内零使用）
   - 孤儿模块（零 import）: server.py(ExecutionServer)、normalizer.py(ExternalToolNormalizer)、
     monitor/p1_gaps.py（L5MemoryBridge + ProfileEvolution + SandboxExecutor）
   - B 路径（runtime/cli）对 execution/ 零 import（`rg "from core.agent.execution" runtime/` 空）
4. **A 路径 bootstrap() 实测可加载**：Compass/Execution/Sandbox/Permission/ReActor/PlanGate/
   EventBus/Context/Cognition/Feedback 全部非 None；但 ExecutionPipeline.run() 仅在
   `llm 存在 ∧ plan_gate checkpoint.requires_review=False ∧ plan 有 steps` 时才执行（agent_native.py:246-262）。
   无 LLM 时执行层永不运行。

---

## 一、7 树消费矩阵（全库 rg 实锤）

| 树 | 方法 | 消费方 | 状态 |
|---|---|---|---|
| DiscourseTree | record_turn | 无（全库 0 处调用 `atm.discourse`）| 🔴 死树 |
| ExecutionTree | create_task / spawn_sub_agent / complete_node | ExecutionPipeline.run（pipeline.py:338/386/388）| 🟢 真消费（A 路径条件触发）|
| ConstraintTree | add_rule / check | pipeline.py:354（真）；sandbox.py:259 与 permissions.py:514 也调 `.check`，但 bootstrap 创建 FileSandbox/PermissionEnforcer 时**未传 constraint_tree** → `self._constraint=None` → 这两处恒空转 | 🟡 半接线（仅 pipeline 内生效）|
| AssociationTree | map_nodes / find_mappings | 无 | 🔴 死树 |
| BehaviorTree | record_pattern / get_approval_rate | 无 | 🔴 死树 |
| MetaTree | record_decision / assess_quality | ReActRetryEngine 收到 `self._atm.meta`（pipeline.py:310）但类内只存 `self._meta`，**方法体零引用** | 🟡 假消费（死线）|
| ProfileTree | record_profile_update | 仅 p1_gaps.py:178 的 ProfileEvolution（自身也是孤儿，无任何 import）| 🔴 死树 |
| AgentTreeManager | global_query | 无 | 🔴 死方法 |
| AgentTreeManager | get_node_by_pointer | MemoryNode.retrieve_by_pointer（pipeline.py:86）+ closure.py:94/97（closure 自身无人实例化）| 🟢 真消费（pipeline 内）|
| AgentTreeManager | archive_all_completed / get_all_stats | pipeline.py:412/422 | 🟢 真消费 |

---

## 二、ExecutionPipeline 接线实况（A/B 路径）

### 2.1 A 路径（agent_native / bootstrap_v6）— 已接线但条件触发
```
bootstrap_v6.bootstrap() 实测（anaconda 3.9）:
  loaded=[Compass, Execution, Sandbox, Permission, ReActor, PlanGate, EventBus, Context, Cognition, Feedback]
  _execution_pipeline.run callable: True

触发条件（agent_native.process()）:
  if self.llm:                          # ← 无 LLM → 执行层永不运行（结构性模式跳过）
    plan = self._llm_synthesize(result)
    if self._plan_gate and plan.steps:
      checkpoint = plan_gate.create_checkpoint(...)
      if checkpoint.requires_review: return   # 需人工审批 → 提前返回
      if self._execution_pipeline:
        exec_result = asyncio.run(pipeline.run(plan, checkpoint))  # ← 唯一入口
```

### 2.2 B 路径（runtime / cli）— 零接触
```
rg "from core.agent.execution|import execution" runtime/ core/agent/runtime/ → 空
→ runtime/engine.py 与 cli/engine.py 完全不消费 execution/ 包。
```

### 2.3 结论
- 执行层不是"孤儿"，而是**只活在 A 路径的条件分支里**；B 路径（当前 CLI/API 主路径）
  从未触碰 → 用户感知"没接线"在 B 路径语境下成立。

---

## 三、closure.py（ReActor/NodeLifecycle/CausalTracer/UserInLoop）— 死线

```
bootstrap_v6._load_reactor() → ReActor()  # 不传任何 tree_manager/meta_tree/behavior_tree
ReActor.__init__ → NodeLifecycle() / CausalTracer() / UserInLoop()  # 内部树参数全 None
agent_native.py:44 self._reactor = reactor  # 仅存储，全类无后续调用（rg 实锤）
→ closure.py 四个类在 A/B 路径均不生效；NodeLifecycle.meta_tree、
  CausalTracer.tree_manager、UserInLoop.behavior_tree 参数全是摆设。
```

---

## 四、sandbox / permissions — ConstraintTree 空转

```
bootstrap_v6._load_file_sandbox() → FileSandbox(os.getcwd())          # 无 constraint_tree
bootstrap_v6._load_permission_guard() → PermissionEnforcer()          # 无 constraint_tree
→ 两处 self._constraint = None
→ sandbox.py:258-259 / permissions.py:511-514 的 ConstraintTree.check 分支恒不执行
→ 执行层安全护栏（gVisor 语义）实际空转，与"约束空间/工程链"设计脱节。
```

---

## 五、孤儿模块

| 文件 | 类 | 消费方 | 状态 |
|---|---|---|---|
| server.py | ExecutionServer（ws://127.0.0.1:9100）| 仅自身 `__main__` | 🔴 孤儿 |
| normalizer.py | ExternalToolNormalizer | 全库 0 引用 | 🔴 孤儿 |
| monitor/p1_gaps.py | L5MemoryBridge / ProfileEvolution / SandboxExecutor | 全库 0 import | 🔴 孤儿（且与 tree_manager.ProfileTree 概念重复）|

---

## 六、ExecutionEngine 本体（真实可用的独立实现）

```
engine.py ExecutionEngine: 7 工具（bash/read/write/edit/glob/grep/image）
  - 原子写（FileMutationQueue + 临时文件 + os.replace）
  - 图片 MIME 嗅探（JPEG/PNG/GIF/WebP/BMP）+ base64 预览
  - 约束预检 _check_constraints + 超时（asyncio.wait_for / run_in_executor）
  - DRY_RUN / SANDBOX / FULL 三模式
→ 引擎本体质量尚可，是唯一"真实现"的部分；问题在接线不在实现。
```

---

## 七、测试现状

- `core/agent/execution/` 下无任何测试文件；`monitor/p1_gaps.py` 也无测试。
- A 路径 ExecutionPipeline.run 无端到端测试（需 LLM + plan_gate 双条件）。
- 与 P-3（测试缺失/断裂）同型。

---

## 八、待拍板/待修复清单（并入执行层 X 系列）

| # | 级别 | 事项 | 方向 |
|---|---|---|---|
| X9 | P1 | 7 树归一：5 棵死树（discourse/association/behavior/profile/meta）去留 | 按对话树/子图/画像现有体系决定合并 or 删除 |
| X10 | P1 | ExecutionPipeline 在 B 路径（runtime/cli）接线 | runtime engine 挂 ExecutionPipeline，或明确定位为 A 路径专用 |
| X11 | P1 | ConstraintTree 注入 sandbox/permissions（当前 None 空转）| bootstrap 传入 AgentTreeManager().constraint |
| X12 | P2 | closure.py 四类复活 or 删除（当前死线）| ReActor 接 agent_native 或归档 |
| X13 | P2 | server.py / normalizer.py / p1_gaps.py 三个孤儿模块处置 | 归档 un_use 或接线 |
| X14 | P2 | 补执行层测试（引擎 7 工具单测 + pipeline 集成）| 真实断言，非浅测 |

---

## 九、与全局拍板池的关系

- **P-1 接线断裂**新增 1 例: closure.py 四类 + sandbox/permissions 约束空转。
- **P-2 多代演进分裂**新增 1 例: monitor/p1_gaps.py 与 tree_manager 的 ProfileTree
  概念重复（两套 OCEAN 进化实现）。
- **P-4 双路径分裂**新增 1 例: 执行层只接 A 路径，B 路径零接触（与 LLM 认知层、
  规划、上下文同型）。

