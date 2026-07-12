# DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md

> 版本: v1.0 | 日期: 2026-07-12
>
> 对话树是内存态的刚性结构（树），持久化层是灵活结构（图）。
> 本模块定义"修正网关"——在持久化时做重分类 + 结构校验，
> 确保从图加载回来的数据永远是已修正版本。

---

## 目录

1. [问题：树刚性 vs 分类器进化](#1-问题树刚性-vs-分类器进化)
2. [方案：修正网关 + 标注索引](#2-方案修正网关-标注索引)
3. [DialogueTreePersistenceAdapter](#3-dialoguetreepersistenceadapter)
4. [NodeAnnotationStore](#4-nodeannotationstore)
5. [Schema 定义](#5-schema-定义)
6. [集成面：与已有 v4 模块的关系](#6-集成面与已有-v4-模块的关系)
7. [实现计划](#7-实现计划)

---

## 1. 问题：树刚性 vs 分类器进化

### 1.1 时序问题

```
Session 1:
  T1: 分类器 v1 不认识 "add_monitoring"
      → 对话树节点 N23 被标注为 action: "ask"
  T2: LLM 介入 → 分类器 v2 认识 "add_monitoring"
      → 但 N23 的标注仍然是 "ask"（树节点不可原地修改）
  T3: Session 结束 → 树被释放

Session 2:
  T4: 从图加载 N23 → action 仍然是 "ask"（如果未经修正存储）
```

**根本矛盾**：分类器可以进化（TieredActionResolver 的反馈闭环），但树节点的标注是创建时固定的。

### 1.2 为什么不能在内存态修正

树节点的 parent/child 边、位置、拆分决策——这些和创建时的标注耦合在一起。重分类一个节点的 action 应该影响它的拆分逻辑吗？不应该——拆分是不可逆的结构决策，不应该被分类器的进化触发重拆分。

**原则**：拆分决策（不可逆）只依赖 Tier 0 规则结果。标注（可逆）允许 Tier 1+2 参与，但标注的值不存储在树节点内。

### 1.3 为什么图可以解决

UnifiedGraphStore 是通用的图结构：
- 节点可以原地更新属性
- 边可以自由增删
- 没有 "parent/child" 固定约束
- 支持 HCWA 分层（Hot/Warm/Cold/Archive）

**在持久化时做修正——把树的刚性内容释放为图的柔性结构，修正后再写入。下次从图加载时，拿到的是已修正版本。**

---

## 2. 方案：修正网关 + 标注索引

### 2.1 核心思路

```
内存态（运行时）
  Tree Node
    node_id: "N23"
    parent: "N17"
    summary: "User asks about monitoring"   ← 不可变（拆分决策依据）
    action: ???                              ← 不存这里

标注索引（内存态，可演化）
  NodeAnnotationStore
    "N23" → {action: "add_monitoring", version: 3, source: "llm", ...}
            ↑ 随时可重分类覆盖

持久化时
  Tree Node + Annotation → Graph Node（合并修正）
    node_id: "N23"
    parent: "N17"
    action: "add_monitoring"               ← 写入时取最新标注
    action_version: 3

加载时
  Graph Node → 拆分为 Tree Node（结构） + Annotation（标注）
    Tree Node: {node_id, parent, summary...}
    Annotation: {action: "add_monitoring", ...}
```

### 2.2 不只是对话树

任何"创建后不便原地修改"的结构都可以用这个模式：

- **对话树节点** — 树结构刚性
- **持久化图节点** — 图的更新方便，但有些历史标注也需要版本化
- **行为链节点** — 行为模式随时间重新解释
- **工程链节点** — 工程知识持续演化

`NodeAnnotationStore` 被设计为**多域共享**——每个域有自己的 annotation schema，但共享同一套索引 + 版本化基础设施。

---

## 3. DialogueTreePersistenceAdapter

### 3.1 职责

```
输入：
  Tree Node（内存态） + NodeAnnotationStore 当前标注

处理：
  1. 取最新标注（可能触发重分类）
  2. 结构校验（合并/拆分/跨节点引用）
  3. 转换为图节点 + 边

输出：
  UnifiedGraphStore 中的 Graph Node + Graph Edge
```

### 3.2 接口

```python
class DialogueTreePersistenceAdapter:
    def __init__(self, store: UnifiedGraphStore,
                 resolver: TieredActionResolver,
                 annotation_store: NodeAnnotationStore)

    def persist_node(self, tree_node: TreeSegment,
                     conversation_id: str) -> str:
        """持久化单个树节点。返回 graph_node_id。"""

    def persist_tree(self, root: TreeSegment,
                     conversation_id: str) -> list[str]:
        """持久化整棵树。返回所有 graph_node_id。"""

    def load_node(self, graph_node_id: str) -> LoadResult:
        """从图加载节点，拆分为 Tree Node + Annotation。"""

    def load_tree(self, conversation_id: str) -> LoadResult:
        """从图加载整棵树。"""
```

### 3.3 修正逻辑

```python
def _resolve_action(self, tree_node, annotation_store) -> ActionCandidate:
    # 1. 尝试从 annotation_store 获取最新标注
    existing = annotation_store.get(tree_node.node_id, domain="dialogue")
    if existing and not existing.stale:
        return existing

    # 2. 重分类
    result = self._resolver.resolve("dialogue", tree_node.text)
    best = result[0] if result else None

    # 3. 写入 annotation_store
    if best:
        annotation_store.put(tree_node.node_id, domain="dialogue",
                             data={"action": best.action,
                                   "confidence": best.confidence,
                                   "source": best.source,
                                   "version": (existing.version + 1) if existing else 1})
    return best
```

### 3.4 结构校验

持久化时做轻量校验，不改变树结构，只做标注层面的修正：

- **相邻节点 action + topic 完全相同** → 追加 `merged_from` / `merged_to` 引用边，标注标记为 "redundant"
- **action 漂移但 topic 不变** → 追加 `action_shift` 边，连接两个节点

**不合并节点，不删除边，不改变树的拓扑结构。** 只追加元数据边。

---

## 4. NodeAnnotationStore

### 4.1 设计

```python
class NodeAnnotationStore:
    """
    多域共享的标注索引表。
    每个节点在每个域可以有一组标注。
    标注可以版本化，允许追溯历史值。
    """

    def put(self, node_id: str, domain: str,
            data: dict, version: int = 1) -> None

    def get(self, node_id: str, domain: str) -> Optional[NodeAnnotation]

    def mark_stale(self, node_id: str, domain: str) -> None

    def get_stale(self, domain: str, limit: int = 100) -> list[str]

    def history(self, node_id: str, domain: str) -> list[NodeAnnotation]
```

### 4.2 Schema

```python
@dataclass
class NodeAnnotation:
    node_id: str
    domain: str                     # "dialogue" | "engineering" | "behavior" | ...
    data: dict                      # 域特定的标注数据
    version: int = 1
    stale: bool = False             # 分类器进化后标记为待重分类
    previous_versions: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)
```

### 4.3 与 TieredActionResolver 的联动

```python
# TieredActionResolver.on_new_action 触发:
resolver.register_domain(adapter)
adapter.on_new_action(text, new_action)

# → 通知 NodeAnnotationStore:
annotation_store.mark_stale_by_source(node_id, domain="dialogue",
                                       source_pattern="llm")

# → 下次 get() 时自动触发重分类:
annotation = annotation_store.get(node_id, "dialogue")
if annotation.stale:
    result = resolver.resolve("dialogue", tree_node.text)
    annotation_store.put(node_id, "dialogue", {"action": result[0].action, ...})
```

### 4.4 存储策略

| 位置 | 生命周期 |
|:---|:---|
| 内存（dict） | 当前 Session 内 |
| 持久化（与树节点同步写入） | 跨 Session |
| 图节点 metadata 扩展字段 | 长期 |

---

## 5. Schema 定义

### 5.1 LoadResult

```python
@dataclass
class LoadResult:
    nodes: list[TreeSegment]                # 树结构节点
    annotations: dict[str, NodeAnnotation]  # node_id → 标注
    edges: list[dict]                       # 图边（含结构校验产生的）
```

### 5.2 Graph 序列化格式

```python
# 树节点 → 图节点
graph_node = {
    "id": "g_N23",
    "type": "dialogue_tree_node",
    "tier": "W",  # Warm tier by default
    "data": {
        "tree_node_id": "N23",
        "summary": tree_node.summary,
        "parent_id": "N17",
        "action": annotation.action,         # 最新标注
        "action_version": annotation.version,
        "conversation_id": conv_id,
        "created_at": tree_node.created_at,
    },
    "metadata": {
        "domain": "dialogue",
        "annotation_history": [...],
    },
}
```

---

## 6. 集成面：与已有 v4 模块的关系

| 模块 | 关系 | 改动 |
|:---|:---|:---|
| UnifiedGraphStore | 存储目标 | 不修改 |
| TieredActionResolver | 重分类引擎 | 不修改（新增 on_new_action → mark_stale 联动） |
| NodeAnnotationStore | 本模块 | 新建 |
| DialogueTreePersistenceAdapter | 本模块 | 新建 |
| TIERED_ACTION_RESOLVER design doc | 设计依据 | 不修改 |
| DiscourseBlockTree segmenter / context_builder | 消费者 | 注入 annotation_store |
| GraphTierManager / TierHeatBridge | 分层策略 | 不修改（图节点的 tier 正常流转） |

### 6.1 消费者接入点

```
segmenter.split(turns)
    ↓
context_builder.build(nodes)
    ↓  ← 在 build 时注入 annotation_store
    nodes[i].action = annotation_store.get(node_id, "dialogue").data["action"]
    ↓
persistence_adapter.persist_node(node, annotation)
    ↓  ← 写入时做重分类 + 结构校验
    UnifiedGraphStore.put(graph_node)
```

---

## 7. 实现计划

| Phase | 内容 | 依赖 | 估时 |
|:---|:---|:---|:---|
| Phase 1 | NodeAnnotationStore（内存版） | 无 | 小 |
| Phase 2 | DialogueTreePersistenceAdapter（persist_node + load_node） | Phase 1, UnifiedGraphStore, TieredActionResolver | 中 |
| Phase 3 | 结构校验逻辑（action_shift / merged_from 边） | Phase 2 | 小 |
| Phase 4 | Segmenter / ContextBuilder 接入 NodeAnnotationStore | Phase 1, DiscourseBlockTree | 小 |
| Phase 5 | 持久化：NodeAnnotationStore → 图 metadata | Phase 2 | 小 |

---

> 树不需要改结构。它只需要"退休"——持久化 → 修正网关 → 写入图 → 下次加载痊愈。
> 这不是树的局限，这是分层的设计：刚性留在内存态，柔性在持久化层消化。
