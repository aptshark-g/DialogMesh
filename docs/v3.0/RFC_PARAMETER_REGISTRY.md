# RFC-000: ParameterRegistry — 全系统参数统一管理（完整版）

> 覆盖 DialogMesh v3.0 + v3.2 + v4 所有浮动参数。共 50+ 参数，分布在 22 个模块中。
> 每个参数绑定独立的 reward_signal，全局策略一键切换。

> 版本: v2.0 | 日期: 2026-07-10

---

## 目录

1. 设计动机
2. 参数全景（v3.0 基础设施层）
3. 参数全景（v3.0 推理层）
4. 参数全景（v3.2 认知层）
5. 参数全景（v4 新模块）
6. AdaptiveParameter 统一接口
7. 全局策略切换
8. 参数自身热冷分层
9. 新增代码估计

## 1. 设计动机

全系统 50+ 参数散落在 22 个模块中，硬编码在各处。
ParameterRegistry 集中管理：统一锚点-区间-自适应范式、全局策略一键切换、审计轨迹。

## 2. 参数全景：v3.0 基础设施层

### 2.1 TopicTree（对话树）

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| topic_merge_coherence | 0.60 | [0.45, 0.75] | 0.01 | merge_reversal_rate: 合并后被重新拆分的比例 |
| topic_split_coherence | 0.30 | [0.20, 0.45] | 0.01 | split_stability: 拆分后保持独立的比例 |
| topic_decay | 1.0 | [0.5, 2.0] | 0.1 | topic_revisit_rate: 已衰减话题被重新访问的频率 |
| boundary_threshold | 0.55 | [0.40, 0.70] | 0.01 | boundary_recall: 人工标记的边界被检测到的比例 |
| fork_depth_limit | 10 | [5, 20] | 1 | tree_balance: 树的深度/广度比 |

### 2.2 LLM Providers（故障转移与熔断）

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| circuit_breaker_error_rate | 0.50 | [0.30, 0.70] | 0.05 | false_trip_rate: 误熔断比例 |
| circuit_breaker_warning_rate | 0.30 | [0.15, 0.50] | 0.05 | detection_lag: 实际故障到触发的时间差 |
| circuit_breaker_recovery_rate | 0.10 | [0.05, 0.25] | 0.02 | recovery_success_rate: 恢复请求的成功比例 |
| failover_threshold | 0.50 | [0.30, 0.70] | 0.05 | failover_latency_p50: 切换延迟中位数 |

### 2.3 安全层

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| sanitizer_critical_threshold | 0.50 | [0.30, 0.70] | 0.05 | false_positive_rate |
| sanitizer_medium_threshold | 0.30 | [0.15, 0.50] | 0.05 | detection_escape_rate |
| sanitizer_low_threshold | 0.10 | [0.05, 0.25] | 0.02 | noise_level |
| intent_confidence_threshold | 0.20 | [0.10, 0.35] | 0.02 | intent_classification_accuracy |
| gate_decision_threshold | 0.20 | [0.10, 0.35] | 0.02 | gate_bypass_rate: 被绕过频率 |

### 2.4 可观测性

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| alert_warning_threshold | 0.20 | [0.10, 0.35] | 0.02 | alert_fatigue_rate: 忽略警告频率 |
| alert_critical_threshold | 0.10 | [0.05, 0.20] | 0.01 | missing_alert_rate |

## 3. 参数全景：v3.0 推理与编排层

### 3.1 Orchestrator / Algorithm Engine

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| fusion_alpha (认知) | 0.50 | [0.30, 0.70] | 0.05 | fusion_coverage: 融合结果覆盖原始意图的比例 |
| fusion_beta (行为) | 0.30 | [0.15, 0.50] | 0.05 | behavior_integration_rate: 行为数据被使用的频率 |
| fusion_gamma (环境) | 0.20 | [0.10, 0.40] | 0.05 | context_relevance: 环境信息准确的评分 |

### 3.2 Tool Registry

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| tool_shortlist_alpha | 0.30 | [0.15, 0.50] | 0.05 | tool_hit_rate: 短列表包含最终使用的工具比例 |

### 3.3 Gates / PCR

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| gate_alpha | 0.30 | [0.15, 0.50] | 0.05 | gate_decision_accuracy |
| pcr_alpha (语义) | 0.25 | [0.10, 0.40] | 0.03 | pcr_match_accuracy |
| pcr_beta (结构) | 0.20 | [0.08, 0.35] | 0.03 | structural_match_accuracy |

### 3.4 Onboarding

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| onboarding_skill_threshold | 0.60 | [0.40, 0.75] | 0.03 | skill_activation_accuracy |
| onboarding_intent_threshold | 0.40 | [0.25, 0.60] | 0.03 | intent_misclassify_rate |
| onboarding_confidence_threshold | 0.65 | [0.50, 0.80] | 0.03 | profile_confidence_stability |

## 4. 参数全景：v3.2 认知层

### 4.1 约束编译器

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| compiler_confidence_threshold | 0.75 | [0.65, 0.85] | 0.02 | llm_vs_rule_win_rate: LLM与规则胜率比(Bradley-Terry) |
| compiler_cosine_threshold | 0.60 | [0.50, 0.70] | 0.01 | semantic_match_accuracy |

### 4.2 BehaviorGraph（行为图）

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| bg_alpha (LLM因果) | 0.25 | [0.15, 0.35] | 0.02 | edge_stability: 边权重波动幅度 |
| bg_beta (频率统计) | 0.30 | [0.20, 0.40] | 0.02 | pattern_recall: 行为模式召回率 |
| bg_gamma (画像匹配) | 0.05 | [0.03, 0.15] | 0.01 | profile_correlation: 与画像的一致性 |
| bg_delta (结构先验) | 0.05 | [0.01, 0.15] | 0.01 | structural_consistency: 结构一致性 |
| bg_cold_start_interval | 50 | [20, 100] | 10 | cold_start_coverage: 冷启动覆盖范围 |
| bg_cold_start_threshold | 10 | [5, 25] | 3 | cold_start_noise: 误预热的比例 |
| bg_fast_correction_threshold | 2 | [1, 5] | 1 | correction_false_positive: 误判纠正比例 |

### 4.3 Predictor / Rewarder

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| predictor_weight_interval | [0.25,0.55] | — | — | prediction_hit_rate: 每10轮命中率 |
| rewarder_time_decay_days | 30 | [14, 60] | 5 | reward_signal_stability |
| correction_explicit_high_conf | 0.90 | [0.80, 0.95] | 0.01 | explicit_correction_accuracy |
| correction_rollback_conf | 0.70 | [0.55, 0.85] | 0.02 | rollback_pattern_precision |
| correction_consecutive_fail_conf | 0.80 | [0.70, 0.92] | 0.02 | failure_detection_lag |
| rewarder_adaptive_interval | 100 | [50, 200] | 25 | reward_value_stability |

### 4.4 FoA / do-calculus / CausalSubstrate

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| foa_decay (ACT-R) | 0.30 | [0.20, 0.50] | 0.02 | attention_focus_stability |
| foa_activation_threshold | 0.30 | [0.15, 0.50] | 0.02 | activation_signal_noise_ratio |
| do_calculus_backdoor_threshold | 0.95 | [0.90, 0.99] | 0.01 | false_causal_claim_rate |
| causal_structural_prior_interval | [0.05,0.25] | — | — | causal_validation_rate: 因果边被后续验证的比例 |

### 4.5 嵌入层 / 语义层

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| embedding_behavior_threshold | 0.30 | [0.15, 0.50] | 0.02 | embedding_classification_accuracy |
| embedding_index_threshold | 0.20 | [0.10, 0.35] | 0.02 | index_query_hit_rate |

### 4.6 合并 / 持久化 / 元认知

| 参数 | 锚点 | 区间 | 步长 | Reward Signal |
|:---|:---|:---|:---|:---|
| consolidation_merge_threshold | 15 | [8, 30] | 3 | merge_conflict_rate: 合并后冲突比例 |
| consolidation_delta | 0.00 | [-0.05, 0.05] | 0.01 | merge_satisfaction: 合并后人工满意度 |
| persistence_save_interval_sec | 60 | [30, 120] | 10 | data_loss_risk: 未持久化数据量 |
| metacognition_token_threshold | 10000 | [5000, 20000] | 1000 | meta_insight_density: 每触发产生的有价值的洞察数 |
| negative_kb_threshold | 0.50 | [0.30, 0.70] | 0.05 | negative_kb_precision: 负知识库准确率 |

## 5. 参数全景：v4 新模块（已定义，摘要列出）

| 模块 | 参数 | 锚点 | 区间 |
|:---|:---|:---|:---|
| Hypothesis Pool | promotion_threshold | 0.85 | [0.75, 0.92] |
| | demotion_threshold | 0.40 | [0.30, 0.55] |
| | decay_rate | 0.95 | [0.90, 0.98] |
| Belief Update | evidence_weight | 0.08 | [0.03, 0.15] |
| | counter_penalty | 0.12 | [0.05, 0.20] |
| | hot_cooling_hours | 24 | [6, 72] |
| | warm_cooling_days | 30 | [14, 90] |
| | cold_archive_months | 6 | [3, 12] |
| Refinement | hot_interval_sec | 5 | [1, 30] |
| | warm_interval_min | 10 | [5, 60] |
| | cold_interval_hours | 24 | [6, 72] |
| | max_concurrent | 4 | [1, 8] |
| Skill Layer | distillation_min | 5 | [3, 15] |
| | draft_to_verified | 0.90 | [0.80, 0.95] |
| | verified_to_core | 10 | [5, 30] |
| | deprecated_inactive | 6 | [3, 12] |
| Event IR | vocab_auto_approve | 20 | [10, 50] |
| | vocab_min_occurrences | 3 | [2, 10] |
| Obs Pool | retention_hot | 7 | [1, 30] |
| | retention_total | 365 | [90, 730] |
| ContextCompiler | budget_default | 500 | [300, 1000] |
| | primary_pct | 0.60 | [0.50, 0.75] |
| | auxiliary1_pct | 0.25 | [0.15, 0.35] |
| | auxiliary2_pct | 0.15 | [0.05, 0.25] |
| Subgraph Prune | candidate_percentile | 0.30 | [0.20, 0.50] |
| | betweenness_threshold | 0.60 | [0.40, 0.80] |
| | recency_rounds | 3 | [1, 5] |


## 6. AdaptiveParameter 统一接口

`
AdaptiveParameter {
  name: str              # 全局唯一参数名
  anchor: float          # 文献/经验锚点
  interval: [min, max]   # 安全区间
  step: float            # 单次调整步长
  current: float         # 当前生效值
  min_samples: int       # 最少采样数才触发调整
  reward_signal: fn      # 绑定信号函数 -> float
  last_adjusted: timestamp
  cooldown_sec: int      # 冷却期（防震荡）
  tier: hot|warm|cold   # 参数自身热冷分层
}
`

更新逻辑：samples>=min_samples and cooldown passed -> 信号改善则+step，恶化则-step，clamp到区间内。
每次调整写入 Event Log 作为审计轨迹。

## 7. 全局策略切换

| 策略 | 描述 | 效果 |
|:---|:---|:---|
| quality_first | 质量优先，不计算力 | 提高阈值(宽松)+高频精炼+大上下文预算 |
| balanced | 默认平衡 | 锚点默认值 |
| cost_first | 成本优先 | 降低阈值(严格)+低频精炼+小上下文预算 |
| provider_default | 按 Provider 自动选择 | DeepSeek->quality, OpenAI->balanced, Ollama->quality |

策略切换时，所有受影响参数线性过渡而非瞬时突变。

## 8. 参数自身热冷分层

| 参数层 | 包含哪些参数 | 更新频率 | 冷却期 |
|:---|:---|:---|:---|
| Hot | context_budget, analyzer_interval, circuit_breaker, alert_threshold | 实时 | 1min |
| Warm | compiler_confidence, bg_alpha/beta/gamma/delta, predictor_weights | 每小时 | 10min |
| Cold | bg_cold_start, consolidation, skill_distillation, vocab, do_calculus, foa_decay | 每天 | 1h |

## 9. 新增代码估计

| 组件 | 行数 |
|:---|:---|
| AdaptiveParameter 基类（已有 adaptive_threshold.py 可扩展） | ~80 行 |
| ParameterRegistry（注册+查询+审计） | ~120 行 |
| 各模块 reward_signal 函数（~30 个） | ~300 行 |
| 全局策略切换逻辑 | ~60 行 |
| **总计** | **~560 行** |

---

> 完整版 RFC: 50+ 参数，22 模块，v3.0/v3.2/v4 全覆盖。
> 每个参数绑独立 reward_signal，全局策略一键切换，参数自身热冷分层。
> 所有参数调整记录审计轨迹到 Event Log。

## 10. 代码定位表：每个参数在哪个文件的哪一行

### 10.1 TopicTree / DiscourseBlockTree

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| topic_merge_coherence | core/agent/topic_tree/manager.py | L40 | THRESHOLD = 0.6 |
| topic_split_coherence | core/agent/topic_tree/manager.py | L41 | THRESHOLD = 0.3 |
| topic_decay | core/agent/topic_tree/manager.py | L407 | decay = 1.0 |
| topic_decay | core/agent/topic_tree/manager_v2.py | L366 | decay = 1.0 |
| boundary_threshold | core/agent/topic_tree/manager_v2.py | L716 | THRESHOLD = 10 |
| boundary_threshold | core/agent/config/discourse_config.py | L359 | _threshold = 0.5 |
| boundary_threshold | core/agent/config/discourse_config.py | L383 | _threshold = 0.55 |
| fork_depth_limit | core/agent/discourse_block_tree/manager.py | L21 | _threshold = 0.5 |

### 10.2 LLM Providers

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| cb_error_rate | core/agent/v3_0/llm_providers/circuit_breaker.py | L337 | _threshold = 0.5 |
| cb_warning_rate | core/agent/v3_0/llm_providers/circuit_breaker.py | L364 | _threshold = 0.3 |
| cb_recovery_rate | core/agent/v3_0/llm_providers/circuit_breaker.py | L370 | _threshold = 0.1 |
| failover_threshold | core/agent/v3_0/llm_providers/failover_provider.py | L76 | _threshold = 0.5 |

### 10.3 安全层

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| sanitizer_medium | core/agent/security/input_sanitizer.py | L53 | THRESHOLD = 0.30 |
| sanitizer_critical | core/agent/security/input_sanitizer.py | L54 | THRESHOLD = 0.50 |
| sanitizer_low | core/agent/security/input_sanitizer.py | L55 | THRESHOLD = 0.10 |
| intent_confidence | core/agent/intent_parser.py | L450 | _threshold = .2 |
| gate_decision | core/agent/gates.py | L209 | _threshold = .2 |
| gate_alpha | core/agent/gates.py | L63 | alpha = 0.3 |

### 10.4 可观测性

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| alert_warning | core/agent/observability/alert.py | L212 | threshold = .2 |
| alert_critical | core/agent/v3_0/observability/alert.py | L212 | threshold = .2 |

### 10.5 推理编排层

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| fusion_alpha | core/agent/v3_0/orchestrator/algorithm_engine.py | L62 | alpha = 0.5 |
| fusion_beta | core/agent/v3_0/orchestrator/algorithm_engine.py | L62 | beta = 0.3 |
| fusion_gamma | core/agent/v3_0/orchestrator/algorithm_engine.py | L62 | gamma = 0.2 |
| tool_shortlist_alpha | core/agent/v3_0/tool_registry/models.py | L93 | alpha = 0.3 |
| pcr_alpha | core/agent/pcr/rule_based.py | L771 | alpha = 0.25 |
| pcr_beta | core/agent/pcr/rule_based.py | L778 | alpha = 0.20 |
| onboarding_skill_thresh | core/agent/onboarding/prompts.py | L76 | threshold = 0.6 |
| onboarding_intent_thresh | core/agent/onboarding/prompts.py | L77 | threshold = 0.4 |
| onboarding_confidence_thresh | core/agent/onboarding/prompts.py | L78 | _threshold = 0.65 |
| adapt_threshold | core/agent/adaptive_threshold.py | L415 | _threshold = 0.5 |
| adapt_decay | core/agent/adaptive_threshold.py | L583 | decay = 1.0 |
| coord_alpha | core/agent/coordinator/adaptive_threshold.py | L169 | alpha = 0.3 |

### 10.6 v3.2 认知层

| RFC参数 | 文件 | 行号 | 当前硬编码值 |
|:---|:---|:---|:---|
| compiler_confidence | core/agent/v3_2/compiler/rule_engine.py | L135 | THRESHOLD = 0.75 |
| bg_cold_start_interval | core/agent/v3_2/behavior_graph/cold_start.py | L8 | INTERVAL = 50 |
| bg_cold_start_threshold | core/agent/v3_2/behavior_graph/cold_start.py | L9 | THRESHOLD = 10 |
| bg_fast_correction | core/agent/v3_2/behavior_graph/fast_correction.py | L5 | THRESHOLD = 2 |
| rewarder_time_decay | core/agent/v3_2/rewarder/time_decay.py | L4 | DECAY = 30 |
| foa_decay | core/agent/v3_2/foa/actr_activator.py | L5 | DECAY = 0.3 |
| foa_activation | core/agent/v3_2/foa/actr_activator.py | L6 | THRESHOLD = 0.3 |
| do_calculus_backdoor | core/agent/v3_2/do_calculus/backdoor_criterion.py | L6 | THRESHOLD = 0.95 |
| embedding_behavior | core/agent/v3_2/embedding/behavior_embedding.py | L87 | threshold = .3 |
| embedding_index | core/agent/v3_2/embedding/index_builder.py | L15 | THRESHOLD = 0.20 |
| consolidation_merge | core/agent/v3_2/consolidation.py | L10 | THRESHOLD = 15 |
| consolidation_delta | core/agent/v3_2/consolidation.py | L23 | delta = 0.0 |
| metacognition_token | core/agent/v3_2/metacognition.py | L76 | THRESHOLD = 10000 |
| persistence_save | core/agent/v3_2/persistence.py | L8 | INTERVAL = 60 |
| negative_kb | core/agent/v3_2/knowledge/models.py | L39 | threshold = 0.5 |

### 10.7 v4 新模块（设计阶段，代码尚未生成）

| RFC参数 | 状态 |
|:---|:---|
| Hypothesis: promotion_threshold, demotion_threshold, decay_rate | 设计文档已定义，代码未生成 |
| Belief Update: evidence_weight, counter_penalty, hot/warm/cold cooling | 同上 |
| Refinement: hot/warm/cold intervals, max_concurrent | 同上 |
| Skill: distillation, lifecycle thresholds | 同上 |
| EventIR: vocab_auto_approve, vocab_min_occurrences | 同上 |
| ObsPool: retention_hot, retention_total | 同上 |
| ContextCompiler: budget, primary/auxiliary pct | 同上 |
| SubgraphPrune: candidate_percentile, betweenness, recency | 同上 |

---

> 第10节映射: 55个硬编码参数在25个文件中的精确位置。v4参数在代码生成时补充。
