# 阶段 B P2 施工 — GAP-5 taint / GAP-O4 world 归位 / 启发活性 / 反推成本（2026-08-07）

> 状态: 完成 ✅ | 四项（对标剩余 + 二阶抽象配套）

---

## 一、GAP-5 回合污染跟踪（OpenClaw toolResultTaintsTurn 对齐）

### 问题
工具失败/异常结果直接进上下文, 后续判定（llm_reply）无法区分可信与不可信证据。

### 实现（executor.py）
- `self._turn_tainted` — 回合污染标记（execute 入口重置 False）
- `_record_tool_step`: 工具失败 → `_turn_tainted=True` +
  决策事件 after 加 `tainted` 字段（可回看）
- `_summarize`: 失败/blocked/unavailable 输出 → `[不可信]` 前缀
  （污染传播到 llm_reply 上下文）
- `execute` 返回 `tainted` 标志（上层/前端可感知回合可信度）

### 验证
`test_taint.py` **3/3**: 失败→tainted=True / 成功→False / [不可信] 标注

## 二、GAP-O4 world/importance 归位（断线修复, 非归档）

### 判定修正
`world/importance.py`（13KB, 7 策略 + 工厂 + 复杂度分析）**不是历史遗留**,
是"设计好但断线"——`compute_backbone_scores` / `write_backbone_to_graph`
全库零调用; `compiler.py` 读 `graph.backbone` 恒 0 → backbone 优先级是假的。
`world/community.py`（CommunityChunkStrategy 依赖）同断线。

### 接线（compiler.py）
- `_ensure_backbone(graph)`: compile_subgraph 入口懒填充
  （backbone 已填则跳过）— TieredImportanceStrategy 按图大小自适应路由
  （betweenness / k-sampling / community-chunk）→ compute_backbone_scores
  四维融合（缺省结构维度）→ write_backbone_to_graph 写回 graph.backbone + units
- 一处接线, 任何调用方生效（adapter 构建链无需改动）

### 验证
`test_importance_wiring.py` **3/3**: 星形图中心 backbone 最高 /
  compile 触发填充 + backbone_units 排序 / 四维融合权重正确

## 三、启发活性监测（A24 配套）

### 实现
- `HeuristicInventory.check_health(threshold=0.5)` — active 且 coverage < 阈值
  的蒸馏/规则启发 → stale（**种子不自动停用**: 人为维护的示范）
- `HeuristicInventory.deactivate_stale(threshold)` — 批量停用 + 持久化
- `LearningBridge.check_heuristic_health(threshold)` — 停用 + 决策事件记录
  （kind=heuristic_health, 可回看）; 停用启发由下一次蒸馏重新长出

### 验证
`test_check_health_deactivates_stale` + `test_health_check_via_bridge`:
  蒸馏/规则低覆盖停用, 种子/健康启发保留

## 四、LLM 反推成本优化

### 实现（heuristic_distiller.py）
- `verify_sample_size` 构造参数: 默认 12（原 20）
- 护栏 clamp: `[4, 20]`（下限保证统计意义, 上限成本护栏）
- 成本: 每候选反推验证从 20 次 LLM 判定降为 12（-40%）

### 验证
`test_verify_sample_size_param_clamped`: 默认 12 / 100→20 / 1→4 / 8→8

## 五、总验证

- 新增 **25/25 全绿**: 启发套件 19 + taint 3 + world importance 3
- 回归 **82/82 全绿**: learning_bridge 12 + production_learning 3 +
  learn_template 4 + tool_batch 8 + tool_node 6 + kernel_dispatch 49

## 六、遗留

- taint 前端可视化（决策事件已有 tainted 字段, GAP-F1 变更日志可展示）
- 活性监测触发频率（当前手动/桥接调用, 可挂到定时或失败触发链）
- world 其他维度（runtime/commit/retrieval centrality）待数据源接入,
  当前仅结构维度（w_structural=1.0 效果）
