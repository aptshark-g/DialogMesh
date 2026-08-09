# B1-8 CognitiveWorkspace 容器 — 拍板定案（2026-08-04）

> 定位: 真决策 B1-8（归 LLM-1 认知层接线）正式定案。
> 关联: `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` 聚类 2 B1-8；
> `landscape_read/BATCH1_COGNITIVE_SPACE_SCHEDULER` 批 1（四空间/认知运行时精读）；
> 执行层审计 DESIGN_FULL_READ（OS 类比: Observer=CPU / Workspace=Process /
> Scheduler=OS Scheduler / WorkspaceGraph=Address Space）。
> 状态: ✅ 已拍板（2026-08-04，用户确认方案）

---

## 一、核查事实（代码级实锤）

### 1.1 设计（两份，四空间 + 认知运行时）
```
DESIGN_COGNITIVE_WORKSPACE.md (v3.0, 310L):
  四空间模型: Document → Concept → Knowledge → Cognitive Space
  Cognitive Space = "推理时内部状态如何演化"（当前关注窗口）
  一次 LLM 推理 = 一个 Workspace 实例

DESIGN_COGNITIVE_RUNTIME.md (v3.0, 384L):
  v1→v2: StateMachine → CognitiveScheduler / Stack → WorkspaceGraph / +ExecutionTrace
  OS 类比: Observer=CPU(唯一) / Workspace=Process / WorkspaceGraph=Address Space /
           Scheduler=OS Scheduler / Core Dump=ExecutionTrace
  CognitiveTask 7 类: LOAD/PERCEIVE/RETRIEVE/EXPAND/REASON/REFLECT/VERIFY/COMMIT/DESTROY
  实现计划 R1-R6 ~360 行, 0 接口破坏
```

### 1.2 实现实况（三套并存，全部未接主路径）
```
① v4/cognitive/workspace.py (4.4KB) + scheduler.py (4.5KB) + runtime.py (5KB)
   = 设计直译实现:
     CognitiveWorkspace（goal/focus/active_objects/hypotheses/conflicts/
       reasoning_depth/max_depth 全字段在）
     WorkspaceGraph（add/can_merge/merge 子假设合并）
     ExecutionTrace / TraceStep（replay/debug/聚合三用途）
     Observer（perspective/attention/token_budget）
     CognitiveScheduler（MetaReflection → CognitiveTask 映射, 无决策逻辑）
     run_cognitive_loop（PERCEIVE → [REASON→REFLECT→决策→执行]* → COMMIT）
   ⚠️ 主路径零调用: engine._cognitive_observer=None / engine._scheduler=None
      run_cognitive_loop 只在 un_use/engine_legacy + 归档测试被调
② v4/cognitive_scheduler/（另一套! scheduler.py 统一调度循环 + path_scheduler.py +
   WorkerPool）— 有测试, 主路径同样零接线
③ association/global_workspace.py (GlobalWorkspace 轨道竞争) — 关联链在用 (fusion)
```

### 1.3 仅有的"使用点"是假的
```
perspective_planner.py:214: 临时 CognitiveWorkspace(id="persp", goal=text)
  喂给 MetaCognition.reflect() 后即弃（不写树/不进图/无 trace）
subsystem_registrations.py: "mind" = Mind（画像记忆聚合）, 不是 CognitiveWorkspace
agent_native.py:111: PipelineObserver() 是另一类型
```

---

## 二、拍板内容（正式）

```
B1-8: 归 A 套（v4/cognitive/*），做"认知运行时"完整落地

① 容器归一（A 套为主）:
   保留: CognitiveWorkspace + WorkspaceGraph + ExecutionTrace +
         Observer + CognitiveScheduler + run_cognitive_loop
   归档: v4/cognitive_scheduler/*（scheduler + path_scheduler + WorkerPool）
         → 调度职责未来归 CognitiveScheduler（G1 未来调度层），
           不是现在的 WorkerPool；B 套设计偏离 + 零接线 → un_use
   GlobalWorkspace (association/) 保留（关联链 fusion 在用，职责不同）

② 接主路径（engine）:
   engine._scheduler / engine._cognitive_observer 懒初始化
   run_cognitive_loop 作为 engine.on_event 的可选前置（配置开关）:
     A16 快慢: 快速通道不走认知循环；LLM 主推理走
   → 与 G1+G3 分工: StateMachine 执行链 + 认知循环（感知/推理/反思）

③ 与 LLM-1 共享树接线联动:
   Workspace 的 reasoning_tree / hypotheses 写入 cognitive_tree
   （6 LLM 思考记录），一个容器两个视图
   → 与 LLM-1（共享树通信接线）一起施工

④ 测试:
   补 workspace / graph / merge / trace 测试
   （对应设计 R1-R6 的 360 行实现计划）
```

---

## 三、施工前置

```
B1-8-P1  v4/cognitive_scheduler/ 归档 un_use（B 套）P1
B1-8-P2  engine._scheduler/_cognitive_observer 懒初始化 + 配置开关 P1
B1-8-P3  run_cognitive_loop 接 engine.on_event 可选前置（A16 快慢分流）P1
B1-8-P4  Workspace → cognitive_tree 写入（与 LLM-1 共享树联动）P2
B1-8-P5  补 workspace/graph/merge/trace 测试（R1-R6 对应）P2
```

## 四、验收标准

```
① engine 启动后 _cognitive_observer/_scheduler 可实例化（开关开启时）
② run_cognitive_loop 主路径可跑（PERCEIVE→REASON→REFLECT→COMMIT 闭环）
③ 快速通道（非 LLM 推理）不经过认知循环（A16）
④ 认知循环的 reasoning_tree/hypotheses 落 cognitive_tree（LLM-1 联动）
⑤ v4/cognitive_scheduler/ 已在 un_use
⑥ workspace/graph/merge/trace 测试全绿
```

---

> 关联: G1+G3（执行链分工）/ LLM-1（共享树接线，一起施工）/ A16（快慢分流）
