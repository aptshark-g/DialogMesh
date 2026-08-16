Building prefix dict from the default dictionary ...
Loading model from cache C:\Users\APTShark\AppData\Local\Temp\jieba.cache
Loading model cost 0.751 seconds.
Prefix dict has been built successfully.
Failed to load YAML config from C:\Users\APTShark\.config\memorygraph\discourse.yaml: [WinError 5] �ܾ����ʡ�: 'C:\\Users\\APTShark\\.config\\memorygraph\\discourse.yaml'
文档块: 8369

Loading weights:   0%|          | 0/391 [00:00<?, ?it/s]
Loading weights: 100%|��������������������| 391/391 [00:00<00:00, 21419.91it/s]
# 统一评测 100 条 — 意图感知 + 重排对比（2026-08-17）

- 数据: docs/test/recall_queries_100.md（100 条, 含 intent 列）
- 重排层: ON
- 真 HyDE: ON（K=3, gate=1, 网关 LLM）
- 总耗时: 754s

## dialogue 域（39 条）

- top1: 27/39 (69.2%)
- top3: 79.5% | top5: 87.2%
- MRR@5: 0.760 | nDCG@5: 0.766
- Recall@5: 87.2% | @10: 94.9% | @20: 100.0%
- Context Precision@5: 0.712
- 返回层 parent_context 覆盖: 0/195 个 top5 锚点带文件摘要
- 平均耗时: 5333 ms/query

## doc 域（61 条）

- top1: 33.0/61.0 (54.1%)
- top3: 68.9% | top5: 78.7%
- MRR@5: 0.633 | nDCG@5: 0.659
- Recall@5: 78.7% | @10: 82.0% | @20: 90.2%
- Context Precision@5: 0.601
- 返回层 parent_context 覆盖: 305.0/305.0 个 top5 锚点带文件摘要
- 平均耗时: 8712 ms/query

## 按意图细分（W1 验收）

- casual: n=3  top1=66.7%  top3=66.7%  top5=66.7%
- 代码分析: n=3  top1=66.7%  top3=100.0%  top5=100.0%
- 任务规划: n=18  top1=55.6%  top3=72.2%  top5=88.9%
- 因果推理: n=2  top1=100.0%  top3=100.0%  top5=100.0%
- 数据搜索: n=1  top1=100.0%  top3=100.0%  top5=100.0%
- 记忆召回: n=67  top1=58.2%  top3=71.6%  top5=80.6%
- 通用对话: n=4  top1=50.0%  top3=50.0%  top5=50.0%
- 通用讨论: n=2  top1=100.0%  top3=100.0%  top5=100.0%

## 诊断汇总（为什么）

- 分类: A(融合命中)=94  B(路线内被融合挤出)=6  C(检索缺口)=0
- top1 命中块的来源: {'hot:vector': 54, 'hot:bm25': 4, 'diffusion': 1, 'hot:spo': 1}
- 期望块在单路线排第 1 的 query 数: {'vector': 57, 'bm25': 53, 'spo': 13}
- 期望块进入某路线 top-20 的 query 数: {'vector': 95, 'bm25': 91, 'spo': 42}
- 融合命中但非 top1（排序竞争）: 34
- 各路线平均耗时 ms/query: {'vector': 26.9, 'bm25': 27.4, 'spo': 89.4}

## 逐条明细

- [A/通用讨论] fused=1 vec=1 bm25=1 spo=1 | vec2ms bm251ms spo8ms | top1源=hot:vector | 如果想做一个pi一样的agent你会怎么做？
- [A/数据搜索] fused=1 vec=1 bm25=1 spo=1 | vec1ms bm251ms spo26ms | top1源=hot:vector | 去看看pi的信息，openclaw的原型貌似是，去查一下
- [A/通用讨论] fused=1 vec=1 bm25=2 spo=None | vec2ms bm251ms spo17ms | top1源=hot:vector | 你现在可以做编排吗？有那些内容是你可以操作的？
- [A/任务规划] fused=8 vec=12 bm25=1 spo=None | vec1ms bm251ms spo17ms | top1源=hot:vector | 试试看任务编排，你规划一个，设计里面我是可以改的吧？
- [A/任务规划] fused=2 vec=4 bm25=3 spo=1 | vec1ms bm251ms spo26ms | top1源=hot:spo | 你是无法去做任务规划吗？直接给一个完整的检验任务规划，系统会去做吧？
- [A/任务规划] fused=1 vec=7 bm25=3 spo=1 | vec1ms bm251ms spo7ms | top1源=hot:vector | 你可以直接规划刀任务的吧？就用你发的这个
- [A/任务规划] fused=1 vec=2 bm25=1 spo=4 | vec1ms bm251ms spo16ms | top1源=hot:bm25 | 你不能直接加载到任务里面吗？
- [A/任务规划] fused=5 vec=16 bm25=14 spo=None | vec1ms bm251ms spo12ms | top1源=hot:bm25 | 现在可以去规划了吧？
- [A/因果推理] fused=1 vec=3 bm25=1 spo=1 | vec1ms bm251ms spo8ms | top1源=diffusion | 没显示什么情况
- [A/任务规划] fused=1 vec=1 bm25=1 spo=7 | vec1ms bm252ms spo8ms | top1源=hot:vector | 帮我规划一个代码审查任务
- [A/任务规划] fused=7 vec=1 bm25=8 spo=8 | vec1ms bm251ms spo8ms | top1源=hot:spo | 你现在来规划一个东西，然后给我规划图
- [A/通用对话] fused=8 vec=1 bm25=4 spo=None | vec2ms bm251ms spo8ms | top1源=hot:vector | 我改了你能看到吗？
- [A/通用对话] fused=1 vec=1 bm25=1 spo=2 | vec2ms bm251ms spo8ms | top1源=hot:vector | 现在我改了你收到了？
- [A/任务规划] fused=5 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 帮我规划一个用户登录系统
- [A/通用对话] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 有上下文吗？
- [A/任务规划] fused=1 vec=6 bm25=2 spo=3 | vec2ms bm251ms spo15ms | top1源=hot:bm25 | 规划一个用户登录系统，包含注册、JWT认证、密码找回
- [A/任务规划] fused=2 vec=2 bm25=3 spo=4 | vec2ms bm251ms spo8ms | top1源=hot:spo | 规划一个用户登录系统
- [A/通用对话] fused=13 vec=2 bm25=1 spo=None | vec1ms bm251ms spo10ms | top1源=hot:vector | 你现在所知的上下文有什么
- [A/任务规划] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo23ms | top1源=hot:vector | 设计一个用户登录系统，包含JWT认证和数据库设计
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 简短说一下JWT和Session的区别
- [A/casual] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 我是一个喜欢探索新技术的软件工程师
- [A/任务规划] fused=1 vec=2 bm25=1 spo=1 | vec1ms bm251ms spo22ms | top1源=hot:vector | 设计一个全新的探索性系统架构，我计划分步骤实现，先验证核心模式
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=1 | vec2ms bm251ms spo9ms | top1源=hot:vector | 简述微服务架构的优势
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=3 | vec1ms bm251ms spo10ms | top1源=hot:vector | 审计测试：微服务架构的优缺点
- [A/任务规划] fused=1 vec=1 bm25=2 spo=None | vec2ms bm251ms spo8ms | top1源=hot:vector | 设计用户登录系统的JWT认证方案
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | PostgreSQL数据库选型对比MySQL
- [A/任务规划] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo22ms | top1源=hot:vector | 设计一个全新的探索性系统架构，我计划分步骤验证核心模式，需要规范化的流程和明确的测试标准
- [A/任务规划] fused=2 vec=2 bm25=2 spo=None | vec1ms bm251ms spo22ms | top1源=hot:vector | 设计全新探索性系统架构，计划分步骤验证核心模式，需要规范化流程和明确测试标准
- [A/任务规划] fused=1 vec=1 bm25=1 spo=2 | vec1ms bm251ms spo15ms | top1源=hot:vector | 设计一个用户认证系统，需要规范流程和明确测试标准
- [A/casual] fused=1 vec=1 bm25=2 spo=None | vec1ms bm251ms spo15ms | top1源=hot:vector | 我叫小明，我的项目是DialogMesh
- [A/记忆召回] fused=1 vec=1 bm25=6 spo=2 | vec2ms bm251ms spo16ms | top1源=hot:vector | 我叫什么名字？我的项目是什么？
- [A/因果推理] fused=1 vec=1 bm25=1 spo=1 | vec2ms bm251ms spo16ms | top1源=hot:spo | 帮我分析一下这个系统的架构设计，网关和状态机的关系是什么
- [A/任务规划] fused=4 vec=3 bm25=1 spo=None | vec2ms bm251ms spo8ms | top1源=hot:vector | 帮我规划一个用户登录系统的JWT认证方案
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo8ms | top1源=hot:vector | 刚才的方案里 JWT 有效期怎么设置比较合理？
- [A/casual] fused=20 vec=1 bm25=1 spo=None | vec1ms bm251ms spo9ms | top1源=hot:vector | 你好,介绍一下你自己
- [A/代码分析] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo16ms | top1源=hot:bm25 | 修改 core/agent/recall 下的召回服务，把 bm25 权重提高
- [A/任务规划] fused=1 vec=1 bm25=1 spo=None | vec2ms bm251ms spo17ms | top1源=hot:bm25 | 写一份关于统一召回方案的简短设计文档，保存到 data/demo_recall_doc.
- [A/代码分析] fused=2 vec=1 bm25=1 spo=None | vec1ms bm251ms spo24ms | top1源=hot:vector | 写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。
- [A/代码分析] fused=1 vec=1 bm25=1 spo=None | vec1ms bm251ms spo17ms | top1源=hot:vector | 写一个 Python 脚本计算 1 到 100 的质数之和并运行验证，然后告诉我结果。
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=3 | vec37ms bm2550ms spo115ms | top1源=hot:vector | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
- [A/记忆召回] fused=12 vec=None bm25=2 spo=None | vec61ms bm2564ms spo143ms | top1源=hot:vector | agentic 工具节点怎么让 LLM 自己调工具
- [A/记忆召回] fused=3 vec=4 bm25=11 spo=2 | vec42ms bm2570ms spo135ms | top1源=hot:vector | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
- [A/记忆召回] fused=2 vec=1 bm25=2 spo=None | vec42ms bm2545ms spo168ms | top1源=hot:vector | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=None | vec40ms bm2555ms spo174ms | top1源=hot:vector | 执行偏差怎么触发宏观计划改变，双向归因是什么
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=3 | vec38ms bm2543ms spo171ms | top1源=hot:vector | 用户介入分几级？PlanGate 和异步日志怎么分工
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=6 | vec35ms bm2547ms spo156ms | top1源=hot:vector | 蓝图薄点审计发现了哪些没接线的模块
- [A/记忆召回] fused=1 vec=1 bm25=3 spo=None | vec40ms bm2548ms spo156ms | top1源=hot:vector | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=3 | vec41ms bm2542ms spo150ms | top1源=hot:vector | recall 结果怎么注入执行层，锚点为什么带路径
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=3 | vec39ms bm2543ms spo158ms | top1源=hot:vector | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
- [A/记忆召回] fused=1 vec=5 bm25=1 spo=None | vec36ms bm2545ms spo114ms | top1源=hot:vector | subgraph 节点的 recall_anchor 参数是干嘛的
- [A/记忆召回] fused=3 vec=13 bm25=8 spo=None | vec32ms bm2538ms spo162ms | top1源=hot:vector | 统一召回用了哪些算法，RRF 融合提升多少
- [A/记忆召回] fused=4 vec=3 bm25=7 spo=None | vec44ms bm2554ms spo130ms | top1源=hot:vector | SPO 约束投影怎么提炼主宾关系，谓语权重多少
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec34ms bm2550ms spo164ms | top1源=hot:vector | 中文 SPO 怎么处理，双语两阶段是什么
- [A/记忆召回] fused=4 vec=1 bm25=None spo=None | vec34ms bm2538ms spo121ms | top1源=hot:vector | 记忆怎么按热温冷分层，预取怎么触发
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec34ms bm2542ms spo107ms | top1源=hot:vector | 召回第二批施工做了哪些事，黄金集多少条
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec31ms bm2541ms spo116ms | top1源=hot:vector | 召回评测为什么要有四路 Baseline 对比
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec32ms bm2544ms spo153ms | top1源=hot:vector | 文档语料召回测试的 query 怎么来，为什么要人工标注
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=3 | vec38ms bm2545ms spo111ms | top1源=hot:vector | 第一版功能核对清单里 C1-C4 权限是什么
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec34ms bm2542ms spo115ms | top1源=hot:vector | 端到端自检 E1-E5 分别检查什么
- [A/记忆召回] fused=4 vec=1 bm25=5 spo=None | vec33ms bm2541ms spo160ms | top1源=hot:vector | 树是推理工作台是什么意思，遗忘怎么处理
- [A/记忆召回] fused=1 vec=1 bm25=4 spo=10 | vec31ms bm2538ms spo118ms | top1源=hot:vector | 记录永不可删和抽象可逆推是哪几条公理
- [A/记忆召回] fused=4 vec=2 bm25=None spo=None | vec445ms bm2539ms spo161ms | top1源=hot:vector | 偏差是养分怎么理解，归因回流到哪层
- [A/记忆召回] fused=1 vec=1 bm25=2 spo=1 | vec37ms bm2542ms spo156ms | top1源=hot:vector | 白盒化承诺是什么，为什么行为必记录
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=10 | vec31ms bm2539ms spo110ms | top1源=hot:vector | M1 到 M9 的施工顺序是什么
- [B/记忆召回] fused=None vec=15 bm25=None spo=None | vec36ms bm2541ms spo125ms | top1源=hot:vector | 阶段 A 和阶段 B 分别包含哪些模块
- [B/记忆召回] fused=None vec=None bm25=None spo=13 | vec34ms bm2540ms spo112ms | top1源=hot:vector | v2.1 召回桥之后下一个施工项是什么
- [A/记忆召回] fused=9 vec=18 bm25=15 spo=12 | vec34ms bm2543ms spo115ms | top1源=hot:vector | 本轮压缩交接的恢复入口是哪个文档
- [A/记忆召回] fused=1 vec=1 bm25=3 spo=1 | vec39ms bm2547ms spo145ms | top1源=hot:vector | 工作流自增长是怎么实现的，成功路径怎么沉淀
- [A/记忆召回] fused=1 vec=1 bm25=9 spo=None | vec34ms bm2537ms spo143ms | top1源=hot:vector | G3 四保护是哪四个，PlanGate 怎么触发
- [A/记忆召回] fused=8 vec=1 bm25=None spo=None | vec33ms bm2542ms spo117ms | top1源=hot:vector | 执行层监控 Hot Warm Cold 分别做什么
- [B/记忆召回] fused=None vec=17 bm25=None spo=None | vec48ms bm2540ms spo143ms | top1源=hot:vector | TaskRunner 重规划循环怎么工作，为什么高风险要停下
- [B/记忆召回] fused=None vec=None bm25=2 spo=None | vec39ms bm2547ms spo123ms | top1源=hot:vector | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区别
- [A/记忆召回] fused=2 vec=1 bm25=1 spo=7 | vec37ms bm2540ms spo121ms | top1源=hot:vector | 变更日志怎么回看和介入，approve reject 语义
- [A/记忆召回] fused=2 vec=1 bm25=17 spo=None | vec34ms bm2545ms spo143ms | top1源=hot:vector | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
- [A/记忆召回] fused=1 vec=1 bm25=None spo=None | vec38ms bm2539ms spo114ms | top1源=hot:vector | 技能生命周期怎么做活性管理的
- [A/记忆召回] fused=2 vec=2 bm25=None spo=None | vec49ms bm2557ms spo172ms | top1源=hot:vector | 对话树和召回是什么关系，命中怎么并行
- [A/记忆召回] fused=15 vec=16 bm25=8 spo=19 | vec37ms bm2540ms spo117ms | top1源=hot:vector | 元认知复盘每几轮做一次，和策略权重什么关系
- [A/记忆召回] fused=1 vec=1 bm25=2 spo=2 | vec40ms bm2552ms spo146ms | top1源=hot:vector | 编码类请求怎么识别，施工信号有哪些
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec37ms bm2546ms spo156ms | top1源=hot:vector | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
- [A/记忆召回] fused=2 vec=8 bm25=2 spo=None | vec42ms bm2554ms spo143ms | top1源=hot:vector | 权限门怎么拦截链式 shell 和越权写入
- [A/记忆召回] fused=1 vec=9 bm25=2 spo=1 | vec38ms bm2539ms spo135ms | top1源=hot:vector | OS 工具集有哪些，run_session 是干嘛的
- [A/记忆召回] fused=1 vec=1 bm25=2 spo=None | vec33ms bm2540ms spo106ms | top1源=hot:vector | function calling 端到端实测做了什么
- [B/记忆召回] fused=None vec=None bm25=7 spo=None | vec34ms bm2550ms spo119ms | top1源=hot:vector | 执行迹和变更日志两个白盒视图各展示什么
- [A/记忆召回] fused=14 vec=18 bm25=15 spo=None | vec37ms bm2540ms spo0ms | top1源=hot:vector | 跟 OpenClaw Hermes 对标后我们还差什么
- [A/记忆召回] fused=1 vec=10 bm25=1 spo=None | vec34ms bm2540ms spo148ms | top1源=hot:vector | 定时自动化 automation 为什么是孤儿，怎么接
- [B/记忆召回] fused=None vec=2 bm25=3 spo=None | vec33ms bm2539ms spo112ms | top1源=hot:vector | replanner 自动换方案为什么没做，MC 全场景缺什么
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=1 | vec35ms bm2544ms spo125ms | top1源=hot:vector | 文档漂移检测怎么融入召回评测
- [A/记忆召回] fused=2 vec=1 bm25=1 spo=None | vec34ms bm2539ms spo168ms | top1源=hot:vector | 评测看护为什么要有基线和趋势，怎么复跑
- [A/记忆召回] fused=4 vec=2 bm25=1 spo=None | vec32ms bm2538ms spo146ms | top1源=hot:vector | 第一版发布前还差哪些，前端绑定和量化测试优先级
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec34ms bm2544ms spo0ms | top1源=hot:vector | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用
- [A/记忆召回] fused=18 vec=None bm25=1 spo=17 | vec32ms bm2538ms spo114ms | top1源=hot:vector | 隐式关系候选怎么生成和核验，precision 多少
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=2 | vec37ms bm2544ms spo105ms | top1源=hot:vector | 图导航 API 有哪些，path 和 callers 怎么用
- [A/记忆召回] fused=1 vec=2 bm25=1 spo=1 | vec32ms bm2544ms spo137ms | top1源=hot:vector | Rust 重构召回核心的验收门槛是什么
- [A/记忆召回] fused=1 vec=3 bm25=2 spo=2 | vec36ms bm2547ms spo137ms | top1源=hot:vector | 符号注入怎么压缩上下文，Mermaid 图怎么生成
- [A/记忆召回] fused=1 vec=1 bm25=3 spo=None | vec34ms bm2539ms spo130ms | top1源=hot:vector | v2 执行层四壳是哪四层，监控怎么介入
- [A/记忆召回] fused=11 vec=20 bm25=4 spo=12 | vec38ms bm2545ms spo120ms | top1源=hot:vector | 存储分层 H/W/C/A 怎么升降，阈值多少
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=None | vec32ms bm2538ms spo119ms | top1源=hot:vector | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
- [A/记忆召回] fused=2 vec=2 bm25=3 spo=2 | vec30ms bm2546ms spo549ms | top1源=hot:vector | PCR zone 和意图分类怎么映射到召回策略
- [A/记忆召回] fused=5 vec=2 bm25=None spo=None | vec40ms bm2550ms spo175ms | top1源=hot:vector | 设计哲学里偏差为什么是养分，归因回流到哪层
- [A/记忆召回] fused=1 vec=1 bm25=1 spo=9 | vec33ms bm2543ms spo111ms | top1源=hot:vector | 子图扩展的 DAG 分层和同步剪枝怎么实现
