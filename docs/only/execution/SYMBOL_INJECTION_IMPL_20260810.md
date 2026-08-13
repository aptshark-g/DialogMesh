# 符号注入施工记录 — 执行迹 → Mermaid 状态图（2026-08-10）

> 依据: RECALL_CROSSLINGUAL_DECISION_20260810 §三（用户拍板下一施工项）
> 参考: TencentDB Agent Memory MMD 符号注入（token -61% 实证）
> 分析: docs/only/reference/TENCENTDB_AGENT_MEMORY_ANALYSIS_20260810.md

---

## 一、施工内容

### 新增 core/agent/llm/symbol_injector.py
- `trace_to_mermaid(trace)`: 执行迹 → Mermaid 状态图
  - 每步节点 n<round>（node_id=round, 与 TaskResult.trace 对齐可追溯）
  - 边推进 + ok/err 状态 + 错误摘要
- `build_symbol_summary(trace)`: 符号摘要 = Mermaid 图 + 统计
  （已完成步骤/ok/err + 工具使用 top5）
- `compress_old_tool_rounds(msgs, trace, keep_last)`: 上下文压缩
  - 早期 (assistant+tool) 轮次 → 一条符号摘要消息（_symbol_summary 标记）
  - 保留最近 keep_last 轮原文（LLM 近期细节需要）
  - 信息不丢: trace 全量返回, node_id 可追溯

### tool_loop 集成
- 新参数: `symbol_interval`（每 N 轮压缩, 0=关默认）+ `symbol_keep_last`
- 每 N 轮调用 compress_old_tool_rounds

### TaskRunner 接线（生产路径）
- `TaskConstraint` 加 symbol_interval/symbol_keep_last 字段（A18 可调）
- run() 传给 tool_loop

## 二、设计要点（注入侧结构化）

- 检索侧结构化（文本→SPO/块→混合锚点）已有; 本模块补**注入侧**:
  工具输出流 → 符号图注入上下文, 原文 offload 到 trace
- 与"蓝图=任务地图"呼应: 执行时任务状态符号图注入, 非逐轮原文堆砌
- 默认关闭（symbol_interval=0 不改变既有行为）, 渐进启用

## 三、验证

- 新增 test_symbol_injector.py 5 项: 图生成/统计/压缩保留最近轮/空迹 noop/空摘要
- tool_loop 测试适配 mock 签名（+symbol_interval/keep_last）
- 端到端（真实 LLM）: 写文件→读→运行 3 步, 符号图正确生成
  （file_write→file_read→run_shell, Mermaid graph LR + 统计）
- 回归: llm 17/17 + learning_bridge 12/12 + statemachine_m4 13/13 = 42 全绿

## 四、开放问题（下一轮）

1. 提炼器升级: 当前规则提炼（trace 结构→图）; 可选 LLM 提炼
   （状态转换语义, 更紧凑但每次调用成本）
2. 注入时机: 当前固定间隔; 可加 token 阈值触发（超预算才压缩）
3. 原文 offload 位置: 当前 trace 内存返回; 可落盘 refs/ 目录
   （跨重启保留, TencentDB refs/*.md 同款）
4. 统一提炼调度层: 符号注入是"执行产出→提炼→分发"框架的第一实例;
   后续画像/蓝图自增长/行为链共用调度（设计记录在 RECALL_CROSSLINGUAL_DECISION）
