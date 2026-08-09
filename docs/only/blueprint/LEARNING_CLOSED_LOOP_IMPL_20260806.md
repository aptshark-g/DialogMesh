# 学习闭环施工记录 — GAP-D2/D1/D5（2026-08-06）

> 依据: `COMPLETENESS_GAP_INVENTORY_20260806.md` §A（第一批施工）
> 状态: 三项全部完成并验证（12 项新测试 + 全量 1744 passed / 0 failed / 16 skipped）

---

## 一、GAP-D2: learn_blueprint 生产注入 ✅

**问题**: executor.learn_hook 参数存在但生产（v3_session/engine/bootstrap）
从不传 → LEARNED_TEMPLATES 只在测试里沉淀。

**修复**:
- 新增 `blueprint/learning_bridge.py` — `LearningBridge.learn_from_execution(
  dag, intent, request_id, success)`: 生产学习统一入口
  - ① `registry.learn_blueprint`（含 tool 节点才沉淀, 已有逻辑）
  - ② 成功轨迹 → `ExecutionTraceStore`（蒸馏原料）
  - ③ 周期触发批量蒸馏（默认 5 分钟）
- `BlueprintEngine.__init__` 加 `registry` 注入参数 — 本地 BlueprintEngine
  与 runtime engine 共享同一 SkillRegistry（match/learn 不分叉）
- runtime engine `_init_whitebox` 装配 `_learning_bridge` + `_skill_lifecycle`,
  暴露 `learn_from_execution()` / `skill_lifecycle_report()`
- `v3_session_api` Phase 3.5: run_dag 成功后注入
  `_eng.learn_from_execution(dag, intent, msg_id, success=True)`
  （共享 registry 传入本地 BlueprintEngine）

## 二、GAP-D1: 蒸馏原料管道 ✅

**问题**: DistillationEngine.scan() 全库零数据流。

**修复**:
- `LearningBridge.ExecutionTraceStore` — 环形轨迹存储（max 200）,
  实现 `get_sequences()` 接口（DistillationEngine behavior_store 契约）
- `LearningBridge.distill_once()` — trace_store → scan(behavior_store) →
  `_a24_verify()`（A24 可逆推验证: coverage 60-80%, 100%=过拟合拒绝,
  0%=没学到拒绝）→ 达标候选 → `_promote_candidate()` 沉淀为
  LEARNED_TEMPLATES（带 DISTILLED provenance）
- 触发: 每 `_distill_interval`（默认 300s）或测试可置 0 强制

## 三、GAP-D5: 技能生命周期 ✅

**新增** `blueprint/skill_lifecycle.py` — LEARNED_TEMPLATES 活性状态机:
```
active → stale（N 天未用, 默认 14）→ archived（M 天, 默认 30）
       → pruned（P 天, 默认 90; 从 LEARNED_TEMPLATES 移除, 元数据保留）
```
- 元数据平行表（created_at/last_used/use_count/state/pinned/referenced_by）,
  不侵入 BlueprintDAG
- `register()`（learn_blueprint 沉淀时） / `touch()`（match 命中时, 复活）/
  `pin()`（用户固定） / `add_reference()`（cron/外部引用保护）
- `apply_transitions()` — 确定性迁移（零 LLM, 与 Hot/Warm/Cold 同构）
- `report(dry_run)` — dry-run 预测报告（对齐 Hermes curator 语义）
- 接线: SkillRegistry.set_lifecycle()（learn_blueprint 登记 + match touch）;
  engine 装配共享实例

## 四、验证

- 新增 `blueprint/tests/test_learning_bridge.py` 12 项:
  D2 生产沉淀/跳过纯链/失败不收集; D1 trace→distill→A24 边界→沉淀;
  D5 状态机/迁移/pin+引用保护/dry-run/engine 装配/生产入口
- 新增 `blueprint/tests/test_production_learning.py` 3 项（**生产路径契约测试**,
  用户质疑"测试浅层"后补）:
  - T1 源级契约: v3_session_api 必须调 learn_from_execution + 传共享 registry
  - T1 BlueprintEngine registry 注入参数契约
  - T2 完整生产路径: 真实 _create_engine_instance（bootstrap）→ run_dag →
    learn_from_execution → 断言 LEARNED_TEMPLATES 真增长 + 蒸馏原料真收集
- 生产核查（临时脚本, 已删）: shared registry identity=True /
  lifecycle attached=True / LEARNED grew before=0 after=1 / trace_store=1
- 相关套件: blueprint+planner+runtime 118/118
- 全量 core/agent: **1744 passed / 0 failed / 16 skipped**（14:16）

## 四点五、反思记录（用户质疑: 测试是否浅层 / 完备为何还有问题）

- **质疑成立**: 原 12 项是模块级, 验证"方法可用 + 装配", 未验证
  "生产请求路径真的调用"（v3_session_api → run_dag → learn 注入可达性）。
- **结构性教训**: 模块测试隔离 = 各组件自测通过, 但**跨层接线无测试**。
  learn_blueprint 测试测方法本身, 无人测"生产引擎 run_dag 后 registry
  真多一条"——1732 绿掩盖接线断裂的根本原因。
- **根治**: 生产路径契约测试（源级断言 + 完整 bootstrap 端到端）,
  防"方法可用但生产不调"回归。此类测试应推广到其他"测试绿≠生产通"
  的高风险接线点（executor 占位链/蒸馏/介入路由）。
- 顺带确认: 生产 bootstrap 真实挂 state_machine + learning_bridge,
  注入路径真实可达; NATS 连接超时是已知环境噪声（已有 timeout=5 降级,
  非功能缺陷）。

## 五、改动文件

- 新增: `blueprint/learning_bridge.py` / `blueprint/skill_lifecycle.py` /
  `blueprint/tests/test_learning_bridge.py`
- 修改: `blueprint/skill_registry.py`（lifecycle 挂载 + touch）/
  `blueprint/engine.py`（registry 注入）/ `runtime/engine.py`（装配 +
  learn_from_execution + lifecycle_report）/ `api/v3_session_api.py`（生产注入）

## 六、剩余（缺口清单后续批次）

- 第二批: GAP-E1/E2（meta/behavior 占位真接线）+ GAP-1（权限引擎细化）+
  GAP-2（定时自动化持久实体）
- 第三批: GAP-O1/O2（memory/coordinator 归位）+ GAP-O3（PCR 模型统一）+
  GAP-P1（控制面板参数化）
