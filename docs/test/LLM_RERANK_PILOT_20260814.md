# LLM 精排试点 — doc 域（2026-08-14）

- 模型: qwen/qwen3.5-9b (http://127.0.0.1:1234) | 候选数: 15
- 总耗时: 80s | 平均 LLM 延迟: 1314 ms/query

## 汇总

- 运行: 61 条 doc 查询
- fused top1: 31/61 (50.8%)
- LLM top1: 25/61 (41.0%)
- 上行（fused miss → LLM 中）: 7
- 下行（fused 中 → LLM 拆）: 13
- 期望块未进候选（检索缺口, LLM 无法救）: 6
- LLM 解析失败: 0

## 混合策略模拟（2026-08-14, 从逐条数据计算）

- 运行: 61 条 doc 查询 | fused top1: 31/61 (50.8%) | LLM top1: 25/61 (41.0%)
- 上行（fused miss → LLM 中）: 7 | 下行（fused 中 → LLM 拆）: 13

| 策略 | top1 | 说明 |
|---|---|---|
| V1 纯 fused | 31/61 (50.8%) | 现状基线 |
| V2 纯 LLM 替换 | 25/61 (41.0%) | 拆掉 13 条正确的, 只补 7 条 — 小模型单独排序劣于融合 |
| 受限覆盖 cap= 1 | 31/61 (50.8%) |
| 受限覆盖 cap= 2 | 31/61 (50.8%) |
| 受限覆盖 cap= 3 | 32/61 (52.5%) |
| 受限覆盖 cap= 4 | 34/61 (55.7%) ** |
| 受限覆盖 cap= 5 | 33/61 (54.1%) |
| 受限覆盖 cap= 6 | 32/61 (52.5%) |
| 受限覆盖 cap= 7 | 32/61 (52.5%) |
| 受限覆盖 cap= 8 | 32/61 (52.5%) |
| 受限覆盖 cap=10 | 29/61 (47.5%) |
| 受限覆盖 cap=15 | 25/61 (41.0%) |

关键观察:
- 下行 pick 排名 [3, 3, 5, 6, 7, 9, 9, 9, 11, 12, 13, 13, 14] / 上行 pick 排名 [3, 3, 3, 4, 4, 7, 11] — 排名信号不能完全区分, cap 值换数据集需重验
- LLM 与 fused 一致（pick=1）: fused 对 10 条 / fused 错 4 条 — 'LLM 同意'是强确认信号, 'LLM 不同意'才是模糊区
- 受限覆盖 cap=4 是模拟最优（+4.9pp）; 生产接入建议: DM_LLM_RERANK=1（默认关）+ BASE/MODEL/TIMEOUT 环境变量, 失败降级 fused, 仅 doc/知识类意图启用
- 待网关恢复后用 deepseek-v4-flash 复跑对比模型质量（下行是否收窄）, 再决定小模型/云端模型入生产

## 逐条

- fused=True llm=False rank=1 pick=3 gap=False 323ms [hot:vector] | 执行层怎么分层？tool_loop 和蓝图、元认知是什么关系
- fused=False llm=False rank=None pick=15 gap=True 324ms [hot:vector] | agentic 工具节点怎么让 LLM 自己调工具
- fused=False llm=False rank=2 pick=4 gap=False 251ms [hot:vector] | 蓝图里 tool 节点有哪些参数，agentic 和静态工具节点区别
- fused=False llm=True rank=2 pick=11 gap=False 1556ms [hot:vector] | 5 分钟做一个 MC 游戏，元认知怎么发现超时并换方案
- fused=True llm=True rank=1 pick=1 gap=False 1235ms [hot:vector] | 执行偏差怎么触发宏观计划改变，双向归因是什么
- fused=True llm=False rank=1 pick=9 gap=False 1393ms [hot:vector] | 用户介入分几级？PlanGate 和异步日志怎么分工
- fused=True llm=True rank=1 pick=7 gap=False 1710ms [hot:vector] | 蓝图薄点审计发现了哪些没接线的模块
- fused=True llm=False rank=1 pick=13 gap=False 1159ms [hot:vector] | 权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了
- fused=True llm=False rank=1 pick=7 gap=False 1618ms [hot:vector] | recall 结果怎么注入执行层，锚点为什么带路径
- fused=True llm=True rank=1 pick=1 gap=False 2023ms [hot:vector] | 粗召回和执行层精确查阅怎么配合，为什么不能只靠向量
- fused=True llm=True rank=1 pick=3 gap=False 1349ms [hot:vector] | subgraph 节点的 recall_anchor 参数是干嘛的
- fused=False llm=False rank=8 pick=13 gap=False 1411ms [hot:vector] | 统一召回用了哪些算法，RRF 融合提升多少
- fused=False llm=False rank=5 pick=1 gap=False 1442ms [hot:vector] | SPO 约束投影怎么提炼主宾关系，谓语权重多少
- fused=True llm=True rank=1 pick=1 gap=False 1719ms [hot:vector] | 中文 SPO 怎么处理，双语两阶段是什么
- fused=False llm=True rank=4 pick=4 gap=False 1707ms [hot:vector] | 记忆怎么按热温冷分层，预取怎么触发
- fused=True llm=True rank=1 pick=10 gap=False 1605ms [hot:vector] | 召回第二批施工做了哪些事，黄金集多少条
- fused=True llm=True rank=1 pick=2 gap=False 1366ms [hot:vector] | 召回评测为什么要有四路 Baseline 对比
- fused=True llm=True rank=1 pick=4 gap=False 1334ms [hot:vector] | 文档语料召回测试的 query 怎么来，为什么要人工标注
- fused=True llm=False rank=1 pick=3 gap=False 1426ms [hot:vector] | 第一版功能核对清单里 C1-C4 权限是什么
- fused=True llm=True rank=1 pick=1 gap=False 1338ms [hot:vector] | 端到端自检 E1-E5 分别检查什么
- fused=False llm=False rank=4 pick=2 gap=False 1347ms [hot:vector] | 树是推理工作台是什么意思，遗忘怎么处理
- fused=False llm=False rank=3 pick=5 gap=False 1157ms [hot:vector] | 记录永不可删和抽象可逆推是哪几条公理
- fused=False llm=False rank=5 pick=15 gap=False 1173ms [hot:vector] | 偏差是养分怎么理解，归因回流到哪层
- fused=True llm=False rank=1 pick=5 gap=False 1349ms [hot:vector] | 白盒化承诺是什么，为什么行为必记录
- fused=False llm=True rank=4 pick=4 gap=False 1663ms [hot:vector] | M1 到 M9 的施工顺序是什么
- fused=False llm=False rank=16 pick=7 gap=False 1424ms [hot:vector] | 阶段 A 和阶段 B 分别包含哪些模块
- fused=False llm=False rank=None pick=10 gap=True 1369ms [hot:vector] | v2.1 召回桥之后下一个施工项是什么
- fused=False llm=False rank=8 pick=1 gap=False 1507ms [hot:vector] | 本轮压缩交接的恢复入口是哪个文档
- fused=True llm=True rank=1 pick=10 gap=False 1426ms [hot:vector] | 工作流自增长是怎么实现的，成功路径怎么沉淀
- fused=True llm=True rank=1 pick=1 gap=False 1393ms [hot:vector] | G3 四保护是哪四个，PlanGate 怎么触发
- fused=False llm=True rank=7 pick=7 gap=False 1548ms [hot:vector] | 执行层监控 Hot Warm Cold 分别做什么
- fused=False llm=False rank=3 pick=7 gap=False 1269ms [hot:vector] | TaskRunner 重规划循环怎么工作，为什么高风险要停下
- fused=False llm=False rank=None pick=6 gap=True 1184ms [hot:vector] | 决策事件有哪些 kind，strategy_switch 和 plan_gate 区别
- fused=True llm=False rank=1 pick=12 gap=False 1204ms [hot:vector] | 变更日志怎么回看和介入，approve reject 语义
- fused=False llm=False rank=2 pick=15 gap=False 1290ms [hot:vector] | 蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据
- fused=False llm=True rank=3 pick=3 gap=False 988ms [hot:vector] | 技能生命周期怎么做活性管理的
- fused=False llm=False rank=11 pick=8 gap=False 1178ms [hot:vector] | 对话树和召回是什么关系，命中怎么并行
- fused=True llm=False rank=1 pick=9 gap=False 1233ms [hot:vector] | 元认知复盘每几轮做一次，和策略权重什么关系
- fused=True llm=False rank=1 pick=9 gap=False 1269ms [hot:vector] | 编码类请求怎么识别，施工信号有哪些
- fused=True llm=True rank=1 pick=1 gap=False 1646ms [hot:vector] | 混合式通用 agent 的定位是什么，和纯 RAG 有什么区别
- fused=False llm=False rank=3 pick=10 gap=False 1252ms [hot:vector] | 权限门怎么拦截链式 shell 和越权写入
- fused=False llm=False rank=2 pick=1 gap=False 1372ms [hot:vector] | OS 工具集有哪些，run_session 是干嘛的
- fused=False llm=True rank=2 pick=3 gap=False 1331ms [hot:vector] | function calling 端到端实测做了什么
- fused=False llm=False rank=None pick=7 gap=True 1146ms [hot:vector] | 执行迹和变更日志两个白盒视图各展示什么
- fused=False llm=False rank=14 pick=13 gap=False 1223ms [hot:vector] | 跟 OpenClaw Hermes 对标后我们还差什么
- fused=True llm=False rank=1 pick=14 gap=False 1230ms [hot:vector] | 定时自动化 automation 为什么是孤儿，怎么接
- fused=True llm=False rank=1 pick=11 gap=False 1196ms [hot:vector] | replanner 自动换方案为什么没做，MC 全场景缺什么
- fused=True llm=True rank=1 pick=1 gap=False 1286ms [hot:vector] | 文档漂移检测怎么融入召回评测
- fused=False llm=True rank=2 pick=3 gap=False 1279ms [hot:vector] | 评测看护为什么要有基线和趋势，怎么复跑
- fused=False llm=False rank=2 pick=10 gap=False 1334ms [hot:vector] | 第一版发布前还差哪些，前端绑定和量化测试优先级
- fused=True llm=True rank=1 pick=5 gap=False 1206ms [hot:vector] | 内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用
- fused=False llm=False rank=None pick=9 gap=True 1189ms [hot:vector] | 隐式关系候选怎么生成和核验，precision 多少
- fused=True llm=True rank=1 pick=1 gap=False 1137ms [hot:vector] | 图导航 API 有哪些，path 和 callers 怎么用
- fused=True llm=False rank=1 pick=13 gap=False 1305ms [hot:vector] | Rust 重构召回核心的验收门槛是什么
- fused=True llm=True rank=1 pick=4 gap=False 1042ms [hot:vector] | 符号注入怎么压缩上下文，Mermaid 图怎么生成
- fused=True llm=True rank=1 pick=1 gap=False 1328ms [hot:vector] | v2 执行层四壳是哪四层，监控怎么介入
- fused=False llm=False rank=20 pick=7 gap=False 1498ms [hot:vector] | 存储分层 H/W/C/A 怎么升降，阈值多少
- fused=True llm=True rank=1 pick=1 gap=False 1846ms [hot:vector] | 前端 B5 UI 测试怎么跑，Playwright 基建在哪
- fused=False llm=False rank=None pick=4 gap=True 1588ms [hot:vector] | PCR zone 和意图分类怎么映射到召回策略
- fused=False llm=False rank=4 pick=1 gap=False 1133ms [hot:vector] | 设计哲学里偏差为什么是养分，归因回流到哪层
- fused=True llm=False rank=1 pick=6 gap=False 1331ms [hot:vector] | 子图扩展的 DAG 分层和同步剪枝怎么实现