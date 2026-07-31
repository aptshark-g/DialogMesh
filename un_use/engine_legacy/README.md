# Engine Legacy Code — 归档于 2026-07-31

## 归档原因

| 方法 | 行数 | 原因 |
|------|:---:|------|
| on_event() | ~3500 | 双轨→on_event_sm 统一入口 |
| start() | ~660 | factory + registry 替代 |
| _feed_trackb/profile/extractions | ~300 | StateMachine handlers 覆盖 |
| _update_profile_from_trace | ~400 | handle_profile 覆盖 |
| _init_* / _create_* / _instantiate_* | ~500 | factory + registry 替代 |

## 恢复方法

```
git show pre-archive:core/agent/runtime/engine.py > engine_restored.py
```

或直接复制 `engine_full.py` 回原位置。

## 验证

归档前: 28/28 CLI tests green, 195/200 v3_2 tests pass
归档后: 同上 (未改 on_event_sm 核心逻辑)
