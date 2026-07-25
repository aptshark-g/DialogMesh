# Guard System — 背压控制 + 级联检测 + 断路保护

> 2026-07-25 · P0基础设施 · 保护管线过载

---

## 一、架构

```
RequestGuard (统一入口)
  ├── TokenBucket × 9       每阶段独立限流
  ├── CascadeDetector        级联故障检测
  └── CircuitBreaker × 9     每阶段独立断路

管线钩子:
  agent_native.process() 每阶段:
    guard.enter(stage) → 通过/拒绝
    ...执行...
    guard.exit(stage, success, latency_ms)
```

---

## 二、TokenBucket

限流机制：恒定速率补充令牌，突发请求消耗令牌。

```
每阶段默认速率:
  compass: 200/s   llm_plan: 10/s
  pcr:     200/s   llm_answer: 10/s
  intent:  150/s   execution: 20/s
  l4:      150/s   plan_gate: 50/s
  context: 100/s

Burst = rate / 5 (最大突发)
超出 → 拒绝 (返回 False), 不进入该阶段
```

---

## 三、CascadeDetector

级联检测：A故障 → B开始慢 → C被阻塞。

```
5级健康状态:
  OK → SLOW (>2s) → DEGRADED (>5s) → FAILING (5次连续失败) → CRITICAL (10次)

检测逻辑:
  1. 每阶段记录 success/failure + latency (EMA)
  2. 发现 FAILING/CRITICAL → 按连续失败次数排序
  3. 最深的是根因 (root_cause)
  4. 返回级联链: [根因阶段, 传播阶段1, 传播阶段2]

输出:
  { detected: true, root_cause: "execution",
    chain: ["execution", "llm_answer"], stages: {...} }
```

---

## 四、CircuitBreaker

断路保护：重复失败 → 自动断开 → 冷却后重试。

```
状态机:
  CLOSED → (5次失败) → OPEN (拒绝所有)
  OPEN   → (30s冷却)  → HALF_OPEN (允许2个测试请求)
  HALF_OPEN → 成功    → CLOSED (恢复)
  HALF_OPEN → 失败    → OPEN (重新断开)

每阶段独立断路 — 一个阶段断开不影响其他阶段
```

---

## 五、接入方式

```python
from core.agent.monitor.guard import RequestGuard

guard = RequestGuard()

# Pipeline hook
if guard.enter("compass"):
    try:
        # ... stage work ...
        guard.exit("compass", success=True, latency_ms=12.5)
    except:
        guard.exit("compass", success=False, latency_ms=0)

# Check periodically
cascade = guard.check_cascade()
if cascade:
    logger.warning(f"Cascade detected: {cascade['root_cause']}")

# Stats
stats = guard.stats()  # buckets, circuits, cascade
```
