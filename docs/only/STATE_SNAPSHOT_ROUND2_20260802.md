# 冻结快照 — 2026-08-02 第二轮（行为链质量深挖 + DPO，压缩前）

> 目的: 压缩前冻结本轮完成情况与待办，压缩后以此文档 + STATE_HANDOFF §十三/§十四 为恢复入口。
> 下一步: **对话树专项审计**（🔴 最严重，3 处同名类分裂）——入口见 `docs/only/discourse_tree/AUDIT_ENTRY_20260802.md`。

---

## 一、本轮完成（2026-08-02 第二轮会话）

### 1.1 行为链压测 + 强壮性（新增 18 项，-m slow）

- `tests/test_behavior_stress.py`（新）: 300 事件流 / 50 次预测稳定 / 并发 registry+40 线程 / brain 8 线程并发 / 后台预测防线程堆叠 / token 预算耗尽 L1 强制 stats / 生命周期非法转换 / LLM 故障回退 / 坏图容忍 / registry 越界拒绝 / reward 值域 / `_shared_direction` 对抗 / scheduler 200 次稳定性 / 持久化 round-trip / 重模拟预算耗尽 / 空输入
- 验证: **18/18 绿**
- 修复的真实缺陷: `predictor.predict()` 未捕获 LLM 异常 → 现在回退 hints/fallback（BC05 §2 成本悖论降级）

### 1.2 DPO 偏好学习（B6，新增但待审计）

- `core/agent/behavior/dpo_learner.py`（新）: `PreferencePair` + `DPOLearner`（record/ready/learn/apply_to_graph/reset/stats）
- 反馈映射（LLM_COLLABORATIVE §四）: accept→preferred(1.0) / reject→dispreferred(1.0) / correction→preferred(0.8) / no_response→weak(0.3)
- N>20 触发（registry `behavior.dpo_min_pairs=20`）; LLM 蒸馏（非参数, ADR-014）失败回退规则蒸馏
- `brain.py` 接线: `learn_from_event` 记录偏好对 + `on_checkpoint` 触发蒸馏并应用图权重
- **⚠️ 粗糙点待审计（勿直接固化）**:
  1. `top1 == summary` 不可靠（summary=用户文本 vs 预测=图内动作摘要，字符串相等几乎恒 false → 假 reject 池）
  2. `no_response` 弱信号污染（无预测事件记 `(summary, summary)` preferred 对，语义错误）
  3. LLM 蒸馏 action→delta 与图内 action_summary 字符串对齐率低
  4. 正确方向: 仅对可观测行为事件（ui/tool/api/config/document kind）记录；accept/reject 用 top3 命中或语义相似；对话类事件仅弱信号或不记
- `tests/test_dpo_learner.py` **未建**（待办）

### 1.3 llm_collaborative 修复

- `core/agent/behavior/llm_collaborative.py`: 清除 `suggest_and_apply` return 后死代码残留；新增 `record_observation`/`get_patterns`（BehaviorGraphBridge 契约：发现→审核→吸收）
- `core/agent/engineering_bridges.py`: `BehaviorCollaborative`（不存在）→ `BehaviorLLMCollaborator`（消除 try/except 静默吞）
- `tests/test_behavior_collab.py`: 4/4 绿（此前回归遗漏，本轮纳入）

### 1.4 其他

- `core/agent/compiler/tests/test_parameter_registry.py`: 对齐真实实现（load_defaults 移除 + 2 个不存在参数断言修正）→ 9/9 绿（预先存在的坏测试）
- `docs/only/behavior/BEHAVIOR_IMPL_PROGRESS_20260802.md`: 行为链 P0-P3+CLI 全量施工记录

## 二、测试终态

| 套件 | 结果 |
|------|------|
| 行为链核心（brain 9 + scheduler 23 + cli 8 + collab 4 + rewarder 16 + predictor 9）| **69/69** |
| 行为链压测（slow）| **18/18** |
| 全量回归（关联链 103 + 蓝图 10 + 子图 40 + PCR 9）| **162/162**（DPO 接入前验证）|
| 行为链全套（含旧 behavior_graph 50 + adapter 8）| **124/124**（DPO 接入前验证）|

## 三、待办（压缩后按序）

1. **DPO 粗糙点审计 + 修复**（§1.2 四项）→ 补 `tests/test_dpo_learner.py`
2. **对话树专项审计**（下一个模块，🔴）:
   - 3 处同名 `DiscourseBlockTreeManager`: `compiler/discourse_block_tree.py:698` + `discourse/models.py:33` + `discourse_block_tree/manager.py:17`
   - 4 处 `DiscourseBlock`: compiler:340 + discourse/models:24 + 另有 2 处待定位
   - 入口: `docs/only/discourse_tree/AUDIT_ENTRY_20260802.md`
3. 行为链剩余: B5 回退重模拟 engine 接线 / B7 多视角识别跨模块 / 显式承诺持久化挂载
4. 蓝图 P1 清单（STATE_HANDOFF §八）

## 四、环境坑（回查）

- anaconda 3.9: pytest 可用，numpy/transformers 坏 → 全管线 state machine 偶发 0xC000013D（后台线程退出竞态，`brain.shutdown()` 已防御）
- stderr `State save failed PermissionError: ~/.dialogmesh/state.json` = 环境噪音（_save_state 已防御）
- PowerShell stdin 传 python 中文乱码 → UTF-8 文档用 apply_patch 写，脚本避免中文字面量
