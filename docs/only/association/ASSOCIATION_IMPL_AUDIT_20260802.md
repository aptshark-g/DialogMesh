# 关联链实现深度审计 — 2026-08-02

> 目的: 逐文件核查关联链实现的真实状态——四套并行实现、断链 D1-D8 根因链、真实接线方、测试质量。为施工提供精确的修复清单。
> 方法: 源码精读（24+13 文件）+ 探针实测（断链/实例化）+ 测试运行（v3_2 旧测试包 41 项）+ 接线追踪（引用方全量）。
> 前置: `ASSOCIATION_AUDIT_ENTRY_20260802.md`（资产盘点）+ `DESIGN_DEEP_READ_ASSOCIATION_20260802.md`（设计基准）+ `DESIGN_PHILOSOPHY_CHECK_20260802.md`（哲学红线）。

---

## 1. 审计结论先行

**关联链实现 = "组件完备、整链未通"**：
- ✅ 25 个核心组件真实可运行（L1-L4 分层实现 + 融合引擎 + 指代消解 + 配置驱动）
- ❌ 整条链没有任何一条完整路径被引擎调用（冷路径 D4 从未实例化；事件订阅 D7 缺依赖）
- ❌ L5 因果基板 stub 断链（D1/D2/D5），正确模型残留在 v3_2
- ❌ 三处 CausalSubstrateAdapter 命名分裂、四套并行实现、双 BeliefAccumulator
- ⚠️ 测试 40+1 中 1 挂（正是 stub 断链），但设计 8 文件 13 测试通过（浅断言）

---

## 2. 四套并行实现全景（带真实状态）

| # | 实现 | 文件 | 状态 | 谁在用 |
|---|------|------|------|--------|
| 1 | **分层 L1-L5** | `l1_modifier/l1_5_completer/l2_5_belief/l3_intent/l4_temporal/l4_collaborative` | ✅ 组件级可用 | `cli/registry.py` Tier5 注册（l1_modifier/l1_5_completer/l2_5_belief/l3_validator）；`event/subscribers.py` 想用但 engine 缺属性（D7）|
| 2 | **旧漏斗 V2** | `association_funnel.py` | ✅ 可运行（实测 funnel.run() 出结果）| `assoc_subscriber.py` + `v4/assoc_subscriber.py`（但从未被 engine 实例化 D4）|
| 3 | **v4 belief_map** | `v4/cognitive/belief_map.py` | ✅ 加载成功 | `v4/cognitive_bridge.py` 注册为 "belief_map"（实测 13/13 加载）|
| 4 | **v3_2 残留模型** | `v3_2/causal_substrate/models.py` | ✅ 正确的 `CausalConstraints`/`SkeletonMatch`（带 to_prior）| 无——顶层 `association/models.py` 反而是 stub（D1/D5）|

**关键判断**: 第 4 套（v3_2 残留）是 D1/D2/D5 的根修方向——把正确 dataclass 迁回顶层替换 stub，而不是重写算法。

---

## 3. 断链 D1-D8 根因链（探针实测证据）

### D1: `skeleton_matcher.py` 用 stub 的 `CausalConstraints`

- `models.py:21` `class CausalConstraints: pass`（无字段）
- `skeleton_matcher.py:27` `CausalConstraints(*mapped)` → **TypeError: CausalConstraints() takes no arguments**
- 实测: `skeleton_matcher.ConstraintExtractor.extract` → FAIL
- 根因: v3_2 迁移时正确模型未搬全（`v3_2/causal_substrate/models.py` 有完整 dataclass）

### D2: `causal_substrate.py` 调 `m.to_prior()`

- `models.py:15` `class SkeletonMatch` 是普通类（无 `__init__`、无 `to_prior`）
- `causal_substrate.py:24` `m.to_prior()` → AttributeError
- 实测: `causal_substrate.process_single` → FAIL（先被 D1 拦截）
- 根因: 同 D1——正确 `SkeletonMatch.to_prior()` 残留在 v3_2

### D3: `v4/causal_substrate/source.py` import 不存在

- `source.py:10` `from core.agent.causal_substrate.adapter import V4CausalSubstrate`
- 实测: **ImportError: cannot import name 'V4CausalSubstrate'**（adapter 只导出 CausalSubstrateAdapter/CausalContextEntry/CausalInsight）
- 影响: `CausalSource` 整个模块不可 import（但无调用方，所以未触发）

### D4: `runtime/engine.py` 关联链冷路径从未运行（最高危）

- `engine.py:431` `if text and self._l1_extractor:` — `_l1_extractor` **从未赋值**（全库仅此一处引用）
- `engine.py:433` `self._run_association_chain(event, text, pcr_output)` — 方法**不存在**（全库仅此一处调用）
- 实测: `hasattr(CognitiveRuntimeEngine, '_run_association_chain')` = **False**
- 影响: AttributeError 被 `try/except` 吞掉（L435）→ **关联链在 runtime 主路径从未运行，且无任何日志**
- 与 PCR/行为链同型: "多代演进 → 代码分裂 → 旧路径断裂被 try/except 吞 → 静默降级"

### D5: `v3_2/causal_substrate/__init__.py` 断链

- `v3_2/causal_substrate/__init__.py:2` `from core.agent.causal_substrate.adapter import CausalSubstrate` — adapter 无此导出 → ImportError
- `:3` `from core.agent.causal_substrate.models import ...` — **顶层 models 不存在** → ImportError
- 影响: 任何 import `core.agent.v3_2.causal_substrate` 都会炸（v3_2 兼容层失效）

### D6: `event/cognitive_loop.py` 调不存在的 `slow_path`

- `cognitive_loop.py:56` `if cp and hasattr(cp, 'slow_path'):` — CausalPlanner 只有 `record_step/process_chain`，无 `slow_path`
- 影响: hasattr 返回 False → 静默跳过（不是崩溃，但学习闭环从未触发因果路径）

### D7: `event/subscribers.py` AssociationSubscriber 缺依赖

- `subscribers.py:95` `AssociationSubscriber.handle()` 用 `engine._l1_modifier` / `engine._l2_5_belief`
- 实测: 生产 engine 无这两个属性（只有测试 dummy 赋值）→ `getattr` 返回 None → **静默无操作**
- 注意: `cli/registry.py` 注册了 `l1_modifier`/`l2_5_belief` 但挂在不同 key，`wire_subscribers` 找 `_l1_modifier` 找不到

### D8: `v3_2/tests/test_causal_substrate/test_core.py` 导入即挂

- `test_core.py:18` `from core.agent.association.models import CausalConstraints`（stub）
- 实测: **1 failed / 40 passed** — `TestMatcher.test_match_none` → AttributeError: 'CausalConstraints' object has no attribute 'domain_hint'
- 影响: 旧测试包 41 项中唯一失败，正是 D1 同根因

---

## 4. 接线审计（谁真正调用/不调用）

### 4.1 真实接线（✅ 有调用方）

| 接线 | 路径 | 状态 |
|------|------|------|
| CLI lazy loader | `cli/engine.py:162-166` 注册 `_pronoun_resolver/_context_qualifier/_semantic_coref/_hybrid_coref/_entity_extractor` | ✅ 但 CLI engine 与 runtime engine 是两套 |
| CLI registry Tier5 | `cli/registry.py:333-350` 注册 `l1_modifier/l1_5_completer/l2_5_belief/l3_validator/belief_map` | ✅ 注册存在 |
| v4 bridge | `v4/cognitive_bridge.py` 13 模块加载（实测 `belief_map` 在内）| ✅ 13/13 |
| CognitionHub | `agent_native.py` + `bootstrap_v6.py` 加载（含 L2.5 BeliefAccumulator）| ✅ 真实接线 |
| CausalSource | `context/source.py:700` 完整实现（graph.get_chain + substrate.process_chain）| ⚠️ 依赖 D1/D2，运行即吞异常 |

### 4.2 假接线/断裂（❌ 设计说有线、实际没有）

| 声称 | 实际 |
|------|------|
| runtime engine 冷路径（`_run_association_chain`）| 方法不存在（D4）→ 从未运行 |
| `event/subscribers.py` AssociationSubscriber | engine 无 `_l1_modifier/_l2_5_belief`（D7）→ 静默无操作 |
| `event/cognitive_loop.py` BehaviorLearner | CausalPlanner 无 `slow_path`（D6）→ 因果路径从未触发 |
| `api/stubs_api.py` /relations /causal | 返回空壳（`edge_count: 0`、`relations: []`）|
| `handlers.py` register_pipeline_handlers | **ImportError**（函数名不存在——实际是 `register_handlers` 或内联 `sm.register_handler`）|
| NATS 事件桥 | `nats_bridge.py` 启动重连风暴（无 NATS 服务器时反复重试）——阻塞 engine 启动 |

### 4.3 关键架构判断：三套 engine 路径

```
路径 A: cli/engine.py start_engine → CLI registry（assoc_subscriber 工厂注册，但 bus=None 不订阅）
路径 B: runtime/engine.py CognitiveRuntimeEngine → _l1_extractor 不存在（D4）
路径 C: orchestrator/agent_native.py AgentOrchestrator → CognitionHub（真实加载 L2.5）

→ 关联链组件在 C 路径真实加载，但 A/B 路径均未接通完整漏斗
```

---

## 5. 测试质量审计（真实运行）

### 5.1 v3_2 旧测试包（41 项实测）

```
40 passed / 1 failed（0.75s）
FAILED: test_causal_substrate/test_core.py::TestMatcher::test_match_none
  AttributeError: 'CausalConstraints' object has no attribute 'domain_hint'  ← D1 同根因
```

### 5.2 设计层测试（13 项实测）

```
test_association_funnel.py (2) + test_l1_modifiers.py (4) + test_l1_5_completer.py (1)
+ test_l2_5_belief.py (3) + test_l3_intent.py (1) + test_multi_intent_split.py (2) = 13 passed
```

**质量警示**: 断言多为 `> 0` / `llm_calls > 0` 类浅断言——**"绿了不代表对"**（违背 A18 验证必须真实）。

### 5.3 环境差异（anaconda vs .venv）

- anaconda (3.9): `-pronoun_resolver SKIPPED: numpy 版本不兼容`、`-relation_graph SKIPPED: numpy.dtype size changed`
- .venv (3.13): 模型完整但无 pytest
- NATS 无服务器 → engine 启动重连风暴（`allow_reconnect=False` 修复未覆盖 anaconda 路径）

---

## 6. 设计↔实现对照（设计基准 → 实现状态）

| 设计点 | 实现 | 差距 |
|--------|------|------|
| L1 Stanza 依存 + 39 deprel config | `l1_modifier.py` ✅ | 旧契约（收 stanza Document）；新 L1=PronounResolver（已修 zh coref）|
| L1 指代消解 T1+T2+T3 | `hybrid_coref.py` ✅ | anaconda 环境 numpy 坏 → SKIPPED；需 .venv 验证 |
| L1.5 快慢双通道 | `l1_5_completer.py` ✅ | nomic 走 127.0.0.1:1234 LM Studio（非统一网关）|
| L2 语义本体 | `compiler/relation_substrate.py` ✅ | **无产出路径**（18 处引用但无调用方写入）|
| L2.5 贝叶斯+7D | `l2_5_belief.py` ✅ | 7D 是说明字段，概率主导（A4 哲学要求 7D 决策）|
| L3 四视角投票 | `l3_intent.py` ✅ | 无 `validate_split()`（多意图拆分设计要求扩展）|
| L3 多意图拆分 | `intent/multi_perspective.py` ✅ | Multi-Agent 辩论模式 ≠ 设计五链路（chain_verifier 未实现）|
| L4 时序+漂移 | `l4_temporal.py` + `l4_collaborative.py` ✅ | **0 测试** |
| L5 因果基板 | `causal_substrate.py` ❌ | D1/D2/D5 断链；骨架库 5/20 |
| do-calculus | `do_calculus/` ✅ 实现完整 | **零调用方**（仅 integration.py 引用，integration 断链）|
| 前置富化器 | `cli/engine.py:162-163` 注册 | runtime engine 未注册（两套不一致）|
| 冷路径 Event Sourcing | `event/storage.py` + `assoc_subscriber.py` | D4 从未实例化 |
| 广播风暴隔离（微服务）| — | 蓝图 §7.3 P1 未做 |
| 白盒化（A19）| — | 无 API/CLI CRUD（stubs_api 空壳）|

---

## 7. P0/P1 修复清单（施工输入）

### P0 — 断链根修（让已存在的代码可运行）

| # | 修复 | 文件 | 工作量 |
|---|------|------|:---:|
| F1 | `models.py` 替换 stub：把 `v3_2/causal_substrate/models.py` 的正确 `CausalConstraints`/`SkeletonMatch`（带 `to_prior`）迁回顶层 | `association/models.py` | 小 |
| F2 | `skeleton_matcher.py` 对齐新 models（`CausalConstraints(*mapped)` / `SkeletonMatch(...)`）| `association/skeleton_matcher.py` | 小 |
| F3 | `v3_2/causal_substrate/__init__.py` 修正为从顶层 import（或本地 re-export）| `v3_2/causal_substrate/__init__.py` | 小 |
| F4 | `v4/causal_substrate/source.py` 的 `V4CausalSubstrate` → `CausalSubstrateAdapter` 或本地定义 | `v4/causal_substrate/source.py` | 小 |
| F5 | `runtime/engine.py` 冷路径接线：补 `_l1_extractor` 赋值 + `_run_association_chain` 实现（或删除死调用）| `runtime/engine.py` | 中 |
| F6 | `event/subscribers.py` 依赖对齐：engine 补 `_l1_modifier`/`_l2_5_belief` 或改 key 名 | `event/subscribers.py` + `cli/registry.py` | 小 |
| F7 | `topic_quick_match.py` 修 `from __future__` 位置（SyntaxError，阻塞 test_l2_entity_graph 收集）| `compiler/topic_quick_match.py` | 小 |
| F8 | `event/cognitive_loop.py` 的 `slow_path()` → `process_chain()`（或加方法）| `event/cognitive_loop.py` | 小 |

### P1 — 设计接入（让组件进入真实链路）

| # | 内容 | 依据 |
|---|------|------|
| F9 | `RelationSubstrate` 接入引擎（写入产出路径）| A3 关系必须可查询（哲学红线）|
| F10 | L3 `validate_split()` 扩展（多意图拆分）| ENGINEERING_MULTI_INTENT_SPLIT |
| F11 | 关联链 CRUD CLI/API（`dm assoc` 系列）| A19 白盒化（哲学红线）|
| F12 | do-calculus 接入负向验证（HARD_BLOCK）| A22 因果克制（哲学红线）|
| F13 | 测试重写：黄金样例集 + 真实断言 | A18 验证必须真实（哲学红线）|
| F14 | L4/L5 补测试（当前 0 测试）| 与 F13 合并 |

---

## 8. 诚实评估

**比预期好的**:
- 分层 L1-L5 组件质量不低（配置驱动、无硬编码词表、LLM 降级路径齐全）
- `compiler/relation_substrate.py` 是完整实现（V3 更新过），不是空壳
- `do_calculus` 引擎完整（Pearl 三规则 + backdoor），只是无调用方
- v4 bridge 13/13 加载成功，belief_map 真实可用

**比预期差的**:
- runtime 冷路径连"假接线"都算不上——方法是**不存在**的（D4），比"未接线"更糟
- 三套 engine 路径（CLI/runtime/agent_native）各自为政，关联链组件散落其中
- 旧测试 40/41 通过掩盖了 stub 断链（唯一失败项恰好暴露 D1）
- NATS 重连风暴阻塞 engine 启动——之前 STATE_HANDOFF 记录"已修"的 allow_reconnect=False 在 anaconda 环境未生效

---

## 9. 施工建议（与 P0_RETRO 同模式）

1. **先 F1-F8（断链根修）** → 关联链组件全部可 import/可运行，旧测试 41/41 绿
2. **再 F5 冷路径接线** → runtime engine 首次真正跑关联链（对齐蓝图 §7.3 混合式）
3. **然后 F9-F12 设计接入** → RelationSubstrate 产出 + do-calculus 负向 + 白盒 CLI
4. **最后 F13-F14 测试重写** → 黄金样例集 + 对抗性断言（拒绝浅断言）

> 依赖提醒: F5 冷路径接线与蓝图 §7.3（关联链独立服务）有先后关系——先接线验证漏斗，再做服务化隔离。

--- END OF DOCUMENT ---
