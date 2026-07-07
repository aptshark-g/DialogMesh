# DialogMesh v3.2 改进笔记

> 基于同类项目对比分析提取的三项改进方向。

---

## 1. 高阶关联 (GroupReference)

**来源**: HyperMem (ACL 2026)

### 现状

当前的 cross_refs 是 **pairwise** 的：

`python
# 单个 cross_ref 只连接两个块
cross_refs = [
    CrossReference(target=block_A, type=analogy),
    CrossReference(target=block_B, type=continuation),
]
`

一个 cross_ref 只表达 A 和 B 有关系。无法表达 A/B/C 三者共同指向结论 D 这种 group-wise 的高阶关联。

### 问题

在真实对话中高阶关联很常见：RTX 4060 显存不足 + 上次调优推荐系统也遇到过 + 最后用了梯度累积解决 -> 三者放在一起才构成完整类比。

pairwise cross_refs 只能链接两两之间，丢失了三者共同指向的信息。

### 方案

新增 GroupReference，一个组引用可以包含多个块：

`python
@dataclass
class GroupReference:
    group_id: str
    block_ids: list[str]
    ref_type: str
    strength: float
    context_summary: str
    created_at_turn: int
`

存储在两个层面：
1. DiscourseBlock 上挂 group_refs: list[GroupReference]
2. DiscourseBlockTreeManager 上挂 group_ref_index: dict[str, GroupReference]

检索时匹配到组内任意一个块即激活整个组。

### 工作量: ~55 行, P1

---

## 2. 复杂度感知召回 (Complexity-Aware Retrieval)

**来源**: TiMem (ACL 2026 Findings)

### 现状

当前语义级联激活使用固定阈值 0.12，无论查询复杂度。

### 问题

简单查询应召回少量高精度结果，复杂查询应召回更多结果。固定阈值导致简单查询召回太多无关内容、复杂查询召回不够。

### 方案

添加 ComplexityScorer 动态计算阈值：

`python
class ComplexityScorer:
    def score(self, query_text: str) -> float:
        score = 0.3
        score += min(len(query_text) / 200, 0.3)
        return min(score, 1.0)
    
    def get_threshold(self, c: float) -> float:
        return 0.25 - c * 0.17  # c=0.2 -> 0.22, c=0.8 -> 0.11
`

### 工作量: ~70 行, P2

---

## 3. LLM 证据判断 (LLM Evidence Judgment)

**来源**: HiGMem

### 现状

当前证据采集是全量记录的，没有区分噪音和有诊断价值的证据。

### 问题

不是所有用户行为都值得记录为人格特质证据。用户输入 test 对推断尽责性没有价值。

### 方案

增加一层攒批 LLM 判断：
1. 证据积累到 N 条后批量交给 LLM 判断
2. 仅对 neuroticism/risk_tolerance 等高噪声 trait 启用
3. 每 session 结束时修剪一次

### 工作量: ~50 行, P2

---

## 优先级

| 优先级 | 改进 | 工作量 |
|:------:|------|:------:|
| P1 | 高阶关联 (GroupReference) | ~55 行 |
| P2 | 复杂度感知召回 | ~70 行 |
| P2 | LLM 证据判断 | ~50 行 |
