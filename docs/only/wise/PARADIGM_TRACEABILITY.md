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
| A10 元认知 | AuditFeedbackLoop / decision_bus / Governor+AsyncDiagnosis + ProactiveHealthProbe（主动体检, 2026-08-16 P1-①） | ✅ 小环（Governor 熔断/降级/重试）+ 大环（AsyncDiagnosis 异步诊断+自调节）+ 主动体检（无触发也定期巡检, 复用 introspection 薄弱点+诊断器） | test_governor 9 + test_diagnosis 7 + test_probe 6 + 真实链路（网关挂→自动诊断报告; /v6/probe/run 端到端） | 双环 A10 兑现: 小环秒级止血, 大环分钟级复盘, 定期体检补齐"无信号不检查"盲区 |
| A11 执行层可回溯 | tool_loop + 执行树落树 | ✅ 生产落树（TaskRunner→execution 树 create/spawn/complete） | test_task_runner_lands_execution_tree（engine 真实接线） | 2026-08-15: 生产取树恒 None 已修（engine._agent_trees 挂载） |
| A12 约束空间 | PCR zone / 约束投影 + PlanningSkill 任务图约束（2026-08-16 接入） | 🟡 规划通道已接（HYBRID 骨架+LLM 细化）, 投影仍部分 | test_planning_skill_wiring 8/8 + 端到端（task_graph 落盘 read_code→analyze→modify→test→report） | 通用模板补入规则层 |
| A13 长证明后验 | 信念凝聚器（L2.5）+ 自愈经验库（贝叶斯 prior 累积, 2026-08-16）+ design_lesson LLM 凝练（DM_DIAG_LLM_LESSON, P1-③）+ 经验检索 RAG（P2-①: BGE-M3 语义+关键词混合, sidecar 持久化, 降级关键词） | ✅ 经验库 JSONL + 向量 sidecar; 语义检索端到端实测（"网关连不上"→connection refused 经验, 无关键词重合命中）; 凝练开关开→LLM 1.3s | test_experience 11 + test_diagnosis 7 | 后验→先验闭环: 修复凝练教训→语义检索复用 |
| A14 工程链约束 | ConstraintEngine | ❌ 未接入（07-22 表同） | — | 设计空转已记录 |
| A15 温度×价值 | HCWA 分层 + 变体档位 | 🟡 温度有, 价值轴未 | 变体表 | 价值算子缺 |
| A16 冷热编排 | 快反馈后修正（Governor 熔断/降级 + 诊断自调节低风险自动应用）+ 启动期有界预热 + run_dag 预算接入（2026-08-16 P1-②） | ✅ 自调节 + 预热（首请求 43.9s→1.8s）+ run_dag 挪 executor（请求期间 health 113ms 可响应, 事件循环不阻塞） | test_warmup 5 + test_probe 6 + 端到端（重启后首消息 1.8s） | 预算闸进 run_dag context（_budget_passed）; 子线程超时残留踩坑已记录 |
| A17 记录 | 事件溯源/NodeEditRecord + 七树持久化 + 项目归属持久化（data/projects.json, 2026-08-17）+ 上下文 marks 持久化（data/context_marks.json, 2026-08-17） | ✅ 七树 Warm 层落盘 + 项目 CRUD/会话归属（B15+B1） + 上下文钉住/移除（B3） | test_engine_persist_and_restore + test_projects_api 9 + test_context_marks_b3 | 2026-08-15 补; 2026-08-17 项目/marks 持久化 |
| A18 参数自适应 | recall weights/feedback + 变体开关 | ✅ | A18 持久化测试 33/33 + 融合消融矩阵 12+ 组（2026-08-16）+ 真 HyDE 全量评测（2026-08-17, HYDE_EVAL: K1 全负 / K3 干净对照 = 基线, 方差内无增益 / HyDE→BM25 负 → 默认关） | 负结果回写设计文档; 顺带交付域门控（_hot_is_doc）+ DM_SPO_LLM_JUDGE 隔离（净正架构改进）; SPO 谓词 LLM 判定加 50 次进程预算 |
| A19 白盒 | CLI CRUD / 设计点追踪 + /v6/agent-trees + /v6/system-profile + /v6/repairs + B 类后端全量（B3 钉住移除 / B5 会话标题 / B4+B6 画像健康度 / B8 用户偏好 / B10 预算+稳定ID / B11 图圈选 / B12 编译快照覆写 / B13 全局搜索 / B2 project 范围, 2026-08-17）+ 前端 B15 项目服务端化 | 🟡 系统自画像+修复队列已加, CLI CRUD 仍部分 | /v6/system-profile 端到端 + test_kernel_dispatch 61 + test_projects_api 9 + 全量 2088 绿 + tsc/build 绿 | 元认知可读自己系统; B 类后端闭环完成（B9 远期/B14 待设计） |
| A20 竞争吸收 | md_big / OPENSOURCE_SURVEY | ✅ 清单有 | — | 吸收未验证（A18 要求） |
| A21 安全 | 权限门/沙箱/Guard | ✅ | permission 12/12 | 无异常 |
| A22 因果克制 | CausalSubstrate | ❌ 未（L5 待实现） | — | 设计空转已记录 |
| A23 因果检验 | 三层检验 | ❌ 未（设计空白） | — | 设计空白已记录 |
| A24 可逆推 | 蒸馏/启发链 + full_text 共存 | 🟡 蒸馏部分, 逆推验证未 | full_text 测试 | 双向等价机制（本矩阵） |
| A25 召回重建上下文 | RRF+图扩散+可追源+parent_context+grounding 约束 + HyDE 多查询 RRF（DM_HYDE_K, 默认关）+ 域门控 | ✅ | eval_100（dialogue 76.9% / doc 50.8%, 2026-08-17 当前语料）+ 三分 Faithfulness（幻觉收敛）+ miss 根因分类 + HyDE 干净对照（K3 = 基线, 无增益; 两处测量混淆已修: SPO LLM 判定 / cold 池污染） | 语料自污染发现: 自加文档漂移基线 54.1→50.8; HyDE→BM25 实测负（假设文档缺内部词汇） |

## 派生原则（P1-P28, 关键项）

| 原则 | 落点 | 状态 | 备注 |
|---|---|---|---|
| P9 信息论分治 | full_text 原文保留 + 变体档位 | ✅ 2026-08-15 实测收敛 | 契约 §二; claim 三分 F 0.254→0.568 |
| P11 颗粒度可缩放 | 放大路径（path/full_text） | 🟡 | 前端详情未接 |
| P18 温度×价值 | 变体表 + 温度分层 | 🟡 | 价值轴缺算子 |
| P21 参数自适应 | DM_* 变体 + weights | ✅ | 本表变体即参数 |
| P22 白盒 | CLI + 追踪矩阵 | 🟡 | 本矩阵补 |
| P28 召回可追源 | path + parent_context | ✅ | eval 验证 |
| A14/A19 网关白盒（2026-08-17） | LiteLLM 价格目录同步（启动后台 + POST /v6/gateway/sync-prices, 缓存 models_prices.json, 本地覆盖优先）+ 网关页 Provider 五态（未配置/无网络/未启用/可使用/待检测） | ✅ | test_gateway_price_sync 4 + tsc/build 绿 + 实测 3040 模型 / 115 富化（deepseek/kimi 定价生效） | 价格每 1M tokens; base_url 仍以内置预设+用户配置为准（LiteLLM 目录不含地址） |
| A19 前端白盒（2026-08-17 续） | 总览/会话页搜索+滚动增量加载（电商式懒加载, 防全量渲染卡死）+ v6.0 品牌移除 + 顶部 5 状态卡可读化 + 项目=工作区 P0（path 字段 + /v6/projects/browse 只读目录浏览 + 创建后选文件夹） | ✅ | test_projects_api 13 + tsc/build 绿 + 端点实测（建目录/browse 可见） | 项目方向: 子对话/fork/分支/git 式管理 = 待办（PROJECT_WORKSPACE_20260817.md）; 目录浏览仅读不建（A21） |
| A1/A24 项目设计元信息（2026-08-17） | 项目页视图 `/projects/:id` + design 元信息（理念/公理/目标, 二阶抽象）: GET/PUT + POST digest（LLM 从项目会话凝练, 失败模板兜底） | ✅ | test_projects_api 17 + tsc/build 绿 + 实测 llm_digest 真实产出 | 二阶抽象工程化: 项目即认知边界, 约束从会话实践长出来; 子对话/分支待办 |
| A19 环境信息面板（2026-08-17） | 工程链副屏 → 环境信息: git 只读端点（/v6/git/status, 分支/远端/变更/提交, 全只读 A21）+ skills + 项目关系约束 + 图关系; 项目页新建会话（B16）+ 创建时间修复 | ✅ | test_git_api 2 + test_projects_api 17 + tsc/build 绿 + 实测 git 状态正确 | 内置 git 可视化/VS 联动 = 待办（GIT_VISUALIZATION_20260817.md, 先文件系统桥） |
| A19/A21 工程链多模块副屏（2026-08-18） | 工程链分区折叠: 环境信息（Codex 式变更+N/-N/提交/推送）+ Git 分支可切换（switch/-c）+ 后台进程（/v6/system/processes）+ 连接占位 + Skills 搜索/滚动/下载占位; git 写操作显式触发且限仓库根 | ✅ | test_git_api 3（临时仓库写操作）+ test_system_api 2 + 22 绿 + tsc/build 绿 + 端点实测 | 写操作经 A21 护栏: 仅显式动作; 提交图/VS 联动/远程连接 = 待办 |

## 使用说明

- 施工前: 查 AGENTS.md 对应任务类型的公理子集, 对照本表落点。
- 施工后: 更新相关行状态 + 验收样例; 新增行为找不到设计落点 →
  二选一（回写设计 or 修代码）; 状态 ⚪ 的行排入审计。
- 双向 coverage 审计: 每季度/大版本核对一次, 目标 60-80%。
