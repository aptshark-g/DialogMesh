# 话题树（Topic Tree / Dialog Graph）设计方案 v1.0

> 本文档定义意图识别引擎的话题树架构，解决当前"线性历史"无法处理话题跳切、回溯、多分支并存的结构性缺失。
> 话题树是**会话级记忆结构**，通过 PCRInput_v1 的扩展字段注入，不侵入 PCR 核心规则引擎。

## 目录

- [1. 背景与问题](#1-背景与问题)
- [2. 设计目标](#2-设计目标)
- [3. 核心设计：两层记忆模型](#3-核心设计两层记忆模型)
- [4. 数据模型](#4-数据模型)
- [5. 话题生命周期](#5-话题生命周期)
- [6. 话题路由算法](#6-话题路由算法)
- [7. 与 PCR 集成方案](#7-与-pcr-集成方案)
- [8. 与现有系统集成](#8-与现有系统集成)
- [9. 存储方案](#9-存储方案)
- [10. 测试策略](#10-测试策略)
- [11. 实现计划](#11-实现计划)
- [12. 风险与回退](#12-风险与回退)

---

## 1. 背景与问题

### 当前代码现状

```python
# pcr/datacontract.py — PCRInput_v1 的 session_history 是扁平列表
@dataclass(frozen=True)
class PCRInput_v1:
    query: str
    session_history: List[HistoryEntry]   # ← 线性列表，无话题归属
    process_context: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}         # ← 扩展字段，当前未用于话题
    # ... 其他字段
```

```python
# intent_trace_cli.py — 历史是线性追加
history.append({"role": "user", "content": query})
# 用户说"回到刚才那个" → 系统只能线性搜索 history，无话题概念
```

### 问题

| 场景 | 当前行为 | 期望行为 | 缺失能力 |
|---|---|---|---|
| 用户说"回到刚才那个反汇编" | 在 `history` 中线性搜索关键词"反汇编" | 直接跳转到话题节点 "反汇编分析"，继承该节点上下文 | 话题树索引 |
| 用户从"内存扫描"切换到"学习 Hook"再回来 | 历史混杂，上下文污染，Hook 的实体干扰扫描 | 话题 A 和话题 B 的实体隔离，回来时只加载话题 A 上下文 | 话题隔离 |
| 用户在话题 A 中问了子问题，再回来 | 子问题混入话题 A 的线性历史，难以区分主干 | 话题 A 下挂子节点 A-1，回来时可选回到 A 或 A-1 | 子话题分叉 |
| 用户说"那个地址和之前模块里的有关系吗？" | 系统无法关联两个不同话题的实体 | 跨话题实体关联，图查询找到共同引用 | 话题图关联 |
| 用户同时推进两个独立任务 | 历史全部混在一起，意图识别混乱 | 两个活跃分支，各自独立上下文，可切换 | 多分支并行 |

### 根本原因

当前系统把对话建模为**一维时间序列**：`history[0] → history[1] → ... → history[n]`。

人类对话的自然形态是**树状**（或更一般的图状）：
- 一个话题可以衍生多个子话题（分叉）
- 用户可以跳回之前的话题（回溯）
- 不同话题之间可以引用共同实体（跨边关联）
- 多个话题可以独立推进（并行分支）

---

## 2. 设计目标

### 功能目标

| ID | 目标 | 优先级 | 验收标准 |
|---|---|---|---|
| TT-1 | 话题分叉检测 | P0 | 用户切换话题时，系统创建新分支而非继续线性追加 |
| TT-2 | 话题回溯定位 | P0 | 用户说"回到刚才那个"时，系统能定位到正确话题节点 |
| TT-3 | 话题上下文隔离 | P0 | 不同话题的实体、意图统计不相互污染 |
| TT-4 | 子话题继承 | P1 | 子话题自动继承父话题的实体和画像，但可独立演化 |
| TT-5 | 跨话题实体关联 | P2 | 用户询问跨话题关系时，系统能查询图结构找到关联 |
| TT-6 | 多活跃分支 | P2 | 支持 2-3 个并行活跃话题，用户可主动切换 |
| TT-7 | 话题持久化 | P1 | 话题树结构随会话持久化，重启后可恢复 |

### 非功能目标

| ID | 目标 | 指标 |
|---|---|---|
| N-1 | 话题路由延迟 | 话题检测 + 挂载/分叉 < 5ms（纯规则匹配） |
| N-2 | 内存占用 | 单会话 100 个话题节点 < 500KB |
| N-3 | 无外部依赖 | 话题树零外部依赖（Embedding 可选） |
| N-4 | 向后兼容 | 不启用话题树时，系统退化为线性历史（现有行为） |
| N-5 | 可观测 | 话题切换事件计入日志和仪表盘 |

---

## 3. 核心设计：两层记忆模型

```
┌─────────────────────────────────────────────────────────────────┐
│  推理层（运行时）— 树投影（Tree Projection）                        │
│  ─────────────────────────────────────────────────────────────  │
│  当前活跃分支（Active Branch）                                    │
│                                                                 │
│         ┌─ [节点 A-1] 内存扫描：0x401000                        │
│         │    └─ [节点 A-1-1] 扫描结果分析                        │
│  [根] ──┼─ [节点 A-2] 修改数值：锁定 90                          │
│         │    └─ [节点 A-2-1] 冻结效果确认                        │
│         └─ [节点 B]   学习 Hook 教程                             │
│              └─ [节点 B-1] 尝试 hook MessageBoxA                  │
│                                                                 │
│  当前指针：A-2-1（用户正在确认冻结效果）                          │
│  用户输入："回到刚才那个扫描"                                     │
│  → 路由：A-2-1 → A-1（回溯）                                    │
│  → PCR 收到：topic_node_id="A-1", topic_context=[A-1 的实体]     │
├─────────────────────────────────────────────────────────────────┤
│  存储层（持久化）— 图结构（Graph / Adjacency List）               │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  topic_nodes 表                                                  │
│  ├── node_id: "A-1"                                              │
│  ├── parent_id: "A"                                              │
│  ├── intent_category: "TOOL"                                     │
│  ├── entities: ["0x401000", "4 bytes"]                          │
│  ├── status: "paused"                                            │
│  └── turn_ids: [3, 4, 5]                                       │
│                                                                 │
│  topic_edges 表（支持跨话题关联）                                 │
│  ├── from_node: "A-1"                                            │
│  ├── to_node: "B-1"                                              │
│  ├── edge_type: "entity_reference"                               │
│  └── shared_entity: "0x401000"                                   │
│                                                                 │
│  查询："那个地址和模块里的有关系吗？"                             │
│  → 图查询：find_nodes_with_entity("0x401000")                   │
│  → 返回：A-1（内存扫描）, C-2（模块分析）→ 跨话题关联           │
└─────────────────────────────────────────────────────────────────┘
```

### 设计原则：分层职责

| 层级 | 职责 | 不做什么 |
|---|---|---|
| **话题树（TopicTreeManager）** | 检测话题切换、维护分支结构、提供上下文过滤 | 不做意图分类（PCR 负责） |
| **PCR（规则引擎）** | 基于 topic_tree 提供的上下文做意图识别 | 不感知话题结构（只接收过滤后的 history） |
| **存储层（SQLite）** | 保存节点和边的关系，支持图查询 | 不做话题路由决策 |

---

## 4. 数据模型

### 4.1 TopicNode（话题节点）

```python
@dataclass
class TopicNode:
    """
    话题树节点。
    每个节点代表一个独立的话题上下文，包含该话题下的轮次索引和提取的实体。
    """
    node_id: str                    # UUID 或语义 ID（如 "mem_scan_1"）
    parent_id: Optional[str]        # 父节点 ID（null = 根节点 / 独立话题）
    session_id: str                 # 所属会话
    
    # 创建信息
    intent_category: str            # 创建该节点时的意图类别（TOOL / ADVISOR / COMPANION）
    created_by_turn: int              # 哪一轮创建了该话题
    created_at: float               # 时间戳
    
    # 状态
    status: str = "active"          # active | paused | resumed | resolved | abandoned
    last_active_turn: int = 0       # 最后一次活跃轮次
    last_active_at: float = 0.0     # 最后一次活跃时间戳
    
    # 内容摘要
    title: str = ""                 # 话题标题（规则生成或 LLM 摘要）
    entities: List[str] = field(default_factory=list)   # 该话题提取的关键实体
    keywords: List[str] = field(default_factory=list)   # 关键词指纹（用于快速匹配）
    
    # 历史范围
    turn_ids: List[int] = field(default_factory=list)   # 属于该话题的 turn index 列表
    
    # 认知画像（该话题内的局部画像，可继承父节点）
    local_profile: Dict[str, float] = field(default_factory=dict)
    
    # 树深度
    depth: int = 0                  # 节点深度（根 = 0，子节点 +1）
    
    def is_ancestor_of(self, other: "TopicNode") -> bool:
        """判断 self 是否是 other 的祖先。"""
        # 由 TopicTreeManager 维护，此处简化
        return False
    
    def to_summary(self) -> "TopicNodeSummary":
        """生成摘要（用于注入 PCRInput）。"""
        return TopicNodeSummary(
            node_id=self.node_id,
            title=self.title,
            intent_category=self.intent_category,
            entities=self.entities[:5],      # 只取前 5 个实体
            keywords=self.keywords[:5],
            status=self.status,
            depth=self.depth,
        )


@dataclass
class TopicNodeSummary:
    """话题节点摘要（轻量，用于注入 PCRInput_v1）。"""
    node_id: str
    title: str
    intent_category: str
    entities: List[str]
    keywords: List[str]
    status: str
    depth: int
```

### 4.2 TopicEdge（话题边）

```python
@dataclass
class TopicEdge:
    """
    话题边。
    默认边表示父子关系（树结构），扩展边表示跨话题关联（图结构）。
    """
    edge_id: str
    from_node: str
    to_node: str
    edge_type: str = "parent_child"     # parent_child | entity_reference | similarity | user_link
    
    # 关联信息（可选）
    shared_entity: Optional[str] = None   # 跨话题关联的共享实体
    similarity_score: float = 0.0          # 相似度分数（用于 similarity 边）
    created_at: float = 0.0
    
    # user_link：用户显式关联（如"那个地址和模块里的有关系吗？"）
    user_query: Optional[str] = None
```

### 4.3 TopicTreeManager（话题树管理器）

```python
class TopicTreeManager:
    """
    话题树管理器。
    负责：
    1. 检测用户输入是否属于当前话题（继续）或新话题（分叉）或旧话题（回溯）
    2. 维护话题树结构（内存中）
    3. 为 PCR 提供过滤后的历史上下文
    """
    
    # 话题切换检测阈值
    FORK_THRESHOLD = 0.3          # 与当前话题相似度 < 0.3 → 分叉
    ATTACH_THRESHOLD = 0.7        # 与历史话题相似度 > 0.7 → 回溯挂载
    
    def __init__(self, 
                 session_id: str,
                 enable_semantic_match: bool = False,   # 是否启用语义匹配（需要 Embedding）
                 llm_provider: Optional[LLMProvider] = None):
        self.session_id = session_id
        self.enable_semantic_match = enable_semantic_match
        self.llm = llm_provider
        
        # 内存结构
        self.nodes: Dict[str, TopicNode] = {}           # node_id -> TopicNode
        self.edges: List[TopicEdge] = []                # 边列表
        self.current_node_id: Optional[str] = None      # 当前活跃话题
        self.root_id: Optional[str] = None              # 根节点
        
        # 快速索引
        self._entity_index: Dict[str, List[str]] = {}  # entity -> [node_id, ...]
        self._keyword_index: Dict[str, List[str]] = {}  # keyword -> [node_id, ...]
    
    def route(self, 
              query: str, 
              current_turn: int,
              pcr_output: Any = None) -> "TopicRouteResult":
        """
        话题路由：决定当前输入属于哪个话题。
        
        返回 TopicRouteResult，包含：
        - action: "continue" | "fork" | "attach" | "resume"
        - target_node_id: 目标话题节点
        - context_scope: 应该加载的 turn_ids 列表
        """
        # 1. 提取当前输入的实体和关键词
        query_entities = self._extract_entities(query)
        query_keywords = self._extract_keywords(query)
        
        # 2. 计算与当前话题的相似度
        current_sim = 0.0
        if self.current_node_id:
            current_sim = self._similarity(
                self.nodes[self.current_node_id], 
                query_entities, query_keywords
            )
        
        # 3. 如果与当前话题足够相似 → 继续
        if current_sim >= self.FORK_THRESHOLD:
            return TopicRouteResult(
                action="continue",
                target_node_id=self.current_node_id,
                context_scope=self._get_context_scope(self.current_node_id),
            )
        
        # 4. 搜索历史话题匹配（回溯）
        best_match = None
        best_score = 0.0
        for node_id, node in self.nodes.items():
            if node_id == self.current_node_id:
                continue
            score = self._similarity(node, query_entities, query_keywords)
            if score > best_score:
                best_score = score
                best_match = node_id
        
        # 5. 如果匹配到历史话题 → 回溯挂载
        if best_match and best_score >= self.ATTACH_THRESHOLD:
            return TopicRouteResult(
                action="attach",
                target_node_id=best_match,
                context_scope=self._get_context_scope(best_match),
            )
        
        # 6. 否则 → 分叉（创建新话题）
        return TopicRouteResult(
            action="fork",
            target_node_id=None,  # 需要创建新节点
            context_scope=self._get_context_scope(self.current_node_id) if self.current_node_id else [],
        )
    
    def create_node(self, 
                    parent_id: Optional[str],
                    intent_category: str,
                    turn_id: int,
                    query: str,
                    entities: List[str] = None) -> TopicNode:
        """创建新话题节点。"""
        node_id = f"topic_{len(self.nodes)}_{int(time.time())}"
        
        parent = self.nodes.get(parent_id)
        depth = (parent.depth + 1) if parent else 0
        
        # 生成标题（规则：取 query 前 20 字 + 意图标签）
        title = f"[{intent_category}] {query[:20]}..."
        
        node = TopicNode(
            node_id=node_id,
            parent_id=parent_id,
            session_id=self.session_id,
            intent_category=intent_category,
            created_by_turn=turn_id,
            created_at=time.time(),
            status="active",
            last_active_turn=turn_id,
            title=title,
            entities=entities or [],
            keywords=self._extract_keywords(query),
            turn_ids=[turn_id],
            depth=depth,
        )
        
        self.nodes[node_id] = node
        if parent_id:
            self.edges.append(TopicEdge(
                edge_id=f"edge_{len(self.edges)}",
                from_node=parent_id,
                to_node=node_id,
                edge_type="parent_child",
            ))
        else:
            self.root_id = node_id
        
        # 更新索引
        self._index_node(node)
        
        # 切换当前话题
        self.current_node_id = node_id
        return node
    
    def attach_to_node(self, node_id: str, turn_id: int) -> TopicNode:
        """回溯挂载到已有话题。"""
        node = self.nodes[node_id]
        node.status = "resumed"
        node.last_active_turn = turn_id
        node.last_active_at = time.time()
        node.turn_ids.append(turn_id)
        
        self.current_node_id = node_id
        return node
    
    def continue_current(self, turn_id: int) -> TopicNode:
        """继续当前话题。"""
        if not self.current_node_id:
            raise ValueError("No current topic node")
        node = self.nodes[self.current_node_id]
        node.last_active_turn = turn_id
        node.last_active_at = time.time()
        node.turn_ids.append(turn_id)
        return node
    
    def get_pcr_input_context(self, 
                               node_id: str,
                               full_history: List[HistoryEntry]) -> List[HistoryEntry]:
        """
        获取 PCR 应该接收的过滤历史。
        策略：当前话题 + 祖先话题的摘要（继承上下文），不包含兄弟话题。
        """
        node = self.nodes[node_id]
        
        # 1. 当前话题的完整历史
        context_turn_ids = set(node.turn_ids)
        
        # 2. 祖先话题的最近 2 轮（继承上下文，但不全量）
        ancestor = self.nodes.get(node.parent_id)
        while ancestor:
            if ancestor.turn_ids:
                # 只取祖先话题的最后 2 轮（避免上下文过长）
                context_turn_ids.update(ancestor.turn_ids[-2:])
            ancestor = self.nodes.get(ancestor.parent_id)
        
        # 3. 按时间顺序组装
        filtered = [h for i, h in enumerate(full_history) if i in context_turn_ids]
        return filtered
    
    def get_topic_ancestry(self, node_id: str) -> List[TopicNodeSummary]:
        """获取节点的祖先链（从根到当前）。"""
        ancestry = []
        current = self.nodes.get(node_id)
        while current:
            ancestry.append(current.to_summary())
            current = self.nodes.get(current.parent_id)
        return list(reversed(ancestry))  # 根 -> 当前
    
    def get_siblings(self, node_id: str) -> List[TopicNodeSummary]:
        """获取兄弟节点（用于指代消解"那个"）。"""
        node = self.nodes[node_id]
        if not node.parent_id:
            return []
        siblings = [
            n.to_summary() for n in self.nodes.values()
            if n.parent_id == node.parent_id and n.node_id != node_id
        ]
        return siblings
    
    def find_cross_topic_links(self, entity: str) -> List[TopicNodeSummary]:
        """
        跨话题实体关联查询。
        返回所有包含该实体的其他话题节点。
        """
        node_ids = self._entity_index.get(entity, [])
        return [
            self.nodes[nid].to_summary() for nid in node_ids
            if nid != self.current_node_id
        ]
    
    def _similarity(self, 
                    node: TopicNode, 
                    query_entities: List[str],
                    query_keywords: List[str]) -> float:
        """
        计算输入与话题节点的相似度。
        纯规则版本：基于实体重叠和关键词重叠。
        语义版本：如果启用 Embedding，叠加语义相似度。
        """
        if not node.entities and not node.keywords:
            return 0.0
        
        # 实体重叠
        entity_overlap = 0.0
        if node.entities and query_entities:
            overlap = len(set(node.entities) & set(query_entities))
            entity_overlap = overlap / max(len(node.entities), len(query_entities))
        
        # 关键词重叠
        keyword_overlap = 0.0
        if node.keywords and query_keywords:
            overlap = len(set(node.keywords) & set(query_keywords))
            keyword_overlap = overlap / max(len(node.keywords), len(query_keywords))
        
        # 综合分数（可加权调整）
        score = entity_overlap * 0.6 + keyword_overlap * 0.4
        
        # 语义增强（可选，需要 Embedding）
        if self.enable_semantic_match and self.llm:
            # 通过 LLM 或本地 Embedding 计算语义相似度
            # 此处预留接口，实现时调用 embedding 模型
            semantic_score = 0.0  # 占位
            score = score * 0.5 + semantic_score * 0.5
        
        return score
    
    def _extract_entities(self, text: str) -> List[str]:
        """从文本提取实体（复用现有 entity 提取规则）。"""
        import re
        entities = []
        # 地址
        entities.extend(re.findall(r'0x[0-9a-fA-F]+', text))
        # 数值
        entities.extend(re.findall(r'\b\d+\b', text))
        return entities
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词指纹（简单分词 + 去停用词）。"""
        # 简化版：提取技术术语
        tech_terms = [
            "scan", "patch", "hook", "bp", "breakpoint", "disasm",
            "内存", "扫描", "修改", "锁定", "冻结", "断点", "反汇编",
            "attach", "detach", "module", "模块", "address", "地址",
        ]
        text_lower = text.lower()
        return [t for t in tech_terms if t in text_lower]
    
    def _index_node(self, node: TopicNode):
        """更新实体和关键词索引。"""
        for e in node.entities:
            self._entity_index.setdefault(e, []).append(node.node_id)
        for k in node.keywords:
            self._keyword_index.setdefault(k, []).append(node.node_id)
    
    def _get_context_scope(self, node_id: str) -> List[int]:
        """获取话题节点的 turn_ids 列表。"""
        node = self.nodes.get(node_id)
        return node.turn_ids if node else []


@dataclass
class TopicRouteResult:
    """话题路由结果。"""
    action: str           # "continue" | "fork" | "attach" | "resume"
    target_node_id: Optional[str]
    context_scope: List[int]   # 应该加载的 turn index 列表
    similarity_score: float = 0.0   # 匹配分数（用于调试）
    matched_keywords: List[str] = field(default_factory=list)  # 匹配到的关键词
```

---

## 5. 话题生命周期

```
┌─────────┐    fork/attach     ┌─────────┐    user inactive    ┌─────────┐
│  不存在  │ ─────────────────→ │ active  │ ─────────────────→ │ paused  │
└─────────┘                    └─────────┘   (>5 min 无交互)   └─────────┘
                                     │                              │
                                     │ user says "finished"/"done"  │ user returns
                                     ↓                              ↓
                               ┌─────────┐                    ┌─────────┐
                               │resolved │                    │resumed  │
                               └─────────┘                    └─────────┘
                                     │                              │
                                     │ user abandons                  │ user leaves
                                     ↓                              ↓
                               ┌─────────┐                    ┌─────────┐
                               │abandoned│                    │abandoned│
                               └─────────┘                    └─────────┘
```

### 状态说明

| 状态 | 含义 | 触发条件 | 上下文是否保留 |
|---|---|---|---|
| **active** | 当前活跃话题 | 用户正在交互 | 完整保留 |
| **paused** | 暂时中断 | 用户切换到其他话题 | 保留，可恢复 |
| **resumed** | 恢复活跃 | 用户回到该话题 | 完整保留 |
| **resolved** | 正常结束 | 用户明确表示完成 | 保留（归档） |
| **abandoned** | 废弃 | 用户长时间未返回（>30 min） | 压缩为摘要，保留结构 |

---

## 6. 话题路由算法

### 6.1 算法流程

```python
def route_topic(query: str, current_turn: int, pcr_output) -> TopicRouteResult:
    """
    话题路由算法。
    1. 提取当前输入的实体和关键词
    2. 计算与当前话题的相似度
    3. 如果相似度 >= FORK_THRESHOLD → continue
    4. 否则搜索历史话题，如果最佳匹配 >= ATTACH_THRESHOLD → attach
    5. 否则 → fork（创建新话题）
    """
    
    # Step 1: 提取特征
    query_entities = extract_entities(query)
    query_keywords = extract_keywords(query)
    
    # Step 2: 与当前话题比较
    if current_node:
        sim_current = similarity(current_node, query_entities, query_keywords)
        if sim_current >= FORK_THRESHOLD:
            return TopicRouteResult(action="continue", ...)
    
    # Step 3: 回溯搜索（只在最近 10 个历史话题中搜索，避免全量扫描）
    recent_nodes = get_recent_nodes(limit=10)  # 按 last_active 排序
    best_match = None
    best_score = 0.0
    for node in recent_nodes:
        score = similarity(node, query_entities, query_keywords)
        if score > best_score:
            best_score = score
            best_match = node
    
    # Step 4: 判断回溯
    if best_match and best_score >= ATTACH_THRESHOLD:
        return TopicRouteResult(action="attach", target_node_id=best_match.node_id, ...)
    
    # Step 5: 分叉
    return TopicRouteResult(action="fork", ...)
```

### 6.2 回溯触发词（规则增强）

除了相似度计算，以下关键词**强制触发回溯**（绕过相似度阈值）：

```python
ATTACH_KEYWORDS = {
    "回到", "回到刚才", "回到之前", "继续刚才", "接着那个",
    "back to", "continue with", "go back to", "resume",
    "那个", "刚才的", "之前的", "上一个",
    "the previous", "that one", "the one before",
}

def check_forced_attach(query: str) -> Optional[str]:
    """检查是否包含强制回溯词。"""
    if any(kw in query for kw in ATTACH_KEYWORDS):
        # 强制回溯到最近 3 个 paused 话题中最近活跃的
        return get_most_recent_paused_topic()
    return None
```

### 6.3 分叉检测（语义层面）

当用户输入同时满足以下条件时，**强制分叉**（不继续当前话题）：

1. 意图类别变化（如从 TOOL 变为 COMPANION）
2. 实体集合完全不重叠（当前话题实体 ∩ 输入实体 = ∅）
3. 不包含任何回溯触发词

```python
def should_force_fork(current_node: TopicNode, 
                       pcr_intent: str,
                       query_entities: List[str]) -> bool:
    if not current_node:
        return True  # 无当前话题，必须新建
    
    # 意图类别变化 + 无实体重叠 → 强制分叉
    intent_changed = (pcr_intent != current_node.intent_category)
    no_overlap = not (set(current_node.entities) & set(query_entities))
    
    return intent_changed and no_overlap
```

---

## 7. 与 PCR 集成方案

### 7.1 修改 PCRInput_v1（预留接口）

```python
@dataclass(frozen=True)
class PCRInput_v1:
    version: str = PCRVersion.V1.value
    modality: Modality = Modality.TEXT
    query: str = ""
    raw_payload: Optional[Dict[str, Any]] = None
    session_id: str = ""
    turn_index: int = 0
    session_history: List[HistoryEntry] = field(default_factory=list)
    process_context: Optional[Dict[str, Any]] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)   # ← 扩展字段
    timestamp: float = field(default_factory=time.time)
    
    # ── 新增：话题树注入字段（Phase 1 预留，Phase 2 实现）──
    topic_node_id: Optional[str] = None           # 当前话题节点 ID
    topic_ancestry: List[TopicNodeSummary] = None  # 祖先链（上下文继承）
    topic_siblings: List[TopicNodeSummary] = None   # 兄弟节点（指代消解）
    topic_history_scope: List[int] = None         # 该话题的 turn index 范围
    topic_cross_links: List[TopicNodeSummary] = None  # 跨话题关联（图查询）
    
    def __post_init__(self):
        # ... 现有校验 ...
        
        # 话题树字段校验（如果启用）
        if self.topic_node_id and not self.topic_ancestry:
            raise ValueError("topic_node_id 提供时必须有 topic_ancestry")
```

### 7.2 修改 PCR 调用流程（IntentTraceRunner）

```python
def run_intent_trace_with_topic_tree(
    query: str,
    session_id: str,
    persistence: CLISessionPersistence,
    topic_tree: Optional[TopicTreeManager] = None,   # ← 新增：话题树（可选）
    provider: LLMProvider = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    带话题树的意图追踪执行器。
    """
    
    # 1. 加载完整历史（从持久化或内存缓存）
    full_history = persistence.get_history(session_id) if persistence else []
    
    # 2. 话题路由（如果启用话题树）
    topic_context = None
    if topic_tree:
        # 先做一轮轻量 PCR（无历史，只判断意图类别）
        # 用于话题分叉的意图类别变化检测
        pcr_preview = RuleBasedPCR().evaluate(PCRInput_v1(query=query))
        
        route_result = topic_tree.route(
            query=query,
            current_turn=len(full_history),
            pcr_output=pcr_preview,
        )
        
        if route_result.action == "fork":
            # 创建新话题节点
            topic_tree.create_node(
                parent_id=topic_tree.current_node_id,
                intent_category=pcr_preview.expectation,
                turn_id=len(full_history),
                query=query,
                entities=extract_entities(query),
            )
        elif route_result.action == "attach":
            # 回溯到旧话题
            topic_tree.attach_to_node(route_result.target_node_id, len(full_history))
        elif route_result.action == "continue":
            # 继续当前话题
            topic_tree.continue_current(len(full_history))
        
        # 获取话题过滤后的历史
        topic_context = topic_tree.get_pcr_input_context(
            topic_tree.current_node_id,
            full_history
        )
        
        # 获取话题树信息（注入 PCR）
        ancestry = topic_tree.get_topic_ancestry(topic_tree.current_node_id)
        siblings = topic_tree.get_siblings(topic_tree.current_node_id)
    else:
        # 未启用话题树：退化为线性历史（现有行为）
        topic_context = full_history
        ancestry = None
        siblings = None
    
    # 3. 构建 PCR 输入（包含话题树信息）
    pcr_input = PCRInput_v1(
        query=query,
        session_history=topic_context,   # ← 过滤后的历史（只包含当前话题 + 祖先）
        topic_node_id=topic_tree.current_node_id if topic_tree else None,
        topic_ancestry=ancestry,
        topic_siblings=siblings,
        topic_history_scope=route_result.context_scope if topic_tree else None,
    )
    
    # 4. 执行 PCR（复用现有逻辑）
    pcr = RuleBasedPCR()
    pcr_output = pcr.evaluate(pcr_input)
    
    # 5. 后续流程（门控、意图解析、执行...）保持不变
    # ...
    
    return result
```

### 7.3 指代消解增强（利用话题树）

```python
class AnaphoraResolver:
    """
    指代消解增强器。
    利用话题树的信息（祖先链、兄弟节点）解析"那个""之前"等指代。
    """
    
    def resolve(self, query: str, pcr_input: PCRInput_v1) -> Optional[str]:
        # 1. 检测指代词
        anaphora_markers = ["那个", "这个", "之前", "刚才", "上一步", 
                           "that", "this", "previous", "the one"]
        if not any(m in query for m in anaphora_markers):
            return None
        
        # 2. 在话题祖先链中查找最近实体（优先当前话题）
        if pcr_input.topic_ancestry:
            for node_summary in reversed(pcr_input.topic_ancestry):
                if node_summary.entities:
                    # 返回最相关的实体（可进一步用类型匹配）
                    return node_summary.entities[-1]
        
        # 3. 在兄弟话题中查找（用户说"那个"可能指兄弟话题）
        if pcr_input.topic_siblings:
            for sibling in pcr_input.topic_siblings:
                if sibling.entities and any(e in query for e in sibling.entities):
                    return sibling.entities[0]
        
        return None
```

---

## 8. 与现有系统集成

### 8.1 与 ContextWindowManager（窗口管理）的集成

话题树和窗口管理是**正交**的：

- **话题树**决定**哪些历史轮次**应该被加载（话题过滤）
- **窗口管理**决定**这些轮次如何压缩**（热/温/冷三层）

集成顺序：

```python
# 1. 话题树过滤：从 full_history → topic_filtered_history
filtered_history = topic_tree.get_pcr_input_context(node_id, full_history)

# 2. 窗口管理压缩：从 topic_filtered_history → compressed_history
pcr_input = window_manager.build_pcr_input(
    query=query,
    history=filtered_history,   # ← 注意：传给窗口管理的是已过滤的历史
    session_profile=profile,
)
```

**关键点**：窗口管理的热/温/冷三层只在**话题过滤后的子集**上运作，而不是全量历史。这进一步减少了压缩负担。

### 8.2 与 Observability（可观测性）的集成

话题切换事件应该被记录：

```python
# 在 DecisionLogEntry 中增加话题字段
@dataclass
class DecisionLogEntry:
    # ... 现有字段 ...
    topic_node_id: Optional[str] = None
    topic_action: Optional[str] = None   # "continue" | "fork" | "attach"
    topic_similarity_score: float = 0.0
```

仪表盘增加话题统计：

```
============================================================
  📊 会话指标仪表盘
============================================================
  ...
  话题树:
    总节点数: 8
    活跃分支: 3
    当前话题: topic_5 (修改数值)
    最近切换: 2 轮前 (从"内存扫描"→"修改数值")
  ...
```

### 8.3 与 Persistence（持久化）的集成

话题树需要持久化到 SQLite：

```sql
-- 话题节点表
CREATE TABLE topic_nodes (
    node_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_id TEXT,
    intent_category TEXT,
    created_by_turn INTEGER,
    created_at REAL,
    status TEXT,
    last_active_turn INTEGER,
    last_active_at REAL,
    title TEXT,
    entities JSON,          -- ["0x401000", "4 bytes"]
    keywords JSON,          -- ["scan", "memory"]
    turn_ids JSON,          -- [3, 4, 5]
    depth INTEGER,
    local_profile JSON,     -- {"expertise": 0.8, "stability": 0.9}
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_topic_session ON topic_nodes(session_id, last_active_at DESC);
CREATE INDEX idx_topic_parent ON topic_nodes(parent_id);

-- 话题边表（支持图查询）
CREATE TABLE topic_edges (
    edge_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_type TEXT,         -- parent_child | entity_reference | similarity | user_link
    shared_entity TEXT,
    similarity_score REAL,
    created_at REAL,
    user_query TEXT,
    FOREIGN KEY (from_node) REFERENCES topic_nodes(node_id),
    FOREIGN KEY (to_node) REFERENCES topic_nodes(node_id)
);

CREATE INDEX idx_edge_from ON topic_edges(from_node);
CREATE INDEX idx_edge_to ON topic_edges(to_node);
CREATE INDEX idx_edge_entity ON topic_edges(shared_entity);
```

---

## 9. 存储方案

### 9.1 运行时结构（内存）

```python
class TopicTreeRuntime:
    """运行时话题树（内存中）。"""
    nodes: Dict[str, TopicNode]              # 快速 O(1) 访问
    edges: List[TopicEdge]                   # 边列表
    current_node_id: Optional[str]
    
    # 索引（加速查询）
    _entity_index: Dict[str, List[str]]      # entity -> node_ids
    _keyword_index: Dict[str, List[str]]     # keyword -> node_ids
    _status_index: Dict[str, List[str]]      # status -> node_ids
```

### 9.2 持久化结构（SQLite）

- `topic_nodes` 表：完整节点数据
- `topic_edges` 表：边的关系
- 加载时：从 SQLite 读取节点和边，重建内存中的树/图
- 保存时：增量保存（只保存 dirty 的节点）

### 9.3 为什么底层用图、前端用树？

| 场景 | 需要的结构 | 原因 |
|---|---|---|
| 用户回溯到父话题 | 树 | 需要明确的 parent-child 路径 |
| 用户问"两个话题有什么关系" | 图 | 需要跨分支的 entity_reference 边 |
| 话题推荐（"你可能还想了解..."） | 图 | 需要相似度边（similarity） |
| 持久化查询 | 图 | 邻接表支持任意方向的图遍历 |

**实现策略**：
- 内存中维护 `parent_id` 指针形成树结构（快速祖先遍历）
- 额外维护 `edges` 列表存储非父子关系（图查询时遍历）
- 数据库中统一用 `topic_edges` 表存储所有边，查询时按 `edge_type` 过滤

---

## 10. 测试策略

### 10.1 单元测试

```python
class TestTopicTreeManager(unittest.TestCase):
    
    def test_fork_detection(self):
        """话题分叉检测：意图变化 + 无实体重叠 → 创建新节点。"""
        tree = TopicTreeManager("session_1")
        
        # 创建第一个话题：内存扫描
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        
        # 用户切换到学习：意图 COMPANION + 无实体重叠 → 分叉
        route = tree.route("我想学习 Hook 教程", 1, type('obj', (), {'expectation': 'COMPANION'})())
        
        self.assertEqual(route.action, "fork")
        self.assertIsNone(route.target_node_id)
    
    def test_attach_detection(self):
        """话题回溯：关键词匹配到历史话题 → attach。"""
        tree = TopicTreeManager("session_1")
        
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        tree.create_node(tree.current_node_id, "COMPANION", 1, "学习 Hook", ["Hook"])
        
        # 用户回到扫描话题
        route = tree.route("回到刚才那个扫描", 2, type('obj', (), {'expectation': 'TOOL'})())
        
        self.assertEqual(route.action, "attach")
        self.assertIsNotNone(route.target_node_id)
    
    def test_forced_attach_keywords(self):
        """强制回溯词：包含"回到刚才" → 直接 attach。"""
        tree = TopicTreeManager("session_1")
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        
        route = tree.route("回到刚才", 1)
        self.assertEqual(route.action, "attach")
    
    def test_context_isolation(self):
        """话题上下文隔离：只加载当前话题 + 祖先的轮次。"""
        tree = TopicTreeManager("session_1")
        
        # 话题 A：轮次 0, 1
        node_a = tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        tree.continue_current(1)
        
        # 话题 B（分叉）：轮次 2, 3
        node_b = tree.create_node(node_a.node_id, "TOOL", 2, "patch 0x2000", ["0x2000"])
        tree.continue_current(3)
        
        # 当前在话题 B，获取上下文
        context = tree.get_pcr_input_context(node_b.node_id, [
            HistoryEntry(role="user", content="scan 0x401000"),  # 0
            HistoryEntry(role="user", content="found 5"),         # 1
            HistoryEntry(role="user", content="patch 0x2000"),   # 2
            HistoryEntry(role="user", content="locked"),          # 3
        ])
        
        # 应该包含话题 B 的轮次 2, 3 + 祖先 A 的最后 2 轮 0, 1
        self.assertEqual(len(context), 4)
    
    def test_cross_topic_entity_query(self):
        """跨话题实体查询。"""
        tree = TopicTreeManager("session_1")
        
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        tree.create_node(None, "ADVISOR", 1, "分析模块 0x401000", ["0x401000"])
        
        # 查询包含 0x401000 的所有话题
        links = tree.find_cross_topic_links("0x401000")
        self.assertEqual(len(links), 2)
```

### 10.2 集成测试

```python
class TestTopicTreeWithPCR(unittest.TestCase):
    """话题树 + PCR 端到端测试。"""
    
    def test_topic_switch_pcr_context(self):
        """
        1. 用户在话题 A 讨论内存扫描
        2. 用户切换到话题 B 学习 Hook
        3. 用户回到话题 A，PCR 应该只加载话题 A 的历史
        4. 验证 PCR 不会误判（因为话题 B 的 Hook 实体被隔离）
        """
        tree = TopicTreeManager("session_1")
        
        # 模拟 4 轮对话
        history = [
            HistoryEntry(role="user", content="scan 0x401000"),       # 0: 话题 A
            HistoryEntry(role="user", content="found 5 addresses"),   # 1: 话题 A
            HistoryEntry(role="user", content="我想学习 Hook"),       # 2: 话题 B
            HistoryEntry(role="user", content="如何 hook MessageBox"), # 3: 话题 B
        ]
        
        # 创建话题 A
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        tree.continue_current(1)
        
        # 切换到话题 B（分叉）
        tree.create_node(tree.current_node_id, "COMPANION", 2, "学习 Hook", ["Hook"])
        tree.continue_current(3)
        
        # 用户回到话题 A
        route = tree.route("回到刚才那个扫描", 4)
        self.assertEqual(route.action, "attach")
        
        # 获取 PCR 上下文
        context = tree.get_pcr_input_context(route.target_node_id, history)
        
        # 验证上下文只包含话题 A 的轮次，不包含话题 B 的 Hook 内容
        contents = [h.content for h in context]
        self.assertIn("scan 0x401000", contents)
        self.assertNotIn("我想学习 Hook", contents)
```

---

## 11. 实现计划

### Phase 1: 预留接口（0.5 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1.1 | `pcr/datacontract.py` | `PCRInput_v1` 增加 `topic_node_id`, `topic_ancestry`, `topic_siblings`, `topic_history_scope` 字段（空实现） |
| 1.2 | `pcr/datacontract.py` | 增加 `TopicNodeSummary` dataclass |
| 1.3 | `tests/test_pcr_topic_fields.py` | 验证新增字段不影响现有 PCR 逻辑（向后兼容） |

### Phase 2: 核心话题树（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2.1 | `agent/topic_tree/manager.py` | 创建 `TopicTreeManager` + `TopicNode` + `TopicEdge` + `TopicRouteResult` |
| 2.2 | `agent/topic_tree/manager.py` | 实现 `route()` / `create_node()` / `attach_to_node()` / `continue_current()` |
| 2.3 | `agent/topic_tree/manager.py` | 实现 `get_pcr_input_context()` / `get_topic_ancestry()` / `get_siblings()` |
| 2.4 | `tests/test_topic_tree.py` | 单元测试：分叉、回溯、上下文隔离、跨话题查询 |
| 2.5 | `tests/test_topic_tree_pcr.py` | 集成测试：话题树 + PCR 端到端 |

### Phase 3: 持久化与集成（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 3.1 | `service/stores/async_sqlite.py` | 增加 `topic_nodes` / `topic_edges` 表创建 |
| 3.2 | `service/stores/async_sqlite.py` | 增加 `save_topic_tree()` / `load_topic_tree()` |
| 3.3 | `service/session_persistence.py` | `CLISessionPersistence` 集成 `TopicTreeManager`（创建/加载/保存） |
| 3.4 | `intent_trace_cli.py` | 添加 `--enable-topic-tree` 参数，注入 `TopicTreeManager` |
| 3.5 | `tests/test_topic_tree_persistence.py` | 持久化恢复测试 |

### Phase 4: 增强功能（可选，未来）

| 任务 | 说明 |
|---|---|
| 4.1 | 语义相似度匹配（Embedding） |
| 4.2 | LLM 生成话题标题 |
| 4.3 | 跨话题实体关联自动检测 |
| 4.4 | 话题推荐（基于相似度边） |

---

## 12. 风险与回退

### 风险 1: 话题误检测（错误分叉）

**场景**：用户在同话题内使用了新词汇，系统误判为话题切换。

**回退**：
- 降低 `FORK_THRESHOLD`（从 0.3 降到 0.2）
- 增加"意图类别变化 + 无实体重叠"双重确认（单独一项不触发分叉）
- 允许用户显式纠正（"我还在说那个扫描" → 合并话题）

### 风险 2: 回溯失败（找不到正确话题）

**场景**：用户说"回到刚才那个"，但多个历史话题相似度相近。

**回退**：
- 强制回溯词（"回到刚才"）优先匹配最近 paused 话题
- 如果多个候选，列出让用户选择（CLI 模式）
- 相似度差距 < 0.1 时，保守策略：继续当前话题而非回溯

### 风险 3: 话题树膨胀（内存占用）

**场景**：1000 轮对话产生 200 个话题节点。

**回退**：
- 自动合并：abandoned 状态且超过 50 轮无访问的子节点，合并到父节点
- 限制深度：最大深度 5，超过时强制扁平化
- 定期清理：只保留最近 20 个 active/paused 节点，其余归档到 SQLite

### 风险 4: 与现有测试冲突

**场景**：新增 `topic_*` 字段导致 `PCRInput_v1` 的 `frozen=True` 测试失败。

**回退**：
- 所有话题字段使用 `Optional` + 默认值 `None`
- 现有测试不传入话题字段时，行为完全一致（向后兼容）
- 新增测试单独验证话题字段

---

## 附录：文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `pcr/datacontract.py` | 📝 修改 | `PCRInput_v1` 增加话题字段（预留） |
| `pcr/datacontract.py` | 🆕 新增 | `TopicNodeSummary` dataclass |
| `agent/topic_tree/manager.py` | 🆕 新建 | `TopicTreeManager` + `TopicNode` + `TopicEdge` + `TopicRouteResult` |
| `agent/topic_tree/__init__.py` | 🆕 新建 | 包入口 |
| `tests/test_topic_tree.py` | 🆕 新建 | 话题树单元测试 |
| `tests/test_topic_tree_pcr.py` | 🆕 新建 | 话题树 + PCR 集成测试 |
| `tests/test_topic_tree_persistence.py` | 🆕 新建 | 持久化测试 |
| `service/stores/async_sqlite.py` | 📝 修改 | 增加 `topic_nodes` / `topic_edges` 表 |
| `service/session_persistence.py` | 📝 修改 | 集成 `TopicTreeManager` |
| `intent_trace_cli.py` | 📝 修改 | 添加 `--enable-topic-tree` 参数 |
| `observability/logger.py` | 📝 修改 | `DecisionLogEntry` 增加话题字段 |
| `observability/metrics.py` | 📝 修改 | 仪表盘增加话题统计 |

---

## 与现有设计文档的关系

```
┌─────────────────────────────────────────────────────────────┐
│  设计文档体系                                                │
│  ─────────────────────────────────────────────────────────  │
│  design_persistence.md          — 会话持久化（SQLite）        │
│  design_context_window.md       — 上下文窗口管理（热/温/冷）  │
│  design_observability.md        — 可观测性（日志/指标/告警）  │
│  design_topic_tree.md           — 话题树（本文档）            │
│  ─────────────────────────────────────────────────────────  │
│  依赖关系：                                                  │
│  topic_tree → persistence     （话题树需要会话持久化）       │
│  topic_tree → context_window  （话题过滤后传给窗口压缩）     │
│  topic_tree → observability   （话题切换事件需要记录）       │
│  topic_tree → pcr             （通过 PCRInput_v1 注入）      │
└─────────────────────────────────────────────────────────────┘
```
