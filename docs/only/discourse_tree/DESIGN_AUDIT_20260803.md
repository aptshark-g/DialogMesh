# 对话树设计文档审计（阶段三）— 2026-08-03

> 范围：15 篇设计文档 + 3 篇博客（`docs/blog/`）精读；对照阶段一代码盘点（`AUDIT_ENTRY_20260802.md`）+ 关键接口探针（2026-08-03 实测）。
> 定位：本文件是阶段四「内核拍板」的备料——只做调查与对照，不拍板。
> 严重度：🔴（设计资产本身也是分裂的——3 层 15 篇 + 3 博客未收敛成一份权威设计）

---

## 一、设计资产地图：三层演进脉络

### 1.1 第一层：对话树本体设计（v1 → v2 → 链01 修正）

| 文档 | 规模 | 定位 | 关键内容 |
|------|:---:|------|------|
| `design_discourse_block_tree.md`（v1）| 867L | 概念版 | 三阶段编译器（HeaderInjector→SyntacticDecomposer→Quantizer）、宏观4维+微观5维量化、动态粒度（BDI/BOR）、渐进式四级摘要、与 TopicTreeV2 集成 |
| `design_discourse_block_tree_v2.md`（v2）| 1306L | "实现就绪版" | v1 的精确接口化：伪代码、文献权重表、数据模型 dataclass、测试矩阵（11 单测+5 集成）、里程碑 M1-M10、回退开关 |
| `BUSINESS_CHAIN_01_CONVERSATION_TREE.md`（链01）| 235L | **v3 修正** | 四路径调度归属（C 层 Fast / B 层 Async / Slow 持久化）、C/B 层分离（C 用上一轮 B 结果）、子图编译集成到 ContextCompiler、HCWA=持久化归档分层、剪枝=设计建议 |

**关键演进事实**：v2 自称"实现就绪版"，但链01 在其后做了 v3 架构修正——两代文档基于**不同的架构假设**（见 §三.7），且 v3 修正**没有回流**到 v2。

### 1.2 第二层：工程/对标文档

| 文档 | 规模 | 内容 |
|------|:---:|------|
| `LITERATURE_REF_DISCOURSE_BLOCK_TREE.md` | 397L | LCseg/TextTiling、Granularity-Aware(BOR/Purity)、TiMem、MemGPT/Letta、BATS 的逐项映射 + 可直接采纳参数表 |
| `ENGINEERING_TOPIC_TREE.md` | 909L | TopicTree 操作层（Builder/Operations/SwitchDetector/Integrator/CrossRef）+ 事务性 flush + 简化项 S-01~S-05 + 待讨论 D-01~D-05 |
| `Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md` | 342L | 与 Context-Agent（arXiv:2604.05552）逐维度对标：最大差距=上下文构建（活跃路径全量+非活跃分支摘要）；补强建议 P1-P4 |
| `DESIGN_TOPIC_TREE_GRANULARITY.md` | 131L | L1/L2/L3/L-root 距离衰减摘要 + Token 预算分配 + 与 Subgraph 分工 |
| `TOPIC_TREE_DISCUSSION.md` | 593L | **5 个模糊点的决议**：①温度vs距离=双视角并行不融合 ②缓存失效=关系块元信息+懒加载 ③分支定义=多视角糅合交给 LLM ④刷新时机=行为驱动、纠错=P0 ⑤Token预算=学习结果三维协同 |
| `TOPIC_TREE_GAP.md` | 23L | 接入后差距：分支切换/摘要压实已修，有效实现率 ~70% |

### 1.3 第三层：业务链/认知管线定位

| 文档 | 规模 | 对话树相关 |
|------|:---:|------|
| `BUSINESS_CHAIN_01_INTENT.md` | 344L | 8 阶段 Intent Pipeline，PCR 调控 5 信号（expectation/noise/complexity/noise_source/prompt_style）——对话树的 primary_intent 来源候选 |
| `BUSINESS_CHAIN_01_UNIFIED_INTENT.md` | 145L | 5 层统一意图（结构→句法→语义→语用→时序→因果），T0/T1/T2 分级 |
| `BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md` | 394L | 递归收敛快匹配（熵/峭度/信息缺口/指纹固化）——主题匹配 Tier0 替代 |
| `BUSINESS_CHAIN_2.1_TOPIC_TREE.md` | 88L | 主题树状态机 + 接入现状：feed_turn ✅ / context injection ✅ / 分支切换 ❌ / 双层摘要 ❌（45%） |
| `DESIGN_01_COGNITIVE_PIPELINE.md` | 508L | 五层认知模型（Reality→Observation→Interpretation→Hypothesis→Knowledge）+ 四路径调度；**对话树 = Dialogue 域的 L1/L2 Summary 消费者** |

---

## 二、设计 ↔ 实现对照（核心差距）

> 实现侧代号沿用阶段一：A=单体 `compiler/discourse_block_tree.py`（engine 主用）、B=拆包 `discourse_block_tree/`、C=compiler 独立拆件、D=孤儿 `discourse/models.py`。

| 设计概念（v2 位置） | 设计契约 | 实现位置 | 状态 | 差距说明 |
|---|---|---|---|---|
| 三阶段编译器（§4） | 一条管道：inject→decompose→quantize | C（完整 327/402/242L）+ A（薄壳 46/75/150L）+ B（缩水 40/47/103L）| ⚠️ | **设计是"一条管道"，实现是"三套"**。C 的 `SyntacticDecomposer.decompose()` 返回 `List[ParsedClause]`；A 的返回 `List[EDU]`——接口类型都不一致 |
| `ingest_turn(turn_index, user_query, parsed_clauses, cohesion_scores)`（§8.3）| Manager 接受编译器三阶段输出 | B 实际：`ingest_turn(turn_index, text)`；A 实际：`feed(text, session_id, history)` | ❌ | **设计契约从未被实现**。B 把切分内聚到了 Manager 内部（text 进→块出），A 则完全不用 ingest_turn 语义 |
| 决策函数（§4.3/§5.2）| 单阈值 total>0.75/<0.25（§4.3）+ 四象限（§5.2）| A：`RouteDecision`（continue/fork/gray_zone）+ `is_extreme` 0.75/0.25 单阈值 | ⚠️ | 四象限的 `attach` 决策未实现（见 §三.2 双决策矛盾） |
| 宏观4维+微观5维量化（§4/§5）| 权重表 M1-M4/μ1-μ5，λ=0.6 | A `MacroMicroQuantizer`（自带 `_bge_similarity`）；C `quantize()`（pseudo_embedding 兜底）| ✅ | 实现比设计更重：A 自带 BGE embedding，设计只写"可选" |
| 渐进式四级摘要 v1-v4（§7）| 首句→实体→演化→LLM 命题压缩 | B `models.ProgressiveSummary`（upgrade_v2/v3/v4）；A `DiscourseBlock.summarize()` | ✅ | B 严格按 v2 设计；A 是独立实现 |
| 动态粒度 BDI/BOR（§6）| BOR 驱动阈值自适应 | A `DiscourseBlockGranularityRegulator`（_compute_bor/_adapt_threshold）；B `granularity_regulator.py` | ✅ | 两套并存；BOR 期望边界是拍脑袋假设（§三.8） |
| 上下文构建（§7.2/§8）| 温度策略：Hot 原文+Warm 祖先 v3+Cold 兄弟 v4 | A `build_context`（依赖 **B** 的 SummaryEngine——跨套拼装）；B `build_context` | ⚠️ | 链01 修正后对话树只是 ContextCompiler 数据源，不再"直接给 LLM"——设计-架构断层 |
| 指代回溯（§10 场景3）| `find_block_by_reference` | A 有同名方法；B `find_reference`/`resolve_reference` | ✅ | 双套都有 |
| cross_ref / group_ref | 设计模型 §7/§8 **无专章** | B `CrossReference`/`GroupReference` 完整；D 极简版 | ⚠️ | **设计缺失**：ref_type 语义/创建时机/来源/衰减只在博客出现（§四.1） |
| 温度模型（§2.2）| active→cold(10轮)→frozen(30轮) | A `update_temperature`；B `_update_temperature` | ✅ | 时间阈值驱动——与博客"电容模型=激活计数"哲学相悖（§四.2） |
| 冷压缩（§7）| `compress_cold_blocks` 后台异步 | A `_cold_worker`/`_schedule_cold_compress` 线程 | ✅ | 实现有后台线程 |
| 与 TopicTree 集成（§9.1）| DiscourseBlock→TopicNode 映射 | 链2.1：feed_turn ✅ / context injection ✅ / 分支切换 ❌ / 双层摘要 ❌ | ⚠️ | 有效实现率 45%（2.1 章）~70%（GAP 文档）——**两文档数据冲突** |
| 与 ContextCompiler（链01）| 子图编译集成 ContextCompiler；对话树区块更新在 Async | 实现待核查（阶段二/五） | ❓ | 链01 v3 修正未落到 v1/v2，实现是否按新架构待查 |

---

## 三、设计内部矛盾（审计重点发现）

### 3.1 状态机：v1 5 态 vs v2 4 态
- v1 §2：`active / paused / resumed / cold / frozen`（5 态，含 resumed）
- v2 §2.2 + §8.2：`active / paused / cold / frozen`（4 态，**resumed 消失**）
- **影响**：attach/回溯是对话树核心场景（博客、链01、Context-Agent 对标全在讲"回到刚才那个"），v2 却删掉了 resumed——被 attach 的块只能标 active？语义丢失。

### 3.2 v2 内部双决策函数（最重要矛盾）
- §4.3 `MacroMicroQuantizer.score()`：`total = 0.6*macro + 0.4*micro` → 单阈值（0.75 continue / 0.25 fork / 灰区）
- §5.2 `route_decision(macro, micro)`：**四象限**（高-高 continue / 高-低 attach / 低-高 continue_or_link / 低-低 fork）
- **行为差异**：macro=0.7, micro=0.3 → total=0.54 走灰区（需 LLM）；四象限判 attach（直接挂接）。文档未说明哪套优先。
- 实现 A 用了单阈值（无 attach）——**四象限决策从设计到实现都悬空**。

### 3.3 三阶段顺序矛盾
- v1 §3 图：inject→decompose→quantize；v1 §9.2 数据流代码：`stage2.decompose()` 先于 `stage1.inject()`——**同一文档自相矛盾**
- v2 §3 图：inject→decompose→quantize（顺序统一）
- 接口类型：C 的 decompose 返回 `ParsedClause`，A/B 用 `EDU`——"inject 输出喂给 decompose 还是反过来"在不同套里实现不同，无统一契约

### 3.4 摘要层级三套体系并存（职责未划清）
| 体系 | 层级 | 维度 | 出处 |
|---|---|---|---|
| 对话树四级摘要 | v1 首句 / v2 实体 / v3 演化 / v4 命题 | 时间+温度 | v1/v2 |
| 主题树分层摘要 | L1 细 / L2 段 / L3 跨分支 / L-root 骨架 | **距离衰减** | DESIGN_TOPIC_TREE_GRANULARITY |
| 主题树双层摘要 | L1 分支级 / L2 跨分支 | 分支粒度 | 链 2.1 |
- TOPIC_TREE_DISCUSSION 决议"温度 vs 距离双视角并行"，但对话树 v1/v2 只实现温度维度——**决议未回流到对话树设计**。

### 3.5 对话树定位矛盾：记忆树 vs 推理树
- 博客（design_thinking）："对话树首先是推理树，其次才是记忆树""是思考的工作台，不是记忆系统"
- v1/v2 设计：大量内容在讲摘要/压缩/存储/温度/容量——**做成了记忆结构**
- 链01：对话树区块更新在 Async，作为 ContextCompiler 数据源——"供数据"而非"主持推理"
- 三份材料对"对话树到底干什么"的答案不同，且都没说明推理属性（位置信号、焦点管理、推导链）如何落代码。

### 3.6 温度驱动：时间阈值 vs 激活计数（博客电容模型）
- 博客：遗忘=电容放电，**不计衰减只计使用**（activation_count，零算力）
- v2 §2.2：`10 轮未访问→cold`、`30 轮未访问→frozen`——**时间/轮数驱动**
- 实现：`access_count` 字段存在，但状态转换用轮数阈值。设计未贯彻博客哲学；且与行为链 `activation_count`（已在行为链施工落地）不一致。

### 3.7 链01 v3 修正未回流（架构断层）
v2 基于旧假设："对话树自己 `build_llm_context()` 直接给 LLM"。链01 修正：
- 对话树是 ContextCompiler 的数据源（子图在 Async 预编译，Fast 只取）
- C/B 层分离：C 层用上轮 B 层缓存的意图
- HCWA 是持久化归档分层，不是运行时缓存
- 剪枝=设计建议（非已有设计）
- **矛盾**：v2 说"实现就绪版"，但按链01 它基于过时架构。实现 A 的 `build_context()` 仍按 v2 思路直接组上下文——新旧架构在代码里并存。

### 3.8 BOR 自适应是"伪自适应"
- 文献 BOR = 预测边界数 / **人工标注**边界数
- v2 §6.2：`expected_boundaries = len(children) * 0.5`——纯拍脑袋假设
- 设计 §10.1 自己也承认"在没有人工标注的情况下用熵变检测作为代理"，但代码实现直接用了 0.5 系数——**没有代理、没有标注、没有 Ψ 估计**，阈值自适应是空转。

---

## 四、博客哲学 vs 设计文档张力（用户点名）

### 4.1 `chapter1_conversation_tree.md`（对话树概念引入）— 基本已落地
- 树-图混合（cross_ref 指针 0/1/>1）→ B models 有 ✅
- 三级边界（L0 硬/L1 软/L2 隐式）→ segmenter 有软边界 ✅
- GroupReference 超边 → B 有 `add_group_reference`/`find_activated_groups` ✅
- 温度管理 + 三级摘要 → 对应 v1-v4 ✅
- 与其他系统对比 + 吸收表 → LITERATURE_REF 对应 ✅
- **缺口**：cross_ref 的 ref_type 语义（analogy/continuation/correction/see_also/behavior_similar）、创建时机、来源（manual/auto_entity/auto_graph）只在博客描述——**设计文档没有专章**。

### 4.2 `chapter1_design_thinking.md`（为什么是树不是图）— 张力最大
| 博客哲学 | 设计文档实际 | 张力 |
|---|---|---|
| 对话树是推理树/思考工作台 | v1/v2 做成了记忆/摘要/存储结构 | 定位冲突（§三.5）|
| 电容模型=激活计数替代时间衰减 | v2 用"10 轮/30 轮"时间阈值 | 驱动方式冲突（§三.6）|
| 树的形状=思考形状（收敛/发散/位置信号） | 设计未落"位置信号/焦点管理"到代码接口 | 推理属性悬空 |
| Tree-Graph Hybrid=给树加粗主干 | cross_ref 有实现但设计缺章 | 概念有、设计无 |

### 4.3 `chapter2_relation_over_prompt.md`（v4 认知系统）— 接口未对齐
- v4 认知管线：Event → Observation（多域投影）→ Hypothesis → Knowledge → Skill
- Dialogue 域消费者 = **对话树 L1/L2 Summary**（DESIGN_01_COGNITIVE_PIPELINE §3.3）
- Event kind 路由：`dialog.message → dialogue, memory, user`
- **差距**：对话树设计（v1/v2）输入是"原始文本 feed"，认知管线设计输入是"Observation/Dialogue 域产物"——**两套设计的输入契约从未对齐**。对话树该吃原文还是吃 Observation？无答案。

---

## 五、与兄弟模块接口现状

| 兄弟模块 | 设计声称 | 实现/现状 | 缺口 |
|---|---|---|---|
| PCR | 链01 INTENT：expectation/noise/complexity 调控 8 阶段（0% 接入）| 对话树 v1/v2 完全没提 PCR 输入 | 对话树该不该受 PCR 调控？设计真空 |
| 意图 | 链01 INTENT/UNIFIED：primary_intent 来源 | v1 说 SyntacticDecomposer 提取；链01 说 B 层 LLM 意图分析 | 双来源未统一 |
| 主题树 | 链2.1：feed_turn ✅ / context injection ✅ / 分支切换 ❌ / 双层摘要 ❌（45%）| GAP 文档说 70% | **两文档数据冲突，需实测** |
| 子图 | 链01：子图编译=ContextCompiler 内部阶段；对话树子图 Async 重编译 | 设计有；实现待核查 | 对话树→子图数据流未验证 |
| 行为链 | 博客：DiscourseBlock.cross_refs 引用 BehaviorGraph edge_id（松耦合）| 设计文档无此描述 | 松耦合接口设计缺失 |
| 元认知 | — | 未见对话树设计提及 | 元认知→对话树的裁决/修正关系空白 |
| 持久化 | 链01 §5 修正网关（NodeAnnotationStore、只追加元数据边、不改变拓扑）| 实现 event/storage.py cold store 写入 | 修正网关是否实现待查 |

---

## 六、待拍板清单（阶段四备料）

1. **权威版本**：以 v2 为基 + 链01 v3 修正回流，还是重新凝练一份"对话树内核设计"？（一内核多门面哲学）
2. **决策函数**：单阈值 vs 四象限 vs 双维可配置矩阵（与 PCR zone 决策同型问题；attach 决策必须落地）
3. **状态机**：5 态（v1）vs 4 态（v2）——**resumed 必须保留**（attach 场景核心）
4. **温度驱动**：时间阈值 vs 激活计数（博客电容模型；建议与行为链 activation_count 对齐，双因子）
5. **对话树定位**：记忆树 vs 推理树——决定 build_context 职责边界（自摘要 vs 只供数据给主题树/子图/ContextCompiler）
6. **输入源**：原文 feed vs Observation Compiler Dialogue 域（认知管线输入契约）
7. **摘要层级归一**：对话树 v1-v4 / 主题树 L1-L3+Lroot / 链2.1 双层——三套体系合并方案
8. **PCR/意图接口**：primary_intent 来源定一、PCR 调控是否接入对话树
9. **cross_ref 设计补章**：ref_type 语义/创建时机/来源/强度衰减（博客有、设计无）
10. **BOR 伪自适应**：需要真实标注或 Ψ 估计期望边界，否则去掉自适应
11. **测试矩阵**：v2 §11.1（11 单测+5 集成）vs 实际 3 套小测试——阶段五按设计补全
12. **分裂归一**：A/B/C/D 四套 → 一内核多门面（阶段四内核拍板后，B 或 C 为内核，其余门面/归档）

---

## 七、阶段三结论

1. **设计资产丰富但未收敛**：3 层 15 篇 + 3 博客，v1/v2/链01 基于不同架构假设，TOPIC_TREE_DISCUSSION 的决议未回流到对话树本体设计。
2. **设计-代码差距集中在 6 处**：ingest_turn 契约从未实现、四象限 attach 悬空、温度驱动与博客哲学相悖、摘要层级三套并存、cross_ref 设计缺章、认知管线输入契约未对齐。
3. **两处"伪"设计**：BOR 自适应空转（期望边界拍脑袋）、设计声称 embedding 可选但实现已自带 BGE。
4. **推荐路径**：阶段四先凝练"对话树内核设计"草案（吸收 v2 + 链01 修正 + 博客哲学 + 讨论决议），再拍板内核与门面——避免继续在 4 套实现上叠新设计。

---

*本文件由阶段三设计文档审计产出，配套阶段一 `AUDIT_ENTRY_20260802.md`（实现盘点）、阶段二（实现审计，待开工）。*
