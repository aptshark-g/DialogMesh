# 对话树实现审计（阶段二）— 2026-08-03

> 范围：三套测试实跑 + import 探针 A/B/C/D/E + 深读单体 A / 拆包 B / C 拆件 + 接线追踪（engine/CLI/API/ContextAssembler/unified_context）。
> 方法：anaconda 3.9 实跑；rg 全库引用追踪；逐文件精读核心逻辑。

---

## 一、测试实况（26 项：24 过 / 2 挂）

| 测试文件 | 结果 | 说明 |
|---|---|---|
| `compiler/tests/test_discourse_block_tree.py`（旧单体，12 项）| 10 过 / **2 挂** | 见下 |
| `discourse_block_tree/test_discourse_block_tree.py`（新包，13 项）| 13 过 | B 拆包全部通过 |
| `discourse_block_tree/test_integration.py`（新包集成，1 项）| 1 过 | 见下 |

### 2 挂根因：测试-实现契约断裂（非实现错误）
1. `test_session_entity_cache`：期望 `inject()` 把"这个"替换为实体（v2 §4.1 契约"返回补全后文本"）；**A 的 `HeaderInjector.inject()` 是检测器不替换**（`return text` 原样返回）。
2. `test_context_serialization`：期望 `"Active Branch"` 标签（A `serialize_for_context()` 旧格式）；实现 `build_context()` 已委托 **B 的 SummaryEngine** 输出 `[Hot]/[Warm]` 温度标签。

> 结论：测试写在旧契约上，实现已演进——**测试腐坏，不是代码腐坏**。修复=更新断言契约。

---

## 二、import 探针（A/B/C/D/E 全实测）

| 套 | 模块 | 结果 |
|---|---|---|
| A 单体 | `compiler.discourse_block_tree` | ✅ 可 import |
| B 拆包 | `discourse_block_tree.manager` / `.models` / `.summary_engine` / `.adapter` | ✅ 全部可 import |
| C 拆件 | `compiler.header_injector` / `syntactic_decomposer` | ✅ 可 import |
| C 拆件 | `compiler.macro_micro_quantizer` | ❌ **numpy 损坏**（`need=1.17 found=None`）+ 顶层 `import numpy` |
| D 孤儿 | `discourse.models` | ✅ 可 import |
| E | `context_manager.discourse_manager` | ❌ numpy 损坏（依赖链重）|
| E 管道 | `v3_common.discourse_integration`（DiscoursePipeline）| ❌ numpy 损坏 |

> 环境坑：anaconda numpy 损坏导致 C-quantizer / E / Pipeline 三个模块 import 即炸（非代码断链，但真实环境不可用）。已知环境问题（交接 §五）。

---

## 三、接线追踪结论（回答 AUDIT_ENTRY §九.1 "谁活着"）

### 3.1 engine 主路径 = 单体 A（实锤）
```
engine.py:31   import A 的 DiscourseBlockTreeManager
engine.py:157  self._discourse_tree = DiscourseBlockTreeManager()      ← A
engine.py:69   _feed_discourse() → engine._discourse_tree.feed()       ← A 的 feed
engine.py:743  compass 注入：ThreeParadigmContext.build(block_list)    ← A 块 + 三范式标签
               → ContextEntry(source="discourse_tree") → _last_context.entries
engine.py:863  StateMachine ACTIVATE 记录 tree.blocks / active_blocks  ← A
engine.py:1050 _topic_tree_source.feed_turn()                          ← 若可达则走 B
```

### 3.2 B 拆包：生产路径不可达
- `TopicTreeContextSource.feed_turn()` → `self._discourse.ingest_turn()`（B 契约），但 `engine.py:187` 的 `self._topic_tree_source = None` **全库无赋值**（rg 确认）→ **B 的 ingest_turn 在 engine 主路径零调用**。
- B 仅被：C 的 quantizer 动态加载 models（跨套依赖）+ 自身 13 项测试消费。

### 3.3 CLI / API 全绑 A
- `discourse_cmd.py` 全部 `getattr(e, '_discourse_tree', None)` → A（show/tree/block/feed/search/stats）
- `registry.py:278` + `subsystem_registrations.py:24` 注册 A；`entry.py:757-765` block-tree/context-build → A
- `api_viz_edit.py:87` / `stubs_api.py:152` / `v6_app.py:125` 健康检查 → A
- `inspect_v3_cmd.py:53` → D 断链（ImportError 确认）

### 3.4 E：已被判定废弃（unified_context 实锤）
- `assembly/unified_context.py:90-98` 注释明示："DiscourseManager is a v3 unmaintained module with heavy dependency chain" → try/except 置 None。
- `context_manager/__init__.py:19` 仍顶层 import（numpy 坏即包 import 失败），但 unified_context 已保护。

### 3.5 三范式 compass：已实现且被 engine 注入 ✅
- `compiler/three_paradigm_context.py`：`[Hot·★★·Near]` 标签 + 优先级排序（温度 0.25 + 价值 0.40 + 距离 0.35）——**罗盘式给 LLM 已落地在 A 的注入路径**（engine.py:743）。
- ⚠️ 跨套字段 bug：`three_paradigm_context._block_text()` 读 `summary.v3_milestone`，B models 写 `v3_evolution`、SummaryEngine 写 `v3_milestone`——**三处字段名不一致**，compass 的 v3 摘要实际取不到。

---

## 四、设计-实现契约断裂清单（10 项，阶段二新发现）

| # | 契约 | 设计要求 | 实现实际 | 影响 |
|---|------|---------|---------|------|
| C1 | HeaderInjector.inject() | 返回补全后文本（v2 §4.1）| A 返回原样（检测器）| 指代补全名存实亡（测试 1 失败根因）|
| C2 | 灰区决策 | 灰区走 LLM/Ψ 辅助（v2 §4.3）| A feed 把 `gray_zone` 当 fork（`decision in ("fork","gray_zone")`）| 灰区语义丢失，误分叉 |
| C3 | 决策阈值 | total>0.75 continue / <0.25 fork（v2）| A BGE fast path 0.70 / 0.20 | 阈值不一致 |
| C4 | 温度模型 | 多因子复合场 + 语义唤醒 BGE>0.8（A15）| A 纯时间×importance（300/1800/7200）；B 纯轮数（5/10/30）| 无唤醒机制 |
| C5 | 四级摘要元信息 | v2 一级摘要含行为链+因果链+关联链 | A/B 简化（实体+动词 / 里程碑）| 缺口⑤ 未落地 |
| C6 | ProgressiveSummary 字段 | `v3_evolution`（B models）| SummaryEngine 写 `v3_milestone` | **跨文件字段名不一致，v3 写入读不到** |
| C7 | adapter 契约 | 映射 B models → V2 路由输入 | 引用 `latest_summary`/`intent_label`/`entity_signature`/`id`（B models **无这些字段**）| 被调用即 AttributeError（故零引用）|
| C8 | 三阶段顺序 | 源头：decompose→inject→cohesion | A/B feed 均 inject→decompose（v2 顺序）| 与源头设计相反 |
| C9 | 四象限 attach | v2 §5.2；B `classify_quadrant` 已实现 | A 无 attach 产出（RouteDecision 有枚举但 feed 不产生）| attach 语义悬空 |
| C10 | C quantizer 依赖 | 零 LLM / 轻量 | 顶层 `import numpy`（环境坏即炸）+ dynamic load B models | 脆弱 |

---

## 五、分裂归一评估（内核候选）

| 套 | 优点 | 缺点 | 角色建议 |
|---|---|---|---|
| A 单体 | engine/CLI/API 全接线；compass 注入；冷压缩线程；写操作全（split/merge/delete/promote/demote）| 三阶段薄壳；决策简化（无 attach/灰区误 fork）；温度无唤醒；摘要无行为链 | **门面层（接线保留）** |
| B 拆包 | 最接近 v2（ingest_turn/ProgressiveSummary/cross_ref/group_ref/四象限/indexer/topic_markers 77 标记）；13 测试全绿 | 生产不可达；字段名不一致（C6）；温度轮数驱动 | **内核骨架候选** |
| C 拆件 | header_injector（coreference chains/omitted objects）/syntactic_decomposer（hybrid path）完整 | quantizer 依赖 B models + numpy；无独立测试 | **编译器内核候选** |
| D 孤儿 | — | 断链、零引用 | 归档 un_use |
| E DiscourseManager | 语义检索/话题重叠能力 | numpy 依赖重、已判 unmaintained | 保持废弃（unified_context 已取代）|

**推荐内核组装**（与 KERNEL_ABSORPTION §三 契约对照）：
```
编译器内核 ← C（decompose/inject 完整实现）
管理内核   ← B（ingest_turn/ProgressiveSummary/cross_ref/四象限）
接线/门面  ← A（engine/CLI/API/compass）
输出端     ← compass 三范式（已实现，修 C6 字段名即可用）
```

---

## 六、阶段二结论

1. **活版本确认**：engine/CLI/API = 单体 A + compass；B 生产不可达；C 半套（quantizer 依赖 B）；D 断链；E 已废弃。
2. **测试 24/26**：2 挂为测试腐坏（旧契约）；B 拆包 13 项全绿说明 B 实现自洽。
3. **10 项契约断裂**：C1/C2/C3/C4/C8/C9 是设计-实现偏差（指代不补全、灰区误 fork、阈值漂移、无唤醒、顺序相反、无 attach）；C6/C7 是跨文件不一致（字段名）；C10 是环境脆弱。
4. **施工优先级建议**（阶段五备料）：
   - P0 修复 2 个腐坏测试 + C6 字段名统一（三处 v3 字段对齐）
   - P0 内核组装路线图：C 编译器 + B 管理 + A 接线
   - P1 C2 灰区修复（灰区不再当 fork，走 A13 长证明后验）+
   - P1 C4 温度加语义唤醒（BGE>0.8 回 Hot，A15）
   - P2 C5 四级摘要补行为链元信息（缺口⑤，INTERACTION_MODEL 注解层方案）
   - P2 C9 attach 落地（B classify_quadrant 已就绪，接入路由）

---

*本文件与 DESIGN_AUDIT_20260803.md（阶段三设计审计）、DESIGN_READ_COMPLETE_20260803.md（补充阅读）、KERNEL_ABSORPTION_20260803.md（内核草案）共同构成对话树审计完整资产。*
