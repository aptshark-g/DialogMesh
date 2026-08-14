# 推理精排试点 — doc 域（2026-08-14）

- 模型: qwen35 (http://127.0.0.1:1235, thinking ON + 预算受限)
- 协议: 方面覆盖（问题拆方面 → 候选判覆盖 → 选覆盖最多无矛盾）
- 链路: 融合 top-5 窄窗 + LLM 判断（不替换排序）

## 汇总

- 运行: 61 条 doc 查询
- fused top1: 32/61 (52.5%)
- **推理 LLM top1: 27/61 (44.3%)**
- 上行（fused miss → LLM 中）: 1
- 下行（fused 中 → LLM 拆）: 6
- 解析失败: 4
- 平均 LLM 延迟: 14614 ms/query

## 逐条（含思考摘要）

- fused=True llm=False pick=0 11897ms | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate answers based on a given question. 
- fused=False llm=False pick=1 11652ms | agentic 工具节点怎么让 LLM 自己调工具
    思考: The user wants to identify which candidate best explains how an "agentic tool node" allows an LLM to call tools autonomo
- fused=False llm=False pick=1 11835ms | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a given question.
- fused=True llm=True pick=5 11819ms | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate options against a given problem.   
- fused=False llm=False pick=1 11887ms | 执行偏差怎么触发宏观计划改变，双向归因是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 9029ms | 用户介入分几级？PlanGate 和异步日志怎么分工
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Select the best candidate(s) that cover the most aspec
- fused=True llm=True pick=1 11694ms | 蓝图薄点审计发现了哪些没接线的模块
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Identify which candidate best covers the aspects of th
- fused=True llm=True pick=1 11749ms | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a specific questi
- fused=True llm=True pick=1 11726ms | recall 结果怎么注入执行层，锚点为什么带路径
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 12328ms | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 4526ms | subgraph 节点的 recall_anchor 参数是干嘛的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Question:** "subgraph 节点的 recall_anchor 参数是干嘛的" (What is the `
- fused=False llm=False pick=1 12047ms | 统一召回用了哪些算法，RRF 融合提升多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A question ("统一召回用了哪些算法，RRF 融合提升多少" - Which algorithms ar
- fused=False llm=False pick=2 12161ms | SPO 约束投影怎么提炼主宾关系，谓语权重多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate answers based on a given question. 
- fused=True llm=True pick=1 10700ms | 中文 SPO 怎么处理，双语两阶段是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate answers based on a given question. 
- fused=False llm=False pick=1 12107ms | 记忆怎么按热温冷分层，预取怎么触发
    思考: The user wants to identify which candidate best answers the question: "How is memory layered by hot/warm/cold, and how i
- fused=True llm=True pick=1 12232ms | 召回第二批施工做了哪些事，黄金集多少条
    思考: The user wants to identify which candidate best answers the question: "召回第二批施工做了哪些事，黄金集多少条" (What actions were taken in 
- fused=True llm=True pick=1 17826ms | 召回评测为什么要有四路 Baseline 对比
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate answers against a given question.  
- fused=True llm=True pick=2 12123ms | 文档语料召回测试的 query 怎么来，为什么要人工标注
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 12203ms | 第一版功能核对清单里 C1-C4 权限是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A question ("第一版功能核对清单里 C1-C4 权限是什么" - What are the C1-C4
- fused=True llm=True pick=1 11920ms | 端到端自检 E1-E5 分别检查什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Identify the candidate that covers the most aspects of
- fused=False llm=False pick=2 12130ms | 树是推理工作台是什么意思，遗忘怎么处理
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=False pick=2 4347ms | 记录永不可删和抽象可逆推是哪几条公理
    思考: The user wants to identify which candidate documents cover the most aspects of the question "记录永不可删和抽象可逆推是哪几条公理" (Which 
- fused=False llm=False pick=1 6022ms | 偏差是养分怎么理解，归因回流到哪层
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 16119ms | 白盒化承诺是什么，为什么行为必记录
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/summaries against a given
- fused=False llm=True pick=2 18104ms | M1 到 M9 的施工顺序是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Determine the construction order of M1 to M9 based on 
- fused=False llm=False pick=1 19230ms | 阶段 A 和阶段 B 分别包含哪些模块
    思考: The user wants to identify which candidate best answers the question: "What modules are included in Phase A and Phase B 
- fused=False llm=False pick=2 18402ms | v2.1 召回桥之后下一个施工项是什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Identify the candidate that covers the most aspects of
- fused=False llm=False pick=0 18992ms | 本轮压缩交接的恢复入口是哪个文档
    思考: The user wants to identify the correct document that serves as the "restoration entry point" (恢复入口) for the "current rou
- fused=True llm=True pick=1 15201ms | 工作流自增长是怎么实现的，成功路径怎么沉淀
    思考: The user wants to identify which candidate best answers the question: "How is workflow self-growth implemented, and how 
- fused=True llm=True pick=1 13758ms | G3 四保护是哪四个，PlanGate 怎么触发
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents based on a specific quest
- fused=True llm=True pick=3 18087ms | 执行层监控 Hot Warm Cold 分别做什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets to answer the qu
- fused=False llm=False pick=2 18961ms | TaskRunner 重规划循环怎么工作，为什么高风险要停下
    思考: The user wants to identify which candidate best explains "How the TaskRunner re-planning loop works" and "Why high-risk 
- fused=False llm=False pick=1 18742ms | 决策事件有哪些 kind，strategy_switch 和 plan_gate
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents based on a given question
- fused=False llm=False pick=3 18834ms | 变更日志怎么回看和介入，approve reject 语义
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate options based on a given problem.  
- fused=True llm=True pick=1 7081ms | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
    思考: The user wants to identify which candidate best answers the question: "How is the distillation raw material pipeline col
- fused=True llm=False pick=3 18678ms | 技能生命周期怎么做活性管理的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/summaries against a given
- fused=False llm=False pick=1 18996ms | 对话树和召回是什么关系，命中怎么并行
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents based on a given question
- fused=False llm=False pick=1 19065ms | 元认知复盘每几轮做一次，和策略权重什么关系
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=True llm=True pick=1 18663ms | 编码类请求怎么识别，施工信号有哪些
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Identify which candidate(s) cover the most aspects of 
- fused=True llm=False pick=5 19253ms | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents/snippets against a given 
- fused=False llm=False pick=1 18943ms | 权限门怎么拦截链式 shell 和越权写入
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate answers against a given question.  
- fused=False llm=False pick=1 18966ms | OS 工具集有哪些，run_session 是干嘛的
    思考: Thinking Process:  1.  **Analyze the Request:**     *   Input: A question ("OS 工具集有哪些，run_session 是干嘛的" - What OS toolse
- fused=True llm=False pick=3 18932ms | function calling 端到端实测做了什么
    思考: The user wants to identify which candidate best answers the question "function calling 端到端实测做了什么" (What was done for the
- fused=False llm=False pick=0 18712ms | 执行迹和变更日志两个白盒视图各展示什么
    思考: The user wants to identify which candidate best answers the question: "What do the two white-box views, Execution Trace 
- fused=False llm=False pick=1 18973ms | 跟 OpenClaw Hermes 对标后我们还差什么
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate options against a given question.  
- fused=False llm=False pick=3 19065ms | 定时自动化 automation 为什么是孤儿，怎么接
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents to answer the user's ques
- fused=True llm=True pick=1 18923ms | replanner 自动换方案为什么没做，MC 全场景缺什么
    思考: The user wants to identify which candidate best addresses the question: "Why didn't replanner automatically switch plans
- fused=True llm=True pick=1 19062ms | 文档漂移检测怎么融入召回评测
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a given problem. 
- fused=True llm=True pick=1 18921ms | 评测看护为什么要有基线和趋势，怎么复跑
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a given problem. 
- fused=False llm=False pick=1 14224ms | 第一版发布前还差哪些，前端绑定和量化测试优先级
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a given problem. 
- fused=True llm=True pick=3 16464ms | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用
    思考: The user wants me to select the best candidate from the provided list based on a specific problem. The problem is: "How 
- fused=False llm=False pick=1 15904ms | 隐式关系候选怎么生成和核验，precision 多少
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents against a given question.
- fused=True llm=True pick=2 18871ms | 图导航 API 有哪些，path 和 callers 怎么用
    思考: The user wants to identify which candidate best answers the question "图导航 API 有哪些，path 和 callers 怎么用" (What are the grap
- fused=True llm=False pick=0 15022ms | Rust 重构召回核心的验收门槛是什么
    思考: The user wants to identify which candidate document best answers the question: "What are the acceptance criteria for the
- fused=False llm=False pick=3 14670ms | 符号注入怎么压缩上下文，Mermaid 图怎么生成
    思考: The user wants to identify which candidate documents best answer the question: "How to compress context with symbol inje
- fused=False llm=False pick=1 16180ms | v2 执行层四壳是哪四层，监控怎么介入
    思考: The user wants to identify the "four shells" (四壳) of the v2 execution layer and how monitoring intervenes, based on the 
- fused=False llm=False pick=1 15691ms | 存储分层 H/W/C/A 怎么升降，阈值多少
    思考: The user wants to identify which candidate best answers the question: "How to promote/demote storage tiers H/W/C/A and w
- fused=True llm=True pick=2 12222ms | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Select the best candidate(s) that cover the most aspec
- fused=False llm=False pick=3 12199ms | PCR zone 和意图分类怎么映射到召回策略
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Select the best candidate(s) that cover the most aspec
- fused=False llm=False pick=1 5217ms | 设计哲学里偏差为什么是养分，归因回流到哪层
    思考: Thinking Process:  1.  **Analyze the Request:**     *   **Task:** Evaluate candidate documents based on a given question
- fused=True llm=True pick=1 12190ms | 子图扩展的 DAG 分层和同步剪枝怎么实现
    思考: The user wants to identify the best candidate that answers the question "How to implement DAG layering and synchronous p