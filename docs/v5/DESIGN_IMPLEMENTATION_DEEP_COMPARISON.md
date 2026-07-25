# DialogMesh v6 — 设计×实现 深度对照 (从40+篇设计文档提取)

> 2026-07-24 · 读完 ARCHITECTURE.md, architecture/ARCHITECTURE.md, HYBRID_ARCHITECTURE, 关联链/三范式/信息论压缩 等核心设计

---

## 表一：设计全貌 (42 核心设计点)

### A. 架构模式

| 设计要点 | 来源 | 描述 |
|----------|------|------|
| 热路径直连 | DESIGN_HYBRID_ARCHITECTURE.md | 8链直连 <10ms, 不经过EventBus |
| 冷路径EventSourcing | DESIGN_HYBRID_ARCHITECTURE.md | Meta+Association 两条链走EventBus, 避免广播风暴 |
| LLM是协调者 | agent_native.py docstring | 不是"算法LLM兜底", 是"算法前置滤波, LLM决策" |
| 事件溯源 | DESIGN_EVENT_SOURCING_CQRS.md | EventLog+Snapshot+Replay, SHA256链 |
| 网状非线形 | BUSINESS_CHAIN_06_ASSOCIATION.md | 10链并行消费EventBus, 非L1→L2→L3 |

### B. 核心公式/范式

| 设计要点 | 来源 | 公式 |
|----------|------|------|
| 信息价值 | DESIGN_INFO_THEORETIC_COMPRESSION.md | I(x) = -log₂ P(x), 罕见事件→高价值 |
| 温度×距离正交 | DESIGN_THREE_PARADIGM_LLM_CONTEXT.md | Temp(Hot/Cold) ⟂ Dist(Near/Far) ⟂ Value(Rare/Common) |
| 压缩分治 | DESIGN_L5_LONG_TERM_MEMORY.md | 高频→压缩成规则, 低频高价值→RAG |
| 三范式注入 | DESIGN_THREE_PARADIGM_LLM_CONTEXT.md | 模式C推荐: 自然语言三元组标注 |

### C. 关联链 5层漏斗

| 层 | 输入 | 处理 | 输出 | 用户可见 |
|----|------|------|------|----------|
| L1 句法 | 原始文本 | Stanza+SVO | 三元组 | ❌ |
| L1.5 补全 | 三元组 | 快(画像+上文)+慢(轻量LLM) | 补全语义 | ✅ |
| L2 语义 | 补全语义 | 类型兼容+KG映射 | 实体关系 | ✅ |
| L2.5 信念 | 实体关系 | 跨轮贝叶斯后验 | 锁定意图 | ❌ |
| L3 语用 | 锁定意图 | 主题锁定+行为标签 | 意图链 | 桥接 |
| L4 时序 | 意图链 | 马尔可夫+JS漂移 | 时序预测 | 桥接 |
| L5 因果 | 证据链 | 伪因果→实因果晋升 | 因果链 | ✅ |

### D. 对话树

| 设计要点 | 来源 |
|----------|------|
| 树投影(推理)+图关联(记忆) | architecture/ARCHITECTURE.md |
| 局部热区: 当前+2祖先+1后代 | architecture/ARCHITECTURE.md |
| MAX_DEPTH=6, 超深触发压缩 | architecture/ARCHITECTURE.md |
| 认知画像继承(子继父,可覆盖) | architecture/ARCHITECTURE.md |
| BM25+jieba快匹配+LLM双轨 | topic_quick_match.py |

### E. PCR 路由

| 设计要点 | 来源 |
|----------|------|
| 期望识别3级级联: 规则→历史→LLM | architecture/ARCHITECTURE.md |
| 3D坐标路由(X/Y/Z) | BUSINESS_CHAIN_00_PCR.md |
| X轴: nomic(S,O)cosine×0.7 + IDF×0.3 | PCR V2 |
| 模型规模感知: <7B/7-13B/>70B | PCR V2 |

### F. 元认知

| 设计要点 | 来源 |
|----------|------|
| 消费8条链, 产出review→修正/降级 | DESIGN_HYBRID_ARCHITECTURE.md |
| 7条默认规则+冷却期 | metacognitive_trigger.py |
| 审查优先级+排程+回顾+自审 | metacognition.py |

### G. 联邦索引

| 设计要点 | 来源 |
|----------|------|
| 6源并行: RAG+Discourse+Behavior+Association+Engineering+Meta | federated_index.py |
| 温度LRU排序 | federated_index.py |
| 嵌入式聚类+LLM验证 | llm_relation_extractor.py |

---

## 表二：实现对照 (39 实现 + 3 缺口)

### ✅ 设计↔实现一致

| 设计 | 实现 | 状态 |
|------|------|------|
| PCR 3D路由 | pcr_router_v2.py | ✅ |
| Sentence拆分 | discourse_block_tree/segmenter.py | ✅ |
| L4 时序预测 | association/l4_temporal.py + l4_collaborative.py | ✅ |
| 行为自适应 | behavior/models.py + llm_collaborative.py | ✅ |
| 多意图拆分(LLM-first) | intent/multi_intent_splitter.py | ✅ |
| 对话树 | compiler/discourse_block_tree.py | ✅ |
| BM25+jieba | compiler/topic_quick_match.py | ✅ |
| 元认知触发器 | observability/metacognitive_trigger.py | ✅ |
| 持久化(SHA256+SQLite) | persistence/broker.py + lsm_store.py | ✅ |
| Rust持久化 | persistence_rs/src/ | ✅ |
| V4认知桥(6桥接) | v4/cognitive_bridge.py | ✅ |
| V4认知模块(13/13) | v4/cognitive/*.py | ✅ |
| 联邦索引(Python) | memory/federated_index.py | ✅ |
| 联邦索引(Rust) | persistence_rs/src/federated_index.rs | ✅ |
| 压缩路由器 | memory/compression_router.py | ✅ |
| 策略联邦 | memory/strategy_federation.py | ✅ |
| XML记忆卡 | memory/xml_cards.py | ✅ |
| RAG+图并行 | memory/ragraph.py | ✅ |
| L2 LLM-native关系 | compiler/llm_relation_extractor.py | ✅ |
| 三范式上下文 | compiler/three_paradigm_context.py | ✅ |
| 后验修正 | compiler/posterior_corrector.py | ✅ |
| 评估框架 | tests/eval_memory.py | ✅ |
| orchestator | orchestrator/agent_native.py | ✅ |

### ⚠️ 设计有, 实现简化为LLM-first

| 设计 | 当前实现 | 差距 |
|------|----------|------|
| 21条regex规则+优先级 | MultiIntentSplitter(LLM-first) | 规则层被跳过 — 设计是"规则95%, LLM5%", 实现是"LLM100%" |
| 3级级联(规则→历史→LLM) | PCR直接LLM | 历史缓存/规则fallback未实现 |
| 歧义检测6类(架构设计) | 无歧义检测 | 设计存在, 代码为零 |
| 任务图DAG+拓扑排序 | 无 | 蓝图系统存在于设计,未实现 |

### ❌ 设计存在, 实现为零

| 设计 | 来源 | 缺口描述 |
|------|------|----------|
| Topic Tree深度防御 | architecture/ARCHITECTURE.md | MAX_DEPTH=6压缩, 树投影+图关联未实现 |
| 认知画像继承(子继父) | architecture/ARCHITECTURE.md | discourse_block_tree无继承机制 |
| 热/冷路径分叉 | DESIGN_HYBRID_ARCHITECTURE.md | agent_native是线性管线, 无EventBus分叉 |
| 用户可修改L1.5/L2/L5 | BUSINESS_CHAIN_06_ASSOCIATION.md | 所有层对用户不可见不可改 |
| WebSocket 事件注册表 | architecture/ARCHITECTURE.md | Layer 3 前端协议层未实现 |
| SessionManager(Redis) | architecture/ARCHITECTURE.md | 当前仅SQLite, 无Redis支持 |
| Bayesian GP阈值自适应 | architecture/ARCHITECTURE.md | 设计存在, 未实现 |
| ContextManager温度排序 | BUSINESS_CHAIN_02_CONTEXT.md | 文件不存在 |

---

## 表三：根本矛盾 — 设计哲学冲突

```
设计文档 (2026-07-19):
  "规则优先, LLM兜底"
  "95%请求走规则路径(<5ms)"
  "21条规则分类器(regex+优先级+冲突检测)"
  "确定性第一, LLM仅用于选择不发明"

当前实现 (2026-07-24):
  LLM-first: MultiIntent是LLM调用, PCR是LLM分类, 关系提取是LLM开放命名
  零regex规则, 零硬编码分类器
  
这是根本性冲突 — 不是"少实现了一个模块", 是两条完全不同的路径。
需要决策: 继续LLM-first(符合前沿), 还是回到规则优先(设计原文)?
```
