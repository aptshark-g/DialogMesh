# DialogMesh v6 — GUI API 完整文档 (v3)

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

## 端点总览 (29个)

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v4/event` | 发送消息 |
| `WS` | `/v4/ws` | WebSocket 实时流 |

### 画像 & 信号
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/profile` | OCEAN 10维 + MBTI |
| `PUT` | `/v6/profile` | 编辑画像 (用户纠正→反馈) |
| `GET` | `/v6/trace` | S/W/R 信号 |
| `GET` | `/v6/abc` | ABC 层统计 |

### 可视化: 图/树/对象
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/graph` | 交互图 (节点+边) |
| `GET` | `/v6/discourse-tree` | 对话树 (branch/fork) |
| `GET` | `/v6/objects` | 语义对象图 (概念关系) |

### 可视化: 深层链/图 (新增)
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/relations` | **关系底物** (typed edges: depends_on/causal/...) |
| `GET` | `/v6/causal` | **因果链** (causal substrate chains) |
| `GET` | `/v6/behavior` | **行为图** (behavioral edges + stats) |
| `GET` | `/v6/engineering` | **工程链** (constraints + patterns) |

### Mind & 路由
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/mind` | Mind 统计摘要 |
| `GET` | `/v6/mind/full` | **心智空间全量** (relations/anchors/mistakes) |
| `GET` | `/v6/router` | **Switch 路由状态** |

### 规则 & 反馈
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/rules` | 规则列表 |
| `PUT` | `/v6/rules` | 编辑规则 |
| `POST` | `/v6/feedback` | 用户反馈 (✓/✗→更新规则) |

### 持久化 & 会话
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v6/persistence` | 持久化状态 |
| `GET` | `/v6/persistence/graphs` | **已持久化图数据清单** |
| `GET` | `/v6/sessions` | 会话列表 |
| `GET` | `/v6/session/{f}` | 会话数据 |

### 管理
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v4/health` | 健康检查 |
| `GET` | `/v4/status` | 引擎统计 |
| `POST` | `/v4/checkpoint` | 触发深度分析 |
| `POST` | `/v4/ingest` | 导入文档 |

---

## 深层链/图端点详解

### GET /v6/relations — 关系底物

```json
{
  "edges": [
    {
      "source": "ContextCompiler",
      "target": "Workspace",
      "kind": "depends_on",
      "strength": 0.85,
      "evidence": "from heading hierarchy"
    }
  ],
  "total": 512
}
```
**GUI**: Sankey 图, 边粗细=strength, 颜色=kind

### GET /v6/causal — 因果链

```json
{
  "chains": [
    {"key": "Observer→Workspace→ReasoningTree", "weight": 0.72}
  ],
  "total": 24
}
```
**GUI**: 因果链条, 横向流程图

### GET /v6/behavior — 行为图

```json
{
  "edges": [{"source": "user_query", "target": "Observer", "type": "trigger", "weight": 0.9}],
  "nodes": 15,
  "stats": {"cold_starts": 3, "corrections": 1}
}
```
**GUI**: 行为序列时间线

### GET /v6/engineering — 工程知识图

```json
{
  "constraints": [{"name": "token_limit_4096", "type": "constraint"}],
  "patterns": [{"name": "observer_pattern", "type": "pattern"}]
}
```

### GET /v6/mind/full — 心智空间

```json
{
  "stats": {"active_relations": 3, "active_anchors": 2, "active_rules": 1},
  "relations": {"Observer→Workspace": {"confidence": 0.85}},
  "anchors": {"architecture": {"weight": 0.72}},
  "mistakes": ["turn_5: user_correction"]
}
```

### GET /v6/router — Switch 状态

```json
{
  "active_mode": "ANALYTICAL",
  "stats": {"mode_switches": 3, "current_confidence": 0.8}
}
```

---



## 业务逻辑端点 (新增)

### GET /v6/pipeline — 处理管道

```json
{
  "tiers": {
    "jieba": {"available": true, "pass_rate": 0.85, "correction_rate": 2, "avg_latency_ms": 12.3},
    "deepseek": {"level": 4, "pass_rate": 0.92, "correction_rate": 0, "avg_latency_ms": 3420.0}
  }
}
```
**GUI**: 管道状态面板, 每层通过率/延迟条, 红色=高修正率

### GET /v6/extraction — 提取蓝图

```json
{
  "providers": [{"name": "jieba", "available": true}, {"name": "deepseek", "available": true}],
  "last_result": {"definitions": 3, "relations": 2, "concepts": ["Observer", "Workspace"]}
}
```

### GET /v6/perspectives — 视角规划器

```json
{
  "perspectives": [{"name": "ARCHITECTURE", "horizon": "depth=2 budget=1800", "targets": ["ContextCompiler"]}],
  "active_view": {"depth": 2, "visible": ["ContextCompiler", "SemanticPath"]}
}
```

### GET /v6/parameters — 可调参数 (ALL)

```json
{
  "params": {"slow_path.event_threshold": 5, "relation.min_confidence_edge": 0.15, ...},
  "total": 19
}
```
**GUI**: 参数编辑表 — 每行可编辑, PUT 保存

### PUT /v6/parameters — 修改参数

```json
{"key": "slow_path.event_threshold", "value": "3"}
→ {"key": "...", "old": "5", "new": "3", "updated": true}
```

### GET /v6/router/modes — 完整路由

```json
{
  "modes": ["ANALYTICAL", "CREATIVE", "FAST", "DEEP"],
  "active": "ANALYTICAL",
  "history": ["ANALYTICAL", "ANALYTICAL", "DEEP"],
  "stats": {"mode_switches": 3}
}
```
**GUI**: 模式选择器 dropdown, 历史折线图

### PUT /v6/router/modes — 强制模式

```json
{"mode": "DEEP"}
→ {"active": "DEEP", "overridden": true}
```

### GET /v6/context — 最后组装的上下文

```json
{
  "entries": {"k1": {"domain": "P", "type": "cognitive_profile", "confidence": 0.7}},
  "domains": {"P": 0.6, "C": 0.4},
  "total_entries": 12
}
```
**GUI**: 上下文检查器 — 每个 domain 的颜色块, 大小=token 分配

## GUI 组件映射 (更新)

| GUI 组件 | API | 频率 |
|----------|-----|------|
| 聊天窗口 | POST /v4/event + WS | 实时 |
| OCEAN 雷达图 | GET /v6/profile | 每次回复后 |
| MBTI 标签 | GET /v6/profile | 每次回复后 |
| 交互图 | GET /v6/graph | 启动+手动 |
| 对话树 | GET /v6/discourse-tree | 每5轮 |
| 语义对象图 | GET /v6/objects | 手动 |
| **关系底物图** | GET /v6/relations | 手动 |
| **因果链图** | GET /v6/causal | 手动 |
| **行为序列图** | GET /v6/behavior | 手动 |
| **工程约束面板** | GET /v6/engineering | 手动 |
| **心智空间面板** | GET /v6/mind/full | 每5轮 |
| **路由状态** | GET /v6/router | 手动 |
| S/W/R 指示灯 | GET /v6/trace | 每次回复后 |
| ABC 层叠图 | GET /v6/abc | 每5轮 |
| 学习曲线 | GET /v6/session/{f} | 会话结束时 |
| 规则编辑器 | GET/PUT /v6/rules | 手动 |
| 反馈按钮 | POST /v6/feedback | 用户点击时 |
| 画像编辑器 | PUT /v6/profile | 用户修改时 |
| 历史面板 | GET /v6/sessions | 打开时 |
| 持久化状态 | GET /v6/persistence/graphs | 启动时 |
