# DialogMesh v6 — GUI API 完整文档 (v5 · 42 endpoints)

## 启动
```bash
PYTHONHOME="" PYTHONPATH="" .venv-test\Scripts\python -c "from core.agent.v4.api import serve; serve()"
# Swagger: http://127.0.0.1:8000/docs
```

---

## 端点速查表

### 对话 (2)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v4/event` | 发送消息 |
| WS | `/v4/ws` | 实时流 |

### 画像 & 信号 (6)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/profile` | OCEAN 10维 + MBTI |
| PUT | `/v6/profile` | 用户纠正画像 |
| GET | `/v6/trace` | S/W/R 信号 |
| GET | `/v6/abc` | ABC 层统计 |
| GET | `/v6/mind` | Mind 摘要 |
| GET | `/v6/mind/full` | 心智空间全量 |

### 图/树/对象 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/graph` | 交互图 |
| GET | `/v6/discourse-tree` | 对话树 |
| GET | `/v6/objects` | 语义对象图 |

### 深层链 (4)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/relations` | 关系底物 |
| GET | `/v6/causal` | 因果链 |
| GET | `/v6/behavior` | 行为图 |
| GET | `/v6/engineering` | 工程约束 |

### 规则 & 反馈 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/rules` | 规则列表 |
| PUT | `/v6/rules` | 编辑规则 |
| POST | `/v6/feedback` | 用户反馈 |

### 会话 (3)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/sessions` | 会话列表 |
| GET | `/v6/session/{f}` | 会话数据 |
| POST | `/v4/ingest` | 导入文档 |

### 提供商 & 运维 (6) ← NEW
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/providers` | 提供商列表+健康+降级链 |
| PUT | `/v6/providers` | 切换provider/model/key |
| GET | `/v6/providers/tokens` | Token消耗 |
| POST | `/v6/providers/test` | 连接测试 |
| GET | `/v6/metrics` | 系统指标 |
| PUT | `/v6/context/config` | 上下文调整 |

### 路由/Switch (2) ← REWRITTEN
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/router/modes` | 3模式+复杂度+降级链+统计 |
| PUT | `/v6/router/modes` | 强制模式/禁用模型/预算 |

### 业务管道 (6)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/pipeline` | 管道层级统计 |
| GET | `/v6/extraction` | 提取蓝图 |
| GET | `/v6/perspectives` | 视角规划器 |
| GET | `/v6/parameters` | 全部可调参数 |
| PUT | `/v6/parameters` | 修改参数 |
| GET | `/v6/context` | 最后组装上下文 |

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

## 路由/Switch 详解

### GET /v6/router/modes
```json
{
  "available": true,
  "modes": [
    {"name": "rule", "complexity": "0-3", "cost": "free", "latency": "<1ms"},
    {"name": "small_model", "complexity": "4-7", "cost": "free", "latency": "~20-100ms"},
    {"name": "remote_llm", "complexity": "8-10", "cost": "API", "latency": "~200ms-2s"}
  ],
  "active": "remote_llm",
  "force_mode": null,
  "disabled": {"remote": false, "small_model": false},
  "cost_budget": "standard",
  "route_stats": {"rule": 0, "small_model": 0, "remote_llm": 42, "fallback": 0},
  "complexity": {"evaluator_available": true, "last_score": null},
  "degradation_chain": ["remote_llm → small_model → rule (自动降级)"]
}
```
**GUI**: 三级模式选择器 radio buttons, 实时路由统计柱状图

### PUT /v6/router/modes
```json
{"mode": "small_model", "disable_remote": false, "cost_budget": "free"}
→ {"updated": ["mode=small_model", "budget=free"], "count": 2}
```

---

## 提供商详解

### GET /v6/providers
```json
{
  "active": {"name": "deepseek", "model": "deepseek-chat", "healthy": true, "stats": {...}},
  "failover": {"primary": "deepseek", "fallback": "lmstudio", "active_idx": 0, "failures": 0}
}
```

### PUT /v6/providers — 切换
```json
{"provider": "lmstudio", "base_url": "http://127.0.0.1:1234/v1", "model": "nvidia/nemotron-3-nano-4b"}
→ {"switched": "lmstudio", "model": "nvidia/nemotron-3-nano-4b", "healthy": true}
```

### GET /v6/providers/tokens
```json
{"current": {"turns": 10, "est_tokens": 35000},
 "all_sessions": {"count": 5, "est_tokens": 175000},
 "rate": {"deepseek": "$0.14/M in, $0.28/M out"}}
```

---

## 上下文调整详解

### PUT /v6/context/config
```json
{"token_budget": 4000, "domain_P": 0.3, "domain_C": 0.5, "domain_K": 0.2}
→ {"updated": ["budget=4000", "P=0.30", "C=0.50", "K=0.20"], "count": 4}
```
