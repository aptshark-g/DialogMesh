# DialogMesh v6 — GUI API 完整业务文档 (v9 · 82 endpoints)

> 版本: v9 | 日期: 2026-07-19
> 包含: DialogMesh 74 端点 + switch gateway 8 端点

---

## 端点速查表

### 对话 (2)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v4/event` | 发送消息 |
| WS | `/v4/ws` | WebSocket 实时流 |

### 画像 & 信号 (8)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/profile` | OCEAN 10维 + MBTI |
| PUT | `/v6/profile` | 用户纠正画像 → 修正日志 |
| GET | `/v6/profile/corrections` | 修正历史 (before/after) |
| POST | `/v6/profile/corrections/review` | LLM 回顾漂移 |
| GET | `/v6/trace` | S/W/R 信号 |
| GET | `/v6/abc` | ABC 层统计 |
| GET | `/v6/mind` | Mind 摘要 |
| GET | `/v6/mind/full` | 心智空间全量 |

### 元认知 (4)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/meta/stats` | 元认知状态 (队列/准确率) |
| GET | `/v6/meta/queue` | 审核队列 |
| POST | `/v6/meta/scan` | 触发主动扫描 |
| POST | `/v6/meta/retrospect` | 手动复盘报告 |

### Git 版本控制 (2)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/versions/{category}?target=` | 版本历史 (8类数据) |
| POST | `/v6/versions/{category}/rollback` | 回滚到历史版本 |

### 惯性权重图 (1)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/inertia` | 惯性模式状态 |

### 行为发现 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/behavior/patterns` | 发现的行为模式 |
| POST | `/v6/behavior/feedback` | 用户 ✓/✗ 反馈 |
| GET | `/v6/behavior/predict` | 手动触发行为预测 |

### L2.5 信念 (1)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/belief?session_id=` | 贝叶斯信念累积器状态 |

### 子图 (1)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/subgraph/{perspective}` | 编译后子图 (dialogue/meta) |

### OCEAN→参数 (1)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v6/ocean/params` | 画像→参数自动映射 |

### 工程链 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/recursive-map` | 递归地图状态 |
| PUT | `/v6/recursive-map` | 展开/折叠节点 |
| GET | `/v6/engineering/modules` | 工程模块+约束列表 |
| PUT | `/v6/engineering/constraints` | 编辑工程约束 |

### 可视化 (7)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/graph` | 交互图 |
| GET | `/v6/discourse-tree` | 对话树 |
| GET | `/v6/objects` | 语义对象图 |
| GET | `/v6/relations` | 关系底物 |
| GET | `/v6/causal` | 因果链 |
| GET | `/v6/behavior` | 行为图 |
| GET | `/v6/engineering` | 工程约束 |

### 可视化编辑 (5)
| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/v6/edit/graph` | 编辑交互图 |
| PUT | `/v6/edit/discourse-tree` | 编辑对话树 |
| PUT | `/v6/edit/objects` | 编辑语义对象 |
| PUT | `/v6/edit/relations` | 编辑关系边 |
| PUT | `/v6/edit/ir` | 编辑 IR 上下文 |

### 规则 & 反馈 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/rules` | 规则列表 |
| PUT | `/v6/rules` | 编辑规则 |
| POST | `/v6/feedback` | 用户反馈 (✓/✗) |

### 注释 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/annotate` | 用户注释列表 |
| POST | `/v6/annotate` | 添加注释 → LLM深度分析 |
| GET | `/v6/annotate/stats` | 注释统计 |

### 会话 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/sessions` | 会话列表 |
| GET | `/v6/session/{f}` | 会话数据 |
| POST | `/v4/ingest` | 导入文档 |

### 网关 (Python) (11)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/gateway/providers` | 厂商列表 (代理 switch) |
| PUT | `/v6/gateway/providers/{n}` | 配置厂商 |
| POST | `/v6/gateway/providers/{n}/test` | 连接测试 |
| POST | `/v6/gateway/providers/{n}/models` | 拉取模型 |
| PUT | `/v6/gateway/active` | 切换模型 |
| GET | `/v6/gateway/config` | 网关配置 |
| PUT | `/v6/gateway/config` | 修改配置 |
| GET | `/v6/gateway/usage` | Token 用量 |
| GET | `/v6/gateway/stats` | 代理 switch metrics |
| GET | `/v6/gateway/health` | 代理 switch health |
| POST | `/v6/gateway/reload` | 代理 switch reload |

### 运维 (8)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/parameters` | 全部可调参数 |
| PUT | `/v6/parameters` | 修改参数 |
| GET | `/v6/context` | 最后上下文 |
| PUT | `/v6/context/config` | 调整上下文预算+域权重 |
| GET | `/v6/pipeline` | 管道层级统计 |
| GET | `/v6/extraction` | 提取蓝图 |
| GET | `/v6/perspectives` | 视角规划器 |
| GET | `/v6/router/modes` | 路由模式+复杂度+降级链 |
| PUT | `/v6/router/modes` | 强制模式/禁用/预算 |
| GET | `/v6/provider` / PUT | LLM provider 切换 |
| GET | `/v6/provider/tokens` | Token 消耗 |
| POST | `/v6/provider/test` | 连接测试 |
| GET | `/v6/metrics` | 系统指标 |

### 持久化 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/persistence` | 持久化状态 |
| GET | `/v6/persistence/graphs` | 图数据清单 |

### 管理 (4)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v4/health` | 健康检查 |
| GET | `/v4/status` | 引擎统计 |
| POST | `/v4/checkpoint` | 触发深度分析 |
| GET | `/v4/inspect/{m}` | 检查模块 |

---

## switch Gateway 前端 API (独立端口 :8080)

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|:---:|------|
| GET | `/v1/health` | 无 | 网关健康 |
| GET | `/v1/health/detail` | 无 | 详细健康 |
| GET | `/v1/metrics` | 无 | Prometheus 指标 |
| GET | `/v1/stats` | 无 | 用量快照 |
| GET | `/v1/providers` | 客户端 Key | 供应商列表 |
| GET | `/v1/usage` | 客户端 Key | Token 用量 |
| POST | `/v1/chat/completions` | 客户端 Key | LLM 调用入口 |
| GET | `/v1/admin/providers` | Admin | 查看/添加供应商 |
| DELETE | `/v1/admin/providers/{n}` | Admin | 删除供应商 |
| POST | `/v1/admin/reload` | Admin | 热重载配置 |
| GET | `/v1/diagnostics` | Admin | 诊断信息 |

---

## 新增端点详解

### GET /v6/meta/stats
```json
{
  "queue_size": 5, "pending": 3, "reviewed": 2,
  "decisions_total": 42,
  "self_audit": {"accuracy": 0.85, "by_verdict": {"approved": 30, "rejected": 8, "escalate": 4}}
}
```

### GET /v6/versions/{category}?target=profile.C
```json
{
  "target": "profile.C",
  "commits": [
    {"id": "a1b2c3d4", "ts": 1784365000, "author": "user",
     "before": "0.46", "after": "0.85", "reason": "user_edit", "verify": "verified"}
  ]
}
```

### GET /v6/inertia
```json
{
  "total_patterns": 3, "stable": 1, "confirmed": 1, "breaking": 0,
  "by_weight": {"quality_centric": 0.92, "whitebox_pref": 0.88},
  "constraints": ["回复必须含量化指标", "参数修改路径必须可视化"]
}
```

### GET /v6/behavior/patterns
```json
{
  "patterns": [
    {"trigger": "write_code", "predicted": "add_test", "confidence": 0.85, "support": 4, "verdict": "approved"}
  ],
  "stats": {"total_patterns": 2, "user_approved": 1}
}
```
