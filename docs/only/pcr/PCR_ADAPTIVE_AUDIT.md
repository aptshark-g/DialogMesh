# PCR 自适应闭环可行性审计（A18 落地前）

> 审计日期: 2026-08-01
> 审计目标: 确认 A18 参数自适应闭环落到 PCR 所需的组件，在设计与代码中的真实状态
> 审计方法: 逐组件对照"设计文档 vs 具体实现 vs 接线情况 vs PCR 接入点"
> 结论先行: **组件全部存在且大多已接线；PCR 是唯一零接入的模块；三套参数系统并存需先拍板。**

---

## 一、参数系统全景（三套并存，需拍板）

| # | 实现 | 风格 | 状态 | 使用方 |
|---|------|------|:---:|--------|
| 1 | `core/agent/adaptive_parameter.py` | lr 学习率 + reanchor + history | ✅ 完整 | `api/pipeline_api.py`、`cli/registry.py` |
| 2 | `core/agent/compiler/parameter_registry.py` | EMA observe/adapt + 策略预设 + vmin/vmax | ✅ 完整（有测试） | v4 world 层、`observation/models.py` |
| 3 | `core/agent/v3_2/un_use/parameter_registry.py` | 旧版 ParameterCalibrator | ❌ 弃用（un_use） | 无 |

**拍板点 1**: PCR 接哪套？建议 **ParameterRegistry（#2）**——EMA 自带防抖、策略预设可切换、已被 v4 world 层使用、有单测。

---

## 二、组件审计表

| 组件 | 设计来源 | 实现状态 | 接线情况 | PCR 接入点 | 判定 |
|------|---------|---------|---------|-----------|:---:|
| AdaptiveParameter | RFC_PARAMETER_REGISTRY §6 | `adaptive_parameter.py` ✅ | pipeline_api/registry | 参考其 anchor/lr/history 模式 | ⚠️ 与 #2 重复 |
| ParameterRegistry | RFC §1-§8 | `compiler/parameter_registry.py` ✅ | v4 world + observation | PCR 全部权重注册于此 | ✅ 首选 |
| DeltaAdjuster | ENGINEERING_V3_3_CAUSAL_SUBSTRATE §7 | `association/delta_adjuster.py` ✅ | causal_substrate 接线 | PCR 步长/冷却复用（±0.02/50轮模式） | ✅ 可复用 |
| CorrectionJournal | DESIGN_COLD_HOT_FEEDBACK Layer3 | `v4/cognitive/correction_journal.py` ✅ | metacognition/fusion/integration | PCR 慢信号（用户修正 zone → 回流） | ✅ 可复用 |
| DynamicsComputer | DESIGN_COGNITIVE_DYNAMICS_V6 | `v4/cognitive/dynamics.py` ✅ | metacognition/fusion/convergence | PCR drift 检测信号源 | ✅ 可复用 |
| 元认知周期扫描 | BUSINESS_CHAIN_09 §4 | `v4/cognitive/metacognition.py` ✅ | 消费 CJ + Dynamics | PCR zone 误判率漂移 → 调阈值 | ✅ 已接线 |
| pcr_router_v2 权重 | DESIGN_PCR §8.1 | `pcr_router_v2.py` ⚠️ **零接入** | 无参数系统 import | 全部魔法数 → ParamDef 注册 | ❌ 需改造 |

---

## 三、PCR 现状：魔法数清单（从代码提取）

| 位置 | 魔法数 | 说明 |
|------|--------|------|
| `_compute_distance` | 0.7 / 0.3 | X 轴语义距离×0.7 + IDF×0.3 |
| `_compute_distance` | 0.3 / 0.7 | 英文 fallback: entity_density×0.3 + rarity×0.7 |
| `_compute_distance` | 0.5 + 0.3 | 中文 fallback: entity_density×0.5 + 0.3 |
| `_compute_granularity` | 0.4 / 0.3 / 0.3 | Y 轴 verb/entity/wordcount |
| zone 判定 | 0.3 / 0.3 / 0.7 / 0.6 / 0.3 | v2 放宽版阈值（与设计值 0.2/0.7/0.5 不一致） |
| 内部融合 | 0.4 / 0.4 / 0.2 | x×0.4 + y×0.4 + │z│×0.2 |
| LLM 协同审查 | 0.3 | 偏差 > 0.3 才覆盖重算 |

---

## 四、结论

1. **组件不缺，缺接线**：参数系统、步长器、修正日志、元认知扫描全部存在且大多已接线（画像/元认知/因果路径），唯独 PCR 零接入。
2. **三套参数系统并存**：接入 PCR 前必须先拍板用哪套（建议 ParameterRegistry），否则制造第四套。
3. **PCR 接入是"参数化 + 挂线"，不是"新建系统"**：把魔法数注册进 ParameterRegistry，把 DeltaAdjuster/CorrectionJournal/metacognition 的现有回路接到 PCR 事件上。

---

## 五、建议的最小接入路径

```
P0: 魔法数参数化 —— pcr_router_v2 全部权重/阈值注册为 ParamDef（进 ParameterRegistry，带 vmin/vmax）
P1: 快信号 —— 黄金样例 zone 命中率 → registry.observe() → adapt()（EMA 防抖）
P2: 慢信号 —— CorrectionJournal 记录用户 zone 修正 → 回流调整阈值
P3: 元认知扫描 + 行为链 drift —— 复用 metacognition 现有回路 + DeltaAdjuster（±0.02/50轮）
P4: 审计 —— Event Log + per-param change log + CLI 白盒（dm pcr config show/set/reset）
```

---

## 六、拍板结果（2026-08-01）

1. **PCR 接 ParameterRegistry**（#2，EMA observe/adapt + 策略预设）—— 已写入 DESIGN_PCR.md §8.4
2. **三套系统归档**: 主用 #2；#1 `adaptive_parameter.py` 保留（pipeline_api/cli 在用，不改不删）；#3 `v3_2/un_use` 清理候选
3. **P0 参数化范围**: 全部魔法数（非简化，质量优先）
