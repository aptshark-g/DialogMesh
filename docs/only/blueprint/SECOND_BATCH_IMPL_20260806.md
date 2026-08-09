# 第二批施工记录 — GAP-E1/E2 + GAP-1 + GAP-2（2026-08-06）

> 依据: `COMPLETENESS_GAP_INVENTORY_20260806.md` §B/C（第二批）
> 状态: 三项全部完成并验证（32 项新测试; 全量 1776 passed / 0 failed / 16 skipped）

---

## 一、GAP-E1/E2: executor meta/behavior 占位真接线 ✅

**问题**: `_handle_meta`/`_handle_behavior` 是 `async`/`deferred` 占位,
事件有但无人消费（COMPLETENESS_GAP_INVENTORY §B）.

**修复**（`blueprint/executor.py`）:
- `_handle_behavior` → 真实调 `engine._run_behavior_brain(event)`:
  行为学习（预测评估/DPO 偏好/承诺识别/画像更新）+ 背景预测 +
  冷启动回退重模拟 + CausalPlanner.record_step（因果链）;
  无 engine → unavailable（不做伪数据）; 返回 brain stats
- `_handle_meta` → 真实调 `engine._run_meta_consume()`:
  QualityGate 评分/执行摘要写入 ExecutionTraceV3（元认知原料）+
  MetaConsumer 消费（建议 → 审核队列, 每 5 轮闭环）;
  无 engine → unavailable
- 无 engine 时的语义从"deferred 占位"改为"unavailable 显式缺组件"（对齐
  无伪数据原则）

## 二、GAP-1: 权限引擎细化 ✅

**问题**: P1-2 三层介入概念等价但粒度粗（无 shell 操作符检测/路径根限制/
standing rules/5 模式门控）— 对标 OpenWorker risk.py+permissions.py.

**新增** `blueprint/permission_engine.py`（OpenWorker 同构）:
- `RiskClass` 4 级: read / write_local / exec / external
- `Mode` 5 档: discuss / plan / interactive / auto / custom
- `classify_tool`: 名表（write_file/apply_patch→write_local, run_shell→exec）
  + metadata（risk/requires_approval）+ read 兜底
- `PermissionEngine.evaluate(tool, args, metadata)` → Decision{allowed,
  needs_user, reason, rule}:
  - 写路径可写根限制（多根 + writable 标志, 相对路径解析已修）
  - shell 操作符检测（`;` `|` `>` `<` `$(` 链式命令 → 强制审批,
    防白名单逃逸 `git status && rm -rf ~`）
  - 命令白名单 token 级精确前缀（防 `git statusfoo`）
  - 会话白名单 + 任务级 standing rules（tool → target 精确授权, 可审计）
- 与 InterventionRouter 关系: 本引擎 = 工具调用前安全门;
  InterventionRouter = 决策变更后记录/介入路由（互补）

**集成**: executor PlanGate resolver 可接 PermissionEngine（测试验证
write_file 高风险调用被 reject）。

## 三、GAP-2: 定时自动化持久实体 ✅

**问题**: 蓝图无定时层; OpenWorker 的 ScheduledTask/TaskRun 是完整持久实体
（自有线程/运行记录/续跑/standing rules）.

**新增** `blueprint/automation.py`（OpenWorker scheduler+models 同构）:
- `AutomationSchedule`: interval / cron（5 字段轻量解析）/ once
- `AutomationTask`: 持久实体（title/instructions/workspace/own session_id/
  always_allowed_tools standing rules/enabled/next_run/run_count/max_runs）
- `TaskRun`: 单次运行记录（status/result/error/trigger/续跑 session_id）
- `AutomationStore`: JSON 持久化（data/automations.json）+
  due/advance（next_run 计算）+ runs 历史
- `AutomationScheduler`: 后台线程 tick（默认 30s）+ run-once-catch-up
  （停机错过的启动补跑）+ skip-on-overlap（上一轮未完成不叠加）+
  spawn 执行不阻塞调度循环（runner 注入, 对齐 OpenWorker Runner 契约）

## 四、验证

- 新增测试 32 项:
  - `test_executor_wiring.py` 7（E1/E2 真接线/无 engine 降级/DAG 完整执行）
  - `test_permission_engine.py` 12（风险分类/模式/路径根/shell 操作符/
    standing rules/executor 集成）
  - `test_automation.py` 10（schedule/store 持久化/catch-up/overlap/错误记录）
- 相关套件: blueprint+planner+runtime+behavior 173/173
- 全量 core/agent: **1776 passed / 0 failed / 16 skipped**（14:26）

## 五、改动文件

- 新增: `blueprint/permission_engine.py` / `blueprint/automation.py` /
  `blueprint/tests/test_executor_wiring.py` /
  `blueprint/tests/test_permission_engine.py` /
  `blueprint/tests/test_automation.py`
- 修改: `blueprint/executor.py`（_handle_meta/_handle_behavior 真接线）

## 六、剩余（缺口清单后续批次）

- 第三批: GAP-O1/O2（memory/coordinator 归位）+ GAP-O3（PCR 模型统一）+
  GAP-P1（控制面板参数化）
- 第四批: GAP-F1/F2（前端变更日志 + 139 文件绑定, 阶段 B）+ P2 项

