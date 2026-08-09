# 画像批次施工记录 — P2-P12 + H1-H6（2026-08-04）

> 依据：`PENDING_DECISIONS_20260803.md` §二（P1-P12）+ R5（四层合一）+ H1-H6
> （EXTERNAL_REFERENCE 吸收）。审计资产：`profile/AUDIT_ENTRY` /
> `IMPLEMENTATION_AUDIT` / `DESIGN_AUDIT` / `EXTERNAL_REFERENCE`。
> 状态：**画像批次完成**。画像三套体系 → R5 四层合一，接线全部打通。

---

## 一、施工内容（按 P 项）

| # | 项 | 施工 | 验证 |
|---|---|---|---|
| P1 | 本体归一（四层合一）| R5 拍板；事实层 FactStore（前批已建，PE-3 批量写已修）| test_fact_store + stress ✅ |
| P2 | _cognitive_profile 复活 | `_feed_profile_runtime` 从**零调用** → PROFILE 阶段 handler 逐轮接线（DynamicsComputer 9 维 + ConvergenceEngine EMA + TagAcquisitionEngine L1/L2）| test_profile_wiring TestP2 ✅ |
| P3 | PROFILE_GAP 修正 | `docs/v5/PROFILE_GAP.md` 更新：30-40% → 施工后 ~80-90%（四层合一直观重估）| 文档 ✅ |
| P4 | L3 profile 视角接线 | **已存在**（engine `_l3_profile_traits()` → validate profile_traits），补测试固化 | TestP4 ✅ |
| P5 | 对话树组块边界 ← 认知状态 | engine `cognitive_state()` accessor + B manager `feed/ingest_turn` 接受 `cognitive_hints`（get_stats 白盒暴露）| TestP5 + 端到端 ✅ |
| P6 | P4 双向先验 | PCR→TrackA：`_update_profile_from_pcr`（zone/level/xyz → cognitive_resource/expectation_deviation/attention_anchor EMA）；画像→PCR：`_profile_prior_text` → `pcr.route(subgraph_prior=...)` | TestP6 + 端到端（0.529 EMA）✅ |
| P7 | inertia_graph 喂数据 | `_feed_inertia_evidence`：on_event_sm 管线后从 behavior/meta/profile/association 阶段结果喂 evidence（多视角共识）| TestP7 + 端到端（quality_centric pattern）✅ |
| P8 | ContextCompiler P 域 | `ProfileContextSource` 从**零引用** → engine `_init_profile_runtime` 绑定 CognitiveProfileV2 + ConvergenceEngine；handle_context 注入 P 域 IR | TestP8 + 端到端 ✅ |
| P9 | v2 双轨 11 模块去留 | 死代码归档：`llm_profile_analyst.py` + `signal_filter.py` → `v4/un_use/`（活跃代码 0 引用）；tag_layer/dynamics/convergence/fusion 保留（P2 已吸收）| 全库 rg 复核 ✅ |
| P10 | g 因子领域化 | `build_tag(domain=)` + `assess_g_factor(domain=)` → `track_b["g_factor:<domain>"]`（general 保留兼容旧键）| TestP10 ✅ |
| P11 | CLI 死命令 + 双名注册 | OCEANProfileAnalyst 补 `update_dimension/snapshot/history/reset/save` 门面；`OCEANProfile.save` 补 `import os`（原 NameError）；p10_cmd `cmd_profile_analyze` 签名对齐（会话历史重放）；subsystem_registrations `ocean_analyst` → OCEANProfileAnalyst（双名归一）| TestP11 + compile ✅ |
| P12 | 画像测试 | 新增 `profile/tests/test_profile_wiring.py` 19 项（P2/P4/P5/P6/P7/P8/P10/P11/H2）| 19/19 ✅ |
| H1/H5 | FactStore（事实层 + 注入扫描/快照冻结/防循环）| 前批已建，本批复核 | ✅ |
| H2 | declarative-facts 写入规范 | `FactStore.WRITE_GUIDANCE` 常量（声明式事实/减少 steering/7 天时效/who-vs-how）| TestH2 ✅ |
| H3 | background_review 后验 | 设计吸收记录（fork-agent 模式，未来接元认知周期扫描；本批不施工——边界纪律）| 文档 ✅ |
| H4 | consent-gated 冷启动 | 设计吸收记录（Hermes onboarding 模式，冷启动阶段实施）| 文档 ✅ |
| H6 | who-vs-how 分工 | R5 已拍板：事实层=who，行为链/技能=how | 文档 ✅ |

---

## 二、改动文件清单

```
M core/agent/runtime/engine.py          P2/P5/P6/P7/P8 方法层 + __init__ 懒挂载
M core/agent/event/handlers.py          P2/P5/P6/P8 handler 接线（PCR/DISCOURSE/PROFILE/CONTEXT）
M core/agent/discourse_block_tree/manager.py  P5 cognitive_hints 参数 + get_stats 白盒
M core/agent/v4/cognitive/ocean_profile.py    P11 门面方法 + import os 修复
M core/agent/v4/cognitive/tag_layer.py        P10 g 因子 domain 参数
M core/agent/cli/subsystem_registrations.py   P11 双名注册归一（OCEANProfile → OCEANProfileAnalyst）
M core/agent/cli/commands/p10_cmd.py          P11 cmd_profile_analyze 签名对齐
M core/agent/profile/fact_store.py            H2 WRITE_GUIDANCE
A core/agent/profile/tests/test_profile_wiring.py  P12 19 项
M docs/v5/PROFILE_GAP.md                P3 修正
M core/agent/v4/un_use/                  P9 归档（llm_profile_analyst + signal_filter）
```

---

## 三、验证数字

```
画像批次新增测试:       profile/tests/test_profile_wiring.py 19/19
画像既有回归:           v4 cognitive + fact_store + fact_store_stress + inertia 39/39
跨模块回归:             statemachine + discourse 系列 + intent + CLI + viz_edit 116/116
                       intent + kernel + MCP + statemachine 104/104
端到端冒烟（on_event_sm 全管线）:
  track_a observation_count=11（P2 每轮喂入）
  profile_source=ProfileContextSource（P8 绑定）
  inertia patterns=['quality_centric']（P7 多视角证据）
  discourse cognitive_hints.available=True（P5）
  track_a.cognitive_resource=0.529（P6 PCR→TrackA EMA）
  PCR route(subgraph_prior=...) 无 TypeError（P6 画像→PCR）
```

---

## 四、遗留（记录不施工，边界纪律）

1. `predictor/profile_matcher.py`（ProfileMatcher）与 EnhancedProfileMatcher 重复，
   唯一引用在 `v3_2/un_use/`（归档区）→ 本批不动（跨归档区引用链）。
2. `TagLayerManager` 内 `GFactorInferencer` 类引用为**既有断链**（tag_layer 无该类，
   `build_tag/assess_from_history` 实为 TagAcquisitionEngine 方法）——P10 已按
   TagAcquisitionEngine 修正；TagLayerManager.set_llm/assess_g_factor 仍引用
   不存在的 GFactorInferencer（审计前即存在，属于 v2 双轨纸面残留）。
3. H3 background_review / H4 consent-gated 冷启动：设计吸收，施工归冷启动/
   元认知批次（fork-agent 模式较重，不混入本批）。
4. `association_funnel.run_layers` 的 L3 validate 仍不传 profile_traits（只传
   pcr_zone/entity_relations）——引擎冷路径 `_run_association_chain` 已传；
   funnel 侧接线归关联链批次（避免跨模块越界）。

---

*本文件是画像批次施工记录；交接入口见 `STATE_HANDOFF_IMPLEMENTATION_20260804.md`。*
