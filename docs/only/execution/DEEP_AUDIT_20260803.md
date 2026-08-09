# 执行层深层次复核（第二轮·实锤验证）

> 日期: 2026-08-03 | 对象: `event/statemachine.py` + `event/handlers.py` +
> `event/nats_bridge.py` + `runtime/engine.py` + `cli/engine.py`（启动路径）
> 方法: 源码精读 + 运行时探针（faulthandler 抓栈 / 直接调用）
> 结论: **第一轮的 2 个"测试卡死"升级为 2 个生产级 P0；另发现 1 个全新 P0（无限递归）**。

---

## 一、P0-1: `start_engine` 被 NATS 无限重连阻塞（生产启动路径）

### 证据链（探针实测）
```
faulthandler 抓栈（25s 后 dump）:
  cli/engine.py:268  wire_hybrid_bus(_engine)
  → event/nats_bridge.py:174  HybridEventBus(engine)
  → event/nats_bridge.py:128  NATSPublisher.__init__ → self.connect()
  → nats_bridge.py:57  asyncio.run(_connect())
  → nats-py client._select_next_server → _connect_to_server
  → TCP connect 超时（connect_timeout=1.0）→ 循环重试（无限）
```

### 根因
- 代码**意图是 fail-fast**：`allow_reconnect=False, max_reconnect_attempts=0`（nats_bridge.py:53-54），
  注释明确写了 "with no NATS server this stalls engine startup for minutes. Fail fast and fall back"。
- 但 **nats-py 的 initial connect 不走 reconnect 计数**——`_select_next_server` 对首个服务器
  无限重试（每次 TCP 超时 1s），`max_reconnect_attempts=0` 在首次连接阶段不生效。
- `start_engine` 里 `try/except` 包着 wire_hybrid_bus，但**无限阻塞不是异常** → except 救不了。

### 影响
- `test_e2e.py::test_e2e_full_pipeline_mock` 卡死 = start_engine 卡在 NATS（不是"进程不退出"）。
- **任何无 NATS 服务器的环境启动 CLI 引擎都会挂起**——直到手动 Ctrl+C。
- 顺带发现: `state.json` 在 anaconda 3.9 下也 Permission denied（atexit _save_state 非致命报错）——
  与蓝图审计的 3.13 现象同型，需统一防御。

### 修复方向
- 不用 `asyncio.run(nc.connect())` 同步裸连；改为**先异步预探测**（如 `socket.create_connection`
  带 300ms 超时）再决定是否初始化 nats 客户端；或把 connect 放进带超时的独立线程。
- 或对 nats-py 包一层 `asyncio.wait_for(connect, timeout=2)` + 取消。
- 同步问题: `pluggable.py::NATSBridge` 同样无限重连（test_pluggable 卡死根因）——两处统一修。

---

## 二、P0-2: 纯 runtime engine `on_event` 无限递归（新发现）

### 证据（源码 + 探针）
```
runtime/engine.py:1307-1309:
    def on_event(self, event):
        return self.on_event_sm(event, start_phase="pcr")

runtime/engine.py:656-659:
    sm = getattr(self, '_state_machine', None)   # runtime engine 无此属性（rg 确认）
    if not sm:
        return self.on_event(event)              # ← 递归回 on_event

实测: e = CognitiveRuntimeEngine(); e.on_event(EventIR(...))
      → 无限刷 "on_event_sm: no StateMachine, falling back to on_event" 直至 RecursionError
```

### 影响
- `runtime/engine.py` 作为独立引擎使用时（docstring 示例、bench 脚本、runtime/tests），
  `on_event` 直接爆栈。
- 14/14 runtime 测试通过是因为测试只走 `_run_association_chain`/`record_step` 等内部方法，
  没碰 `on_event` 入口——**测试覆盖了内部，没覆盖公开入口**（真实测试缺口）。

### 修复方向
- `on_event_sm` 无 `_state_machine` 时不应回退 `on_event`（on_event 又调 on_event_sm）；
  应回退到一个真正的串行路径，或直接 `raise RuntimeError("StateMachine not wired")`。

---

## 三、StateMachine 半实现（第一轮确认 + 深挖）

### 3.1 handler 注册缺口（确认）
```
注册 8/11: PCR/INTENT/DISCOURSE/BEHAVIOR/META/PROFILE/PERSIST/ASSOCIATION
缺 3/11:   PLANNING / CONTEXT / LLM —— 这三个阶段在 run_pipeline 中 handler=None
```

### 3.2 新增发现: handler 输出不传递给下游（数据流断）
```
run_pipeline: handler(context) → 结果只存 results[current.value]
下游 handler 收到的仍是同一个原始 context（除非 handler 自己修改 ctx，如 handle_association）
→ handle_meta 里 ctx.get("intent", {}) 恒空 → mc.retrospect(target="general") 永远用 "general"
→ 各阶段产出（pcr 的 zone、intent 的 category）无法供下游阶段消费
```

### 3.3 新增发现: 无 handler 阶段用上一阶段 result 决策（语义错）
```
while 循环里 result 变量只在 handler 存在时重新赋值
→ PLANNING 阶段 handler=None → result 残留 INTENT 的结果 → decide(PLANNING, intent_result)
→ 若 INTENT 返回 skip，PLANNING 会错误走 skip 分支
```

### 3.4 `_on_event_continue`（460 行）零调用方（确认）
```
runtime/engine.py:793 定义，全库无调用 → 死代码
```

### 3.5 `_compile_context` 幽灵调用（确认，上下文审计 C4）

---

## 四、`_planner` 恒 None → runtime 路径规划完全未接线（规划模块联动）

```
runtime/engine.py:224  self._planner = None（唯一赋值）
runtime/engine.py:842  if self._planner is not None:  ← 恒 False
全库 rg: 无任何 _planner = <实例> 赋值
→ v6 主宿主的规划功能（plan/skill_registry 路径）从未启用
```

---

## 五、第一轮修正

1. `test_e2e 卡死` ≠ "进程不退出"，根因 = **NATS 无限重连**（P0-1）。
2. `on_event 旧串行` 表述不准——`on_event` 是 `on_event_sm` 的 wrapper（1307-1309），
   真正的旧串行逻辑在 `_on_event_continue`（793-1253，零调用方死代码）。
3. `events/` vs `event/` 不是"同构双份"——`events/` 是主事件模型（EventIR/EventBus，
   runtime/engine.py 等 28 处），`event/` 是 StateMachine 新体系（45 处）——两者按设计并存，
   但 meta_subscriber（events/）与 handlers（event/）**没有桥接**。

---

## 六、待拍板/待修复清单（执行层）

| # | 级别 | 事项 | 方向 |
|---|---|---|---|
| X1 | P0 | NATS 无限重连（nats_bridge + pluggable 两处）| 预探测/超时线程 |
| X2 | P0 | on_event 无限递归 | 修正回退路径 |
| X3 | P1 | PLANNING/CONTEXT/LLM handler 缺失 | 按设计补 3 阶段 |
| X4 | P1 | handler 输出不传下游 | run_pipeline 注入 results 到 ctx |
| X5 | P1 | 无 handler 阶段 result 残留 | 显式 result={} 兜底 |
| X6 | P2 | `_on_event_continue` 460 行死代码 | 删除或复活 |
| X7 | P2 | `_compile_context` 幽灵调用 | 接真实实现 |
| X8 | P2 | `_planner` 恒 None（规划未接线）| 与规划审计联动 |
