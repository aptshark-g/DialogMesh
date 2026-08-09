# 蓝图薄点审计（2026-08-08 具体核查, 用户要求"对具体内容去查"）

> 触发: 用户判断"蓝图很薄, 很多没使用起来" + 第一版功能核对
> 方法: 引用计数 + 主路径调用点逐项核查（非"存在即使用"）

---

## 一、引用计数（蓝图域 17 模块）

| 模块 | 全库引用 | 状态 |
|---|---|---|
| engine / models / tracer / executor | 1564/532/133/112 | ✅ 主路径 |
| decider / intervention | 32/30 | ✅ 主路径 |
| skill_registry / protection / learning_bridge | 25/13/13 | 🟡 部分 |
| decision_event / heuristic_inventory | 11/9 | 🟡 |
| llm_dag_builder | 4 | ✅ 经 engine.build 主路径 |
| automation | 0 | 🔴 **完全孤儿** |
| heuristic_distiller | 3 | 🟡 经 LearningBridge |
| meta_feedback / skill_lifecycle / permission_engine | 3/3/1 | 🟡/🔴 见下 |

## 二、主路径核查（引用 ≠ 使用）

### ✅ 已接通（真用）
- **蓝图生成**: `v3_session_api.py:302/443 engine.build(content, intent)` →
  LLMDAGBuilder（E2 实测: 规划 JWT → task_graph 响应）
- **执行**: `BlueprintExecutor.execute` → `_handle_tool` → ToolRegistry
  （含 P1-5 多工具并行、T4 ReAct、RECOVERY、GAP-5 taint）
- **蒸馏**: `learning_bridge.py:251 engine.scan(...)` → HeuristicDistiller
  （原料 = trace_store, 有数据流）

### 🔴 生产未接线（代码在, 测试在, 主路径没接）
1. **PermissionEngine（C1-C4 权限）**: 实现完整（RiskClass 4 级 + shell
   操作符 + 写根限制 + standing rules）, 12/12 测试含集成; 但生产构造点
   `decider.py:29` / `gates.py:230` 都是 `BlueprintExecutor()` **无
   gate_resolver** → 权限判定只在测试生效, 工具执行无权限门
2. **automation.py（定时自动化）**: 全库 0 引用 — 完全孤儿
3. **skill_lifecycle**: engine 实例化（:803）但只 `skill_lifecycle_report`
   （:844 报告）— 活性裁剪/归档从未执行, "只增不减"（对标 Hermes curator
   差距未补）
4. **meta_feedback**: engine 无实例化调用（仅 __init__ 导出）— 未接

## 三、结论（用户判断成立的具体化）

蓝图 = **生成+执行主路径通, 但周边能力未接线**:
- "基本能力"权限（C1-C4）= 实现完成但生产没挂 — **第一版必须接**
- 自动化/技能活性/元认知反馈 = 设计+代码存在, 消费方断流 — v2 补

## 四、修复（第一版范围）

### F1. 权限引擎接线（生产生效）
- ✅ `decider.py` / `v3_common/gates.py` 构造 executor 默认挂权限
  gate_resolver（PermissionEngine → PlanGate resolver 同构）
- ✅ 验收实测: write 出根目录 rejected / shell `&&`、`|` rejected /
  write 根内 approved / echo approved / pcr approved
- ✅ 测试 20/20 绿（permission_engine + decision_event）
- 注: 普通 write/exec（needs_user）开发模式放行; 真危险
  （出根/链式 shell/只读模式）拦截 — 第一版语义

### F2. skill_lifecycle 至少跑一次（活性报告 + prune 入口）
- engine 启动时调 `skill_lifecycle_report(dry_run=True)` 落报告
- 留 v2: 自动 prune/归档

## 五、v2 待补（记录不施工）
- automation 定时自动化（OpenWorker ScheduledTask 对标）
- meta_feedback 接入执行后复盘
- 蓝图模板库扩充（LLM 生成 + 成功沉淀已通, 覆盖率靠使用增长）
