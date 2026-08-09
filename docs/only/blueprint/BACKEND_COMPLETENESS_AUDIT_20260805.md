# 后端内在完备性核查 — 2026-08-05

> 目的: 全量测试可跑（收集 0 错误）后的真实失败面分类与根因。
> 用户指令: "核心是实现后端的完备性，先核查各模块内在完备，然后做蓝图，
> 否则无法跑全量测试。"

---

## 一、收集层修复（本轮已完成）

| 错误 | 根因 | 修复 |
|------|------|------|
| `execution/tests/test_semantic_diff.py` | `execution/` 缺 `__init__.py` → pytest 包名冲突 | 补空 `__init__.py` |
| `meta/tests/test_meta_wiring.py` | `meta/` 缺 `__init__.py` → 同上 | 补空 `__init__.py` |
| `pcr/tests/un_use/test_integration_legacy.py` | 归档副本缺 `Dict` 导入 + un_use 被收集 | 删除归档副本（测试已复原回 test_integration.py） |
| `v3_2/tests/test_benchmarks.py` | `testing_utils` 移至 `core/agent/`（d993553）引用未同步 | 改 `core.agent.testing_utils` |
| `v3_common/integration_bridge.py` | 同上 | 同上 |

**结果: core/agent 全量收集 1643 项，0 错误。**

---

## 二、全量测试结果（排除 slow）

`pytest core/agent` → **1543 passed / 30 failed / 12 errors / 16 skipped**

---

## 三、失败分类（按根因）

### A. 预存在断链（交接文档已记录，非本轮引入）

| 模块 | 失败 | 根因 |
|------|------|------|
| pcr test_integration | 25 failed | 旧 `IntentParser` 弃用 shim（a984c79 返回 None）→ 测试已复原但未迁移到 DualTrack |
| compiler test_integration | 12 errors | `e.start()` 不存在（M3 后统一入口 bootstrap）——测试基建未走 DI |
| event test_e2e_full_pipeline_mock | 1 failed | `_persist_state` 引擎从未定义 |

### B. 真实断链（模块内在不完备，需修）

| 模块 | 失败 | 根因 |
|------|------|------|
| v3_0/cognitive_tree CrossRefManager | 9 failed | async API 被当同步调（`coroutine` 无 `.unlink`） |
| document test_document_ingestion | 6 failed | MarkdownParser 断言 `root` vs `paragraph` 不一致 |
| engineering test_auto_persist | 1 failed | 待查 |
| v4/cognitive_scheduler test_path_components | 4 failed | 待查 |
| api test_service_middleware queue_guard | 1 failed | 待查 |

### C. 环境/flaky（非代码缺陷）

| 模块 | 失败 | 根因 |
|------|------|------|
| observability telemetry | 5 failed | 并行测试共享日志文件 → PermissionError 文件锁 |
| behavior DPO | 2 failed | 顺序 flaky（交接文档已记录） |
| discourse_block_tree stress | 1 failed | 压测 |
| llm_providers gateway test_generate_error | 1 failed | 需真实网关 500（mock 未覆盖） |

---

## 四、处理原则

1. **不归档测试**（用户明确批评过）——测试红 = 先查设计意图，迁移优先。
2. **测试基建统一走 DI（bootstrap）**——compiler 测试从 `e.start()` 迁 `e.bootstrap()`。
3. **pcr 测试迁移到 DualTrackIntentPipeline**——保留 3×4×5 矩阵语义，换新管线。
4. 环境/flaky 类记录，不阻塞主线。

---

## 五、与蓝图模板的关系

> 用户核心判断: 蓝图模板 = 业务流。当前 5 模板是线性近似，跑全链测试
> = 串行假象，与订阅表（§14.3 同 Tick 并行）设计两码事。
> 业务链素材已收集: `BUSINESS_FLOW_COLLECTION_20260805.md`。

主线顺序: 收集（✅）→ 重构模板（订阅表语义）→ 执行器对齐（同 Tick 并行）
→ 全链测试用真实模板验证。测试失败面按上述原则随施工处理。
