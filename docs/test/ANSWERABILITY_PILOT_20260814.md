# 质量筛选评测 — 推理 LLM 可答性判断（2026-08-14）

- 模型: qwen35 (http://127.0.0.1:1235, thinking ON + 预算)
- 输入: 问题 + top-5 锚点 + 父摘要 | 标签: 期望 ∈ top-5
- 平均延迟: 12956 ms/query

## 汇总

- 运行: 61 | 标签'能回答': 45 | 判断'能': 24
- 判断准确率: 39.3%
- '能'判断 precision: 83.3% | recall: 95.2%
- 缺口检测（标签'不能' 且 判断'不能'）: 4 条

## 逐条

- label=能 judge=True 14864ms | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=不能 judge=None 14326ms | agentic 工具节点怎么让 LLM 自己调工具
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=None 14400ms | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14429ms | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=True 4562ms | 执行偏差怎么触发宏观计划改变，双向归因是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14369ms | 用户介入分几级？PlanGate 和异步日志怎么分工
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: Retrieved search results (5 snippets 
- label=能 judge=True 14355ms | 蓝图薄点审计发现了哪些没接线的模块
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=None 14346ms | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=True 14390ms | recall 结果怎么注入执行层，锚点为什么带路径
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=True 14446ms | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14465ms | subgraph 节点的 recall_anchor 参数是干嘛的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=True 14439ms | 统一召回用了哪些算法，RRF 融合提升多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A set of retrieved documents (召回资料) a
- label=能 judge=True 6179ms | SPO 约束投影怎么提炼主宾关系，谓语权重多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=True 4607ms | 中文 SPO 怎么处理，双语两阶段是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14415ms | 记忆怎么按热温冷分层，预取怎么触发
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14518ms | 召回第二批施工做了哪些事，黄金集多少条
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A set of retrieved documents (recall 
- label=能 judge=False 14484ms | 召回评测为什么要有四路 Baseline 对比
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question ("召回评测为什么要有四路 Baseline 
- label=能 judge=True 8585ms | 文档语料召回测试的 query 怎么来，为什么要人工标注
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved documen
- label=能 judge=True 14449ms | 第一版功能核对清单里 C1-C4 权限是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=能 judge=True 14458ms | 端到端自检 E1-E5 分别检查什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14435ms | 树是推理工作台是什么意思，遗忘怎么处理
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question ("树是推理工作台是什么意思，遗忘怎么处理" 
- label=能 judge=True 14303ms | 记录永不可删和抽象可逆推是哪几条公理
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=True 14370ms | 偏差是养分怎么理解，归因回流到哪层
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=None 14342ms | 白盒化承诺是什么，为什么行为必记录
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14454ms | M1 到 M9 的施工顺序是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question ("M1 到 M9 的施工顺序是什么" - W
- label=不能 judge=True 14483ms | 阶段 A 和阶段 B 分别包含哪些模块
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=不能 judge=False 4554ms | v2.1 召回桥之后下一个施工项是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=None 14528ms | 本轮压缩交接的恢复入口是哪个文档
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=True 14491ms | 工作流自增长是怎么实现的，成功路径怎么沉淀
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=能 judge=None 14455ms | G3 四保护是哪四个，PlanGate 怎么触发
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14476ms | 执行层监控 Hot Warm Cold 分别做什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=不能 judge=None 14337ms | TaskRunner 重规划循环怎么工作，为什么高风险要停下
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=不能 judge=False 5688ms | 决策事件有哪些 kind，strategy_switch 和 plan_
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=True 4547ms | 变更日志怎么回看和介入，approve reject 语义
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=能 judge=None 14416ms | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=True 14377ms | 技能生命周期怎么做活性管理的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14429ms | 对话树和召回是什么关系，命中怎么并行
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=False 4523ms | 元认知复盘每几轮做一次，和策略权重什么关系
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question + Retrieved documents (
- label=能 judge=None 14426ms | 编码类请求怎么识别，施工信号有哪些
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14495ms | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question + Retrieved documents (
- label=不能 judge=None 14439ms | 权限门怎么拦截链式 shell 和越权写入
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=不能 judge=True 14365ms | OS 工具集有哪些，run_session 是干嘛的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A list of retrieved documents (召回资料) 
- label=能 judge=None 14425ms | function calling 端到端实测做了什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=None 14448ms | 执行迹和变更日志两个白盒视图各展示什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=True 14422ms | 跟 OpenClaw Hermes 对标后我们还差什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=不能 judge=None 14415ms | 定时自动化 automation 为什么是孤儿，怎么接
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=None 14403ms | replanner 自动换方案为什么没做，MC 全场景缺什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14507ms | 文档漂移检测怎么融入召回评测
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question ("文档漂移检测怎么融入召回评测" - How
- label=能 judge=None 14466ms | 评测看护为什么要有基线和趋势，怎么复跑
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and retrieved search 
- label=能 judge=True 14540ms | 第一版发布前还差哪些，前端绑定和量化测试优先级
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=能 judge=True 6034ms | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=不能 judge=False 14415ms | 隐式关系候选怎么生成和核验，precision 多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14382ms | 图导航 API 有哪些，path 和 callers 怎么用
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A list of retrieved documents (recall
- label=能 judge=True 14444ms | Rust 重构召回核心的验收门槛是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=None 14432ms | 符号注入怎么压缩上下文，Mermaid 图怎么生成
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=能 judge=None 14458ms | v2 执行层四壳是哪四层，监控怎么介入
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=不能 judge=None 14495ms | 存储分层 H/W/C/A 怎么升降，阈值多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents
- label=能 judge=None 14482ms | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved search re
- label=不能 judge=None 14500ms | PCR zone 和意图分类怎么映射到召回策略
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A user question and a set of retrieve
- label=能 judge=True 4519ms | 设计哲学里偏差为什么是养分，归因回流到哪层
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question + Retrieved documents (
- label=能 judge=True 14505ms | 子图扩展的 DAG 分层和同步剪枝怎么实现
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: User question and retrieved documents