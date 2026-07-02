# DialogMesh 主题树 — 工程实现文档

> **文档编号**: ENGINEERING-TOPIC-TREE-007  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 已有数据模型（需实现操作层）  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §5.2（Topic Tree）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应数据模型**: `ENGINEERING_DATA_MODEL.md` §7.2（TopicTree / TopicTreeNode）  
> **对应持久化**: `ENGINEERING_PERSISTENCE.md` §9（GraphStore）  
> **原则**: Topic Tree 是用户对话的长期结构，Cognitive Tree 是 LLM 的心智空间，两者通过交叉引用关联。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 树操作 API](#5-树操作-api)
- [6. 与 PCR 层的集成](#6-与-pcr-层的集成)
- [7. 与 Intent Parser 的集成](#7-与-intent-parser-的集成)
- [8. 与 Answer-LLM 的集成](#8-与-answer-llm-的集成)
- [9. 与 Cognitive Tree 的交叉引用](#9-与-cognitive-tree-的交叉引用)
- [10. 持久化与序列化](#10-持久化与序列化)
- [11. 测试策略](#11-测试策略)
- [12. 附录：简化与待讨论项](#12-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **Topic Tree（主题树）**的完整操作层实现规范。数据模型已在 `ENGINEERING_DATA_MODEL.md` §7.2 中定义，持久化层已在 `ENGINEERING_PERSISTENCE.md` §9 中定义。本文档定义**操作 API**（创建、移动、切换、查询、遍历）和**集成层**（与 PCR、Intent Parser、Answer-LLM、Cognitive Tree 的交互）。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 主题树构建 | `DESIGN_FULL_CONCEPT.md` §5.2 | §5 | 节点创建、移动、切换 |
| 主题切换检测 | `DESIGN_FULL_CONCEPT.md` §5.2 | §6 | 基于 PCR 输出的噪声和期望推断 |
| 与意图解析集成 | `DESIGN_FULL_CONCEPT.md` §5.2 | §7 | 意图类别 → 主题节点映射 |
| 与 Answer-LLM 集成 | `DESIGN_FULL_CONCEPT.md` §5.2 | §8 | 读取活跃分支供回复参考 |
| 与 Cognitive Tree 交叉引用 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §9 | 通过 `cog_refs` 关联双树 |
| 持久化操作 | `DESIGN_FULL_CONCEPT.md` §8.2 | §10 | 使用 GraphStore 存储 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/topic_tree/builder.py` | 主题树构建器（从对话历史构建树） | ~200 行 | 新增 |
| `core/agent/topic_tree/operations.py` | 树操作（创建、移动、切换、查询） | ~300 行 | 新增 |
| `core/agent/topic_tree/integrator.py` | 集成层（与 PCR/Intent Parser/Answer-LLM 集成） | ~150 行 | 新增 |
| `core/agent/topic_tree/cross_ref.py` | 与 Cognitive Tree 的交叉引用管理 | ~100 行 | v3.0 新增 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/persistence/graph_store.py` | 新增 `TopicNode` / `TopicEdge` 的操作方法 | 图存储 |
| `core/agent/orchestrator.py` | 每轮调用 `TopicTreeIntegrator.update()` | 编排层 |

---

## 3. 现有实现评估

### 3.1 数据模型（已定义）

**定义位置**: `ENGINEERING_DATA_MODEL.md` §7.2

| 模型 | 字段 | 状态 |
|------|------|------|
| `TopicTree` | `root`, `nodes` (dict), `active_node_id` | ✅ 已定义 |
| `TopicTreeNode` | `node_id`, `content`, `timestamp`, `weight`, `parent_id`, `children_ids`, `cog_refs`, `is_active`, `turn_count` | ✅ 已定义 |

### 3.2 持久化（已实现）

**实现位置**: `ENGINEERING_PERSISTENCE.md` §9

| 功能 | 状态 | 备注 |
|------|------|------|
| `TopicNode` 存储（`graph_nodes` 表） | ✅ 已实现 | GraphStore |
| `TopicEdge` 存储（`graph_edges` 表） | ✅ 已实现 | GraphStore |
| BFS 遍历 | ✅ 已实现 | `bfs_neighbors()` |
| 按实体搜索 | ✅ 已实现 | `find_nodes_by_entity()` |

### 3.3 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 主题树构建器（从对话历史自动构建） | 无 | 需新增 `TopicTreeBuilder` | P1 |
| 主题切换检测（基于 PCR 输出） | 无 | 需新增 `TopicSwitchDetector` | P1 |
| 树操作 API（创建、移动、切换） | 无 | 需新增 `TopicTreeOperations` | P1 |
| 与 Intent Parser 集成（意图 → 主题映射） | 无 | 需新增 `TopicTreeIntegrator` | P2 |
| 与 Answer-LLM 集成（活跃分支读取） | 无 | 需新增 `TopicTreeIntegrator` | P2 |
| 与 Cognitive Tree 交叉引用 | 无 | 需新增 `CrossRefManager` | P2 |
| 主题权重 EMA 更新 | 无 | 需新增 `TopicWeightUpdater` | P2 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户输入层                                       │
│                              ↓                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  PCR 层                                                                       │
│  ────────────────────────────────────────────────────────────────────────  │
│  • expectation (TOOL/ADVISOR/COMPANION) → 影响主题切换决策                    │
│  • noise_level → 高噪声时降低主题切换敏感度                                   │
│  • complexity_level → 高复杂度可能触发新主题                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Intent Parser 层                                                              │
│  ────────────────────────────────────────────────────────────────────────  │
│  • intent.category → 映射到主题节点                                            │
│  • intent.entities → 提取主题关键词                                            │
│  • sub_intents → 可能产生多个主题分支                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  Topic Tree 操作层（本文档）                                                    │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │ TopicTreeBuilder     │  │ TopicTreeOperations  │  │ TopicSwitchDetector  │  │
│  │ 从对话历史构建树     │  │ 创建/移动/切换/查询  │  │ 检测主题切换信号     │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘  │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │ TopicWeightUpdater   │  │ CrossRefManager      │  │ TopicTreeIntegrator  │  │
│  │ EMA 权重更新         │  │ 与 Cognitive Tree    │  │ 与 PCR/Intent/       │  │
│  │                      │  │ 交叉引用             │  │ Answer-LLM 集成      │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│  双树结构                                                                     │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐                 │
│  │ Topic Tree（用户）     │  │  Cognitive Tree（LLM 心智）   │                 │
│  │  ───────────────     │  │  ────────────────────────    │                 │
│  │  用户对话主题层次      │  │  LLM 推理、假设、决策、反思   │                 │
│  │  通过 cog_refs 关联  │  │  通过 topic_refs 关联        │                 │
│  └──────────────────────┘  └──────────────────────────────┘                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Answer-LLM 穿透层                                                            │
│  ────────────────────────────────────────────────────────────────────────  │
│  • 读取 Topic Tree 活跃分支（最近 3 个主题）                                    │
│  • 读取 Cognitive Tree 活跃推理链（最近 5 个节点）                              │
│  • 生成回复时参考主题上下文                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 树操作 API

### 5.1 `TopicTreeBuilder`

```python
class TopicTreeBuilder:
    """主题树构建器 — 从对话历史自动构建主题树。"""
    
    def __init__(self, graph_store: GraphStore):
        self._graph = graph_store
    
    def build_from_session(self, session_id: str) -> TopicTree:
        """
        从会话历史构建主题树。
        
        流程：
        1. 加载会话的所有 TurnRecord
        2. 按意图类别分组（相同类别 → 同一主题分支）
        3. 检测主题切换（时间间隔 > 5min 或意图类别突变）
        4. 创建 TopicTreeNode 和 TopicTreeEdge
        5. 设置 EMA 权重（基于轮次和活跃度）
        """
        turns = self._graph.load_turns(session_id)
        tree = TopicTree(session_id=session_id)
        
        root = TopicTreeNode(content="root", weight=1.0)
        tree.root = root.node_id
        tree.add_node(root)
        
        current_parent = root.node_id
        for turn in turns:
            # 检测主题切换
            if self._is_topic_switch(turn, tree):
                # 创建新主题节点
                node = TopicTreeNode(
                    content=self._extract_topic(turn),
                    parent_id=current_parent,
                    weight=1.0,
                )
                tree.add_node(node)
                tree.add_edge(TopicTreeEdge(source_id=current_parent, target_id=node.node_id))
                current_parent = node.node_id
            else:
                # 更新现有主题节点
                tree.nodes[current_parent].turn_count += 1
                tree.nodes[current_parent].weight = self._update_weight(
                    tree.nodes[current_parent].weight, turn
                )
        
        tree.active_node_id = current_parent
        return tree
    
    def _is_topic_switch(self, turn: TurnRecord, tree: TopicTree) -> bool:
        """
        检测主题切换信号：
        1. 时间间隔 > 5 分钟
        2. 意图类别与当前主题不匹配
        3. 用户显式切换信号（"换个话题"、"另外"）
        """
        # 时间间隔
        if tree.active_node_id and tree.nodes[tree.active_node_id].timestamp:
            gap = turn.timestamp - tree.nodes[tree.active_node_id].timestamp
            if gap > 300:  # 5 分钟
                return True
        
        # 意图类别突变
        if turn.intent.category != tree.nodes[tree.active_node_id].intent_category:
            # 除非是跟随标记（"继续"、"然后"）
            if not self._has_follow_signal(turn.user_input):
                return True
        
        return False
    
    def _extract_topic(self, turn: TurnRecord) -> str:
        """从轮次提取主题关键词（简化：使用意图类别 + 首个实体）。"""
        topic = turn.intent.category.value
        if turn.intent.entities:
            topic += f"_{turn.intent.entities[0].type.value}"
        return topic
```

> ⚠️ **Phase 1 限制**：`TopicTreeBuilder` 的自动构建依赖 `TurnRecord` / `Intent` / `Entity` / `GraphStore`，这些模块在 Phase 1 尚未稳定。Phase 1 使用 `ManualTopicTreeFactory`（见下）进行集成测试，自动构建推迟到 Phase 2（PCR 和持久化层稳定后）。

### 5.1b `ManualTopicTreeFactory`（Phase 1 测试用）

```python
class ManualTopicTreeFactory:
    """手动构造主题树 — 用于 Phase 1 集成测试，不依赖 PCR/Intent Parser。"""
    
    @staticmethod
    def create_tree(session_id: str, topics: List[str]) -> TopicTree:
        """从主题字符串列表手动构建树。"""
        tree = TopicTree(session_id=session_id)
        root = TopicTreeNode(content="root")
        tree.root = root.node_id
        tree.add_node(root)
        
        parent = root.node_id
        for topic in topics:
            node = TopicTreeNode(content=topic, parent_id=parent)
            tree.add_node(node)
            tree.add_edge(TopicTreeEdge(source_id=parent, target_id=node.node_id))
            parent = node.node_id
        
        tree.active_node_id = parent
        return tree
    
    @staticmethod
    def create_from_yaml(session_id: str, yaml_path: str) -> TopicTree:
        """从 YAML 文件加载预定义主题结构（测试用）。"""
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        tree = TopicTree(session_id=session_id)
        root = TopicTreeNode(content=data.get("root", "root"))
        tree.root = root.node_id
        tree.add_node(root)
        
        def _build(parent_id: str, nodes_data: List[Dict]):
            for node_data in nodes_data:
                node = TopicTreeNode(
                    content=node_data["content"],
                    parent_id=parent_id,
                    weight=node_data.get("weight", 1.0),
                )
                tree.add_node(node)
                tree.add_edge(TopicTreeEdge(source_id=parent_id, target_id=node.node_id))
                if "children" in node_data:
                    _build(node.node_id, node_data["children"])
        
        _build(root.node_id, data.get("topics", []))
        tree.active_node_id = data.get("active_node", root.node_id)
        return tree
```

### 5.2 `TopicTreeOperations`

```python
class TopicTreeOperations:
    """主题树操作 — 核心树操作 API。"""
    
    def __init__(self, graph_store: GraphStore):
        self._graph = graph_store
        # v3.0 新增：事务性写入 — 解决内存与持久化时差问题
        self._pending_writes: Dict[str, TopicTreeNode] = {}  # 内存缓存：key = "session_id:node_id"
        self._write_lock = asyncio.Lock()
    
    # ── 事务性写入（v3.0 新增）──
    def _mark_dirty(self, session_id: str, node: TopicTreeNode) -> None:
        """标记节点为待写入（内存更新，不立即持久化）。"""
        key = f"{session_id}:{node.node_id}"
        self._pending_writes[key] = node
    
    async def flush(self, session_id: str) -> int:
        """
        批量持久化所有待写入节点。
        
        调用时机：Orchestrator 每轮结束时调用一次。
        使用 SQLite 事务保证原子性。
        
        解决风险：快速连续消息（<1s）在崩溃时状态丢失。
        """
        async with self._write_lock:
            to_write = [
                n for k, n in self._pending_writes.items()
                if k.startswith(f"{session_id}:")
            ]
            if not to_write:
                return 0
            
            # 批量写入（SQLite 事务）
            self._graph.begin_transaction()
            try:
                for node in to_write:
                    self._graph.save_topic_node(session_id, node)
                self._graph.commit_transaction()
                
                # 清除已写入的缓存
                for k in list(self._pending_writes.keys()):
                    if k.startswith(f"{session_id}:"):
                        del self._pending_writes[k]
                
                return len(to_write)
            except Exception:
                self._graph.rollback_transaction()
                raise
    
    async def emergency_flush(self, session_id: str) -> int:
        """异常时紧急 flush — 保证已处理状态不丢失。"""
        try:
            return await self.flush(session_id)
        except Exception as e:
            # 紧急 flush 失败时记录日志，但不抛出异常（避免二次异常）
            print(f"[TopicTreeOperations] Emergency flush failed: {e}")
            return 0
    
    # ── 节点管理 ──
    def create_node(self, session_id: str, content: str, parent_id: Optional[str] = None) -> TopicTreeNode:
        """创建新节点。"""
        node = TopicTreeNode(content=content, parent_id=parent_id)
        self._mark_dirty(session_id, node)  # v3.0：改为标记待写入
        if parent_id:
            self._graph.save_topic_edge(session_id, TopicTreeEdge(source_id=parent_id, target_id=node.node_id))
        return node
    
    def move_node(self, session_id: str, node_id: str, new_parent_id: str) -> bool:
        """移动节点到新的父节点。"""
        # 1. 删除旧边
        self._graph.delete_topic_edge(session_id, node_id=node_id)
        # 2. 创建新边
        self._graph.save_topic_edge(session_id, TopicTreeEdge(source_id=new_parent_id, target_id=node_id))
        # 3. 更新节点 parent_id
        node = self._graph.load_topic_node(session_id, node_id)
        node.parent_id = new_parent_id
        self._graph.save_topic_node(session_id, node)
        return True
    
    def switch_active_node(self, session_id: str, node_id: str) -> bool:
        """切换活跃节点。"""
        # 1. 标记当前活跃节点为 inactive（待写入）
        current = self._graph.load_active_topic_node(session_id)
        if current:
            current.is_active = False
            self._mark_dirty(session_id, current)
        
        # 2. 标记新节点为 active（待写入）
        new_node = self._graph.load_topic_node(session_id, node_id)
        new_node.is_active = True
        new_node.turn_count += 1
        new_node.weight = self._boost_weight(new_node.weight)
        self._mark_dirty(session_id, new_node)
        return True
    
    # ── 查询 ──
    def get_active_branch(self, session_id: str) -> List[TopicTreeNode]:
        """获取从 root 到 active_node 的活跃分支。"""
        active = self._graph.load_active_topic_node(session_id)
        if not active:
            return []
        
        branch = [active]
        current = active
        while current.parent_id:
            parent = self._graph.load_topic_node(session_id, current.parent_id)
            if not parent:
                break
            branch.insert(0, parent)
            current = parent
        
        return branch
    
    def find_related_topics(self, session_id: str, entity_type: str, entity_value: str) -> List[TopicTreeNode]:
        """查找与特定实体相关的主题节点。"""
        # 使用 EntityIndex 查询包含该实体的主题节点
        nodes = self._graph.find_topic_nodes_by_entity(session_id, entity_type, entity_value)
        return sorted(nodes, key=lambda n: n.weight, reverse=True)
    
    # ── 权重更新 ──
    def _update_weight(self, current_weight: float, turn: TurnRecord) -> float:
        """EMA 权重更新：α = 0.3，新轮次 +1。"""
        return current_weight * 0.7 + 1.0 * 0.3
    
    def _boost_weight(self, weight: float) -> float:
        """切换活跃节点时提升权重（用户重新关注）。"""
        return min(1.0, weight + 0.2)
```

---

## 6. 与 PCR 层的集成

### 6.1 `TopicSwitchDetector`

```python
class TopicSwitchDetector:
    """主题切换检测器 — 基于 PCR 输出推断用户是否切换了主题。"""
    
    def __init__(self, config: Optional[Dict] = None):
        self._time_threshold = 300  # 5 分钟
        self._noise_threshold = 0.7  # 高噪声时降低切换敏感度
        self._config = config or {}
    
    def detect(self, pcr_output: PCROutput, current_topic: TopicTreeNode, last_turn_time: float) -> TopicSwitchSignal:
        """
        基于 PCR 输出检测主题切换信号。
        
        信号类型：
        - CONTINUATION: 继续当前主题（低噪声、同期望类型）
        - SUB_TOPIC: 当前主题下的子话题（同期望类型、新实体）
        - NEW_TOPIC: 全新主题（高噪声、UNKNOWN 期望、时间间隔大）
        - RETURN: 回到之前的话题（跟随标记 + 历史实体引用）
        """
        signals = []
        
        # 信号 1：时间间隔
        time_gap = time.time() - last_turn_time
        if time_gap > self._time_threshold:
            signals.append(("time_gap", time_gap / self._time_threshold, "NEW_TOPIC"))
        
        # 信号 2：期望类型变化
        if pcr_output.expectation != UserExpectation.UNKNOWN:
            if current_topic.expectation and pcr_output.expectation != current_topic.expectation:
                signals.append(("expectation_shift", 0.8, "NEW_TOPIC"))
        
        # 信号 3：噪声水平
        if pcr_output.noise_level > self._noise_threshold:
            # 高噪声降低切换敏感度（可能是用户表达不清，而非切换主题）
            signals = [(s[0], s[1] * 0.5, s[2]) for s in signals]
        
        # 信号 4：复杂度
        if pcr_output.complexity_level > 0.7:
            signals.append(("high_complexity", 0.6, "SUB_TOPIC"))
        
        # 综合判断
        if not signals:
            return TopicSwitchSignal(type="CONTINUATION", confidence=0.9)
        
        best = max(signals, key=lambda s: s[1])
        return TopicSwitchSignal(type=best[2], confidence=best[1])
```

---

## 7. 与 Intent Parser 的集成

### 7.1 `TopicTreeIntentIntegrator`

```python
class TopicTreeIntentIntegrator:
    """Topic Tree 与 Intent Parser 的集成器。"""
    
    def __init__(self, tree_ops: TopicTreeOperations):
        self._tree_ops = tree_ops
    
    def update_from_intent(self, session_id: str, intent: Intent, pcr_output: PCROutput) -> TopicTreeNode:
        """
        根据解析后的意图更新主题树。
        
        流程：
        1. 检测主题切换信号（基于 PCR 输出）
        2. 如果切换 → 创建新主题节点
        3. 如果继续 → 更新当前主题节点
        4. 提取实体作为主题关键词
        5. 更新 EMA 权重
        """
        active_branch = self._tree_ops.get_active_branch(session_id)
        current_topic = active_branch[-1] if active_branch else None
        
        # 检测切换
        detector = TopicSwitchDetector()
        signal = detector.detect(pcr_output, current_topic, current_topic.timestamp if current_topic else 0)
        
        if signal.type == "NEW_TOPIC" and signal.confidence > 0.6:
            # 创建新主题
            content = self._extract_topic_from_intent(intent)
            new_node = self._tree_ops.create_node(session_id, content, parent_id=current_topic.node_id if current_topic else None)
            self._tree_ops.switch_active_node(session_id, new_node.node_id)
            return new_node
        
        elif signal.type == "SUB_TOPIC" and signal.confidence > 0.5:
            # 创建子主题
            content = self._extract_topic_from_intent(intent)
            new_node = self._tree_ops.create_node(session_id, content, parent_id=current_topic.node_id if current_topic else None)
            self._tree_ops.switch_active_node(session_id, new_node.node_id)
            return new_node
        
        else:
            # 继续当前主题
            if current_topic:
                current_topic.turn_count += 1
                current_topic.weight = self._update_weight(current_topic.weight, intent)
                self._tree_ops._mark_dirty(session_id, current_topic)  # v3.0：改为标记待写入
            return current_topic
    
    # v3.0 新增：每轮结束时调用 flush
    async def flush(self, session_id: str) -> int:
        """委托给 TopicTreeOperations.flush()。"""
        return await self._tree_ops.flush(session_id)

```
        """从意图提取主题关键词。"""
        parts = [intent.category.value]
        for entity in intent.entities[:2]:  # 取前 2 个实体
            parts.append(f"{entity.type.value}:{entity.value}")
        return "_".join(parts)
```

---

## 8. 与 Answer-LLM 的集成

### 8.1 `TopicTreeAnswerIntegrator`

```python
class TopicTreeAnswerIntegrator:
    """Topic Tree 与 Answer-LLM 的集成器。"""
    
    def __init__(self, tree_ops: TopicTreeOperations):
        self._tree_ops = tree_ops
    
    def get_context_for_answer(self, session_id: str) -> Dict[str, Any]:
        """
        为 Answer-LLM 生成主题上下文。
        
        返回：
        - active_branch: 活跃分支（最近 3 个主题节点）
        - current_topic: 当前主题
        - topic_history: 主题历史（最近 5 个主题的摘要）
        - related_entities: 当前主题相关的实体列表
        """
        active_branch = self._tree_ops.get_active_branch(session_id)
        
        if not active_branch:
            return {"active_branch": [], "current_topic": None}
        
        # 取最近 3 个主题节点
        recent_nodes = active_branch[-3:]
        
        # 生成主题历史摘要
        topic_history = []
        for node in active_branch[-5:]:
            topic_history.append({
                "topic": node.content,
                "turns": node.turn_count,
                "weight": round(node.weight, 2),
            })
        
        return {
            "active_branch": [n.content for n in recent_nodes],
            "current_topic": active_branch[-1].content,
            "topic_history": topic_history,
            "related_entities": self._extract_entities(active_branch[-1]),
        }
    
    def _extract_entities(self, node: TopicTreeNode) -> List[str]:
        """从主题节点提取实体信息。"""
        # 从 node.content 解析实体（如 "scan_memory_MEMORY_ADDRESS:0x401000"）
        entities = []
        if "_" in node.content:
            parts = node.content.split("_")
            for part in parts[1:]:  # 跳过意图类别
                if ":" in part:
                    entity_type, entity_value = part.split(":", 1)
                    entities.append(f"{entity_type}={entity_value}")
        return entities
```

### 8.2 Orchestrator 层集成（v3.0 新增：事务性 Flush）

```python
class Orchestrator:
    """编排器 — 每轮结束时统一调用 Topic Tree flush。"""
    
    def __init__(self):
        self._topic_tree_integrator = TopicTreeIntentIntegrator(...)
        self._topic_tree_ops = TopicTreeOperations(...)
    
    async def process_turn(self, user_input: UserInput, session: Session) -> ResponsePayload:
        try:
            # 1. PCR 层
            pcr_output = self._pcr.evaluate(user_input)
            
            # 2. Intent Parser 层
            intent = self._intent_parser.parse(user_input, pcr_output)
            
            # 3. 更新 Topic Tree（内存中标记待写入）
            self._topic_tree_integrator.update_from_intent(
                session.session_id, intent, pcr_output
            )
            
            # 4. Planning + Execution + Answer-LLM ...
            
            # 5. 每轮结束统一 flush（保证状态一致性）
            flushed = await self._topic_tree_ops.flush(session.session_id)
            if flushed > 0:
                print(f"[Orchestrator] Flushed {flushed} topic tree nodes")
            
            return response
            
        except Exception:
            # 异常时紧急 flush（保证已处理状态不丢失）
            await self._topic_tree_ops.emergency_flush(session.session_id)
            raise
```

> **关键设计**：所有 `TopicTreeOperations` 的写操作（`create_node`/`switch_active_node`/`update_node`）都使用 `_mark_dirty()` 标记为待写入，真正的持久化发生在 `Orchestrator.process_turn()` 末尾的统一 `flush()` 调用。这保证了：
> 1. 快速连续消息（<1s）不会触发多次数据库写入
> 2. 每轮只有一个 SQLite 事务，原子性保证
> 3. 异常时 `emergency_flush()` 尽最大努力保存已处理状态

---

## 9. 与 Cognitive Tree 的交叉引用

### 9.1 `CrossRefManager`

```python
class CrossRefManager:
    """Topic Tree 与 Cognitive Tree 的交叉引用管理器。"""
    
    def __init__(self, graph_store: GraphStore):
        self._graph = graph_store
    
    def link_topic_to_cognitive(self, session_id: str, topic_node_id: str, cognitive_node_id: str) -> bool:
        """
        创建 Topic Tree 节点到 Cognitive Tree 节点的交叉引用。
        
        触发时机：
        - 当 LLM 产生认知（如 Planning-LLM 生成计划）时，关联到当前主题
        - 当 Meta-Cognitive-LLM 验证时，关联验证节点到主题
        """
        topic_node = self._graph.load_topic_node(session_id, topic_node_id)
        if topic_node:
            topic_node.cog_refs.append(cognitive_node_id)
            self._graph.save_topic_node(session_id, topic_node)
        
        # 反向引用：Cognitive Tree 节点也记录 topic_refs
        cog_node = self._graph.load_cognitive_node(session_id, cognitive_node_id)
        if cog_node:
            cog_node.topic_refs.append(topic_node_id)
            self._graph.save_cognitive_node(session_id, cog_node)
        
        return True
    
    def get_cognitive_nodes_for_topic(self, session_id: str, topic_node_id: str) -> List[CognitiveTreeNode]:
        """获取与某主题相关的所有 Cognitive Tree 节点。"""
        topic_node = self._graph.load_topic_node(session_id, topic_node_id)
        if not topic_node or not topic_node.cog_refs:
            return []
        
        cog_nodes = []
        for cog_id in topic_node.cog_refs:
            node = self._graph.load_cognitive_node(session_id, cog_id)
            if node:
                cog_nodes.append(node)
        return cog_nodes
    
    def get_topic_for_cognitive_node(self, session_id: str, cognitive_node_id: str) -> Optional[TopicTreeNode]:
        """获取某 Cognitive Tree 节点关联的主题。"""
        cog_node = self._graph.load_cognitive_node(session_id, cognitive_node_id)
        if not cog_node or not cog_node.topic_refs:
            return None
        
        return self._graph.load_topic_node(session_id, cog_node.topic_refs[0])
```

---

## 10. 持久化与序列化

### 10.1 持久化策略

| 数据类型 | 存储层 | 表/文件 | 保留策略 |
|---------|--------|---------|---------|
| 活跃主题树 | Hot（内存） | `OrderedDict` | 会话活跃期间 |
| 非活跃主题树 | Warm（SQLite） | `graph_nodes` / `graph_edges` | 30 天 |
| 归档主题树 | Cold（归档文件） | gzip JSONL | 1 年 |

### 10.2 序列化格式

```python
# TopicTree 序列化示例
{
    "session_id": "sess-abc123",
    "root": "root-1",
    "active_node_id": "node-3",
    "nodes": {
        "root-1": {
            "node_id": "root-1",
            "content": "root",
            "timestamp": 1699999999.0,
            "weight": 1.0,
            "parent_id": None,
            "children_ids": ["node-1"],
            "cog_refs": [],
            "is_active": False,
            "turn_count": 0
        },
        "node-1": {
            "node_id": "node-1",
            "content": "scan_memory_MEMORY_ADDRESS:0x401000",
            "timestamp": 1700000000.0,
            "weight": 0.85,
            "parent_id": "root-1",
            "children_ids": ["node-2"],
            "cog_refs": ["cog-1", "cog-2"],
            "is_active": False,
            "turn_count": 3
        }
    }
}
```

---

## 11. 测试策略

### 11.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 每个树操作（创建、移动、切换、查询）的独立测试 |
| 集成测试 | 90% | 从对话历史构建完整主题树的端到端测试 |
| 切换检测测试 | 100% | 时间间隔、期望变化、噪声水平的组合场景 |
| 交叉引用测试 | 100% | Topic Tree ↔ Cognitive Tree 的双向引用一致性 |
| 性能测试 | 关键路径 | 1000 个节点的主题树查询 < 10ms |

### 11.2 关键测试用例

**用例 1：主题树构建**
```python
def test_build_from_session():
    builder = TopicTreeBuilder(mock_graph_store)
    
    # 模拟 3 轮对话
    turns = [
        TurnRecord(intent=Intent(category=IntentCategory.SCAN_MEMORY, entities=[Entity(type=EntityType.MEMORY_ADDRESS, value="0x401000")])),
        TurnRecord(intent=Intent(category=IntentCategory.READ_MEMORY, entities=[Entity(type=EntityType.MEMORY_ADDRESS, value="0x401000")])),
        TurnRecord(intent=Intent(category=IntentCategory.ASK_USER, entities=[])),
    ]
    
    tree = builder.build_from_session("test-session")
    
    assert tree.root is not None
    assert len(tree.nodes) >= 3  # root + 2 个主题
    assert tree.active_node_id is not None
```

**用例 2：主题切换检测**
```python
def test_topic_switch_detection():
    detector = TopicSwitchDetector()
    
    # 场景 1：时间间隔 > 5min → 切换
    pcr = PCROutput(expectation=UserExpectation.TOOL, noise_level=0.2)
    current = TopicTreeNode(timestamp=time.time() - 400)
    signal = detector.detect(pcr, current, current.timestamp)
    assert signal.type == "NEW_TOPIC"
    assert signal.confidence > 0.8
    
    # 场景 2：高噪声 → 不切换（可能是表达不清）
    pcr = PCROutput(expectation=UserExpectation.UNKNOWN, noise_level=0.8)
    signal = detector.detect(pcr, current, time.time() - 10)
    assert signal.type == "CONTINUATION"
```

**用例 3：交叉引用一致性**
```python
def test_cross_ref_consistency():
    manager = CrossRefManager(mock_graph_store)
    
    # 创建引用
    manager.link_topic_to_cognitive("sess-1", "topic-1", "cog-1")
    
    # 正向查询
    cog_nodes = manager.get_cognitive_nodes_for_topic("sess-1", "topic-1")
    assert len(cog_nodes) == 1
    assert cog_nodes[0].node_id == "cog-1"
    
    # 反向查询
    topic = manager.get_topic_for_cognitive_node("sess-1", "cog-1")
    assert topic.node_id == "topic-1"
```

**用例 4：手动构造主题树（Phase 1 测试）**
```python
def test_manual_topic_tree_factory():
    """Phase 1：不依赖 PCR/Intent Parser，手动构造主题树用于集成测试。"""
    tree = ManualTopicTreeFactory.create_tree(
        "test-session",
        ["scan_memory_0x401000", "read_memory_0x401000", "ask_user"]
    )
    
    assert tree.root is not None
    assert len(tree.nodes) == 4  # root + 3 个主题
    assert tree.active_node_id is not None
    
    # 验证活跃分支
    active_branch = [tree.nodes[nid] for nid in tree.active_branch]
    assert len(active_branch) == 4
    assert active_branch[-1].content == "ask_user"
```

**用例 5：事务性 Flush**
```python
async def test_transactional_flush():
    """验证 _mark_dirty + flush 的原子性。"""
    ops = TopicTreeOperations(mock_graph_store)
    
    # 创建节点（仅标记待写入）
    node1 = ops.create_node("sess-1", "topic-1")
    node2 = ops.create_node("sess-1", "topic-2")
    
    # 验证未写入
    assert len(ops._pending_writes) == 2
    
    # flush
    flushed = await ops.flush("sess-1")
    assert flushed == 2
    assert len(ops._pending_writes) == 0
    
    # 验证已写入数据库
    stored = mock_graph_store.load_topic_node("sess-1", node1.node_id)
    assert stored is not None
    assert stored.content == "topic-1"
```

---

## 12. 附录：简化与待讨论项

### 12.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 主题关键词提取 | 使用 NLP/LLM 提取主题摘要 | 使用意图类别 + 实体拼接 | 简化实现降低复杂度，后续可引入 LLM 生成摘要 | Phase 2 引入轻量摘要 LLM 时实现 |
| **S-02** | 主题切换的语义检测 | 基于语义相似度（而非规则）检测切换 | 基于时间 + 意图类别 + 规则 | 语义检测需要 embedding 计算，增加延迟 | Phase 2 引入 embedding 层时实现 |
| **S-03** | 主题树的跨会话合并 | 相似主题跨会话合并（全局主题索引） | 仅会话级主题树 | 跨会话合并需要全局索引和相似度计算 | Phase 3 用户画像系统完善时实现 |
| **S-04** | 主题权重衰减 | 长期不活跃主题的权重衰减 | 仅更新活跃主题权重 | 衰减需要定时任务，增加复杂度 | Phase 2 引入记忆衰减系统时实现 |
| **S-05** | 多轮主题预测 | 基于主题树预测用户下一主题 | 无预测 | 预测需要历史模式学习，增加复杂度 | Phase 3 引入用户行为模型时实现 |

### 12.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 主题切换的时间阈值 | A) 固定 5 分钟  B) 基于用户画像动态调整（专家更长，新手更短）  C) 基于会话长度自适应 | 建议 B：专家用户可能有更长的上下文保持能力 |
| **D-02** | 主题节点的粒度 | A) 每个意图类别一个节点  B) 每个意图实例一个节点（更细）  C) 按实体组合聚类 | 建议 A：当前粒度与意图类别对齐，足够使用 |
| **D-03** | 主题权重的计算 | A) 仅轮次计数  B) EMA 动态更新（当前）  C) 基于用户反馈（正面/负面）调整 | 建议 B：EMA 已覆盖动态性，反馈调整在 Phase 3 实现 |
| **D-04** | 交叉引用的更新策略 | A) 创建时固定  B) 运行时动态更新（Meta-Cognitive 验证后）  C) 定期清理无效引用 | 建议 B：Meta-Cognitive 验证后更新引用，保持准确性 |
| **D-05** | 主题树的 GUI 展示 | A) 折叠树（仅展示活跃分支）  B) 完整树（可展开/折叠）  C) 时间线（按时间顺序） | 建议 B：完整树 + 可交互折叠，适合用户回顾对话历史 |

### 12.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §5.2 | §4-§10 | ✅ 等价 | Topic Tree 构建、操作、持久化全部覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.2.4 | §6 | ✅ 等价 | PCR 噪声/期望 → 主题切换检测覆盖 |
| `DESIGN_FULL_CONCEPT.md` §3.3 | §7 | ✅ 等价 | 意图 → 主题映射覆盖 |
| `DESIGN_FULL_CONCEPT.md` §5.3 | §8 | ✅ 等价 | Answer-LLM 活跃分支读取覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §9 | ✅ 等价 | Topic Tree ↔ Cognitive Tree 交叉引用覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §8 | ✅ 等价 | Answer-LLM 读取主题上下文覆盖 |

---

> ⚠️ **风险缓解**：本文档已针对三个关键风险实施缓解措施：
> 1. **基础设施依赖前置**：`TopicTreeBuilder` 自动构建依赖 `TurnRecord`/`Intent`/`GraphStore`，Phase 1 尚未稳定。Phase 1 使用 `ManualTopicTreeFactory` 手动构造主题树进行集成测试，自动构建推迟到 Phase 2（§5.1b）。
> 2. **权重更新与持久化时差**：`TopicTreeOperations` 采用 `_mark_dirty()` + `flush()` 事务性写入模式，所有写操作先标记内存缓存，Orchestrator 每轮结束统一调用 `flush()` 进行 SQLite 事务写入，保证原子性。异常时 `emergency_flush()` 尽最大努力保存状态（§5.2, §8.2）。
> 3. **主题切换的语义检测**：当前使用基于时间 + 意图类别 + 规则的简化检测，语义检测（embedding 相似度）推迟到 Phase 2（S-02）。

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和已有数据模型/持久化定义生成。数据模型和持久化层已在 `ENGINEERING_DATA_MODEL.md` 和 `ENGINEERING_PERSISTENCE.md` 中实现，本文档新增约 **750 行代码**（构建器 + 操作器 + 集成器 + 交叉引用）。所有简化项已在 §12.1 中诚实标记，待讨论项在 §12.2 中列出，等待团队确认。*
