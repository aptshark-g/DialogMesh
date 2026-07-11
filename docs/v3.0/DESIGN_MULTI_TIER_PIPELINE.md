# Multi-Tier Precision Pipeline：算力-精度的可编排谱系

> 不是快/慢二元。是多层递进——用可配置的算力预算换取递增的精度。
> 每层的输出作为下一层的种子输入，每层的修正回流到前面的层。

> 版本: v1.0 | 日期: 2026-07-11

---

## 目录

1. 为什么不是快慢二元
2. 核心概念：精度-算力谱系
3. Tier 定义
4. Pipeline 编排
5. 升级策略（UpgradePolicy）
6. 修正反馈闭环（FeedbackLoop）
7. 监控与调优
8. 全系统映射
9. 实现计划

## 1. 为什么不是快慢二元

快慢二元的局限：一些场景需要 3 个精度台阶（规则→统计→LLM），
一些场景只需要 2 个（快速匹配→精确匹配），还有一些可能在快慢之间需要一个中等精度的过渡层。

每个模块的精度-算力需求不同——不应该硬编码 2 层或 3 层。
应该是一个可配置的连续谱系。

| 谱系位置 | 算力 | 精度 | 示例 |
|:---|:---|:---|:---|
| L0: 零算力 | 0ms | ~70% | 缓存命中、预计算索引 |
| L1: 符号规则 | <5ms | ~85% | 词典匹配、正则、关键词 |
| L2: 统计模型 | ~30ms | ~92% | spaCy、Tree-sitter、embedding |
| L3: 小模型 | ~200ms | ~95% | 本地小 LLM (Ollama 3B) |
| L4: 大模型 | ~500ms | ~98% | 全量 LLM |
| L5: 人工 | 无限 | 100% | 人工审核/确认 |

## 2. 核心概念：精度-算力谱系

`
输入
  |
  v
Tier 0: 缓存/索引 (<1ms, ~70%)
  | confidence < threshold_0 -> Tier 1
  v
Tier 1: 符号规则 (<5ms, ~85%)
  | confidence < threshold_1 -> Tier 2
  v
Tier 2: 统计模型 (~30ms, ~92%)
  | confidence < threshold_2 -> Tier 3
  v
Tier 3: 小模型 (~200ms, ~95%)
  | confidence < threshold_3 -> Tier 4
  v
Tier N: 大模型 / 人工 (无限, ~99%+)
`

每个模块可以选择使用哪些 Tier。TieredParser 用 3 层（L1+L2+L4）。
Code Context Graph 用 3 层（L0+L2+L4）。NegativeKB 可能只需要 2 层（L1+L3）。

## 3. Tier 定义

每个 Tier 包含：
- level: 精度级别 0-5
- process: (input, context) -> result 的处理函数
- confidence_threshold: 低于此值升级到下一层
- time_budget_ms: 超时降级
- stats: 运行时统计(calls/pass_through/upgraded/corrections/avg_latency)

每个 Tier 输出 result 带 confidence。Pipeline 根据阈值决定是否升级。

## 4. Pipeline 编排

MultiTierPipeline:
  tiers: 从快到慢排列
  执行逻辑:
    for each tier:
      result = tier.process(input, context_with_prev_hints)
      if result.confidence >= tier.threshold: return result
      context.set(tier_hint, result)  # 下层收到上层的种子
    return last_result

关键：每层的 context 包含前面所有层的输出作为提示。下层不需要从零开始。

## 5. 升级策略（UpgradePolicy）

决定何时升级到下一层。三种内置策略 + 可自定义：

| 策略 | 逻辑 | 适用场景 |
|:---|:---|:---|
| ThresholdBased | confidence < tier.threshold -> 升级 | 默认 |
| AdaptiveThreshold | 根据 correction_rate 动态调整阈值 | 长期运行的自优化 |
| BudgetAware | 根据剩余时间预算决定是否升级 | 时间敏感场景 |

可自定义策略：例如升级条件联合判断（confidence < 0.7 AND uncertainty_marker=True）。

## 6. 修正反馈闭环（FeedbackLoop）

这是所有快慢系统最缺的一环。统一定义：

`
Tier N+1 纠正了 Tier N 的结果：
  -> feedback.record_correction(tier=N, correction={...})
  -> feedback.apply():
       将修正写回 Tier N 的本地规则/缓存
       Tier N 的 correction_count += 1
       
  如果 Tier N 的 correction_rate > 阈值:
      触发规则更新（扩充词典/调整正则/追加排除模式）
      生成 Observation: pattern_detected=tier_N_has_systematic_errors
`

闭环不依赖具体的规则格式。每个 Tier 实现了 apply_correction() 接口——
Tier 自己知道如何把修正整合到本地缓存中。FeedbackLoop 只负责调度和阈值判断。

## 7. 监控与调优

PipelineMonitor 输出每层和全局统计：

| 指标 | 含义 |
|:---|:---|
| pass_through_rate | 该层直接返回的比例（越高说明前面的层越精准） |
| upgrade_rate | 从该层升级到下一层的比例 |
| correction_rate | 该层结果被下层修正的比例 |
| avg_latency_per_tier | 每层平均延迟 |
| weighted_avg_latency | 全局加权平均延迟 |

调优：如果 Tier 1 的 upgrade_rate > 60% -> 提升 Tier 1 的词典覆盖率。
如果 Tier 0 的 correction_rate > 20% -> 缓存策略需要重审。

## 8. 全系统映射

哪些现有模块适合套用 MultiTierPipeline：

| 模块 | 谱系配置 | 已经做的 | 要做的事 |
|:---|:---|:---|:---|
| TieredParser | L1(规则) + L2(spaCy) + L4(LLM) | 已实现 | 迁移到通用 Pipeline |
| Code Context Graph | L0(Tree-sitter) + L2(AST) | 未实现 | 新建 |
| BehaviorGraph 更新 | L1(即时纠正) + L3(模式学习) | 无快慢 | 拆分更新路径 |
| CausalSubstrate | L1(统计关联) + L4(LLM因果) | 无快慢 | 新建双路径 |
| UserProfile 更新 | L1(显式信号) + L3(隐式推断) | 无快慢 | 拆分更新路径 |
| NegativeKB | L1(关键词) + L2(语义) | 无快慢 | 新建双路径 |
| IntentParser | L1(规则分类) + L4(LLM消歧) | 有降级无谱系 | 迁移到通用 Pipeline |

## 9. 实现计划

| Phase | 内容 | 预估 |
|:---|:---|:---|
| Phase 1 | MultiTierPipeline 框架 + Tier/TierStats + PipelineMonitor | ~200 行 |
| Phase 2 | UpgradePolicy(3种) + FeedbackLoop | ~100 行 |
| Phase 3 | 迁移 TieredParser 到通用 Pipeline | ~50 行 |
| Phase 4 | Code Context Graph 接入 MultiTierPipeline | ~80 行 |
| Phase 5 | BehaviorGraph/CausalSubstrate/UserProfile 拆分快慢路径 | ~200 行 |

---

> MultiTierPipeline 不是替代现有的快慢系统——是统一它们的编排、修正和监控。

### 7.1 ParameterRegistry 集成

所有 Tier 的 confidence_threshold 纳入 ParameterRegistry 统一管理。
Tier 构造时传入 confidence_threshold_param 和 registry，初始值从 Registry 读取。
Tier.apply_correction() 发生时根据 correction_rate 自动上调或下调阈值。
参数定义见 RFC_PARAMETER_REGISTRY.md 第 2.9 节。


---

## 10. TierHeatBridge?Pipeline ? ??????????

### 10.1 ??

MultiTierPipeline ? GraphTierManager ??"??"???????

| ?? | MultiTierPipeline | GraphTierManager |
|:---|:---|:---|
| ???? | **?????**????????? | **????**??????? ? ????? |
| ???? | ??-????????????????? | ???????Hot?Warm?Cold?Archive? |
| ???? | ????? ? ?????? | ?????? ? ?????? |
| ???? Pipeline? | ? | **???**?GC ??"?????????" |

?? **GraphTierManager ?????? MultiTierPipeline**???????????????????????

### 10.2 ???TierHeatBridge

???????????? <100 ???? Pipeline ????????? GC ??????

```
MultiTierPipeline.stats()
       ?
       v
TierHeatBridge
  ?? ??? tier ? pass_rate / correction_rate / avg_latency_ms
  ?? ??? domain + tier ???????
  ?? ? ParameterRegistry ? tier_heat_* ????
  ?? ?? promote / demote ??
       ?
       v
GraphTierManager.promote(node) / demote(node)
```

### 10.3 ??????

??? domain-tag ??? `negative_kb:block_system`???????? tier ??????

```
heat_score = ? (pass_rate_tier ? weight_tier) - ? (correction_rate_tier ? penalty_tier)

where:
  weight_tier = 1.0 / tier_level    # ?????????????=????
  penalty_tier = 0.5 ? tier_level   # ???????=?????

heat_score ? [-1, 1]   # >0.5=?,  < -0.5=?,  ??=?
```

### 10.4 ??

```
TierHeatBridge
  ??? register_pipeline(pipeline: MultiTierPipeline, domain_tags: list[str])
  ??? collect() -> List[HeatSignal]          # ??????1???
  ??? evaluate() -> List[PromoteDemote]      # ??????
  ??? apply(store: UnifiedGraphStore)        # ????
```

HeatSignal:

- domain_tag: ?????
- heat_score: ??????
- dominant_tier: ???????????
- correction_trend: ??????????
- suggestion: "promote" | "demote" | "keep"

### 10.5 ??????? ParameterRegistry?

| ?? | ??? | ?? |
|:---|:---|:---|
| `heat.promote_threshold` | 0.6 | heat_score > ?? ? promote |
| `heat.demote_threshold` | -0.4 | heat_score < ?? ? demote |
| `heat.collect_interval_ms` | 60000 | ???? |
| `heat.min_samples` | 50 | ?????????? |

### 10.6 ????????

- **??? GraphTierManager** ? HeatBridge ?? promote/demote ??????
- **??? MultiTierPipeline** ? HeatBridge ??? stats() ??
- **?? ParameterRegistry** ? ?????????
- **??** ? ?? PipelineMonitor ? stats ??

### 10.7 ?????

```
????
  ?
  ?
MultiTierPipeline.execute()
  ?? Tier 0 (?) ? ?? ? ???pass_through++?
  ?? Tier 1 (?) ? ?? ? ?? + ?? hint
  ?? Tier 2 (?) ? ?????upgraded++?
  ?
  ?
Pipeline.stats()  ? ?? pass_rate / correction_rate
  ?
  ? (? 60s)
TierHeatBridge.collect()
  ?? ?? domain ??
  ?? ?? promote/demote ??
  ?
  ?
GraphTierManager
  ?? promote: Cold ? Warm, Warm ? Hot
  ?? demote:  Hot ? Warm, Warm ? Cold

????????????? ? Pipeline Tier 0 ????? ? ??????
```

---

> TierHeatBridge ???? GC???? GC ?????????**????**?????????
