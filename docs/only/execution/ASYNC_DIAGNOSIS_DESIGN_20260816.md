# AsyncDiagnosis 设计 — 元认知异步诊断（大环兑现, 第二大脑）

> 状态: 设计定案 + 骨架落地 | 触发: 用户"纠错可以更上一层楼? 出现失误
> 把内容给元认知做异步诊断, 追踪/复盘/检索/上网实现自调节, 这才是真正
> 的第二大脑?"
> 关联: PARADIGM A10（双环: 小环 Think→Act→SelfChk→Correct→Retry +
> **大环 冷路径审计→回档修正→重新执行**）; A11（可自我批判, 修正深度=
> 错误深度）; A10 元认知四职责（协同/学习/裁决/复盘）。

## 〇、判断

**认同, 且这是设计里 A10"大环"的兑现** —— 不是新发明, 是把早就承诺但
未实现的部分补上:

```
小环（已落地）: Governor — 即时快速治理（秒级, 算法）
  熔断/降级/重试/幂等 — "怎么活下去"（止血）
大环（本设计）: AsyncDiagnosis — 异步深度诊断（分钟级, LLM）
  证据收集→根因分析→自调节 — "为什么会这样, 怎么不再犯"（复盘）
```

两层互补: 小环管"快", 大环管"深"; 小环的失败信号是大环的触发源。
这正是"第二大脑"的职责 —— 第一大脑干活出错, 第二大脑反思为什么错。

## 一、触发门槛（防高频写手, H2 纪律）

不是所有失败都值得深度诊断。触发条件（任一）:
- breaker OPEN（首次/冷却后再次）: 链路熔断 = 系统性信号
- 同 scope 预算耗尽 ≥2 次: 任务反复完不成
- 空回复 ≥3 次/窗口: 已知高频痛点
- 新错误类型首次出现: 未知问题（尤其值得诊断）

频率门控: 每 scope 最小间隔 5 分钟（诊断是慢思考, 不是每失败都跑）。

## 二、诊断流程（异步, 后台线程）

```
trigger(scope, reason, evidence)
  → 门槛判定（过则入队 + 记 last_trigger）
  → worker 出队
  → 1. 收集证据包:
       - governor breaker 状态/统计
       - llm-calls by_stage（延迟/空/错误分布）
       - 执行树最近任务（engine.get_agent_tree, 若会话可用）
       - governor 最近治理动作
    2. LLM 根因分析（网关, 结构化 JSON 输出）:
       root_cause / confidence / evidence_summary /
       suggestions[{action_type, scope, params, reason}]
       LLM 不可用 → 算法降级（统计摘要, 无根因）
    3. 落决策: MetaTree.record_decision + bus.log(kind="diagnosis_report")
    4. 自调节 apply（见三）
```

## 三、自调节闭环（大环的"重新执行"前置）

诊断建议 action_type:
| action_type | 行为 | 风险 |
|---|---|---|
| adjust_breaker | 调熔断阈值/冷却（governor.adjust） | 低 → 自动应用 |
| adjust_retry | 调重试策略（如 empty 2→3 次） | 低 → 自动应用 |
| adjust_budget | 调预算分配（如 planning 15→20s） | 中 → 自动应用+记录 |
| note | 仅建议/代码修复提示 | 高 → 等用户/元认知确认 |

低风险自动应用 + 全部记录（A17）; 高风险写建议供后续人工/元认知裁决。
诊断报告与自调节动作都可从 /v6/diagnosis 白盒查看。

## 四、检索/上网（P2 开关）

- 诊断时本地检索: 复用 RecallService（召回历史相似故障/设计文档）作为
  证据补充 —— 本批接入（证据包含 recall anchors）
- 联网查询: 用户此前拍板"联网后面专门做" → DM_DIAG_WEB=1 时启用
  （预留接口, 默认关）

## 五、落点（骨架）

- 模块: `core/agent/meta/diagnosis.py`（AsyncDiagnoser）
- 触发接入: governor（breaker OPEN / 预算耗尽重复 / 空返回重复 /
  新错误类型）→ diagnosis.trigger
- 自调节: governor.adjust(scope, **params) 接口
- 白盒: /v6/diagnosis（pending/reports/最近报告）

## 六、验收

- 单测: 门槛（频率门控/触发条件）/ 证据收集 / LLM 分析降级 /
  自调节 apply（低风险自动 + 记录）/ 报告落决策事件
- 真实链路: 网关挂 → breaker OPEN → 触发诊断 → 报告含根因
  （connection 类）+ 建议（如 cooldown 调整）

## 七、落地记录（2026-08-16 追加）

### 模块与接入（✅）
- `core/agent/meta/diagnosis.py` AsyncDiagnoser: 队列 + 后台线程 +
  门槛（频率门控 300s/scope）+ 证据收集（breaker/llm-calls/执行树）+
  LLM 根因分析（网关, 结构化 JSON）+ 降级（LLM 不可用 → stats_only）+
  自调节 apply（adjust_breaker/adjust_retry/adjust_budget）+ 报告落
  decision_bus（kind=diagnosis_report）+ MetaTree.record_decision
- governor 触发: breaker OPEN（状态转换检测）+ 重复失败计数
  （connection 类 1 次即触发 — 基础设施故障立即诊断; 其他 3 次）
- 自调节接口: governor.adjust(scope, **params) / adjust_retry(kind, n)
- 白盒: /v6/diagnosis（pending/last_trigger/reports）
- engine attach: 只 attach"已存在"的 engine（不触发 get_engine 惰性
  初始化 — 修复测试环境污染, 2026-08-16 实测定位）

### 实测
- 网关挂场景: 请求快速失败（熔断+预算生效）→ governor 记录各 scope
  失败 → **3 个 scope 自动触发诊断** → 报告落盘（source=stats_only,
  因为诊断 LLM 也调不通, 正确降级为统计摘要）
- 正常链路: 75.7s 预算内返回, 不误触发诊断
- 测试: test_diagnosis 7 项 + test_governor 9 项 + 相关回归 230 全绿

### 环境坑（新增）
- API 重启后第一次 message 请求可能冷启动卡死（Phase 1/2 懒加载 +
  /v6/profile 自调用, 实测一次 170s+ 无 CPU）→ 先用 /v6/health 预热
  （本次 warm 后 75.7s 正常）。根因深挖留后续（Phase 1/2 预算接入）。

## 八、边界（后续）

- 诊断 LLM 用 deepseek-v4-flash; LLM 根因建议质量留后续（RAG 证据
  注入 / 多次采样）
- 联网查询: DM_DIAG_WEB=1 开关预留, 未实现（用户拍板联网后续专做）
- adjust_budget 当前只记录（预算按 scope 拆分 P2）
