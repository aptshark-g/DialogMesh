# 未对应设计文档批量精读 · 批 7 — v3.3 行为子组件

> 日期: 2026-08-03 | 批次: 7/8 | 状态: 已读完（4 文档）
> 共同背景: 全部对应 `DESIGN_V3_3_ALGORITHM.md`（v3.3 算法总纲），工程状态均"待实现"，
> 属于行为链 v3.3 算法的子组件工程规范（与行为链审计的 predictor/rewarder 直接相关）。

---

## 1. ENGINEERING_V3_3_FOA.md（113 行）— FoA 注意力焦点（S9）

**原则**: FoA 只做注意力选择，不做推理。返回 3-5 个最相关节点供 LLM 上下文窗口使用。
前置算法: ACT-R 双权重激活传播。

**数据模型**: AttentionNode（node_id/activation/base_activation/distance_from_seed）+
FocusResult（seed_nodes/activated/subgraph_edges/decay_used/fallback_used，top_k 排序）。
覆盖 ACT-R 激活传播、种子选择、阈值裁剪、降级策略。

**冲突登记（暂不裁决）**: 与批 1 COGNITIVE_WORKSPACE 的 attention_distribution /
Observability 注意力——FoA 是注意力选择的算法实现，与"Observer.attention"概念重叠 →
注意力机制归一待统一。

---

## 2. ENGINEERING_V3_3_FUSION.md（1521 行单行文档）— 融合器（S6）

**原则**: 融合器不做新推理，只做已有结果的合并与冲突仲裁。四轨返回时间差一个数量级
（Track-0 算法/10ms + Track-1 LLM/150ms + Track-P 预测/80ms + Causal 因果/<1ms），
分批融合是核心。

**架构**:
```
StageManager: Stage1(10ms, Track-0+Causal→硬事实) → Stage2(+80ms, +Track-P→预加载)
              → Stage3(+150ms, +Track-1→最终)；超时跳过降级
ConflictResolver: 五级优先级 STRUCTURAL(CAUSAL) > FACTUAL(TRACK_0) > SEMANTIC(TRACK_1)
                  > STRATEGIC > PREDICTIVE(TRACK_P)；主动矛盾消解
                  （INTENT_ACTION_MISMATCH→confidence_reduction=0.2 /
                   ENTITY_PREDICTION_MISMATCH→needs_clarification /
                   CONFIDENCE_DIVERGENCE→conservative_mode）
GlobalWorkspace: 有状态轨道竞争——连续压制>3 次优先级+1，防单轨垄断
```

**降级链**: Stage1 超时→纯 LLM 决策；Stage2 超时→Stage1 为最终；Stage3 超时→Stage2；
全超时→ask_clarification；全轨 confidence<0.5→ask_clarification。

**测试策略**: 4 P0 单测（stage_manager/conflict_resolver/global_workspace/fusion_engine）+
9 集成场景。文件规划: core/agent/v3_2/fusion/（models/stage_manager/conflict_resolver/
global_workspace/fusion_engine）。

**冲突登记（暂不裁决）**:
- 与 orchestrator/fusion_engine.py（14.2KB 已实现）+ tiered/fusion.py（消费）: 本文档是
  三阶段融合设计源，现实现为简化版 → 差距=三阶段时序/五级优先级/GlobalWorkspace 是否落地。
- 与批 1 COGNITIVE_SCHEDULER: 融合器是"结果合并"，调度器是"任务调度"——两层的接口
  （谁先谁后）待统一。
- 与执行层双决策器（GlobalDecider vs DeciderStateMachine）: 融合器+全局工作空间是第三套
  "决策仲裁"候选 → 三套归一待哲学统一（批 1 B1-2 同源）。

---

## 3. ENGINEERING_V3_3_L1SUMMARY.md（164 行）— L1 摘要（S10）

**原则**: 行为和因果信息在 meta_info 中零丢失，LLM 压缩的 core_semantics 只用于检索。

**数据模型**: L1SummaryEntry（turn_id/strategy: deterministic|template|llm/core_semantics/
meta_info/raw_text——仅 deterministic 保留原文）+ L1MetaInfo（prev_action/current_action/
predicted_next/causal_events/associations/is_topic_switch/user_satisfaction/
correction_detected/topic_id）+ ContentCategory（DETERMINISTIC 工具输出/代码等）。

**三级自适应摘要**: deterministic（工具输出保留原文）→ template → llm（只压缩 core_
semantics 供检索，meta_info 不丢）；异步存储 + L2 重新聚合触发。

**冲突登记（暂不裁决）**: 与对话树渐进摘要（discourse_block_tree summary_engine v1-v4）
——两套摘要体系（行为链 L1 vs 对话树摘要）→ 摘要归一待统一。

---

## 4. ENGINEERING_V3_3_NEGATIVE_KB.md（181 行）— 负知识库（S8）

**原则**: HARD_BLOCK 不靠人工标注，必须由 do-calculus 验证或形式化证明。

**边界**: 输入=用户意图+当前上下文（非原始输入）；输出=BLOCK/WARN/ALLOW 决策；触发=规则
预先注册 + do-calculus 验证；在线学习只在熔断后记录。

**架构**: NegativeLevel（HARD_BLOCK/WARN/ALLOW）+ ContextualNegativeRule + NegativeResult；
RuleStore（规则注册/查询/验证）+ FuseController（三次熔断）+ NegativeKB 入口。
文件规划: core/agent/v3_2/negative_kb/。

**三级分类 + 三次熔断 + 上下文开关 + 规则冲突仲裁**。

**冲突登记（暂不裁决）**:
- 与工程链约束（ConstraintTree/permissions/sandbox 审计 X11 约束空转）: 负知识库是
  约束的另一种实现（BLOCK/WARN/ALLOW vs add_rule/check）→ 约束体系归一待统一。
- 与 do_calculus（关联链 D1-D5 已覆盖）: HARD_BLOCK 需 do-calculus 验证——与关联链
  因果基板的关系待统一。

---

## 批 7 汇总（冲突登记清单）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B7-1 | FoA 注意力 vs Observer.attention（两套注意力）| 批 7 vs 批 1 |
| B7-2 | 三阶段融合 vs orchestrator/fusion_engine 简化实现 | 批 7 vs orchestrator 盘点 |
| B7-3 | 融合器+GlobalWorkspace = 第三套决策仲裁（vs 双决策器）| 批 7 vs 执行层 X 系列 + B1-2 |
| B7-4 | 行为链 L1 摘要 vs 对话树渐进摘要 | 批 7 vs 对话树审计 |
| B7-5 | 负知识库 vs ConstraintTree 约束体系 | 批 7 vs 工程链/执行层 X11 |
| B7-6 | HARD_BLOCK 需 do-calculus vs 关联链因果基板 | 批 7 vs 关联链 D 系列 |

