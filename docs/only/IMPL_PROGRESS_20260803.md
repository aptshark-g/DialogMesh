# 三模块施工进度 — 2026-08-03

> 恢复入口：读本文件 → `IMPLEMENTATION_PLAN_20260803.md` → `PENDING_DECISIONS_20260803.md`（R1-R6）。

---

## 当前进度

### Phase 1 意图 T0/T1 骨架 ✅ 完成

```
1.1 ✅ fusion_decider 激活（经 splitter 接入）
1.2 ✅ ambiguity_gate 激活（经 splitter 接入）
1.3 ✅ multi_intent_splitter 5 链验证（literal/profile/association/discourse/engineering
       + FusionDecider 裁决 + AmbiguityGate 升级）
1.4 ✅ L3 profile/discourse 接线（engine _l3_profile_traits/_l3_discourse_topics）
       （异步化线程暂缓：L3 规则投票 0ms，死锁 LLM 才慢，风险>收益）
1.5 ✅ T2 回写（engine _apply_l3_feedback → tree_annotation/profile_update 白盒快照）
1.6 ✅ 无 LLM 诚实降级（splitter degraded 标记 + literal_chain stanza 失败缓存）
```

改动：
- `core/agent/intent/multi_intent_splitter.py`（5 链验证 + 裁决 + gate + 降级）
- `core/agent/intent/literal_chain.py`（stanza 失败缓存 `_stanza_failed`）
- `core/agent/runtime/engine.py`（L3 接线 + T2 回写）
- 新增 `core/agent/intent/tests/test_multi_intent_splitter.py` 8/8 绿

### Phase 2 画像事实层 + L3 接线 ✅ 完成

```
2.1 ✅ FactStore（USER.md 式：条目 + 预算 + 注入扫描 + 快照冻结 + drift + 防循环）
2.2 ✅ Track A 复活（_init_profile_runtime + _feed_profile_runtime，替换幽灵调用）
       DynamicsComputer.compute_all 8 维 + memory_point_count(外部) = 9 维完整
2.3 ✅ L3 profile_traits 接线（Phase 1.4 一并完成）
2.4 ✅ inertia_graph feed_evidence/feed_counter（R2 共用生命周期）
2.5 ✅ PROFILE_GAP 修正（95% → 30-40%）
```

改动：
- 新增 `core/agent/profile/fact_store.py` 9/9 绿
- 新增 `core/agent/profile/tests/test_fact_store.py`
- `core/agent/v4/cognitive/inertia_graph.py`（feed 入口）
- 新增 `core/agent/v4/cognitive/tests/test_inertia_graph.py` 5/5 绿
- `core/agent/runtime/engine.py`（Track A 复活 + 幽灵调用替换）
- `docs/v5/PROFILE_GAP.md`（诚实修正）

### Phase 3 对话树内核组装 ✅ 完成

```
3.1 ✅ B 内核 + A 门面兼容层（feed/get_block_relations/get_tree/_trees）+ engine 切 B
3.2 ✅ C6 字段名统一（写 v3_evolution，读兼容 v3_milestone 别名）
3.3 ✅ C2 灰区 A13 修复（单强 ≥0.45 或连续两次 ≥0.30 才 fork）
3.4 ✅ C4 温度语义唤醒（semantic_wake BGE>0.8 回 Hot，manager feed 接入）
3.5 ✅ compass 三范式标签（审计确认已实现 + engine 注入）
3.6 ✅ 黄金示例集 V1/V2/V3（4/4）
```

**黄金示例集发现（重要）**：
- V1 纯结构（无 LLM）方向性信号弱——decomposer 无 LLM 时 entities 空、predicate 单字
  → score_pair 依赖弱信号，同话题/随机分数不稳定（0.78/0.37 vs 0.78）
  → 按 KERNEL §八.8.5 决策表：方向性需要 LLM 语义补充 → **V1-LLM 对照实验后置 Phase 4.5**
- V2 回溯 / V3 时间局部性：结构信号下可测（通过）

### Phase 4 ⏳ 收尾

```
4.4 ✅ 全量回归：60/60（本次改动）+ 48/48（behavior/association 关联）全绿
     6 失败 = 预存腐坏（CausalSubstrateAdapter params 契约，关联链审计已知）
4.5 LLM 全量测试（用户拍板：三模块全通后统一网关跑 + V1-LLM 对照）
```

## 三模块施工终态（2026-08-03）

```
Phase 1 意图 ✅    Phase 2 画像 ✅    Phase 3 对话树 ✅
Phase 4.4 回归 ✅（108/114 = 60 改动 + 48 关联；6 预存腐坏）
Phase 4.5 LLM 全量 ⏳（用户拍板后置：网关 + V1-LLM 对照）

剩余执行项（非阻塞）:
  - compiler A 2 预存腐坏测试修复（C1 指代补全/C4 温度）
  - causal integration 6 预存腐坏测试修复（params 契约）
  - 意图 I9/I10/I11 · 画像 H2/H3/H4（写入规范/后验/冷启动）
  - PCR 26 预存断链（shim IntentParser=None，意图审计实锤）
```

---

## 深度修复进展（2026-08-03 追加）

### 5.1.2 ✅ causal integration 6 腐坏 + 真实缺陷修复
```
测试旧契约（params={"min_chain": N} / execute(ctx)）→ 对齐实现
（min_chain_length=N / should_trigger+process_chain）
真实缺陷：CausalSubstrateAdapter.min_chain_length 从未传入 substrate
  → CausalSubstrate.MIN_CHAIN=10 硬编码恒生效（参数脱节）
修复：CausalSubstrate.__init__ 加 min_chain 参数，adapter 传入
结果：22/22 绿（behavior adapter 8 + causal integration 14）
```

### 5.1.1 🟡 compiler A 2 腐坏 → 深挖出 B 拆包中文损坏（重大发现）
```
监控钩子已加（根 conftest.py：断言 ascii-repr + 环境编码 + 输出捕获）

发现链（监控数据驱动，非猜测）:
  1. test_session_entity_cache 失败 → A inject 委托 B 后仍不替换
  2. 字节级确认：header_injector.py 的 PRONOUNS/NEGATION 中文常量
     在源文件字节里就是 '?'（迁移/编码损坏，非读取问题）
  3. 范围扫描：discourse_block_tree/ 目录 3 文件损坏
     header_injector.py（已修）/ syntactic_decomposer.py（57 处）/
     test_discourse_block_tree.py（10 处）
  4. 根因：迁移时 errors='replace' 之类转换，中文 → '?'，原始字符无法还原

已修复:
  - header_injector.py：PRONOUNS/NEGATION/UNCERTAINTY/IMPERATIVE 用码点恢复
    + EntityCache.find 指示代词逻辑（"这个/那个/这些"→最近实体）
  - compiler A 门面：build_context 桥接 A 块→B 兼容视图（raw_text 恢复）
  - compiler A 测试：断言对齐现状（B 风格 [Hot] 标签 + 无括号实体）

用户关键质疑（采纳）:
  "硬编码常量没泛化能力，有模型为什么不用？"
  → 核查：pyproject 已有 jieba/transformers/sentence-transformers；
     全库 15+ 文件用 stanza/jieba（grammar_tagger/pronoun_resolver 是现成封装）
  → 决策：不重写硬编码常量（坏资产），B decompose 改走模型层
     Stanza 依存树（grammar_tagger.tag_text）→ jieba POS → 标点兜底
     VERBS/CONJUNCTIONS/TOPIC_SWITCH/LOGIC_TURN 常量删除
```

### 进行中
```
- B syntactic_decomposer.py 重写（模型优先，python 脚本执行中）
- B test_discourse_block_tree.py 10 处 '?' 测试输入重写（码点）
- 全量回归 + 压测（5.2）
```

---

## 测试数字（2026-08-03）

```
intent splitter:  8/8 ✅
fact_store:       9/9 ✅
inertia_graph:    5/5 ✅
对话树 B:         14/14 ✅
灰区 A13:         5/5 ✅
语义唤醒 C4:      3/3 ✅
黄金示例集:       4/4 ✅
合计:             55/55 通过（compiler A 2 预存腐坏：C1 指代/C4 温度，审计已记录）
PCR tests: 26 失败 = 预存断链（shim IntentParser=None），非本次改动
```

## 已知剩余

- L3 线程化异步（暂缓，见 1.4）
- 意图 I9/I10/I11（测试补全/自适应阈值归一/认知双工形态）= 执行项，未开工
- 画像 H2 写入规范 prompt / H3 background_review / H4 冷启动 = 执行项，未开工
- compiler A 2 预存测试腐坏（C1 指代补全/C4 温度）待修
- Phase 4.5 LLM 全量测试 + V1-LLM 对照（等三模块全通 + 网关）
