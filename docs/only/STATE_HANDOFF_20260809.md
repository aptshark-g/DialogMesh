# 压缩交接 — 召回探索 + OS 工具 + function calling + 第一版核对（2026-08-09）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: STATE_HANDOFF_UI_TEST_ROUND_20260807（树图化+召回第一批）
> **2026-08-09 追加: v2 执行层分层施工完成**（见 §六）— 下一步:
> ①第一版收尾（README/commit+push GitHub）或 ②前端执行迹绑定（阶段 B）

---

## 一、本轮完成（全部实测）

### 1. 统一召回第二批（黄金集 + 边界测绘）
- `data/recall_goldset.json`: 40 真实 query + 218 块（真实对话自动生成,
  非手写）; 跑分 `scripts/recall_goldset.py`
  （--mode linear|rrf|norm, --single, --scope global|session）
- **RRF 融合**: top1 42.5% vs linear 30%（+12.5pp）— 免费增益, 已接入
- **G0 索引缓存**: 磁盘持久化 SPO+向量（data/recall_index/）, 76s→15s
- **🔴 修复 2 个 vector 全 0 bug**: 语言检测过严（混合文本→384 维零向量）+
  嵌套向量（(1,512) tolist 成 [[...]]）
- **边界测绘结论**: 关系类型映射 top3/top5 +5pp（词面重叠场景有效）;
  词面不相干场景 SPO 单路 0/5（主宾语义是词典盲区）; GLiNER multi-v2.1
  对中文 SPO 无效（英文实体抽取可用）; LLM 三种用法（HyDE 扩展/挑编号/
  打分）全受粗召回天花板限制（5/7）→ **蒸馏该做"主宾语义归一"**
- 设计: SPO_MODEL_STRATEGY + SPO_BILINGUAL_TWOSTAGE + DYNAMIC_TIERING_PREFETCH
  （docs/only/recall/）

### 2. 第一版功能核对（V1_FUNCTION_CHECKLIST）
- E1 服务栈 ✅ / E2 核心链路 ✅（真实 LLM 端到端）/ E3 白盒 ✅
  （修 entry.py 漏 recall 分发）/ E4 前端 ✅（pages-smoke 15/15 + 图谱 4/4）/
  E5 回归 ✅（1856 passed 0 failed）
- C1-C4 权限: 对标后已实现（shell 操作符/写根限制/standing rules/
  RiskClass 4 级, 12/12 测试）— 复核确认并挂接生产路径（decider/gates）

### 3. OS 控制工具（参考 OpenClaw + OpenWorker 源码）
- `core/agent/tools/os_tools.py`: run_shell（平台 shell+超时+结构化）/
  run_python / run_session（后台会话 new/poll/kill/list）/
  dir_list / grep + write_file 别名 — 11 测试
- `tools/__init__.py` 接线（此前 list_all 只有 2 工具 → 13 个）
- 权限门: run_shell/run_python 归 EXEC, 链式 shell/出根目录被拒
- 参考落盘: docs/only/reference/OPENCLAW_OS_TOOLS + OPENWORKER_CODE_AGENT

### 4. 执行链路 + function calling（"实现软件"）
- Statemachine `_run_node` 加 tool 分支（权限门 + ToolRegistry）
- 代码执行后处理（检测 ```python 块自动执行）— 权宜之计
- **tool_loop**（core/agent/llm/tool_loop.py）: function calling 循环
  （注入 tools → LLM tool_calls → 权限门执行 → 回灌 → 循环）— 5 测试
- v3 主流程接入: 编码类请求（is_code_request）走 tool_loop
- **端到端实测**: "写 hello world 并运行" → LLM 自主 write_file +
  run_shell（处理 Windows python3 占位符 → 用 anaconda）→ 总结 → 主动建议
- 端点: POST /v6/task/{sid}/execute（读已确认图 → Decider）

### 5. 执行层分层架构（用户拍板）
- `docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md`
- tool_loop = 微观执行引擎（普通 ReAct 级）; 蓝图宏观约束 + 元认知树图
  监控是壳（v2 施工: 蓝图→执行接线 / 元认知监控 / 用户可见变更日志）

## 二、测试与验证
- tool_loop 5/5 + os_tools 11 + permission 12 + statemachine 67 +
  code_postprocess 3 + recall 9 + topic_tree 23 — 本批全绿
- 全量回归: 1856 passed / 16 skipped / 0 failed
- 前端: pages-smoke 15/15 + graph-interaction 4/4 + tsc 0 错误 + build OK

## 三、环境
- 8000 API ✅（新代码: tool_loop/os_tools/执行端点）/ 8080 网关 ✅
  （deepseek active）/ 4173 preview ✅
- 模型: models/gliner_multi-v2.1（1.1GB, 中文 SPO 无效, 英文实体可用）+
  models/mdeberta-v3-base（GLiNER tokenizer）
- git 未提交（按惯例）; 临时文件已清

## 四、恢复三步
1. 读本文档（终态 + 待办）
2. 读 RECOVERY_PLAN（顶部已指向本文档）
3. 下一步: ①第一版收尾（README/commit+push GitHub）或
  ②前端执行迹绑定（阶段 B）— 用户定优先级

## 六、v2 执行层分层施工（2026-08-09 追加, 完成 ✅）

- 施工记录: docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md
- 四壳补全: tool_loop 增强（allowed_tools/system_inject/on_step/timeout/
  trace）+ ExecutionMonitor（Hot/Warm/Cold 三层）+ TaskRunner（蓝图节点
  执行壳, 重规划循环 + 三层介入 + 复盘回流）+ 接线（statemachine agentic
  分支 / v3 Phase 4 任务图约束注入 / GET /v6/execution/{sid} 白盒视图）
- 验证: 新测试 22 项 + 回归 150 项全绿 + 真 LLM 端到端冒烟通过
  （LLM 自主 write_file → run_shell → 总结, 3.8s, 约束内无越界）
- 事件进 engine 决策总线 → /v6/changelog 可回看可介入（approve/reject）
- 遗留: Warm 单次 LLM 评估（P2）; 前端执行迹展示（阶段 B）

## 五、关键文档索引
- 第一版核对: docs/only/V1_FUNCTION_CHECKLIST_20260808.md
- 执行层架构: docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md
- 召回设计: docs/only/recall/（STRATEGY/BILINGUAL/DYNAMIC_TIERING）
- 蓝图薄点审计: docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md
- 参考: docs/only/reference/（OPENCLAW_OS_TOOLS + OPENWORKER_CODE_AGENT）
- 测试数据: docs/test/RECALL_GOLDSET_20260808.md
