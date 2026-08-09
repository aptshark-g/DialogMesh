# M4 执行层施工记录 — G1+G3 + X 系列（2026-08-04）

> 定位: M4 执行层施工完整记录（StateMachine 补全 + DAG 拓扑序 + 双路径归一）。
> 关联定案: `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` §6/§7（G1+G3 合并）+
> 执行层审计 `docs/only/execution/AUDIT_ENTRY_20260803.md`（X1-X8）。
> 状态: ✅ M4 施工完成（测试 10/10 绿 + 回归 96+38 无新破坏）

---

## 一、施工清单对照（G1+G3-P1~P5 + X 系列）

```
✅ G1+G3-P1  修 StateMachine（X3 补 3 handler + X4 输出传递 + X5 result 兜底）P0
✅ G1+G3-P2  StateMachine 支持 DAG 拓扑序执行（run_dag + CHAIN_TO_PHASE）P0
✅ G1+G3-P3  v3_session_api L125 归一（空壳 orch.process → 引擎 PCR+Intent 真数据）P0
✅ G1+G3-P4  agent_native 处置（无参构造清零, bootstrap_v6 有参装配保留）P1
✅ G1+G3-P5  GlobalDecider 注入 StateMachine（复用 registry 实例, 状态底座）P1
✅ X1        NATS 无限重连（M1 已修）
✅ X2        on_event 无限递归（M3 已修 anti-recursion）
✅ X3        PLANNING/CONTEXT/LLM 3 handler 补全（13 阶段全管线可跑）
✅ X4        handler 输出传下游（run_pipeline 前序结果注入 ctx + LLM 回复返回）
✅ X5        无 handler 阶段 result 兜底（每轮显式重置, 不残留）
✅ X6        _on_event_continue 461 行死代码归档 un_use（A17 保留）
✅ X7        _compile_context 幽灵调用 → handle_context 接真实 IR 组装
✅ X8        _planner 恒 None → handle_planning 懒初始化 LLMPlanner
```

---

## 二、核心改动

### 2.1 event/statemachine.py
```
decide():  X5 修复 — 每轮 result={} 显式重置（无 handler 阶段不留上轮残留）
           + G1+G3-P5 — 有 GlobalDecider 时, phase 结果转 Command 记录状态
             （Event → evolve, 不改变路由, 防广播风暴）
run_pipeline(): X4 修复 — 前序阶段结果注入 phase_ctx（LLM/CONTEXT 可消费）
run_dag(): G1+G3-P2 — BlueprintDAG 拓扑序执行（Kahn）, 环形检测,
           节点输出按 data_key 喂下游, chain→phase 映射
CHAIN_TO_PHASE: pcr/intent/context/subgraph/llm_reply/behavior/meta/metap/
                discourse/association/profile/engineering → PipelinePhase
```

### 2.2 event/handlers.py（X3: 补 3 handler）
```
handle_planning: LLMPlanner 懒初始化（X8 修复 _planner 恒 None）→ plan steps
handle_context:  _last_context 真 IR 组装（X7 修复幽灵调用）→ ir_entries/domains
                 + P1/P3 resolver 注入（失败不阻塞）
handle_llm:      _llm_provider.generate → reply（无 LLM 模板降级 A16）
                 → results["llm"]["reply"] 由 on_event_sm 返回给调用方（X4）
G1+G3-P5:       sm._decider = engine._decider（复用 registry GlobalDecider 实例）
```

### 2.3 runtime/engine.py
```
on_event_sm: X4 收尾 — 优先返回 results["llm"]["reply"]（LLM 主回复）
X6:          _on_event_continue 461 行死代码 → un_use/engine_legacy/
             _on_event_continue_archived.py（A17 记录永不可删）
```

### 2.4 api/v3_session_api.py（G1+G3-P3, P0 数据流断裂修复）
```
L125: 数据源从空壳 AgentOrchestrator() 换真引擎:
  - get_engine() → _pcr_router.route() + _intent_parser.parse()（轻量认知）
  - cognitive_ctx 有真实 intents.segments/confidence/category + route.zone
  - 保留 try/except + prompt fallback（v3 旧前端兼容不破）
  - 不重跑 post-LLM 管线（避免与 L262 StateMachine 双跑）
agent_native: 无参构造清零（验证标准③）, bootstrap_v6 有参装配保留
```

---

## 三、测试

```
新增 core/agent/event/tests/test_statemachine_m4.py: 10/10 绿
  覆盖: 11 handler 注册 / 全管线 13 阶段 / X4 下游消费上游 / X5 无残留 /
        run_dag 拓扑序 + 环形检测 / CHAIN_TO_PHASE / decider 注入记录 /
        v3_session_api 归一（无无参 AgentOrchestrator + 真字段）

回归:
  event/tests（除 NATS 两件）+ runtime + M2 白盒   96/96 ✅
  cli/tests + 认知层接线                         38/39 ✅（D-14 预存在）
```

---

## 四、遗留（不阻塞）
```
D-14  CohesionScore 字段 bug（对话树, 预存在）
v3_0/cognitive_tree tests 10 async fixture 兼容（预存在, 归测试基建）
BlueprintExecutor 执行逻辑并入 StateMachine（切主路径后续, 蓝图退视图）
```

---

> 恢复路径: STATE_HANDOFF_IMPLEMENTATION_20260804.md → 本记录 → M5 EventBus 生命周期
