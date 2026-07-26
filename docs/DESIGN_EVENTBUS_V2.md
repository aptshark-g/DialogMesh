# EventBus v2 — NATS-patterned pub/sub

> 2026-07-25 · subject路由 · queue groups · req-reply · 永不丢弃

---

## NATS 模式吸收

```
Subject routing:  "pcr.completed" → subscriber "pcr.>" 匹配
Wildcards:        "*" single token, ">" all trailing
Queue groups:     same-subject consumers → round-robin
Request-reply:    publish(inbox) → await response
```

---

## 本土化适应

```
NATS 默认:  slow consumer → drop oldest (fire-and-forget)
我们:       NEVER drop → EventLog persists → subscriber replay
            Queue full → subscriber should catch up via EventLog replay
            GC cleans old events later
```

## 核心 API

```python
bus = EventBus()

# Subscribe
sub = await bus.subscribe("pcr.>", cb=my_handler)
sub2 = await bus.subscribe("tasks.work", queue="workers")  # queue group

# Publish
await bus.publish("pcr.completed", {"zone": "MIXED"})

# Request-reply
reply = await bus.request("ping", "hello", timeout=2)

# Async iteration
async for msg in sub:
    print(msg.subject, msg.data)

# Graceful drain
await bus.drain()
```

## 集成

```
EventBus → EventLog (persist) → subscriber
         → MetaSubscriber (cold path)
         → FeedbackBridge (hot path)
```
