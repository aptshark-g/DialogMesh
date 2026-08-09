# 交接终态 — 工程链 + 上下文审计完成（2026-08-03）

> 压缩恢复入口（工程链/上下文专项）。前置恢复顺序见 `RECOVERY_PLAN_20260803.md`。
> 状态: **两模块四轮审计全部完成**（文件盘点 → 设计对照 → 设计精读 → 运行验证），
> 尚未施工、尚未拍板。**2026-08-03 更新: 待讨论清单已用 PARADIGM 哲学消解**
> （17 项 → 12 项施工/清理项 + 5 项核心讨论，见 §六）。
> 恢复后第一步 = 展开 5 项核心讨论，然后施工。

---

## 一、完成态总览

| 阶段 | 工程链（07） | 上下文（02） |
|---|---|---|
| 文件盘点（AUDIT_ENTRY）| ✅ 11 文件消费矩阵 + 14 缺陷 | ✅ 5 套并行实现 + 3 路接线全断 |
| 设计对照（DESIGN_IMPL_AUDIT）| ✅ 5 文档逐条对照 | ✅ 8 文档逐条对照 |
| 设计精读（DESIGN_FULL_READ）| ✅ 17 节（含补充）| ✅ 15 节（含补充）|
| 运行验证（IMPL_VERIFY）| ✅ 10 项实测 + 4 新 P0/P1 | ✅ 14 项实测 + 2 新 P0 + 2 P1 |

**核心结论（一句话）**
- 工程链: 约束空间设计完整，实现 = 模型层可用 + 推理层空转 + 接入层 0% 接线。
- 上下文: Context Engineering 设计完整，实现 = v3 会话管理可用 + v4 算法层两处 P0 bug + 主路径 0% 生效。

---

## 二、落盘文档清单（压缩后必读）

### 工程链 `docs/only/engineering/`
1. `AUDIT_ENTRY_20260803.md` — 第一轮: 文件消费矩阵 / 接线实证 / 14 缺陷
2. `DESIGN_IMPL_AUDIT_20260803.md` — 第二轮: 设计 vs 实现逐条对照（符合度 15-35%）
3. `DESIGN_FULL_READ_20260803.md` — 设计完整记录（约束空间/执行层 ConstraintTree/工具注册/持久化/约束补全）
4. `IMPL_VERIFY_20260803.md` — 运行验证: 10 项实测 + 4 新 P0/P1 实锤

### 上下文 `docs/only/context/`
1. `AUDIT_ENTRY_20260803.md` — 第一轮: 5 套实现族 / 3 路接线全断 / 5 处 API 错配
2. `DESIGN_IMPL_AUDIT_20260803.md` — 第二轮: 设计 vs 实现对照（算法层>接线层>状态报告层）
3. `DESIGN_FULL_READ_20260803.md` — 设计完整记录（子图组合/观察编译器/穿透层/压缩哲学三阶段）
4. `IMPL_VERIFY_20260803.md` — 运行验证: 14 项实测 + 2 新 P0（to_prompt 短路 / ConceptGraph 中文全灭）

---

## 三、关键实锤缺陷（恢复后修复范围）

### 工程链 P0
| # | 缺陷 | 位置 |
|---|---|---|
| E1 | `check_anti_patterns` 不看边类型（任何 Controller 边都违反）| constraint_engine.py |
| E2 | `__init__.py` 把 `Artifact` 导出为 `ArtifactType` 枚举 | __init__.py:14 |
| E3 | `chain.snapshot()` MCP 分支恒空（`callable(列表)=False`）| chain.py:61 |
| E4 | `compile_context` 假模式/空反模式/空决策（五要素只交 1.5 个）| constraint_engine.py:54 |
| E5 | v3_2 shim 缺 `models.py`（旧路径 ModuleNotFoundError，测试实测失败）| v3_2/engineering_chain/ |
| E6 | `KnowledgeGraph.add()` 丢 impact 参数 | knowledge_graph.py:83 |

### 上下文 P0
| # | 缺陷 | 位置 |
|---|---|---|
| C1 | `to_prompt` 0-budget 过滤短路（预算耗尽全量输出，与 CONTEXT_GAP 宣称相反）| cross_domain_ir.py:202 |
| C2 | `ConceptGraph` 中文双字词全被 `len<3` 过滤（nodes=0）| graph_source.py:145 |
| C3 | `assemble_ir` 域选择与预算错位（两套矩阵: QUERY C,K,E vs C,E,P）| assembler.py / domain_selector.py / budget_allocator.py |
| C4 | 状态机 PLANNING/CONTEXT/LLM 三 phase 无 handler（主路径 CONTEXT 空转）| event/handlers.py |
| C5 | `runtime/engine.py` `_compile_context` 幽灵调用 + `_on_event_continue` 死代码 | runtime/engine.py:894 |
| C6 | assembly 5 处 API 错配（BudgetAllocator/ContextAssembler/Pruner/ContextLayer）| assembly/unified_context.py |

### 共同 P1
- 中文分词: `_keyword_score`/`check_feasibility` 全库 `split()` 英文假设（stanza/jieba 未复用）
- 白盒 CLI: `KnowledgeGraph.remove/get_node/search` UUID 键 vs name 查询全失效
- 状态文档造假: `CONTEXT_GAP.md` 宣称 95%「最完整链」与实测相反

---

## 四、验证为「可用」的部分（勿误删）

### 工程链
- `APIDocPreprocessor`（OpenAPI/markdown/json 基础解析）✅
- `EngineeringChainPersistence`（UnifiedGraphStore 往返）✅（但生产零接线）
- `models` is_a 树 / `ArtifactRegistry` 注册查询 ✅

### 上下文
- `ContextManager` v3 会话全流程（47 测试绿）✅
- `ContextWindow` SUMMARY 压缩 ✅ | `SQLiteContextStore` ✅ | IR 序列化往返 ✅
- `BudgetAllocator` 三策略 ✅ | `DomainSelector.with_boost` ✅ | `CrossRefBuilder` naive ✅
- `context_window/` 孤立模块（WindowManager/RuleBasedCompressor，12 测试绿）✅
- `SubgraphPruner` 算法完整（4 轮修剪+3 步降落）✅

---

## 五、下一步（恢复后）

1. 拍板待讨论清单（§六）→ 落盘 PENDING_DECISIONS
2. 施工顺序建议（供讨论）:
   - 上下文: 先修 C1/C2 两个算法 P0（纯 bug 修复）→ 再修 C6 assembly 接线 → 再补 C4/C5 主路径
   - 工程链: 先修 E2/E5（导出陷阱 + 断链）→ E1/E6（逻辑缺陷）→ 定位拍板后施工
   - 共同: 中文分词统一（复用 discourse 侧 stanza/jieba）
3. **哲学消解已完成**: `docs/only/wise/PARADIGM_FILTER_ENGINEERING_CONTEXT_20260803.md`
   → 12 项消解为施工项（§六.一）+ 5 项核心讨论（§六.二）
4. **继续审计（可选，压缩后）**: 按模块缺口清单，下一候选 = **元认知（09）**
   （`meta/` 5 文件 + `v4/cognitive/metacognition.py`，蓝图审计已点「Meta 学习闭环零调用方」）
   或 **规划（1.5）**（`planner/` 20 文件 + `causal/planner.py`，关联链审计已点「无 slow_path」）。

---

## 六、待讨论清单（全部拍板点）

> **2026-08-03 哲学消解更新**: 本清单 17 项已用 `PARADIGM.md` 过滤，
> 详细分析见 `docs/only/wise/PARADIGM_FILTER_ENGINEERING_CONTEXT_20260803.md`。
> 结论: **12 项消解为施工/清理/修复项**（A2-A8 多数/B2/B3/B4/B6/C1/C2/C4），
> **5 项保留为核心讨论**（C1-C5，见文末「核心讨论」）。

### A. 工程链定位与施工
- A1 定位: 收缩为「子图 K/E 域数据源 + MCP 约束校验」还是补全约束推理引擎（七类节点/递归地图/白盒/Pattern 蒸馏）？
- A2 v3_2 shim: 补 `models.py` 还是直接删旧路径？
- A3 `persistence_full.py` 重复文件: 删除？
- A4 `__init__` Artifact 别名: 修复导出（Artifact→数据类）？
- A5 白盒 CLI（remove/get_node/search）: 改 ID 查询还是重建 name 索引？
- A6 MCP 约束校验: 接线 `EngineeringChain` 进 `MCPIntegrationHub` 还是维持 allowed？
- A7 `api_doc_preprocessor`: 补全 6 组件还是维持基础解析？
- A8 工程链持久化: 接 UnifiedGraphStore（domain=E）还是继续内存 preset？

### B. 上下文接线与收敛
- B1 主接线点: CLI prompt 构造 / 状态机 CONTEXT phase / agent_native —— 三选一还是混合？
- B2 assembly 5 处 API 错配: 修包装层（assembly）还是修 context/ 本身签名？
- B3 两套 IntentCategory 枚举 + 两套域矩阵: 归一策略（以哪套为准）？
- B4 `to_prompt` 0-budget 语义: 预算耗尽应全量输出还是全跳过？（当前与注释相反）
- B5 5 套并行实现收敛: `context_manager/`（87KB discourse_manager）归档？`context_window/` 去留？
- B6 `ContextManager` 锁创建时机: 延迟到 async 上下文？
- B7 v3 ContextManager 服务路径: 保留还是随 v6 迁移退役？
- B8 Event ID 跨域索引（设计 §3 核心粘合剂）: 是否单独立项（可复用关联链 Event Sourcing 基建）？

### C. 跨模块
- C1 中文分词统一: 全库接 jieba/stanza 还是按模块？
- C2 状态文档纠偏: `CONTEXT_GAP.md`/`BUSINESS_CHAIN_02` 立即修正还是施工后修正？
- C3 上下文与子图组合: SubgraphCompiler K 域已接（20% token），CONTEXT phase 补全后如何协同？
- C4 测试策略: v4 context 管线零测试 → 补单元/接线/压测的优先级？

---

## 七、核心讨论（哲学消解后保留的 5 项）

> 完整版见 `docs/only/wise/PARADIGM_FILTER_ENGINEERING_CONTEXT_20260803.md` §二。

1. **上下文 × 子图协同边界**（核心）: Context 决定「看什么/多少/优先级」，
   子图决定「以什么结构呈现」；CONTEXT phase 补全后分工边界 + A8 表达形式（XML/JSON/NL）落点。
2. **Event ID 跨域索引**: 设计 §3 核心粘合剂从未实现；复用关联链 Event Sourcing 基建还是独立实现。
3. **约束空间工具域 + 上下文快通道**: 工程链约束是否纳入工具/命令域（MCP 校验）；
   快通道（CLI 直接 LLM）给什么、后补修什么。
4. **代码分裂治理**: `context_manager/`（87KB）与 `context/` 替代还是生态位共存；
   v3 ContextManager（47 绿）保留复用还是迁移升级。
5. **工程链施工范围与顺序**: 首期做到哪一档（模型层→推理层→接入层）；先修 P0 还是先接子图 K 域。

**讨论顺序建议**: C1 → C2 → C4 → C3 → C5（C1 决定上下文工程最终形态）。
