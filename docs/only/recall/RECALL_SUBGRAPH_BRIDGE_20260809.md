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
