# DialogMesh v6 — 业务链设计 · 第2.1章：Topic Tree (主题树)

> 版本: v1.0 | 日期: 2026-07-21
> 接入: TopicTree feed ✅ · Context injection ✅ · 分支切换 ❌ · 双层摘要 ❌

---

## 一、在 10 链中的位置

```mermaid
graph TD
    DISCOURSE["DiscourseBlockTree<br/>块分段结果"]

    subgraph TOPIC["Topic Tree"]
        direction TB
        FEED["feed_turn()<br/>每轮更新主题状态"]
        MATCH["主题匹配<br/>fork/merge/switch/resume"]
        SUMMARY["双层摘要<br/>L1: 分支级 · L2: 跨分支"]
        INJECT["_inject_topic_tree_context()<br/>→ CrossDomainContextIR"]
    end

    DISCOURSE -->|"continue→保持<br/>fork/new→匹配"| MATCH
    MATCH --> FEED
    FEED --> SUMMARY
    SUMMARY --> INJECT
    INJECT --> CTX["CrossDomainContextIR<br/>上下文装配"]
```

---

## 二、核心模型

```mermaid
graph TD
    ROOT["TopicTree"]
    ROOT --> B1["Branch A · 显存量化的4bit方案<br/>state: ACTIVE"]
    ROOT --> B2["Branch B · 多肉养护<br/>state: PAUSED"]
    ROOT --> B3["Branch C · 架构讨论<br/>state: ARCHIVED"]

    B1 --> B1L1["L1摘要:<br/>{core: 'RTX4060显存量化的4bit方案',<br/>behavior_chain: [{quantize, RTX4060},...],<br/>source_turns: [1,3,5]}"]
    B2 --> B2L1["L1摘要:<br/>{core: '多肉7-10天浇水',<br/>behavior_chain: [{water, succulent},...]}"]
    B3 --> B3L1["L1摘要 (压缩)"]

    ROOT --> L2["L2摘要 (跨分支聚合)<br/>用户长期行为pattern"]
```

**状态机**: ACTIVE → PAUSED → ARCHIVED  
**上下文隔离**: 活跃分支全量 · 非活跃分支摘要

---

## 三、引擎现状

```mermaid
graph LR
    subgraph DONE["✅ 已接"]
        A1["TopicTreeSource 初始化"]
        A2["feed_turn() · 每轮调用"]
        A3["_inject_topic_tree_context()"]
        A4["ContextAssembler 数据源"]
    end

    subgraph GAP["❌ 未接"]
        B1["分支切换 (switch/resume)"]
        B2["双层摘要 (L1/L2)"]
        B3["行为链内建 (v3.1)"]
        B4["TopicMarkers → DiscourseBlock"]
    end
```

**代码**: `topic_tree/manager_v2.py` (1091行) + `manager.py` (624行) + `v4/context/topic_tree_source.py` (183行)

---

## 四、接入差距

```
✅ 初始化 + feed_turn            — 每轮对话更新主题
✅ Context injection             — _inject_topic_tree_context
✅ ContextAssembler 数据源         — TopicTreeSource
❌ 分支切换                      — switch/resume API
❌ 双层摘要                      — summary_engine 未触发
❌ 行为链内建                    — v3.1 设计
❌ 递归收敛主题快匹配             — BUSINESS_CHAIN_02_APPENDIX

有效实现率: ~45%
需接入约 30 行
```
