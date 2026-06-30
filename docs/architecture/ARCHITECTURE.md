# MemoryGraph Agent 架构设计

> 完整架构说明、数据流、状态机和模块交互。

---

## 目录

1. [设计原则](#设计原则)
2. [分层架构](#分层架构)
3. [核心数据流](#核心数据流)
4. [状态机](#状态机)
5. [模块交互图](#模块交互图)
6. [数据模型](#数据模型)
7. [Topic Tree（对话树）](#topic-tree对话树)
8. [扩展点](#扩展点)

---

## 设计原则

1. **规则优先，LLM 兜底**：95% 请求走规则路径（<5ms），LLM 仅在规则未命中或冷启动时触发（<10%）
2. **确定性第一**：所有规则可预测、可调试、可测试；LLM 仅用于"选择"而非"发明"
3. **上下文显式传递**：对话历史、实体状态、澄清进度全部显式传递，不依赖隐式全局状态
4. **延迟预算**：每轮总延迟 < 200ms（规则路径 < 5ms，LLM 路径 < 200ms）
5. **渐进式智能**：冷启动用规则，随着交互自适应提升阈值精度（Bayesian GP）

---

## 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 前端协议层（可选）                                      │
│  ─────────────────────────────────────────────────────────────  │
│  • WebSocket 事件注册表（Schema + 版本管理）                       │
│  • ClarificationPanel UI Schema 渲染协议                         │
│  • TaskGraph 可视化（SVG / Canvas）                              │
│  • Multimodal 预处理（图片 OCR / 音频 ASR / 文档解析）             │
└─────────────────────────────────────────────────────────────────┘
                              ↑↓ WS / HTTP
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: 服务层（可选）                                          │
│  ─────────────────────────────────────────────────────────────  │
│  • FastAPI REST + WebSocket 路由                                   │
│  • AgentService（同步）/ AsyncAgentService（异步）                 │
│  • SessionManager（内存 / SQLite / Redis）                         │
│  • RateLimiter（令牌桶 + 优先队列）                                │
│  • RequestQueue（异步请求队列）                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↑↓ 内部调用
┌─────────────────────────────────────────────────────────────────┐
│  Topic Tree（对话树 / 记忆层）                                    │
│  ─────────────────────────────────────────────────────────────  │
│  • 话题路由：continue / fork / attach / new（基于 cohesion_score） │
│  • 双结构：树投影（推理层） + 图关联（记忆层）                     │
│  • 局部热区：当前节点 + 前 2 层祖先 + 后 1 层后代（内存优化）     │
│  • 深度防御：MAX_DEPTH=6，超过触发路径压缩（摘要节点）            │
│  • 实体索引：跨话题实体关联（ENTITY_REFERENCE / SIMILARITY 边）  │
│  • 认知画像继承：子节点继承父节点画像，可本地覆盖                  │
└─────────────────────────────────────────────────────────────────┘
                              ↑↓ 记忆读写
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: 意图解析器（Intent Parser）                            │
│  ─────────────────────────────────────────────────────────────  │
│  • 21 条规则分类器（regex + 优先级 + 冲突检测）                    │
│  • 实体提取（类型化、置信度、位置）                                │
│  • 多意图拆分（"and then" / 分号 / 中文连接词）                    │
│  • 歧义检测（6 类歧义）                                           │
│  • 引用解析（跨轮实体继承："把它改成 100" → 继承上一轮的地址）     │
│  • LLM Fallback（规则未命中时，带上下文历史调用 LLM）              │
│  • 蓝图系统（固定执行序列，LLM 只选择不发明）                       │
│  • 任务图 DAG（拓扑排序 + 依赖边 + 回退链）                        │
│  • 意图规则注册表（单例 + fuzz 测试 + 域隔离）                     │
└─────────────────────────────────────────────────────────────────┘
                              ↑↓ 控制信号（ParseResult）
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: 前置认知路由器（PCR）                                   │
│  ─────────────────────────────────────────────────────────────  │
│  • 期望识别（3 级级联：规则 → 历史 → LLM fallback）                 │
│  • 噪声估计（4 维规则 + 历史衰减）                                │
│  • 复杂度估计（YAML 配置 + 启发式规则）                            │
│  • 认知画像（EMA 滑动窗口 + Jaccard 相似度）                       │
│  • 冷启动 expertise_probe（5 维评分 + 可配置词表）                  │
│  • 自适应阈值（Bayesian GP + 8-D MLP，Sherman-Morrison 增量）      │
│  • 版本化数据契约（PCRInput_v1 / PCROutput_v1）                    │
│  • 遥测收集（延迟 / 成功率 / 噪声分布）                             │
│  • 生命周期管理（热插拔 + 线程安全）                                │
└─────────────────────────────────────────────────────────────────┘
                              ↑↓ 用户输入
```

---

## 核心数据流

### 单轮对话完整数据流

```
User Input（如"把它改成 100"）
  │
  ▼
┌────────────────────────────────────────────────────────────┐
│ 1. PCR.evaluate(PCRInput_v1)                                │
│    • 输入：query + session_history + turn_index + session_id  │
│    • 输出：PCROutput_v1（expectation, noise, complexity,       │
│            cognitive_profile, execution_mode, prompt_style）  │
│    • 延迟：< 5ms（规则路径）                                   │
└────────────────────────────────────────────────────────────┘
  │
  ▼ PCROutput_v1
┌────────────────────────────────────────────────────────────┐
│ 2. IntentContext.from_pcr_output() → IntentContext          │
│    • 映射：expectation → UserExpectation enum                │
│    • 动态阈值：auto_resolve_threshold, max_ambiguities_before_ask│
│    • 执行模式：CONSERVATIVE / BALANCED / AGGRESSIVE            │
└────────────────────────────────────────────────────────────┘
  │
  ▼ IntentContext
┌────────────────────────────────────────────────────────────┐
│ 3. IntentParser.parse(query, intent_context, parse_context) │
│    • 输入：用户输入 + PCR 控制信号 + 会话级解析上下文（持久化）  │
│    • 预处理：词汇调谐（synonym_expansion, topic_inheritance）  │
│    • 引用解析："它" → 继承上一轮实体（跨轮状态传递）             │
│    • 实体提取：类型化、置信度、位置                              │
│    • 意图分类：21 条规则匹配（优先级排序）                        │
│    • 冲突检测：规则间 fuzz 重叠测试                              │
│    • 多意图拆分：复合输入拆分为多个子意图                         │
│    • 歧义检测：6 类歧义（缺失实体、模糊实体、冲突实体等）         │
│    • 歧义消解：自动消解（auto_resolvable）或 生成澄清 FSM         │
│    • 输出：ParseResult（Intent + TaskGraph + Clarifications）    │
│    • 延迟：< 5ms（规则路径），< 200ms（LLM fallback）            │
└────────────────────────────────────────────────────────────┘
  │
  ▼ ParseResult
┌────────────────────────────────────────────────────────────┐
│ 4. ExpertiseProbe.probe()                                    │
│    • 5 维评分：terminology_density, parameter_precision,       │
│              query_complexity, language_style, historical       │
│    • 如果 raw_score > threshold（默认 0.72）→ LLM 介入        │
│    • 如果 raw_score > 0.85 → 专家模式 bypass 澄清             │
│    • 阀门：max_clarification_rounds=3 触发降级                   │
└────────────────────────────────────────────────────────────┘
  │
  ▼ ExpertiseScore
┌────────────────────────────────────────────────────────────┐
│ 5. AdaptiveThreshold.suggest()                               │
│    • 8 维特征：rule_confidence, history_consistency,            │
│              query_length_norm, terminology_density, noise,    │
│              clarification_rounds, time_decay, user_feedback    │
│    • MLP 变换：8 → 16 → 8（固定随机投影 + 岭回归输出层）         │
│    • GP 预测：RBF kernel，均值 + 方差                           │
│    • Thompson Sampling：均值 + 1.96×标准差 作为探索阈值           │
│    • 输出：ThresholdSuggestion（threshold, mean, variance）    │
└────────────────────────────────────────────────────────────┘
  │
  ▼ ThresholdSuggestion
┌────────────────────────────────────────────────────────────┐
│ 6. LLM.generate()                                            │
│    • 输入：标准 OpenAI messages 格式（system + history + query） │
│    • 系统提示：persona + 约束（简洁、中文、无 Markdown）          │
│    • 历史：最近 N 轮（默认 10 轮）user/assistant 交替             │
│    • 输出：自然语言回复                                         │
│    • 延迟：~50-200ms（取决于模型和硬件）                         │
└────────────────────────────────────────────────────────────┘
  │
  ▼ GenerateResult
┌────────────────────────────────────────────────────────────┐
│ 7. TopicTree.route()                                         │
│    • 输入：query + extracted_entities + cohesion_score         │
│    • 路由决策：                                                │
│      - cohesion_score > 0.6 → continue（继续当前话题）       │
│      - 0.3 < cohesion_score < 0.6 → attach（附着到相似话题）  │
│      - cohesion_score < 0.3 + 历史话题存在 → fork（分叉新话题）│
│      - 无历史话题 → new（创建新话题）                          │
│    • 更新：当前节点实体、轮次、认知画像                        │
│    • 维护热区：当前节点 + 前 2 层祖先 + 后 1 层后代            │
│    • 深度检查：超过 6 层触发路径压缩（摘要节点）               │
│    • 延迟：< 5ms（纯规则 + 实体索引）                         │
└────────────────────────────────────────────────────────────┘
  │
  ▼ RoutingDecision
┌────────────────────────────────────────────────────────────┐
│ 8. 记录历史 + 更新状态                                          │
│    • HistoryEntry(role="user", content=query)                  │
│    • HistoryEntry(role="assistant", content=reply)             │
│    • ParseContext 更新（resolved_entities, pending_clarifications）│
│    • AdaptiveThreshold.update()（下一轮反馈信号）                │
│    • ConversationLog 追加（用于审计和调试）                       │
└────────────────────────────────────────────────────────────┘
```

### 上下文传递机制

**跨轮状态传递（关键设计）**：

```python
# 每轮保留的状态（ParseContext 持久化）
parse_context = ParseContext(session_id="interactive")

# 第 1 轮：用户说"扫描地址 0x1000"
#   → 提取实体：Entity(MEMORY_ADDRESS, 0x1000, confidence=0.95)
#   → ParseContext.resolved_entities = {"memory_address": 0x1000}

# 第 2 轮：用户说"把它改成 100"
#   → 引用解析："它" → 查找 ParseContext.resolved_entities
#   → 继承实体：Entity(MEMORY_ADDRESS, 0x1000, confidence=0.8, inherited=True)
#   → 新实体：Entity(NUMERIC_VALUE, 100, confidence=0.95)
```

**对话历史传递（LLM 上下文）**：

```python
messages = [
    {"role": "system", "content": "你是 MemoryGraph Agent..."},
    # 历史对话（标准 OpenAI 格式）
    {"role": "user", "content": "扫描地址 0x1000"},
    {"role": "assistant", "content": "已扫描地址 0x1000，找到 3 个结果..."},
    {"role": "user", "content": "把它改成 100"},  # 当前输入
]
```

---

## 状态机

### Clarification FSM（多轮澄清）

```
                    ┌─────────────┐
                    │    IDLE     │ ← 初始状态
                    └──────┬──────┘
                           │ 歧义检测 > 0
                           ▼
                    ┌─────────────┐
                    │  CLARIFYING │ ← 显示澄清面板
                    └──────┬──────┘
                           │ 用户回复
                           ▼
              ┌────────────────────────┐
              │   RESOLVING / MERGING  │ ← 合并用户回复到意图
              └───────────┬────────────┘
                          │
              ┌───────────┴───────────┐
              │ 成功解析               │ 仍有歧义
              ▼                        ▼
       ┌─────────────┐         ┌─────────────┐
       │   RESOLVED  │         │  CLARIFYING │ ← 再次澄清（最多 3 轮）
       └──────┬──────┘         └─────────────┘
              │ 超过 max_clarification_rounds
              ▼
       ┌─────────────┐
       │  DEGRADED   │ ← 降级到保守规则模式
       └─────────────┘
              │
              ▼
       ┌─────────────┐
       │   FAILED    │ ← 最终失败，提示用户重新描述
       └─────────────┘
```

### PCR 执行模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **FAST** | 输入 < 20 字符，noise < 0.3 | 纯规则路径，跳过 LLM，延迟 < 5ms |
| **HYBRID** | 输入 < 100 字符，noise < 0.5 | 规则 + 轻量 LLM（intent 分类），延迟 < 50ms |
| **FULL** | 输入 > 100 字符，或 noise > 0.5 | 完整 LLM 路径，延迟 < 200ms |
| **CONSERVATIVE** | noise > 0.7，或 stability < 0.3 | 强制澄清，LLM 仅用于歧义消解 |
| **DEGRADED** | 超过 max_clarification_rounds | 纯规则，拒绝 LLM，避免 token 浪费 |

---

## 模块交互图

```
                          User Input
                              │
                              ▼
                    ┌─────────────────┐
                    │   PCR (Layer 0) │
                    │  • Expectation   │
                    │  • Noise         │
                    │  • Complexity   │
                    │  • Cognitive     │
                    └────────┬────────┘
                             │ PCROutput_v1
                             ▼
                    ┌─────────────────┐
                    │ IntentContext   │
                    │  • threshold    │
                    │  • mode         │
                    │  • style        │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 21 Rules     │    │  Expertise   │    │  Adaptive    │
│ Classifier   │    │   Probe      │    │  Threshold   │
│  (determin)  │    │  (5-dim)     │    │  (GP+MLP)    │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                    │
       │                   │ ExpertiseScore     │ ThresholdSuggestion
       │                   │                    │
       └───────────────────┼────────────────────┘
                           │
                           ▼
                    ┌─────────────────┐
                    │ IntentParser    │
                    │ (Layer 1)       │
                    │ • Entity Extract │
                    │ • Multi-intent   │
                    │ • Ambiguity      │
                    │ • Reference      │
                    │ • TaskGraph      │
                    └────────┬────────┘
                             │ ParseResult
                             ▼
                    ┌─────────────────┐
                    │   LLM Provider  │
                    │  (OpenAI/Local) │
                    │  • generate()   │
                    │  • messages[]   │
                    │  • history      │
                    └────────┬────────┘
                             │ GenerateResult
                             ▼
                    ┌─────────────────┐
                    │  HistoryEntry   │
                    │  ParseContext   │
                    │  (persist)      │
                    └─────────────────┘
                             │
                             ▼
                          Reply
```

---

## 数据模型

### 核心实体关系

```
PCRInput_v1 ──→ PCR.evaluate() ──→ PCROutput_v1
    │                                    │
    │ session_history                    │ expectation
    │ query                              │ noise_level
    │ turn_index                         │ complexity_level
    │ session_id                         │ cognitive_profile
                                       │ execution_mode
                                       │ prompt_style
                                              │
                                              ▼
                                    IntentContext.from_pcr_output()
                                              │
                                              ▼
User Input ──→ IntentParser.parse() ──→ ParseResult
    │              │                        │
    │              │ intent_context         │ intent: Intent
    │              │ parse_context          │ task_graph: TaskGraph
    │              │                        │ is_actionable: bool
    │              │                        │ clarification_message: str
    │              │                        │
    │              │                        ▼
    │              │              Intent ──→ TaskGraph
    │              │                │          │
    │              │                │ entities │ nodes: TaskNode[]
    │              │                │ ambiguities│ edges: TaskEdge[]
    │              │                │ sub_intents│ topological_order()
    │              │                │            │ get_ready_nodes()
    │              │                │            │ get_fallback_chain()
    │              │                │            │
    │              │                │            ▼
    │              │                │      TaskNode ──→ TaskStatus
    │              │                │        │           │ PENDING
    │              │                │        │           │ RUNNING
    │              │                │        │           │ SUCCESS
    │              │                │        │           │ FAILED
    │              │                │        │           │ BLOCKED
    │              │                │        │           │ CANCELLED
    │              │                │        │           │ SKIPPED
    │              │                │        │           │ NEEDS_CLARIFICATION
    │              │                │        │
    │              │                │        ▼
    │              │                │   Entity ──→ EntityType
    │              │                │     │           │ MEMORY_ADDRESS
    │              │                │     │           │ NUMERIC_VALUE
    │              │                │     │           │ STRING_VALUE
    │              │                │     │           │ ... (20+ types)
    │              │                │     │
    │              │                │     ▼
    │              │                │   Ambiguity ──→ AmbiguityType
    │              │                │                  │ MISSING_ENTITY
    │              │                │                  │ AMBIGUOUS_ENTITY
    │              │                │                  │ CONFLICTING_ENTITIES
    │              │                │                  │ VAGUE_SCOPE
    │              │                │                  │ UNSUPPORTED_OPERATION
    │              │                │                  │ MULTIPLE_INTENTS
```

---

## Topic Tree（对话树）

> 跨轮对话的记忆管理层。负责话题的路由、分叉、回溯和实体关联。独立于 Layer 0-3，作为**记忆层**贯穿所有层级。

### 设计动机

传统对话系统用扁平的 `history[]` 数组存储历史，无法表达话题之间的层次关系（如"讨论内存扫描 → 分叉到 hook 技术 → 回溯到扫描结果"）。Topic Tree 引入**树投影 + 图关联**的双结构，实现：

1. **话题路由**：新输入应继续当前话题、分叉到新话题、还是附着到历史话题？
2. **跨话题实体引用**："回到刚才的 0x401000" → 在任意历史话题中查找实体
3. **记忆压缩**：深度超过阈值时自动摘要，防止树无限增长
4. **局部热区**：仅保留当前节点附近的全量数据，其余节点可卸载到持久层

### 数据模型

```
TopicNode ──→ 树结构（PARENT_CHILD 边）
  ├── id: str                    # 唯一标识
  ├── parent_id: Optional[str] # 父节点（根节点为 None）
  ├── name: str                 # 话题名称（如"内存扫描"）
  ├── description: str          # 话题描述
  ├── entities: List[Dict]     # 本话题关联的实体
  ├── turn_ids: List[int]      # 关联的轮次索引
  ├── local_profile: Dict       # 本地认知画像（继承父节点但可覆盖）
  ├── depth: int               # 树深度（根 = 0）
  ├── last_active_at: float    # 最近活跃时间戳
  ├── created_at: float        # 创建时间
  ├── children_ids: List[str]  # 子节点列表
  └── metadata: Dict           # 扩展字段（如 is_summary 标记）

TopicEdge ──→ 图结构（跨树关联）
  ├── source_id: str
  ├── target_id: str
  ├── edge_type: TopicEdgeType
  │   ├── PARENT_CHILD      # 树结构：父 → 子
  │   ├── ENTITY_REFERENCE  # 图结构：共享实体引用
  │   ├── SIMILARITY        # 图结构：语义相似
  │   ├── USER_LINK         # 图结构：用户主动关联
  │   └── TEMPORAL          # 图结构：时间顺序
  ├── weight: float          # 关联强度 (0-1)
  └── metadata: Dict
```

### 路由算法

```python
def route(query, turn_index, cohesion_score=0.5, extracted_entities=None):
    """
    基于 cohesion_score 和实体匹配做路由决策。
    
    决策矩阵：
    ────────────────────────────────────────────────────────────
    cohesion_score    实体匹配    动作        说明
    ────────────────────────────────────────────────────────────
    > 0.6             任意        continue   继续当前话题
    0.3 ~ 0.6         有匹配      attach     附着到匹配的历史话题
    0.3 ~ 0.6         无匹配      new        创建新话题（同级）
    < 0.3             任意        fork       分叉新话题（当前节点的子节点）
    ────────────────────────────────────────────────────────────
    """
```

**cohesion_score 来源**：
- PCR 的 `topic_cohesion` 计算（基于查询与当前话题实体的 Jaccard 相似度）
- 或外部语义相似度模型（如 embedding cosine similarity）

### 局部热区（内存优化）

```python
# 热区定义：当前节点 + 前 HOT_ZONE_DEPTH 层祖先 + 后 1 层后代
HOT_ZONE_DEPTH = 2

# 每轮对话后自动维护热区
_maintain_hot_zone(current_node_id)

# 实体查找优先在热区中进行（O(1) 索引），热区外节点可懒加载
_hot_zone_lookup(query, extracted_entities)
```

### 深度防御（路径压缩）

```python
MAX_DEPTH = 6  # 树深度阈值

# 当节点深度超过 6 时，自动将前半段路径压缩为摘要节点
def _check_depth_and_compress(node_id):
    path = _get_path_to_root(node_id)
    if len(path) > MAX_DEPTH:
        mid = len(path) // 2
        summary_node = _create_summary_node(path[:mid])
        # 后半段挂载到摘要节点
        for node in path[mid:]:
            node.parent_id = summary_node.id
```

**摘要节点**：合并被压缩节点的实体和名称，标记 `metadata["is_summary"] = True`。用户可展开查看详情。

### 实体索引（跨话题查询）

```python
# 倒排索引：entity_value → Set[node_id]
_entity_index: Dict[str, Set[str]] = {}

# 使用示例：查找包含 "0x401000" 的所有话题节点
nodes = manager.find_nodes_by_entity("0x401000")
# 返回：TopicNode 列表（可能来自不同分支）
```

### 认知画像继承

```python
# 子节点继承父节点的认知画像，但可本地覆盖
parent_profile = parent.local_profile  # 如 {"domain": "reverse_engineering", "tool": "ghidra"}
child_profile = {**parent_profile, **child.local_profile}  # 本地覆盖

# 使用场景：在"内存扫描"话题下讨论"hook 技术"，子话题继承 reverse_engineering 域画像
```

### 状态流转

```
User Input
  │
  ▼
ParseResult（Intent + Entities）
  │
  ▼
TopicTree.route()
  │
  ├── cohesion_score > 0.6 ──→ continue ──→ 更新当前节点（实体、轮次）
  │
  ├── 0.3 < cohesion_score < 0.6 + 实体匹配 ──→ attach ──→ 切换到匹配节点
  │
  ├── cohesion_score < 0.3 ──→ fork ──→ 创建子节点（继承父画像）
  │
  └── 无历史 ──→ new ──→ 创建根节点
  │
  ▼
维护热区 → 深度检查 → 实体索引更新
  │
  ▼
当前话题上下文（用于下一轮 PCR 的 topic_inheritance）
```

### 使用示例

```python
from core.agent.topic_tree import TopicTreeManager

manager = TopicTreeManager()

# 第 1 轮：创建新话题
d1 = manager.route("scan 0x401000", turn_index=1,
                   extracted_entities=[{"type": "memory_address", "value": "0x401000"}])
# d1.action == "new"
# d1.target_node_id == 根节点 ID

# 第 2 轮：继续当前话题（高 cohesion）
d2 = manager.route("read that address", turn_index=2, cohesion_score=0.8)
# d2.action == "continue"

# 第 3 轮：分叉到新话题（低 cohesion，不同领域）
d3 = manager.route("学习如何写 hook", turn_index=3, cohesion_score=0.1)
# d3.action == "fork"
# 新节点 depth = 1，继承父节点画像

# 第 4 轮：附着到历史话题（实体匹配）
d4 = manager.route("check 0x401000 again", turn_index=4, cohesion_score=0.4,
                   extracted_entities=[{"type": "memory_address", "value": "0x401000"}])
# d4.action == "attach"（通过实体索引找到第 1 轮的节点）

# 查询跨话题实体
nodes = manager.find_nodes_by_entity("0x401000")
# 返回 [TopicNode(根节点, "scan 0x401000", depth=0)]
```

### 测试覆盖

```bash
python -m pytest core/agent/topic_tree/tests/test_topic_tree.py -v
# 测试项：
# - test_route_new: 首次路由创建新话题
# - test_route_continue_high_cohesion: 高 cohesion 继续
# - test_route_fork_low_cohesion: 低 cohesion 分叉
# - test_route_attach_mid_cohesion: 中 cohesion + 实体匹配附着
# - test_entity_index: 跨话题实体查询
# - test_tree_hierarchy: 树结构层次验证
```

---

## 扩展点

### 1. 添加新的 IntentCategory

```python
# core/agent/models.py
class IntentCategory(Enum):
    # ... existing categories
    MY_NEW_CATEGORY = "my_new_category"  # ← 添加

# core/agent/intent_parser.py
register_intent_rule(IntentRule(
    category=IntentCategory.MY_NEW_CATEGORY,
    patterns=_compile([r"my trigger regex"]),
    required_entities=[],
    optional_entities=[EntityType.MY_ENTITY],
    min_confidence=0.6,
    priority=100,
    name="my_new_category",
    domain="my_domain",
))
```

### 2. 添加新的 LLM Provider

```python
# core/agent/llm_providers/my_provider.py
from core.agent.llm_providers.base import LLMProvider, GenerateRequest, GenerateResult

class MyProvider(LLMProvider):
    def generate(self, request: GenerateRequest) -> GenerateResult:
        # 实现生成逻辑
        ...

    def health_check(self) -> bool:
        ...

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        ...

# 注册到工厂
# core/agent/llm_providers/provider_factory.py
```

### 3. 自定义 ExpertiseProbe 词表

```yaml
# config/expertise_lexicon.yaml
weights:
  terminology_density: 0.30
  parameter_precision: 0.30
  query_complexity: 0.15
  language_style: 0.15
  historical_behaviour: 0.10

lexicon:
  terminology:
    - "AST"
    - "CFG"
    - "symbolic execution"
    - "heap spray"
    - "ROP chain"
  # ... more terms
```

### 4. 自定义 PCR 配置

```yaml
# config/agent_config.yaml
thresholds:
  # 调整触发 LLM 补全的阈值
  strategy_completer:
    confidence_low: 0.3
    noise_complexity_combo: 0.3
    advisor_confidence_low: 0.5

  # 调整话题树分叉阈值
  topic_tree:
    cohesion_continue: 0.6
    cohesion_fork: 0.3
```

---

## 下一步

- [QUICKSTART.md](QUICKSTART.md) — 从零到运行
- [LLM_PROVIDER_GUIDE.md](LLM_PROVIDER_GUIDE.md) — Provider 配置详解
- `examples/minimal_agent.py` — 3 行代码集成示例
