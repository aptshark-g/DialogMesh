# DialogMesh v6 — GUI API 完整文档

## 启动

```bash
cd DialogMesh
PYTHONHOME="" PYTHONPATH="" .venv-test\Scripts\python -c "
from core.agent.v4.api import serve
serve(host='127.0.0.1', port=8000)
"
# Swagger: http://127.0.0.1:8000/docs
```

---

## 端点总览 (21个)

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v4/event` | 发送消息 |
| `WS` | `/v4/ws` | WebSocket 实时流 |

### 画像 & 状态

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/profile` | OCEAN 10维 + MBTI |
| `PUT` | `/v6/profile` | **编辑画像** (用户纠正→反馈) |
| `GET` | `/v6/trace` | S/W/R 信号 |
| `GET` | `/v6/abc` | ABC 层统计 |
| `GET` | `/v6/mind` | Mind 学习状态 |

### 可视化 (Graph/Tree/Object)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/graph` | **交互图** (节点+边) |
| `GET` | `/v6/discourse-tree` | **对话树** (branch/fork) |
| `GET` | `/v6/objects` | **语义对象图** (概念关系) |

### 规则 & 反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/rules` | **规则列表** (查看) |
| `PUT` | `/v6/rules` | **编辑规则** (前提/结论/置信度) |
| `POST` | `/v6/feedback` | **用户反馈** (正确/错误→更新规则) |

### 持久化 & 会话

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/persistence` | 持久化状态 |
| `GET` | `/v6/sessions` | 会话列表 |
| `GET` | `/v6/session/{filename}` | 会话数据 |

### 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v4/health` | 健康检查 |
| `GET` | `/v4/status` | 引擎统计 |
| `POST` | `/v4/checkpoint` | 触发深度分析 |
| `POST` | `/v4/ingest` | 导入文档 |

---

## 交互端点详解

### GET /v6/graph — 交互图可视化

```json
{
  "nodes": [
    {"id": "EventIR", "state": {}},
    {"id": "Observer", "state": {}},
    {"id": "Workspace", "state": {}}
  ],
  "edges": [
    {"source": "EventIR", "target": "Observer", "type": "DEPENDS_ON", "weight": 0.8},
    {"source": "Observer", "target": "Workspace", "type": "CAUSAL", "weight": 0.7}
  ],
  "subgraph_nodes": ["MemoryManager", "ContextCompiler", ...]
}
```

**GUI**: 力导向图 (D3/vis.js), 边粗细=weight, 颜色=type

### GET /v6/discourse-tree — 对话树

```json
{
  "blocks": [
    {
      "id": "blk_a1b2",
      "tree_id": "session-1",
      "topic": "记忆功能讨论",
      "temperature": "hot",
      "edus": 3,
      "children": ["blk_c3d4"],
      "parent": null
    }
  ],
  "total": 5
}
```

**GUI**: 树形图 (缩进/连线), hot=红色, warm=黄色, cold=蓝色

### GET /v6/objects — 语义对象

```json
{
  "nodes": [
    {"id": "ContextCompiler", "lifespan": "stable", "relations": ["depends_on"]}
  ],
  "edges": [
    {"source": "ContextCompiler", "target": "Workspace", "type": "depends_on"}
  ],
  "total_objects": 5000
}
```

**GUI**: 概念关系图, lifespan=颜色

### PUT /v6/profile — 用户纠正画像

```json
// 请求
{
  "dim": "C",
  "value": 0.85,
  "mbti": "INTJ"
}

// 响应
{
  "updated": ["C: 0.46 → 0.85"],
  "feedback": ["Rule: MBTI→INTJ (conf=0.9)"]
}
```

**行为**: 纠正后写入 ABC 规则库, 后续自动优先使用用户值。

### POST /v6/feedback — 回复评价

```json
// 请求: 标记第5轮回复错误
{
  "turn": 5,
  "correct": false,
  "rule_name": "personality_t_type"
}

// 响应
{
  "updated": true,
  "rule": "personality_t_type",
  "hit": false,
  "mind_updated": true
}
```

**行为**: 规则 confidence 下降, Mind 记录错误模式。

### GET /v6/rules — 规则浏览

```json
{
  "rules": [
    {
      "name": "personality_t_type",
      "premise": {"strengthen": {">=": 2}},
      "conclusion": {"tag": "personality_analytical"},
      "confidence": 0.5,
      "hits": 3, "misses": 1,
      "source": "manual"
    }
  ],
  "total": 6
}
```

**GUI**: 规则卡片列表, 每张显示前提→结论, hits/misses 条形图

### PUT /v6/rules — 编辑规则

```json
// 请求
{
  "name": "personality_t_type",
  "conclusion": {"tag": "personality_analytical", "threshold": 3},
  "confidence": 0.8
}
```

---

## GUI 组件映射

| GUI 组件 | API | 刷新频率 |
|----------|-----|---------|
| 聊天窗口 | POST /v4/event + WS | 实时 |
| OCEAN 雷达图 | GET /v6/profile | 每次回复后 |
| MBTI 标签 | GET /v6/profile → .mbti | 每次回复后 |
| 交互图 | GET /v6/graph | 会话开始 + 手动 |
| 对话树 | GET /v6/discourse-tree | 每5轮 |
| 语义对象图 | GET /v6/objects | 手动刷新 |
| S/W/R 指示灯 | GET /v6/trace | 每次回复后 |
| ABC 层叠图 | GET /v6/abc | 每5轮 |
| 学习曲线 | GET /v6/session/{f} | 会话结束时 |
| 规则编辑器 | GET/PUT /v6/rules | 手动 |
| 反馈按钮 (👍/👎) | POST /v6/feedback | 用户点击时 |
| 画像编辑器 | PUT /v6/profile | 用户修改时 |
| 历史面板 | GET /v6/sessions | 打开面板时 |
| 历史重放 | GET /v6/session/{f} | 选中会话时 |

---

## 用户反馈闭环

```
GUI 操作 → API → 引擎 → 持久化
───────────────────────────────
点赞/踩     → POST /v6/feedback   → ABC rule.hits/misses ±1
编辑 MBTI   → PUT /v6/profile     → 新 Rule(source=user_feedback, conf=0.9)
编辑 OCEAN  → PUT /v6/profile     → profile.dims 直接修改
编辑规则    → PUT /v6/rules       → 持久化到 neuro_symbolic_rules.json
```
