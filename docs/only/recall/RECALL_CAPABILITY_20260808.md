# 统一召回能力接口 — 施工 + 哲学化 + 文献依据（2026-08-08）

> 状态: 第一批施工完成（GAP-R1/R2/R5/R6 部分）| 第二批待排（A18 反馈持久化/
> 关联链深度/LLM 挑选/前端展示）
> 关联: COMPLETENESS_GAP_INVENTORY §五（R 系列）、GLOBAL_PHILOSOPHY_FILTER
> B2-3（召回能力底座）、A12（约束空间）、A18（参数自适应）

---

## 一、已施工（`core/agent/recall/recall_service.py`, 9 测试 + HTTP 验证）

```
RecallService.recall(query, intent=None, top_k, sid, use_hyde=True)
  → 混合锚点（BGE 向量 0.9 + BM25 0.7 + SPO 约束投影 0.85 + HyDE 0.8 +
     关联链 0.75, 可学习置信度）→ k-hop 扩散（对话树 parent/child,
     hierarchical 0.8/hop）→ 融合排序（score × source_confidence × 温度）
feedback(hit_id, useful)  — A6 后验 ε=0.02 调整来源置信度（GAP-D4 落地雏形）
weights()/set_weight()    — A18 参数白盒 + 用户感知调节
```

**哲学化（A12 约束空间 + 状态转化）**:
- 切分 = 语法补全（代词闭环: 块内最近主语补全它/他/这）→ SPO 提炼
  （`SyntacticDecomposer` → subject/predicate/obj）
- 块 = 约束投影 {SPO 三元组 + 原文 + 温度}
- 召回 = SPO 结构对齐（谓语 0.5 / 主语 0.3 / 宾语 0.2 加权）+
  词法/语义/问题扩展多路
- 扩散 = 转化投影导航（parent/child 关系边 k-hop）

**接线**:
- ChunkStore 解孤儿（R2）: discourse 块原子自动喂入（hash 去重）
- 内核端点 `/v6/recall?query=&sid=&top_k=`（三级 page-in 前置）
- CLI `dm recall <query> [--top-k N] [--weights]`

**实测**（真数据, sid=b84e1b45）: query "pi agent 怎么做" →
`bm25 0.7 / diffusion 0.504 / vector 0.45` 三路命中, 1004ms。
测试: 9/9（融合排序/BM25/SPO 对齐/扩散/反馈自适应/clamp/代词闭环）。

## 二、踩坑（防复发）
1. **`apply_patch` 重复函数定义** — 同一函数补两次, 后定义遮蔽前定义
   （Python 取最后一个）；`inspect.getsource` 是定位神器
2. PowerShell 发中文消息 → v3_sessions 存损坏文本（`?` 字符）—
   测试数据污染, 非代码 bug; 中文一律 apply_patch 或 UTF-8 文件
3. `-LiteralPath *.json` 不展开通配符
4. Warm 文件 Windows 锁竞态 → `_discourse_ensure` 加载重试 3 次

## 三、文献依据（2026-08-08 联网查证, clash 代理）

| 论文/方向 | 出处 | 与设计的关系 |
|---|---|---|
| HyDE "Precise Zero-Shot Dense Retrieval without Relevance Labels" | arxiv 2022 (Gao et al.) | question 召回: LLM 展开假设文档再检索 — 已实现 `_expand_questions` |
| GraphRAG "From Local to Global" | arxiv 2024 (Edge et al.) | 锚点→子图→社区→QFS — 本接口的锚点→扩散→组装同构 |
| Event-QA "Event-Centric QA over Knowledge Graphs" | arxiv 2020 | 事件中心检索 = 状态转化投影（A12 Transition 一等公民）的现实版本 |
| Structure-Mapping Theory of Analogy | Gentner 1983 (Cognitive Science, 非 arxiv) | 类比 = 关系结构对齐而非特征相似 — **SPO 约束投影对齐的理论锚点** |
| Scripts/Event Schemas | Schank & Abelson 1977 | 转化链检索的经典来源 |
| Do-Calculus / 因果结构 | Pearl (已在 A22 设计内) | 因果 = 约束空间中稳定投射 |

> 设计文档已吸收: `merge/DESIGN_02_CONTEXT_AND_MEMORY.md:148`（HyDE 原文 +
> 混合检索 0.7/0.3）、`context/DESIGN_FULL_READ §12.3`（问题预生成/HyDE/
> 混合检索）、`BUSINESS_CHAIN_01:126`（水波展开, CohesionScorer 9 维决定强度）

## 四、我的判断（用户要求直说）

1. **方向对**: SPO 结构对齐有 Gentner 硬理论支撑; 混合锚点 + 溯源置信度 +
   A18 自适应 = 正确骨架
2. **防哲学化过度**: 约束空间是组织框架不是算法 — SPO 是一路信号（0.85）
   不是主导; 直接事实召回词法/向量往往已够
3. **验证纪律（A18）**: SPO 一路到底强多少, 必须黄金示例集 + 真实反馈说话,
   不能"感觉好" — 下一批建召回黄金集（20-30 条真实 query）

## 五、第二批待排（记录不施工）
```
R1 完整: subgraph_compiler 11+ getattr 改走 recall 接口
R3 溯源置信度持久化（update_source_credibility 接 feedback_log）
R4 搜索引擎路（修查询词: query 原文 + 扩展）
R5 完整: WaveQueryEngine（GraphStore BFS）+ 关联链边扩散
R6 完整: HyDE LLM 扩展在真实网关下的验证
R7 LLM 挑选器（候选 ≤30 → 一次挑选）
R8 前端召回白盒展示（来源/置信度/扩散路径）
召回黄金集: 20-30 条 query → 期望命中, 对比带/不带 SPO
```
