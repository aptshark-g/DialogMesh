# PARADIGM 承诺级追踪矩阵（2026-08-15 建）

> 定位: 设计↔实现双向等价的核对表（A24 可逆推性应用于开发流程）。
> 双向 coverage 目标 60-80%（100% = 过拟合/契约化, 0% = 空转/漂移）。
> 每行两方向: 设计→实现（兑现? 测试?）; 实现→设计（行为可解释?
> 已回写?）。施工后更新状态; 交接时对照。
> 状态: ✅ 兑现且有测试 / 🟡 部分（注明缺什么） / ❌ 未实现 /
> ⚪ 待核（本矩阵初建时未逐条核查, 需审计确认）。

## 公理（A1-A25）

| 公理 | 设计→实现落点 | 状态 | 验收样例/测试 | 实现→设计（回写/异常） |
|---|---|---|---|---|
| A1 视角/颗粒度 | PCR V2 zone / 各模块一级视角; 二级视角（结构/语义/时序/反例） | 🟡 一级有, 二级验证零散 | 蒸馏四视角调整（部分） | 待审计 |
| A2 颗粒度递归 | 颗粒度变体表; full_text 原文通路 + 聊天链路放大（2026-08-15） | ✅ 存储+生成上下文都接 | test_full_text_backfilled_p9; 幻觉收敛实测 | 变体表已回写契约文档 |
| A3 关系第一公民 | 子图/vault 图 + graph_anchors + 关联树映射 | 🟡 有图; 执行→meta audit 映射已接（2026-08-15）, 关系消费仍有限 | test_consume_writes_seven_trees_and_persists | 待审计 |
| A4 信念 7 维 | Hypothesis Engine（chapter2） | ⚪ 待核 | — | 待审计 |
| A5 树是推理工作台 | 对话树/七树/ExecutionTree | ✅ 生产接线 + 跨树联邦（query_agent_trees + /v6/agent-trees, 2026-08-16 跨会话聚合） | test_execution_tree_production_wiring 10/10 + 端到端实测 | 生产取树此前错取对话树管理器（恒 None）, 已修 |
| A6 自我纠错 | recall feedback()/A18 持久化 | ✅ | test_feedback_persists | 无异常 |
| A7 信息论 | P9 分治; 概率/价值算子 | ✅ 原文保留已落地（算子未, 启发式） | 真幻觉率 0.175→0.045 实测 | 算子缺 → 契约 §三补丁 |
| A8 表达形式 | 符号注入 Mermaid/JSON | 🟡 | 符号注入端到端（08-10） | 待审计 |
| A9 行为一等公民 | 行为链 + ExecutionTree 消费 | 🟡 消费器有（ExecutionPatternStore 持久化 + BehaviorTree 风险模式接线）, 深度偏好 W7 未 | _consume_execution_tree 生产路径实测 | 生产接线修复后消费端可达 |
| A10 元认知 | AuditFeedbackLoop / decision_bus / Governor+AsyncDiagnosis | ✅ 小环（Governor 熔断/降级/重试）+ 大环（AsyncDiagnosis 异步诊断+自调节, 2026-08-16） | test_governor 9 + test_diagnosis 7 + 真实链路（网关挂→自动诊断报告） | 双环 A10 兑现: 小环秒级止血, 大环分钟级复盘 |
| A11 执行层可回溯 | tool_loop + 执行树落树 | ✅ 生产落树（TaskRunner→execution 树 create/spawn/complete） | test_task_runner_lands_execution_tree（engine 真实接线） | 2026-08-15: 生产取树恒 None 已修（engine._agent_trees 挂载） |
| A12 约束空间 | PCR zone / 约束投影 + PlanningSkill 任务图约束（2026-08-16 接入） | 🟡 规划通道已接（HYBRID 骨架+LLM 细化）, 投影仍部分 | test_planning_skill_wiring 8/8 + 端到端（task_graph 落盘 read_code→analyze→modify→test→report） | 通用模板补入规则层 |
| A13 长证明后验 | 信念凝聚器（L2.5） | ⚪ 待核 | — | 待审计 |
| A14 工程链约束 | ConstraintEngine | ❌ 未接入（07-22 表同） | — | 设计空转已记录 |
| A15 温度×价值 | HCWA 分层 + 变体档位 | 🟡 温度有, 价值轴未 | 变体表 | 价值算子缺 |
| A16 冷热编排 | 快反馈后修正（Governor 熔断/降级 + 诊断自调节低风险自动应用） | ✅ 2026-08-16（自调节: adjust_breaker/retry 自动应用+记录） | test_apply_suggestion_* | 低风险自动+记录, 高风险留建议 |
| A17 记录 | 事件溯源/NodeEditRecord + 七树持久化 | ✅ 七树 Warm 层落盘（data/agent_trees, 重启恢复实测） | test_engine_persist_and_restore + 端到端持久化文件 | 2026-08-15 补 |
| A18 参数自适应 | recall weights/feedback + 变体开关 | ✅ | A18 持久化测试 33/33 | 无异常 |
| A19 白盒 | CLI CRUD / 设计点追踪 + /v6/agent-trees | 🟡 七树白盒端点已加, CLI CRUD 仍部分 | /v6/agent-trees 端到端 200 | 本矩阵即回写 |
| A20 竞争吸收 | md_big / OPENSOURCE_SURVEY | ✅ 清单有 | — | 吸收未验证（A18 要求） |
| A21 安全 | 权限门/沙箱/Guard | ✅ | permission 12/12 | 无异常 |
| A22 因果克制 | CausalSubstrate | ❌ 未（L5 待实现） | — | 设计空转已记录 |
| A23 因果检验 | 三层检验 | ❌ 未（设计空白） | — | 设计空白已记录 |
| A24 可逆推 | 蒸馏/启发链 + full_text 共存 | 🟡 蒸馏部分, 逆推验证未 | full_text 测试 | 双向等价机制（本矩阵） |
| A25 召回重建上下文 | RRF+图扩散+可追源+parent_context+grounding 约束 | ✅ | eval_100 / 三分 Faithfulness（幻觉收敛） | grounding 约束已回写 |

## 派生原则（P1-P28, 关键项）

| 原则 | 落点 | 状态 | 备注 |
|---|---|---|---|
| P9 信息论分治 | full_text 原文保留 + 变体档位 | ✅ 2026-08-15 实测收敛 | 契约 §二; claim 三分 F 0.254→0.568 |
| P11 颗粒度可缩放 | 放大路径（path/full_text） | 🟡 | 前端详情未接 |
| P18 温度×价值 | 变体表 + 温度分层 | 🟡 | 价值轴缺算子 |
| P21 参数自适应 | DM_* 变体 + weights | ✅ | 本表变体即参数 |
| P22 白盒 | CLI + 追踪矩阵 | 🟡 | 本矩阵补 |
| P28 召回可追源 | path + parent_context | ✅ | eval 验证 |

## 使用说明

- 施工前: 查 AGENTS.md 对应任务类型的公理子集, 对照本表落点。
- 施工后: 更新相关行状态 + 验收样例; 新增行为找不到设计落点 →
  二选一（回写设计 or 修代码）; 状态 ⚪ 的行排入审计。
- 双向 coverage 审计: 每季度/大版本核对一次, 目标 60-80%。
