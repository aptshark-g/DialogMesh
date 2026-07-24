# Behavior Chain — LLM-Collaborative Learning Design

> 2026-07-24 · 行为链升级: 纯统计→LLM协同强化学习

---

## 一、当前 vs 前沿

```
当前: BehaviorStep记录 → 统计转移概率 → 成功率
      ❌ 纯算法, 无LLM
      ❌ 无自适应阈值
      ❌ 无异常行为解释

前沿:
  RLHF:  LLM学习用户偏好 → 调整行为预测
  DPO:   直接偏好优化 → 减少reward hacking
  Implicit: 用户接受/拒绝/修正 → 隐式反馈信号
  Online: 每轮更新 → 实时适应
  
目标: Q-table基础: 用户修正=负奖励, 接受=正奖励
      LLM协同: 解释行为变化, 建议新行为模式
      DPO: 隐式反馈→偏好对 → LLM学习
```

## 二、三层架构

```
Layer 1: 信号采集 (已有)
  BehaviorStep.record_observation(success, correction)
  → edge.success_rate, edge.instability_ratio

Layer 2: LLM协同分析 (新增)
  行为变化时 → LLM解释: "为什么'诊断→修复'成功率从0.9降到0.4?"
  异常模式时 → LLM发现: "每次先分析后回退, 可能缺少验证步骤"
  阈值调参:   LLM建议: "correction_threshold从0.3调到0.25"

Layer 3: DPO偏好学习 (新增)
  用户接受 → 正偏好对: (predicted_behavior, user_actual)
  用户拒绝 → 负偏好对: (predicted_behavior, user_actual)
  LLM从偏好对学习 → 调整behavior classifier权重
```

## 三、LLM协同接口

### 3.1 行为变化解释

```python
def explain_behavior_drift(edge: BehaviorEdge, llm) -> str:
    """LLM解释行为模式变化"""
    ctx = {
        "behavior": f"{edge.from_action} → {edge.to_action}",
        "old_success_rate": edge._historical_success[-5:-1],
        "new_success_rate": edge.success_rate,
        "recent_corrections": edge.correction_count[-5:],
    }
    # → LLM: "最近成功率下降可能因为用户切换了工具链"
```

### 3.2 异常模式发现

```python
def discover_anomalous_patterns(graph, llm) -> List[Pattern]:
    """LLM从行为图中发现异常模式"""
    ctx = {
        "top_unstable": graph.unstable_edges(top_k=5),  # 成功率波动大的边
        "correction_chains": graph.correction_sequences(),  # 连续修正序列
        "cold_spots": graph.cold_regions(),  # 行为空白区
    }
    # → LLM: "A→B→correction→A重复出现, 用户可能在反复尝试后回退"
```

### 3.3 阈值自适应

```python
def adaptive_threshold_update(graph, llm):
    """LLM建议调整行为判定阈值"""
    ctx = {
        "current_thresholds": {"success": 0.7, "instability": 0.3},
        "false_positives": graph.fp_count,  # 预测了但用户没做
        "false_negatives": graph.fn_count,  # 没预测但用户做了
    }
    # → LLM: {"new_thresholds": {"success": 0.65, "instability": 0.25}}
```

## 四、DPO偏好学习

### 4.1 隐式反馈→偏好对

```
用户行为 → 隐式反馈:
  接受预测  → (predicted, actual) → PREFERRED
  拒绝预测  → (predicted, actual) → DISPREFERRED
  修正预测  → (predicted, corrected) → PREFERRED (修正版)
  无反应    → 弱信号, 权重×0.3

偏好对积累:
  [("诊断→修复", positive), ("诊断→探索", negative), ...]
  → DPO训练 → LLM行为分类器权重更新
```

### 4.2 实现路径

```
Phase 1: 信号采集增强
  BehaviorEdge + 历史成功率窗口
  + correction序列记录
  + 用户反应时间 (快速接受=强信号)

Phase 2: LLM协同
  行为变化 → explain_behavior_drift
  异常模式 → discover_anomalous_patterns
  阈值调参 → adaptive_threshold_update

Phase 3: DPO学习 (需要持续多轮)
  偏好对积累(N>20) → DPO微调 → 行为分类器更新
  → cold_start种子库更新
```

## 五、数据流

```
用户行为 → BehaviorStep → BehaviorEdge[success_rate, corrections]

每N轮或检测到变化:
  → LLM协同分析:
      explain_drift: "为什么成功率变化"
      discover_pattern: "有什么新行为模式"
      adjust_thresholds: "阈值需要调到多少"
      
  → DPO偏好对:
      (predicted, actual, feedback) → 偏好池
      池满 → 更新行为分类器

  → 反馈回写:
      edge.success_rate ← 重算
      cold_start_seed ← 新发现模式
```

## 六、文件清单

```
新增:
  core/agent/behavior/llm_collaborative.py  — 协同分析
  core/agent/behavior/dpo_learner.py         — 偏好学习
  tests/test_behavior_collab.py              — JSON驱动测试

修改:
  core/agent/behavior/models.py              — 加历史窗口字段
  core/agent/behavior/statistics.py          — 加异常检测
```
