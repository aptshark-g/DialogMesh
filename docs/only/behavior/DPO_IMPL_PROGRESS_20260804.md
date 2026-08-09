# 行为链 DPO 批次施工记录 — 2026-08-04

> 依据：`RECOVERY_PLAN_20260803.md` §三（3.1 DPO 粗糙点 / 3.2 测试 / 3.3 B5+B7+持久化）
> + `STATE_SNAPSHOT_ROUND2_20260802.md` §1.2（DPO 偏好学习四项粗糙点）。
> 状态：**行为链 DPO 批次完成**。

---

## 一、施工内容

### 3.1 DPO 粗糙点修复（3 项）

| # | 粗糙点 | 根因 | 修复 | 文件 |
|---|---|---|---|---|
| 3.1a | `top1 == summary` 不可靠 → 假 reject 池 | predictor 的 top1 是图内动作摘要，dialog 事件 summary 是用户文本，字符串相等恒 false | 新增 `OBSERVABLE_ACTION_TYPES = {ui, tool, api, config, document}`；brain `learn_from_event` 仅对可观测 kind + 有 top1 时记录偏好对（dialog 类直接跳过）| `behavior/dpo_learner.py` + `brain.py` |
| 3.1b | `no_response` 污染（`(summary, summary)` 自对）| 无预测时记录 `(summary, summary)` 语义错误 | `DPOLearner.record` 丢弃 `predicted==actual` 的 no_response 自对；`_rule_distill` 跳过自对/空对（防御）| `behavior/dpo_learner.py` |
| 3.1c | LLM 蒸馏 action→delta 与图内 action_summary 对齐率低 | 字符串精确匹配，LLM key 带大小写/空白差异 | `apply_to_graph` 双通道：精确 + 归一化（去空白/大小写）匹配，钳制 [0,1] | `behavior/dpo_learner.py` |

### 3.2 测试补全 ✅

- 新增 `behavior/tests/test_dpo_learner.py` **18 项**：
  反馈映射（accept/reject/correction 权重/无效信号）/ no_response 自对丢弃 /
  可观测 kind 门控（dialog 不进池、ui+top1 命中→accept、真实 reject）/
  阈值触发（ready/learn 重置池+计数）/ 图权重应用（精确/归一化/无匹配跳过/钳制）/
  白盒 stats（learn 前后）。

### 3.3 B5 / B7 / 显式承诺持久化接线 ✅

| 项 | 内容 | 文件 |
|---|---|---|
| 承诺持久化挂载 | engine `_init_behavior_brain` 传 `commitments_store_path="data/behavior/commitments.json"`；brain `on_checkpoint` 落盘 `commitments.save()` | `runtime/engine.py` + `brain.py` |
| B7 多视角识别 | `learn_from_event(event, pcr_zone="")` — PCR 视角输入：ABYSS/PRECISION/CHAOS 域声明置信度门槛 0.7→0.6（高压下承诺语义更重）；常规域保持 0.7 宁缺勿滥；承诺 metadata 记 pcr_zone | `brain.py` |
| B5 回退重模拟 | engine `_maybe_commitment_resimulation(brain)`：`cold_start_retry_trigger`（turn≤3 或 PCR ABYSS/CHAOS/MIXED+ambiguity>0.5）触发 → 后台线程 `simulate_with_retry` → distilled 承诺入 registry（每会话限 1 条，无 LLM 诚实降级）| `runtime/engine.py` |
| 辅助 | `CommitmentRegistry.add` 补 `metadata` 参数 | `explicit_commitment.py` |

---

## 二、验证数字

```
DPO 新测试:            behavior/tests/test_dpo_learner.py 18/18
行为链+状态机回归:       behavior/ + statemachine_m4 36/36
画像+认知+行为跨模块:     81/81（profile_wiring 19 + fact_store + cognitive + adapter）
端到端冒烟（UTF-8 文件方式，PowerShell 中文乱码为显示问题）:
  B7: ABYSS 域"以后每次开会前都要先检查依赖版本" → commitment 入 registry
      (when=以后每次开会前, should=先检查依赖版本, zone=ABYSS) ✅
  B7: MIXED 域普通闲聊 → 不误加 ✅
  B5: turn≤3 + mock LLM → resim flag=True + distilled 承诺入 registry ✅
  持久化: on_checkpoint → commitments.json 落盘（测试 cwd=C:\tmp 时相对路径
          解析到 C:\tmp 属预期；engine 固定 data/behavior/ 路径正确）✅
```

---

## 三、遗留（记录不施工，边界纪律）

1. `data/behavior/commitments.json` 相对路径依赖进程 cwd（与 FactStore/OCEAN
   同约定；CLI 从项目根启动即正确）。
2. B5 resim 每会话上限 1 条用 `_resim_ran` 标志（非 registry 参数，会话级即可）。
3. B7 目前接入 PCR 一个外部视角；关联链/子图视角的声明识别接口（设计提到）
   归后续批次（避免跨模块越界）。

---

*本文件是行为链 DPO 批次施工记录；交接入口见 `STATE_HANDOFF_IMPLEMENTATION_20260804.md`。*
