# Profile — 接入后差距

> 2026-07-21（初版声明"全部修复 ~95%"）
> **2026-08-03 修正（画像审计实锤）**：原声明与代码不符，有效实现率约 **30-40%**。
> 依据：`docs/only/profile/IMPLEMENTATION_AUDIT_20260803.md`——TrackA EMA / TagLayer
> infer_from_trace / ConvergenceEngine.update 三处**全库无调用方**；OCEAN 是逐轮 analyze
> 而非文档说的"每 10 轮 update"；`_cognitive_profile`（CognitiveProfileV2）生产路径
> 从未实例化。修正见 `docs/only/PENDING_DECISIONS_20260803.md` R5（画像四层合一）。
> **2026-08-04 施工后复核**（画像批次 P2-P12）：
>   P2 复活 —— `_feed_profile_runtime`（DynamicsComputer + ConvergenceEngine +
>   TagAcquisitionEngine）已从 PROFILE 阶段 handler 逐轮接线（handlers.py
>   handle_profile）；PCR→TrackA EMA（`_update_profile_from_pcr`）已从 PCR 阶段
>   接线；P7 inertia 喂数据（`_feed_inertia_evidence`）已从 on_event_sm 管线后
>   接线；P8 ProfileContextSource 已从 engine `_init_profile_runtime` 注册。
>   有效实现率按"四层合一"（R5）重估：事实层 FactStore ✅ / 人格投影层 OCEAN
>   ✅（CLI 路径逐轮 + save 挂载 + BFI 校准方法）/ 认知状态层 ✅（Track A 复活）/
>   行为模式层 inertia ✅（已喂证据，证据源为 P7 多视角）。测试见
>   `docs/only/profile/PROFILE_IMPL_PROGRESS_20260804.md`。

## 修复清单

| # | 问题 | 修复 |
|---|------|------|
| 1 | PCR→TrackA EMA | `alpha·fast + (1-alpha)·slow` (cognitive_level, expertise_level, preferred_detail) |
| 2 | LLM metrics→trust | `success→+0.02, fail→-0.05` |
| 3 | TrackB infer_from_trace | `TagLayer.infer_from_trace()` 每5轮执行 |
| 4 | OCEAN 映射 | `ocean_analyst.update()` 每10轮执行 |
| 5 | ConvergenceEngine | `update(track_a)` 每3轮执行 |

## 有效实现率

```
ExecutionTraceV3       ✅（已有）
TrackA EMA (3维度)     ✅（2026-08-04: `_feed_profile_runtime` + `_update_profile_from_pcr`
                       从 handlers PCR/PROFILE 阶段接线；ConvergenceEngine EMA）
LLM trust feedback     ✅（Track A trust_score 由 `_feed_profile_runtime` 每轮喂入；
                       L3 LLM deadlock 走 association_funnel）
TrackB TagLayer        ✅（`_feed_profile_runtime` 内 TagAcquisitionEngine L1/L2 每轮）
OCEAN mapping          ✅（CLI 路径逐轮 analyze + P11 save 落盘 + update_dimension 白盒）
ConvergenceEngine      ✅（`_init_profile_runtime` 实例化，`_feed_profile_runtime` 调用）
────────────────────────────
有效实现率: 按 R5 四层合一直观重估 ~80-90%（2026-08-04 施工后；
其余偏差见 PROFILE_IMPL_PROGRESS 遗留节）
```

## Context — 确认无遗漏

```
DomainSelector · PerspectivePlanner · ContextAssembler
BudgetAllocator · SubgraphCompiler · DiscourseBlockTree
TopicTree · to_prompt budget过滤
ContextCompressor · Pruner · LOGICAL_LEAP→Subgraph · TTL decay
────────────────────────────
❌ 12/12 声明未验证（审计未逐项复核 Context 清单；接线以 IMPLEMENTATION_AUDIT 为准）
```
