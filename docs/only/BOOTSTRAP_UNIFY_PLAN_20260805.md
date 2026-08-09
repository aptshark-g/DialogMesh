# 主线贯通施工方案 — B（统一装配）+ G1（蓝图退视图）+ LLM 全链验证

> 日期: 2026-08-05 | 状态: 待开工（压缩恢复入口）
> 触发: 真 LLM 测试（test_linkage_quality_v2）首次走全链暴露——引擎装配是散的，
> 冷启动无统一入口 → 全链组件 None（_trace_v3/对话树/meta/StateMachine 均未装配）。
> 用户判断: 模块层完成度高、系统层（装配/编排/主线）完成度低 → 做完整 = 打通主线。

---

## 一、当前终态（压缩前事实）

### 1.1 后端（已完成）
```
M1-M9 模块化施工 ✅ + 9 批模块级补全 ✅（对话树/意图/画像/关联链Phase6/
行为链DPO/causal/主题树/元认知/规划PL/SD）
测试: 各模块域内全绿（planner 27/27、SD 19/19、CLI 28/28、event 63/64 预存在等）
```

### 1.2 前端深审（已完成，FE_DEEP_AUDIT_20260805.md）
```
前端编译失败（53 TS 错误）→ 根因 = syntax-highlighter.d.ts 内 @reactflow 遮蔽 shim
  （已删除，剩余 53 为真实错误）; FE-1/FE-4 已被 M1-M9 修复（白盒编辑已挂载、
  stubs=内核dispatch）; 死代码 ~40 项（task 全家桶/WS四套/useChat/graph-utils）;
  RightDock 三屏设计已记录（RIGHT_DOCK_DESIGN_20260805.md）
```

### 1.3 Codex 健康排查（已完成）
```
蓝屏 0x000000EF = Codex Windows 版缺陷（官方 issue #36778/#36561/#36619/#36821 同型），
  非硬件; 磁盘无 SMART/错误事件; 写放大真实（logs_2.sqlite 192MB, transport TRACE
  单条 1.3MB）; 已清理 .tmp 178MB + 归档会话 116MB; 预防清单已给
```

### 1.4 网关/LLM 环境（已就绪）
```
网关: start.bat 启动 → 127.0.0.1:8080, deepseek active+healthy（key 已 POST 配置）
API:  127.0.0.1:8000 活着（/health 404 = 无该路由, 服务正常）
key:  sk-REPLACE_WITH_YOUR_KEY（DEEPSEEK_API_KEY 环境变量）
test_linkage_quality_v2 已修: 去 eng.start() + key 环境变量化 + L5/L6 改
  （_monitor 移除 → 用 report; _strategy_engine 移除 → 从 meta_consumer 取）
  → 剩余阻塞 = 冷启动装配缺失（见 §二）
```

---

## 二、根因定位（B 的动机）

`test_linkage_quality_v2` 走 `eng.on_event()`（= on_event_sm 兼容包装）:
```
on_event_sm → _state_machine 为 None → return None（M3 防递归）
  → 对话树未填充（L1 blocks=0）→ _trace_v3 None（meta 未初始化）
  → _simulation_stats total=0（L2）
```

装配现状（散的）:
```
cli/engine.py L264-350+:  大函数 try/except 串联 20+ 组件
                          （EventLog/Storage/Tracer/Guards/NATS/StateMachine/
                           KG/BehaviorGraph/ToolRegistry/Learning）
cli/pool.py L51-57:       独立装配 StateMachine 片段
event/handlers.py L51-52: 独立装配片段（register_all_handlers）
测试:                     直接 CognitiveRuntimeEngine(...) 不装配
```

**无统一冷启动入口 → 测试/API/CLI 各自手拼 → 主线断裂。**

---

## 三、施工方案

### B1: 抽统一装配入口
```
在 runtime/engine.py 增加 engine.bootstrap(registry=None, config=None) 方法:
  将 cli/engine.py L264-350+ 的装配逻辑（EventLog/Storage/Tracer/Guards/NATS/
  StateMachine+handlers/KG/BehaviorGraph/ToolRegistry/Learning 等）抽入，
  保留 try/except 降级语义（无依赖不崩）。
  cli/engine.py / cli/pool.py / 测试 / v3_session_api 统一改走 engine.bootstrap()
```

### B2: G1 蓝图退视图（切主路径）
```
BlueprintDecider → 纯视图层（build DAG + 校验 + 白盒编辑）✅ 已有
BlueprintExecutor 从"主执行器"退为"DAG 消费方":
  v3_session_api L202-205 改用 StateMachine 执行（或经 bootstrap 装配后的引擎）
  BlueprintExecutor 保留为视图校验/回放工具（不删, A17）
```

### B3: LLM 全链验证
```
test_linkage_quality_v2 改用 engine.bootstrap() 装配 → 走真 LLM 10 轮
验证 L1-L8 全绿（对话树/meta/模拟/策略/监控/泛化/画像稳定性）
```

---

## 四、验收门槛
```
1. engine.bootstrap() 可独立调用（CLI/测试/API 三处统一）
2. test_linkage_quality_v2 全链跑通（真 LLM）→ L1-L8 通过
3. v3_session_api 主路径不再直接 new BlueprintExecutor 当执行器
4. 既有回归不破（CLI 28/28、event、runtime 等）
```

---

## 五、恢复路径（压缩后）
```
读本文档 → STATE_HANDOFF_IMPLEMENTATION_20260804.md（M1-M9+9批完成态）
  → IMPLEMENTATION_PLAN_20260804.md → 开工 B1/B2/B3
```
