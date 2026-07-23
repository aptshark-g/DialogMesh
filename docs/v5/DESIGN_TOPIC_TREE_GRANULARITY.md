# Topic Tree — 分层粒化摘要 (Distance-Decay Granularity)

> 2026-07-22 · 替代滑动窗口方案

---

## 一、核心模型

```
Topic Tree = 一棵活跃的对话树, 每个节点有:
  - 原始内容 (raw blocks)
  - 距离衰减摘要 (L1/L2/L3/Lroot, 随距离粗化)
  - 消费热度 (被引用次数, 影响刷新频率)
```

```
         Root (全局主题词, 1句话)
        /    \
     BranchA  BranchB (L3: 跨分支摘要)
     /    \      \
   Node1 Node2  Node3 (L2: 段落级)
   / | \  / \     |
  B1 B2 B3 B4 B5 B6  (L1: 细粒度, 接近原文)
  ↑ 当前消费点
```

## 二、四层摘要定义

| 层级 | 粒度 | Token预算 | 刷新频率 | 内容 |
|:---:|------|:---:|:---:|------|
| **L1** | 细粒度, 接近原文 | ~200 tokens/块 | 每次消费 | 原文压缩, 保留关键实体+操作 |
| **L2** | 段落级, 邻居分支 | ~100 tokens/分支 | 5轮或分支切换 | 分支主题+关键结论 |
| **L3** | 跨分支摘要 | ~50 tokens/分支 | 10轮或跨域跳转 | 远距离分支的一句话概要 |
| **L-root** | 全局骨架 | ~30 tokens | 新分支/新话题 | 全局主题词, 用于路由 |

## 三、距离衰减算法

```python
class TopicTreeGranularity:
    def summary_level(self, distance_from_active: int, heat: float) -> int:
        """
        distance_from_active: 从当前活跃节点到目标节点的树距离
        heat: 该分支近期被引用次数
        
        返回: 1(L1细) / 2(L2中) / 3(L3粗) / 4(root骨架)
        """
        effective_distance = distance_from_active / max(1, heat)
        
        if effective_distance <= 2:   return 1  # 近邻 → 细粒度
        elif effective_distance <= 5: return 2  # 中距 → 中粒度
        elif effective_distance <= 10: return 3  # 远距 → 粗粒度
        else:                         return 4  # 全局 → 骨架
```

**动态调整**：
- 宏观讨论 → 活跃节点发热度高 → 分支摘要更频繁 → L2/L3 自然更新
- 微观操作 → 活跃节点固定 → L1 维持不变 → 节省计算

## 四、与 Subgraph 的分工

```
Discourse Tree (对话树):
  - 提供: 原始块, 块间关系, 距离信息
  - 不提供: 摘要, 跨链视图

Topic Tree (主题树):
  - 提供: 分层摘要, 距离衰减粒度, 分支管理
  - 消费: Discourse Tree 的结构信息

Subgraph (子图):
  - 提供: 特定视角的投影 (Meta子图, Dialogue子图)
  - 消费: Topic Tree 的摘要 + Discourse Tree 的原始块
  - 不重复: Topic Tree 已提供的摘要
```

## 五、对应成熟方案

| 方案 | 对应 | 机制 |
|------|------|------|
| **RAPTOR** (Stanford 2024) | 树形递归摘要 | 聚类→树→自底向上摘要, 查询时树遍历 |
| **GraphRAG** (Microsoft) | L2/L3 摘要 | 社区检测→社区摘要→全局聚合 |
| **MemGPT/Letta** | 层级记忆 | 核心记忆(热)+归档记忆(冷), 自动升降级 |
| **LongLLMLingua** | L1 压缩 | 提示词压缩, 保留关键实体 |

## 六、实现路径

```python
class TopicTreeSummary:
    def __init__(self, discourse_tree):
        self.tree = discourse_tree
        self.l1_cache = {}   # node_id → L1 summary
        self.l2_cache = {}   # branch_id → L2 summary
        self.l3_cache = {}   # far_branch → L3 summary
        self.root_summary = ""  # global
    
    def get_context(self, active_node: str, max_tokens: int = 2000):
        """组装当前消费需要的上下文——距离衰减粒度"""
        context = []
        budget = max_tokens
        
        # 1. L1: 同一分支内的近邻 (细)
        siblings = self.tree.siblings(active_node, distance=2)
        for node in siblings:
            if node.id != active_node:
                summary = self._ensure_l1(node)
                context.append(summary)
                budget -= len(summary)
        
        # 2. L2: 相邻分支 (中)
        if budget > 0:
            adj_branches = self.tree.adjacent_branches(active_node)
            for branch in adj_branches:
                summary = self._ensure_l2(branch)
                context.append(summary)
                budget -= len(summary)
        
        # 3. L3: 远距离分支 (粗)
        if budget > 0:
            for far_branch in self.tree.far_branches(active_node):
                summary = self._ensure_l3(far_branch)
                if len(summary) <= budget:
                    context.append(summary)
                    budget -= len(summary)
        
        return context
```

**关键**: 摘要不是预计算全部——是**按需生成**：
- 热节点频繁访问 → 缓存命中 → 零成本
- 冷节点偶尔访问 → 按需生成 → LLM 调用
- 宏/微观自动调整：宏观 = 大量 L2/L3, 微观 = 密集 L1
