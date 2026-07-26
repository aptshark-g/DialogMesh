# Gateway v2 — pingora-patterned 多provider代理

> 2026-07-25 · 7阶段管线 · 连接池 · failover · provider.yaml

---

## pingora 模式吸收

```
Phase pipeline:  request_filter→upstream_peer→send_req→response_filter→log→error
Connection pool: per-provider keep-alive, idle_timeout, max_idle
Failover:        provider A fails → try B → try C (max 3)
Health check:    passive failure counting + active probing
Rate limiter:    per-provider TokenBucket (via Guard)
```

---

## 7 阶段管线

```
1. request_filter   validate, sanitize, rate limit check
2. upstream_peer     select provider (weighted + health)
3. connected         connection pool get/create (Bulkhead)
4. send_request      proxy to provider (aiohttp / urllib)
5. response_filter   add _provider, _model metadata
6. log               record metrics
7. error             failover → retry next provider
```

## Provider 选择

```
provider.yaml → 9 providers → dynamic routing
Priority: preferred → weighted by health → fallback
Health: success_rate EMA + latency EMA
Bulkhead: max_active=10 per provider
```

## 接入

```python
gw = GatewayV2("gateway/provider.yaml", guard=guard, event_bus=bus)

result = await gw.proxy(
    method="POST", path="/chat/completions",
    body={"model": "deepseek-chat", "messages": [...]},
    provider_name="deepseek",
    fallback=True,
)
```
