# 竞品吸收设计文档

> 基于 MemWalker, Hermes-Agent, M-FLOW, MRAgent, VeritasGraph 五个项目的深度阅读。
> 每个吸收点标注：来源、映射到 DialogMesh 的模块、实现代价、优先级。
> 日期: 2026-07-10

---

## 目录

1. 来源追溯独立层（P0 — 已设计、未独立）
2. 指代消解前置（P0 — 新能力）
3. 冲突检测 + 版本追踪（P1 — 设计存在、未独立）
4. 技能自动创建模式（P1 — 新能力）
5. Pipeline Trace 结构化输出（P1 — 新能力）
6. 结构感知初始摄入（P2 — 新能力）
7. Cone Graph 动态检索深度（P2 — 设计可增强）
8. 因果发现自动化管线（P2 — 新能力）

---
## 1. 来源追溯独立层

**来源**：VeritasGraph (Attribution & Provenance Layer) + M-FLOW (Source Attribution + Traceability)
**优先级**：P0 — 已设计、未独立

### 现有状态

DialogMesh 的 Node 和 Edge 已有 source_events 字段（记录创建该节点/边的原始 Event ID）。
但在输出层从未显式暴露——最终用户看不到回答的溯源。Context Serializer 直接把 ContextModel 转为 prompt，不标注来源。

### 吸收内容

将来源追溯提升为 Context Compiler Pipeline 的独立子模块：
1. ContextModel 中的每个 SECTION 附带 source_events 引用列表
2. ContextSerializer 在生成 prompt 时，为每个信息来源追加 [src:Event_id] 引用标记
3. 最终 LLM 回答中，系统可以事后回溯：每个结论来自哪个 Event / 哪条推理边

吸收 VG 和 M-FLOW 共有的设计模式：来源追溯不是事后审计——它是生成阶段就嵌入的信息。

### 映射到 DialogMesh

- ContextModel 增加 source_refs: [UUID] 字段
- ContextSerializer 增加引用标记格式（如 [ref:E123, R456]）
- 不改变现有 pipeline 结构，仅增强 Context IR 的输出格式

### 代价

极低。修改 ContextSerializer 一个函数（约 30 行）。不需要新模块。

## 2. 指代消解前置

来源: M-FLOW (Coreference Resolution)
优先级: P0

现有状态: TopicBoundaryDetector 有指代回溯场景但依赖块级索引而非显式消解。

吸收内容: 在 Context Compiler 预处理阶段增加指代消解层。规则匹配先行(80% 常见指代), LLM 消解兜底。

映射: 新增 coreference_resolver.py, 在 TopicLocator 之前调用。输出 resolved_query + resolved_references。
代价: 中低。约150行规则代码 + 可选 LLM 调用。

## 3. 冲突检测 + 版本追踪

来源: M-FLOW (Conflict Detection + Version Tracking)
优先级: P1

现有状态: Memory Compiler 设计中有 ConflictResolver 步骤, 但未定义版本追踪数据结构。

吸收内容: 
1. 同实体矛盾: 两个 patch 对同一节点给出不同属性 -> 标记分叉(old_value, new_value_a, new_value_b)
2. 逆转关系: A->B 和 B->A 同时出现 -> 标记为双向关系
3. 版本追踪: 每次节点/边修改记录 old_value -> new_value + source_event + timestamp

映射: Memory Compiler 的 ConflictResolver 增加 VersionTracker 子模块。PersistentGraph 边/节点增加 version_history 字段。
代价: 中。需要新的 PatchVersion 数据结构 + ConflictResolver 逻辑增强(约200行)。

## 4. 技能自动创建模式

来源: Hermes-Agent (Automatic Skill Creation)
优先级: P1

现有状态: BehaviorGraph 的快速纠正路径只在内存中调整边权重, 不产生持久化产物。

吸收内容: 用户修正系统行为一次 -> 不只是更新权重, 而是抽象为可复用的 skill 规则, 持久化存储。
例如: 用户给 TopicDetector 手动加了监控 -> 系统自动生成规则: add_module(type=detector) -> also_add_monitor()

映射: EngineeringGraph 增加 SkillGenerator 子模块。产出物: 结构化 skill 规则(JSON/YAML), 存于 ColdIndexer 可检索。
代价: 中。需要新增 SkillGenerator 模块 + 与 ColdIndexer 的存储对接, 约300行。

## 5. Pipeline Trace 结构化输出

来源: VeritasGraph (Agent Studio pipeline trace)
优先级: P1

现有状态: EngineeringGraph 设计中有模块完整性的概念, 但无运行时 Pipeline Trace 输出。

吸收内容: 每轮对话输出结构化的 Pipeline Trace:
1. 格式: JSON per-stage (stage_name, inputs, outputs, duration_ms, status)
2. 参考 VG 的 Guardrails->Memory->KG->Headroom->Tools->Log 链式 Trace 设计
3. 我们的 stages: PCR->IntentParse->TopicLocator->SubgraphExtract->ContextIR->LLM->HallucinationCheck

用途: 消融实验(关闭某个模块看效果差分)、问题定位(哪个 stage 超时/异常)

映射: EngineeringGraph 增加 trace_start()/trace_stage()/trace_end() 接口。和现有的 structured_logger 对接。
代价: 低。复用现有 logger, 增加 TraceCollector 约100行。

## 6. 结构感知初始摄入

来源: VeritasGraph (document-centric ingestion)
优先级: P2

现有状态: Knowledge Layer 从 Event 逐步构建, 冷启动从零开始。

吸收内容: 当系统首次导入文档(设计文档/README/配置文件)时, 一次性构建 Knowledge Layer 初始骨架:
1. 解析文档结构(章节/段落/表格/代码块)
2. 以结构边界为单位构建初始 Knowledge 节点(而非按 token 窗口切分)
3. 节点间预建 parent/child 关系(文档树)
4. LLM 辅助提取关键实体和关系 -> 构建初始图边

映射: 新增 DocumentIngestionAdapter, 输入文档 -> 输出初始 Event Log 序列 + Knowledge 骨架。
代价: 中高。需要文档解析器(PDF/Markdown)+ LLM 实体抽取的适配, 约500行。

## 7. Cone Graph 动态检索深度

来源: M-FLOW (Cone Graph Architecture — 从抽象摘要到原子事实的锥形层级)
优先级: P2

现有状态: Context Compiler 使用固定 k 跳水波扩展, 不根据查询复杂度动态调整深度。

吸收内容:
1. 查询复杂度评估: 简单事实查询(1跳) vs 多跳推理(3-5跳)
2. 动态扩展深度: 简单查询 -> shallow(1-2跳) + 更细粒度的叶节点。复杂查询 -> deep(3-5跳) + 更粗粒度的摘要节点
3. 借鉴 Cone Graph 的锥形层级概念: 顶层(抽象摘要)->中层(结构化关系)->底层(原子事实)

映射: Context Compiler 的 SubgraphExtractor 增加 ComplexityScorer 集成, 根据复杂度选择扩展策略。
代价: 中。ComplexityScorer 已有雏形, 需增加检索深度决策逻辑, 约200行。

## 8. 因果发现自动化管线

来源: MRAgent (LLM 驱动因果发现: 文献扫描->暴露-结果对提取->MR验证)
优先级: P2

现有状态: CausalSubstrate 的因果骨架是手写的预定义模板, 不自动扩展。

吸收内容:
1. LLM 从 Event Chain 中自动扫描候选因果对(patten: A发生之后频繁出现B)
2. 候选因果对标为待验证, 存入 CausalSubstrate 的 hypothesis 池
3. 累积足够证据后(同一因果对出现 N 次), 提升为已验证因果边
4. 简化版: 不做 MRAgent 的统计验证(MR), 只做频次+结构验证

映射: CausalSubstrate 增加 CausalDiscovery 子模块。吸收 MRAgent 的管线模式但不引入统计方法。
代价: 高。需要新的 discovery pipeline + hypothesis 管理, 约400行。可先做简化版(仅频次验证)。

---

## 吸收优先级汇总

| 优先级 | 编号 | 吸收点 | 代价 | 映射模块 |
|:---|:---|:-----|:-----|:-----|
| **P0** | 1 | 来源追溯独立层 | 极低 | ContextSerializer |
| **P0** | 2 | 指代消解前置 | 中低 | coreference_resolver |
| P1 | 3 | 冲突检测+版本追踪 | 中 | ConflictResolver |
| P1 | 4 | 技能自动创建模式 | 中 | SkillGenerator |
| P1 | 5 | Pipeline Trace | 低 | TraceCollector |
| P2 | 6 | 结构感知初始摄入 | 中高 | DocumentIngestionAdapter |
| P2 | 7 | Cone Graph 动态深度 | 中 | SubgraphExtractor |
| P2 | 8 | 因果发现自动化 | 高 | CausalDiscovery |

---

## 附录: 五项目核心差异速查

| 项目 | 和 DM 最像的点 | DM 超越它的点 | 来源追溯 | 指代消解 | 冲突检测 | 技能创建 | 因果推理 |
|:-----|:---------------|:-------------|:-------|:-------|:-------|:-------|:-------|
| MemWalker | 树上导航阅读 | 三链+双Compiler | 无 | 无 | 无 | 无 | 无 |
| Hermes-Agent | Pipeline编排+本地部署 | 因果+画像+元认知 | 无 | 无 | 无 | 有* | 无 |
| M-FLOW | Cone Graph+树图混合 | Event Log+冷热分层 | 有* | 有* | 有* | 无 | 无 |
| MRAgent | 因果发现管线模式 | 通用因果骨架(非垂直) | 无 | 无 | 无 | 无 | 有* |
| VeritasGraph | 树图双引擎+来源追溯 | 交互流而非文档流 | 有* | 无 | 无 | 无 | 无 |

> (*) 标记: 该能力在对应项目中出现且被我们吸收。
