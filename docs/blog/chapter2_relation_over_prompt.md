'# Chapter 2：关系不是提示词能给的 —— v4 的认知系统

> 提示词可以告诉 Agent 一条规则。
> 但它无法告诉 Agent：这条规则和谁相关、从哪来、什么时候会变。
>
> 关系是一种比文本更难传递、却更稀缺的上下文资源。
> v4 把关系从"设计理念"变成了"可运行的系统"。

---

## 一、一个让 Agent 尽职但不尽责的瞬间

你在做一个网关项目。模块链路很简单：

`
Gateway -> Auth -> Logger
`

每个模块都有监控埋点。你让 Agent 在 Auth 和 Logger 之间加一个新模块 RateLimiter。
Agent 写好了代码，测试通过，提交了。

一周后你发现：Auth 和 Logger 都有监控，但 RateLimiter 没有。

Agent 完美执行了你的指令。它不知道的不是 Prometheus 怎么用。
它不知道的是：

`
在这个项目里，
  Auth 有监控
  Logger 有监控
-> 新模块也该有监控
`

这条约束不在 Auth 的代码里，不在 Logger 的文档里。它在 Auth 和 Logger 之间那条看不见的关系里。

**Agent 没有被要求做错事。它只是没有被告诉：这个世界上有哪些关系。**

## 二、提示词的边界

你当然可以把这条约束写进 system prompt：

`
项目规则：所有模块都需要添加监控埋点。
`

能解决吗？能，这一次。

下一次加新模块，你又要重复。下一次换了会话，约束丢了。下一次换了一个表达方式，
Agent 可能识别不出来这是同一条规则。

提示词适合描述的是：所有模块都需要监控。一条全局规则。

但当系统复杂到 100 个模块时：A 依赖 B，B 继承 C 的规范，D 是例外，E 需要特殊处理。
这些规则被平铺在 system prompt 里，LLM 需要在每次推理时重新从文本中读出关系。

**规则可以写。关系需要长出来。**

DialogMesh v4 的答案是：不是一个更好的 system prompt。而是一个完整的认知系统。

## 三、v4 的认知流水线：从事件到能力

v4 的核心是一条五阶段的知识精炼链：

`
Event  ->  Observation  ->  Hypothesis  ->  Knowledge  ->  Skill
(事实)     (候选解释)       (竞争中的信念)    (冻结共识)     (可复用能力)
`

### 3.1 Observation Compiler：把事件投影到多个认知域

一个用户事件不是只有一种理解方式。拖一个 RateLimiter 到 Auth 前面：

`
Event: drag(RateLimiter, position=before Auth)
  |
  +--> Behavior Observation:   "用户在进行模块调整"
  +--> Engineering Observation:"Pipeline 顺序改变"
  +--> Memory Observation:     "用户修改了工程结构"
  +--> Dialogue Observation:   "用户请求重排模块"
  +--> User Observation:       "用户习惯手动调顺序"
`

这些观察同时成立，不是互斥的。v4 用 Observation Compiler 把一个事件投影到 5 个域。

`python
from core.agent.v4.observation_compiler.projector import Projector

projector = Projector()
domains = projector.project("ui.drag")  
# -> ["engineering", "behavior", "memory"]
`

### 3.2 Hypothesis Engine：让解释竞争

Observation 提出"可能是什么"。Hypothesis Engine 决定"最可能是什么"。

不是用一个 confidence 数字。是一个 7 维信念状态：

`python
{
    "support": 12,      # 有多少证据支持
    "conflict": 3,      # 有多少证据反对
    "stability": 0.81,  # 信念是否稳定
    "coverage": 0.72,   # 证据覆盖程度
    "recency": 1.0,     # 最近是否有新证据
    "novelty": 0.12,    # 是否新颖
    "entropy": 0.05,    # 不确定性
}
`

当 support > 8 且 conflict < 3 且 stability > 0.7 时，Hypothesis 冻结为 Knowledge。
这不是阈值调参。这是一个假说在证据竞争中自然胜出的过程。

### 3.3 Knowledge：冻结共识

Knowledge 是 Hypothesis 的终点。一旦冻结，它就不再参与竞争——它变成了"已知事实"。

### 3.4 Skill Layer：从知识到能力

当同一个 Pattern 出现 5 次以上且成功率 >90%：
"加中间件模块后，上下游的监控模式需要继承给新模块"

Knowledge 蒸馏为 Skill。Skill 不是 Prompt，而是一个可执行的能力蓝图：

`python
Skill {
    trigger: "add_middleware_module",
    context: ["engineering_chain", "monitoring_pattern"],
    constraints: ["inherit_upstream", "inherit_downstream"],
    procedure: ActionGraph([...]),
    verification: ["check_metrics", "check_health"],
}
`

## 四、Semantic World Model：把代码世界变成可推理的图

v4 不是"代码索引"。是把整个项目建模为一个 Structural World Graph：

### 4.1 Reference Unit：只有能被引用的才是节点

不是所有代码都是节点。Class、Function、Module 是节点。if(){}、局部变量、注释 不是。
标准只有一条：**能被外部引用。**

### 4.2 多类型边：不是一条 depends_on

9 种边类型，每种有不同的语义和传播权重：

`
imports (0.30)   | calls (0.25)       | co_changes (0.25)
overrides (0.20) | implements (0.20)  | constrains (0.20)
references (0.15)| tests (0.10)       | generates (0.15)
`

### 4.3 社区检测替代目录结构

utils/ 下面有 logger.py 和 cache.py。它们同目录。
但社区检测发现 logger 调用了 gateway 的日志模块，cache 独立使用——它们不属于同一个社区。
**真实的模块边界来自图，不来自文件系统。**

`python
from core.agent.v4.world.community import CommunityDetector

detector = CommunityDetector(resolution=1.0)
communities = detector.detect(world_graph)
# community_0: [gateway, auth, logger, metrics]
# community_1: [cache, redis, serializer]
`

### 4.4 分层重要性：不是谁被调用最多

Logger 被调用次数最多，但它不决定系统拓扑。真正重要的是**信息流必经路径**。

v4 用三层自动路由：
- <5000 节点：精确 Betweenness Centrality
- 5000-20000 节点：K-Sampling 近似（95% 质量，10x 速度）
- >20000 节点：社区切块（85% 质量，20x 速度）

系统自适应图规模，不需要手动切换算法。

## 五、Context Engineering：不是 Prompt，是子图编译

v4 的 Context Assembler 不是给 LLM 一段文本。是给 LLM 一个跨域的局部世界：

`python
from core.agent.v4.context.assembler import ContextAssembler
from core.agent.v4.context.source import KnowledgeSource, WorldSource, SkillSource

sources = [
    KnowledgeSource(knowledge_nodes),
    WorldSource(world_graph),
    SkillSource(skill_pool),
]

assembler = ContextAssembler(sources)
ctx = assembler.assemble("add monitoring to gateway", top_k=10)

for item in ctx.top_k(5):
    print(f"[{item.source}] score={item.relevance:.2f}")
`

**关键设计：每个知识源独立检索，组装器统一排序。**

加一个新知识源（比如 RAG、Milvus、记忆）不需要改组装器。每个 Source 实现 etrieve() 即可。

这和提示词的本质区别：不是把所有规则塞进一个 prompt，而是让 LLM 的上下文空间被最适合当前意图的知识填充。

## 六、Cognitive Runtime：谁在什么时候运行

30+ 个认知模块不能互相直接调用。v4 的 Runtime 是一台调度器：

`
用户输入
  |
  v
Async Path (<5s):    Observation -> Behavior/Engineering Analyzer
  |
  v  (checkpoint: 50 events or 30 min)
Slow Path (minutes): ObservationPool -> Hypothesis Engine -> Knowledge
  |
  v  (threshold: 5 patterns, 90% success)
Deep Path (hours):   Pattern -> Skill Distiller
`

Runtime 不做推理。它决定谁在什么时候推理。每个模块通过适配器接入，不耦合：

`python
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

engine = CognitiveRuntimeEngine()
engine.start()
engine.on_event(event)          # Async Path
engine.trigger_checkpoint()     # Slow Path
`

## 七、持久化与向量：不依赖外部服务

v4 默认用 SQLite 存储所有认知数据（Observation、Hypothesis、Knowledge、Skill），WAL 模式，支持快照。

向量检索内置 numpy 余弦相似度，不需要 Milvus。
达到 10 万条向量时，TieredVectorStore 自动切换到 Milvus——冷启动 + 自然预热，不需要数据迁移。

`python
from core.agent.v4.persistence.vector_store import SQLiteVectorStore

store = SQLiteVectorStore("data/vectors.db")
store.open()
store.put("k1", embedding_vector)

results = store.search(query_vector, top_k=5)
# -> [("k1", 0.87), ("k3", 0.72), ...]
`

## 八、关系的白盒化：这不是一个黑盒系统

v4 的一个核心设计选择：**relations are first-class, auditable objects.**

你可以检查任意一个模块缺少哪条边。你可以看一个 Hypothesis 是怎么一步步被证据推上去的。
你可以追踪一个 Skill 是从哪些 Knowledge 蒸馏出来的。

`python
# 检查模块缺少哪些约束
from core.agent.v4.world.schema import StructuralWorldGraph

graph: StructuralWorldGraph
backbone = graph.backbone  # 每个节点的骨干分数
communities = graph.communities  # 社区边界
edges = graph.edges  # 所有关系边
`

关系不是隐式推导的。关系是存储在图中、可查询、可修改、可泛化的。

## 九、从"还没实现"到"304 个测试，0 失败"

这篇文章的第一版结尾是："坦诚说，这是设计，代码还没写完。"

现在是 2026 年 7 月 13 日。v4 已经实现：

`
core/agent/v4/
    runtime/               认知调度引擎
    world/                 语义世界模型
    observation_compiler/  观测编译器 (5 域)
    hypothesis_engine/     假设引擎 (7 维信念状态)
    skill_layer/           技能层 (蒸馏 + 评估)
    context/               上下文工程 (Source -> Rank -> Assemble)
    tiered/               多级管道 (快慢系统)
    persistence/          统一持久化 (SQLite + 快照 + 向量)
    cli/                   Runtime DAG Builder
    cognitive_scheduler/   任务调度

304 个测试，0 失败。
`

## 十、这不是 Prompt Engineering。这是 Context Engineering。

如果你只是想找一个更好的 system prompt，v3 就够。

如果你想构建一个系统：事件进来，知识沉淀，能力增长，关系可追溯——
你需要的不只是一个更好的提示词，而是一个完整的认知流水线。

这就是 v4。

---

_下一篇：Chapter 3 — 从 Event 到 Skill：v4 的知识精炼全过程_