# M3 认知层施工记录 — B1-8 + LLM-1 + LLM-3（2026-08-04）

> 定位: M3 认知层施工完整记录（认知运行时落地 + 共享树接线 + 对内执行预测学习）。
> 关联定案: `B18_COGNITIVE_WORKSPACE_DECISION_20260804.md`（B1-8）+
> `LLM3_V6_COGNITIVE_INTEGRATION_20260804.md`（LLM-3）+ LLM-1（共享树通信）。
> 状态: ✅ M3 施工完成（测试 11/11 绿 + 回归无新破坏）

---

## 一、施工清单对照（B1-8-P1~P5 + LLM-3-P1~P5 + LLM-1）

```
✅ B1-8-P1  B 套调度归档（范围修正, 见 §二.1）— scheduler/policy → un_use
✅ B1-8-P2  engine._cognitive_observer/_cognitive_scheduler 懒初始化 + 配置开关
✅ B1-8-P3  run_cognitive_loop 接 engine 可选前置（A16 快慢分流, _run_cognitive_prepass）
✅ B1-8-P4  Workspace → cognitive_tree 写入（record_llm_thought + 认知循环产出落树）
✅ B1-8-P5  workspace/graph/merge/trace + 认知接线测试（test_cognitive_runtime_wiring）
✅ LLM-3-P1  runtime/cli engine 挂 cognitive_tree（懒初始化）
✅ LLM-3-P2  预测接入: predict_execution（读思考树历史 PREDICTION 节点）
✅ LLM-3-P3  学习闭环: record_execution_outcome（PREDICT→EXECUTE→COMPARE→LEARN）
✅ LLM-3-P4  输出吸收机制: record_llm_thought 统一写树（工程链/元认知/skill 消费 P2）
🟡 LLM-3-P5  simulation_engine 扩展执行预测域（P2, 现有用户预测保留）
✅ LLM-1     record_llm_thought = 6 LLM 思考记录唯一写树入口（compiler 修复后可用）
```

---

## 二、核心改动

### 2.1 归档（B1-8-P1 范围修正）
```
✅ 已归档 → un_use/cognitive_scheduler_b/:
   scheduler.py（B 套 CognitiveScheduler/SchedulerMonitor/QueueSnapshot）
   policy.py（SchedulerPolicy/PriorityFIFOPolicy/PathAwarePolicy）
   tests/test_scheduler.py

⚠️ 范围修正（相对定案）:
   定案说"归档整个 v4/cognitive_scheduler/*" — 但实测 engine 顶部 import
   并实际消费 path_*（PathAwareScheduler = engine._scheduler / ConfigDriven
   TriggerPolicy/PathStateMachine = engine._trigger_policy/_path_state_machine/
   _event_counter / tasks.ObservationTask 等）。
   → 整目录归档会破坏 engine 启动。
   修正: 只归档真正被取代且零生产引用的 scheduler/policy；path_* + models
   (tasks 依赖 Task) + tasks 保留。__init__.py 同步修正（去掉归档模块导入）。
```

### 2.2 真实 bug 修复（M3 发现）
```
🔴 1. engine.on_event_sm 无限递归（阻断认知前置 + 无 StateMachine 的引擎事件处理）:
   on_event_sm 无 SM 时 fallback 到 self.on_event() → on_event 又委托回
   on_event_sm → 无限递归 (RecursionError)。run_cognitive_loop 的 PERCEIVE/
   REASON 步调 engine.on_event 触发海量警告。
   → 修复: 无 SM 或 pipeline 异常时返回 None（调用方降级, v3_session_api
     fallback 语义不破）。

🔴 2. CognitiveCompiler 是"坏件"（LLM-1 唯一写树入口从未跑通过）:
   compile() 一跑即崩:
   - access.can_write() 不存在（AccessControlMatrix 是 check_create）
   - _create_node 引 CogNodeType（不存在, 只有 CogType）
   - store API 不匹配: compiler 调 add_node/get_node/add_edge(4参),
     默认 store (CognitiveTreeStore) 只有 save_node/load_node
   - CogType 无 PREDICTION 成员（LLM-3 语义）
   → 修复: 权限检查兼容（未配置 LLM = 内部白盒允许）、CogType 映射、
     cross-ref 边构造 CognitiveTreeEdge 对象、默认 store 改 CognitiveTree
     (v3_0 思考树, 与定案一致)、_make_event_bus 返回 None（async EventBus
     在同步引擎路径不可用, 写树不依赖, 事件接线归 G2）。

🟡 3. path_scheduler config 断链（预存在）:
   _ensure_runtime_config 引 core.agent.v4.runtime.config（4d3aaf7 重构后
   已移动到 core.agent.runtime.config）→ PathAwareScheduler 实例化即崩。
   → 修复 import 路径。test_path_components 9 失败 → 4（剩余 4 为测试自身
     抽象类/断言问题, 预存在）。
```

### 2.3 新增能力（engine）
```
engine._init_cognitive_runtime()        — Observer/Scheduler/CognitiveTree/
                                          CognitiveCompiler 懒初始化（非致命）
engine.cognitive_state()                — 认知层白盒状态快照
engine.record_llm_thought(...)          — 6 LLM 思考记录唯一写树入口 (LLM-1)
engine.predict_execution(action_desc)   — 执行前预测 (LLM-3 PREDICT)
engine.record_execution_outcome(...)    — 结果对照+差异回写+自监督统计 (LEARN)
engine._run_cognitive_prepass(text)     — 认知循环可选前置 (B1-8-P3, A16 快慢)
CogType.PREDICTION                      — 新增认知类型 (对内执行预测)
```

---

## 三、测试

```
新增 core/agent/v4/cognitive/tests/test_cognitive_runtime_wiring.py:
  11/11 绿
  覆盖: 认知运行时懒初始化 / 默认关闭(A16) / 短文本快速通道跳过 /
        认知循环 PERCEIVE→REASON→REFLECT / 6 LLM 写树 / 预测学习闭环
        (predict→outcome→再次预测命中) / B 套归档验证 / path API 保留

回归（本次改动范围）:
  api/tests/test_viz_edit.py                29/29 ✅（M2 未破坏）
  runtime/tests/test_behavior_causal        11/11 ✅
  v4/cognitive/tests/test_cognitive.py      12/12 ✅
  v4/cognitive/tests/test_mind.py            4/4 ✅
  cli/tests                                 27/28 ✅（D-14 预存在）
  v3_0/cognitive_tree/tests                 94/104 ✅（10 失败 = 预存在的
     pytest-asyncio strict async fixture 问题, 与本轮无关）
```

---

## 四、遗留（P2, 不阻塞）
```
LLM-3-P4  输出吸收: 工程链执行前检查项 / 元认知反思输入 / skill 沉淀 —
          机制已就绪 (record_llm_thought), 消费点接线待模块施工
LLM-3-P5  simulation_engine 执行预测域扩展（现有用户问题预测保留）
LLM-1     6 LLM 实例 (llm_instances/*_llm.py) 逐点调 record_llm_thought
          — 入口已就绪, 逐点接线归模块施工
G2        认知 EventBus 事件通知（_make_event_bus 现返回 None, 归 G2 统一）
v3_0/cognitive_tree tests: 10 个 async fixture 兼容问题（预存在, 归测试基建）
```

---

> 恢复路径: STATE_HANDOFF_IMPLEMENTATION_20260804.md → 本记录 → M4 执行层
