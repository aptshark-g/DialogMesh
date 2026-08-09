# 三模块施工计划 — 2026-08-03（R1-R6 拍板后）

> 拍板依据：`docs/only/PENDING_DECISIONS_20260803.md`（R1 三时相 / R2 类别补种 / R3 意图接线 / R4 四通道 / R5 画像四层 / R6 对话树内核）。
> 施工顺序：意图 T0/T1 骨架 → 画像事实层+L3 接线 → 对话树内核组装 → 三模块测试+黄金示例集。

---

## Phase 1 — 意图 T0/T1 骨架（输入源，先立）

```
1.1 ✅ fusion_decider 激活（三策略 + PCR 调控）→ splitter 接入（R3）
1.2 ✅ ambiguity_gate 激活（5 触发器）→ splitter 接入（R3）
1.3 ✅ multi_intent_splitter 补 5 链验证（literal/profile/association/discourse/engineering
       + FusionDecider 裁决 + AmbiguityGate 升级）8/8 测试绿
1.4 🟡 L3 接线：validate() 传 profile_traits/discourse_topics（P4 完成）；
       异步化（线程）标记剩余（L3 规则投票 0ms，死锁 LLM 才慢，风险>收益暂缓）
1.5 ✅ T2 回写激活：_apply_l3_feedback（tree_annotation/profile_update 落白盒快照，A19）
1.6 ✅ 无 LLM 诚实降级（splitter 显式 degraded + literal_chain stanza 失败缓存）
```

改动文件：
- ✅ `core/agent/intent/multi_intent_splitter.py`（5 链验证 + 裁决 + gate + 降级）
- ✅ `core/agent/intent/literal_chain.py`（stanza 失败缓存防御）
- ✅ `core/agent/runtime/engine.py`（L3 profile/discourse 接线 + T2 回写）
- 🟡 `core/agent/intent/fusion_decider.py`（复用，未改；激活经 splitter）
- 🟡 `core/agent/intent/ambiguity_gate.py`（复用，未改；激活经 splitter）
- ⏳ `core/agent/association/l3_intent.py`（异步化剩余项，暂不改）

验证：`C:\Users\APTShark\anaconda3\python.exe -m pytest core/agent/intent/ core/agent/association/tests/ -q --tb=short`

实况（2026-08-03）：
- 新包测试 `core/agent/intent/tests/test_multi_intent_splitter.py` 8/8 绿
- PCR 26 失败 = 预存断链（shim IntentParser=None，意图审计实锤），与本次改动无关

---

## Phase 2 — 画像事实层 + L3 接线

```
2.1 ✅ 事实层存储（FactStore：条目列表 + 预算 + 注入扫描 + 快照冻结 + drift + 防循环）
2.2 ✅ Track A 复活接线（_init_profile_runtime + _feed_profile_runtime，替换幽灵调用；
       DynamicsComputer.compute_all 8 维 + memory_point_count(外部) = 9 维完整）
2.3 ✅ L3 profile_traits 接线（engine _l3_profile_traits，Phase 1.4 一并完成）
2.4 ✅ inertia_graph feed_evidence/feed_counter（R2 共用生命周期）5/5 测试绿
2.5 ✅ PROFILE_GAP 修正（95% → 30-40%，诚实标记）
```

改动文件：
- ✅ 新增 `core/agent/profile/fact_store.py`（9/9 测试绿）
- ✅ `core/agent/v4/cognitive/inertia_graph.py`（feed_evidence/feed_counter）5/5 测试绿
- ✅ `docs/v5/PROFILE_GAP.md`（修正）
- ✅ `core/agent/runtime/engine.py`（L3 profile/discourse 接线，Phase 1.4）
- ✅ `core/agent/runtime/engine.py`（Track A 复活 + 幽灵调用替换 + TrackB 轻量标签）

验证：画像黄金示例集（事实层写入/预算/注入扫描）+ 现有 test_cognitive.py

实况（2026-08-03）：22/22 绿（fact_store 9 + inertia 5 + intent splitter 8）

---

## Phase 3 — 对话树内核组装

```
3.1 ✅ B 内核 + A 门面兼容层（feed/get_block_relations/get_tree/_trees）+ engine 切 B
3.2 ✅ C6 字段名统一（写 v3_evolution，读兼容别名）B 14/14
3.3 ✅ C2 灰区 A13 修复（单强 ≥0.45 或连续两次 ≥0.30 才 fork）5/5 测试
3.4 ✅ C4 温度语义唤醒（semantic_wake BGE>0.8 回 Hot，manager feed 接入）3/3 测试
3.5 ✅ compass 三范式标签（审计已实现 + engine 注入，无改动）
3.6 ✅ 黄金示例集 V1/V2/V3（4/4 绿；V1 诚实记录：无 LLM 结构特征稀疏 → LLM 对照后置 Phase 4）
```

改动文件：
- ✅ `core/agent/discourse_block_tree/manager.py`（A 兼容门面 + 语义唤醒接入）
- ✅ `core/agent/discourse_block_tree/summary_engine.py`（v3_evolution + semantic_wake）
- ✅ `core/agent/compiler/discourse_block_tree.py`（C2 灰区 A13）
- ✅ `core/agent/compiler/three_paradigm_context.py`（v3_evolution 兼容读）
- ✅ `core/agent/runtime/engine.py`（_discourse_tree 切 B）
- ✅ 新增测试：test_gray_zone_a13.py 5/5 + test_semantic_wake.py 3/3 + C6 1/1

验证：`C:\Users\APTShark\anaconda3\python.exe -m pytest core/agent/compiler/ -q --tb=short`

实况（2026-08-03）：55/55 通过（compiler A 2 失败 = 预存测试腐坏 C1/C4，审计已记录，非本次改动）

---

## Phase 4 — 三模块测试 + 黄金示例集

```
4.1 ✅ 意图：新包 8/8（splitter 5 链验证路径）
4.2 ✅ 画像：FactStore 9/9 + inertia 5/5
4.3 ✅ 对话树：黄金示例集 4/4 + 灰区 5/5 + 语义唤醒 3/3 + C6 1/1 + B 14/14
4.4 🟡 全量回归（本轮 55/55 通过；compiler A 2 预存腐坏待修）
4.5 ⏳ LLM 全量测试（用户拍板：等三模块全通后统一网关跑，含 V1-LLM 对照）
```

---

## 风险与回退

- L3 异步化影响：回答窗口竞态（先出 T0 意图，T1 修正晚到）→ 修正走 T2 通道，不覆盖已发回复
- 意图 5 链验证补全：可能拖慢 T1 → 链验证并行 + 超时阈值（fusion_decider 已含 PCR 调控）
- 对话树 C+B+A 组装：B 生产不可达历史 → 先 import 探针 + 单测绿再切门面
- 无 LLM 环境：所有新接线必须有显式降级路径（Phase 1.6 是硬约束）

---

## Phase 5 — 深度修复 + 压测（2026-08-03 追加）

### 5.1 深度修复（预存腐坏，非本次改动引入但需清理）

```
5.1.1 compiler A 2 腐坏（C1 指代补全 / C4 温度）：
      A 已降级为门面（engine 走 B），修复 = 更新测试断言对齐架构现状，
      或修复 A 实现使设计一致 —— 按红线 7"一内核多门面"，A 门面转发正确即可
5.1.2 causal integration 6 腐坏：CausalSubstrateAdapter.__init__() 不接 params
      （测试旧契约）→ 加 params 兼容（min_chain 读取）或更新测试
5.1.3 PCR 26 预存断链：shim IntentParser=None（registry 文件丢失）
      → I4 决议执行：新包替代 + 测试改走新包（大改，单列）
```

### 5.2 压测（新增模块性能基线，pytest-benchmark 可用）

```
5.2.1 FactStore：批量 add/replace（预算内/外 + 注入扫描）耗时
5.2.2 MultiIntentSplitter：mock LLM 多轮 5 链验证吞吐
5.2.3 InertiaWeightGraph：大量 feed_evidence 状态机推进
5.2.4 对话树 B：长对话 feed（100 轮）块/温度/唤醒路径
```
