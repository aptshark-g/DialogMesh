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

## 4. Cross-Session Memory with Temporal Decay

**Source**: TiMem temporal hierarchical memory + ProfileUpdater.merge_session()

### Status: PARTIALLY IMPLEMENTED (P1)

### Current State
Single-session CognitiveProfile. merge_session() added to ProfileUpdater.
Profile persists per session, but lacks:
- Temporal decay (older sessions weighted less)
- Importance-based cross-session consolidation
- Cross-session graph edge persistence

### Problem
Session 1 teaches the system that the user is technically deep. Session 2 (purely casual chat) should not erase that trait. But a stale session-1 trait from 30 days ago should decay.

### Proposed Design

4-layer temporal hierarchy: SessionMemory dataclass + CrossSessionMemory manager.
- merge_profile: weighted blend with decay_factor ** age_days
- get_relevant_graph_edges: cross-session graph consolidation with temporal decay
- Importance-weighted: sessions with higher importance get more weight

See core/agent/v3_2/predictor/cognitive_profile.py: merge_session() for partial implementation.

---

## 5. Memory Update with Importance-Driven Consolidation

**Source**: HY-Memory self-evolving + _fire_event()

### Status: PARTIALLY IMPLEMENTED (P1)

### Current State
_fire_event() handles SUCCESS/CORRECTION/CONSOLIDATE events.
Importance field on BehaviorEdge.
But lacks:
- Event batching (consolidation should happen in bulk, not per-turn)
- Importance threshold for pruning (currently time-only)
- Explicit consolidation cycle (background task)

### Proposed Design

ConsolidationCycle class with BATCH_SIZE=10 events.
- push_event() buffers events and batch-consolidates
- consolidate() processes buffered events, updates importance
- should_prune() checks importance < 0.2 and sample_count > 3

See core/agent/v3_2/integration.py: _fire_event() and
core/agent/v3_2/behavior_graph/models.py: BehaviorEdge.importance for partial implementation.

---

## 6. Hypergraph Memory (Topic-Episode-Fact)

**Source**: HyperMem (ACL 2026)

### Status: DESIGNED, NOT IMPLEMENTED (P2)

### Reference Architecture
HyperMem three-level hypergraph:
- L3 Topic: long-horizon theme (DialogMesh: DiscourseBlock)
- L2 Episode: temporally contiguous segment (DialogMesh: BehaviorGraph edges)
- L1 Fact: atomic knowledge (DialogMesh: CognitiveProfile evidence)

Weighted hyperedges connect same-level nodes. Coarse-to-fine retrieval: Topic -> Episode -> Fact.
Reciprocal Rank Fusion (RRF) for BM25 + dense embedding merge.

### What Changes
1. Hyperedge type in GroupReference (N-way connections)
2. Coarse-to-fine retrieval path in waterwave_activate
3. RRF fusion for BM25 + dense embedding

---

## Updated Priority

| Priority | Improvement | Work | Status |
|:--------:|:-----------|:----:|:------:|
| P0 | System1/System2 mode | ~40 lines | DONE |
| P1 | Cross-session memory | ~90 lines | Partial |
| P1 | Importance-driven consolidation | ~110 lines | Partial |
| P1 | GroupReference (high-order) | ~55 lines | DONE |
| P2 | Complexity-aware retrieval | ~70 lines | Design |
| P2 | Hypergraph memory | ~80 lines | Design |
| P2 | LLM evidence judgment | ~50 lines | Design |

﻿
## 4. Three-Level Memory Architecture (JVM-GC Inspired)

**Source**: User design discussion + JVM garbage collection analogy

### Architecture

Three layers, each with a distinct role:

Layer 1: Flat Memory (permanent, never deleted)
  Role: Authoritative storage — all raw data lives here forever
  Storage: DiscourseBlockTree (unchanged)
  GC: NONE

Layer 2: Active BehaviorGraph (hot zone)
  Role: Frequently-used edges, directly queried
  Storage: Existing BehaviorGraph (enhanced with activation_count)
  GC: Activation-Count-Driven Pruning

Layer 3: Cold Index (meta-space)
  Role: Edge meta-data for edges that left Layer 2
  Storage: ColdIndexer (keyword/summary/profile_bias)
  GC: Summary retention only

### Design Rules
1. Layer 1 is ALWAYS source of truth. All layers derive from it.
2. Layer 2 to 3: preserve edge_id + keywords + profile_bias + summary
3. Layer 3 to 2: full reconstruction from Layer 1 flat data

## 4a. Activation Count

**Source**: Fixes TiMem temporal decay

### Status: TO BE IMPLEMENTED

### Change
Add activation_count: int = 0 to BehaviorEdge.
Incremented each time the edge is retrieved via waterwave_activate.
Naturally reflects usage frequency without decay math.

### Threshold

| Parameter | Anchor | Range | Adaptive Signal |
|:----------|:------:|:-----:|:----------------|
| Pruning threshold (activation) | 3 | [2, 6] | If cold recall > 20% in last 100 turns, lower |
| Pruning threshold (sample_count) | 10 | [5, 20] | If graph size > 500 edges, raise lower bound |

## 4b. ColdIndexer (Layer 3)

**Source**: JVM metaspace analogy

### Status: TO BE IMPLEMENTED

### Storage Schema
ColdEdgeRecord: edge_id, from_summary, to_summary, keywords, profile_bias, activation_history, last_active
ColdIndexer: dict of ColdEdgeRecord, keyword search, recall reconstruction

### Threshold

| Parameter | Anchor | Range | Adaptive |
|:----------|:------:|:-----:|:---------|
| Max records | 5000 | [2000, 10000] | If search > 10ms, reduce |
| Recall top_k | 3 | [2, 5] | If re-warmed edges re-cool within 10 turns, reduce k |


## 4c. Adaptive Batch Consolidation

**Source**: User feedback — batch by data volume, not turn count

### Status: TO BE IMPLEMENTED

### Design
Consolidate when pending edge changes reaches threshold (not turn count):
- ConsolidationCycle.record_event() buffers by edge_id
- consolidate() applies all pending weight deltas at once
- EDGE_CHANGE_THRESHOLD anchor=15, range=[8, 30]

### Threshold

| Parameter | Anchor | Range | Adaptive |
|:----------|:------:|:-----:|:---------|
| Batch size | 15 edges | [8, 30] | If consolidation > 5ms, reduce |

## 4d. Cold Re-warming (Layer 3 to 2)

**Source**: JVM GC promotion analogy

### Status: TO BE IMPLEMENTED

### Design
When waterwave gets less than top_k hits from active graph, search ColdIndexer:
1. ColdIndexer.search(query_tokens)
2. ColdIndexer.recall(record, flat_data_provider)
3. graph.add_edge(reconstructed_edge)
4. Return hits

## Updated Priority

| Priority | Improvement | Work | Status |
|:--------:|:-----------|:----:|:-------|
| P0 | Activation count | ~5 lines | TODO |
| P0 | Adaptive batch consolidation | ~60 lines | TODO |
| P0 | ColdIndexer | ~80 lines | TODO |
| P0 | Cold re-warming path | ~30 lines | TODO |
| P1 | User profile weighting | ~20 lines | DONE |
| P2 | Hypergraph memory | ~80 lines | Design |
