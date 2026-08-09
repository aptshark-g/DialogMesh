# 压缩交接 — 后端完备性 + 蓝图自增长闭环（2026-08-06）

> 状态: 压缩恢复唯一入口（本批终态 + 已知内容 + 待办 + 环境）
> 恢复路径: 读本文档 → RECOVERY_PLAN_20260803.md（顶部已同步）→ 开工剩余

> **2026-08-06 P1 批次更新（后端 P1 全部完成）:
> 施工记录 = `docs/only/blueprint/P1_PROTECTION_REFLECTION_IMPL_20260806.md`
> 完成: G3 四保护（PlanGate/Budget/LoopDetector/QualityGate, protection.py +
> executor 接线）/ E5-E6 错误反思（error_pattern.py + engine 触发）/
> P1-4 availability（ToolAdapter.availability, discover/list_all/resolve 过滤）/
> P1-5 MCP 工具接入（mcp/tool_bridge.py + tool 节点多工具并行）/
> P1-2 三层介入（intervention.py + DecisionEventBus.intervene + engine API）。
> 全量 core/agent: 1732 passed / 0 failed / 16 skipped（净增 55 项新测试）。
> 剩余: P1-1 前端变更日志 / P1-3 热路径监视 / P1-6 前端绑定（阶段 B）。**

---

## 一、本批终态（实测）

### 测试
- **全量 core/agent: 1677 passed / 0 failed / 16 skipped**（13:12）
- 蓝图 44/44 + common 17/17 + statemachine 13/13 + tools 回归
- 真 LLM 全链: linkage_quality_v2 1/1（239s）+ v3_session_api 端到端通

### 本轮新增测试
| 文件 | 覆盖 | 数 |
|---|---|---|
| `blueprint/tests/test_decision_event.py` | 决策事件 schema/双写/回看/介入 | 8 |
| `blueprint/tests/test_recovery_switch.py` | RECOVERY 执行期切换 | 3 |
| `blueprint/tests/test_meta_side_effect.py` | check_degradations 副作用化 | 3 |
| `blueprint/tests/test_tool_node.py` | tool 节点 + T2 校验 + T3 回灌 | 6 |
| `blueprint/tests/test_tool_react.py` | T4 ReAct 子循环 | 4 |
| `blueprint/tests/test_attribution.py` | T5/T6 归因 | 7 |
| `blueprint/tests/test_learn_template.py` | G2 模板进化 | 4 |
| `common/tests/test_text_utils.py` | text_utils 基础设施 | 17 |

---

## 二、本批施工完成（全部已验证）

### 蓝图主线（前一轮, 已含在全量绿）
- 5 模板重构为订阅表语义（同 Tick 并行 + 工具/安全约束参数）
- `run_dag` 同 Tick 并行（ThreadPoolExecutor）+ async 段
- PCRRouterV2.warm_up / PathState 三处归一 / gateway 异常降级 /
  engine._persist_state / telemetry 日志隔离 / DPO loop 迁移
- pcr 测试迁移 DualTrack（38/38）+ compiler 迁移 M3 语义（11/11）

### META_ARBITER P0（元认知仲裁 × 异步介入）
- **决策事件** `blueprint/decision_event.py`（EventLog+Journal 双写）
- **RECOVERY 执行期切换**（executor recovery_hook 中途换子图）
- **check_degradations 副作用化**（真实改权重 + 事件）

### FLOW_SELF_GROWTH（业务流自增长）
- **tool 链节点** + converge 注入完整工具 schema（LLM 决策工具）
- **T2 调用前校验** + **T3 结果回灌 llm_reply**
- **G2 LEARNED_TEMPLATES**（执行成功含 tool → 沉淀模板, match 优先）

### ERROR_META_REFLECTION（基础设施）
- **`common/text_utils.py`**: safe_str / to_json_safe / zh_keyword_match /
  normalize_text
- **discover 接 zh_keyword_match** + builtin 工具中文关键词

### BIDIRECTIONAL_ATTRIBUTION（双向归因）
- **T4 ReAct 子循环**（tool 节点 max_steps, LLM 决策重试）
- **T5 归因字段**（attribution: plan/constraint/data/tool）
- **T6 attribution_hook 回流**

---

## 三、设计定案（4 份新文档, 压缩后必读）

| 文档 | 内容 |
|------|------|
| `blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md` | 元认知仲裁 = 微观↔宏观双向纽带; 异步介入 = GitHub 更新日志式; 三层介入分级 |
| `blueprint/FLOW_SELF_GROWTH_20260806.md` | 业务流三来源（种子/生成/沉淀）; 行业调研（Hermes/OpenClaw）; G1-G3 规划 |
| `blueprint/ERROR_META_REFLECTION_20260806.md` | 3 类反复问题（编码/匹配/序列化）; text_utils; 错误模式→元认知反思 |
| `blueprint/BIDIRECTIONAL_ATTRIBUTION_20260806.md` | 偏差=养分; 双向归因闭环; T4-T6 施工分层 |
| `blueprint/META_ARBITER_IMPL_PROGRESS_20260806.md` | 施工记录（P0 + 追加批次） |

---

## 四、核心设计论断（压缩后恢复必读, 与代码对应）

1. **蓝图 = 任务地图（宏观无环）; 执行层 = 复杂网络（微观有环）**
   - 蓝图 DAG 无环（可验证/可审计）; 学习环跨请求有环（自适应）
2. **元认知树图 = 双向纽带（内化仲裁者, 非翻译层）**
   - 微观偏差（超时/质量）→ 元认知裁决 → 宏观计划变更
   - RECOVERY 执行期切换 = "手搓超时→换 forge" 场景底座
3. **用户介入 = 异步可回看（GitHub 更新日志式）**
   - 决策变更 = 事件（EventLog + Journal 双写）
   - 低风险异步日志 / 中风险 approve / 高风险同步 PlanGate
4. **业务流不靠人工补, 靠"生"**
   - LLM_DRIVEN 生成 → 执行 → 成功沉淀 LEARNED_TEMPLATES
   - 工具 = 第一等公民（descriptor 注入, LLM 语义决策）
5. **偏差 = 养分（双向归因）**
   - 工具失败 → attribution（plan/constraint/data/tool）→ 回流对应层

---

## 五、已知环境/坑（压缩后必读）

- **网关**: Switch 8080, deepseek active+healthy
  - `DEEPSEEK_API_KEY=sk-a471baac...`（环境变量, 不入库）— 新 shell 需重设
- **启动**: `start.bat`（gateway.exe + v6_app :8000 + frontend preview）
  - start.bat 结构未过时（B8-4 唯一内核）
- **依赖**: pytest-timeout 2.4.0 已装; chromadb/websockets 因 numpy dist-info
  损坏未装（UnifiedStore/EventBus 内存版覆盖同等能力）
- **PowerShell 管道转码坑**: heredoc `| python -` 中文变 `????`
  - 对策: 中文输入一律走 `apply_patch` 写临时 .py 文件再执行, 不裸管道
- **pytest 包名冲突**: 顶层 `tests/` 与 `core/agent/xxx/tests/` 混跑会
  `No module named 'tests.xxx'` — 分开跑（先 core/agent, 再顶层 tests/）
- **conftest assertrepr**: 对 list/None 的 `in` 断言会崩（`right in left`）
  - 对策: 测试断言用 `"x" in " ".join(list)` 绕开
- **state.json 写权限**: `C:\Users\APTShark\.dialogmesh\state.json` 非致命警告

---

## 六、剩余待办（P1）

| # | 任务 | 内容 |
|---|------|------|
| G3 | LLM_DRIVEN 四保护 | PlanGate / LoopDetector 未接（Budget 已有 MAX_NODES=7） |
| E5 | 错误模式计数 → meta_advice | 滑动窗口 + 阈值 → 反思事件 |
| E6 | 用户明示触发反思 | "反复出现" → 最高优先级反思 |
| P1-1 | 前端变更日志视图 | git log + PR review 风格 |
| P1-2 | 三层介入分级生效 | 低/中/高风险路由 |
| P1-3 | 元认知热路径监视 | Hot/Warm/Cold 分层 |
| P1-4 | availability signal | auth/config/env 条件工具可见性 |
| P1-5 | MCP 工具接入 / 多工具并行 | OpenClaw kind=mcp 式 |
| P1-6 | 前端绑定（阶段 B） | 前端 139 文件接真数据 |

---

## 七、git 状态

- 改动未提交（按惯例, 压缩前不提交）
- 本轮改动文件: 蓝图 executor/engine/llm_dag_builder/skill_registry/models/
  meta_feedback/decision_event（新）/tools/registry+builtin/common/text_utils（新）/
  runtime/engine/api/v3_session_api/statemachine/event tests 等

---

## 八、恢复三步

1. 读本交接文档（已知内容 + 待办 + 坑）
2. 读 RECOVERY_PLAN_20260803.md 顶部（已同步本批）
3. 开工: 建议先 G3（四保护, LLM_DRIVEN 可安全跑）或 E5（错误反思闭环）
