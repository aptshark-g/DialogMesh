# recall→subgraph 桥 + 生产情景溯源（2026-08-09）

> 状态: 施工完成 ✅ | 触发: 用户"召回概念后子图扩展找完整内容 +
> 情景再现（文稿 ↔ 会话要求/查的源/写的代码）"
> 关联: RECALL_EXECUTION_BRIDGE_DESIGN（粗召回→执行层桥）/
> DESIGN_SUBGRAPH（子图编译 §11 事件溯源 / §13 图扩展）

---

## 一、问题

1. recall 锚点（片段）→ 完整内容的链路: 之前只靠执行层 file_read
   （单文件原文, 精度够但无自动关联展开）
2. "情景再现": 看一份文稿, 应能找回它的生产情景——
   写文稿的会话要求 / 查过的内容 / 写的代码——而不是只有文稿本身

## 二、实现（compile_from_anchors, 三路合并）

`SubgraphCompiler.compile_from_anchors(anchors, event_id=...)`:

```
召回锚点（域 R, 带 path cross_ref = 执行层精确查阅索引）
  + 事件溯源 _expand_from_event(event_id)   → 同 trace 生产轨迹
    （会话要求/决策, 来自 EventLog, DESIGN_SUBGRAPH §11）
  + 代码轨迹 _expand_from_trace(event_id)   → 工具序列
    （写的代码/操作, 来自 learning_bridge.trace_store, 本轮新增）
  + 图扩展 expand_from_graph(query)         → ConceptGraph 关联边
    （DESIGN_SUBGRAPH §13）
  → SubgraphContext（结构化 IR, 预算裁剪, assemble_prompt/to_ir 可出）
```

生产接线: v3 Phase 4 编码/施工请求 recall 后, 锚点 + 子图上下文合并
注入 TaskRunner（anchors 参数）——执行层带着"概念 + 生产情景"工作。

## 三、"情景再现"闭环（数据都有, 链路本次补齐）

| 情景成分 | 数据源 | 链路 |
|---|---|---|
| 文稿/内容本身 | 文档/块 | recall 锚点 + path |
| 写它的会话要求 | EventLog（同 trace 事件） | _expand_from_event |
| 查过的内容/源 | EventLog payload + RecallHit.path | 同上 + 锚点索引 |
| 写的代码/操作 | ExecutionTraceStore（工具序列） | _expand_from_trace（新增） |
| 关联内容 | ConceptGraph 边 | expand_from_graph |

边界（诚实）: 事件溯源依赖 trace_id 跨模块传播完整性
（DESIGN_SUBGRAPH §11.2 已知待办）——trace 断则溯源断, 容错降级 []。

## 四、验证

- 单测 6 项（无引擎安全 / path cross_ref / event 容错 / 空锚点 /
  trace 序列命中 / trace 无匹配空）全绿
- recall 回归 18 项全绿
- 生产链路: v3 Phase 4 已接（SubgraphCompiler(engine) 无引擎降级安全）

## 五、待办（记录不施工）

- trace_id 跨模块传播（§11.2）——溯源完整性的前置
- 执行迹（/v6/execution）与子图上下文联动展示（前端阶段 B）
- compile_from_anchors 的预算裁剪策略细化（当前条目数有限, 天然可控）

## 六、端到端验证 + 质量审计（2026-08-09 晚）

### 实证（真实 LLM 会话, 非 mock）
- 会话: "写一份关于统一召回方案的简短设计文档, 保存到 data/demo_recall_doc.md"
  → LLM 自主 write_file（1.1-1.7KB 落盘）
- reconstruct 三支核查: 概念(R) 5 锚点 ✅ / 会话要求(Q) user_message
  事件原文 ✅ / 代码轨迹(T) write_file 序列 ✅ —— **三支全通**
- 修复链: trace_store 写入（TaskRunner）→ EventLog.get_event 直查（新方法,
  replay_unconsumed ASC 截断 bug）→ 显式 msg_id 事件（v3）

### 质量审计（诚实, 3 缺口）
| 缺口 | 现象 | 优先级 |
|---|---|---|
| 产出内容未索引 | write_file 的文件不在语料库, 召回锚点是对话请求而非文稿内容 | 🔴 P0 写即索引 |
| 代码轨迹无内容详情 | trace 只有工具名（write_file）, 无 path/bytes/摘要 | 🟡 P1 并执行迹 |
| 图扩展无数据源 | 引擎未装 ConceptGraph（content_index 未接线）, G 支线空 | 🟡 P2 装配 |

### P0 方案（写即索引）
write_file 成功后 → 文件内容进 chunk_store（向量+文本块）→
"产出内容可召回"的记忆闭环。

### P0 施工完成（2026-08-09 深夜）
- write_file 产出内容进 chunk_store（produced 标签, >20 字符）
- recall 冷路径合并 produced 块（atoms_by_tag + _ensure_global_blocks）
- **G0 记忆闭环**: produced 块向量现算一次 → _index_cache →
  _save_index_cache("global") 落盘 data/recall_index/ → 重启恢复
  （_load_index_cache）——跨重启记忆, 零新依赖（复用 G0 持久化）
- 实证: 语义特征词"混合锚点 RRF 融合"召回到文稿原文
- 测试: write_index 4 项（含向量持久化+二次加载恢复）+
  recall 18 回归全绿

### 待办（环境/完备性, 独立任务）
- chromadb 环境修复（.venv numpy 正常 + clash → pip 装 chromadb,
  切 unified 后端持久向量库）——存储层完备性, 不阻塞 G0 闭环
