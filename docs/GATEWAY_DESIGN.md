# DialogMesh v6 — 网关 & 模型选择 业务设计

## 1. 问题诊断

当前 API 碎片化：
- `/v6/providers` 只返回当前引擎的 hardcoded provider
- `/v6/router/modes` 返回 mode 枚举但和 provider 无关
- 没有模型列表，没有 key 管理，没有配置持久化
- 前端无法完成：选厂商 → 填 key → 测连通 → 选模型 → 开始对话

## 2. 业务对象

### Provider（厂商）
```
name:          "deepseek" | "lmstudio" | "openai"
display_name:  "DeepSeek" | "LM Studio" | "OpenAI"
api_key:       "sk-xxx" (GET 时脱敏, PUT 时传入)
base_url:      "https://api.deepseek.com/v1" | "http://127.0.0.1:1234/v1"
healthy:       true | false
config_saved:  true | false (key+url 是否已持久化)
```

### Model（模型）
```
id:               "deepseek-chat" | "nvidia/nemotron-3-nano-4b"
display_name:     "DeepSeek V3" | "Nemotron Nano 4B"
provider:         "deepseek" | "lmstudio"
context_window:   128000 | 4096
max_output:       8192 | 2048
cost_per_1M_in:   0.14 | 0
cost_per_1M_out:  0.28 | 0
capabilities:     ["chat","reasoning"] | ["chat"]
```

### Gateway Config（网关配置）
```
active_provider:   "deepseek"
failover_chain:    ["deepseek", "lmstudio"]
auto_failover:     true
max_retries:       2
timeout_ms:        30000
health_check_url:  "/v1/models"
```

### Session Usage（用量）
```
provider:          "deepseek"
model:             "deepseek-chat"
turns:             10
prompt_tokens:     25000
completion_tokens: 8000
cost_estimate:     "$0.0057"
latency_avg_ms:    3420
```

## 3. 前端 → API 业务流程

```
┌─────────────────────────────────────────────────────────────┐
│                    设置页面                                  │
│                                                             │
│  [厂商下拉]  DeepSeek ▼                                     │
│  [API Key]   sk-●●●●●●●●●●●●●●●●  [测试连接] [保存]        │
│  [Base URL]  https://api.deepseek.com/v1                    │
│                                                             │
│  ┌─ 可用模型 ──────────────────────────────────────────┐   │
│  │ ○ deepseek-chat      128K  $0.14/M  延迟~3s         │   │
│  │ ○ deepseek-reasoner  64K   $0.55/M  延迟~8s         │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
│  [设为当前]  当前使用: deepseek / deepseek-chat              │
│                                                             │
│  ── 降级链 ──                                               │
│  主: deepseek  →  备: lmstudio  →  兜底: rule-only          │
│  ☑ 自动故障转移   最大重试: [2]  超时: [30s]                 │
└─────────────────────────────────────────────────────────────┘
```

## 4. API 端点设计

### 4.1 获取所有厂商 + 模型

```
GET /v6/gateway/providers

Response:
{
  "providers": [
    {
      "name": "deepseek",
      "display_name": "DeepSeek",
      "configured": true,
      "healthy": true,
      "base_url": "https://api.deepseek.com/v1",
      "models": [
        {"id": "deepseek-chat", "display": "DeepSeek V3", "context": 128000, "cost_in": 0.14, "cost_out": 0.28},
        {"id": "deepseek-reasoner", "display": "DeepSeek R1", "context": 64000, "cost_in": 0.55, "cost_out": 2.19}
      ]
    },
    {
      "name": "lmstudio",
      "display_name": "LM Studio (本地)",
      "configured": true,
      "healthy": true,
      "base_url": "http://127.0.0.1:1234/v1",
      "models": null
    },
    {
      "name": "openai",
      "display_name": "OpenAI",
      "configured": false,
      "healthy": null,
      "base_url": "https://api.openai.com/v1",
      "models": null
    }
  ],
  "active_provider": "deepseek",
  "active_model": "deepseek-chat"
}
```

### 4.2 配置厂商

```
PUT /v6/gateway/providers/{name}

Request:
{
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com/v1"
}

Response:
{
  "name": "deepseek",
  "configured": true,
  "healthy": true,
  "models_fetched": 2
}
```

### 4.3 测试连接

```
POST /v6/gateway/providers/{name}/test

Request: {} (使用已保存的配置)

Response:
{
  "name": "deepseek",
  "healthy": true,
  "latency_ms": 234,
  "models_available": 2,
  "error": null
}
```

### 4.4 拉取模型列表

```
POST /v6/gateway/providers/{name}/models

Response:
{
  "name": "deepseek",
  "models": [
    {"id": "deepseek-chat", "display": "DeepSeek V3", "context": 128000, "cost_in": 0.14, "cost_out": 0.28}
  ]
}
```

### 4.5 切换当前模型

```
PUT /v6/gateway/active

Request:
{
  "provider": "deepseek",
  "model": "deepseek-chat"
}

Response:
{
  "active_provider": "deepseek",
  "active_model": "deepseek-chat",
  "healthy": true,
  "switched_at": "2026-07-18T..."
}
```

### 4.6 网关配置

```
GET /v6/gateway/config

Response:
{
  "active_provider": "deepseek",
  "active_model": "deepseek-chat",
  "failover_chain": ["deepseek", "lmstudio"],
  "auto_failover": true,
  "max_retries": 2,
  "timeout_ms": 30000,
  "stats": {
    "deepseek": {"calls": 142, "errors": 2, "avg_latency_ms": 3420, "total_tokens": 450000},
    "lmstudio": {"calls": 0, "errors": 0, "avg_latency_ms": 0, "total_tokens": 0}
  }
}
```

```
PUT /v6/gateway/config

Request:
{
  "failover_chain": ["deepseek", "lmstudio", "openai"],
  "auto_failover": true,
  "max_retries": 3
}
```

### 4.7 用量统计

```
GET /v6/gateway/usage

Response:
{
  "current_session": {
    "provider": "deepseek", "model": "deepseek-chat",
    "turns": 10, "prompt_tokens": 25000, "completion_tokens": 8000,
    "cost_estimate": "$0.0057", "latency_avg_ms": 3420
  },
  "all_sessions": {
    "total_tokens": 450000, "total_cost": "$0.10",
    "by_provider": {
      "deepseek": {"tokens": 450000, "cost": "$0.10"}
    }
  }
}
```

## 5. 存储设计

```
data/gateway/
├── providers/
│   ├── deepseek.json    → {api_key: "encrypted?", base_url: "..."}
│   ├── lmstudio.json    → {api_key: "", base_url: "http://127.0.0.1:1234/v1"}
│   └── openai.json      → {api_key: "", base_url: "https://api.openai.com/v1"}
├── config.json          → {active_provider, active_model, failover_chain, ...}
└── models_cache/
    ├── deepseek.json    → [{id, display, context, cost}, ...]
    └── lmstudio.json    → [{id, display, context, cost}, ...]
```

## 6. 前端交互序列

```
用户打开设置:
  1. GET /v6/gateway/providers  → 显示厂商卡片列表
  2. 每个卡片: [名称] [状态灯] [配置按钮] [模型列表]

用户配置 DeepSeek:
  3. PUT /v6/gateway/providers/deepseek {api_key, base_url}
  4. POST /v6/gateway/providers/deepseek/test  → 显示 "✅ 连接成功 234ms"
  5. POST /v6/gateway/providers/deepseek/models → 显示模型列表

用户选择模型:
  6. PUT /v6/gateway/active {provider: "deepseek", model: "deepseek-chat"}
  7. 主界面顶部显示: "🟢 DeepSeek / deepseek-chat"

用户开始对话:
  8. POST /v4/event {text: "..."}
  9. 回复区域显示 + token 计数器更新
```
