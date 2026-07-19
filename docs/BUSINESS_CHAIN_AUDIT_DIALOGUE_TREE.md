# DialogMesh v6 — 对话树业务审计 · 缺口补充

> 版本: v1.0 | 日期: 2026-07-18
>
> 对比设计文档审计链 01-04, 发现 5 个缺口。

---

## 1. 对比审计

| 设计文档 | 内容 | 链 01-04 覆盖? | 状态 |
|----------|------|:---:|:----:|
| DESIGN_INTERACTION_MODEL | 双轨制 (Event Log + Projection) | ✅ 链 01 | |
| DESIGN_CROSS_DOMAIN_CONTEXT | ContextCompiler 域选择+预算分配 | ✅ 链 01 | |
| DESIGN_TIERED_ACTION_RESOLVER | 共享分类内核 + 反馈闭环 | ✅ 链 02 | |
| DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER | 树→图 + 修正网关 + NodeAnnotationStore | ✅ 链 04 | |
| DESIGN_COGNITIVE_DYNAMICS_V6 | State→Transition | ✅ 链 04 | |
| design_discourse_block_tree_v2 §5 | **9维宏微观粘合度** | ❌ | **缺口 ①** |
| design_discourse_block_tree_v2 §2.2 | **温度模型 4 态** (active/paused/cold/frozen) | ❌ | **缺口 ②** |
| design_discourse_block_tree_v2 §4.1 | **HeaderInjector 代词消解** | ❌ | **缺口 ③** |
| design_discourse_block_tree_v2 §7 | **渐进式四级摘要** (v1→v2→v3→v4) | ❌ | **缺口 ④** |
| DESIGN_V3_1_BEHAVIOR_SUMMARY §3 | **对话树节点内建行为链** | ❌ | **缺口 ⑤** |
| CAPABILITY_GAP | 温度模型/HeaderInjector/渐进式摘要均未实现 | ❌ | **确认** |

---

## 2. 缺口 ① — 9 维宏微观粘合度

### 2.1 设计 (discourse_block_tree_v2 §5)

```
当前链 02: 只提到 BGE 语义相似度用于重复检测
         ❌ 没有描述 EDU 之间的粘合度计算——这是决定树结构的核心算法

设计: CohesionScorer — 9 维双层量化
  宏观 (4维, M1-M4):
    M1 cosine embedding    (0.35权重) — BGE 语义相似
    M2 intent overlap      (0.25)      — 意图一致性
    M3 domain match        (0.20)      — "设计讨论" vs "闲聊"
    M4 mood/politeness     (0.20)      — 语气一致性

  微观 (5维, μ1-μ5):
    μ1 entity overlap      (0.30) — 名词重叠
    μ2 causal chain        (0.25) — 因果连接词 (所以/因为/导致)
    μ3 anaphora            (0.20) — 指代回溯 (这个/那个/它)
    μ4 verb-object pair    (0.15) — 动宾对匹配
    μ5 modifier            (0.10) — 修饰语一致性

  融合: λ×宏观 + (1-λ)×微观, λ=0.6 (TiMem 文献)
  话题切换强制降级: 含话题转换词 → cohesion×0.3
```

### 2.2 业务影响

```
粘合度 > 0.7  → 同话题, 合并到同一 DiscourseBlock
粘合度 0.4-0.7 → 弱关联, 创建新 Block 但建立关联边
粘合度 < 0.4  → 话题切换, 新 Block 新分支
话题转换标记 → 强制低粘合, 即使其他维度高

此算法决定链 01 中 "水波展开" 的强度、
      链 02 中 "重复检测" 的阈值、
      链 03 中 "切分建议" 的断点位置
```

### 2.3 应在链 01 补充

链 01 §3.2 "水波展开" 的强度应引用 CohesionScorer 的 9 维分数，而非仅语义距离。

---

## 3. 缺口 ② — 温度模型 4 态

### 3.1 设计

```
当前链 01-04: 使用了 hot/warm/cold 三态描述
            ❌ 设计文档是四态: active → paused → cold → frozen

四态定义:
  active (活跃):  当前讨论中, 全量EDU + 上下文
  paused (暂停):  暂停但未结束, 完整EDU + 一级摘要
  cold   (冷却):  短期不会讨论, 二级摘要 + 关键实体
  frozen (冻结):  长期归档, 仅元数据 + 索引

状态迁移:
  active → paused:  用户话题切换 (粘合度 < 0.4)
  paused → active:  用户回到话题 (BGE匹配>0.8)
  paused → cold:    10 轮无访问
  cold → frozen:    50 轮无访问
  cold → active:    用户明确提及 (比 paused→active 更难, 阈值更高)
```

### 3.2 业务影响

```
链 02: 子图获取时, active块 = 全量, paused = EDU+摘要, cold = 仅摘要
链 03: 用户修改 cold/frozen 节点 → 需要升温
链 04: 持久化时, 温度决定 HCWA 分层:
        active → H, paused → C, cold → W, frozen → A
```

---

## 4. 缺口 ③ — HeaderInjector 代词消解

### 4.1 设计

```
当前: 没有提到代词消解

设计:
  User: "这个喝了很呛"
  系统: 向上查找 heading 层级 → 发现 "汽水分析讨论" 
  → 补全为: "汽水喝了很呛" → 正确语义分析

  实现: HeadingHierarchyInjector
    遍历 EDUs → 检测无主语/代词开头 → 向上查找最近 heading
    → 注入补全 → 向量化时有完整语义
```

### 4.2 应在链 01 补充

链 01 §2.1 "事件解构" 之后，应加入 HeaderInjector 补全阶段。

---

## 5. 缺口 ④ — 渐进式四级摘要

### 5.1 设计

```
当前链 02: 提到 L1/L2 摘要
            ❌ 设计文档是四级: v1 → v2 → v3 → v4

四级摘要:
  v1 (原文): EDU 原文, 不作压缩
  v2 (一级摘要): LLM 生成 20-40字, 含核心意思 + 行为链 + 因果链 + 关联链
                 信息丢失 ≤ 20%
  v3 (二级摘要): 同主题 5+ 轮 → 50-100字自然语言 + 完整行为推演图
                 元信息展开而非压缩
  v4 (归档摘要): 单一主题块冻结 → 仅主题标签 + 关键决策 + 索引
                 压缩率 > 50%

生成时机:
  v1→v2: 每轮生成 (Fast Path)
  v2→v3: 同主题积累≥5轮 且 距上次v3≥10轮 → Slow Path
  v3→v4: 温度=frozen 时触发
```

### 5.2 业务影响

```
链 02 §3.4: L1 → L2 级联应改为 v1→v2→v3 三级联动
链 03 §3.4: 切分后需重新生成 v2/v3
链 04 §2: MetaCognition 检测摘要漂移 → 触发重生成
```

---

## 6. 缺口 ⑤ — 对话树节点内建行为链

### 6.1 设计 (V3_1_BEHAVIOR_SUMMARY §3)

```
当前: 对话树节点只记录 topic + action
      ❌ 设计要求每个节点内建 behavior_chain / causal_chain / association_chain

升级后 DiscourseBlock:
  {
    topic: "监控讨论",
    edus: [...],
    chains: {
      behavior_chain:   ["用户确认缺失 → 询问原因 → 建议方案"],
      causal_chain:     ["延迟飙升 因为 无监控 → 无监控 导致 无法定位"],
      association_chain:["监控 ↔ Observer ↔ Metric ↔ Alert"]
    }
  }

行为链的来源:
  - Fast Path: 从对话文本中提取显式行为序列
  - Async Path: LLM 分析隐含行为因果
  - 存储: 每个 DiscourseBlock 携带自己的行为链片段
  - 聚合: L2 摘要将同主题的多个行为片段拼接为完整行为推演图
```

### 6.2 业务影响

```
链 01 §3: 子图获取时, 行为链嵌入对话树节点 → 不需要单独调用 BehaviorGraph
链 02 §2: 标注的 action 不仅描述对话类型, 也记录行为类型
链 03: 用户修改节点 → 对应的行为链也需标记 stale
```

---

## 7. 综合影响

| 缺口 | 影响链 | 修复方式 |
|------|--------|---------|
| ① 9维粘合度 | 链 01 §3.2 | 补充 CohesionScorer 在水波展开中的作用 |
| ② 温度4态 | 链 01-04 全部 | 统一使用 active/paused/cold/frozen |
| ③ HeaderInjector | 链 01 §2.1 | 在解构后加入补全阶段 |
| ④ 四级摘要 | 链 02 §3.4, 链 03 §3.4, 链 04 §2 | v1→v2→v3→v4 替代 L1/L2 |
| ⑤ 节点内建行为链 | 链 01 §3, 链 02 §2, 链 03 | DiscourseBlock 增加 chains 字段 |
