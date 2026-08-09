# Literature Cortex v5.2a 设计方案：对偶器 (Dual Matcher)

> **文档编号:** LC-DESIGN-v5.2a
> **版本:** v5.2a-DRAFT
> **状态:** 🔄 WIP（实现进行中）
> **完成度:** 70%
> **日期:** 2026-06-16
> **依赖:** v5.2 多视角 Schema（`node_perspectives` 表已落地）
> **注册表:** 参见 `DESIGN-REGISTRY.md` 第 #design-文档清单 节
> **核心目标:** 通过锚点吸引解决概念浮动覆盖率不足的问题

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-16 | v5.2a-DRAFT | 初始设计 + 核心实现完成 |

---

## 1. 问题陈述

### 1.1 Phase 1 的遗留问题

v5.2 Phase 1 完成后，多视角覆盖率只有 **47%**（8/17 节点），平均视角数 **1.5**。

**根本原因：** 概念浮动依赖硬编码关键词匹配，大量节点因标题不含触发词而只有单个 `core` 视角。

**示例：**

| 节点 | 原始层级 | 当前视角 | 缺失视角 |
|------|---------|---------|---------|
| causality-principle | L1 | core(L1) | mathematical(L2) — 因果性有数学形式 |
| wiener-hopf | L2 | core(L2) | physical(L1) — 有物理基础 |
| single-channel-anc | L4 | core(L4) | engineering(L5) — 有工程实现 |
| thermal-vibration-coupling | L4 | core(L4) | physical(L1), mathematical(L2) — 热力学+振动 |

### 1.2 核心洞察

**相似的节点应该有相似的视角分布。**

如果 `signal-propagation-delay`（L1）有 `mathematical(L2)` 视角，那么与其高度相似的 `causality-principle`（L1）也应该有 `mathematical(L2)` 视角。

这就是**对偶吸引**：用已有多视角节点作为锚点，吸引单视角节点生成缺失视角。

---

## 2. 对偶器架构

```
┌─────────────────────────────────────────────────────────────┐
│                    DualMatcher (对偶器)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 特征提取器   │  │ 相似度引擎   │  │ 锚点吸引器   │      │
│  │ Feature      │  │ Similarity   │  │ Attractor    │      │
│  │ Extractor    │  │ Engine       │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                           ↑
                    ┌──────┴──────┐
                    ↓             ↓
            ┌─────────────┐ ┌─────────────┐
            │ 目标节点     │ │ 锚点节点池  │
            │ (单视角)     │ │ (多视角)    │
            └─────────────┘ └─────────────┘
```

---

## 3. 核心算法

### 3.1 特征提取

```python
def extract_features(node: dict) -> NodeFeatures:
    """提取节点的多维特征向量。"""
    return NodeFeatures(
        # 文本特征
        text_tokens = tokenize(
            node["title"] + " " + 
            (node.get("what") or "") + " " +
            (node.get("why_exists") or "") + " " +
            (node.get("content") or "")
        ),
        
        # 结构特征
        neighbor_ids = get_neighbors(node["id"]),
        neighbor_semantics = get_neighbor_semantics(node["id"]),
        
        # 层级特征
        level = node.get("knowledge_level"),
        
        # 关系模式特征
        edge_pattern = get_edge_pattern_signature(node["id"]),
    )
```

### 3.2 相似度计算（三层融合）

```python
def compute_similarity(target: NodeFeatures, candidate: NodeFeatures) -> float:
    """三层相似度融合。"""
    
    # 层1：文本相似度（Jaccard / TF-IDF）
    text_sim = jaccard_similarity(target.text_tokens, candidate.text_tokens)
    
    # 层2：结构相似度（邻居重叠）
    common_neighbors = len(set(target.neighbor_ids) & set(candidate.neighbor_ids))
    union_neighbors = len(set(target.neighbor_ids) | set(candidate.neighbor_ids))
    struct_sim = common_neighbors / union_neighbors if union_neighbors > 0 else 0
    
    # 层3：层级邻近度
    level_dist = abs(level_order(target.level) - level_order(candidate.level))
    level_sim = 1 - (level_dist / 5)  # L1-L6 最大距离为 5
    
    # 融合权重：文本 50% + 结构 30% + 层级 20%
    return 0.5 * text_sim + 0.3 * struct_sim + 0.2 * level_sim
```

### 3.3 锚点吸引

```python
def attract_perspectives(node_id: str, top_k: int = 5, min_sim: float = 0.5) -> list[Suggestion]:
    """基于对偶锚点吸引生成视角建议。"""
    
    # Step 1: 找到高相似度锚点
    duals = find_duals(node_id, top_k, min_sim)
    
    # Step 2: 收集锚点视角投票
    level_votes = defaultdict(list)
    for dual in duals:
        for p in store.get_perspectives(dual.node_id):
            level_votes[p.knowledge_level].append({
                "dual_id": dual.node_id,
                "similarity": dual.similarity,
                "perspective_name": p.perspective_name,
                "constraint_context": p.constraint_context,
            })
    
    # Step 3: 为目标节点生成缺失视角
    existing_levels = {p.knowledge_level for p in store.get_perspectives(node_id)}
    suggestions = []
    
    for level, votes in level_votes.items():
        if level in existing_levels:
            continue  # 已有该层级，跳过
        
        # 计算吸引力强度
        total_weight = sum(v["similarity"] for v in votes)
        avg_confidence = min(0.95, total_weight / len(votes))
        
        # 视角名称投票（取权重最高的）
        name_weights = defaultdict(float)
        for v in votes:
            name_weights[v["perspective_name"]] += v["similarity"]
        best_name = max(name_weights, key=name_weights.get)
        
        suggestions.append(PerspectiveSuggestion(
            node_id=node_id,
            perspective_name=best_name,
            knowledge_level=level,
            confidence=avg_confidence,
            reason=f"由 {len(votes)} 个相似锚点对偶吸引生成: {[v['dual_id'] for v in votes]}",
            dual_sources=[v["dual_id"] for v in votes],
        ))
    
    return suggestions
```

### 3.4 约束浮动（阈值控制）

```python
def constrained_float(node_id: str, suggestions: list[Suggestion]) -> list[ApprovedPerspective]:
    """基于锚点分布约束浮动范围。"""
    
    # 获取锚点的层级分布
    duals = find_duals(node_id)
    anchor_levels = []
    for d in duals:
        for p in store.get_perspectives(d.node_id):
            anchor_levels.append(p.knowledge_level)
    
    # 计算层级分布的统计特征
    level_counts = Counter(anchor_levels)
    total_anchors = len(duals)
    
    approved = []
    for sug in suggestions:
        level = sug.knowledge_level
        
        # 约束1：锚点中该层级出现频率必须 > 30%
        freq = level_counts.get(level, 0) / total_anchors if total_anchors > 0 else 0
        if freq < 0.3:
            continue  # 锚点不支持该层级，拒绝
        
        # 约束2：置信度必须 > 0.6
        if sug.confidence < 0.6:
            continue
        
        # 约束3：与目标原始层级的距离 ≤ 2
        original_level = store.get_node(node_id).get("knowledge_level")
        if original_level and abs(level_order(level) - level_order(original_level)) > 2:
            continue
        
        approved.append(sug)
    
    return approved
```

---

## 4. 数据模型

### 4.1 新增表：dual_matches

```sql
CREATE TABLE IF NOT EXISTS dual_matches (
    id TEXT PRIMARY KEY,
    target_node_id TEXT NOT NULL,
    anchor_node_id TEXT NOT NULL,
    similarity REAL NOT NULL CHECK(similarity >= 0 AND similarity <= 1),
    text_similarity REAL DEFAULT 0,
    struct_similarity REAL DEFAULT 0,
    level_similarity REAL DEFAULT 0,
    match_type TEXT DEFAULT 'auto' CHECK(match_type IN ('auto', 'manual', 'confirmed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(target_node_id, anchor_node_id)
);

CREATE INDEX idx_dual_target ON dual_matches(target_node_id);
CREATE INDEX idx_dual_anchor ON dual_matches(anchor_node_id);
CREATE INDEX idx_dual_sim ON dual_matches(similarity DESC);
```

### 4.2 新增表：perspective_suggestions

```sql
CREATE TABLE IF NOT EXISTS perspective_suggestions (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    perspective_name TEXT NOT NULL,
    knowledge_level TEXT NOT NULL CHECK(knowledge_level IN ('L1','L2','L3','L4','L5','L6')),
    confidence REAL DEFAULT 0.5,
    reason TEXT,
    dual_sources TEXT,  -- JSON: [anchor_node_id, ...]
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'auto_applied')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE INDEX idx_suggestions_node ON perspective_suggestions(node_id);
CREATE INDEX idx_suggestions_status ON perspective_suggestions(status);
```

---

## 5. 工作流

```
输入：单视角节点（如 causality-principle）
  ↓
Step 1: 特征提取
  - 文本：title + what + why_exists + content
  - 结构：邻居 ID 集合 + 邻居语义集合
  - 层级：原始 L1
  ↓
Step 2: 相似度搜索（遍历所有节点）
  - 计算文本相似度（Jaccard）
  - 计算结构相似度（邻居重叠）
  - 计算层级邻近度
  - 融合：0.5*text + 0.3*struct + 0.2*level
  - 筛选：similarity > 0.5
  - 排序：取 top_k=5
  ↓
Step 3: 锚点吸引
  - 收集锚点的所有视角
  - 按层级分组投票
  - 计算吸引力强度
  - 生成视角建议
  ↓
Step 4: 约束浮动
  - 锚点频率约束（>30%）
  - 置信度约束（>0.6）
  - 层级距离约束（≤2）
  - 通过约束 → 写入 perspective_suggestions
  ↓
Step 5: 应用建议
  - auto_applied：高置信度（>0.85）自动添加
  - pending：中置信度（0.6-0.85）待人工审核
  - rejected：低置信度（<0.6）直接拒绝
```

---

## 6. 示例

### 示例1：causality-principle

```
目标：causality-principle (L1)
当前视角：core(L1)

对偶搜索：
  signal-propagation-delay    sim=0.85  perspectives: core(L1), mathematical(L2)
  mechanical-wave-transmission sim=0.80  perspectives: core(L1), mathematical(L2)
  group-delay                 sim=0.75  perspectives: core(L1), mathematical(L2)

锚点视角投票：
  L1: 3 votes (sim: 0.85+0.80+0.75 = 2.40)
  L2: 3 votes (sim: 0.85+0.80+0.75 = 2.40)

生成建议：
  mathematical(L2), confidence=0.80, reason="3个相似物理基础锚点均有数学视角"

约束检查：
  - L2 频率：3/3 = 100% > 30% ✓
  - confidence=0.80 > 0.6 ✓
  - |L2-L1| = 1 ≤ 2 ✓

结果：
  causality-principle 新增 mathematical(L2) 视角
```

### 示例2：single-channel-anc

```
目标：single-channel-anc (L4)
当前视角：core(L4)

对偶搜索：
  mimo-fxlms            sim=0.72  perspectives: core(L4), engineering(L5)
  thermal-vibration-coupling sim=0.45  (低于阈值，忽略)

锚点视角投票：
  L4: 1 vote (sim: 0.72)
  L5: 1 vote (sim: 0.72)

生成建议：
  engineering(L5), confidence=0.72, reason="相似系统架构锚点有工程实现视角"

约束检查：
  - L5 频率：1/1 = 100% > 30% ✓
  - confidence=0.72 > 0.6 ✓
  - |L5-L4| = 1 ≤ 2 ✓

结果：
  single-channel-anc 新增 engineering(L5) 视角
```

---

## 7. 与 v5.2 的集成

```python
class MetaCognitiveArbiter:
    def __init__(self, ...):
        ...
        self.dual_matcher = DualMatcher(convergent_store)
    
    def enrich_perspectives(self, node_id: str) -> list[PerspectiveSuggestion]:
        """使用对偶器丰富节点视角。"""
        suggestions = self.dual_matcher.attract_perspectives(node_id)
        approved = self.dual_matcher.constrained_float(node_id, suggestions)
        
        for p in approved:
            if p.confidence > 0.85:
                # 高置信度自动应用
                self.store.add_perspective(
                    node_id=node_id,
                    perspective_name=p.perspective_name,
                    knowledge_level=p.knowledge_level,
                    constraint_context=p.reason,
                    confidence=p.confidence,
                )
            else:
                # 中置信度加入待审核队列
                self.store.add_suggestion(p)
        
        return approved
```

---

## 8. 预期效果

| 指标 | Phase 1 后 | Phase 1+对偶器后 | 提升 |
|------|-----------|-----------------|------|
| 多视角节点比例 | 47% (8/17) | ~80% (13-14/17) | +33% |
| 平均视角/节点 | 1.5 | ~2.2 | +0.7 |
| 覆盖率 | 单视角节点 9 个 | 单视角节点 3-4 个 | -60% |

---

## 9. 风险与边界

| 风险 | 缓解措施 |
|------|---------|
| 锚点质量差导致错误吸引 | 相似度阈值 ≥0.5；频率约束 ≥30% |
| 循环吸引（A吸引B，B又吸引A） | 单向处理：只从多视角节点向单视角节点吸引 |
| 层级距离约束过松 | max_distance=2；可配置 |
| 文本相似度被停用词主导 | Jaccard 前过滤停用词 |

---

## 10. 一句话总结

**对偶器是概念浮动的"社会学习"机制：一个节点不应该独自决定自己在哪一层，它应该看看和自己最像的节点都在哪一层，然后被吸引过去。**

---

*设计方案版本: v5.2a-DRAFT*  
*撰写日期: 2026-06-16*  
*作者: 合作 (OpenClaw)*
