# DialogMesh FoA 注意力焦点 --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-FOA-009  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S9  
> **前置算法**: ACT-R 双权重激活传播  
> **原则**: FoA 只做注意力选择, 不做推理。返回 3-5 个最相关节点供 LLM 上下文窗口使用。  

---
## 1. 文档目标与范围
为 FoA(Focus of Attention)提供工程实现规范。覆盖 ACT-R 激活传播、种子选择、阈值裁剪、降级策略。

---
## 2. 数据模型
```python
@dataclass
class AttentionNode:
    node_id: str
    activation: float = 0.0
    base_activation: float = 0.0
    distance_from_seed: int = 0

@dataclass
class FocusResult:
    seed_nodes: list[str]
    activated: list[AttentionNode]
    subgraph_edges: list[tuple[str, str]]
    decay_used: float
    fallback_used: bool = False

    @property
    def top_k(self, k=5) -> list[AttentionNode]:
        return sorted(self.activated, key=lambda n: -n.activation)[:k]
```

---
## 3. ACT-RActivator
```python
class ACTRActivator:
    DEFAULT_DECAY = 0.3
    ACTIVATION_THRESHOLD = 0.3
    MAX_NODES = 5

    def __init__(self, decay=DEFAULT_DECAY):
        self.decay = decay

    def propagate(
        self, seeds: list[str], node_degrees: dict[str, int], edges: dict[tuple[str,str], float]
    ) -> list[AttentionNode]:
        visited = {}  # node_id -> AttentionNode
        for seed in seeds:
            visited[seed] = AttentionNode(seed, activation=1.0, base_activation=node_degrees.get(seed, 0), distance_from_seed=0)
        queue = list(seeds)
        while queue:
            current = queue.pop(0)
            cur_node = visited[current]
            for (src, tgt), weight in edges.items():
                if src == current and tgt not in visited:
                    dist = cur_node.distance_from_seed + 1
                    base = node_degrees.get(tgt, 0)
                    act = base + weight * cur_node.activation - self.decay * dist
                    if act > self.ACTIVATION_THRESHOLD:
                        visited[tgt] = AttentionNode(tgt, act, base, dist)
                        queue.append(tgt)
        return sorted(visited.values(), key=lambda n: -n.activation)[:self.MAX_NODES]

    def get_subgraph_edges(self, nodes: list[AttentionNode], all_edges: dict) -> list[tuple[str,str]]:
        ids = {n.node_id for n in nodes}
        return [(s,t) for (s,t) in all_edges if s in ids and t in ids]
```

---
## 4. FoA (入口)
```python
class FoA:
    def __init__(self, activator=None):
        self.activator = activator or ACTRActivator()

    def focus(
        self, intent: str, expectation: str,
        node_degrees: dict[str, int], edges: dict
    ) -> FocusResult:
        seeds = self._select_seeds(intent, expectation, node_degrees)
        if not seeds:
            return FocusResult([], [], [], self.activator.decay, fallback_used=True)
        activated = self.activator.propagate(seeds, node_degrees, edges)
        if not activated:
            return FocusResult(seeds, [], [], self.activator.decay, fallback_used=True)
        sub_edges = self.activator.get_subgraph_edges(activated, edges)
        return FocusResult(seeds, activated, sub_edges, self.activator.decay)

    def _select_seeds(self, intent, expectation, degrees) -> list[str]:
        seeds = []
        if expectation and expectation in degrees:
            seeds.append(expectation)
        if intent and intent in degrees:
            seeds.append(intent)
        if not seeds:
            # 退避: 按度数取 Top-2
            sorted_nodes = sorted(degrees.items(), key=lambda x: -x[1])
            seeds = [n for n,_ in sorted_nodes[:2]]
        return seeds[:2]
```

---
## 5. 测试策略
| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_actr_activator | 激活传播, 阈值裁剪, 距离衰减 | P0 |
| test_foa | 种子选择, 完整流程, 退避 | P0 |
--- END OF DOCUMENT ---