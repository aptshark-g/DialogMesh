# 对话树设计阅读完成记录（补充轮）— 2026-08-03

> 目的：补读 AUDIT_ENTRY 原 15 篇之外的直接相关设计文档（15 篇），并沉淀本轮新增发现。与 `DESIGN_AUDIT_20260803.md`（第一轮审计结论）互补。
> 状态：**对话树相关设计文档 30 篇全部精读完成**（清单见 `AUDIT_ENTRY_20260802.md` §六.6）。

---

## 一、本轮补读清单（15 篇）

| # | 文档 | 核心贡献 |
|---|------|---------|
| 1 | `BUSINESS_CHAIN_AUDIT_DIALOGUE_TREE.md` | 对话树 5 缺口（①9维粘合度 ②温度4态 ③HeaderInjector ④四级摘要 v1原文/v2一级/v3二级/v4归档 ⑤节点内建行为链）|
| 2 | `DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md` | 修正网关：拆分不可逆只依赖 Tier0，标注可逆进 NodeAnnotationStore；图=柔、树=刚 |
| 3 | `LITERATURE_CORTEX_CONVERSATION.md` | **设计源头**：主题切分→行为因果链→预测+纠错即训练→v3.1/3.2/3.3 演进 |
| 4 | `BUSINESS_CHAIN_03_USER_EDIT_TREE.md` | NodeEditRecord 区块链式 diff；切分最复杂（摘要级联）；警告分级 |
| 5 | `design_cognitive_compiler.md` | **三阶段源头**：decompose→inject→cohesion（非 v2 图所示 inject→decompose）+ DualStructure 双结构 |
| 6 | `DESIGN_INTERACTION_MODEL.md` | **链=注解层不嵌入树边**；Event Layer=唯一事实源；Conversation Projection 边=follow_up/elaborate/switch_to |
| 7 | `DESIGN_CROSS_DOMAIN_CONTEXT.md` | 对话树=域C；意图感知域选择矩阵（query→C 主域等）；预算 60/25/15；子图四轮修剪 |
| 8 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` | 双树：Topic Tree（用户）+ Cognitive Tree（LLM 心智，10 节点/8 边）+ 三层验证 + ADR-010~016 |
| 9 | `DESIGN_FULL_CONCEPT.md` §5.2-5.4 | 宪法级：Topic Tree=长期 EMA；Context Window=Hot/Warm/Cool/Cold 分层压缩；对话状态机 |
| 10 | `DESIGN_V4_COGNITIVE_INTEGRATION.md` | Bridge 3: DiscourseBlock[v3_summary] → MemoryExtractor + TagLayer → SubgraphCompiler |
| 11 | `MEMORY_LANDSCAPE_VS_MAINSTREAM.md` | Enhanced Notes = DiscourseBlock.raw_text；XML Memory Cards 6 类型 |
| 12 | `DESIGN_THREE_PARADIGM_LLM_CONTEXT.md` | 温度·距离·信息价值三轴正交；模式 C（自然语言标签）推荐——**罗盘式给 LLM 的设计源头** |
| 13 | `DISCUSSION_PARALLEL_REUSE.md` | PCR=关联链 L3 粗处理；IntentParser=L1-2 粗处理；PCR∥Intent 并行化 |
| 14 | `DESIGN_HYBRID_ARCHITECTURE.md` | 热路径直连（8 链）+ 冷路径 EventSourcing（Meta+Association，含 DISCOURSE_UPDATED 事件）|
| 15 | `DESIGN_SYNTHESIS.md` | 全貌：对话树子图 D40%/B15%/A25%/P10%/E10%；26+27 篇 ENGINEERING 全"工程待实现" |

---

## 二、本轮新增发现（第一轮 DESIGN_AUDIT 未覆盖）

### 2.1 关键矛盾：链=注解层 vs 节点内建行为链
- `DESIGN_INTERACTION_MODEL.md` §4 明确：**行为链/因果链/工程链是关系的注解（Annotation），不是树的边属性**；树的边只表示语义关系（follow_up/elaborate/switch_to）；"新增链类型不影响现有树结构"。
- `BUSINESS_CHAIN_AUDIT_DIALOGUE_TREE.md` 缺口⑤ 却要求：**DiscourseBlock 内建 chains 字段**（behavior_chain/causal_chain/association_chain），"子图获取时行为链嵌入对话树节点，不需要单独调用 BehaviorGraph"。
- **两份设计直接冲突**：注解层（解耦、独立演化） vs 内嵌字段（聚合、免查询）。→ 待拍板（与 A9 行为一等公民、INTERACTION_MODEL 的 Projection 哲学相关）。

### 2.2 三阶段顺序源头确认（解决第一轮 §三.3 矛盾）
- 认知编译器源头（design_cognitive_compiler §3）：**decompose（先拆子句）→ inject（再补全 ParsedClause 主语/宾语）→ cohesion（量化）**。
- v2 对话树设计 §3 数据流图写的是 inject→decompose→quantize（文本级注入再拆）——**与源头设计相反**。
- 实现 C（compiler 拆件）：SyntacticDecomposer 返回 `ParsedClause`、HeaderInjector 返回 `InjectionResult`——**C 遵循源头顺序**（decompose 先），A/B 遵循 v2 顺序。→ 内核拍板时需定顺序。

### 2.3 DualStructure（双结构）——第一轮遗漏的重要组件
- 认知编译器 §4.4：**树型逻辑视图（话题层级）+ 时空事实视图（严格时序 timeline）+ 虚拟边（时序冲突补丁 TEMPORAL_INVERSION）**。
- 这正是 A12/A17 在对话树的落点：事实轨（Event Log）不可改、逻辑轨（Projection）可重组——"经历不可改、解释可变"。
- 现有实现（A/B）无此组件。→ 内核吸收项。

### 2.4 三范式上下文 = "罗盘式给 LLM"的设计源头
- `DESIGN_THREE_PARADIGM_LLM_CONTEXT.md`：温度（时间）⟂ 距离（空间）⟂ 信息价值（稀缺），三轴正交；推荐模式 C——块注入时带自然语言标签 `[Hot·Near·High]`，LLM 自己决定关注度。
- 与用户此前讨论的"罗盘式给 LLM、维度可换、简单规则减少维度量"完全同构。→ 内核输出端（缩放建议）可直接采用此模式。

### 2.5 双树认知架构（Topic Tree 用户 / Cognitive Tree LLM 心智）
- `DESIGN_MULTILAYER_LLM_COGNITIVE`：对话树（用户侧）与 LLM 心智树（推理侧）**物理分离**，通过 `cog_refs`/`topic_refs` 交叉引用；Cognitive Tree 节点生命周期 CREATED→VALIDATED/INVALIDATED/SUPERSEDED，版本不覆盖。
- 佐证 A5 定位：对话树服务"用户在聊什么"，Cognitive Tree 服务"LLM 在想什么"——推理工作台属性在 LLM 侧有独立载体。

### 2.6 ContextCompiler 域选择给了对话树"数据源"精确接口
- 意图感知域选择：`query→C(对话)主域`、`discussion→P主+C辅`、`casual→C主`、`topic_switch→C主`——对话树在多数意图下是主域或辅助域。
- 预算 60/25/15；子图四轮修剪（电容→结构→时序→摘要）；话题切换三步降落（旧话题 L2 摘要+连接器保活+新话题展开）。
- 链01"对话树只是数据源"的修正在此有完整落地规格。

---

## 三、与第一轮审计的合并结论

| 主题 | 第一轮（DESIGN_AUDIT） | 本轮补充 | 合并状态 |
|---|---|---|---|
| 推理 vs 记忆 | A5 × A15 职责分离 | 双树架构佐证（用户树 vs LLM 心智树）| 定位收敛：推理工作台在用户侧 + 心智侧 |
| 三阶段顺序 | v1 §9.2 与 v2 §3 矛盾 | 源头=decompose→inject→cohesion | 顺序有了权威答案 |
| 链与树关系 | 缺口⑤ 内建 chains | INTERACTION_MODEL 注解层 | **新增待拍板矛盾** |
| 上下文构建 | v2 自己 build_llm_context 直接给 LLM | 三范式标签 + ContextCompiler 域选择 | 输出端形态清晰（罗盘式）|
| 双结构 | 未发现 | 认知编译器 DualStructure | **新增吸收项** |
| 温度驱动 | 时间阈值 vs 激活计数 | FULL_CONCEPT Context Window 分层（Hot/Warm/Cool/Cold）| 记忆侧分层确认 |

---

## 四、对 KERNEL_ABSORPTION 草案的增量修正建议

1. **三阶段顺序**：定 `decompose → inject → cohesion`（源头设计为准），v2 的文本级注入图废弃；
2. **链与树关系**：倾向 INTERACTION_MODEL 注解层方案（A9 行为一等公民=独立数据源，非嵌入树的字段）——但保留块级 `chains` 作为**缓存视图**（注解的物化，非事实源）备选；
3. **DualStructure 吸收**：对话树内核增加"事实轨（timeline）+ 逻辑轨（树）+ 虚拟边"三层——直接落地 A17 git 式记录；
4. **输出端采用三范式标签**：`[温度·距离·价值]` 标签注入，替代 v2 的纯温度分组截断；
5. **ContextCompiler 接口**：对话树暴露 `get_domain_C(意图类别)` 域视图（域选择矩阵的 C 域实现）。

---

*本文件与 DESIGN_AUDIT_20260803.md、KERNEL_ABSORPTION_20260803.md 共同构成阶段三设计审计完整资产。*
