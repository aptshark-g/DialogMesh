# 元认知仲裁 × 异步介入 施工记录（P0, 2026-08-06）

> 设计: `META_ARBITER_ASYNC_INTERVENTION_20260806.md`
> 状态: P0 三项全部完成并验证（决策事件 8/8 + RECOVERY 3/3 + Meta 副作用 3/3）

---

## P0-1 决策变更事件 schema ✅

**新增** `core/agent/blueprint/decision_event.py`:
- `DecisionEvent` dataclass: kind/dimension/before/after/reason/actor/turn/comment/status/request_id/trace_id
- kinds: `strategy_switch` / `plan_gate` / `meta_advice` / `user_correction`
- `DecisionEventBus`: EventLog 持久化 + CorrectionJournal 双写 + 内存缓冲（500）
- `recent(limit, kind)`: git log 语义回看; `log()` 便捷单行

**装配**: engine `_init_whitebox` 挂 `_decision_bus`（每次刷新 attach 最新 EventLog/Journal）

**验证**: `test_decision_event.py` 8/8（schema/双写/回看/介入 rejected/engine 装配）

---

## P0-2 RECOVERY 执行期策略切换 ✅

**改动** `core/agent/blueprint/executor.py`:
- `__init__` 加 `recovery_hook` + `decision_bus`
- 节点失败（error status）→ hook 提供替换子图 → 替换进 DAG → 下游重跑
- 只移除失败节点自身, 下游依赖边重定向到替换节点
- 已完成上游保留（pcr/intent 不重跑）
- 切换写 `strategy_switch` 事件（回看基础）

**验证**: `test_recovery_switch.py` 3/3（替换成功/下游重跑/无 hook 保持错误语义）

---

## P0-3 check_degradations 副作用化 ✅

**改动** `core/agent/blueprint/meta_feedback.py`:
- `__init__` 加 `decision_bus`
- degrade: 真实降所有意图下该策略权重 + 写 strategy_switch 事件
- promote: 真实恢复权重 + 写事件
- 无 bus 安全降级

**验证**: `test_meta_side_effect.py` 3/3（权重真实变化/事件/安全）

---

## 生产接线 ✅

- `BlueprintEngine(decision_bus=...)`: 构建期可记录
- v3_session_api: 从 `get_engine()._decision_bus` 传入
- 端到端: engine.bootstrap → decision_bus → strategy_switch 事件 → recent 回看 ✅

---

## 回归

- 蓝图 + kernel: 63/63 全绿
- 决策事件 8/8 + RECOVERY 3/3 + Meta 副作用 3/3

---

## 下一步（P1, 待开工）

- P1-1 前端变更日志视图（git log + PR review 风格, 回看/建议/否决/约束）
- P1-2 三层介入分级生效（低/中/高风险路由）
- P1-3 元认知热路径监视（Hot 轻量信号 → Warm LLM 评估 → Cold 深度复盘）

---

## 追加批次：FLOW_SELF_GROWTH + ERROR_META_REFLECTION + BIDIRECTIONAL_ATTRIBUTION（同日）

### G1+T1-T3 工具链路重构 ✅
- `CHAIN_IDS` 加 `tool`；executor `_handle_tool` 真执行 ToolRegistry
- converge 注入完整工具 schema（OpenClaw descriptor 式）→ LLM 决策工具+参数
- T2 调用前校验（工具存在 + 必填参数）
- T3 工具结果完整回灌 llm_reply 上下文
- 测试: test_tool_node.py 6/6

### E1-E2 基础设施 ✅（ERROR_META_REFLECTION）
- 新增 `core/agent/common/text_utils.py`: safe_str / to_json_safe /
  zh_keyword_match / normalize_text（17/17）
- discover 接 zh_keyword_match + builtin 工具补中文关键词
  （"查论文"→arxiv_search / "爬网页"→web_fetch 实测通过）

### T4 ReAct 子循环 ✅（BIDIRECTIONAL_ATTRIBUTION）
- tool 节点 `max_steps`（默认 3）: 失败/结果不足 → LLM 决策
  （改参数/换工具/完成），每步写 decision_bus 事件
- 超限 → error → 外层 RECOVERY 接管
- 测试: test_tool_react.py 4/4

### T5-T6 归因闭环 ✅
- DecisionEvent 加 `attribution`（plan/constraint/data/tool）
- 工具失败 → 事件带 attribution + attribution_hook 回流
- 测试: test_attribution.py 7/7

### G2 模板进化 ✅（业务流自增长核心）
- SkillRegistry 加 `LEARNED_TEMPLATES` + `learn_blueprint`
- 执行成功含 tool 节点 → 沉淀学习模板；match 时 LEARNED 优先
- executor `learn_hook` 执行成功触发
- 测试: test_learn_template.py 4/4

### 回归
- 蓝图+common+tools+statemachine: 65/65 全绿

### 剩余（P1, 待开工）
- G3 LLM_DRIVEN 四保护（PlanGate/LoopDetector 未接, Budget 已有）
- E5 错误模式计数 → meta_advice（滑动窗口 + 阈值）
- E6 用户明示触发反思
- availability signal（auth/config/env 条件工具可见性）
- MCP 工具接入 / 多工具并行
