# Switch Gateway — 全代码审计

> 2026-07-21 · 40 个 Go 文件 · 约 5000 行

---

## 一、架构: 40 文件清单

```
cmd/gateway/          ← 入口 (main.go + selftest.go)
config/               ← 配置解析 (yaml/json → GatewayConfig)
provider/             ← 核心: Manager + Provider 接口 + 断路器 + 限流 + 路由
server/               ← HTTP 层: API + 中间件 + Admin
cache/                ← 内存缓存 (HashKey)
observability/        ← Metrics + Tracing + SLO + StructuredLogger
persistence/          ← 状态保存/恢复 (gateway.state.json)
stream/               ← SSE 流式输出
token/                ← 词元计数
i18n/                 ← 国际化 (有语法错误)
```

---

## 二、启动流程

```
main()
├─ ParseFile(provider.yaml) → GatewayConfig { Providers[], Server, Auth }
├─ NewManager()
│   ├─ RegisterFactory("openai", openai_compatible, ollama) → all → NewOpenAIProvider
├─ store.Restore() → gateway.state.json → 只恢复用量统计,不注册 provider
├─ mgr.Bootstrap(cfg.Providers)
│   ├─ 遍历 providers, Enabled=true → Register(cfg)
│   │   ├─ 创建 Provider(OpenAIProvider)
│   │   ├─ 初始化 CircuitBreaker + Semaphore + RateLimiter + RetryBudget
│   │   └─ 可选 AdaptiveSemaphore
│   └─ Enabled=false → 跳过 (config 存入 allConfigs 但不在 providers map)
├─ go store.StartAutoSave() → 5min 周期 snapshot → state.json
├─ watcher.Start() → 5s 监控 provider.yaml 变更
└─ server.NewWithWatcher(...)
    ├─ 注册路由 (mux.HandleFunc)
    ├─ BuildHandler → 中间件链:
    │   LoadShedding → Tracing → Metrics → CORS → PanicRecovery → Logging → Auth → RateLimit
    └─ Start() on :8080
```

---

## 三、40 端点清单

| 路由 | 方法 | 功能 | 鉴权 |
|------|------|------|:---:|
| `/v1/health` | GET | 健康检查 | public |
| `/v1/health/detail` | GET | 详细健康 | public |
| `/v1/metrics` | GET | Prometheus | public |
| `/v1/stats` | GET | 请求统计 | public |
| `/v1/chat/completions` | POST | **LLM 调用** | api_key |
| `/v1/providers` | GET | 厂商列表 | public |
| `/v1/usage` | GET | 用量统计 | public |
| `/v1/diagnostics` | GET | 诊断信息 | public |
| `/v1/admin/reload` | GET | 重载配置 | admin |
| `/v1/admin/providers` | GET/POST/DELETE | 厂商 CRUD | admin |
| `/v1/admin/providers/` | GET/POST/PUT/DELETE | 厂商 CRUD | admin |
| `/v1/admin/routing` | GET/POST | **路由池管理** | admin |

---

## 四、关键数据流: Chat Completions

```
POST /v1/chat/completions {model, messages, max_tokens}
├─ AuthMiddleware: 检查 Bearer token ∈ api_keys[]
├─ RateLimit 检查 → 全局限制
├─ 选 Provider:
│   ├─ ?provider=X → 指定
│   ├─ getRoutingProvider() → routingPool 中有 key 的
│   └─ 兜底 → 第一个 active+key_configured
├─ mgr.Generate(ctx, providerName, req)
│   ├─ Semaphore.Acquire(ctx) → 并发控制
│   ├─ RateLimiter.Allow() → 厂商级限流
│   ├─ CircuitBreaker.Allow() → 断路器
│   ├─ p.Generate(ctx, req) → OpenAIProvider
│   │   └─ POST {base_url}/chat/completions
│   └─ cb.Record(err, latency) → 更新断路状态
├─ Cache (非 stream):
│   └─ HashKey(last_message + model) → 命中直接返回
└─ 返回 OpenAI 格式响应
```

---

## 五、发现的问题

### 5.1 P0 — 断路器 + 降级未完整

| 问题 | 文件:行 | 说明 |
|------|---------|------|
| 断路后无降级 | api.go:220-225 | `ClassifyError` + `gracefulDegradation` 存在但未实现实际的降级重试到下一厂商 |
| 路由池未集成到 generate | api.go:193 | `getRoutingProvider()` 只选一个,若失败不尝试下一个 |
| public 端点鉴权不统一 | auth.go | `/v1/admin/routing` 未加入 public_paths,需要 admin token |

### 5.2 P1 — 状态管理问题

| 问题 | 文件:行 | 说明 |
|------|---------|------|
| auto-save 每 5min 写全量 state | persistence/store.go | 覆盖已存在的 state.json |
| state.json 含空配置时可能污染 | main.go:44 | Restore 先于 Bootstrap,但写回时含快照 |
| 并发 map 未完整保护 | manager.go:61-68 | Register 中 RUnlock → Lock 之间有窗口 |

### 5.3 P2 — 功能不完整

| 问题 | 文件 | 说明 |
|------|------|------|
| 加权路由未使用 | routing.go | 整个文件实现了权重选择但从未被调用 |
| SSE 流式存在但未经测试 | stream/sse.go | StreamProvider 接口已有但 handleStream 未完整 |
| i18n 语法错误 | i18n/i18n.go:116 | `non-declaration statement outside function body` |
| Provider.Health() 未被激活调用 | openai.go | HealthCheck 探测依赖于外部调用,未内置定时 |
| 缓存无 TTL 清理策略 | cache/cache.go | 需检查 eviction 逻辑 |
| tenant.go 定价更新依赖外部 HTTP | tenant.go:150+ | SyncFromLitellm 可能因网络问题失败 |

### 5.4 P3 — 代码质量

| 问题 | 文件 | 说明 |
|------|------|------|
| `ClassifyError` 返回 hardcoded 状态 | errors.go | 错误分类逻辑简单,不同 provider 无法区分 |
| `persistProviderToYAML` 字符串替换 YAML | admin_providers.go:110 | 正则匹配脆弱,多 provider 时可能误匹配 |
| `tokenEstimate` 粗糙 | manager.go:167 | token = len(Messages.Content)/4,不考虑 model 差异 |
| `List()` 中 Active = active && hasKey | manager.go:114 | 语义模糊:active 同时表示"已注册"和"有 key" |

---

## 六、已修复 (本轮)

| # | 问题 | 修复 |
|---|------|------|
| 1 | providers[0] 不筛 active | → `getRoutingProvider()` 过滤 active+key |
| 2 | lmstudio 默认 active | → yaml `enabled: false` |
| 3 | 路由池无控制 | → `routing_pool.go` + `/v1/admin/routing` |
| 4 | auto-save 覆盖 yaml 配置 | → `restoreState` 只恢复用量,不注册 provider |
| 5 | 双 `/v1` base_url | → engine 配置改为 `:8080/v1` |

---

## 七、业务完成度

```
核心功能: ✅ chat/completions + 断路 + 限流 + 并发
管理 API: ✅ 厂商 CRUD + 路由池 + 诊断
监控:     ✅ metrics + SLO + tracing + struct log
流式:     ⚠️ 接口已定义,未通测
加权路由: ⚠️ 实现但未接入 → routing_pool 已替代
降级重试: ❌ 断路后无自动切换
```
