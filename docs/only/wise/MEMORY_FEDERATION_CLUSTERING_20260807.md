# 施工记录 — memory_strategy_federation 接入二阶抽象聚类（2026-08-07）

> 状态: 完成 ✅ | 触发: UN_USE_AUDIT 判定"高价值断线"候选 →
> 用户确认接入二阶抽象聚类

---

## 一、恢复（un_use → 活跃）

- `core/agent/un_use/memory_strategy_federation/` → 恢复为
  `core/agent/memory/strategy_federation/`（6 文件 46KB）
- 修复内部引用: cluster_map.py L172 `un_use.memory_strategy_federation`
  → `core.agent.memory.strategy_federation`
- 新增 `memory/__init__.py`（说明 + 归档审计依据）
- 恢复模块全部可导入（StrategyFederation / CompressionRouter / MemoryCard /
  FederatedAnchorIndex / RAGraphBridge / ClusterMap）

## 二、接入（HeuristicDistiller 规则兜底增强）

### P×I 信息论路由（用户深化修正 2026-08-07）

**质疑**: "低概率只靠出现次数是不是太粗糙了？" — 低频垃圾 vs 低频高价值
统计频率相同, 价值天差地别。**修正**: I（信息价值）= LLM 语义评估,
与冷热系统互补（ColdIndexer importance 三信号: activation_count /
recency / semantic_value）。

**路由规则**:
```
P(≥0.5)          → aggregate（高频凝练）
P(<0.3) + I(≥0.6) → preserve（低频高价值, 深路径保留）
P(<0.3) + I(<0.6) → filter（低频低价值, 不因稀有而保留）
P(中)             → filter
```

**实现**:
- `_info_route(frequency, semantic_value)` — 三信号路由（替代单频率）
- `_semantic_value_proxy(intent_count, seq_len, total_seqs)` — 无 LLM 时
  的语义价值代理（意图多样性 × 0.5 + 新颖度 × 0.3 + 序列长度 × 0.2）
- LLM 路径: 收敛步骤（_converge）让 LLM 显式评 `information_value`
  （新颖性/可迁移性/是否揭示机制, 提示词明示"不因低频就高, 垃圾=低值"）
- `_rule_baseline` 规则兜底: 按 P×I 路由产出启发（aggregate=高覆盖 /
  preserve=低频高价值保留 / filter=不沉淀）

## 三、验证

- 新增测试: `test_info_route_three_signal`（三参数路由）+
  `test_semantic_value_proxy`（价值代理）
- 启发套件 + learning_bridge: **33/33 全绿**
- 恢复模块 import 探针: OK

## 四、对齐

- 博客 §8.5 RAG 分治（Shannon 自信息: 高概率凝练 / 低概率保留）—
  CompressionRouter 是该思想的现成实现（P×I 存储路由）
- ColdIndexer importance 三信号（G2 EventBus 温减枝同源）
- 用户深化: 冷热系统（频率加权）与信息论（语义价值）互补, 非替代

## 五、遗留

- MemoryCard heuristic 卡片类型 ↔ HeuristicInventory 互转（XML 记忆卡片
  作为启发库存的持久化形态之一, P2）
- FederatedAnchorIndex / RAGraphBridge 接入检索路径（A25 级联召回的
  多源锚点, P2 — 与 B2-3 持久化能力底座联动）
- StrategyFederation 多策略聚类（LLM/blueprint/Markov/greedy + 验证循环）
  作为 distiller 聚类环节的进阶（当前规则兜底用简化路由, P2）
