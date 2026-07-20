# DialogMesh v6 — P2 完成质量审计

> 日期: 2026-07-20

---

## P2 总览: 已完成模块化, 引擎+API 未接入 ⚠️

| # | 项目 | 代码 | 引擎接线 | API | 参考设计 |
|:---:|------|:---:|:---:|:---:|------|
| 1 | CausalPromoter (L4→L5) | ✅ 252行 | ❌ | ❌ | ARCHITECTURE_OVERVIEW §六 |
| 2 | TTLManager (HCWA) | ✅ 同文件 | ❌ | ❌ | ARCHITECTURE_OVERVIEW §六 |
| 3 | SubgraphCache | ✅ 同文件 | ❌ | ❌ | ARCHITECTURE_OVERVIEW §六 |

---

## 架构文档中的 P2 缺口 (未实现)

| 项目 | 设计文档 | 状态 |
|------|---------|:---:|
| 存算分离 (ObservationPool+State→对象存储) | ARCHITECTURE_OVERVIEW §六 | ❌ |
| 因果晋升算法 (L4→L5) | ARCHITECTURE_OVERVIEW §六 | ⚠️ 已实现, 未接入 |
| TTL 自动清理 | ARCHITECTURE_OVERVIEW §六 | ⚠️ 已实现, 未接入 |
| Signal HMAC 签名 | SECURITY_PERFORMANCE_AUDIT §P2 | ❌ |
| api_key 加密传输 | SECURITY_PERFORMANCE_AUDIT §P2 | ❌ |
| Snapshot Copy-on-Write | SECURITY_PERFORMANCE_AUDIT §P2 | ❌ |
| 前端乐观更新 | DESIGN_SYSTEM_SCHEDULER | ❌ (前端) |

---

## 接入缺失

```
CausalPromoter:
  ⚠️ 引擎未初始化 (应在 start() 中 init)
  ⚠️ _feed_profile 未调用 assess()
  ⚠️ 无 API 暴露 (/v6/causal → 已有但基于旧实现)

TTLManager:
  ⚠️ 引擎未初始化
  ⚠️ 未接入 HCWA 温度迁移
  ⚠️ 无 API 暴露

SubgraphCache:
  ⚠️ 引擎未接入 SubgraphCompiler
  ⚠️ 无缓存命中率监控
  ⚠️ 无 API 暴露
```

---

## 结论

```
P2 完成率: 3/10 = 30%

已完成: CausalPromoter, TTLManager, SubgraphCache 模块代码
未接入: 3 模块未连到引擎和 API (0 行 engine wiring)
架构缺口: 存算分离, Signal 签名, 加密传输, Snapshot CoW 均未实现

建议: 先接入 3 个已完成的模块, 再评估架构缺口
```
