# M8 CLI/REST 对齐（B4-5）— 施工进度 2026-08-04

> 状态: ✅ 完成（内核唯一 + 传输可插拔，CLI 消假执行 + REST 消假数据）
> 定案依据: `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` §十（B4-5）
> 前置审计: `landscape_read/BATCH4_SERVICE_LAYER_CLI_20260803.md`（69 vs 30 端点差异）

---

## 一、核心成果：命令内核（唯一 dispatch 函数集）

新增 `core/agent/kernel/`（`__init__.py` + `dispatch.py`，~700 行）：

- **内核函数 60+ 个**，全部返回真实数据 dict（引擎属性优先，磁盘文件兜底），
  无假数据：拿不到真实数据返回空结构 + `status: unavailable`，绝不硬编码伪造值。
- **CLI 与 REST 共用同一内核**（B4-5 核心洞察）：
  - CLI: `argv → kernel_* → print(json)`
  - REST: `JSON → kernel_* → JSON`
- 覆盖面：engine/profile/trace/mind/graph/discourse/objects/rules/relations/
  causal/behavior/inertia/engineering/pipeline/extraction/perspectives/
  parameters/context/subgraph/belief/persistence/annotations/corrections/
  sessions/versions/router/providers/metrics/meta/degradation/ttl/recursive-map
  + eventlog/memory/format/blueprint/decider（CLI 消假执行核心）
  + 缺口补齐（meta_scan/retrospect、behavior_feedback、causal_chain、
    context_config、engineering_constraints、ocean_params、corrections_review、
    providers_test、sync、ttl_tick、versions_rollback）

---

## 二、B4-5-P1 CLI 消假执行（✅ 完成）

### 2.1 改造文件

| 文件 | 改动 |
|---|---|
| `core/agent/cli/commands/p9_cmd.py` | 40+ 假 handler → 内核真实调用（format/eventlog/memory/blueprint/decider/meta/assoc/behavior/engineering/profile/discourse） |
| `core/agent/cli/commands/blueprint_cmd.py` | `cmd_decider_execute` 假执行 → `kernel_decider_execute` 真管线 |
| `core/agent/cli/commands/p5_cmd.py` | `cmd_rules_delete` 假删除 → 真 ABC remove_rule + 磁盘兜底 |

### 2.2 消除的假执行点（实测）

```text
cmd_decider_execute   以前: {"executed": true, "handlers": N}   → 现在: 真 StateMachine 管线 11 阶段
cmd_decider_show      以前: {"error": "No decider"}             → 现在: GlobalDecider 真 stats
cmd_decider_chains    以前: {"chains": []}                      → 现在: tick/state 真数据
cmd_format_encode     以前: "format encoder not yet implemented" → 现在: FormatEngine 真编码
cmd_eventlog_stats    以前: {"total": 0, "by_type": {}}         → 现在: EventLog v2 真统计
cmd_memory_*          以前: 0/空                                → 现在: MemoryCompiler 真三档
cmd_discourse_compress 以前: "compress not yet implemented"     → 现在: 真 compress_cold_blocks
cmd_rules_delete      以前: "rule deletion queued"              → 现在: 真 ABC remove_rule
```

### 2.3 附带修复

- `discourse compress` 缺 `session_id` 参数 → 按签名自适应传入
- `rules delete` 不校验 remove_rule 返回值 → 现在返回真实 deleted 布尔
- `profile mbti/bfi` 写磁盘 → 现在真实持久化 `data/profile_state.json`

---

## 三、B4-5-P2 REST 对齐（✅ 完成）

### 3.1 stubs_api.py 重写（874L → 480L）

- **全部端点转发内核**，删除硬编码假数据。
- **删除假 `/v6/gateway/*` 路由**（api_gateway 真实 switch 代理接管）。
- **删除重复端点**：`/v6/parameters`、`/v6/context`（pipeline_api 已转内核）、
  `/v6/annotate`、`/v6/annotate/stats`（api_annotate 真实 JSONL 接管）。
- **v4 旧 API** 独立 `v4_router`（health/status/checkpoint/event/ingest/inspect）。
- **缺口补齐 18 个端点**：behavior/feedback、causal-chain、context/config、
  engineering/constraints、meta/scan、meta/retrospect、ocean/params、
  profile/corrections/review、providers/test、sync、ttl/tick、
  versions/{category}、versions/{category}/rollback + v4 系列。

### 3.2 路由去重（实测）

```text
改造前: 6 处重复路由（gateway/providers、annotations、corrections、parameters、
        context、v3/session 假 demo）
改造后: 0 重复，126 条路由
```

### 3.3 前端覆盖（实测）

```text
前端 v6.ts + v4.ts 86 个路径 → 后端 100% 覆盖（0 missing）
（v6.ts 模板三元表达式解析假阳性已排除，真实路径全部注册）
```

### 3.4 配套修复

- `pipeline_api.py` `/v6/context` 假硬编码 → 内核转发
- `v6_app.py` 删除假 demo `/v3/session`、假 `v6_usage`、假 gateway/annotations/corrections
- `v6_app.py` 挂载 `api_annotate`（此前真实注释系统未 include）+ `v4_router`
- `api_annotate.py` stats 增加 `by_author/by_date`（前端契约）
- 新增 `/v1/health` 真实健康检查

---

## 四、测试（✅ 全绿）

```text
新增: core/agent/api/tests/test_kernel_dispatch.py  49/49
  - 内核函数真实数据（engine/profile/mind/pipeline/metrics/graph/relations/
    decider/eventlog/memory/format）
  - REST 端点转发内核（profile/trace/rules/relations/behavior/engineering/
    pipeline/metrics/meta/sessions/parameters/context/annotate/gateway +
    18 个新补齐端点 + v4 系列）
  - CLI 假执行点已消（decider/format/eventlog/memory/discourse/rules）
回归: M8 核心集 127/127（kernel 49 + viz_edit 29 + statemachine 10 +
      event_log 12 + cli 27）
  + service_middleware 8/8（单独跑，测试间 event loop 共享为预存在 flaky）
排除: test_discourse_write_ops = D-14（CohesionScore 字段 bug，归对话树）
```

### 测试环境坑（沿用）

```text
- pytest 用 anaconda3（--import-mode=importlib 必须）
- REST 测试需 X-Session-Id（服务中间件 anonymous 桶 burst=20，测试循环会 429）
- 429 为测试速率问题，非产品缺陷（真实用户会话独立）
```

---

## 五、验收对照（B4-5 §10.5）

| 验收项 | 结果 |
|---|---|
| CLI: `dm <任何命令>` 返回真实数据（无假执行） | ✅ 实测 decider/format/eventlog/memory/discourse/rules 全真实 |
| REST: v6.ts 每个调用 → 内核 dispatch（无 stub 响应） | ✅ 86 路径 100% 覆盖，0 假数据 |
| MCP: 工具 = 内核命令注册表映射 | ⏭ 阶段 3（M8 未含，归后续） |

---

## 六、遗留（归后续，不阻塞）

```text
- MCP 标准化（阶段 3，B4-5 顺序: CLI → REST → MCP → 多 agent）
- 多 agent 直连（阶段 4，B2-3 持久化能力底座就绪后）
- D-14 CohesionScore 字段 bug（归对话树模块）
- service_middleware 测试间 event loop flaky（预存在，归测试基建）
```
