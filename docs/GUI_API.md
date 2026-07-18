# DialogMesh v6 — GUI API 完整业务文档 (v7 · 60 endpoints)


## 可视化交互编辑 (NEW — 白盒化)

| 端点 | 用途 | 操作 |
|------|------|------|
| `PUT /v6/edit/graph` | 编辑交互图 | update_weight / add_edge / set_node |
| `PUT /v6/edit/discourse-tree` | 编辑对话树 | reclassify / rename / merge |
| `PUT /v6/edit/objects` | 编辑语义对象 | relate / unrelate |
| `PUT /v6/edit/relations` | 编辑关系边 | update / add |
| `PUT /v6/edit/ir` | 直接编辑 IR 上下文 | 增删改 LLM 所见的中间表示 |

**所有修改自动记录到 correction_journal → 馈入 Mind 行为学习**

### PUT /v6/edit/graph
```json
{"action": "update_weight", "source": "Observer", "target": "Workspace", "weight": 0.95}
→ {"edited": "edge", "weight": 0.95}
```

### PUT /v6/edit/discourse-tree
```json
{"action": "reclassify", "block_id": "blk_a1", "temperature": "cold"}
→ {"edited": "temperature", "before": "hot", "after": "cold"}
```

### PUT /v6/edit/ir (最深白盒层)
```json
{"domain": "K", "entry_type": "user_note", "content": "ContextCompiler is the most critical module"}
→ LLM 下轮对话将看到此用户注入的上下文
```


## 业务域划分

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Gateway    │  │ Conversation │  │   Profile    │  │Visualization │
│  网关管理     │  │   对话交互   │  │   用户画像    │  │   可视化      │
│   8 APIs     │  │    2 APIs    │  │    6 APIs    │  │    7 APIs    │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Monitoring  │  │  Operations  │  │Rules/Feedback│  │  Sessions    │
│   监控面板    │  │   运维操作   │  │  规则反馈    │  │   会话管理    │
│   5 APIs     │  │   8 APIs     │  │   3 APIs     │  │   9 APIs     │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 一、Gateway — 网关管理 (8 APIs)

**业务**: 配置LLM厂商、选择模型、管理降级链、查看用量

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/gateway/providers` | 所有厂商+模型+健康状态 | 设置页-厂商卡片列表 |
| `PUT /v6/gateway/providers/{n}` | 配置API key+URL | 设置页-Key输入框+保存按钮 |
| `POST /v6/gateway/providers/{n}/test` | 连接测试 | 设置页-"测试连接"按钮 |
| `POST /v6/gateway/providers/{n}/models` | 拉取模型列表 | 设置页-"刷新模型"按钮 |
| `PUT /v6/gateway/active` | 切换当前模型 | 顶部栏-模型下拉选择器 |
| `GET /v6/gateway/config` | 网关配置+降级链 | 设置页-降级链配置 |
| `PUT /v6/gateway/config` | 修改降级/重试/超时 | 设置页-保存配置 |
| `GET /v6/gateway/usage` | Token用量+费用估算 | 底部状态栏-用量显示 |

### 前端交互流

```
打开设置 →
  GET /providers → 显示 3 个厂商卡片 (DeepSeek/LMStudio/OpenAI)
  点击 DeepSeek [配置] →
    输入 Key: sk-xxx [测试连接] → POST /test → "✅ 234ms"
    [拉取模型] → POST /models → 显示 deepseek-chat / deepseek-reasoner
    选择 deepseek-chat [设为当前] → PUT /active
  顶部栏更新: 🟢 DeepSeek / deepseek-chat
```

**持久化**: `data/gateway/providers/{name}.json` + `config.json`

---

## 二、Conversation — 对话交互 (2 APIs)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `POST /v4/event` | 发送消息,获取回复 | 聊天窗口-输入框+发送按钮 |
| `WS /v4/ws` | WebSocket实时双向流 | 聊天窗口-实时推送 |

**请求**: `{event_id, kind:"dialog.message", payload:{text, user_id}}`
**响应**: `{response, trace_hints}`

---

## 三、Profile — 用户画像 (6 APIs)

**业务**: OCEAN 10维人格分析、MBTI类型、用户纠正反馈

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/profile` | OCEAN 10维 + MBTI + BFI校准 | 画像页-雷达图+MBTI标签 |
| `PUT /v6/profile` | 用户纠正维度/MBTI | 画像页-拖拽调整+保存 |
| `GET /v6/trace` | S/W/R实时信号 | 画像页-信号指示灯 |
| `GET /v6/abc` | ABC层统计 (C/B/A命中率) | 画像页-三层堆叠图 |
| `GET /v6/mind` | Mind学习摘要 | 画像页-学习状态卡片 |
| `GET /v6/mind/full` | 心智空间全量(关系/锚点/错误) | 心智空间页-详情面板 |

**GET /v6/profile 返回**:
```json
{
  "ocean_dims": {"O":0.70,"C":0.78,"E":0.39,...},  // 10个0-1值
  "mbti": "ENTJ",                                   // 4字母类型
  "top_dimensions": ["MS","CS","NC"],                // 最显著的3维
  "bfi_latest": {"E":4,"A":3,"C":4.5,...},          // BFI-10校准
  "turn_count": 10                                   // 已分析轮数
}
```

**PUT /v6/profile 用户纠正**:
```json
{"dim": "C", "value": 0.85, "mbti": "INTJ"}
→ 写入ABC规则: source=user_feedback, confidence=0.9
```

---

## 四、Visualization — 可视化 (7 APIs)

**业务**: 图结构、对话树、概念关系、因果链

| 端点 | 用途 | 图表类型 |
|------|------|---------|
| `GET /v6/graph` | 交互图 (节点+边) | 力导向图 |
| `GET /v6/discourse-tree` | 对话树 (branch/fork) | 树形图 |
| `GET /v6/objects` | 语义对象关系图 | 概念网络图 |
| `GET /v6/relations` | 关系底物 (typed edges) | Sankey图 |
| `GET /v6/causal` | 因果依赖链 | 流程图 |
| `GET /v6/behavior` | 行为图 (触发+序列) | 时间线/序列图 |
| `GET /v6/engineering` | 工程约束+模式 | 约束面板 |

**GET /v6/relations 返回**:
```json
{"edges": [{"source":"ContextCompiler","target":"Workspace","kind":"depends_on","strength":0.85}]}
```

**GET /v6/discourse-tree 返回**:
```json
{"blocks": [{"id":"blk_a1","topic":"记忆讨论","temperature":"hot","children":["blk_b2"]}]}
```

---

## 五、Monitoring — 监控 (5 APIs)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/trace` | S/W/R实时信号 | 信号指示灯 |
| `GET /v6/abc` | ABC层命中率 | 层叠柱状图 |
| `GET /v6/pipeline` | 管道层级统计(通过率/延迟) | 管道面板 |
| `GET /v6/metrics` | 系统指标(uptime/延迟/错误) | 仪表盘 |
| `GET /v6/router` | 路由摘要 | 状态栏 |

**GET /v6/pipeline 返回**:
```json
{"tiers": {"jieba":{"pass_rate":0.85,"latency_ms":12}, "deepseek":{"pass_rate":0.92,"latency_ms":3420}}}
```

---


## Monitoring + 用户注释 (NEW)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/annotate` | 查看所有用户注释(按domain筛选) | 监控面板-注释列表 |
| `POST /v6/annotate` | 添加注释 → LLM自动深度分析 | 监控面板-"注释"按钮 |
| `GET /v6/annotate/stats` | 注释统计(domain/severity分布) | 监控面板-统计卡片 |

**POST /v6/annotate — 用户注释→LLM深度解读**:
```json
{
  "domain": "trace",
  "target": "trace.W",
  "comment": "WEAKEN一直很高,但这不像是情感冲突",
  "question": "这是分析型质疑还是情感型冲突?",
  "severity": "warn",
  "tags": ["personality", "weaken_signal"]
}
→ LLM 自动读取当前 trace/ocean/abc 数据
→ 返回: "该用户的WEAKEN来源于分析型质疑(T-type skepticism)而非情感冲突。
   证据: NC=0.75(高认知需求), MS=0.79(高元认知), A=0.41(低宜人/批判型)。
   建议: 将WEAKEN分为两个子信号: weaken_analytic vs weaken_conflict。"
→ 保存到 annotations/user_notes.jsonl
→ 馈入 correction_journal → Mind 行为学习
```


## 六、Operations — 运维 (8 APIs)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/parameters` | 全部可调参数(19+) | 参数编辑表 |
| `PUT /v6/parameters` | 修改参数值 | 参数编辑表-保存 |
| `GET /v6/context` | 最后上下文(域分配) | 上下文检查器 |
| `PUT /v6/context/config` | 调整token预算+域权重 | 上下文配置面板 |
| `GET /v6/pipeline` | 管道状态 | 管道监控 |
| `GET /v6/extraction` | 提取蓝图(4-tier) | 提取管道面板 |
| `GET /v6/perspectives` | 视角规划器 | 视角状态 |
| `GET /v6/persistence` | 持久化状态 | 系统状态 |
| `GET /v6/persistence/graphs` | 持久化图清单 | 数据管理 |

**PUT /v6/parameters**:
```json
{"key": "slow_path.event_threshold", "value": "3"}
→ {"key":"...","old":"5","new":"3","updated":true}
```

**PUT /v6/context/config**:
```json
{"token_budget": 4000, "domain_P": 0.3, "domain_C": 0.5}
→ {"updated":["budget=4000","P=0.30","C=0.50"],"count":3}
```

---

## 七、Rules & Feedback — 规则+反馈 (3 APIs)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/rules` | 规则列表(hits/misses) | 规则卡片列表 |
| `PUT /v6/rules` | 编辑规则(前提/结论/置信度) | 规则编辑器 |
| `POST /v6/feedback` | 用户点赞/踩(更新规则置信度) | 每条回复的👍👎按钮 |

**POST /v6/feedback**:
```json
{"turn":5, "correct":false, "rule_name":"personality_t_type"}
→ {"updated":true, "rule":"personality_t_type", "hit":false, "mind_updated":true}
```

---

## 八、Sessions & History (9 APIs)

| 端点 | 用途 | 前端组件 |
|------|------|---------|
| `GET /v6/sessions` | 会话列表 | 历史面板-会话列表 |
| `GET /v6/session/{f}` | 完整会话数据(每轮JSON) | 历史重放 |
| `GET /v6/router/modes` | 路由模式详情 | 路由设置 |
| `PUT /v6/router/modes` | 强制模式/禁用/预算 | 路由设置-保存 |
| `GET /v4/health` | 健康检查 | 状态栏 |
| `GET /v4/status` | 引擎统计 | 仪表盘 |
| `POST /v4/checkpoint` | 触发深度分析 | 手动触发按钮 |
| `POST /v4/ingest` | 导入文档 | 文档导入 |
| `GET /v4/inspect/{m}` | 检查模块 | 调试面板 |

---

## 业务统一流程

```
┌─────────────────────────────────────────────────────────┐
│  1. 设置网关                                             │
│  GET gateway/providers → 选厂商 → 填Key → 测试 → 选模型  │
├─────────────────────────────────────────────────────────┤
│  2. 开始对话                                             │
│  POST /v4/event → 每轮自动 profile/trace/abc/mind 更新  │
│  WS /v4/ws → 实时推送 profile_update                    │
├─────────────────────────────────────────────────────────┤
│  3. 查看分析                                             │
│  GET profile → OCEAN雷达图 + MBTI                       │
│  GET sessions → 历史列表 → GET session/{id} → 重放       │
├─────────────────────────────────────────────────────────┤
│  4. 深入探索                                             │
│  GET graph / tree / objects / relations / causal         │
│  GET mind/full → 心智空间全貌                            │
├─────────────────────────────────────────────────────────┤
│  5. 反馈改进                                             │
│  POST feedback → 点赞/踩 → 规则置信度更新                │
│  PUT profile → 纠正画像 → 写入ABC规则                    │
│  PUT rules → 手动编辑规则                                │
├─────────────────────────────────────────────────────────┤
│  6. 运维调整                                             │
│  PUT parameters → 调整阈值                               │
│  PUT context/config → 调整上下文预算                      │
│  PUT gateway/active → 切换模型                            │
└─────────────────────────────────────────────────────────┘
```
