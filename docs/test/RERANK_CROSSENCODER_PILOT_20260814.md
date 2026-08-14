# cross-encoder 精排试点 — doc 域（2026-08-14）

- 模型: C:\Users\APTShark\PycharmProjects\DialogMesh\models\bge-reranker-v2-m3 (CrossEncoder, 判别式相关性打分)
- 粗召回: 融合 top-15（与 LLM 试点同口径）
- 总耗时: 29s | 平均打分: 481 ms/query

## 汇总

- 运行: 61 条 doc 查询
- fused top1: 31/61 (50.8%)
- **CE top1: 27/61 (44.3%)**
- **RRF(fused+CE) top1: 28/61 (45.9%)** — 多信号后期融合, 不替换
- fused 文件级 top1: 31/61 (50.8%)
- CE 文件级 top1: 27/61 (44.3%)
- MRR@15 fused: 0.618 | CE: 0.565 | RRF: 0.588

## 逐条

- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | agentic 工具节点怎么让 LLM 自己调工具
- fused_rank=2 ce_rank=3 rrf_rank=2 file=2/3 [hot:vector] | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
- fused_rank=2 ce_rank=1 rrf_rank=1 file=2/1 [hot:vector] | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
- fused_rank=2 ce_rank=1 rrf_rank=1 file=2/1 [hot:vector] | 执行偏差怎么触发宏观计划改变，双向归因是什么
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 用户介入分几级？PlanGate 和异步日志怎么分工
- fused_rank=1 ce_rank=2 rrf_rank=2 file=1/2 [hot:vector] | 蓝图薄点审计发现了哪些没接线的模块
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
- fused_rank=1 ce_rank=2 rrf_rank=1 file=1/2 [hot:vector] | recall 结果怎么注入执行层，锚点为什么带路径
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
- fused_rank=1 ce_rank=3 rrf_rank=1 file=1/3 [hot:vector] | subgraph 节点的 recall_anchor 参数是干嘛的
- fused_rank=6 ce_rank=8 rrf_rank=7 file=6/8 [hot:vector] | 统一召回用了哪些算法，RRF 融合提升多少
- fused_rank=5 ce_rank=1 rrf_rank=2 file=5/1 [hot:vector] | SPO 约束投影怎么提炼主宾关系，谓语权重多少
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 中文 SPO 怎么处理，双语两阶段是什么
- fused_rank=4 ce_rank=6 rrf_rank=4 file=4/6 [hot:vector] | 记忆怎么按热温冷分层，预取怎么触发
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 召回第二批施工做了哪些事，黄金集多少条
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 召回评测为什么要有四路 Baseline 对比
- fused_rank=1 ce_rank=2 rrf_rank=1 file=1/2 [hot:vector] | 文档语料召回测试的 query 怎么来，为什么要人工标注
- fused_rank=1 ce_rank=3 rrf_rank=3 file=1/3 [hot:vector] | 第一版功能核对清单里 C1-C4 权限是什么
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 端到端自检 E1-E5 分别检查什么
- fused_rank=4 ce_rank=7 rrf_rank=5 file=4/7 [hot:vector] | 树是推理工作台是什么意思，遗忘怎么处理
- fused_rank=3 ce_rank=6 rrf_rank=4 file=3/6 [hot:vector] | 记录永不可删和抽象可逆推是哪几条公理
- fused_rank=3 ce_rank=6 rrf_rank=3 file=3/6 [hot:vector] | 偏差是养分怎么理解，归因回流到哪层
- fused_rank=1 ce_rank=8 rrf_rank=3 file=1/8 [hot:vector] | 白盒化承诺是什么，为什么行为必记录
- fused_rank=2 ce_rank=6 rrf_rank=3 file=2/6 [hot:vector] | M1 到 M9 的施工顺序是什么
- fused_rank=15 ce_rank=15 rrf_rank=15 file=15/15 [hot:vector] | 阶段 A 和阶段 B 分别包含哪些模块
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | v2.1 召回桥之后下一个施工项是什么
- fused_rank=6 ce_rank=13 rrf_rank=11 file=6/13 [hot:vector] | 本轮压缩交接的恢复入口是哪个文档
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 工作流自增长是怎么实现的，成功路径怎么沉淀
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | G3 四保护是哪四个，PlanGate 怎么触发
- fused_rank=5 ce_rank=1 rrf_rank=3 file=5/1 [hot:vector] | 执行层监控 Hot Warm Cold 分别做什么
- fused_rank=13 ce_rank=2 rrf_rank=9 file=13/2 [hot:vector] | TaskRunner 重规划循环怎么工作，为什么高风险要停下
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区
- fused_rank=1 ce_rank=2 rrf_rank=2 file=1/2 [hot:vector] | 变更日志怎么回看和介入，approve reject 语义
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
- fused_rank=2 ce_rank=1 rrf_rank=2 file=2/1 [hot:vector] | 技能生命周期怎么做活性管理的
- fused_rank=10 ce_rank=1 rrf_rank=5 file=10/1 [hot:vector] | 对话树和召回是什么关系，命中怎么并行
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 元认知复盘每几轮做一次，和策略权重什么关系
- fused_rank=1 ce_rank=6 rrf_rank=2 file=1/6 [hot:vector] | 编码类请求怎么识别，施工信号有哪些
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
- fused_rank=3 ce_rank=4 rrf_rank=4 file=3/4 [hot:vector] | 权限门怎么拦截链式 shell 和越权写入
- fused_rank=2 ce_rank=1 rrf_rank=1 file=2/1 [hot:vector] | OS 工具集有哪些，run_session 是干嘛的
- fused_rank=1 ce_rank=2 rrf_rank=1 file=1/2 [hot:vector] | function calling 端到端实测做了什么
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 执行迹和变更日志两个白盒视图各展示什么
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 跟 OpenClaw Hermes 对标后我们还差什么
- fused_rank=1 ce_rank=3 rrf_rank=1 file=1/3 [hot:vector] | 定时自动化 automation 为什么是孤儿，怎么接
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | replanner 自动换方案为什么没做，MC 全场景缺什么
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 文档漂移检测怎么融入召回评测
- fused_rank=2 ce_rank=1 rrf_rank=2 file=2/1 [hot:vector] | 评测看护为什么要有基线和趋势，怎么复跑
- fused_rank=2 ce_rank=5 rrf_rank=2 file=2/5 [hot:vector] | 第一版发布前还差哪些，前端绑定和量化测试优先级
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 隐式关系候选怎么生成和核验，precision 多少
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 图导航 API 有哪些，path 和 callers 怎么用
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | Rust 重构召回核心的验收门槛是什么
- fused_rank=1 ce_rank=2 rrf_rank=3 file=1/2 [hot:vector] | 符号注入怎么压缩上下文，Mermaid 图怎么生成
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | v2 执行层四壳是哪四层，监控怎么介入
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | 存储分层 H/W/C/A 怎么升降，阈值多少
- fused_rank=1 ce_rank=2 rrf_rank=1 file=1/2 [hot:vector] | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
- fused_rank=None ce_rank=None rrf_rank=None file=None/None [hot:vector] | PCR zone 和意图分类怎么映射到召回策略
- fused_rank=4 ce_rank=3 rrf_rank=3 file=4/3 [hot:vector] | 设计哲学里偏差为什么是养分，归因回流到哪层
- fused_rank=1 ce_rank=1 rrf_rank=1 file=1/1 [hot:vector] | 子图扩展的 DAG 分层和同步剪枝怎么实现