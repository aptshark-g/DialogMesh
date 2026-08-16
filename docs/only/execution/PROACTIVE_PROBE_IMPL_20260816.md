# 主动体检（ProactiveHealthProbe）— 实施记录（2026-08-16 P1-①）

> 设计依据: SELF_REPAIR_DESIGN_20260816 §八（"自修定期巡检（无触发也
> 主动体检）"原列为 P2, 本批提前实施）+ PARADIGM A10（元认知第二大脑,
> 小环止血 / 大环复盘）+ A17（记录永不可删）+ A16（快反馈后修正）。

## 〇、为什么做

诊断器（AsyncDiagnoser）此前只**被动触发**: 失败信号 → 门槛判定 → 诊断。
若系统"一切正常但没有失败信号", 元认知从不主动检查 —— 薄弱点会
累积到下一次失败才暴露。主动体检 = **无触发也定期巡检**, 复用
introspection 薄弱点 + 诊断器, 兑现"自修定期巡检"。

## 一、实施内容

### 1. 新模块 `core/agent/meta/probe.py` — ProactiveHealthProbe

- **周期巡检**: daemon 线程, 启动延迟后首检（默认 120s, `DM_PROBE_STARTUP_DELAY`）,
  之后按 interval 巡检（默认 1800s = 30min, `DM_PROBE_INTERVAL`）;
  sleep 分片 1s 检查 `_running`, stop 1s 内生效; start 幂等。
- **信号收集** `_gather`:
  - introspection.weak_spots（诊断报告数）
  - governor breakers（熔断器统计）
  - llm-calls 近窗（recent(500), 逐阶段 empty/errors/retries）
- **薄弱点识别** `_detect`:
  - governor scope: `total_failures>0` 或 state≠closed → breaker 信号
    （非 closed 标 high, 其余 medium）
  - LLM 阶段: empty>0 或 errors>0 → llm_stage 信号（medium）
- **触发诊断**: 每薄弱点 `get_diagnoser().trigger(scope, "proactive_check:...")`
  —— 诊断器自身频率门控（min_interval 300s）兜底, 不刷屏;
  被 gate 的记入 `skipped`。
- **记录（A17）**: 每轮巡检（signals/findings/triggered/skipped）→ 内存环
  （200 条）+ JSONL 落盘 `data/probe_history.jsonl`; 重启尾部恢复 +
  `_last_run` 还原。
- 依赖可注入（governor/diagnoser/recorder）, 测试隔离; 默认走单例。

### 2. 白盒端点（stubs_api.py）

- `GET /v6/probe` — 运行状态/周期/下次巡检/最近历史
- `POST /v6/probe/run` — 立即巡检一轮（诊断异步入队, 不阻塞）

### 3. 启动钩子（v6_app.py startup）

- `get_probe().start()`; `DM_PROBE_ENABLED=0` 可关; 失败不阻断启动。

### 4. 顺带修复: call_recorder 落盘路径

- `_default_path()` 原少一层 dirname → 落到 `core/data/llm_calls.jsonl`,
  与 introspection/experience 的 `data/` 约定不一致; 已修
  （`core/data/execution_patterns.json` 是既有数据, 不动）。

## 二、测试

- `core/agent/meta/tests/test_probe.py` 6 项:
  - 健康态零发现（且落盘）
  - breaker 薄弱点 → 触发诊断（last_trigger 含 scope）
  - LLM 阶段薄弱点检出 + 健康阶段不误报
  - 诊断器频率门控尊重（第二轮同 scope → skipped）
  - 历史持久化 + 重启恢复（含 _last_run）
  - worker 生命周期（start 幂等 / stop 1s 内生效）
- 回归: meta 65 + call_recorder 4 + api 22 全绿。

## 三、实测（端到端, 真实 API :8000 重启后）

- `GET /v6/probe` → running=true, interval=1800, next_due≈110s
- `POST /v6/probe/run` → 健康态: breakers=0 / llm_calls=0 /
  findings=[] / triggered=[]; 记录落盘 `data/probe_history.jsonl`

## 四、边界与后续

- 巡检发现的薄弱点触发诊断后, 报告/自调节沿用 AsyncDiagnoser 既有链路;
  LLM 凝练 design_lesson（DM_DIAG_LLM_LESSON）仍为 P1 ③ 待办。
- 薄弱点识别当前是规则启发（失败计数/空返回）; 后续可接执行效率
  （复杂任务 6 轮探索不完）作为巡检信号。
- 巡检频率默认 30min: 环境变量可调; 若未来做动态调度（A21 参数
  自适应闭环）可并入 governor.self_tune。
