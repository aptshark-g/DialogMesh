# 上下文设计完整记录 — 与子图组合的上下文工程哲学

> 日期: 2026-08-03 | 性质: 设计精读完整记录（非审计）
> 组织框架（用户定义）: 上下文 = **与子图组合完成上下文工程哲学** ——
> 不是写更好的 prompt，而是构建更好的 Context；子图是跨链通信的核心织物，
> Context IR 是进入 Transformer 之前的信息组织方式。
> 配套: `AUDIT_ENTRY_20260803.md`（一轮现状）+ `DESIGN_IMPL_AUDIT_20260803.md`（二轮对照）

---

## 一、设计文档全景

| 文档 | 层级 | 核心内容 |
|---|---|---|
| `docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md` | 设计 | 域选择/预算/跨域引用/Context IR v2/子图修剪 |
| `docs/v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md` | 设计 | 双 Compiler、十个洞察、Context IR 核心概念 |
| `docs/v3.0/ENGINEERING_CONTEXT_MANAGER.md` | 工程实现 | v3 分层工作记忆 Hot/Warm/Cool/Cold |
| `docs/v3.0/design_context_window.md` | 工程实现 | 三层窗口 + 规则压缩 + PCR 集成 + 增量缓存 |
| `docs/v3.0/CONTEXT_COMPRESSION_DESIGN.md` | 设计 | MemGPT 渐进式摘要 + 依赖感知 + 持久化 |
| `docs/v5/DESIGN_THREE_PARADIGM_LLM_CONTEXT.md` | 设计 | 温度×距离×信息价值三范式注入 |
| `docs/BUSINESS_CHAIN_02_CONTEXT.md` | v6 链规范 | DS+BA+SC+IR 流水线 |
| `docs/BUSINESS_CHAIN_10_SUBGRAPH.md` | v6 链规范 | **子图 = 对话树子图 + 元认知子图（视角不同）** |
| `docs/v5/CONTEXT_GAP.md` | 状态报告 | 已证伪（见 AUDIT）|

---

## 二、核心命题：Context Engineering

### 2.1 问题定义（v4）
```
旧范式: 全部历史 → LLM → 回答（LLM 兼任数据库+摘要器+冲突仲裁器+调度器）
新范式: Memory → Reason Graph → Context IR → Token → Transformer

真正应该优化的不是"AI 怎么记住更多"，而是"进入 Transformer 之前的 Context 怎么构建"。
评估标准从覆盖率 → 信息密度。
```

### 2.2 十个洞察（核心摘录）
1. Memory 不是文档，是关系（Typed Edge）。
2. 记忆不是知识，是推理轨迹（Reason Graph，推理边为主干）。
3. Context Compiler 不是全文，是子图（50K 节点 → 500 token 任务子图）。
4. Transformer 只吃 Token 序列 → **序列化策略 = Context Engineering 的核心技术**。
5. 真正可优化的是 Transformer 前面的层（Prompt → Memory → Context）。
6. **Context IR = 为当前任务定制的信息组织方式；Graph 是 IR 的原料，不是 IR 本身**。
7. Event Log 懒合并（Spark 懒求值 / WAL / Git commit 类比，Checkpoint 批量 Merge）。
8. Memory Compiler 维护记忆（非实时、批处理、可规则化，LLM 只负责推理）。
9. 双 Compiler 分工: Memory=Git commit（Checkpoint 懒），Context=Git checkout（每 Query 实时）。
10. Memory 不是状态，是 Patch Chain（Base + Patch1 + Patch2...，O(1) 追加、可回放、延迟合并）。

### 2.3 双 Compiler 规格
| | Memory Compiler | Context Compiler |
|---|---|---|
| 触发 | Checkpoint（懒）| 每次 Query（实时）|
| 输入 | Event Log | Persistent Graph + 当前任务 |
| 输出 | 更新后的 Persistent Graph | Context IR |
| 优化目标 | 一致性和信息保真 | Token 预算内最大相关性 |
| 实现 | 规则为主 + LLM 冲突仲裁 | LLM + 子图算法 |

---

## 三、跨域编译（DESIGN_CROSS_DOMAIN_CONTEXT 完整规格）

### 3.1 域定义
```
域E (Engineering): 模块状态/依赖/约束       域C (Conversation): 对话树/话题结构
域P (Profile): 八维认知特征/操作偏好          域B (Behavior): 操作序列/行为模式
域K (Causal): 因果边/因果骨架
```

### 3.2 意图感知域选择矩阵（设计原文）
| 意图 | 主域60% | 辅域1 25% | 辅域2 15% | 策略 |
|---|---|---|---|---|
| task | E | B | P | 深度聚焦 |
| query | C | E | P | 话题锚定 |
| correction | B | E | K | 因果回溯 |
| discussion | P | C | E | 广度发散 |
| casual | C | P | — | 轻量组织 |
| topic_switch | C | B | P | 结构重建 |

### 3.3 预算模型（三层）
```
必要层 200 tokens（用户消息，不可裁剪）
策略层 300 tokens（跨域编译子图，意图感知分配 60/25/15）
弹性层 200 tokens（溢出，仅子 token 充足时）

耗尽处理: 域填不满 → 剩余给下一优先级域；全填不满 → 返还必要层；
策略层整体不足 → 降级摘要模式。

用户可定制（三层优先级）: 用户显式设置 > 用户习惯推断（UserProfile 第九维
context_budget_preference）> Provider 默认（DeepSeek 800-1000 / GPT-4 400-500 /
本地 Ollama 1500+ / 统一定价 500-700）。
```

### 3.4 Context IR v2 结构
```
CrossDomainContextIR {
  intent_category, domain_allocation[]（domain/role/budget_pct/budget_tokens）,
  entries[]（domain/type/content/cross_refs/source_events/confidence/estimated_tokens）,
  total_estimated_tokens, compile_strategy（primary_deep/balanced/summary_fallback）
}
```
- cross_ref 格式: `[DOMAIN:TYPE] content ^ref: DOMAIN.event_id = 关联说明`，双向指针。
- **核心原则: 传给 LLM 的不是多个独立 SECTION，而是有导航结构的子图网络。**

### 3.5 子图溢出修剪（11.2-11.6）
```
节点保留优先级 = α·frequency + β·recency + γ·betweenness（α/β/γ 按意图挂 DomainSelector）
四轮修剪: R1 电容排序(后30%) → R2 结构保护(betweenness>0.6 移除) →
           R3 时序修复(最近3轮移除) → R4 摘要压缩(域感知压缩, 仍超则扩到50%)
话题切换三步降落: 旧话题摘要压缩 → 结构保活(连接器不压) → 新话题展开
用户可察觉性: 压缩后系统标记 + 画像记录 context_overflow_behavior
```

---

## 四、与子图的组合（上下文工程哲学核心）

### 4.1 子图的本质（BUSINESS_CHAIN_10）
```
子图不是对话树的附庸 —— 它是跨链通信的核心织物。
共享数据层（对话树/行为/关联/工程/画像/参数/元认知日志）
  → 对话树子图（视角: 用户当前问题, 目的: 生成回复）
  → 元认知子图（视角: 系统质量+多链一致性, 目的: 审核+复盘）
```

### 4.2 对话树子图 token 分配（与 Context 组合的直接接口）
```
D 域(对话树) 35% | K 域(工程约束+模式) 20% | B 域(行为) 15% | R 域(关联) 10%
| P 域(画像) 10% | E 域(工程模块) 5% | F 域(子图反馈 OCEAN+MBTI) 5%
```

### 4.3 元认知子图 token 分配
```
M 域(元认知操作历史) 15% | V 域(版本 diff) 25% | E 域(多链证据) 30%
| I 域(惯性) 15% | P 域(画像) 10% | Q 域(审核对象) 5%   —— 默认 2000 tokens
```

### 4.4 Context + Subgraph 的组合哲学
```
ContextAssembler（多源组装）→ CrossDomainContextIR（统一表示）
  → SubgraphCompiler（水波扩展: 锚点出发 2 跳, max_nodes=50）
  → Pruner（预算内修剪）
  → to_prompt() → LLM

关系: Context 决定"LLM 应该看到什么/多少/什么优先级"；
      子图决定"这些信息以什么网络结构呈现"（cross_ref 指针 = 导航结构）。
      子图是 Context IR 的结构化载体 —— 两者组合 = 完整的上下文工程。
```

---

## 五、事件流粘合剂（跨域索引）

```
核心主张: Event Log 不只是审计日志 —— 是系统唯一权威索引（Single Source of Truth Index）。

跨域扩展流程:
1. 从 Event Chain 选取锚点 Event（最近 N 条）
2. 沿 Event ID 多跳扩展:
   对话树方向 → DiscourseBlock 父/子/兄弟
   工程链方向 → 模块依赖/监控/翻译状态
   行为链方向 → 前后同类事件模式
   画像方向   → 认知特征
3. 同一 Event 的不同域投影之间建立 cross_ref 指针
4. 基于意图优先级裁剪和预算分配

与传统多源聚合对比: 传统 = 分别查 UserProfile DB / ModuleRegistry / ConversationHistory 再拼接
（三个查询互不知道彼此关系）；事件流 = 只查 Event Chain + Event ID 索引，天然带关联。
```

---

## 六、分层工作记忆（v3 ENGINEERING_CONTEXT_MANAGER 完整规格）

### 6.1 四层结构
```
Hot Layer  (容量 3)  — 完整轮次记录（TurnRecord），内存 OrderedDict
Warm Layer (容量 7)  — 单轮摘要（TurnSummary: 意图类别+关键实体+结果状态），SQLite
Cool Layer (容量 20) — 多轮合并摘要（TopicSummary: 主题+关键决策+未解决+用户偏好），SQLite
Cold Layer           — 仅索引（ColdIndexEntry: topic_tag+关键决策+偏好更新），gzip JSONL

降级链: Hot→Warm（Hot 超 3 触发）→ Cool（Warm 每 3 合并）→ Cold（Cool 超 20 归档）
回热: rehydrate_cold(session_id, topic_id) → Cold→Cool（topic_id 精确匹配）
```

### 6.2 6 个 LLM 实例专属组装（v3 架构，已被 v4 域驱动取代）
```
PCR-LLM: 最近 1 轮 + PCR 历史
Intent-LLM: 最近 3 轮 + 实体历史 + 当前主题
Planning-LLM: 最近 3 轮 + 工具注册表 + 活跃主题 + 已执行计划
Meta-Cognitive-LLM: 最近 5 轮 + Cognitive Tree 最近 10 节点
Reflective-LLM: 全部历史（跨会话）+ 用户画像
Answer-LLM: 全部 4 层 + Topic Tree + Cognitive Tree（穿透层）
```

### 6.3 TokenBudgetManager（v3）
```
base_budget 8000；allocate(llm_name, min, max): 剩余>max→max；剩余<min→0；否则 80%
update_spent(字符/4 估算)；get_allocation_report（利用率/按 LLM 分配表）
```

### 6.4 诚实标记的简化项（S-01~S-05）
LLM 驱动压缩 / Token 精确计数 / 跨会话共享 / 自适应压缩率 / 语义回热 —— 均 Phase 2。

---

## 七、窗口管理（design_context_window 完整规格）

### 7.1 三层窗口
```
WindowConfig: hot_size=5, warm_size=15, compress_interval=5, max_tokens=4000,
              enable_llm_compressor=False
Hot: 最近 5 轮原始 → Warm: 6-20 轮规则压缩 → Cold: 更早轮次摘要（增量缓存）
增量: cached_summary + cached_cold_turns 复用，避免重复全量压缩
```

### 7.2 规则压缩保留矩阵
```
完整 user query / intent 标签 / entity / 认知画像更新 / 自适应阈值 → 必保留
完整 assistant 回复 → Warm 摘要 / Cold 丢弃（可丢失）
tool 调用详情 / 用户情绪 → Warm 丢弃（可丢失）
时间戳 → Hot/Warm 保留 / Cold 仅范围
```

### 7.3 冷摘要格式（供 PCR 感知）
```
"[历史摘要] 时间范围: ... | 用户画像: 专家度=.., 稳定性=.. | 主要意图: TOOL(15), ADVISOR(3)
 | 技术主题: 内存扫描, 反汇编 | 总对话轮数: 50"
PCR 识别到 [历史摘要] 标记 → 时间间隔因子降级
```

### 7.4 压缩对 PCR 各组件的影响适配
```
NoiseEstimator: 用 timestamp 而非轮数索引；冷摘要条目降级时间间隔权重
CognitiveProfiler: process_context 传 total_turns（EMA 基于真实轮数）
ExpectationIdentifier: 热窗口 5 轮覆盖 Tier2；温窗口保留 metadata.entities/intent_category
ComplexityEstimator: 基于冷摘要意图分布，非全量历史
```

### 7.5 触发条件
```
历史 > 20 轮 → 温窗口压缩 | > 100 轮 → 冷摘要 | tokens > 4000 → 紧急压缩
静默 > 30 分钟 → 会话归档 | 每 5 轮 → 增量压缩（后台异步）
```

---

## 八、MemGPT 渐进式压缩（CONTEXT_COMPRESSION_DESIGN 完整规格）

### 8.1 三层记忆（AOI 论文对应）
```
Layer 1 Recent Context (~2000t): 最近 5-10 步原始 REASON/ACTION/PARAM/RESULT
Layer 2 Compressed Memory (~1500t): 渐进式摘要（结构化 SUMMARY/FACTS/DEPENDENCIES）
Layer 3 Core Prompt (~500t): 永不压缩（系统提示/任务定义/安全约束/高置信度发现）
触发: 上下文达 60% 阈值；保留最新 2 步不压缩；二级压缩（Compressed 超 1500t）
```

### 8.2 依赖感知压缩（ContextWeaver）
```
DependencyGraph: step_id → action/result/critical（是否被后续依赖）
压缩选择: 保留关键依赖链 + 失败记录，压缩冗余步骤（重复扫描/失败尝试）
```

### 8.3 持久化结构
```
turns.jsonl（完整，永久）+ compressed.json（会话期）+ dependencies.json（会话期）
+ discoveries.json（高置信度，永久，跨会话复用）+ embeddings.db（向量检索相似会话）
```

### 8.4 4B 模型调优（速度优势）
```
80 tok/s → 压缩 2K tokens 仅 ~25s → 可更频繁压缩（每 5-10 步），阈值 50%，
keep_recent_turns=2, max_words=300, 二级压缩开启
```

---

## 九、三范式注入（THREE_PARADIGM 完整规格）

```
温度 Temperature (NOW←→PAST):   last_active_turn/access_count/recency decay
距离 Distance (FAMILIAR←→NOVEL): topic_tree distance/entity overlap/domain shift
信息价值 Info Value (COMMON←→RARE): entity_rarity/intent_novelty/action_deviation
三者正交 —— 同一块可同时 Hot·Near·Common 或 Cold·Far·Rare。

注入模式: A 结构化标签 [Block#3 temp:2 dist:0.8 value:0.9]
         B 优先级排序 P = α·temp + β·(1-dist) + γ·value（高 P 先注入，低 P 被截断）
         C 三元组自然语言（推荐）: [★重要] 时间/领域/价值 标注，LLM 自己决定关注

哲学: 不是算法替 LLM 决定，是算法给 LLM 提供结构化的注意引导。
```

---

## 十、设计要点摘录（供讨论）

1. **上下文工程哲学的落点**: Context 回答"LLM 应该看到什么/多少/什么优先级"；
   子图回答"以什么网络结构呈现"；两者组合才是完整的上下文工程。
2. **子图 = 视角而非数据**: 对话树子图（窄而深）与元认知子图（宽而浅）数据源相同、
   视角不同 —— 与「一个事实多视角」哲学一致。
3. **Event ID 是跨域 JOIN 键**: 设计反复强调 Event Log = 唯一权威索引，这是
   「事件流粘合剂」哲学 —— 也是当前实现最大缺口（从未实现）。
4. **压缩是有损但可控的**: 三范式注入让"正确的位置被截断"成为有损压缩的正确方式；
   MemGPT 保留关键依赖链；窗口保留矩阵明示可丢失项 —— 压缩哲学 = 信息分层。
5. **LLM 是推理引擎不是数据库**: 所有设计（IR/子图/压缩/预算）都围绕这一命题，
   把信息组织/关联/裁剪的工作在进入 Transformer 之前完成。
6. **冷热哲学贯穿**: Hot/Warm/Cool/Cold、温度范式、LRU、冷启动回退 ——
   时空局限性的复合考虑是上下文的底层律。

---

# 补充记录（第二轮精读）— 观察编译器 / 穿透层 / 统一持久化 / 推导与信息论压缩

> 本部分追加于 2026-08-03，补齐以下设计文档: `DESIGN_OBSERVATION_COMPILER.md`、
> `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（§5 穿透层）、`DESIGN_UNIFIED_PERSISTENCE.md`、
> `ENGINEERING_DATA_MODEL.md`（§7.3）、`DESIGN_DERIVATION_COMPRESSION.md`、
> `DESIGN_DERIVATION_COMPRESSION_V2.md`、`DESIGN_INFO_THEORETIC_COMPRESSION.md`、
> `DESIGN_TRACEABILITY.md`。

---

## 十、观察编译器（Observation Compiler）— 上下文的源头

### 10.1 定位：不是 Parser，是棱镜投影
```
统一 Event IR（白光）→ 棱镜（Compiler）→ 光谱（工程/行为/对话/记忆/画像）
多模态事件源: 对话 / UI 操作 / 代码变更 / 工具调用 / 配置变更 / 系统事件
其中很多没有语言文本 → 没有 intent，只有 action: drag, target: node42
```

### 10.2 五层认知递进（DMN/ECN 对应）
```
Layer 0 Reality（事实发生）→ Layer 1 Observation（各域感知，共存不互斥）
→ Layer 2 Interpretation（同域候选，竞争）→ Layer 3 Hypothesis（跨域收敛，Bayesian）
→ Layer 4 Knowledge（confidence>threshold 冻结 → Skill/Constraint/Pattern/Preference）

DMN = 发散（生成大量候选解释）；ECN = 收束（竞争收敛择优）
发散的不是"信息"，是"解释空间"——信息没增加，增加的是对同一事件的不同理解方式。
```

### 10.3 ObservationBundle（1:1 Event → 1:N DomainObservation）
```
Event(evt_001) → Bundle(bun_001) → [engineering, behavior, dialogue, memory, user, causal]
每个 DomainObservation 内含多个 Interpretation（同域内竞争）

核心区分:
  Perspective（跨域）= 共存不互斥，不淘汰
  Interpretation（同域）= 竞争，由 Hypothesis Engine 淘汰
  例: "Pipeline Changed"(工程) AND "User Dragged Node"(行为) 同时为真；
      工程域内部 "调整布局" vs "优化依赖" vs "修改规范" 竞争

原则: Observation 永不淘汰（不做置信度判断）；Interpretation 稍后竞争；
      Partial OK（部分域完成即可发布，后台补充）
```

### 10.4 与上下文的关系
- ObservationBundle 是 ContextAssembler 各 Source（observation/document/knowledge）的
  **数据原料** —— `source.py` 的 `_extract_bundle_text()` 正是从 bundle 提取搜索文本。
- 五域投影 = 跨域上下文的「光谱」哲学：同一事件在不同认知维度的呈现，
  各自完整各自独立，没有哪个更"正确" —— 与「一个事实多视角」一致。

---

## 十一、穿透层：Answer LLM 的综合上下文包（MULTILAYER_LLM §5）

```
AnswerContext = {
  用户层: user_input + user_profile(Track A+B) + topic_tree 活跃分支,
  系统层: algorithm_result + llm_result + fusion_mode,
  认知层: active_cognitive_branch(最近3-5节点) + system_confidence + known_uncertainties,
  约束层: response_constraints{ style / structure / max_length / honesty_required },
  记忆层: relevant_memories(当前话题相关记忆组块)
}
```

### 11.1 回答 LLM 的三特征
1. **双重身份**: 用户界面"客服" + 系统认知网络成员（思考进入 Cognitive Tree）。
2. **穿透性**: 读取所有层输出（算法/LLM/Cognitive Tree 活跃分支）综合生成回复。
3. **受控性**: 回复受系统约束（画像决定详细度 / Skill 模板决定结构 /
   Meta-Cognitive 决定置信度声明）。

### 11.2 与上下文的强关联
- **实时约束注入**: Planning-LLM 的任务计划结构注入回答提示词；
  Meta-Cognitive 检测到不确定性 → 要求声明。
- **幻觉缓解**: 系统置信度<0.7 必须声明不确定；Skill 模板约束结构；
  Cognitive Tree 回溯（引用推理链，找不到就"不知道"）；高风险回复 Meta 预审。
- 这印证「上下文工程哲学」: 回答 LLM 的输入不是裸 prompt，
  而是**用户+系统+认知+约束+记忆五层综合包** —— 与 CLI 现状（裸 prompt）的差距即在此。

---

## 十二、统一持久化（Unified Graph Store）— 上下文的存储底座

### 12.1 ContextWindow 数据模型（ENGINEERING_DATA_MODEL §7.3）
```
ContextWindow: hot_layer(TurnRecord, cap 3) + warm_layer(TurnSummary, cap 7)
               + cool_layer(TopicSummary, cap 20) + cold_index(ColdIndexEntry)
               + base_size(10) + complexity_factor(PCR调节) + user_preference_factor + token_budget(8000)
TurnRecord: turn_id/user_input/intent/response/timestamp/metadata
TurnSummary: turn_id/category/key_entities/result_status/timestamp
TopicSummary: topic_id/summary_text/key_decisions/unresolved_issues/user_preferences/start_turn/end_turn
ColdIndexEntry: topic_id/topic_tag/key_decisions/user_preference_updates
```

### 12.2 通用节点表 + 多粒度索引（RAG 大小块）
```
graph_nodes: node_id/node_type/domain/session_id/data/summary/l2_summary/
             activation_count/importance/tier(H/W/C/A)/source_events
三级粒度: 全文(data) / 摘要(summary) / 极简(l2_summary)
检索: Coarse scan(摘要快速扫描) → Full recall(全文精确加载)
```

### 12.3 分层存储 + 强化检索
```
H/W/C/A 四级（JVM GC 模型）: 升降基于 activation_count + importance
WaveQuery 扩展: 水波多跳 / 域过滤 / 层级过滤 / 粒度选择
三种强化: 问题预生成(generated_questions) / HyDE(假设文档嵌入) /
          混合检索(语义0.7 + 关键词0.3 双通路去重)
性能: 动态索引锚点(HotIndex SQLite partial index) / 主干染色(Rust betweenness)
```

### 12.4 分层存储写入流（ENGINEERING_PERSISTENCE）
```
写入: HOT→TieredStorageManager.put_hot(内存) / WARM·COOL→SQLite /
      COLD·FROZEN→archive_warm_to_cold(归档文件)
读取: Hot 命中返回 → Warm 命中并异步 put_hot → Cold 命中并 rehydrate_cold_to_warm + put_hot
```

---

## 十三、推导压缩三件套 — 上下文压缩的深层哲学

### 13.1 约束驱动推导压缩（V1: 四步算法）
```
哲学内核: 同一信号(低概率信息)，不同约束 → 相反结论
  卡尔曼滤波: 低概率=低权重(丢弃)   约束=正态分布, 追求准确性
  信息论:     低概率=高价值(放大)   约束=log分布, 追求信息价值
  结论: 不是"低概率"本身，是"约束框架"决定它的意义

压缩 ≠ 聚类:
  聚类压缩 → 主题群 → 主题词袋，丢失【监控缺失→延迟难定位】的因果推导链
  推导压缩 → 提取状态转移(a→b→c) → 归纳规则 → 逆推验证

四步: 提取状态转移 → 归纳推导规则(模式A/B/C) → 压缩为规则集(<200t/条) → 逆推验证
目标: 压缩率<5%；逆推覆盖率>80%；新鲜度=1-last_fired/current_turn
哲学: "压缩不是让信息变小——是让信息的约束结构显式化。聚类压缩的是内容,丢失了推导。"
```

### 13.2 发散→收敛启发链（V2: 修正规则归纳=过拟合）
```
规则归纳 = LSTM 窗口拟合 = 过拟合（从有限采样归纳确定性规则，零泛化）

正确路径:
  发散: LLM 无上下文猜测(temperature=0.8, K=3-5) → 产生预训练知识驱动的假设
  收敛: LLM 有上下文筛选(temperature=0.1) → 验证+置信度+拒绝理由
  启发链: 模式描述 + 适用条件 + 反例 + 推理路径（保留推导结构、可逆推、有泛化）

类比神经网络: 训练=随机态发散(梯度探索)，推理=约束下收敛(forward)，过拟合=发散不足
质量度量: 启发覆盖率 60-80%（不是100%——100%=过拟合）
生命周期: 覆盖率下降 → 重新发散 → 新启发链 → 替换
```

### 13.3 信息论温度×价值二维矩阵（V3: SummaryEngine 升级）
```
Shannon 自信息: I(x) = -log₂P(x) —— 稀有=高价值
温度(时间轴) × 价值(稀缺轴) 正交 —— 当前只有温度维 → 损失"罕见但冷"的高价值信息

信息价值 = 0.3·entity_rarity + 0.35·intent_novelty + 0.35·action_deviation

二维决策矩阵:
  HOT·High  → FULL_TEXT      WARM·High → V3_MILESTONE
  COLD·High → V3_MILESTONE   COLD·Low  → V4_LLM_COMPRESS
  FROZEN    → INDEX_ONLY（不注入，仅检索）

文献: Shannon(1948) / Rate-Distortion / TF-IDF·IDF / Focus(2024) / BM25·IDF /
      Perplexity-based Novelty
```

### 13.4 三件套的关系（压缩哲学演进链）
```
V1 约束驱动推导压缩: 压缩=让约束结构显式化（规则化，但过拟合风险）
  → V2 发散收敛启发链: 过拟合修正（LLM 发散+收敛，产出含反例的启发链）
  → V3 信息论二维矩阵: 决定"压缩到哪个粒度"（温度×价值 → 保留策略）
三者共同构成: 上下文的"信息分层 + 结构保留 + 粒度决策"完整哲学。
```

---

## 十四、TRACEABILITY 追踪 — 上下文/工程链相关设计点状态

### 14.1 与上下文相关
| 设计点 | 状态 | 说明 |
|---|---|---|
| Context 6 sources | ✅ | `context/source.py` |
| **Subgraph 跨链通信** | ❌ 零 | Meta 子图/Dialogue 子图/LLM 调用（与子图审计一致）|
| **Cold→Hot 回写** | ❌ 未实现 | Meta→Intent, Assoc→Context |
| Slow Path checkpoint | ⚠️ 框架存在 | trigger_checkpoint 未触发业务 |

### 14.2 与工程链相关
| 设计点 | 状态 | 说明 |
|---|---|---|
| **Engineering 约束推理** | ❌ 未接入 | ConstraintEngine, RecursiveMap |
| Planner Distillation | ❌ 未触发 | 蒸馏引擎, Skill 提炼 |
| Do-Calculus / Predictor/Rewarder | v3_2 | 因果/预测域 |

### 14.3 已吸收的等效替代（对工程链/上下文的启示）
```
PCR 离散标签(TOOL/ADVISOR/COMPANION) → V4.0 6-zone 连续空间（标签泛化）
PCR 硬编码关键词 → StructuralFeatures 语法特征（零硬编码红线）
Intent 独立 Parser → AssociationFunnel Layer1-3（意图=关联浅层）
Multi-Tier Pipeline → 5-layer Funnel（漏斗更通用）
Emotion 关键词 → BGE mood_profiles.yaml 向量（泛化）
```

---

## 十五、补充记录小结（上下文）

1. **上下文源头 = 观察投影**: ObservationBundle 五域共存 + 同域 Interpretation 竞争，
   是跨域上下文"光谱"哲学的数据基座。
2. **回答 LLM 的输入 = 五层综合包**: 用户/系统/认知/约束/记忆 —— 这是"上下文工程"
   的最终消费者视角，也是与当前 CLI 裸 prompt 的最大差距。
3. **压缩哲学三阶段**: 规则化（V1）→ 启发链（V2）→ 信息论粒度决策（V3），
   统一于"温度×价值"二维律 —— 与 `THREE_PARADIGM` 和统一持久化的 tier 体系同构。
4. **TRACEABILITY 实锤**: Subgraph 跨链通信、Cold→Hot 回写、Engineering 约束推理
   三大设计点在 v5 追踪中已明确标注"未实现" —— 与本次审计结论互证。
