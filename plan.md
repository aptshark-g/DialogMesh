# DialogMesh v3.0 测试质量修复计划

## 背景
测试全部通过（127/127），但质量仅 3/10。运行时暴露大量实际问题：响应乱码、意图退化、会话同步失败、LLM 接口断裂、虚假断言泛滥。本次修复覆盖 P0-P2 全部问题。

## 技能加载
- **Stage 1（诊断）**：`diagnostic-first-debugging` — 诊断优先
- **Stage 2（修复代码）**：`coder` — 修复代码 bug
- **Stage 3（修复测试）**：`coder` — 重写测试断言
- **Stage 4（补充测试）**：`coder` — 新增测试覆盖
- **Stage 5（验证）**：`coder` — 运行测试并验证

---

## Stage 1：诊断根因（并行）

### 任务 1.1：诊断响应乱码根因
- 定位 `answer` 字段的来源：从 Orchestrator → AnswerComposer → 最终输出
- 检查编码链：unicode 处理、bytes 解码、字符串拼接
- 输出：乱码产生的具体代码路径和修复方案

### 任务 1.2：诊断意图退化根因
- 检查 `AlgorithmEngine.parse_intent` 的 `scan` 关键词匹配逻辑
- 检查 `orchestrator.py` 中 intent 被覆盖或丢弃的位置
- 检查 E2E 测试运行日志中 `intent=unknown` 的原因
- 输出：意图从 SCAN_MEMORY 退化为 unknown 的具体原因

### 任务 1.3：诊断会话同步根因
- 检查 `SystemBootstrap` 创建的 `ContextManager` 与 `Orchestrator` 使用的 `ContextManager` 是否为同一实例
- 检查 `orchestrator.process_turn` 中 session 创建/查找逻辑
- 输出：Session not found 的具体原因和修复方案

### 任务 1.4：诊断 ProviderManager 接口断裂
- 检查 `ProviderManager` 类是否缺少 `generate_async` 方法
- 检查调用链中哪个组件期望 `generate_async` 但实际没有
- 输出：接口断裂的具体位置和修复方案

---

## Stage 2：修复代码 Bug（顺序，依赖 Stage 1）

### 任务 2.1：修复响应乱码
- 根据 Stage 1.1 的诊断，修复编码问题
- 确保 answer 字段始终返回可读字符串

### 任务 2.2：修复意图退化
- 根据 Stage 1.2 的诊断，修复规则引擎或意图传递逻辑
- 确保 `scan` 关键词被正确识别为 `SCAN_MEMORY`

### 任务 2.3：修复会话同步
- 根据 Stage 1.3 的诊断，修复 ContextManager 实例共享问题
- 确保 Orchestrator 创建的 session 能被 ContextManager 访问

### 任务 2.4：修复 ProviderManager 接口
- 根据 Stage 1.4 的诊断，添加 `generate_async` 方法或修复调用链
- 确保 LLM 调用路径在测试配置下也能正确降级

---

## Stage 3：修复测试质量（并行，依赖 Stage 2）

### 任务 3.1：重写端到端测试（TestEndToEnd）
- 将 `test_memory_scan_workflow` 的断言从"存在性"改为"精确值"
- 断言每轮对话的预期意图类别（SCAN_MEMORY、READ_MEMORY）
- 断言 answer 包含预期内容（如扫描结果、地址值）
- 断言 task_graph 节点有正确的语义
- 断言多轮上下文传递（如第二轮读取的地址与第一轮相关）

### 任务 3.2：重写编排器集成测试（TestOrchestrator）
- 将 `status in ("ok", "fallback")` 改为 `status == "ok"`（或精确匹配预期状态）
- 将 `answer is not None` 改为具体答案验证（或至少验证内容不是乱码）
- 将 `task_graph is not None` 改为节点内容验证
- 移除所有 `print()` 调试语句，替换为断言

### 任务 3.3：修复服务层虚假断言
- 将 `test_session_manager` 中 `add_user_message` 和 `add_intent` 的 `assert_true(True, ...)` 替换为验证副作用
- 将 `test_websocket_manager` 的 `assert_true(True, ...)` 替换为生命周期验证或移除
- 将 `test_response_composer_in_agent_service` 的格式白名单检查改为精确格式验证

---

## Stage 4：补充测试覆盖（并行，依赖 Stage 3）

### 任务 4.1：新增 LLM 路径冒烟测试
- 创建一个使用 mock LLM provider 的测试
- 验证 `enable_intent_llm=True` 时，融合引擎能正确接收 LLM 输出
- 验证 LLM 高置信度时选择 LLM 源

### 任务 4.2：新增负面测试
- 空字符串输入：`process_turn(session, "")` 应返回 `NEEDS_CLARIFICATION`
- 超长输入：> 1000 字符输入应被截断或拒绝
- 关闭后调用：`process_turn` 在关闭后应返回 `error` 状态（已验证，确认即可）
- 非法 session_id：`get_session("not-exist")` 应返回 None

### 任务 4.3：新增格式路由验证测试
- 验证 `novice` 用户 → `explanatory` 或 `tutorial` 格式（精确等值，不是白名单）
- 验证 `expert` 用户 → `brief` 或 `balanced` 格式
- 验证显式请求格式覆盖（`requested_format=TUTORIAL` 应生效）

---

## Stage 5：验证（顺序，依赖 Stage 4）

- 运行全部修复后的测试
- 确认所有新断言通过
- 确认无新引入的 regression
- 输出最终质量报告

---

## 文件清单

| 阶段 | 目标文件 |
|------|----------|
| Stage 1.1 | `core/agent/v3_0/orchestrator/answer_composer.py` (or similar) |
| Stage 1.2 | `core/agent/v3_0/orchestrator/orchestrator.py`, `algorithm_engine.py` |
| Stage 1.3 | `core/agent/v3_0/orchestrator/bootstrap.py`, `orchestrator.py` |
| Stage 1.4 | `core/agent/v3_0/llm/provider_manager.py` (or similar) |
| Stage 3.1 | `core/agent/v3_0/orchestrator/tests/test_orchestrator.py` |
| Stage 3.2 | `core/agent/v3_0/orchestrator/tests/test_orchestrator.py` |
| Stage 3.3 | `core/service/v3_0/tests/test_service.py` |
| Stage 4.1-4.3 | `core/agent/v3_0/orchestrator/tests/test_orchestrator.py`, `core/service/v3_0/tests/test_service.py` |

---

## 预期输出

- 修复后的代码文件（解决乱码、意图退化、会话同步、接口断裂）
- 重写后的测试文件（强断言、无虚假断言、无 print）
- 新增的测试文件（LLM 路径、负面测试、格式路由）
- 最终验证报告：质量评分从 3/10 提升到 ≥ 7/10
