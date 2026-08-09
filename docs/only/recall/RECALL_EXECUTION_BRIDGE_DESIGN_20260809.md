# 定位定案 + 召回→执行层桥设计（2026-08-09）

> 状态: 讨论定案, 记录待施工（v2.1）
> 触发: 用户提出"我们算通用 agent 吗？RAG 不准确, 施工需要准确性,
> 通用 agent 的召回是顺着文件树具体查阅"

---

## 一、定位定案：混合式通用 Agent

**DialogMesh = 混合式通用 AI Agent 引擎**, 不是"对话记忆引擎/上下文管理系统"。

对照（通用 agent 召回范式）:
- Codex / Claude Code / OpenClaw: **不做向量 RAG** — 对话上下文 +
  文件系统导航（glob/grep/read）+ 网络/API 直接查询
- Hermes: 同样（USER.md 事实文件 + 终端后端）
- DialogMesh: **粗召回（RAG 家族）+ 执行层精确查阅 双轨混合**:
  - 粗召回（BGE 向量 + BM25 + SPO 投影 + HyDE + 关联链 RRF 融合）
    → 负责"回忆/候选": 把可能相关的锚点拉进上下文
  - 执行层精确查阅（dir_list / grep / file_read / run_shell）
    → 负责"施工准确性": LLM 自主导航文件树, 读真实内容
  - 验证回灌: 读到的内容回灌上下文（事实校验）

## 二、About 文案（GitHub, 350 字符内）

> **自增长的通用 AI Agent 引擎** — 蓝图宏观规划 × 执行层工具调用 ×
> 元认知双向仲裁；真实工具跑通任务、成功沉淀模板；白盒可编辑、
> 决策可回看可介入。

要点: 通用 agent（非记忆引擎）/ 自增长（LLM 生成工作流+沉淀）/
白盒（决策事件流）。

## 三、召回分层设计（准确性梯度）

```
层1 粗召回（RAG 混合锚点）  — 回忆/候选: "可能相关"进上下文
        ↓ 锚点注入执行上下文
层2 执行层精确查阅          — 施工: dir_list/grep/file_read 顺文件树
        ↓ 结果回灌
层3 验证                    — 读到真实内容 → 修改 → 回灌校验
```

### 锚点注入的两条路径（2026-08-09 施工定案）

1. **图拓扑路径（主）**: 锚点是蓝图 DAG 的 subgraph 节点
   （`chain="subgraph", params.recall_anchor=True`）→ 产出
   `{"anchors", "hits"}` → 下游 agentic 工具节点经
   `data_key="anchors"` 依赖消费（白盒可见、可编辑、可删）。
2. **快速注入路径（兜底）**: v3 编码类请求直连 tool_loop 时,
   粗召回结果经 TaskRunner `anchors` 参数拼进 system_inject
   （无 DAG 拓扑时的轻量路径）。

两路径共用 `format_anchors()`（候选锚点文本, 不塞原文）。

适用场景（用户实例）:
- 修改代码: 粗召回定位候选文件 → agentic 查阅节点读具体片段 → 改
- 涉及"具体内容"的任务: 不靠向量相似度猜, 靠文件树导航读真

## 四、现状核查（2026-08-09, 诚实）

| 环节 | 现状 |
|---|---|
| 粗召回 | ✅ `/v6/recall` + `dm recall`（混合锚点 + RRF + G0 索引缓存） |
| 执行层精确查阅工具 | ✅ dir_list / grep / file_read / run_shell（tool_loop 可用, v2 实测） |
| **recall → 执行层注入** | ❌ **未接线**: recall 结果不进 tool_loop/TaskRunner 上下文 |
| 蓝图 subgraph 转查阅任务 | ❌ 未接线（api_viz_edit 有 subgraph 模式, 未接执行层） |

结论: 工具齐、串接缺。准确性的最后一公里（锚点→执行层）是 v2.1 主项。

## 五、施工建议（v2.1, 待开工）

1. ✅ **图拓扑锚点节点**: statemachine `_run_node` subgraph 分支
   支持 `params.recall_anchor=True` → 产出 `{anchors, hits}`;
   agentic 工具节点 data_key 消费（`_extract_anchors` 解包）,
   节点内自召回为兜底（`_recall_anchors` 图注入优先）
2. ✅ **快速注入**: TaskRunner `anchors` 参数（重规划循环也保留）;
   v3 Phase 4 编码请求先 `RecallService.recall` → `format_anchors`
   → 注入执行上下文
3. ✅ **format_anchors**: 候选锚点文本（来源/置信度/160 字符片段,
   max_chars/max_hits 截断, 空结果容错）
4. ⏳ **回灌校验**: 执行层读到的真实内容回灌上下文供后续节点消费
   （run_dag data_key 机制已具备, 未做专门回灌节点）
5. ✅ **开关**: 普通闲聊不召回; 编码/施工请求（is_code_request）与
   `recall_anchor` 节点才召回

## 七、施工记录（2026-08-09）

- 改动: recall_service.format_anchors（新增）/
  task_runner.run(anchors=)（新增, 重规划保留）/
  statemachine `_run_node`（subgraph recall_anchor 分支 + node_ctx
  提前 + _extract_anchors）/ v3_session_api Phase 4（recall → anchors）
- 测试: format_anchors 4 + 图拓扑 1 + 既有 18 = 23 项全绿
- 真实验证: 待服务重启后冒烟（编码请求 → 锚点注入 → 精确查阅）

## 六、关联

- 执行层架构: EXECUTION_LAYER_ARCHITECTURE_20260809（v2 已落地）
- 召回设计: SPO_MODEL_STRATEGY / SPO_BILINGUAL_TWOSTAGE /
  DYNAMIC_TIERING_PREFETCH（docs/only/recall/）
- 子图: B5-3 白盒编辑（api_viz_edit 5 端点 + GraphEditPanel）
