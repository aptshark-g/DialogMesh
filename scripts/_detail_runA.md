# 统一评测 100 条 — 无 LLM 全指标（2026-08-11）

- 数据: docs/test/recall_queries_100.md（100 条）
- 总耗时: 106s

## dialogue 域（39 条）

- top1: 21/39 (53.8%)
- top3: 79.5% | top5: 92.3%
- MRR@5: 0.686 | nDCG@5: 0.731
- Recall@5: 92.3% | @10: 97.4% | @20: 100.0%
- Context Precision@5: 0.650
- 平均耗时: 621 ms/query

## doc 域（61 条）

- top1: 13.0/61.0 (21.3%)
- top3: 39.3% | top5: 44.3%
- MRR@5: 0.303 | nDCG@5: 0.347
- Recall@5: 44.3% | @10: 63.9% | @20: 85.2%
- Context Precision@5: 0.310
- 平均耗时: 1066 ms/query

## 诊断汇总（为什么）

- 分类: A(融合命中)=91  B(路线内被融合挤出)=7  C(检索缺口)=2
- top1 命中块的来源: {'hot:vector': 34}
- 期望块在单路线排第 1 的 query 数: {'vector': 45, 'bm25': 41, 'spo': 12}
- 期望块进入某路线 top-20 的 query 数: {'vector': 91, 'bm25': 82, 'spo': 40}
- 融合命中但非 top1（排序竞争）: 57
- 各路线平均耗时 ms/query: {'vector': 36.5, 'bm25': 34.0, 'spo': 99.8}

## 逐条明细

- [A] fused=1 vec=1 bm25=1 spo=1 | vec1ms bm251ms spo7ms | top1源=hot:vector | 如果想做一个pi一样的agent你会怎么做？
- [A] fused=1 vec=1 bm25=1 spo=1 | vec2ms bm251ms spo24ms | top1源=hot:vector | 去看看pi的信息，openclaw的原型貌似是，去查一下
- [A] fused=4 vec=1 bm25=2 spo=None | vec1ms bm251ms spo16ms | top1源=hot:vector | 你现在可以做编排吗？有那些内容是你可以操作的？
- [A] fused=9 vec=12 bm25=1 spo=None | vec1ms bm251ms spo14ms | top1源=hot:vector | 试试看任务编排，你规划一个，设计里面我是可以改的吧？
- [A] fused=2 vec=4 bm25=3 spo=1 | vec1ms bm251ms spo22ms | top1源=hot:vector | 你是无法去做任务规划吗？直接给一个完整的检验任务规划，系统会去做吧？
- [A] fused=2 vec=7 bm25=3 spo=1 | vec1ms bm251ms spo7ms | top1源=hot:vector | 你可以直接规划刀任务的吧？就用你发的这个
- [A] fused=1 vec=2 bm25=1 spo=4 | vec1ms bm251ms spo7ms | top1源=hot:vector | 你不能直接加载到任务里面吗？
- [A] fused=14 vec=16 bm25=14 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 现在可以去规划了吧？
- [A] fused=1 vec=3 bm25=1 spo=1 | vec1ms bm251ms spo7ms | top1源=hot:vector | 没显示什么情况
- [A] fused=1 vec=1 bm25=1 spo=7 | vec1ms bm251ms spo7ms | top1源=hot:vector | 帮我规划一个代码审查任务
- [A] fused=1 vec=1 bm25=8 spo=8 | vec1ms bm251ms spo7ms | top1源=hot:vector | 你现在来规划一个东西，然后给我规划图
- [A] fused=2 vec=1 bm25=4 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 我改了你能看到吗？
- [A] fused=1 vec=1 bm25=1 spo=2 | vec1ms bm251ms spo7ms | top1源=hot:vector | 现在我改了你收到了？
- [A] fused=5 vec=1 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 帮我规划一个用户登录系统
- [A] fused=1 vec=1 bm25=1 spo=4 | vec1ms bm251ms spo7ms | top1源=hot:vector | 有上下文吗？
- [A] fused=1 vec=6 bm25=2 spo=3 | vec1ms bm251ms spo14ms | top1源=hot:vector | 规划一个用户登录系统，包含注册、JWT认证、密码找回
- [A] fused=5 vec=2 bm25=3 spo=4 | vec1ms bm251ms spo9ms | top1源=hot:vector | 规划一个用户登录系统
- [A] fused=2 vec=2 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 你现在所知的上下文有什么
- [A] fused=5 vec=1 bm25=1 spo=None | vec1ms bm251ms spo14ms | top1源=hot:vector | 设计一个用户登录系统，包含JWT认证和数据库设计
- [A] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 简短说一下JWT和Session的区别
- [A] fused=2 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 我是一个喜欢探索新技术的软件工程师
- [A] fused=2 vec=2 bm25=1 spo=1 | vec1ms bm251ms spo21ms | top1源=hot:vector | 设计一个全新的探索性系统架构，我计划分步骤实现，先验证核心模式
- [A] fused=1 vec=1 bm25=1 spo=1 | vec1ms bm251ms spo7ms | top1源=hot:vector | 简述微服务架构的优势
- [A] fused=1 vec=1 bm25=1 spo=3 | vec1ms bm251ms spo7ms | top1源=hot:vector | 审计测试：微服务架构的优缺点
- [A] fused=8 vec=1 bm25=2 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 设计用户登录系统的JWT认证方案
- [A] fused=2 vec=1 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | PostgreSQL数据库选型对比MySQL
- [A] fused=2 vec=1 bm25=1 spo=None | vec2ms bm252ms spo22ms | top1源=hot:vector | 设计一个全新的探索性系统架构，我计划分步骤验证核心模式，需要规范化的流程和明确的测试标准
- [A] fused=3 vec=2 bm25=2 spo=None | vec1ms bm251ms spo21ms | top1源=hot:vector | 设计全新探索性系统架构，计划分步骤验证核心模式，需要规范化流程和明确测试标准
- [A] fused=1 vec=1 bm25=1 spo=2 | vec1ms bm251ms spo14ms | top1源=hot:vector | 设计一个用户认证系统，需要规范流程和明确测试标准
- [A] fused=3 vec=1 bm25=2 spo=None | vec1ms bm251ms spo14ms | top1源=hot:vector | 我叫小明，我的项目是DialogMesh
- [A] fused=1 vec=1 bm25=6 spo=1 | vec1ms bm251ms spo14ms | top1源=hot:vector | 我叫什么名字？我的项目是什么？
- [A] fused=1 vec=1 bm25=1 spo=1 | vec1ms bm251ms spo14ms | top1源=hot:vector | 帮我分析一下这个系统的架构设计，网关和状态机的关系是什么
- [A] fused=4 vec=3 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 帮我规划一个用户登录系统的JWT认证方案
- [A] fused=1 vec=1 bm25=1 spo=5 | vec1ms bm251ms spo7ms | top1源=hot:vector | 刚才的方案里 JWT 有效期怎么设置比较合理？
- [A] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo7ms | top1源=hot:vector | 你好,介绍一下你自己
- [A] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo14ms | top1源=hot:vector | 修改 core/agent/recall 下的召回服务，把 bm25 权重提高
- [A] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo14ms | top1源=hot:vector | 写一份关于统一召回方案的简短设计文档，保存到 data/demo_recall_doc.
- [A] fused=1 vec=1 bm25=1 spo=14 | vec1ms bm251ms spo22ms | top1源=hot:vector | 写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。
- [A] fused=1 vec=1 bm25=1 spo=19 | vec1ms bm251ms spo14ms | top1源=hot:vector | 写一个 Python 脚本计算 1 到 100 的质数之和并运行验证，然后告诉我结果。
- [A] fused=3 vec=1 bm25=1 spo=6 | vec38ms bm2554ms spo129ms | top1源=hot:vector | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
- [A] fused=12 vec=None bm25=5 spo=None | vec39ms bm2552ms spo125ms | top1源=hot:vector | agentic 工具节点怎么让 LLM 自己调工具
- [B] fused=None vec=7 bm25=None spo=None | vec38ms bm2559ms spo122ms | top1源=hot:vector | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
- [A] fused=8 vec=13 bm25=8 spo=None | vec37ms bm2550ms spo171ms | top1源=hot:vector | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
- [A] fused=2 vec=1 bm25=1 spo=None | vec37ms bm2550ms spo173ms | top1源=hot:vector | 执行偏差怎么触发宏观计划改变，双向归因是什么
- [A] fused=1 vec=1 bm25=1 spo=4 | vec40ms bm2552ms spo150ms | top1源=hot:vector | 用户介入分几级？PlanGate 和异步日志怎么分工
- [A] fused=1 vec=7 bm25=1 spo=12 | vec43ms bm2551ms spo122ms | top1源=hot:vector | 蓝图薄点审计发现了哪些没接线的模块
- [A] fused=4 vec=1 bm25=8 spo=None | vec38ms bm2549ms spo158ms | top1源=hot:bm25 | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
- [A] fused=5 vec=3 bm25=1 spo=None | vec38ms bm2554ms spo164ms | top1源=hot:vector | recall 结果怎么注入执行层，锚点为什么带路径
- [A] fused=6 vec=1 bm25=1 spo=6 | vec40ms bm2550ms spo152ms | top1源=hot:vector | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
- [A] fused=1 vec=3 bm25=1 spo=None | vec53ms bm2551ms spo132ms | top1源=hot:vector | subgraph 节点的 recall_anchor 参数是干嘛的
- [B] fused=None vec=16 bm25=None spo=None | vec40ms bm2553ms spo178ms | top1源=hot:bm25 | 统一召回用了哪些算法，RRF 融合提升多少
- [A] fused=13 vec=3 bm25=19 spo=None | vec40ms bm2566ms spo142ms | top1源=hot:vector | SPO 约束投影怎么提炼主宾关系，谓语权重多少
- [A] fused=1 vec=1 bm25=2 spo=None | vec46ms bm2552ms spo161ms | top1源=hot:vector | 中文 SPO 怎么处理，双语两阶段是什么
- [A] fused=19 vec=11 bm25=None spo=None | vec38ms bm2550ms spo119ms | top1源=hot:vector | 记忆怎么按热温冷分层，预取怎么触发
- [A] fused=3 vec=6 bm25=2 spo=None | vec44ms bm2553ms spo129ms | top1源=hot:bm25 | 召回第二批施工做了哪些事，黄金集多少条
- [A] fused=8 vec=None bm25=1 spo=None | vec502ms bm2549ms spo118ms | top1源=hot:bm25 | 召回评测为什么要有四路 Baseline 对比
- [A] fused=8 vec=6 bm25=2 spo=None | vec42ms bm2552ms spo163ms | top1源=hot:vector | 文档语料召回测试的 query 怎么来，为什么要人工标注
- [A] fused=1 vec=3 bm25=1 spo=8 | vec40ms bm2551ms spo122ms | top1源=hot:vector | 第一版功能核对清单里 C1-C4 权限是什么
- [A] fused=2 vec=4 bm25=1 spo=None | vec45ms bm2552ms spo137ms | top1源=hot:vector | 端到端自检 E1-E5 分别检查什么
- [A] fused=10 vec=1 bm25=16 spo=None | vec40ms bm2550ms spo162ms | top1源=hot:vector | 树是推理工作台是什么意思，遗忘怎么处理
- [A] fused=2 vec=2 bm25=4 spo=20 | vec42ms bm2551ms spo125ms | top1源=hot:vector | 记录永不可删和抽象可逆推是哪几条公理
- [A] fused=17 vec=3 bm25=None spo=None | vec41ms bm2549ms spo181ms | top1源=hot:vector | 偏差是养分怎么理解，归因回流到哪层
- [A] fused=1 vec=1 bm25=2 spo=1 | vec40ms bm2550ms spo154ms | top1源=hot:vector | 白盒化承诺是什么，为什么行为必记录
- [A] fused=5 vec=3 bm25=1 spo=14 | vec37ms bm2551ms spo124ms | top1源=hot:vector | M1 到 M9 的施工顺序是什么
- [A] fused=18 vec=4 bm25=None spo=None | vec37ms bm2547ms spo127ms | top1源=hot:bm25 | 阶段 A 和阶段 B 分别包含哪些模块
- [B] fused=None vec=None bm25=None spo=18 | vec41ms bm2550ms spo139ms | top1源=hot:bm25 | v2.1 召回桥之后下一个施工项是什么
- [A] fused=13 vec=9 bm25=15 spo=None | vec46ms bm2552ms spo125ms | top1源=hot:vector | 本轮压缩交接的恢复入口是哪个文档
- [A] fused=2 vec=1 bm25=3 spo=1 | vec40ms bm2556ms spo166ms | top1源=hot:vector | 工作流自增长是怎么实现的，成功路径怎么沉淀
- [A] fused=13 vec=1 bm25=None spo=None | vec41ms bm2557ms spo150ms | top1源=hot:vector | G3 四保护是哪四个，PlanGate 怎么触发
- [A] fused=11 vec=1 bm25=None spo=None | vec38ms bm2548ms spo118ms | top1源=hot:vector | 执行层监控 Hot Warm Cold 分别做什么
- [A] fused=17 vec=7 bm25=None spo=None | vec41ms bm2554ms spo165ms | top1源=hot:vector | TaskRunner 重规划循环怎么工作，为什么高风险要停下
- [A] fused=1 vec=5 bm25=3 spo=None | vec39ms bm2552ms spo119ms | top1源=hot:vector | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区别
- [A] fused=1 vec=1 bm25=1 spo=13 | vec41ms bm2550ms spo128ms | top1源=hot:vector | 变更日志怎么回看和介入，approve reject 语义
- [A] fused=14 vec=3 bm25=None spo=None | vec43ms bm2558ms spo160ms | top1源=hot:bm25 | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
- [C] fused=None vec=None bm25=None spo=None | vec42ms bm2549ms spo118ms | top1源=hot:bm25 | 技能生命周期怎么做活性管理的
- [A] fused=6 vec=3 bm25=None spo=None | vec39ms bm2556ms spo164ms | top1源=hot:vector | 对话树和召回是什么关系，命中怎么并行
- [A] fused=8 vec=None bm25=17 spo=20 | vec37ms bm2553ms spo138ms | top1源=hot:vector | 元认知复盘每几轮做一次，和策略权重什么关系
- [A] fused=2 vec=3 bm25=9 spo=9 | vec43ms bm2552ms spo170ms | top1源=hot:vector | 编码类请求怎么识别，施工信号有哪些
- [A] fused=1 vec=1 bm25=1 spo=None | vec48ms bm2562ms spo715ms | top1源=hot:vector | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
- [A] fused=17 vec=18 bm25=5 spo=None | vec43ms bm2551ms spo130ms | top1源=hot:vector | 权限门怎么拦截链式 shell 和越权写入
- [A] fused=7 vec=11 bm25=3 spo=None | vec44ms bm2556ms spo149ms | top1源=hot:vector | OS 工具集有哪些，run_session 是干嘛的
- [A] fused=7 vec=2 bm25=3 spo=None | vec45ms bm2553ms spo137ms | top1源=hot:vector | function calling 端到端实测做了什么
- [B] fused=None vec=None bm25=11 spo=None | vec41ms bm2553ms spo145ms | top1源=hot:vector | 执行迹和变更日志两个白盒视图各展示什么
- [B] fused=None vec=17 bm25=None spo=None | vec46ms bm2551ms spo0ms | top1源=hot:vector | 跟 OpenClaw Hermes 对标后我们还差什么
- [A] fused=8 vec=None bm25=2 spo=None | vec44ms bm2551ms spo154ms | top1源=hot:vector | 定时自动化 automation 为什么是孤儿，怎么接
- [A] fused=8 vec=2 bm25=12 spo=None | vec37ms bm2549ms spo139ms | top1源=hot:vector | replanner 自动换方案为什么没做，MC 全场景缺什么
- [A] fused=2 vec=7 bm25=2 spo=1 | vec510ms bm2552ms spo163ms | top1源=hot:vector | 文档漂移检测怎么融入召回评测
- [A] fused=3 vec=1 bm25=3 spo=None | vec50ms bm2558ms spo193ms | top1源=hot:bm25 | 评测看护为什么要有基线和趋势，怎么复跑
- [A] fused=15 vec=4 bm25=None spo=None | vec56ms bm2564ms spo192ms | top1源=hot:bm25 | 第一版发布前还差哪些，前端绑定和量化测试优先级
- [A] fused=1 vec=1 bm25=2 spo=None | vec54ms bm2557ms spo0ms | top1源=hot:vector | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用
- [C] fused=None vec=None bm25=None spo=None | vec42ms bm2558ms spo176ms | top1源=hot:bm25 | 隐式关系候选怎么生成和核验，precision 多少
- [A] fused=1 vec=1 bm25=1 spo=4 | vec49ms bm2573ms spo144ms | top1源=hot:vector | 图导航 API 有哪些，path 和 callers 怎么用
- [A] fused=2 vec=6 bm25=2 spo=4 | vec45ms bm2555ms spo147ms | top1源=hot:vector | Rust 重构召回核心的验收门槛是什么
- [A] fused=1 vec=3 bm25=5 spo=3 | vec57ms bm2577ms spo188ms | top1源=hot:vector | 符号注入怎么压缩上下文，Mermaid 图怎么生成
- [A] fused=6 vec=7 bm25=8 spo=None | vec51ms bm2566ms spo226ms | top1源=hot:bm25 | v2 执行层四壳是哪四层，监控怎么介入
- [B] fused=None vec=None bm25=None spo=20 | vec64ms bm2574ms spo234ms | top1源=hot:bm25 | 存储分层 H/W/C/A 怎么升降，阈值多少
- [A] fused=1 vec=1 bm25=2 spo=None | vec60ms bm2565ms spo173ms | top1源=hot:vector | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
- [B] fused=None vec=18 bm25=None spo=None | vec53ms bm2563ms spo154ms | top1源=hot:vector | PCR zone 和意图分类怎么映射到召回策略
- [A] fused=14 vec=3 bm25=None spo=None | vec59ms bm2563ms spo214ms | top1源=hot:vector | 设计哲学里偏差为什么是养分，归因回流到哪层
- [A] fused=3 vec=1 bm25=2 spo=14 | vec58ms bm2580ms spo157ms | top1源=hot:vector | 子图扩展的 DAG 分层和同步剪枝怎么实现