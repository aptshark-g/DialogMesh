# ?????????2026-08-11, md ???

| id | query | expected | level | note |
|---|---|---|---|---|
| q001 | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | simple | 三层架构定案 |
| q002 | agentic 工具节点怎么让 LLM 自己调工具 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | simple | agentic 节点语义 |
| q003 | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | 节点参数 |
| q004 | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | MC 例 |
| q005 | 执行偏差怎么触发宏观计划改变，双向归因是什么 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 双向纽带 |
| q006 | 用户介入分几级？PlanGate 和异步日志怎么分工 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 三层介入 |
| q007 | 蓝图薄点审计发现了哪些没接线的模块 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | simple | 薄点清单 |
| q008 | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md; docs/only/V1_FUNCTION_CHEC | complex | F1 接线 |
| q009 | recall 结果怎么注入执行层，锚点为什么带路径 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | 召回桥 |
| q010 | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | complex | 分层准确性 |
| q011 | subgraph 节点的 recall_anchor 参数是干嘛的 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | 图拓扑锚点 |
| q012 | 统一召回用了哪些算法，RRF 融合提升多少 | docs/only/recall/RECALL_CAPABILITY_20260808.md | simple | 混合锚点 |
| q013 | SPO 约束投影怎么提炼主宾关系，谓语权重多少 | docs/only/recall/SPO_MODEL_STRATEGY_20260808.md | complex | SPO 对齐 |
| q014 | 中文 SPO 怎么处理，双语两阶段是什么 | docs/only/recall/SPO_BILINGUAL_TWOSTAGE_20260808.md | complex | 双语 |
| q015 | 记忆怎么按热温冷分层，预取怎么触发 | docs/only/recall/DYNAMIC_TIERING_PREFETCH_20260808.md | complex | 分层预取 |
| q016 | 召回第二批施工做了哪些事，黄金集多少条 | docs/only/recall/RECALL_BATCH2_PLAN_20260808.md | simple | 第二批 |
| q017 | 召回评测为什么要有四路 Baseline 对比 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 评测设计 |
| q018 | 文档语料召回测试的 query 怎么来，为什么要人工标注 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 层2人工集 |
| q019 | 第一版功能核对清单里 C1-C4 权限是什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | C1-C4 |
| q020 | 端到端自检 E1-E5 分别检查什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | complex | E1-E5 |
| q021 | 树是推理工作台是什么意思，遗忘怎么处理 | docs/only/wise/PARADIGM.md | complex | 公理 |
| q022 | 记录永不可删和抽象可逆推是哪几条公理 | docs/only/wise/PARADIGM.md | simple | A17/A24 |
| q023 | 偏差是养分怎么理解，归因回流到哪层 | docs/only/wise/PARADIGM.md | complex | 偏差公理 |
| q024 | 白盒化承诺是什么，为什么行为必记录 | docs/only/wise/PARADIGM.md | complex | A19 |
| q025 | M1 到 M9 的施工顺序是什么 | docs/only/IMPLEMENTATION_PLAN_20260804.md | simple | 施工计划 |
| q026 | 阶段 A 和阶段 B 分别包含哪些模块 | docs/only/IMPLEMENTATION_PLAN_20260804.md | complex | 阶段划分 |
| q027 | v2.1 召回桥之后下一个施工项是什么 | docs/only/STATE_HANDOFF_20260809.md | simple | 交接 |
| q028 | 本轮压缩交接的恢复入口是哪个文档 | docs/only/STATE_HANDOFF_20260809.md | simple | 恢复路径 |
| q029 | 工作流自增长是怎么实现的，成功路径怎么沉淀 | docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md | complex | 自增长 |
| q030 | G3 四保护是哪四个，PlanGate 怎么触发 | docs/only/blueprint/P1_PROTECTION_REFLECTION_IMPL_20260806.md; docs/only/bluepri | complex | 四保护 |
| q031 | 执行层监控 Hot Warm Cold 分别做什么 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | simple | 三层监控 |
| q032 | TaskRunner 重规划循环怎么工作，为什么高风险要停下 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | 重规划 |
| q033 | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区别 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 事件 kind |
| q034 | 变更日志怎么回看和介入，approve reject 语义 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | simple | changelog |
| q035 | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据 | docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md | complex | 蒸馏 |
| q036 | 技能生命周期怎么做活性管理的 | docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md | complex | skill lifecycle |
| q037 | 对话树和召回是什么关系，命中怎么并行 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | cross | 跨域 |
| q038 | 元认知复盘每几轮做一次，和策略权重什么关系 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md; docs/only/bluep | cross | 跨域 |
| q039 | 编码类请求怎么识别，施工信号有哪些 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | is_code_request |
| q040 | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | complex | 定位 |
| q041 | 权限门怎么拦截链式 shell 和越权写入 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md; docs/only/blueprint/BLUEPRINT_THIN_ | complex | 权限 |
| q042 | OS 工具集有哪些，run_session 是干嘛的 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | OS 工具 |
| q043 | function calling 端到端实测做了什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | tool_loop 实测 |
| q044 | 执行迹和变更日志两个白盒视图各展示什么 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md; docs/only/blueprin | cross | 跨域 |
| q045 | 跟 OpenClaw Hermes 对标后我们还差什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | complex | 对标差距 |
| q046 | 定时自动化 automation 为什么是孤儿，怎么接 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | complex | automation 孤儿 |
| q047 | replanner 自动换方案为什么没做，MC 全场景缺什么 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | replanner 缺口 |
| q048 | 文档漂移检测怎么融入召回评测 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 漂移审计 |
| q049 | 评测看护为什么要有基线和趋势，怎么复跑 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 看护 |
| q050 | 第一版发布前还差哪些，前端绑定和量化测试优先级 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md; docs/only/STATE_HANDOFF_20260809.md | cross | 收尾 |
| q051 | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md | complex | 内容→图 |
| q052 | 隐式关系候选怎么生成和核验，precision 多少 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md | complex | 隐式边核验 |
| q053 | 图导航 API 有哪些，path 和 callers 怎么用 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md | simple | 图导航 |
| q054 | Rust 重构召回核心的验收门槛是什么 | docs/only/recall/RECALL_RUST_DESIGN_20260810.md | simple | Rust 验收 |
| q055 | 符号注入怎么压缩上下文，Mermaid 图怎么生成 | docs/only/execution/SYMBOL_INJECTION_IMPL_20260810.md | complex | 符号注入 |
| q056 | v2 执行层四壳是哪四层，监控怎么介入 | docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md | complex | 执行层四壳 |
| q057 | 存储分层 H/W/C/A 怎么升降，阈值多少 | docs/only/G10_STORAGE_DECISION_20260803.md | complex | 存储分层 |
| q058 | 前端 B5 UI 测试怎么跑，Playwright 基建在哪 | docs/only/frontend/B5_UI_TEST_PLAN_20260807.md | simple | 前端测试 |
| q059 | PCR zone 和意图分类怎么映射到召回策略 | docs/only/recall/RECALL_MAINSTREAM_GAP_20260811.md | complex | 意图→召回 |
| q060 | 设计哲学里偏差为什么是养分，归因回流到哪层 | docs/only/wise/PARADIGM.md | cross | 哲学公理 |
| q061 | 子图扩展的 DAG 分层和同步剪枝怎么实现 | docs/only/recall/SUBGRAPH_EXPANSION_UPGRADE_20260811.md | complex | 子图增强 |
