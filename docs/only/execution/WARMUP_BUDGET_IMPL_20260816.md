# 启动期有界预热 + run_dag 预算接入 — 实施记录（2026-08-16 P1-②）

> 设计依据: HA_EXECUTION_ANALYSIS_20260816（预算传播/观测）+ PARADIGM A16
>（快反馈后修正, 不阻断）+ A10（元认知第二大脑）。触发: 交接待办
> "Phase 1/2 预算接入（根治重启后首次请求冷启动卡死）"。

## 〇、实测根因（阶段计时, 非猜测）

给 `send_message` 加阶段计时 spans（`phase_ms`, 进 blueprint tracer）后
实测（warm 态, 简单问候）:

| 阶段 | 首请求（无预热） | 稳态 |
|---|---|---|
| phase1 认知（pcr.route） | **14.7s**（embedding/mood 冷加载） | 0.1s |
| run_dag intent handler | **13.5s**（DualTrack 首调 LLM） | ~1s |
| run_dag discourse handler | **14.2s**（feed 首调 embedding） | ~0.5s |
| llm_reply（Phase 4） | ~1s（预算感知, 有记录） | ~1s |

衰减曲线: 首请求 43.9s → 第二条 14.6s → 第三条 3.8s —— 冷启动税逐次
消解, 但首个用户请求要付全额。

**两个真问题**:
1. 冷启动税在请求路径上（懒路径首调）。
2. `run_dag` 是**同步**调用, 其内部 handler 做无预算 LLM 调用（provider
   默认 60s×N）——上游慢时**阻塞事件循环**, 实测 120s+ 健康端点不可达
   （整机"卡死", 这就是 170s 卡死的本质）。

## 一、实施内容

### 1. 启动期有界预热 `core/agent/meta/warmup.py`（WarmupManager）

- 后台 daemon 线程, 启动后按预算（默认 75s, DM_WARMUP_BUDGET）跑懒路径:
  - `prewarm`: 共享 BGE / ModelService / PCR mood vectors 就绪
    （`prewarm_models(blocking=True)`, 幂等; 与引擎 bootstrap 的
    `prewarm_models(blocking=False)` 串行化, 不重复加载竞争）
  - `pcr`: `engine._pcr_router.route("预热")`（Phase 1 同路径）
  - `intent`: `engine._intent_parser.process("预热")`（run_dag INTENT 同路径）
  - `discourse`: `engine._discourse_tree.feed("预热", "__warmup__")`
    （副作用收敛到 `__warmup__` 会话）
  - `topic`: `engine._topic_tree.route(...)`
  - `planner`: LLMPlanner 懒初始化
- 步内自带硬超时（LLM 60s/10s, embedding 有限 CPU）,**同步执行, 不用
  子线程超时**——实测子线程超时残留会占 embedding 锁, 级联卡死（先踩坑
  后移除）。
- 历史 JSONL 落盘 `data/warmup_history.jsonl`（A17）+ `/v6/warmup`
  GET/POST 白盒。

### 2. run_dag 预算接入（事件循环不再阻塞）

- `v3_session_api` Phase 3.5: `sm.run_dag(...)` 挪
  `await loop.run_in_executor(None, ...)` —— 同步 handler 不再卡事件循环;
  **请求进行中 /v6/health 113ms / /v6/governor 14ms 响应**（修复前 120s+ 不可达）。
- `context["deadline"] = _req_deadline` 传入 run_dag。
- `event/handlers.py`: `_budget_passed(ctx)` 预算闸 —— INTENT/DISCOURSE
  handler 超时快速降级（degraded=budget_exhausted）, 不无限磨蹭。

### 3. 观测增强

- `send_message` 阶段计时 `phase_ms`（phase1_cognitive / phase2_profile /
  phase3_dag / phase4_execute / phase4_llm_reply + Phase 1 子段
  phase1_get_engine / phase1_pcr / phase1_parse）→ 进 blueprint tracer
  `data/pipeline_traces.jsonl`。
- 本批定位全靠它（"卡在哪直接查, 不猜"）。

## 二、实测验收（重启后）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 首消息延迟 | 43.9s（无预热） | **1.8s**（全量预热） |
| 请求期间健康端点 | 120s+ 不可达 | 113ms |
| 预热状态 | — | 6/6 步 ok（总 ~54s） |
| phase1 pcr 冷加载 | 14.7s | 103ms |

## 三、测试

- `test_warmup.py` 5 项（全路径预热/预算跳过/步骤降级/无引擎/历史持久化）
- 回归: meta 66 + event 60 + api 22 全绿。

## 四、边界与后续

- 首消息 1.8s 后, 次消息 5.8s —— 剩余波动来自网关/deepseek 上游延迟
  （非代码路径）, 属外部因素。
- P1-③ LLM 凝练 design_lesson（DM_DIAG_LLM_LESSON）仍待办。
- `prewarm_models` 与 warmup 的 `prewarm` 步语义有重叠（都加载共享 BGE）;
  当前串行化不竞争; 后续可让 warmup 直接等 ModelService.status=warm 而非
  重复调用。
