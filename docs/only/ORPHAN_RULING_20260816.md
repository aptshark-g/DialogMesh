# 孤儿组件裁决记录（2026-08-16）

> 触发: 接线核查探针发现"有实现零调用"组件群（GAP 5.2/5.5）。
> 裁决口径: **能接的接（有真实价值且低成本）, 该归档的明确归档**
> （标注 ARCHIVED + 理由, 不删代码 A17, 不移动文件避免 import 断裂）。

## 一、已接线

| 组件 | 接线 | 理由 |
|---|---|---|
| `MetaFeedback.suggest_blueprints`（GAP-D3 P1） | `/v6/blueprint/suggestions` 白盒端点 | 蓝图自增长建议链（高频意图≥3 次 → 建议建模板）; 数据源 `_intent_sightings` 已由 `update_strategy_weights` 填充, 只缺消费方 |

## 二、已归档（功能被现有实现覆盖 / 属后期阶段）

| 组件 | 归档理由 | 覆盖方 |
|---|---|---|
| `HybridSearchEngine`（hybrid_hyde.py） | persistence 旧体系 | recall_service 统一召回（HyDE 扩展 + RRF + 图扩散） |
| `WaveQueryEngine`（wave_query.py） | 水波扩散旧体系 SQL 生成器 | recall_service expand_graph / k-hop |
| `AuditTrail`（audit_trail.py） | A17 记录分散承担, 统一聚合视图 P2 | decision_bus + 各子系统 JSONL |
| `WriteAheadLog`（write_ahead_log.py） | 崩溃恢复属分布式阶段（G5） | —（单进程内存态无需求） |
| `SandboxExecutor`（p1_gaps.py） | 工具沙箱零调用 | permission_engine（RiskClass/Mode/path root） |
| executor `_handle_discourse/_handle_engineering` | 生产已走 StateMachine | event/handlers.py |
| executor `expand_from_dag_trace / route_mode` | P2 设计承诺未兑现, 不阻塞生产 | —（记录待后续） |

## 三、待办联动

- `update_source_credibility`（GAP-D4 P2）: 来源可信度学习, 保持待办（低优先）。
- 统一审计聚合视图（AuditTrail 重启用）: 排前端绑定阶段。
- 后续新组件原则: 注册/定义即接线或标注阶段, 不再留"无主组件"。
