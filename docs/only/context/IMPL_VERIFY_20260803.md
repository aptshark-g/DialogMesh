# 上下文具体实现核查 — 运行验证报告

> 日期: 2026-08-03 | 方法: 探针脚本逐文件运行验证（anaconda 3.9，PYTHONIOENCODING=utf-8）
> 状态: 关键缺陷**实锤**（可复现）；可用组件**实测**确认

---

## 一、运行验证结论总表

| # | 核查点 | 验证结果 | 严重度 |
|---|---|:---:|:---:|
| 1 | `assemble_ir` 域选择与预算串联 | selector 选 K（query: C,K,E）→ allocator 无 K 预算（C,E,P）→ **K 域 0 预算仍被注入** | 🔴 P0 双 bug |
| 2 | `to_prompt` 0-budget 过滤 | **active_domains 为空集时短路，0 预算条目照常输出** | 🔴 P0 |
| 3 | `ConceptGraph` 中文概念 | **中文双字词（网关/监控/延迟）全被 `len<3` 过滤 → nodes=0** | 🔴 P0 |
| 4 | `_keyword_score` 中文分词 | 中文查询无空格 → split 整句 → 与词条不匹配 | 🟡 P1 |
| 5 | ContextManager 全流程 | 会话/消息/意图/实体/缓存/统计 **全部可用**（47 测试佐证）| ✅ |
| 6 | ContextWindow SUMMARY 截断 | 30 切片 → 2 切片+10 摘要，tokens 270→108 | ✅ |
| 7 | temperature_patch | 对 v3 风格对象可打补丁；v4 manager 无 entries → no-op | 🟡 P2 |
| 8 | cross_ref_builder | 共享 event_id 双向指针生成 ✅（naive 但可用）| ✅ |
| 9 | cross_domain_expander | 纯 stub 输出（`{"stub": True}`）| 🟡 已知 |
| 10 | IR 序列化往返 | to_dict/from_dict/to_legacy_context 全部可用 | ✅ |
| 11 | BudgetAllocator 三策略 | quality_first/balanced/cost_first 分配正确 | ✅ |
| 12 | DomainSelector with_boost | 域提升 + 归一化正确 | ✅ |
| 13 | SQLiteContextStore | 落库/读取/列表往返可用 | ✅ |
| 14 | context_window/ WindowManager | 三层窗口 + pcr_input 构建 + 规则压缩可用 | ✅（孤立模块）|

---

## 二、P0 缺陷实锤细节

### 2.1 P0-1: `assemble_ir` 域选择与预算错位（运行复现）
```
asm.assemble_ir("gateway monitoring", token_budget=700)
→ intent_category: QUERY
→ entries: [('K', 'knowledge', 'gateway monitoring latency metrics')]   # selector 选了 K
→ domain_allocation: [('K', AUXILIARY, 0)]                              # allocator 没给 K 预算
```
根因: `DomainSelector` QUERY 矩阵 = (C,K,E)，`BudgetAllocator` QUERY 矩阵 = (C,E,P)
（两套矩阵不一致，第一轮已实锤）→ selector 选中的域拿不到预算。

### 2.2 P0-2: `to_prompt` 0-budget 过滤短路（运行复现）
```
ir.to_prompt(max_tokens=200)  # domain_allocation=[('K', AUXILIARY, 0)]
输出:
  [Context] intent=query strategy=balanced
  # Domain Allocation
    • K: 0 tokens (0%)
  ## [K]
    • knowledge [1.00] gateway monitoring latency metrics (8t)
  # Total: 8 tokens used
```
代码:
```python
active_domains = {a.domain for a in (self.domain_allocation or []) if a.budget_tokens > 0}
for entry in self.entries:
    if active_domains and entry.domain not in active_domains:
        continue
```
**逻辑 bug**: 当所有域预算=0（或 domain_allocation 为空）→ `active_domains` 为空集 →
`if active_domains and ...` 短路为 False → 全部条目照常输出。
注释声称 "Zero-budget domains are skipped"，实际相反：**预算耗尽时全量输出**。
这与 `CONTEXT_GAP.md` 宣称的「to_prompt 0-budget 过滤已修复 ✅」**正好相反** —— 假修复实锤。

### 2.3 P0-3: `ConceptGraph` 中文概念全灭（运行复现）
```
build_from_pool(中文 concepts=["网关","监控","延迟","告警"])
→ nodes=0, edges=1    # 双字词全被 len(c)<3 过滤
对照: 英文 concepts=["gateway","monitor","latency","alert"] → nodes=4
```
根因: `if not c or len(c) < 3: continue` —— 针对英文设计的长度阈值，
中文核心概念（2 字词）全部被丢弃 → `find_seeds` 恒空 → `compile_context` 恒空 →
`ConceptGraphSource` 中文场景静默回退 DocumentSource 关键词检索。
噪声过滤同时失效: `v1.2.3` 版本号未被过滤（`replace('.','')` 后非纯数字），会进图。

---

## 三、P1 缺陷实锤细节

### 3.1 `_keyword_score` 中文分词失效（运行复现）
```
_keyword_score("监控 延迟".split(), "监控缺失导致延迟飙升") → 1.0   # 带空格可匹配
_keyword_score("监控延迟".split(), "监控缺失导致延迟飙升") → 0.0   # 无空格整句 → 0
ObservationSource.retrieve("监控延迟") → 0 items                   # 中文用户不打空格
```
根因: 全库统一 `query.lower().split()` 英文分词假设，中文无分词器。
影响: `_keyword_score` / `ObservationSource` / `DocumentSource` / `KnowledgeSource` /
`SkillSource` / `CausalSource` / `EngineeringChain.check_feasibility` 全部受影响。
（首轮已确认 `syntactic_decomposer` 有 stanza/jieba 分词可用，context 侧未复用。）

### 3.2 `ContextManager` 构造依赖事件循环（观察）
```
ContextManager()（无 asyncio 运行循环）→ InMemoryContextStore.__init__ → asyncio.Lock()
→ RuntimeError: There is no current event loop
```
Python 3.9 行为（Lock 创建时绑定循环）。v3 服务在 async 上下文内构造不受影响，
但同步/线程场景构造会炸 —— 应在 __init__ 延迟创建锁。

### 3.3 `temperature_patch` 与 v4 manager 不兼容（运行复现）
```
patch_context_manager(v3风格 obj with entries+add_entry) → 补丁生效 ✅
patch_context_manager(ContextManager()) → no-op（v4 无 entries 属性，直接返回）
```
该 patch 面向已退役的 v3 `context_manager.entries` 结构，对 v4 ContextManager 无效。

---

## 四、验证为「可用」的部分（实测）

| 组件 | 验证点 | 结论 |
|---|---|---|
| `ContextManager` | create/add_user_message/add_intent/build_prompt/get_resolved_entities/entity_cache/stats | ✅ 全流程可用（47 测试佐证）|
| `ContextWindow` | SUMMARY 策略 30 切片压缩：slices 2 + summaries 10，270→108 tokens | ✅ |
| `SQLiteContextStore` | save→load→list_sessions→close 往返 | ✅ |
| `CrossDomainContextIR` | to_dict→from_dict→to_legacy_context 往返 | ✅ |
| `DomainSelector.with_boost` | QUERY→boost P: 归一化 [C 0.46, K 0.19, E 0.12, P 0.23] | ✅ |
| `BudgetAllocator` | 三策略分配 + casual 无辅域2 返还主域 | ✅ |
| `CrossRefBuilder` | 共享 event_id → E↔B 双向指针 | ✅（naive）|
| `context_window/` | WindowManager 三层统计 + build_pcr_input + RuleBasedCompressor 单轮压缩（保留意图标签）| ✅（孤立模块）|
| `ConceptGraph`（英文） | 4 节点构建 + seeds + BFS 扩展 | ✅ 英文场景 |
| `SubgraphPruner`（首轮）| 4 轮修剪 + 3 步降落 + 意图权重 | ✅ 算法完整 |

---

## 五、本轮新增缺陷清单（相对前两轮）

1. **`to_prompt` 0-budget 过滤短路**（P0）—— 与 CONTEXT_GAP 宣称相反，假修复实锤。
2. **`assemble_ir` 预算错位运行级复现**（P0）—— 两套矩阵不一致的直接后果。
3. **`ConceptGraph` 中文概念全灭**（P0）—— `len<3` 阈值 + 无中文分词。
4. **`_keyword_score` 中文分词失效**（P1）—— 全库英文分词假设。
5. **`ContextManager` 构造依赖事件循环**（P2 观察）—— asyncio.Lock 创建时机。
6. **`temperature_patch` 面向退役 v3 结构**（P2）—— 对 v4 manager 无效。

---

## 六、结论

上下文实现「v3 会话管理可用、v4 算法层部分可用、接线全断」的结论被运行验证夯实，
并新增**两个 P0 逻辑 bug**（to_prompt 过滤短路、ConceptGraph 中文全灭）——
这两个都在「写得最好」的算法组件里，说明实现质量不是表面问题，需要逐组件修复验证。
