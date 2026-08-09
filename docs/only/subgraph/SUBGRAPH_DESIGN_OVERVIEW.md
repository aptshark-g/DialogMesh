# Subgraph 设计梳理 — 设计全景、演进与实现差距

> 梳理日期: 2026-08-01
> 目的: 把散落在多份设计文档中的子图设计理成一条线，对照 v4 实现找出差距。
> 设计源: BUSINESS_CHAIN_10（简版）/ DESIGN_CROSS_DOMAIN_CONTEXT（v3 完整版）/
>         DESIGN_V4_CONTEXT_ENGINEERING（水波）/ DESIGN_SEMANTIC_WORLD_MODEL /
>         merge/DESIGN_02_CONTEXT_AND_MEMORY（合并版）/ v5/DESIGN_SYNTHESIS
> 结论先行: **子图设计有一个完整且精密的 v3 版本（意图感知 + cross_ref + 三层预算 +
> 四轮修剪 + 三步降落），但 BUSINESS_CHAIN_10 只保留了"双视角 + 域分配"骨架，
> v4 实现又只做了"域抓取"，设计 → 落地一路衰减。**

---

## 一、子图的本质（各文档共识）

```
子图 = 相同数据池 × 不同视角 × 不同预算分配
```

- **不是数据，是视角**：对话树子图（窄而深，为生成回复）、元认知子图（宽而浅，
  为审核复盘）共享同一数据池，按视角不同做域选择与预算分配。
- **不是 RAG**：RAG 是"找到相关文本"；子图是"构造适合当前问题的局部世界"
  （DESIGN_SEMANTIC_WORLD_MODEL §1：Node 是子图的入口，不是终点）。
- **不是 prompt 工程**：不是写更好的 prompt，而是构建更好的 Context
  （DESIGN_CROSS_DOMAIN_CONTEXT 开篇）。

---

## 二、设计演进（四代）

| 代 | 文档 | 子图设计深度 |
|----|------|------------|
| v3 完整 | `DESIGN_CROSS_DOMAIN_CONTEXT.md` + `DESIGN_V4_CONTEXT_ENGINEERING.md` | **最完整**：意图感知域选择、cross_ref、三层预算、四轮修剪、三步降落、Context IR v2 |
| v3 合并 | `merge/DESIGN_02_CONTEXT_AND_MEMORY.md` | 保留 v3 全部 + 三级召回（Intent→Subgraph→ReferenceUnits→RawCode）、Persistent Graph 多尺度 |
| v4 简版 | `BUSINESS_CHAIN_10_SUBGRAPH.md` | **衰减**：只剩双视角 + 域分配百分比，丢掉 cross_ref/修剪/意图矩阵 |
| v5 合成 | `v5/DESIGN_SYNTHESIS.md` | 复述"双视角公式"（D40+B15+A25+P10+E10 / M15+V25+E30+I15+P10+Q5），无深化 |

**关键判断**: v3 是设计的"完全体"，后续文档是面向实现的简化，但简化丢掉了
子图最核心的两个机制——**cross_ref 指针网络**（让 LLM 看到跨域叙事而非孤立块）
和**结构感知修剪**（预算内保留子图完整性）。

---

## 三、设计核心要素（v3 完全体）

### 3.1 意图感知的域选择矩阵（§4.2）

| 意图 | 主域 60% | 辅助1 25% | 辅助2 15% | 策略 |
|------|---------|----------|----------|------|
| task | E(工程) | B(行为) | P(画像) | 深度聚焦 |
| query | C(对话) | E(工程) | P(画像) | 话题锚定 |
| correction | B(行为) | E(工程) | K(因果) | 因果回溯 |
| discussion | P(画像) | C(对话) | E(工程) | 广度发散 |
| casual | C(对话) | P(画像) | — | 轻量组织 |
| topic_switch | C(全树) | B(行为) | P(画像) | 结构重建 |

**域选择不是硬编码**（§4.3）：用户画像修正历史可覆盖默认矩阵，
AdaptiveParameter 调节意图-域映射权重。

### 3.2 cross_ref 指针网络（§6）

```
[E:MODULE] ModuleA
  status: monitor_missing, translation_ok
  ^ref: B.event_87 = 用户前3轮连续调整此模块
  ^ref: P.profile = 偏好可视化调试而非日志
```

- cross_ref 是**域间指针**，双向，告诉 LLM"不同域指向同一事实"
- LLM 收到的不是文档，是**可导航的子图网络**
- Context IR 每条 entry 带 source_events + confidence + estimated_tokens

### 3.3 三层预算（§5）

| 层 | 预算 | 内容 |
|----|------|------|
| 必要层 | 200 | 用户消息，不可裁剪 |
| 策略层 | 300 | 跨域子图，意图感知分配（60/25/15） |
| 弹性层 | 200 | 溢出用，预算充足时才启用 |

预算可用户化（§10）：Provider 自适应（DeepSeek 800-1000 / GPT-4 400-500 /
本地 1500+）→ 用户习惯推断（追问→上调，嫌啰嗦→下调）→ 显式设置。

### 3.4 编译策略（§7.2）

`primary_deep`（主域填满）/ `balanced`（均衡）/ `summary_fallback`（摘要降级）。

### 3.5 四轮修剪（§11.3，结构完整性核心）

1. 电容排序：activation_count 后 30% 为候选
2. 结构保护：betweenness > 0.6 的跨域连接器移除出候选
3. 时序修复：last_accessed < 3 轮的新节点移除出候选
4. 摘要压缩：按域类型压缩（DiscourseBlock→L2 摘要、ModuleState→状态标记...）

节点保留优先级 = α·activation + β·recency + γ·betweenness（α/β/γ 挂意图类别）。

### 3.6 三步降落法（§11.4，话题切换重组）

1. 旧话题摘要压缩（L2 Summary，保留话题锚点 + cross_ref）
2. 结构保活（betweenness > 0.6 连接器不压缩）
3. 新话题展开（默认 2-3 跳，仍超预算则对新话题四轮修剪）

### 3.7 三级召回（merge §4.6）

```
Level 1: Intent → Subgraph (~300 nodes, ~500 tokens)
Level 2: Subgraph → Reference Units (签名+docstring, ~300 tokens)
Level 3: Reference Units → Raw Code (top 5-10, ~200 tokens/function)
```

---

## 四、v4 实现 vs 设计要素差距（AST 实测）

| 设计要素 | v4 实现 | 判定 |
|---------|--------|:---:|
| 双视角（dialogue/meta） | compile_dialogue / compile_meta | ✅ |
| 域抓取（D/K/E/B/P/F / V/M/I/Q） | 有（部分域空） | ⚠️ 部分 |
| alloc 预算分配 | 硬编码 {D:0.35,...} | ⚠️ 硬编码非配置 |
| **cross_ref 指针** | **无** | ❌ |
| **意图感知域选择矩阵** | **无**（intent 参数收了不用） | ❌ |
| **四轮修剪** | **无** | ❌ |
| **三步降落（话题切换）** | **无** | ❌ |
| **Context IR v2 / compile_strategy** | **无**（assemble_prompt 简单拼接） | ❌ |
| **Event ID 跨域索引** | **无**（不沿事件流扩展） | ❌ |
| **三级召回** | **无**（直接域抓取） | ❌ |
| Serializer 分离 | assemble_prompt（简陋） | ⚠️ |

**实现只覆盖了设计 ~30%**：域抓取 + 预算分配（硬编码）有了，但子图的灵魂
（cross_ref 网络、意图感知选择、结构修剪、话题重组）全部缺失。

---

## 五、与 PCR §5 协同的落点

DESIGN_PCR §5 要求子图提供 `pull_prior(domain_scope) → SubgraphPrior`
（PCR 定域口径 → 子图反哺预期上下文先验）。这个接口的设计基础：
- domain_scope.domains 应来自**意图感知域选择矩阵**（v3 §4.2），而非硬编码 alloc
- 反哺的 coordinate_bias 可理解为"子图对该域的预期上下文信号强度"——
  对应设计中的 domain confidence/activation 聚合
- 只有先补上意图矩阵 + 域抓取真实化，pull_prior 才有真实输入

---

## 六、结论

1. **子图设计不缺，缺的是实现**：v3 完整设计（意图矩阵/cross_ref/修剪/降落）
   至今零实现，v4 只做了域抓取。
2. **衰减路径清晰**：v3 完全体 → BUSINESS_CHAIN_10 简版（丢 cross_ref/修剪）
   → v4 实现（再丢意图矩阵）→ 生产还只挂了一半 registry。
3. **修复不能只修接线**：P0 补注册只是让"残缺的域抓取"能跑；真正符合设计的
   子图需要按 v3 要素重建——至少补 cross_ref + 意图矩阵 + 结构修剪。
4. **pull_prior 依赖设计回补**：先有意图感知域选择，pull_prior 的 domain_scope
   才有意义。

---

## 七、讨论结论与待拍板点（2026-08-01 讨论记录）

> 本节为设计讨论后的固化记录，非设计本身。

### 7.1 讨论确认的事实

1. **审计深度修正**：初版审计只查了"实现断链"（双 registry / CLI API 错配），
   未把"子图设计本身"理出来；补读设计源后确认——设计不缺，实现缺。
2. **设计核心是视角不是数据**：子图 = 相同数据池 × 不同视角 × 不同预算分配；
   最值钱的机制是 cross_ref 指针网络（让 LLM 看到跨域叙事）和结构感知修剪
   （预算内保子图完整性），这两者在 BUSINESS_CHAIN_10 简版里就丢了。
3. **实现覆盖率 ~30%**：双视角 + 域抓取 + 硬编码 alloc 有；意图矩阵/cross_ref/
   四轮修剪/三步降落/Context IR/Event 索引/三级召回全缺。
4. **pull_prior 不是独立接口**：它依赖意图感知域选择矩阵先落地，否则
   domain_scope 的 domains 没有真实语义来源（DESIGN_PCR §5.4 也点名了
   "domains 由主题树域 + 关联链规则枚举"，与 v3 意图矩阵同源）。

### 7.2 拍板结果（2026-08-01 用户拍板）

| # | 决策项 | 拍板 |
|---|--------|------|
| 1 | 施工范围 | **建完整**：按 v3 设计要素完整实现，不做半个 |
| 2 | 建造方式 | **在 v4 原本基础上改造**：复用 compile_dialogue/compile_meta 双视角骨架，补齐缺失要素，减少不兼容 |
| 3 | 质量基线 | 对标下一代 agent，质量优先；设计若有不足后续再演进，**先把现有设计实现到匹敌** |
| 4 | 施工主文档 | 产出 `DESIGN_SUBGRAPH.md`（对齐 DESIGN_PCR.md 模式） |

### 7.3 施工顺序（拍板后）

```
① DESIGN_SUBGRAPH.md（施工主文档：v3 设计缩编 + 落点清单 + 执行顺序）
② P0 接线：B registry 补注册 + CLI 修正（子图首次真实运行）
③ v4 改造：alloc 配置化 → 意图感知域选择矩阵 → cross_ref → 结构修剪
④ pull_prior 接口（PCR §5 双向协同）
⑤ 死代码归档 + 黄金样例集回归
```
