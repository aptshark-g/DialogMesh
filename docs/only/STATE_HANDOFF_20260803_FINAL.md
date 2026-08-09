# 压缩交接终态 — 2026-08-03（三模块施工 + 深度修复完成态）

> 本文件是压缩后唯一恢复入口。恢复顺序：本文件 → `IMPL_PROGRESS_20260803.md` → `IMPLEMENTATION_PLAN_20260803.md` → `PENDING_DECISIONS_20260803.md`。

---

## 一、完成态总览（R1-R6 拍板全部落地）

| 阶段 | 状态 | 成果 |
|---|---|---|
| Phase 1 意图 | ✅ | 5 链验证 + FusionDecider + AmbiguityGate + L3 profile/discourse 接线 + T2 回写 + 无 LLM 降级 |
| Phase 2 画像 | ✅ | FactStore + Track A 复活 + inertia feed + PROFILE_GAP 修正 |
| Phase 3 对话树 | ✅ | engine 切 B + A 门面兼容 + C6/C2/C4 修复 + 黄金示例集 V1/V2/V3 |
| Phase 4.4 回归 | ✅ | 60/60 改动模块 + 48/48 关联 |
| 深度修复 | ✅ | causal 6 + compiler A 2 + B 拆包中文损坏（3 文件）+ decompose 模型优先重写 |
| 压测 5.2 | 🟡 | FactStore stress 暴露**批量写缺陷未修**（见 §三）|

---

## 二、代码改动清单（git diff 全部内容）

### 意图（Phase 1）
- `core/agent/intent/multi_intent_splitter.py`：5 链验证（literal/profile/association/discourse/engineering）+ FusionDecider 裁决 + AmbiguityGate 升级 + 无 LLM 显式 degraded + 结构兜底
- `core/agent/intent/literal_chain.py`：`_stanza_failed` 失败缓存（环境坑防御）
- `core/agent/runtime/engine.py`：`_l3_profile_traits`/`_l3_discourse_topics`/`_apply_l3_feedback`（T2 回写）
- 新增 `core/agent/intent/tests/test_multi_intent_splitter.py` 8/8

### 画像（Phase 2）
- 新增 `core/agent/profile/fact_store.py`（FactStore：条目 + 预算 + 注入扫描 + 快照冻结 + drift + 防循环）
- 新增 `core/agent/profile/tests/test_fact_store.py` 9/9
- `core/agent/runtime/engine.py`：`_init_profile_runtime`/`_feed_profile_runtime`（Track A 复活，替换幽灵调用）+ `_l3_discourse_topic_weights`
- `core/agent/v4/cognitive/inertia_graph.py`：`feed_evidence`/`feed_counter`（R2 生命周期）
- 新增 `core/agent/v4/cognitive/tests/test_inertia_graph.py` 5/5
- `docs/v5/PROFILE_GAP.md`：95% → 30-40% 诚实修正

### 对话树（Phase 3）
- `core/agent/runtime/engine.py`：`_discourse_tree` import 切 B（`discourse_block_tree.manager`）
- `core/agent/discourse_block_tree/manager.py`：A 兼容门面（`feed`/`get_block_relations`/`get_tree`/`_trees`）+ `semantic_wake` 接入
- `core/agent/discourse_block_tree/summary_engine.py`：`v3_evolution` 写 + 兼容读 + `semantic_wake`（BGE>0.8 回 Hot）
- `core/agent/compiler/discourse_block_tree.py`：C2 灰区 A13（`_gray_scores`/`_gray_should_fork`）+ HeaderInjector 委托 B + build_context 桥接 B 视图
- `core/agent/compiler/three_paradigm_context.py`：`v3_evolution` 兼容读
- 新增测试：test_gray_zone_a13.py 5/5 + test_semantic_wake.py 3/3 + test_golden_axiom.py 4/4 + test_stress.py 2/2

### 深度修复（Phase 5.1）
- `core/agent/runtime/tests/test_behavior_causal_integration.py`：6 腐坏测试重写（params→min_chain_length / execute→should_trigger+process_chain）
- `core/agent/association/causal_substrate.py`：`min_chain` 参数（修复 adapter 参数脱节真实缺陷）
- `core/agent/behavior/causal_adapter.py`：substrate 构造传 min_chain
- `core/agent/discourse_block_tree/header_injector.py`：PRONOUNS/NEGATION/UNCERTAINTY/IMPERATIVE 码点恢复 + EntityCache.find 指示代词
- `core/agent/discourse_block_tree/syntactic_decomposer.py`：**整体重写**（模型优先三层：Stanza grammar_tagger → jieba POS → 标点兜底；删 VERBS/CONJUNCTIONS 硬编码；补全角逗号 65292）
- `core/agent/discourse_block_tree/test_discourse_block_tree.py`：整体重写（码点中文 + 修 worktree 路径 + 对齐新契约）
- `core/agent/compiler/tests/test_discourse_block_tree.py`：2 断言对齐（B 风格 [Hot] + 无括号实体）
- 新增根 `conftest.py`：**测试监控**（ascii repr + 环境编码 + 输出捕获，防猜）

---

## 三、未完成/待办（恢复后继续）

### 🔴 压测暴露缺陷（未修）
```
5.2.1 FactStore stress 失败（2 项）:
  - test_fact_store_1000_writes: 预算 20000 只容纳 490 条（压测参数错，非缺陷）
  - test_fact_store_budget_rejection_fast: 超时
  → 根因（用户指出）：FactStore 每次 add 全量落盘 + drift 读盘 = 磁盘 thrash
  → 修复方向（已讨论未实施）:
    a. 内存脏标记 + apply_batch + 显式 save()（批量一次 IO）
    b. 可选热层：cache_layer.py / service/stores/redis.py（有 redis server 才启用）
    c. 多线程：会话级 KeyedOperationQueue 模式（复用 Pi 同款），不做全局锁
```

### 🟡 存储架构讨论（未拍板，用户提出）
```
用户问题链:
  1. "没加 redis 吗？适合多线程吗？" → 核查：项目无 redis 依赖，但有
     service/stores/redis.py + event/redis_otel.py（预留）；主力 = SQLite
  2. "SQLite 能做向量 RAG？能做图存储？" → SQLite 原生不能，但项目已有
     unified_store(BGE+LSH) + sqlite index_vectors(512-dim blob) + graph_store
  3. "自己搓的 FactStore 效率可行吗？更强 DB 收益更高？SQLite 太小怎么拓展？"
  → 结论待拍板: FactStore 应接统一存储层（sqlite_store/unified_store/cache_layer）
    而非纯文件 USER.md（Hermes 单机模式）。SQLite 拓展措施：WAL + FTS5 +
    sqlite-vec 扩展 + 存储抽象层（可切 PG/Redis）。单用户桌面场景 SQLite 够用；
    多用户服务才需 PG/pgvector。
  → 参考文档: 未写，待拍板后落盘
```

### ⏳ 其余待办（此前已记录）
```
- Phase 4.5 LLM 全量测试 + V1-LLM 对照（用户拍板：三模块全通后统一网关跑）
- 意图 I9/I10/I11（测试补全/自适应阈值归一/认知双工形态）
- 画像 H2 写入规范 prompt / H3 background_review / H4 consent-gated 冷启动
- PCR 26 预存断链（shim IntentParser=None，I4 决议：新包替代）
- 压测 5.2.2 splitter / 5.2.3 inertia（未写，test_stress 只覆盖 FactStore+对话树）
```

---

## 四、测试数字（压缩前终态）

```
intent splitter:      8/8 ✅
fact_store:           9/9 ✅（stress 2 未过 = 缺陷未修）
inertia_graph:        5/5 ✅
test_cognitive:      12/12 ✅
对话树 B（重写后）:   15/15 ✅
compiler A:          18/18 ✅（含灰区 5）
黄金示例集:           4/4 ✅
语义唤醒:             3/3 ✅
stress:              2/4 ✅（FactStore 2 失败 = 待修）
behavior adapter:     8/8 ✅
causal integration:  14/14 ✅
总计（不含 stress）:  ~87/87 全绿
```

## 五、环境坑（回查）

```
- anaconda 3.9 pytest；numpy 坏 → stanza/BGE 路径静默降级（decompose 已加 jieba 层）
- PowerShell stdin 中文乱码 → UTF-8 文档用 apply_patch；测试输入用码点 \uXXXX
- pytest GBK 控制台 → 根 conftest.py 已强制 UTF-8 + ascii-repr 监控
- 测试命令模板: C:\Users\APTShark\anaconda3\python.exe -m pytest <files> -q --tb=short
```

## 六、git 状态
- 本轮改动未提交；不主动 commit
- 临时文件清理：`.tmp_t_adecomp.py` / `.tmp_monitor_hi.py`（工作区根，待删）
