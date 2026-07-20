# DialogMesh v6 — 性能与安全审计

> 版本: v1.0 | 日期: 2026-07-19

---

## 一、性能瓶颈

### P0: WAL 同步写阻塞

```
当前设计: append() → sync write → fsync → return accepted
影响: 每个 Command = 1次磁盘 IO (0.1-5ms SSD, 1-10ms HDD)
      高频操作 (连续修改5个节点) → 5×5ms = 25ms 阻塞

解决:
  Group Commit: 收集 N 个 Command → 1次 fsync
  或: 内存buffer → async flush (类似 Kafka producer batch)
```

### P0: 单 Event 串行化瓶颈

```
当前: 每 Tick 只产 1 个 Event, 100ms/Tick
影响: 5个并发修改 → 500ms 才能全部处理完
      如果其中一个依赖 LLM (Async 1-5s) → 整个 Tick 卡住

解决:
  LLM Activity 不阻塞 Tick → 异步回调 → 新 Event 进入下一 Tick
  非 LLM Event (NodeEdited, ProfileDrifted) 可以批量处理:
    同 Tick 内, 如果 N 个 Event 互不冲突 → 并行 evolve
```

### P1: ShardedState 内存膨胀

```
当前: 所有 shard 在内存
影响: 1000 个对话节点 → 1000 个 shard → ~50MB
      10 个并发会话 → 500MB → OOM

解决:
  冷 Shard 换出: cold/frozen shard → 磁盘 (mmap 或 rocksdb)
  参考 Flink: RocksDB State Backend → 热数据内存, 冷数据磁盘
  HCWA 分层: Hot=内存, Warm=mmap, Cold=磁盘, Frozen=归档
```

### P1: Snapshot 缓存击穿

```
当前: Fast Path 读 _state_cache → 如果 miss → ??? 
影响: 全量重放 Event Log 构建 State → 几百个 Event → 50ms+

解决:
  Snapshot 写时复制 (Copy-on-Write):
    每 Slow Path Checkpoint → 写入 Snapshot
    Fast Path 读 Snapshot → 0ms (内存)
    miss → 回退到上一个 Snapshot + 增量 Event 重放
```

### P2: 子图编译器重复计算

```
当前: 每轮对话 → compile_dialogue 从零构建
影响: 6域查询 → 遍历对话树/工程链/行为链 → 10-20ms
      如果连续5轮同一话题 → 5×15ms = 75ms 浪费

解决:
  上下文缓存: 如果 intent 未变 + 对话树未变 → 复用上一个子图
  或: 增量更新 → 只更新变化的域 (E域变了, 其他5域不变)
```

---

## 二、安全漏洞

### P0: 零输入验证

```
当前: api.py 无任何输入验证
影响: 
  POST /v4/event: 恶意识别文本 (10MB 文本 → WAL 写入 → OOM)
  PUT /v6/edit/discourse-tree: node_id 注入 (../../etc/passwd)
  PUT /v6/profile: 维度值越界 (C=100.5, 超出 [0,1])
  POST /v6/meta/retrospect: target 路径遍历

解决:
  Pydantic 字段级验证 (每个 BaseModel 加 validators)
  文本大小限制: max_length=10000
  路径安全: 禁止 ../ 符号
  范围检查: OCEAN 维度 ∈ [0,1], parameters 有界
```

### P0: Event Log 可篡改

```
当前: JSONL 文件 append-only (理论上)
影响: 如果有文件系统访问 → 直接编辑 JSONL → 重放产生虚假 State
      没有 checksum/hash 链验证

解决:
  SHA256 链: 每个 Event 的 hash = SHA(prev_hash + event_data)
  定期 Merkle Tree 根 hash 写入不可变存储
  或: 直接使用 SQLite WAL 模式 (内置事务保证)
```

### P1: API Key 明文传输

```
当前: PUT /v6/gateway/providers → body 包含 api_key → 明文
影响: 即使 HTTPS, 日志中可能泄露 (console.log, 错误报告)

解决:
  前端发送时加密: 使用服务端公钥加密 api_key
  日志脱敏: logger 自动 mask 任何匹配 api_key 模式的行
  最小化传输: 只传输变更的字段, 不每次发完整 config
```

### P1: 无用户认证

```
当前: api.py → 无任何 auth middleware
影响: 任何人都可以:
  POST /v4/event (发送任意消息)
  PUT /v6/profile (修改画像)
  DELETE /v6/... (删除数据)

解决:
  Bearer Token 中间件 (最小可行):
    开发环境: 环境变量 AUTH_TOKEN
    生产环境: JWT + 用户系统 + 权限矩阵
  至少区分: admin / user / anonymous 三级
```

### P1: Decider 可绕过

```
当前: 无强制约束 → 代码可以直接写 _state_cache
影响: bug 或恶意代码 → 绕过 Decider → 产生不一致 State
      State 不是 Event Log 唯一投影 → Event Sourcing 承诺被打破

解决:
  State 设为只读 → 只有 Decider.evolve 有写权限
  Python 无法真正 enforce (无 private), 依赖 code review
  或: State 放在独立进程 (gRPC/REST) → 物理隔离读写
```

### P2: Signal 伪造

```
当前: Signal → Decider (无验证)
影响: 伪造的 Signal → 触发元认知审核 → 修改系统状态
      例如: 伪造 MetaVerified Signal → 强制通过错误的行为模式

解决:
  Signal 签名: 每个 Signal 携带 HMAC 签名
  Decider 验证: sender 是否合法 (元认知的 Signal key != 用户的 Signal key)
  或: Signal 必须来自 Event Log 的内部 Event → 外部无法直接发送 Signal
```

---

## 三、修复优先级

```
P0 (立即):
  ① 输入验证 (Pydantic validators)              ← 安全底线
  ② 文本大小限制 (max_length=10000)             ← 防 OOM
  ③ api_key 日志脱敏                             ← 防泄露
  ④ WAL Group Commit                             ← 性能基线
  ⑤ LLM Activity 不阻塞 Tick                     ← 性能基线

P1 (本周):
  ⑥ Bearer Token 中间件                           ← 安全
  ⑦ Event Log SHA256 链                          ← 防篡改
  ⑧ ShardedState 冷热分层                         ← 防 OOM
  ⑨ Decider 只读约束 (code review 层)             ← 防绕过

P2 (本月):
  ⑩ Signal HMAC 签名                              ← 防伪造
  ⑪ 子图上下文缓存                                 ← 性能优化
  ⑫ Snapshot Copy-on-Write                        ← 性能优化
```
