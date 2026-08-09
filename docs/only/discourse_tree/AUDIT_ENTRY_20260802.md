# 对话树审计入口 — 2026-08-02/03（🔴 最严重模块：5 套实现 + 断链）

> 状态: **阶段一资产盘点 ✅ / 阶段二实现审计 ✅（IMPLEMENTATION_AUDIT_20260803.md）/ 阶段三设计文档审计 ✅（DESIGN_AUDIT + DESIGN_READ_COMPLETE）/ 阶段四内核拍板待开工**
> 严重度: 🔴（用户核查：3 个位置同名类分裂，比子图还严重）
> 审计方法: 与 PCR/行为链同法——资产盘点（本文件）→ 深读 → 断链/分裂核查 → 接线追踪 → 测试

---

## 一、审计对象全景（已找齐，2026-08-03）

对话树不是"1 个模块"，是 **5 套实现/碎片 + 1 孤儿适配器 + 1 断链**：

| 套 | 位置 | 规模 | 谁在用 |
|:---:|------|:---:|------|
| **A 单体** | `compiler/discourse_block_tree.py` | 993L | **engine 主用**（`_discourse_tree`）+ handlers feed + cli registry/subsystem_registrations + discourse_cmd |
| **B 拆包** | `discourse_block_tree/`（17 文件）| ~1700L | v3_common/serialization.py + discourse_integration（部分）+ 自测 |
| **C 独立拆件** | `compiler/header_injector.py`(498L) + `syntactic_decomposer.py`(408L) + `macro_micro_quantizer.py`(325L) | ~1230L | discourse_integration（compiler 版）+ 孤立存在 |
| **D 孤儿** | `discourse/models.py` | 58L | 唯一引用 `inspect_v3_cmd.py:53` 是**断链**（实测 ImportError）|
| **E 大杂烩** | `context_manager/discourse_manager.py`（DiscourseManager）| 1988L | onboarding/agent + prompts + service/discourse_api（经 DiscoursePipeline 包 B）|

## 二、B 拆包 17 文件清单（discourse_block_tree/）

```
__init__.py(20) _debug.py(1) adapter.py(137) context_builder.py(95)
granularity_regulator.py(98) header_injector.py(85) indexer.py(107)
macro_micro_quantizer.py(134) manager.py(256) models.py(195)
plugin_system.py(210) segmenter.py(85) summary_engine.py(136)
syntactic_decomposer.py(156) test_discourse_block_tree.py(207)
test_integration.py(31) topic_markers.py(117)
```

## 三、同名类跨 5 处（分裂核心，行数已核实 2026-08-03）

| 类 | 单体 A | compiler 拆件 C | 拆包 B | 孤儿 D |
|---|:---:|:---:|:---:|:---:|
| `HeaderInjector` | 75L（薄壳）| **402L（完整）** | 47L | - |
| `SyntacticDecomposer` | 46L（薄壳）| **327L（完整）** | 40L | - |
| `MacroMicroQuantizer` | 150L | **242L** | 103L | - |
| `DiscourseBlock` | 170L | - | 46L | 24L |
| `DiscourseBlockTreeManager` | **297L** | - | 241L | 33L |
| `DiscourseBlockTree` | 83L | - | - | - |
| `GranularityRegulator` | 94L | - | 98L | - |
| `CohesionScore` | 27L | - | 21L | - |
| `EDU` | 25L | - | 31L | - |
| `CrossReference`/`GroupReference` | - | - | - | 7/14L |

## 四、Manager API 完全不同（彻底并行，非代码重复）

- **A 单体 Manager**: `feed()` / `split_block` / `merge_blocks` / `delete_block` / `promote_block` / `demote_block` / `compress_cold_blocks` / `get_block_relations` / `get_tree` / `get_stats` / `find_block_by_reference` / `_cold_worker`
- **B 拆包 Manager**: `ingest_turn()` / `add_cross_ref` / `add_group_reference` / `find_activated_groups` / `find_reference` / `resolve_reference` / `search` / `get_tree_summary` / `get_status` / `get_reachable_blocks`
- **主入口都不同**（feed vs ingest_turn）——两套完全独立的实现

## 五、引用格局（谁 import 哪套）

```
engine._discourse_tree = DiscourseBlockTreeManager()      ← 单体 A（feed/get_block_relations）
handlers.handle_discourse → engine._discourse_tree.feed() ← 单体 A
cli/registry + subsystem_registrations                    ← 单体 A
cli/commands/discourse_cmd.py → engine._discourse_tree    ← 单体 A
v3_common/serialization.py                                ← 拆包 B（manager+models+segmenter）
v3_common/discourse_integration.py (DiscoursePipeline)    ← C 独立拆件(compiler版) + B 组件混用
context_manager/discourse_manager.py (DiscourseManager)   ← DiscoursePipeline（包 B）
onboarding/agent + prompts, service/discourse_api         ← DiscoursePipeline（包 B）
inspect_v3_cmd.py:53                                      ← 断链（from core.agent.discourse import DiscourseBlockTree → ImportError 实测）
```

## 六、关键耦合事实

1. **单体依赖拆包**（单向）: 单体 `build_context()` 内 `from core.agent.discourse_block_tree.summary_engine import SummaryEngine`——engine 主路径实际依赖 B 的 SummaryEngine
2. **单体是混合体（关键修正）**: 单体内的 `SyntacticDecomposer`(46L)/`HeaderInjector`(75L) 是**薄壳**，完整实现在 compiler 拆件 C（327L/402L）；单体的真正价值 = `DiscourseBlockTree`(83L) + `DiscourseBlockTreeManager`(297L) + `GranularityRegulator`(94L) + 后台冷压缩——engine 主路径实际是 "单体壳 + C 类 + B SummaryEngine" 三处拼装
3. **脆弱 fallback**: `discourse_integration.py` 正常 import 失败后用 `importlib.util.spec_from_file_location` 动态加载相对路径（`_load("compiler/header_injector.py")` 等）——环境敏感
4. **DiscourseBlockAdapter 孤儿**: `discourse_block_tree/adapter.py`（137L, "V2 集成适配器"）全库零引用
5. **config 独立**: `config/discourse_config.py`（437L, 13 配置类: Encoder/Parser/Decomposer/Injector/Segmenter/Manager/Summary/Context/Pipeline/ModelDownload/Logging/Discourse/ConfigLoader）——两套实现读同一配置
6. **上下文助手**: `compiler/three_paradigm_context.py`（172L, engine compass 注入）+ `compiler/topic_quick_match.py`（214L, BM25, 关联链已修 from __future__）——周边

## 六.5 API / CLI / 持久化 关联（调查补全，2026-08-03）

### API
- `api/viz_edit.py:83` `PUT /discourse-tree`（reclassify/rename/merge/split）→ `engine._discourse_tree`（**单体 A**）
- `api/stubs_api.py:245` `GET /discourse-tree` → `engine._discourse_tree`（**单体 A**，注释明说 "Try engine's DiscourseBlockTree first (real algorithmic tree)"）+ 读 `data/discourse_state.json` 兜底统计

### CLI（操作面全部绑定单体 A）
- `cli/commands/discourse_cmd.py`: dm discourse show/tree/block/stats/compress/topics/topic-tree → 全部 `engine._discourse_tree`（单体 A）；持久化兜底读 `data/discourse_state.json`
- `cli/entry.py`: `("d","split/merge/delete/promote/demote/undo")` + `("discourse","compress/summary/topic-show/topic-add/topic-remove/topic-heat")` + `decompose/cohesion/block-tree/context-build` → 对应单体 A 的 +13 engine methods
- `cli/commands/batch3_cmd.py`: memory 读 `engine._discourse_tree`
- `cli/inspect_v3_cmd.py:48-58`: `_inspect_discourse` **断链**（`from core.agent.discourse import DiscourseBlockTree` → ImportError 实测；except 分支打印 "not found" 静默吞）

### 持久化
- `data/discourse_state.json`（API 兜底 + CLI 兜底读取）
- 写入点: `event/storage.py:290` `store.cold.save("discourse_state.json", block_tree)`——走持久化层冷存储（ColdStore），**A/B 两套实现自身都没有 save/load**，由 event/storage 统一持久化
- 读取点: `api/stubs_api.py:563` + `cli/commands/discourse_cmd.py:114`（兜底统计）+ `api/v6_app.py:146`（健康检查 _disk_info）

### 关键洞察
**CLI/API 对话树操作面（用户编辑树链 03 的白盒通道）全部绑定单体 A**；onboarding/service 的 DiscoursePipeline（B）是对话生成侧另一条线。→ **A = 编辑/运维面活版本，B = 生成/集成面活版本**，两条线不同场景都在用，不是"一死一活"。

## 六.6 设计文档资产（调查补全，为设计文档审计备料）

| 文档 | 规模 | 内容 | 读 |
|------|:---:|------|:---:|
| `docs/v3.0/design_discourse_block_tree.md` | 867L | 对话树本体设计 v1 | ✅ |
| `docs/v3.0/design_discourse_block_tree_v2.md` | 1306L | 对话树本体设计 v2（最大）| ✅ |
| `docs/v3.0/LITERATURE_REF_DISCOURSE_BLOCK_TREE.md` | 397L | 对话树文献参照 | ✅ |
| `docs/BUSINESS_CHAIN_01_CONVERSATION_TREE.md` | 235L | 链 01 对话树（业务链，v3 修正）| ✅ |
| `docs/BUSINESS_CHAIN_01_INTENT.md` | 344L | 链 01 意图（同链另一面）| ✅ |
| `docs/BUSINESS_CHAIN_01_UNIFIED_INTENT.md` | 145L | 统一意图 | ✅ |
| `docs/BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md` | 394L | topic_quick_match（递归收敛快匹配）| ✅ |
| `docs/BUSINESS_CHAIN_2.1_TOPIC_TREE.md` | 88L | 主题树（链 2.1）| ✅ |
| `docs/v3.0/ENGINEERING_TOPIC_TREE.md` | 909L | 主题树工程（操作层+事务 flush）| ✅ |
| `docs/v3.0/design_topic_tree.md` | 1187L | 主题树设计（PCRInput 注入）| ✅ |
| `docs/v3.0/Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md` | 342L | 主题树深潜对比 | ✅ |
| `docs/v5/DESIGN_TOPIC_TREE_GRANULARITY.md` | 131L | 主题树颗粒度（L1-L3+Lroot 距离衰减）| ✅ |
| `docs/v5/TOPIC_TREE_DISCUSSION.md` | 593L | 主题树 5 模糊点决议 | ✅ |
| `docs/v5/TOPIC_TREE_GAP.md` | 23L | 主题树缺口 | ✅ |
| `docs/merge/DESIGN_01_COGNITIVE_PIPELINE.md` | 508L | 认知管线（对话树定位）| ✅ |
| `docs/BUSINESS_CHAIN_AUDIT_DIALOGUE_TREE.md` | 205L | **对话树业务审计：5 缺口**（9维粘合度/温度4态/HeaderInjector/四级摘要/节点内建行为链）| ✅ |
| `docs/v3.0/DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md` | 321L | **修正网关 + NodeAnnotationStore**（拆分不可逆/标注可逆）| ✅ |
| `docs/v3.0/LITERATURE_CORTEX_CONVERSATION.md` | 620L | **设计源头对话记录**（行为因果链→预测→纠错即训练→v3.1-3.3 演进）| ✅ |
| `docs/BUSINESS_CHAIN_03_USER_EDIT_TREE.md` | 359L | **用户编辑树**（NodeEditRecord 区块链式/切分级联）| ✅ |
| `docs/v3.0/design_cognitive_compiler.md` | 1882L | **三阶段源头**（decompose→inject→cohesion + DualStructure 双结构）| ✅ |
| `docs/v3.0/DESIGN_INTERACTION_MODEL.md` | 152L | **链=注解层不嵌入树边**（Event Layer 唯一事实源 + Projection）| ✅ |
| `docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md` | 501L | ContextCompiler：意图感知域选择（对话树=域C）+ 预算 + 子图修剪 | ✅ |
| `docs/v3.0/DESIGN_MULTILAYER_LLM_COGNITIVE.md` | 1077L | 双树认知架构（Topic Tree 用户 + Cognitive Tree LLM 心智）| ✅ |
| `docs/v3.0/DESIGN_FULL_CONCEPT.md` §5.2-5.4 | 1548L | 宪法级：Topic Tree（长期 EMA）+ Context Window（分层压缩）+ 状态机 | ✅ |
| `docs/v5/DESIGN_V4_COGNITIVE_INTEGRATION.md` | 114L | Bridge 3: DiscourseBlock → Memory Extractor + Tag Layer | ✅ |
| `docs/v5/MEMORY_LANDSCAPE_VS_MAINSTREAM.md` | 91L | Enhanced Notes = DiscourseBlock.raw_text 映射 | ✅ |
| `docs/v5/DESIGN_THREE_PARADIGM_LLM_CONTEXT.md` | 140L | 温度·距离·信息价值三范式注入（罗盘式标签）| ✅ |
| `docs/v5/DISCUSSION_PARALLEL_REUSE.md` | 135L | PCR=关联链L3粗处理 / IntentParser=L1-2 | ✅ |
| `docs/v5/DESIGN_HYBRID_ARCHITECTURE.md` | 312L | 热路径直连 + 冷路径 EventSourcing（Association 消费 Discourse）| ✅ |
| `docs/v5/DESIGN_SYNTHESIS.md` | 691L | 设计全貌（对话树子图 D40%/B15%/A25%/P10%/E10%）| ✅ |

> 注：资产清单已从 15 篇补全至 30 篇（2026-08-03 第二轮阅读），全部精读完成。

## 七、演进史（git）

```
80e65a0（最早）: compiler/syntactic_decomposer + header_injector（v1 源头，独立拆件）
单体 993L: 合成 + 演进（fork/gray_zone、+13 engine methods、find_block_by_reference、
            temperature summary via SummaryEngine、Hot/Warm/Cold/Frozen tiers）
拆包 17 文件: 重构拆散 + 新增（SummaryEngine v4、plugin_system、MacroDimensions、
             DeepSeek direct、observability/Prometheus 集成）
11393ea: discourse/models.py 孤儿产生（搬移残留）
DiscourseManager 1988L: 另一条线（话题重叠/审计/语义检索，包 DiscoursePipeline）
```

## 八、测试现状

```
core/agent/compiler/tests/test_discourse_block_tree.py    112L（旧单体）
core/agent/discourse_block_tree/test_discourse_block_tree.py 207L（新包）
core/agent/discourse_block_tree/test_integration.py        31L（新包集成）
```
> 需验证: 三套测试是否可收集/通过；是否存在针对孤儿 D 的测试（零）

## 八.5 调查完整度自检（2026-08-03）

✅ 代码实现（5 套 + 孤儿适配器 + 断链）✅ 同名类行数核实 ✅ Manager API 对比
✅ 引用格局（engine/handlers/CLI/API/serialization/integration/onboarding/service/context_manager）
✅ API/CLI/持久化关联 ✅ 设计文档资产（15 篇）✅ 测试分布 ✅ 演进史（git）
✅ 持久化链路（event/storage.py cold store 写入 + API/CLI 兜底读取）
⏳ 已完成（2026-08-03）: 三套测试实跑（24/26）+ import 探针 A/B/C/D/E + 深读 A/B/C + 接线追踪 → 见 IMPLEMENTATION_AUDIT_20260803.md

## 九、待查清单（审计开工问题）

1. **确定"活版本"**: engine 主用单体 A，但单体依赖 B 的 SummaryEngine——A 是"活"还是 A+B 混合是活？C/E 是否生产可达？
2. **断链清理**: `inspect_v3_cmd.py:53` ImportError 确认；`discourse/models.py` 孤儿去留（un_use 归档 or 糅合）
3. **API 归一**: feed() vs ingest_turn() 两套入口——按"一内核多门面"哲学选内核，另一套降级为门面/归档
4. **孤儿适配器**: DiscourseBlockAdapter 是"规划中未接线"还是"已废弃"——拍板去留
5. **脆弱 fallback**: discourse_integration 的 importlib 动态加载——正常化 import 路径
6. **同名单类**: HeaderInjector/SyntacticDecomposer/MacroMicroQuantizer 三处（单体 96/163/298L vs compiler 498/408/325L vs 拆包 85/156/134L）——哪个是"真实现"？compiler 拆件最大，但谁在用？
7. **配置一致性**: 两套实现读同一 discourse_config——参数是否都生效
8. **测试**: 三套测试跑一遍，看旧单体测试是否仍绿（还是已腐坏）
9. **元认知/持久化关联**: 对话树 ← 用户编辑树（discourse/ 白盒）、topic_tree、StateMachine DISCOURSE 阶段
10. **engine 双轨**: on_event_sm 的 DISCOURSE 阶段走 handlers，`_on_event_continue` 死代码里也有 discourse 注入（compass）——确认无双重 feed

## 十、审计计划（建议顺序）

```
```
阶段一（本轮）: 总体收集 ✅ —— 代码/文档/测试/API/CLI/持久化/演进全盘点（本文件）
阶段二: 具体实现审计 —— 跑三套测试 + import 探针（A/B/C/D/E 全 import 实测）
                    + 深读单体 A（993L, engine 主用）→ 拆包 B（manager/models）
                    + C 拆件差异对比 + 接线追踪（各路径实际触达）
阶段三: 设计文档审计 —— 精读 v1(867L)/v2(1306L) + 链 01 + topic 系列 + 3 篇博客，对照实现找设计-代码差距
        ✅ 已完成（2026-08-03，见 DESIGN_AUDIT_20260803.md）
阶段四: 内核拍板 —— 一内核多门面：选内核 + 门面/归档清单（用户: 内核决策不着急，先调查全）
阶段五: 施工（按拍板）+ 测试 + 全量回归
```
```
