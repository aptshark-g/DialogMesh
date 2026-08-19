# switch 网关 — LLM 网关专属功能清单（2026-08-19）

> 对照主流 LLM 网关（one-api / LiteLLM / k8s gateway）盘点 switch 现状。

## 一、已有（生产级, 非 demo）

| 能力 | 说明 | 状态 |
|---|---|---|
| 响应缓存 | 内存 TTL 缓存, 键 = messages + 生成参数 | ✅ 已修隔离（见下） |
| **缓存命中率** | CacheHits/CacheMisses 计数 + admin 页展示 + `/v1/stats.cache_hit_rate` | ✅ 本轮补 hit_rate |
| 请求合并 | 同 key 并发 → 1 次上游调用（coalescer） | ✅ |
| 健康缓存 | provider 健康探测结果缓存, 不串行阻塞 | ✅ |
| **上下文/租户隔离** | per-key 配额（月度 token/成本上限/模型白名单/软限警告）; 网关无会话状态, 对话上下文天然隔离 | ✅ 配额已有; 缓存隔离本轮修复 |
| 限流 | per-provider RPM + 多档 rate limit | ✅ |
| 熔断 | 滑动窗口 + 自适应（3-5 次失败, 恢复探测） | ✅ |
| 流式聚合 | SSE tool_call 按 index 合并碎片/空 arguments | ✅ |
| 计费 | per-key/per-model JSONL 落盘 + 重放 | ✅ |
| per-key 配额 | 租户级 token 配额 + 每日用量 | ✅ |
| 错误码目录 | /v1/error-catalog（码 → 含义 → 处置） | ✅ |
| admin 页 | 零依赖控制台: providers/health/计费/用量 | ✅ |
| 热更新 | 50ms diff（added/updated/removed） | ✅ |
| 认证 | Bearer API key + admin token（env 注入, 不入库） | ✅ |
| 可观测 | metrics / SLO 燃烧率 / tracing / 压测 3.4K-22.8K req/s | ✅ |
| 降级/甩尾 | load shedding + graceful degradation + failover | ✅ |

## 二、本轮修复

- **缓存隔离缺陷（真 bug）**: `cache.HashKey(req, "")` 的 model 参数此前传空串
  → 缓存键不含 model/provider/租户, 跨模型、跨 Provider、跨租户会误命中。
  已修为 `provider|model|api_key` 三重命名空间。
- **stats 补 `cache_hit_rate`**（前端网关页「缓存命中率」卡此前恒 0）。

## 三、缺失/待办（可选的增强项）

- **语义缓存**（embedding 相似度命中, 非精确键）— 主流网关多为精确缓存, 此为增强。
- **内容安全过滤**（输入/输出审计或关键词拦截）。
- **按用户/项目维度的用量看板**（当前 per-key; 可加 per-model 时间序列, DialogMesh 前端已有 usage/series 消费侧）。
- **多实例共享缓存/限流**（当前单机内存; 多副本需 Redis）。
- **配额自动续期/订阅管理**（当前静态配置）。

## 四、结论

网关不是 demo 级——生产要素齐全; 本轮修复了缓存隔离这一关键正确性/安全缺口。
发布形态已具备（CI release 工作流, 打 v* tag 出三平台二进制）。
