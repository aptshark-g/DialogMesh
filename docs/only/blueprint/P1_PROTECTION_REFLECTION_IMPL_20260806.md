# P1 批次施工记录 — 四保护 × 错误反思 × availability × MCP × 三层介入（2026-08-06）

> 前置: STATE_HANDOFF_BACKEND_BLUEPRINT_20260806.md（M1-M9 + 蓝图自增长闭环 P0 完成态）
> 本批完成交接 §六 全部后端 P1 项（G3 / E5 / E6 / P1-4 / P1-5 / P1-2）

---

## 一、本批完成（全部有测试, 先红后绿）

| # | 任务 | 设计依据 | 新增文件/改动 | 测试 |
|---|------|---------|--------------|------|
| G3 | LLM_DRIVEN 四保护 | FLOW_SELF_GROWTH §三 G3 | `blueprint/protection.py`（新）+ executor 接线 | 15 |
| E5 | 错误模式计数 → meta_advice | ERROR_META_REFLECTION §三 | `common/error_pattern.py`（新）+ executor/engine 接线 | 13 |
| E6 | 用户明示触发反思 | ERROR_META_REFLECTION §三.2 | engine.trigger_error_reflection | 并入 E5 |
| P1-4 | availability signal | FLOW_SELF_GROWTH §5.5 OpenClaw | `tools/registry.py` ToolAdapter.availability | 8 |
| P1-5 | MCP 工具接入 + 多工具并行 | FLOW_SELF_GROWTH §5.5 | `mcp/tool_bridge.py`（新）+ executor 并行 | 7 |
| P1-2 | 三层介入分级生效 | META_ARBITER §3.3 | `blueprint/intervention.py`（新）+ DecisionEventBus.intervene + engine API | 12 |

**合计新增 55 项测试; 全量 core/agent 1732 passed / 0 failed / 16 skipped（12:38）。**

---

## 二、G3 四保护（blueprint/protection.py）

```
PlanGate      — node.checkpoint 或高风险链（tool/engineering/metap）
                 → 执行前暂停 → resolver 三态:
                   approved（默认, 异步日志） / rejected（节点 error） /
                   adjust（替换节点, 同 RECOVERY 语义）
Budget        — 节点数 ≤ 7（对齐 ConstraintChecker）+ 执行期总执行次数
                上限 = 节点数 × 4（防 RECOVERY/PlanGate adjust 死循环）
LoopDetector  — 同一 node_id 重访 ≥ 3 → 强制 checkpoint（plan_gate 事件）
QualityGate   — 执行后纯算法评分（0.0-1.0, 零 LLM）: 节点 ok +1 /
                error/skipped +0 / unavailable +0.5; llm_reply 非空 +0.1;
                tool 失败 -0.15×N; 低分 → strategy_switch 事件（降级 HYBRID）
```

executor 集成:
- 执行循环内预算/重访/gate 检查（rejected 不执行该节点）
- `_apply_replacements()` 提取共用（RECOVERY + PlanGate adjust）
- 返回结果加 `quality` 字段（白盒可读）

设计要点: 四保护全部走 decision_bus 事件（可回看/可介入）; 无 resolver
默认 approved（低风险全自动+留痕, 高风险才阻塞）——符合 A16 快反馈。

---

## 三、E5/E6 错误反思（common/error_pattern.py）

```
classify_error(text)  — type_mismatch / encoding / serialization / zh_match / unknown
                        （关键词匹配, 纯算法零 LLM; json 优先于 encoding 防误判）
maybe_user_explicit(text) — "反复出现/又失败了/每次都/老出错..." → E6 触发

ErrorPatternTracker:
  record(error_type, example) — 滑动窗口（默认 50）计数; 跨阈值瞬间
    （prev < 3 ≤ count）→ 写 meta_advice 事件（status=proposed, 可回看）
  explicit_trigger()          — 用户明示 → actor=user, 最高优先级反思
```

接线:
- executor: 节点 error → `record(classify_error(err), example)`（自动反思源）
- engine `_init_whitebox`: 装配 `_error_pattern`（绑定 decision_bus）
- engine.trigger_error_reflection(text) — E6 显式触发（API/CLI 可调）

---

## 四、P1-4 availability signal（tools/registry.py）

ToolAdapter 新增 `availability` 条件:
```
{"env": ["GITHUB_TOKEN"], "config": ["gateway.url"], "auth": True, "note": "..."}
```
- `availability_reason(tool)` — 空串=可用; 非空=原因（disabled/missing env/
  missing config/auth required）
- discover / list_all（默认）/ resolve 全部过滤不可用工具（resolve 抛明确错误）
- ToolRegistry.set_config / set_auth 注入（engine/bootstrap 装配）
- status 加 `available` 标记（白盒）

设计对齐: OpenClaw descriptor + availability signal —— LLM 只看到当前
条件下可用的工具（auth/config/env 条件可见性）。

---

## 五、P1-5 MCP 工具接入（mcp/tool_bridge.py）

缺口: 既有 mcp/integration.py 只把外部 MCP 工具注册进 planning 侧
ToolRegistryBridge（tool_registry.registry）; blueprint 执行侧
（core.agent.tools.registry.ToolRegistry）从未接入。

新增:
- `MCPToolAdapter` — ToolAdapter 子类, handler 同步桥接 async
  client.call_tool（每次调用独立 event loop, 防线程串扰）
- `register_mcp_tools(adapter, server_label, tools)` — 注册进核心
  ToolRegistry, 名称 `mcp_{server}_{tool}`, availability.env 按连接状态
- `sync_discover_and_register` — 从 adapter 缓存便捷注册

多工具并行（executor）: tool 节点 `params.parallel = [{tool, args}, ...]`
→ ThreadPoolExecutor 并发执行（上限 5）→ 结果聚合
`{tool_results, errors, summary}`, status=ok/partial/error。

---

## 六、P1-2 三层介入分级（blueprint/intervention.py）

```
RiskClassifier.classify_kind(kind, dimension, reason):
  plan_gate → HIGH（同步 PlanGate）
  strategy_switch / meta_advice → MEDIUM（异步 + 通知, PR review）
  user_correction → LOW（用户修正最权威, 直接留痕）
  关键词升级: write/delete/pay/写文件/删除/不可逆 → HIGH
RiskClassifier.classify_node(node):
  checkpoint=True 或 chain ∈ HIGH_RISK_CHAINS → HIGH

InterventionRouter.route() — 统一决策事件写入:
  low → status=applied（CHANGELOG 语义）
  medium → status=proposed（不阻塞执行, 可 approve/reject）
  high → status=proposed + sync_required=True
approve()/reject() — DecisionEventBus.intervene 回写
  （status 更新 + 追加 user_correction 评论事件, 回看可追溯）
```

接线:
- executor `_record_switch`（RECOVERY 策略切换）→ 走路由（medium → proposed）
- engine `_init_whitebox`: 装配 `_intervention`; 暴露
  intervention_approve / intervention_reject（前端/API 可调）

---

## 七、环境/回归

- 全量 core/agent（排除 slow）: **1732 passed / 0 failed / 16 skipped**（12:38）
- 相关套件: blueprint 77 / common 30 / tools 8 / mcp 32 / runtime+event 81 全绿
- 已知非致命: state.json 写权限警告（.dialogmesh）
- git 改动未提交（按惯例）; C:\tmp 无本批临时文件

## 八、剩余（阶段 B / 前端）

- P1-1 前端变更日志视图（git log + PR review 风格）
- P1-6 前端绑定（139 文件接真数据, 阶段 B）
- P1-3 元认知热路径监视（Hot/Warm/Cold 分层, Rust 化前置）
- MCP 多工具并行的前端暴露 / CLI 命令补全

