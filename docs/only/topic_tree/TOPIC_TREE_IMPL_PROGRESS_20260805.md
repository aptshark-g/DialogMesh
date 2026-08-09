# 主题树 T1-T7 施工记录（2026-08-05）

> 批次: 模块级补全第六批（主题树）。入口: `docs/only/context/TOPIC_TREE_MANAGER_V2_DEEP_READ_20260803.md`
> （T1-T7 问题清单来源）。对象: `core/agent/topic_tree/`（V2 内核 947L）+ 消费方接线。
> 原则: 一内核多门面（红线 7）/ 参数自适应（A18）/ 记录不删（A17）/ 边界纪律。

---

## 一、完成态（诚实汇报）

| 项 | 级别 | 内容 | 状态 |
|---|---|---|---|
| T1 | P1 | `EmbeddingEngine._load_model` 只 catch ImportError → 改宽异常兜底（环境 ValueError/TypeError 一律回退 hash） | ✅ |
| T2 | P1 | `context_assembly` 调不存在的 `get_current_branch` → V2 补真实现 + 消费方序列化 | ✅ |
| T3 | P1 | `engineering_bridges.TopicTreeBridge` 调不存在的 `get_active_path` → V2 补别名 + `get_summary` 真数据 | ✅ |
| T4 | P2 | V1/V2 双实现归一 → V2 唯一内核，V1 归档 `un_use/manager_v1.py`，`manager.py` 改门面，registry 指向 V2 | ✅ |
| T5 | P2 | 阈值硬编码 → `DEFAULT_TOPIC_TREE_CONFIG` 全参数化（A18 入口），分类器/分叉定位器/意图映射可配 | ✅ |
| T6 | P2 | `ACTIVATION_THRESHOLD=10` 延迟激活 → 默认 `auto_activate=True` 首轮建树，阈值保留为外部策略 | ✅ |
| T7 | P3 | hash/BGE 向量混用 → 编码器契约（`register_encoder`/`current_encoder`/`supports_semantics`）+ 节点标记 + 跨空间语义置 0 | ✅ |

**测试**: 主题树 40/40（原 17 + 新增 23）；上下文 46/46；CLI 28/28；
综合回归 266 passed（含画像/行为链/意图/对话树/状态机/causal/主题树/上下文）。

---

## 二、逐项明细

### T1 EmbeddingEngine 健壮性（P1）
```
根因: _load_model 只 catch ImportError；当前环境 sentence-transformers →
  huggingface_hub 导入链抛 ValueError（numpy 版本元数据损坏）→ route() 崩溃。
修复: _load_model catch Exception → None → encode 回退 hash（384-dim 确定性伪向量）。
验证: 原 10 failed / 7 passed → 17/17 全绿；新增模拟坏导入链测试 2 项。
```

### T2/T3 两个 API 断点（P1）
```
T2: assembly/context_assembly.py:145 调 get_current_branch（V2 无此方法）→ 恒空。
  修复: V2 新增 get_current_branch()（root→current 活跃路径）；消费方改为
  [n.to_dict() for n in branch]（真数据、可序列化）。
T3: engineering_bridges.TopicTreeBridge 调 get_active_path（V2 无）→ 恒 []。
  修复: V2 新增 get_active_path()（别名）；TopicTreeBridge.get_summary 由恒 {}
  改为 V2 get_tree_summary() 真数据。
验证: ContextAssembly._gather_sources 产出 topic_tree 分支；TopicTreeBridge
  get_current_branch 返回真实节点；对应测试 3 项。
```

### T4 V1/V2 归一（P2）
```
决策（对齐"一内核多门面"）:
  V2（manager_v2.TopicTreeManagerV2）= 唯一话题树内核。
  V1（manager.py 包装类）零真实消费方（engine._topic_tree 从未赋值；
    integration_bridge 期望的 route/get_node API 本就不在 V1 → 路径早已断链）。
施工:
  - manager.py → 薄门面（re-export V2；旧名兼容 registry/integration_bridge/inspect）
  - V1 原始代码归档 core/agent/topic_tree/un_use/manager_v1.py（A17 记录不删）
  - __init__.py 导出 V2 为主（TopicTreeManager 门面 / TopicTreeManagerV2 内核 /
    EmbeddingEngine / RoutingDecisionV2 + 组件资产）
  - cli/registry.py + subsystem_registrations.py: "topic_tree" 注册串 → manager_v2
  - context/topic_tree_source.py: 从 V1 不存在 API（current_topic_id/tree.nodes）
    改写为 V2 公开 API（get_current_node/get_active_path/get_node）→ 真数据
组件资产保留原位（供后续接线）: heat_model（A15 温度）/ fact_store / context。
验证: 门面 is 断言 2 项 + registry 串断言 + 归档存在性 + 组件资产导出。
```

### T5 阈值参数化（P2，A18）
```
新增 DEFAULT_TOPIC_TREE_CONFIG（默认值 = 原硬编码）:
  cohesion_continue 0.55 / cohesion_fork 0.25 / max_depth 6 /
  hot_zone_depth 2 / activation_threshold 10 / auto_activate True /
  cohesion_weights {0.4,0.35,0.25} / intent_related / classifier_weights /
  classifier_thresholds / intent_drift_threshold 0.3 / merge_similarity 0.85 /
  attach_score_floor 0.25 / fork_similarity_threshold 0.4 / fork_intent_drift 0.5
组件级:
  - TopicDecisionClassifier: intent_drift_threshold / merge_similarity /
    attach_score_floor / attach_sim·recency 权重（原 0.3/0.85/0.25/0.7/0.3 硬编码）
  - CohesionCalculator: intent_related 实例级映射表（原 3 对硬编码）
  - ForkPointLocator: 接收 calculator 注入（配置统一源）+ 既有阈值参数保留
  - TopicTreeManagerV2.__init__(config=None) 全量下发
验证: 默认值一致性 / config 覆盖 / 分类器独立参数 / 意图映射替换 4 项测试。
```

### T6 激活策略（P2）
```
原行为: route() 未激活 → 静默返回 continue（前 10 轮不建树）。
拍板: 默认 auto_activate=True → 首轮 route 即建树（discourse_manager 显式
  activate 不受影响）；auto_activate=False 时保留"延迟激活"语义；
  activation_threshold 保留为 should_activate 外部策略入口。
验证: 自动激活建树 / 关闭后不建树 / should_activate 阈值 2 项测试。
```

### T7 编码器契约（P3）
```
问题: hash 伪向量（384-dim，无语义信号，跨文本相似度基线 0.9+ 噪声）与
  BGE（512-dim）混用 → 跨空间比较无意义（实测 len 不等已被 0.0 守卫，
  但同维不同空间仍可能误判）。
契约:
  - EmbeddingEngine.register_encoder(name, fn)：官方注册入口（BGE 用）
  - current_encoder() / supports_semantics() / reset()
  - V2 _create_node 写 metadata.embedding_encoder + embedding_dim
  - CohesionCalculator.calculate：目标节点编码器 ≠ 当前 → 语义贡献置 0
    （实体/意图仍参与）
消费方: discourse_manager BGE 补丁改 register_encoder("bge", fn)，失败返回
  None 由引擎统一回退 hash 并正确标记身份。
验证: 注册契约 / hash 非语义 / 节点标记 / 跨空间置 0 / 同空间正常 5 项测试。
```

---

## 三、改动文件清单（未提交，按惯例压缩前不提交）

```
core/agent/topic_tree/manager_v2.py              T1/T2/T3/T5/T6/T7 核心（+259 行）
core/agent/topic_tree/manager.py                 门面（V1 代码 → un_use）
core/agent/topic_tree/__init__.py                V2 主导出 + 组件资产
core/agent/topic_tree/un_use/manager_v1.py       归档（A17 保留）
core/agent/topic_tree/tests/test_topic_tree_batch.py  新增 23 项
core/agent/context/topic_tree_source.py          T2/T4 改写为 V2 API
core/agent/context_manager/discourse_manager.py  T7 register_encoder + 失败返回 None
core/agent/assembly/context_assembly.py          T2 分支序列化
core/agent/engineering_bridges.py                T3 get_summary 真数据
core/agent/cli/registry.py                       T4 注册串 → manager_v2
core/agent/cli/subsystem_registrations.py        T4 注册串 → manager_v2
```

---

## 四、遗留记录（记录不施工，边界纪律）

| # | 内容 | 归属 |
|---|---|---|
| L1 | `TopicTreeBridge.get_summary(level)` 仍为 V2 `get_tree_summary()` 简化映射（level 语义未实现） | 工程链后续 |
| L2 | `compass_patch.py`（三范式指南针补丁）无调用方，`ThreeParadigmContext` 接线未做 | 蓝图/PCR 后续 |
| L3 | `integration_bridge` 的 `save_to_graph_store/load_from_graph_store` 在 V1/V2 均不存在（早已断链）；门面切 V2 后 route/get_node 已通，持久化缺 2 方法 | 持久化批次（G10） |
| L4 | `TopicTreeContextSource` 已修复为 V2 API，但 engine 仍未挂载（`_topic_tree_source=None` 幻影） | 上下文/执行批次 |
| L5 | e2e `test_e2e_full_pipeline_mock` 预存在失败：engine 重构（4a85ae8）后 `_persist_state` 消失，`PersistenceSubscriber` 恒不触发（persistence=0）；与本批无关 | event/持久化批次 |
| L6 | `test_dpo_learner` 2 项在综合套件中 flaky（pytest-asyncio 事件循环顺序依赖，单独跑全绿） | 测试基建 |
| L7 | `engine._topic_tree`（V1 touch 路径）从未赋值 = 幻影；V2 已由 discourse_manager 消费，无需补 | — |

---

## 五、验证命令

```
python -m pytest core/agent/topic_tree/tests -q --tb=short --import-mode=importlib
  -p no:cacheprovider -p no:faulthandler        # 40/40
python -m pytest core/agent/context/tests -q ...  # 46/46
python -m pytest core/agent/cli/tests -q ...       # 28/28
综合回归（画像/行为链/意图/对话树/状态机/causal/主题树/上下文）: 266 passed
（3 failed = L5 e2e 预存在 + L6 DPO flaky 顺序依赖，均非本批回归）
```
