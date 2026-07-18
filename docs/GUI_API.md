# DialogMesh v6 — GUI API 文档

## 启动

```bash
cd DialogMesh
PYTHONHOME="" PYTHONPATH="" .venv-test\Scripts\python -c "
from core.agent.v4.api import serve
serve(host='127.0.0.1', port=8000)
"
```

启动后访问:
- Swagger UI: `http://127.0.0.1:8000/docs`
- 所有端点根路径: `http://127.0.0.1:8000`

---

## 端点总览 (13个)

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v4/event` | 发送消息,获取回复 |
| WS | `/v4/ws` | WebSocket 双向流 |

### 状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v4/health` | 健康检查 |
| GET | `/v4/status` | 引擎统计 |
| GET | `/v4/inspect/{module}` | 检查模块详情 |

### v6 画像 (新增)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/profile` | OCEAN 10维 + MBTI |
| GET | `/v6/trace` | S/W/R 信号 |
| GET | `/v6/abc` | ABC 层统计 |
| GET | `/v6/mind` | Mind 学习状态 |

### 持久化 & 会话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v6/persistence` | 持久化状态 |
| GET | `/v6/sessions` | 会话列表 |
| GET | `/v6/session/{filename}` | 会话数据 |

### 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v4/checkpoint` | 触发深度分析 |
| POST | `/v4/ingest` | 导入文档 |

---

## 核心端点的数据模型

### POST /v4/event — 对话

```json
// 请求
{
  "event_id": "msg-001",
  "kind": "dialog.message",
  "payload": {
    "text": "你觉得这个设计如何？",
    "user_id": "default",
    "session_id": "session-1"
  }
}

// 响应
{
  "response": "根据当前上下文, 这个设计...",
  "event_id": "msg-001",
  "trace_hints": {
    "obs_cost": 0.18,
    "reasoning_depth": 2
  }
}
```

### GET /v6/profile — OCEAN 10维画像

```json
{
  "ocean_dims": {
    "O": 0.70,   // Openness (0=具体, 1=抽象)
    "C": 0.78,   // Conscientiousness (0=灵活, 1=结构化)
    "E": 0.39,   // Extraversion (0=内向, 1=外向)
    "A": 0.41,   // Agreeableness (0=批判, 1=合作)
    "N": 0.34,   // Neuroticism (0=稳定, 1=敏感)
    "NC": 0.75,  // Need for Cognition (0=直觉, 1=深度分析)
    "CS": 0.78,  // Communication Style (0=叙事, 1=分析)
    "DK": 0.65,  // Domain Knowledge (0=泛化, 1=专业)
    "MS": 0.79,  // Meta-Cognition (0=任务, 1=自指)
    "CL": 0.72   // Curiosity Level (0=满足, 1=探索)
  },
  "mbti": "ENTJ",
  "turn_count": 10,
  "top_dimensions": ["MS","CS","NC","CL","O"],
  "bfi_history": 10,
  "bfi_latest": {"E":4,"A":3,"C":4.5,"N":2,"O":4}
}
```

**GUI 渲染建议**: 10维用雷达图, MBTI 用 4 字母标签, BFI 用于校准验证。

### GET /v6/trace — 实时信号

```json
{
  "reason_distribution": {
    "observe": 10,
    "activate": 10,
    "infer": 10,
    "reflect": 10,
    "strengthen": 0,
    "weaken": 0,
    "reject": 0
  },
  "avg_confidence": 0.747,
  "total": 40
}
```

**GUI 渲染建议**: S/W/R 用红绿指示灯, confidence 用进度条。

### GET /v6/abc — 神经符号层

```json
{
  "hits": 20,
  "by_layer": {"C": 0, "B": 0, "A": 20},
  "rules": {
    "total_rules": 5,
    "by_source": {"manual": 5},
    "avg_confidence": 0.5
  },
  "config_layers": {"C": true, "B": true, "A": true}
}
```

**GUI 渲染建议**: 三层堆叠图 (C/B/A), 规则数计数器。

### GET /v6/mind — 学习状态

```json
{
  "active_relations": 0,
  "active_anchors": 0,
  "active_rules": 0
}
```

### GET /v6/persistence — 持久化

```json
{
  "annotation_store": {
    "namespaces": {"rules": {"files":1,"size_kb":0}},
    "total_kb": 0,
    "version": 1,
    "write_count": 1,
    "integrity": {"total_files":1,"errors":0,"healthy":true}
  },
  "unified_store": {"indexed_objects":0,"dim":512,"cache_size":0},
  "ocean_saved": true,
  "rules_saved": true
}
```

### GET /v6/sessions — 会话列表

```json
[
  {"name": "chat_1784366450.jsonl", "size": 6042},
  {"name": "chat_1784365004.jsonl", "size": 6087}
]
```

### GET /v6/session/{filename} — 单轮数据

```json
[
  {
    "turn": 1,
    "trace_S": 0, "trace_W": 0, "trace_R": 0,
    "trace_conf": 0.725,
    "abc_hits": {"C":0,"B":0,"A":0},
    "trackB_tags": ["_ocean"],
    "ocean_dims": {"O":0.5,"C":0.78,"E":0.5,"A":0.5,"N":0.5,"NC":0.5,"CS":0.5,"DK":0.5,"MS":0.5,"CL":0.5},
    "ocean_mbti": "ISFJ",
    "bfi10_scores": {"E":3,"A":3,"C":4.5,"N":2,"O":3},
    "bfi_divergence": 0.89,
    "mind_relations": 0,
    "mind_anchors": 0
  }
  // ... 每轮一条
]
```

**GUI 渲染建议**: 
- `ocean_dims` → 10条折线图 (随时间变化)
- `ocean_mbti` → 每轮标签
- `bfi_divergence` → 校准质量线 (越低越好)
- `mind_relations/anhors` → 学习曲线

### GET /v4/health — 健康检查

```json
{
  "status": "ok",
  "engine_ready": true,
  "checks": {
    "engine": "started",
    "llm": "available",
    "bge": "loaded",
    "jieba": "ready"
  }
}
```

---

## WebSocket /v4/ws

双向流，用于实时对话 + 画像更新推送。

```
连接: ws://127.0.0.1:8000/v4/ws

发送 (JSON):
  {"type": "message", "text": "用户输入..."}
  {"type": "ping"}

接收 (JSON):
  {"type": "response", "text": "系统回复...", "turn": 5}
  {"type": "profile_update", "ocean": {...}, "mbti": "ENTJ"}
  {"type": "trace_update", "S": 0, "W": 3, "R": 0}
  {"type": "error", "message": "..."}
```

---

## GUI 典型工作流

### 新对话

```javascript
// 1. 检查健康
GET /v4/health → {status: "ok"}

// 2. 获取初始画像 (可能为空)
GET /v6/profile → {ocean_dims: {...}, mbti: "?"}

// 3. 发送消息
POST /v4/event → {response: "..."}

// 4. 刷新画像
GET /v6/profile → {mbti: "INTJ", ocean_dims: {...}}
```

### 继续对话

```javascript
// 1. 列出历史会话
GET /v6/sessions → [{name: "chat_xxx.jsonl", size: 6042}, ...]

// 2. 加载特定会话
GET /v6/session/chat_xxx.jsonl → [{turn:1, ...}, ...]

// 3. 画像已自动从跨会话持久化加载
GET /v6/profile → {turn_count: 10, mbti: "ENTJ"}
```

### 实时监控 (WebSocket)

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/v4/ws");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "profile_update") {
    updateRadarChart(msg.ocean);  // 更新雷达图
    updateMBTILabel(msg.mbti);    // 更新类型标签
  }
};
ws.send(JSON.stringify({type: "message", text: "你好"}));
```

---

## 轮询频率建议

| 端点 | 建议频率 | 理由 |
|------|---------|------|
| `/v6/profile` | 每次回复后 | OCEAN 每轮更新 |
| `/v6/trace` | 每次回复后 | 实时信号 |
| `/v6/abc` | 每5轮 | 规则积累慢 |
| `/v6/mind` | 每5轮 | 学习间隔 |
| `/v6/persistence` | 会话开始时 | 一次性检查 |
| `/v6/sessions` | 打开历史面板时 | 列表不常变 |
