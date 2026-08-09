# 第三批施工记录 — GAP-O1/O2/O3 + GAP-P1（2026-08-06）

> 依据: `COMPLETENESS_GAP_INVENTORY_20260806.md` §D/E（第三批）
> 状态: 四项全部完成并验证（全量 1782 passed / 0 failed / 16 skipped）

---

## 一、GAP-O1: memory/ 孤儿归档 ✅

**问题**: memory/ 六文件（ClusterMap/压缩路由/联邦索引/ragraph/XML 卡片/
策略联邦）全库生产零引用（仅包内自洽）, 概念与 L5 四区记忆 + 子图可视化
重叠但未接线（PE-1 拍"归档 or 接持久化层"）。

**处置**: 归档到 `un_use/memory_strategy_federation/`（A17 记录不删,
保留全部 6 文件）; cluster_map.py 内部引用改为 un_use 相对路径;
确认无测试/生产引用破坏。

## 二、GAP-O2: coordinator 判定修正 ✅（非缺陷）

**修正**: 第一轮探针只查 api/runtime/cli/blueprint 生产目录, 判定
coordinator 为"生产零引用孤儿"——**错误**。实测:
- `discourse_manager.py` 11 处消费（mode_router/small_model_client/
  adaptive_threshold/invoke_llm）
- `task_engine/task_detector.py` + `user_engine/*` 3 处消费

**结论**: coordinator 已真实接线（三级决策: 规则→本地小模型→远程大模型）。
它的问题仅是 PE-4 的另一半"multi_tier_llm_client 与 llm_providers 关系
未定义"——属两套 LLM 分层命名差异, 非功能缺陷, 记录不施工（P3 归一时处理）。

## 三、GAP-O3: PCR 模型统一（SemanticEncoder 优先）✅

**问题**: PCR 用 bge-small-zh-v1.5（sentence_transformers/fastembed 在线
加载）, SemanticEncoder 用 bge-small-zh（本地路径）——双模型并存,
冷启动多份内存 + fastembed 联网重试。

**修复**（`pcr_router_v2.py` `_load_mood_vectors`）:
- 新增 **Try 0: 复用 SemanticEncoder**（本地 bge-small-zh 就绪时优先,
  与上下文/子图共用单模型内存）; `_mood_source="semantic_encoder"`
- 无本地模型时静默回退现有链（nomic → sentence_transformers →
  fastembed → mirror）, **不新增失败路径**
- 语法修复（Try 1/Try 2 块缩进）

## 四、GAP-P1: 控制面板参数化 ✅

**问题**: DESIGN_DEEP_AUDIT §P2 — 深度/严格度/广度/决策模式从未接进
engine.build（"用户可理解的驾驭"零落地）。

**修复**:
- `BlueprintEngine.build(text, intent, strategy, strictness, depth,
  breadth, decision_mode)` — 全参数透传
- `ConstraintChecker.validate(dag, strictness)` — 严格度缩放上限:
  0.0 宽松→节点 12/深度 24; 0.5 默认→7/18; 1.0 严格→5/12
- `LLMDAGBuilder.diverge(text, intent, breadth)` — 发散路径数 2-6
- `decision_mode`: template|hybrid|llm|rule_based → 强制对应策略;
  auto → registry.match（默认）
- engine 构造器支持 default_strictness/depth/breadth（全局默认可配）

## 五、验证

- 新增 `blueprint/tests/test_control_panel.py` 6 项（strictness 缩放/
  build 参数/decision_mode 映射/breadth 透传/auto 模式）
- 相关套件: blueprint+pcr 364/364
- 全量 core/agent: **1782 passed / 0 failed / 16 skipped**（12:49）

## 六、改动文件

- 归档: memory/ 6 文件 → `un_use/memory_strategy_federation/`
- 修改: `pcr_router_v2.py`（SemanticEncoder 优先 + 缩进修复）/
  `blueprint/engine.py`（build 参数化 + strictness 缩放）/
  `blueprint/llm_dag_builder.py`（diverge breadth）/
  `un_use/memory_strategy_federation/cluster_map.py`（引用修正）
- 新增: `blueprint/tests/test_control_panel.py`

## 七、剩余

- 第四批: GAP-F1/F2（前端变更日志视图 + 139 文件绑定, 阶段 B）+ P2 项
  （GAP-3 工具批次介入 / GAP-4 压缩反馈 / GAP-5 taint / GAP-P2 自调节 /
  GAP-P3 热路径监视 / GAP-O4 world）

