# DialogMesh 统一召回查询集 — 100 条（2026-08-11）

> 39 对话（goldset 块期望） + 61 文档（文档路径期望）
> 格式: | id | query | expected | level | note |; 软拓展直接加行

| id | query | expected | level | note | intent |
| --- | --- | --- | --- | --- | --- |
| c001 | 如果想做一个pi一样的agent你会怎么做？ | goldset:r000,r001,r002,r003,r004,r005,r006,r007,r008 | dialogue | b84e1b45-4f5 | 通用讨论 |
| c002 | 去看看pi的信息，openclaw的原型貌似是，去查一下 | goldset:r009,r010,r011 | dialogue | 6c37deb1-3c7 | 数据搜索 |
| c003 | 你现在可以做编排吗？有那些内容是你可以操作的？ | goldset:r012,r013,r014 | dialogue | 46f894d8-2cf | 通用讨论 |
| c004 | 试试看任务编排，你规划一个，设计里面我是可以改的吧？ | goldset:r015,r016,r017,r018 | dialogue | 46f894d8-2cf | 任务规划 |
| c005 | 你是无法去做任务规划吗？直接给一个完整的检验任务规划，系统会去做吧？ | goldset:r019,r020,r021,r022 | dialogue | 46f894d8-2cf | 任务规划 |
| c006 | 你可以直接规划刀任务的吧？就用你发的这个 | goldset:r023,r024,r025,r026 | dialogue | 46f894d8-2cf | 任务规划 |
| c007 | 你不能直接加载到任务里面吗？ | goldset:r027,r028,r029,r030 | dialogue | 46f894d8-2cf | 任务规划 |
| c008 | 现在可以去规划了吧？ | goldset:r031 | dialogue | 46f894d8-2cf | 任务规划 |
| c009 | 没显示什么情况 | goldset:r032,r033 | dialogue | 46f894d8-2cf | 因果推理 |
| c010 | 帮我规划一个代码审查任务 | goldset:r034,r035,r036,r037,r038,r039,r040,r041,r042 | dialogue | demo | 任务规划 |
| c011 | 你现在来规划一个东西，然后给我规划图 | goldset:r043,r044,r045,r046 | dialogue | a9c84948-bc1 | 任务规划 |
| c012 | 我改了你能看到吗？ | goldset:r047 | dialogue | a9c84948-bc1 | 通用对话 |
| c013 | 现在我改了你收到了？ | goldset:r048 | dialogue | a9c84948-bc1 | 通用对话 |
| c014 | 帮我规划一个用户登录系统 | goldset:r049,r050,r051,r052,r053 | dialogue | a9c84948-bc1 | 任务规划 |
| c015 | 有上下文吗？ | goldset:r054,r055 | dialogue | a9c84948-bc1 | 通用对话 |
| c016 | 规划一个用户登录系统，包含注册、JWT认证、密码找回 | goldset:r056,r057,r058,r059,r060,r061,r062,r063 | dialogue | aaf0c679-727 | 任务规划 |
| c017 | 规划一个用户登录系统 | goldset:r064,r065,r066 | dialogue | 45bda4aa-4a8 | 任务规划 |
| c018 | 你现在所知的上下文有什么 | goldset:r067 | dialogue | a40bd2e8-d8f | 通用对话 |
| c019 | 设计一个用户登录系统，包含JWT认证和数据库设计 | goldset:r068,r069,r070,r071,r072,r073,r074,r075,r076,r077,r078,r079,r080,r081,r082,r083,r084 | dialogue | 7b509b3d-718 | 任务规划 |
| c020 | 简短说一下JWT和Session的区别 | goldset:r085,r086,r087 | dialogue | ef309875-81e | 记忆召回 |
| c021 | 我是一个喜欢探索新技术的软件工程师 | goldset:r088,r089,r090 | dialogue | b0c37811-c90 | casual |
| c022 | 设计一个全新的探索性系统架构，我计划分步骤实现，先验证核心模式 | goldset:r091,r092,r093 | dialogue | fe3a7a79-517 | 任务规划 |
| c023 | 简述微服务架构的优势 | goldset:r094,r095,r096 | dialogue | 0b3d2455-f2c | 记忆召回 |
| c024 | 审计测试：微服务架构的优缺点 | goldset:r097,r098,r099,r100 | dialogue | 5d3bd6ef-9ac | 记忆召回 |
| c025 | 设计用户登录系统的JWT认证方案 | goldset:r101,r102,r103,r104,r105 | dialogue | 6f78417d-35f | 任务规划 |
| c026 | PostgreSQL数据库选型对比MySQL | goldset:r106,r107,r108,r109,r110,r111,r112 | dialogue | 6f78417d-35f | 记忆召回 |
| c027 | 设计一个全新的探索性系统架构，我计划分步骤验证核心模式，需要规范化的流程和明确的测试标准 | goldset:r113,r114,r115,r116,r117,r118 | dialogue | 08da846a-ecf | 任务规划 |
| c028 | 设计全新探索性系统架构，计划分步骤验证核心模式，需要规范化流程和明确测试标准 | goldset:r119,r120,r121,r122 | dialogue | 272507a7-e86 | 任务规划 |
| c029 | 设计一个用户认证系统，需要规范流程和明确测试标准 | goldset:r123,r124,r125,r126,r127,r128,r129,r130,r131 | dialogue | 216aa648-491 | 任务规划 |
| c030 | 我叫小明，我的项目是DialogMesh | goldset:r132,r133 | dialogue | ba35e8f4-f1a | casual |
| c031 | 我叫什么名字？我的项目是什么？ | goldset:r134 | dialogue | ba35e8f4-f1a | 记忆召回 |
| c032 | 帮我分析一下这个系统的架构设计，网关和状态机的关系是什么 | goldset:r135,r136,r137,r138,r139,r140,r141,r142 | dialogue | abfd3223-a16 | 因果推理 |
| c033 | 帮我规划一个用户登录系统的JWT认证方案 | goldset:r143,r144,r145,r146,r147,r148,r149,r150,r151,r152,r153,r154,r155,r156,r157 | dialogue | 4ac03ef9-61d | 任务规划 |
| c034 | 刚才的方案里 JWT 有效期怎么设置比较合理？ | goldset:r158,r159,r160,r161,r162,r163 | dialogue | 4ac03ef9-61d | 记忆召回 |
| c035 | 你好,介绍一下你自己 | goldset:r164,r165 | dialogue | 64d2ce82-857 | casual |
| c036 | 修改 core/agent/recall 下的召回服务，把 bm25 权重提高 | goldset:r166 | dialogue | d63676dc-8af | 代码分析 |
| c037 | 写一份关于统一召回方案的简短设计文档，保存到 data/demo_recall_doc.md | goldset:r167,r168,r169,r170,r171 | dialogue | 2cd98b6a-8db | 任务规划 |
| c038 | 写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。 | goldset:r172,r173,r174,r175,r176 | dialogue | b4ea43d2-a1e | 代码分析 |
| c039 | 写一个 Python 脚本计算 1 到 100 的质数之和并运行验证，然后告诉我结果。 | goldset:r177,r178,r179,r180 | dialogue | 0acd4a82-522 | 代码分析 |
| q001 | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | simple | 三层架构定案 | 记忆召回 |
| q002 | agentic 工具节点怎么让 LLM 自己调工具 | docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md; docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | simple | agentic 节点语义 | 记忆召回 |
| q003 | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | 节点参数 | 记忆召回 |
| q004 | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | MC 例 | 记忆召回 |
| q005 | 执行偏差怎么触发宏观计划改变，双向归因是什么 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 双向纽带 | 记忆召回 |
| q006 | 用户介入分几级？PlanGate 和异步日志怎么分工 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 三层介入 | 记忆召回 |
| q007 | 蓝图薄点审计发现了哪些没接线的模块 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | simple | 薄点清单 | 记忆召回 |
| q008 | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md; docs/only/V1_FUNCTION_CHECKLIST_20260808.md | complex | F1 接线 | 记忆召回 |
| q009 | recall 结果怎么注入执行层，锚点为什么带路径 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | 召回桥 | 记忆召回 |
| q010 | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | complex | 分层准确性 | 记忆召回 |
| q011 | subgraph 节点的 recall_anchor 参数是干嘛的 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | 图拓扑锚点 | 记忆召回 |
| q012 | 统一召回用了哪些算法，RRF 融合提升多少 | docs/only/recall/RECALL_CAPABILITY_20260808.md | simple | 混合锚点 | 记忆召回 |
| q013 | SPO 约束投影怎么提炼主宾关系，谓语权重多少 | docs/only/recall/SPO_MODEL_STRATEGY_20260808.md | complex | SPO 对齐 | 记忆召回 |
| q014 | 中文 SPO 怎么处理，双语两阶段是什么 | docs/only/recall/SPO_BILINGUAL_TWOSTAGE_20260808.md | complex | 双语 | 记忆召回 |
| q015 | 记忆怎么按热温冷分层，预取怎么触发 | docs/only/recall/DYNAMIC_TIERING_PREFETCH_20260808.md | complex | 分层预取 | 记忆召回 |
| q016 | 召回第二批施工做了哪些事，黄金集多少条 | docs/only/recall/RECALL_BATCH2_PLAN_20260808.md | simple | 第二批 | 记忆召回 |
| q017 | 召回评测为什么要有四路 Baseline 对比 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 评测设计 | 记忆召回 |
| q018 | 文档语料召回测试的 query 怎么来，为什么要人工标注 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 层2人工集 | 记忆召回 |
| q019 | 第一版功能核对清单里 C1-C4 权限是什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | C1-C4 | 记忆召回 |
| q020 | 端到端自检 E1-E5 分别检查什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | complex | E1-E5 | 记忆召回 |
| q021 | 树是推理工作台是什么意思，遗忘怎么处理 | docs/only/wise/PARADIGM.md | complex | 公理 | 记忆召回 |
| q022 | 记录永不可删和抽象可逆推是哪几条公理 | docs/only/wise/PARADIGM.md | simple | A17/A24 | 记忆召回 |
| q023 | 偏差是养分怎么理解，归因回流到哪层 | docs/only/wise/PARADIGM.md | complex | 偏差公理 | 记忆召回 |
| q024 | 白盒化承诺是什么，为什么行为必记录 | docs/only/wise/PARADIGM.md | complex | A19 | 记忆召回 |
| q025 | M1 到 M9 的施工顺序是什么 | docs/only/IMPLEMENTATION_PLAN_20260804.md | simple | 施工计划 | 记忆召回 |
| q026 | 阶段 A 和阶段 B 分别包含哪些模块 | docs/only/IMPLEMENTATION_PLAN_20260804.md | complex | 阶段划分 | 记忆召回 |
| q027 | v2.1 召回桥之后下一个施工项是什么 | docs/only/STATE_HANDOFF_20260809.md; docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md | simple | 交接 | 记忆召回 |
| q028 | 本轮压缩交接的恢复入口是哪个文档 | docs/only/STATE_HANDOFF_20260809.md | simple | 恢复路径 | 记忆召回 |
| q029 | 工作流自增长是怎么实现的，成功路径怎么沉淀 | docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md | complex | 自增长 | 记忆召回 |
| q030 | G3 四保护是哪四个，PlanGate 怎么触发 | docs/only/blueprint/P1_PROTECTION_REFLECTION_IMPL_20260806.md; docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | complex | 四保护 | 记忆召回 |
| q031 | 执行层监控 Hot Warm Cold 分别做什么 | docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md | simple | 三层监控 | 记忆召回 |
| q032 | TaskRunner 重规划循环怎么工作，为什么高风险要停下 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | 重规划 | 记忆召回 |
| q033 | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区别 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | complex | 事件 kind | 记忆召回 |
| q034 | 变更日志怎么回看和介入，approve reject 语义 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | simple | changelog | 记忆召回 |
| q035 | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据 | docs/only/wise/HEURISTIC_DISTILLATION_IMPL_20260807.md | complex | 蒸馏 | 记忆召回 |
| q036 | 技能生命周期怎么做活性管理的 | docs/only/blueprint/LEARNING_CLOSED_LOOP_IMPL_20260806.md; docs/only/wise/HEURISTIC_DISTILLATION_IMPL_20260807.md | complex | skill lifecycle | 记忆召回 |
| q037 | 对话树和召回是什么关系，命中怎么并行 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | cross | 跨域 | 记忆召回 |
| q038 | 元认知复盘每几轮做一次，和策略权重什么关系 | docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md | cross | 跨域 | 记忆召回 |
| q039 | 编码类请求怎么识别，施工信号有哪些 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | simple | is_code_request | 记忆召回 |
| q040 | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别 | docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md | complex | 定位 | 记忆召回 |
| q041 | 权限门怎么拦截链式 shell 和越权写入 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md; docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | complex | 权限 | 记忆召回 |
| q042 | OS 工具集有哪些，run_session 是干嘛的 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | OS 工具 | 记忆召回 |
| q043 | function calling 端到端实测做了什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | simple | tool_loop 实测 | 记忆召回 |
| q044 | 执行迹和变更日志两个白盒视图各展示什么 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | cross | 跨域 | 记忆召回 |
| q045 | 跟 OpenClaw Hermes 对标后我们还差什么 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md | complex | 对标差距 | 记忆召回 |
| q046 | 定时自动化 automation 为什么是孤儿，怎么接 | docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md | complex | automation 孤儿 | 记忆召回 |
| q047 | replanner 自动换方案为什么没做，MC 全场景缺什么 | docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md | complex | replanner 缺口 | 记忆召回 |
| q048 | 文档漂移检测怎么融入召回评测 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 漂移审计 | 记忆召回 |
| q049 | 评测看护为什么要有基线和趋势，怎么复跑 | docs/only/recall/RECALL_BENCHMARK_DESIGN_20260809.md | complex | 看护 | 记忆召回 |
| q050 | 第一版发布前还差哪些，前端绑定和量化测试优先级 | docs/only/V1_FUNCTION_CHECKLIST_20260808.md; docs/only/STATE_HANDOFF_20260809.md | cross | 收尾 | 记忆召回 |
| q051 | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md | complex | 内容→图 | 记忆召回 |
| q052 | 隐式关系候选怎么生成和核验，precision 多少 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md; docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md | complex | 隐式边核验 | 记忆召回 |
| q053 | 图导航 API 有哪些，path 和 callers 怎么用 | docs/only/recall/CONTENT_TO_GRAPH_20260811.md | simple | 图导航 | 记忆召回 |
| q054 | Rust 重构召回核心的验收门槛是什么 | docs/only/recall/RECALL_RUST_DESIGN_20260810.md | simple | Rust 验收 | 记忆召回 |
| q055 | 符号注入怎么压缩上下文，Mermaid 图怎么生成 | docs/only/execution/SYMBOL_INJECTION_IMPL_20260810.md | complex | 符号注入 | 记忆召回 |
| q056 | v2 执行层四壳是哪四层，监控怎么介入 | docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md | complex | 执行层四壳 | 记忆召回 |
| q057 | 存储分层 H/W/C/A 怎么升降，阈值多少 | docs/only/G10_STORAGE_DECISION_20260803.md; docs/only/discourse_tree/TREE_TIERING_DECISION_20260807.md | complex | 存储分层 | 记忆召回 |
| q058 | 前端 B5 UI 测试怎么跑，Playwright 基建在哪 | docs/only/frontend/B5_UI_TEST_PLAN_20260807.md | simple | 前端测试 | 记忆召回 |
| q059 | PCR zone 和意图分类怎么映射到召回策略 | docs/only/recall/INTENT_AWARE_RECALL_IMPL_20260813.md | complex | 意图→召回 | 记忆召回 |
| q060 | 设计哲学里偏差为什么是养分，归因回流到哪层 | docs/only/wise/PARADIGM.md | cross | 哲学公理 | 记忆召回 |
| q061 | 子图扩展的 DAG 分层和同步剪枝怎么实现 | docs/only/recall/SUBGRAPH_EXPANSION_UPGRADE_20260811.md | complex | 子图增强 | 记忆召回 |
