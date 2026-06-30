# DiscourseBlock Tree：文献参照与理论对标报告

> **目的**：将 DiscourseBlock Tree 设计方案与前沿文献进行系统性对比，确认理论来源、量化参照基准、以及可借鉴的工程实践。
>
> **文献覆盖**：
> - TextTiling / LCseg（词汇链话语分割，2003-2013）
> - Granularity-Aware Evaluation（粒度感知评估，2025/2026）
> - TiMem（时间-层次记忆树，ACL 2026 Findings）
> - MemGPT / Letta（操作系统式记忆层次，2023-2024）
> - BATS / TopicTiling（双聚类文本分割，2020）

---

## 1. 宏观对标：五大文献体系与我们的设计

| 文献体系 | 核心创新 | 与 DiscourseBlock Tree 的对应关系 | 我们的差异化 |
|---|---|---|---|
| **TextTiling / LCseg** | 基于词汇链的 cohesion 断崖检测，窗口相似度计算 | **宏观量化**的语义相似度基础（M1: embedding cosine）<br>**微观量化**的实体重叠基础（μ1: Jaccard） | 升维：从单一标量 cohesion → 宏观(4维)+微观(5维) 的解耦量化 |
| **Granularity-Aware Evaluation** | BOR 密度比、Purity/Coverage 诊断框架 | **动态粒度调节**的理论直接来源<br>过密/过疏的诊断标准 | 引入 BDI 作为实时调节信号，将静态评估指标变为运行时控制参数 |
| **TiMem (TMT)** | 五级时间-层次记忆树、渐进式整合、复杂度感知召回 | **渐进式摘要**（v1→v4）与 TiMem 的 level-specific consolidation 对应<br>**温度策略**（Hot/Warm/Cold/Frozen）与 TiMem 的层次搜索对应 | 粒度更细：TiMem 以"轮次/会话"为原子，我们以"EDU/话语块"为原子 |
| **MemGPT / Letta** | OS 式三层记忆（Core/Recall/Archival）、sleep-time 重组、function call 管理 | **温度策略**的硬件隐喻来源（RAM→disk→cold）<br>**渐进式压缩**的动机来源 | 额外引入"动态切分"作为第一层决策，MemGPT 无轮内切分能力 |
| **BATS / TopicTiling** | 双聚类 + LDA 主题信息、词向量窗口 | 可借鉴的**实现方法**（Python 重实现、窗口大小参数） | 不依赖 LDA 训练，使用预训练 embedding + 规则语义 |

---

## 2. TextTiling / LCseg：微观量化的基石

### 2.1 核心公式

**LCseg 词汇链得分**（Galley et al., 2003）：

$$
score(R_i) = freq(t_i) \cdot \log\left(\frac{L}{L_i}\right)
$$

- $freq(t_i)$ = 词汇链中术语重复次数
- $L$ = 对话/文本总长度
- $L_i$ = 词汇链跨度（越短越紧凑，得分越高）

**窗口 cohesion 计算**（TextTiling-style）：

$$
LexCoh(X, Y) = \cos\_sim(X, Y) = \frac{\sum_{i=1}^{N} w_{i,X} \cdot w_{i,Y}}{\sqrt{\sum_{i=1}^{N} w_{i,X}^2} \cdot \sqrt{\sum_{i=1}^{N} w_{i,Y}^2}}
$$

其中 $w_{i,\Omega}$ = 链 $C_i$ 重叠窗口 $\Omega$ 时的 $rank(C_i)$，否则为 0。

**边界检测**：在 cohesion 曲线的局部最小值处，计算深度得分：

$$
score(m) = \frac{LC(l) + LC(r) - 2 \cdot LC(m)}{2}
$$

- $l, r$ = 最小值 $m$ 两侧的局部最大值
- 深度越大，越可能是话题边界

### 2.2 实验效果

| 方法 | 数据集 | 指标 | 结果 | 基准对比 |
|---|---|---|---|---|
| LCseg | ICSI meeting corpus | WindowDiff | **0.35** | 比 C99 算法提升 **22.92%** |
| LCseg | Brown corpus (Choi) | Pk | 0.29-0.31 | 多种词汇链变体 |
| TopicTiling | BATS 自测 | Pk/WD | 中等 | 与 BATS 方法差距明显 |

**关键参数**（LCseg 调参结果）：
- $h = 11$（词汇链中断阈值，超过 11 个句子无出现则断裂）
- $k = 2$（分析窗口大小，每侧 2 个句子）
- $p_{limit} = 0.1$（边界选择概率阈值）
- $\alpha = 1/2$（阈值计算参数）

### 2.3 与我们的设计的对应

| LCseg 概念 | DiscourseBlock Tree 对应 | 升级点 |
|---|---|---|
| 词汇链（lexical chains） | **微观 μ1**: 实体重叠 Jaccard | 从"词重复"升级为"实体重复+语义关联"，兼容同义词 |
| 窗口 cohesion | **宏观 M1**: embedding cosine + 其他 3 维 | 从纯词汇升级为语义+意图+场景+情绪 |
| 局部最小值检测 | **cohesion_boundary 检测** | 相同算法，但输入是宏观+微观融合的复合得分 |
| 链断裂（hiatus） | **轮内切分**中的 EDU 边界 | 从"句子级"降级到"子句/EDU级"，更细粒度 |

**我们的借鉴**：
- 保留窗口比较（window size=2）作为微观 cohesion 的基础计算方式
- 将 LCseg 的"链得分"替换为"实体-关系图得分"（含因果、指代、修饰关系）
- 将"局部最小值检测"作为 `detect_cohesion_cliffs()` 的实现参考

---

## 3. Granularity-Aware Evaluation：动态粒度调节的理论锚点

### 3.1 核心发现（Coen et al., 2025/2026）

**论文标题**："When F1 Fails: Granularity-Aware Evaluation for Dialogue Topic Segmentation"

**核心命题**：F1 在粒度不匹配时失效——一个模型可能正确识别了所有粗粒度边界，但因为多切了几个细粒度边界而被 F1 惩罚。

### 3.2 三大诊断指标

| 指标 | 定义 | 诊断意义 |
|---|---|---|
| **W-F1** | 窗口容忍 F1（±1 message tolerance） | 边界放置的准确性 |
| **BOR** | Boundary Over-segmentation Ratio = \|P_pred\| / \|G_gold\| | 预测边界密度 vs 标注密度 |
| **Purity** | 每个预测段是否主要来自单一 gold 段 | 段内一致性（高 = 没切跨话题） |
| **Coverage** | 每个 gold 段是否被单一预测段捕获 | 段完整性（高 = 没漏切） |

### 3.3 五大失败模式（文献表格）

| F1/W-F1 | BOR | Purity/Coverage | 诊断 | 我们的调节策略 |
|---|---|---|---|---|
| High | ≈ 1 | High | **校准**（粒度匹配） | 维持当前阈值 |
| High | ≫ 1 | High purity | **过细分**（细粒度但合理） | 提升容量上限，允许更细切分 |
| Low | ≫ 1 | High purity | **粒度不匹配**（多切但切对了） | **关键场景**：降低 `global_split_threshold`，提升 BOR |
| Low | < 1 | High coverage | **欠细分**（粗于标注） | 降低 `global_split_threshold`，增加边界 |
| Low | ≈ 1 | Low | **检测失败**（边界放错/噪声） | 需要重新训练/调参 |

### 3.4 实验数据（论文 Table 10）

| 数据集 | W-F1 | BOR | Purity | Coverage | F1 |
|---|---|---|---|---|---|
| DialSeg711 | 0.767 | **2.53** | **0.962** | 0.651 | 0.434 |
| SuperSeg | 0.584 | 0.81 | 0.847 | 0.915 | 0.609 |
| TIAGE | 0.512 | 0.76 | 0.785 | 0.896 | 0.368 |

**关键洞察**：DialSeg711 上 BOR=2.53（严重过切），但 Purity=0.962（几乎每段都是纯话题）→ **这不是检测失败，是粒度不匹配**。

### 3.5 与我们的设计的对应

| 文献概念 | DiscourseBlock Tree 对应 | 工程化改造 |
|---|---|---|
| BOR（边界密度比） | **BDI**（Block Density Index） | 从"评估指标"变为"运行时控制参数"：每 10 轮计算一次，驱动阈值自适应 |
| Purity | **cohesion_internal** | 块内粘合度作为纯度代理 |
| Coverage | **entity_signature coverage** | 实体签名覆盖作为完整性代理 |
| 粒度不匹配诊断 | **动态粒度调节**的触发条件 | 将静态评估变为实时反馈控制 |

**我们的借鉴**：
- **核心诊断公式**：用 BOR 判断"切多了"还是"切少了"，用 Purity 判断"切对了还是切乱了"
- **阈值调节策略**：`BOR > 1.5 + Purity > 0.85` → 过切但合理，提升容量；`BOR < 0.6 + Coverage > 0.9` → 欠切，降低阈值
- **评估标准**：测试集报告 W-F1 + BOR + Purity + Coverage，不单独看 F1

---

## 4. TiMem：渐进式摘要与层次化召回的 SOTA 参照

### 4.1 核心架构（ACL 2026 Findings）

**论文**：TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents（arXiv:2601.02845）

**三大组件**：
1. **Temporal Memory Tree (TMT)**：五级层次（segments → sessions → days → weeks → profiles）
2. **Memory Consolidator**：分层整合，level-specific instruction prompts，无需微调
3. **Memory Recall Pipeline**：复杂度感知召回（Recall Planner → Hierarchical Recall → Recall Gating）

### 4.2 五级层次与我们的四级摘要对应

| TiMem 层级 | 时间粒度 | 内容 | 我们的 v1-v4 对应 | 差异 |
|---|---|---|---|---|
| **L1: Segments** | 单次对话 | 原始对话轮次 | **v1: 首句** | TiMem 保留完整原文，我们取首句（更轻量） |
| **L2: Sessions** | 一次会话 | 非冗余事件摘要 | **v2: 实体列表** | 类似，但 TiMem 用 LLM 生成摘要，我们用规则提取 |
| **L3: Days** | 一天 | 例行行为 + 反复兴趣 | **v3: 关键转折/决策点** | 我们的 v3 更关注话题演化而非时间累积 |
| **L4: Weeks** | 一周 | 行为特征 + 偏好模式 | —（我们无时间聚合层） | 这是跨会话聚合，我们当前设计在单会话内 |
| **L5: Profiles** | 长期 | 稳定人格/偏好/价值观 | —（无对应） | 用户画像层，我们可扩展但当前设计未包含 |

### 4.3 实验基准（SOTA）

| 基准 | 指标 | TiMem 结果 | 提升 |
|---|---|---|---|
| **LoCoMo** | Accuracy | **75.30%** | SOTA |
| **LongMemEval-S** | Accuracy | **76.88%** | SOTA |
| **LoCoMo** | Memory Reduction | **52.20%** | 召回记忆长度减少 |

### 4.4 召回机制（双通道评分）

$$
s(m, q, K) = \lambda \cdot s_{sem}(m, q) + (1 - \lambda) \cdot s_{lex}(m, K)
$$

- $s_{sem}$ = 语义相似度（embedding）
- $s_{lex}$ = BM25 词汇匹配
- $\lambda$ = 可调配重

这与我们的 **宏观 M1(embedding)** + **微观 μ1(实体重叠)** 的融合思路一致，只是 TiMem 用于检索，我们用于切分。

### 4.5 与我们的设计的对应

| TiMem 概念 | DiscourseBlock Tree 对应 | 关键差异 |
|---|---|---|
| 五级 TMT | 四级渐进摘要（v1-v4） | TiMem 以时间聚合，我们以语义密度聚合；TiMem 跨会话，我们当前单会话 |
| Memory Consolidator | **渐进式摘要升级** | TiMem 用 LLM instruction prompts 做分层整合；我们用规则+LLM 混合，v1-v3 规则，v4 LLM |
| Complexity-Aware Recall | **上下文构建**（build_llm_context） | TiMem 根据查询复杂度选择搜索层级；我们根据块温度选择注入精度 |
| 双通道评分（语义+词汇） | **宏观+微观量化** | 相同思想，不同用途：TiMem 用于检索，我们用于切分 |
| Sleep-time 后台重组 | **compress_cold_blocks()** | 相同动机：异步维护记忆层次 |

**我们的借鉴**：
- **渐进式整合策略**：TiMem 的 level-specific prompts 是优秀工程实践。我们的 v4 摘要可以借鉴其 prompt 模板：
  ```
  "将以下对话片段总结为不超过 50 字的命题级摘要，保留：
  1. 核心实体 2. 关键决策/结论 3. 未完成任务"
  ```
- **双通道评分的参数**：TiMem 论文未报告 $\lambda$ 具体值，但经验上 0.6-0.7 语义权重较优。我们的宏观/微观权重可借鉴：宏观 0.6，微观 0.4（当 embedding 质量高时）。
- **评估基准**：TiMem 的 52.20% 记忆长度减少是我们的目标基准。我们的上下文构建也应追求类似压缩率。

---

## 5. MemGPT / Letta：记忆层次架构的工程先驱

### 5.1 三层记忆架构

| 层级 | 类比 | 内容 | 寿命 | 我们的温度对应 |
|---|---|---|---|---|
| **Core Memory** | RAM | 用户画像、当前任务状态、Persona | 永久，始终注入 | Hot（活跃块完整原文） |
| **Recall Memory** | Disk Cache | 近期对话历史（context window 溢出部分） | 会话级，可检索 | Warm（祖先链 v3 摘要） |
| **Archival Memory** | Cold Storage | 长期归档，向量索引，按需检索 | 永久，异步 | Cold（v4 压缩摘要）+ Frozen（只保留索引） |

### 5.2 关键工程实践

1. **Function Call 管理**：LLM 通过 `archival_memory_search`、`core_memory_append` 等函数主动管理记忆。这要求 LLM 具备工具调用能力。

2. **Sleep-time 重组**：后台进程定期重新组织归档记忆，合并相似项，更新索引。这与我们的 `compress_cold_blocks()` 完全对应。

3. **Local Embedding**：使用 BAAI/bge-small-en-v1.5 做本地向量检索，不依赖外部 API。这与我们的 `EmbeddingEngine`（all-MiniLM-L6-v2 或 SHA256 伪向量）的设计一致。

4. **Raw Trajectory Storage**：MemGPT 存储原始轨迹文本而非预摘要，依赖检索时切片。这与我们的设计**不同**——我们主张主动渐进式摘要，而非被动检索切片。

### 5.3 与我们的设计的对应

| MemGPT/Letta 概念 | DiscourseBlock Tree 对应 | 工程借鉴 |
|---|---|---|
| Core/Recall/Archival 三层 | **Hot/Warm/Cold/Frozen 四级** | 更细的温度分级，增加 Frozen（只保留索引） |
| Function Call 管理 | 无直接对应（我们的 Agent 无工具调用） | 未来扩展：让 LLM 主动调用 `memory_search`/`memory_compress` |
| Sleep-time 重组 | **compress_cold_blocks()** | 相同动机，相同实现模式（后台异步） |
| BAAI/bge-small-en-v1.5 | **all-MiniLM-L6-v2 / SHA256 伪向量** | 类似的小模型本地嵌入策略 |
| Raw Trajectory | **v1 首句保留完整原文** | 我们的 v1 比 MemGPT 的 raw 更轻量，但保留了最近轮次 |

---

## 6. BATS / TopicTiling：工程实现的参数参照

### 6.1 BATS 方法要点

- **双聚类（Biclustering）**：同时聚类文档和词汇，发现共现模式
- **TopicTiling**：TextTiling + LDA 主题信息。在文本分割中，窗口内不仅比较词汇重叠，还比较 LDA 主题分布的相似度
- **实现参数**：window size = 2，LDA iterations = 500

### 6.2 与我们的设计的对应

| BATS/TopicTiling | DiscourseBlock Tree | 借鉴 |
|---|---|---|
| LDA 主题分布 | **意图类别 (M2)** | 用意图类别作为"主题标签"替代 LDA 主题，无需训练 |
| 窗口大小 2 | **分析窗口 $k=2$**（LCseg 参数） | 直接采用：相邻块比较时，每侧取 2 个 EDU |
| 500 iterations | 不适用 | 我们的 embedding 是预训练模型，无需迭代 |

---

## 7. 综合参照：我们的设计在文献坐标中的位置

### 7.1 理论坐标系

```
                          细粒度（EDU级）
                              ↑
                              │  DiscourseBlock Tree (本文)
                              │  TiMem (segments级)
                              │
         静态切分 ←───────────┼───────────→ 动态调节
                              │
                              │  LCseg / TextTiling
                              │  TopicTiling
                              │
                          粗粒度（轮次级）
                              │  当前 TopicTree
                              │  MemGPT (turn-level storage)
                              ↓

         单层结构 ←───────────┼───────────→ 层次结构
                              │
                              │  MemGPT / Letta (3-tier)
                              │  TiMem (5-tier TMT)
                              │  DiscourseBlock Tree (4-tier summary)
```

### 7.2 量化参照基准

| 指标 | 文献基准 | 我们的目标 | 差距分析 |
|---|---|---|---|
| **分割质量 (WD)** | LCseg: 0.35 (越低越好) | < 0.40 | 目标可行，需要中文适配的词汇链/实体链 |
| **准确率** | TiMem: 75.30% (LoCoMo) | > 70% (长期对话) | 需要构建中文对话分割测试集 |
| **记忆压缩率** | TiMem: 52.20% | > 50% (token 减少) | 渐进式摘要天然可达此水平 |
| **Purity** | BOR-aware: 0.85-0.96 | > 0.85 | 需要调参验证 |
| **端到端延迟** | 无直接文献 | < 5ms (轮内切分) | 纯规则路径可达成 |
| **召回速度** | TiMem 双通道: < 100ms | < 10ms (内存索引) | 我们的规模更小（单会话），可更快 |

### 7.3 可直接采纳的文献参数

| 参数 | 文献来源 | 建议取值 | 说明 |
|---|---|---|---|
| 窗口大小 $k$ | LCseg / BATS | **2** | 相邻块比较，每侧 2 个 EDU |
| 词汇链断裂 hiatus | LCseg | **11** | 11 个句子无出现则断裂。我们改为：5 个 EDU 无实体重叠则断裂 |
| 边界概率阈值 $p_{limit}$ | LCseg | **0.1** | 选择概率 > 0.1 的局部最小值作为边界 |
| 语义权重 $\lambda$ | TiMem 双通道 | **0.6-0.7** | embedding 相似度 vs 实体重叠的权重 |
| BOR 健康区间 | Granularity-Aware | **0.8 ~ 1.2** | 预测边界密度与期望密度的比 |
| 过切容忍 | Granularity-Aware | BOR > 1.5 + Purity > 0.85 | 允许细粒度细分，只要纯度够高 |
| 欠切诊断 | Granularity-Aware | BOR < 0.6 + Coverage > 0.9 | 需要更激进切分 |

---

## 8. 关键文献的工程化映射表

### 8.1 从论文到代码的映射

| 论文段落 | 算法/方法 | 我们的代码位置 | 实现方式 |
|---|---|---|---|
| LCseg §3.1: 词汇链构建 | 词重复检测 + 链断裂 | `micro_graph.py` | 实体链替代词汇链（同义词兼容） |
| LCseg §3.2: 窗口 cohesion | Cosine 相似度 | `macro_scorer.py` | embedding cosine + 意图/场景/情绪 |
| LCseg §3.3: 局部最小值检测 | 深度得分计算 | `cohesion_cliff_detector.py` | 相同算法，输入为复合得分 |
| Granularity-Aware §6: BOR | 边界密度比 | `granularity_regulator.py` | 运行时计算，驱动阈值调节 |
| Granularity-Aware §6: Purity | 段内一致性 | `block_cohesion_validator.py` | 块内 EDU 间平均 cohesion |
| TiMem §3.1: TMT | 五级层次树 | `discourse_block_tree.py` | 四级摘要树，单会话内 |
| TiMem §3.2: Consolidator | 分层整合提示 | `progressive_summarizer.py` | v4 触发 LLM 异步压缩 |
| TiMem §3.3: Recall | 双通道评分 | `context_builder.py` | 语义相似度 + 实体匹配 |
| MemGPT §2: 三层记忆 | Core/Recall/Archival | `temperature_manager.py` | Hot/Warm/Cold/Frozen 四级 |
| MemGPT §3: Sleep-time | 后台重组 | `cold_compress_worker.py` | 异步线程，每 60s 检查 |

---

## 9. 理论缺口：文献未覆盖的我们的创新

### 9.1 宏观-微观解耦量化

**文献现状**：所有文献（LCseg、TiMem、MemGPT）的 cohesion/相似度都是**单一标量**或**双通道融合**（TiMem 的语义+词汇）。

**我们的创新**：
- 首次将 cohesion 解耦为**宏观（整体语义）**和**微观（实体关系）**两个独立维度
- 四个象限决策（高-高/高-低/低-高/低-低）产生不同的路由行为
- 这是受认知编译器中"属性标签不丢失"原则的启发，文献中未见类似设计

### 9.2 认知编译器前置层

**文献现状**：所有记忆系统（TiMem、MemGPT、Letta）都假设输入是**干净的自然语言**，直接进行分割或检索。

**我们的创新**：
- **头文件引入（HeaderInjector）**：在切分前补全隐含实体，避免"这个喝了很呛"被当作空主语
- **语法分解（SyntacticDecomposer）**：提取主谓宾骨架，保留修饰语属性
- **三级模式（Fast/Hybrid/Full）**：根据输入复杂度选择处理路径，避免过度消耗
- 这是文献中**未覆盖**的前置层，灵感来自编译器设计（预处理→编译→链接）而非 NLP 流水线

### 9.3 动态容量调节

**文献现状**：TiMem 的层次是**静态时间驱动**（segments→sessions→days→weeks→profiles），MemGPT 的层级是**固定容量驱动**（core 始终注入，recall 溢出，archival 按需）。

**我们的创新**：
- **一家独大 → 再切割**：块内 cohesion 极高且 EDU 过多 → 自动分裂
- **主题过多 → 合并/提升容量**：子块过多且相邻 cohesion 高 → 自动合并
- **BOR 驱动的全局阈值自适应**：将评估指标变为运行时控制参数
- 这是文献中**未覆盖**的自适应粒度机制，更接近数据库的自动分片/合并策略

### 9.4 渐进式摘要的温度策略

**文献现状**：TiMem 的分层整合是**时间驱动**（每轮/每天/每周触发），MemGPT 的压缩是**溢出驱动**（context window 满时触发）。

**我们的创新**：
- **温度驱动**：Hot（不压缩）→ Warm（规则压缩）→ Cold（LLM 压缩）→ Frozen（只保留索引）
- 温度由**访问频率**和**时间衰减**共同决定，而非固定时间或容量
- 上下文构建时**混合温度**：活跃块完整原文 + 祖先 v3 + 兄弟 v4，形成动态精度的上下文注入

---

## 10. 结论：我们的设计在文献中的定位

**一句话定位**：
> DiscourseBlock Tree 是 **LCseg 的词汇链思想**（微观量化基础）+ **Granularity-Aware 的 BOR 诊断**（动态调节理论）+ **TiMem 的渐进式整合**（摘要策略）+ **MemGPT 的温度层次**（存储架构）+ **认知编译器的前置解析**（独特创新）的**融合与升维**。

**与每个文献体系的核心差异**：
- 比 LCseg/TextTiling：**多维度**（不是单一 cohesion，而是宏观+微观 9 维）
- 比 Granularity-Aware：**实时化**（评估指标变为运行时控制参数）
- 比 TiMem：**更细粒度**（EDU 级 vs 轮次级），**更前置**（编译器层）
- 比 MemGPT/Letta：**主动切分**（MemGPT 被动存储，我们主动分割）
- 比所有文献：**编译器隐喻**（头文件引入→语法分解→量化链接，这是软件工程而非 NLP 的范式）

**建议的下一步**：
1. **构建中文对话分割测试集**：用 50-100 轮真实对话标注话题边界，验证我们的 BOR/Purity 指标
2. **复现 LCseg 的中文适配版**：将词汇链替换为实体链，在测试集上建立 WD/Pk 基准
3. **对标 TiMem 的压缩率**：在相同对话长度下，比较我们的上下文构建 vs 全量历史的 token 数
4. **评估认知编译器的补全率**：统计"这个/那个"等代词在头文件引入后的正确补全比例

---

## 附录：参考文献速查

| 文献 | 作者 | 年份 | 关键页/节 | 核心内容 |
|---|---|---|---|---|
| TextTiling | Hearst | 1994 | 全文 | 词汇 cohesion + 窗口比较 |
| Discourse Segmentation of Multi-Party Conversation | Galley, McKeown, etc. | 2003/2007 | §3 LCseg 算法 | 词汇链 + 深度得分 + WD=0.35 |
| Topic Segmentation and Labeling in Asynchronous Conversations | Joty et al. | 2013 | §3.1.1 | LCseg 在异步对话的扩展 |
| When F1 Fails: Granularity-Aware Evaluation | Coen et al. | 2025/2026 | §6, Table 2, 10 | BOR + Purity/Coverage + 五大失败模式 |
| TiMem: Temporal-Hierarchical Memory Consolidation | Yu et al. | 2026 (ACL Findings) | §3, 实验部分 | TMT 五级树 + 75.30% LoCoMo + 52.20% 压缩 |
| MemGPT: Towards LLMs as Operating Systems | Packer et al. | 2023 | §2-3 | 三层记忆 + function call 管理 + sleep-time |
| BATS: Spectral Biclustering Approach | 多作者 | 2020 | §4.3 | TopicTiling 实现参数 (window=2, iter=500) |
| Letta Platform | Letta Inc. | 2024 | 架构文档 | Core/Recall/Archival 工程实践 + REST API |

