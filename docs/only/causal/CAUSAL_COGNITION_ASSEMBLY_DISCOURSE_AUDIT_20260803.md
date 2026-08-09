# 新增遗漏审计 — causal / cognition / assembly / discourse（用户核查新增）

> 日期: 2026-08-03 | 触发: 用户核查新增「causal/planner.py(470行) + cognition/ + assembly/ +
> discourse/(models 薄壳) 从未被任何审计完整覆盖」。
> 方法: 全文精读 + 全库 rg 消费矩阵 + 运行时探针（anaconda 3.9 实测）。

---

## 〇、结论先行

1. **causal/planner.py（470 行）是「组件完整、接线为零」的典型**——CausalPlanner 与
   CausalContextSource 实现完整、可独立运行（`_ensure_v3_2()` 实测返回 True），
   但 `runtime/engine.py:152` 声明 `self._causal_planner = None` 后**全库再无赋值**。
   引擎内 3 处因果分支（927/946/1167）全在 `if is not None` 守卫后 → 永远不执行。
   CLI `dm causal trigger` 恒输出 `{"error":"causal planner not loaded"}`。
2. **cognition/hub.py（4.3KB）是少数「真接线」模块**——`CognitionHub.is_loaded=True` 实测
   （hypothesis_engine/belief_accumulator/relation_extractor 三件套全部 import 成功）；
   A 路径 agent_native.py:276 真调用 `converge()`。但 `ingest_relations()` 全库零调用 →
   关系缓冲恒空 → converge 空转（有引擎调用、无数据喂入）。
3. **assembly/ 双文件（15.3KB）都是薄包装**——`UnifiedContext` 号称合并 context/
   pipeline 与 context_manager/ runtime，但 **DiscourseManager 集成被整段注释掉**
   （"v3 unmaintained... Skipping for v6 minimal loop"）→ "unified" 名不副实，
   只是 context/ pipeline 换了个包名。
4. **discourse/models.py（1.9KB 薄壳）断了一个 CLI 引用**——`inspect_v3_cmd.py:53`
   `from core.agent.discourse import DiscourseBlockTree` 实测 ImportError
   （discourse/ 包只有 models.py，无 DiscourseBlockTree 符号）→ 被 try/except 吞掉 →
   inspect 静默报 "module not found"。真正的 discourse 树实现在
   `discourse_block_tree/`（已审计），discourse/ 是残留薄壳。

---

## 一、causal/planner.py（470 行 19.6KB）— 完整实现，零接线

### 1.1 结构
```
BehaviorStepIR / BehaviorEdgeIR / CausalChainResult     v4-native IR（不 import v3_2）
_kind_to_action_type / _build_summary                   EventIR→IR 映射
CausalPlanner                                          核心（record_step / process_chain /
                                                        get_chain / get_recent_chain /
                                                        save / load / stats）
CausalContextSource                                     ContextSource 实现（retrieve）
```

### 1.2 核心实锤（运行时探针）
```
CausalPlanner() 独立初始化 OK；_ensure_v3_2() → True
  （BehaviorGraph + CausalSubstrate 均可 import，behavior/ 与 association/ 存活）
✔ 实现本身可用——问题不在实现，在无人实例化

runtime/engine.py:
  152: self._causal_planner: Optional[CausalPlanner] = None   ← 唯一"赋值"
  145: self._behavior_graph_adapter = None                    ← 同样从未赋值
  146: self._causal_substrate_adapter = None                  ← 同样从未赋值
  探针: e._causal_planner=None / _behavior_graph_adapter=None /
        _causal_substrate_adapter=None / _behavior_brain=None / ready=False

全库 rg "_causal_planner\s*="（core/cli/api/service/runtime）→ 除声明外 0 处赋值
全库 rg "_behavior_brain\s*=" → 0 处（行为链审计 P0 断链后的残留声明）
```

### 1.3 影响面
```
runtime/engine.py:927-935   record_step 分支      → 永不执行（行为图不记录）
runtime/engine.py:945-957   slow_path 触发分支     → 永不执行（D6「无 slow_path」根因）
runtime/engine.py:1166-1182 对话模式喂因果链        → 永不执行
event/cognitive_loop.py:55  BehaviorLearner 读 _causal_planner → 恒 None
cli/commands/p10_cmd.py:166 cmd_causal_trigger    → 恒 "causal planner not loaded"
cli/commands/assoc_cmd.py:66 causal/blocked 查询   → 恒空
api/stubs_api.py:336        _causal_planner fallback → 恒 None
```

### 1.4 与 D6 的衔接
```
关联链审计 D6「CausalPlanner 无 slow_path」→ 本次勘误补充根因:
  不是"没有实现 slow_path"，而是**整个 CausalPlanner 从未被实例化注入引擎**，
  slow_path 的代码（engine.py:945-957）其实已经写好，只是被恒 False 的守卫挡住。
```

---

## 二、cognition/hub.py（4.3KB）— 真接线但数据源断

### 2.1 接线现状（探针实测）
```
CognitionHub.is_loaded = True
status = {hypothesis_engine: True, belief_accumulator: True, relation_extractor: True}
消费方:
  bootstrap_v6.py:120-125  _load_cognition_hub()       ← 已接线（A 路径）
  agent_native.py:35       _cognition_hub 注入         ← 已接线
  agent_native.py:270-276  if is_loaded: converge()    ← 真调用
```

### 2.2 数据源断点
```
ingest_relations(relations) 全库 0 调用方
→ _relations_buffer 恒空 → converge() 循环喂 hypothesis 为空 →
  result 恒 {active_beliefs: [], resolved: 0, frozen_knowledge: 0}
→ 关联链 funnel 的产出（RelationClusterer 目标）从未喂给 CognitionHub
```

### 2.3 结论
- 与执行层/pcr/主题树相反：cognition 是"引擎调用了、但没人给数据"。
- 待接线: association funnel 或 compiler/llm_relation_extractor 的产出 → hub.ingest_relations()。

---

## 三、assembly/（context_assembly 6.4KB + unified_context 8.9KB）— 薄包装

### 3.1 UnifiedContext — "unified" 名不副实
```
设计宣称: 合并 context/ pipeline（Assembler+Budget+Prune+IR+Store+Window）
          × context_manager/ runtime（DiscourseManager+SemanticIndex+ContextLayer）
实况: DiscourseManager 集成整段注释（"v3 unmaintained module with heavy dependency
      chain... Skipping for v6 minimal loop"）→ _discourse_manager 恒 None
      → 只加载 context/ pipeline 半边，"unified" 另一半不存在
```

### 3.2 ContextAssembly — 纯转发
```
组装 ContextAssembler/BudgetAllocator/SubgraphCompiler/Pruner 的薄壳，
与上下文审计的 ContextAssembly 主体重复（本目录是精简复刻）。
```

### 3.3 消费方
```
blueprint/executor.py:106-107  UnifiedContext()（蓝图执行）
engineering_bridges.py:177-178  ContextBridge → UnifiedContext()
agent_native.py:336             _try_load_context → UnifiedContext()
bootstrap_v6.py:113-114         _load_unified_context → UnifiedContext()
→ 装配层已接线（bootstrap 探针 Context loaded=True）
```

---

## 四、discourse/models.py（1.9KB 薄壳）— 残留门面

### 4.1 内容
```
CrossReference / GroupReference / DiscourseBlock / DiscourseBlockTreeManager（内存版）
— 与 discourse_block_tree/（已审计，真实现）同名概念的最小残留
```

### 4.2 断点（探针实测）
```
inspect_v3_cmd.py:53: from core.agent.discourse import DiscourseBlockTree
  → ImportError: cannot import name 'DiscourseBlockTree' from 'core.agent.discourse'
  → 被 try/except ImportError 吞掉 → inspect 显示 "module not found"（静默降级）
```

### 4.3 结论
- 用户编辑树归并对话树审计的结论不变；discourse/ 包应并入对话树门面或归档。

---

## 五、问题清单

| # | 级别 | 问题 | 方向 |
|---|---|---|---|
| C1 | P1 | CausalPlanner 全库零实例化（引擎 3 分支恒死）| runtime engine 注入（_try_load 模式）或删除死分支 |
| C2 | P1 | CognitionHub.ingest_relations 零调用（converge 空转）| 接 association funnel 产出 |
| C3 | P2 | UnifiedContext 的 DiscourseManager 半边被注释（"unified" 名不副实）| 拍板：修依赖链 or 改名/归档 |
| C4 | P2 | discourse/ 包缺 DiscourseBlockTree 符号（inspect CLI 断）| 补门面 or 归档薄壳 |
| C5 | P3 | `_behavior_brain`/`_behavior_graph_adapter`/`_causal_substrate_adapter` 声明后零赋值 | 与行为链 P0 断链联动清理 |

---

## 六、与全局拍板池的关系

- **P-1 接线断裂** +2 例: CausalPlanner（引擎侧零注入）+ CognitionHub（数据侧零喂入）。
- **P-2 多代演进分裂** +1 例: discourse/ 薄壳 vs discourse_block_tree/ 真实现。
- **P-4 双路径分裂** +1 例: cognition/assembly 只在 A 路径（agent_native）接线，
  B 路径（runtime/cli）不消费——与执行层同型。

