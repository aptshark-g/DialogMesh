# 第一版功能核对清单（2026-08-08）

> 目的: 上 GitHub 前的"功能及格线"核对 — 对标差距分级 + 端到端自检
> 依据: BENCHMARK_EXTERNAL_20260806（三款源码精读）、
> COMPLETENESS_GAP_INVENTORY（缺口）、TROUBLESHOOTING §7（自检方法）

---

## 一、对标差距分级（OpenClaw × Hermes × OpenWorker）

### 🟢 第一版必须补（"基本能力", 用户判定）
| # | 差距 | 参照(OpenWorker) | 现状（2026-08-08 复核） | 状态 |
|---|---|---|---|---|
| C1 | shell 链式命令检测 | `;`/`\|`/`$(` 等 → 强制审批 | ✅ SHELL_OPERATORS + has_shell_operators | 已实现 |
| C2 | 写路径根限制 | 多根 + writable 标志 | ✅ roots 多根 + _under_writable_root | 已实现 |
| C3 | standing rules(目标级授权) | `tool → target` 精确授权 | ✅ task_rules {tool:{targets}} | 已实现 |
| C4 | 风险分级完整性 | RiskClass 4 级 | ✅ RiskClass(read/write_local/exec/external) | 已实现 |

> 复核结论: 2026-08-06 对标后 C1-C4 已施工（permission_engine.py,
> 12/12 测试覆盖含 executor 接线）— 对标文档未同步, 现已更新。

### 📌 v2 再补（不阻塞 GitHub 第一版）
- 多渠道（WhatsApp/Telegram/Slack/Discord/Signal）— OpenClaw 强域
- 多媒体（语音/相机/屏幕）
- Hermes 7 终端后端（Docker/SSH/Modal）
- 技能活性管理（Hermes curator: active→stale→archive→prune）
- 定时自动化生命周期（OpenWorker ScheduledTask/TaskRun 持久实体）
- 记忆→技能连接（learning_graph 词法重叠边）
- 压缩反馈闭环 + 压缩质量评测

### 🟢 已领先（无需动）
- 元认知/仲裁（META_ARBITER 双向纽带, 三项目都无）
- 蓝图动态生成（DAG, 别人都是静态步骤）
- 上下文组装/压缩、存储分层（L5 四区 + EventBus 生命周期）
- 执行循环（StateMachine + ReAct + RECOVERY + 同 Tick 并行）

---

## 二、端到端功能自检（TROUBLESHOOTING §7 方法）

### E1. 服务栈
- [x] 8000 API health（/v3 /v4 health 200）
- [x] 8080 网关 health（deepseek active）
- [x] 4173 preview 可访问（5173 dev 未启, preview 覆盖）
- [ ] start.bat 一键启动全绿（不抢端口）

### E2. 核心链路（端到端）
- [x] 用户提问 → 意图识别 → 规划(DAG) → 执行(工具) → 记忆回写
  （实测: "规划JWT认证" → 完整响应含 task_graph/intent/latency 20.5s）
- [x] 二次提问能召回历史（"刚才的方案里 JWT 有效期" → 正确引用上下文,
  对话树 2 节点）
- [ ] 对话树: 图谱页真数据 + 节点详情 + 右键操作（前端 E4 项）
- [ ] 白盒编辑: api_viz_edit 5 端点 + 前端 GraphEditPanel
- [ ] 任务规划: 规划图展示 + 用户可改

### E2 续（2026-08-08）: "实现软件"链路打通
- ✅ **规划→执行**: 蓝图 tool 节点（write_file/run_python）→ Decider →
  权限门 → 真执行（实测: 写 hello.py + 运行, 文件落盘）
- ✅ OS 工具集: run_shell / run_python / run_session(后台会话) /
  dir_list / grep — os_tools.py, 11 测试
- ✅ 任务执行端点: POST /v6/task/{sid}/execute（读已确认图 → Decider,
  权限门默认挂载）
- 🔴 修 3 个接线 bug: 工具名 write_file↔file_write 不一致（注册别名+
  权限表同步）; input_schema 格式（JSON Schema → 简单 dict 兼容
  executor 校验）; ToolAdapter/ToolResult 字段
- 📌 参考落盘: OpenClaw OS 工具模式 + OpenWorker Code Agent 方法论
  （docs/only/reference/）

### E2 续2（2026-08-09）: 端到端"实现软件"实测通过
- ✅ **完整链路实测**: 用户"写 hello world 并运行" → LLM 生成 python 代码
  → v3 主流程自动执行（代码执行后处理）→ 回复追加执行结果
  （"代码执行结果 (块 1, ok) Hello World"）
- ✅ **Statemachine 执行 tool 节点**: CHAIN_TO_PHASE 缺 tool 映射 →
  `_run_node` 加 tool 分支（权限门 + ToolRegistry 执行）; 单元验证
  write_file → run_python 依赖链真执行
- ✅ **工具注册接线**: `tools/__init__.py` import builtin + os_tools
  （此前 list_all 只有 2 个工具 → 现在 13 个）
- ✅ **write_file 别名** + 权限表同步（蓝图 LLM 用 write_file,
  内置注册 file_write, 不一致 → 别名+WRITE_TOOLS 同步）
- ✅ **执行端点**: POST /v6/task/{sid}/execute（读已确认图 → Decider,
  权限门默认挂）
- 📌 根因记录: LLM_DRIVEN converge 候选路径全是认知链, LLM 不生成
  tool 节点 → 工具 DAG 执行走 Statemachine tool 分支 + 代码后处理
  （确定性）, 不依赖 LLM 生成
- 测试: os_tools 11 + permission 12 + statemachine 67 + code_postprocess 3
  = 93 绿

### E2 续3（2026-08-09）: LLM 自主工具调用（function calling）
- ✅ **tool_loop 模块**（core/agent/llm/tool_loop.py）: 注入工具 schema →
  LLM 返回 tool_calls → 权限门执行 → 结果回灌 → 循环至最终回复
- ✅ **v3 主流程接入**: 编码/实现类请求（is_code_request）走 tool_loop,
  其余走原纯文本路径（渐进, 不破坏普通对话）
- ✅ **端到端实测**: "写 hello world 并运行" → LLM 自主 write_file +
  run_shell（处理 Windows python3 占位符 → 改用 anaconda）→ 中文总结
  → 主动建议调 PATH — 真 function calling agent 行为
- ✅ 权限门: tool_loop 内 _execute_tool_call 复用 PermissionEngine
  （链式 shell / 出根目录拦截）
- 测试: tool_loop 5/5（schema 构建/执行/拦截/未知工具/意图检测）
- 📌 定位: tool_loop = **微观执行层工具引擎**（普通 ReAct 级）;
  蓝图宏观规划 + 元认知监控是"壳", 见架构讨论

### E3. 白盒（CLI + API）
- [x] `dm recall` 接线修复（entry.py 分发漏 recall → usage 错误 → 已修,
  无会话时优雅返回）; 各模块 CRUD 抽样通
- [x] `/v6/recall` 端点返回 hits + expanded + latency
  （实测: bm25 0.7 / diffusion 0.504 / vector 0.45）
- [x] 变更日志（GAP-F1）可查（/v6/changelog, 空事件正常）

### E4. 前端 13 页真数据
- [x] pages-smoke 15 项全过（Playwright, 4173 preview）
- [x] 图谱页 ReactFlow 交互 4/4（拖拽/平移/右键）
- [ ] RightDock 各 tab 真数据

### E5. 测试回归
- [x] 全量 pytest: **1856 passed / 16 skipped / 0 failed**（12min）
- [x] 前端 tsc 零错误（exit 0）+ build 成功（2.88s, 仅 chunk 大小警告）

## 三续、进度（2026-08-08）

✅ E1 服务栈 / ✅ E2 核心链路 / ✅ E5 回归(1856 绿)
✅ E3 白盒(CLI recall 修复 + /v6/recall) / ✅ E4 前端(15/15 + 4/4)
✅ C1-C4 权限（对标后已实现, 12/12 测试） / ✅ GAP-F1 变更日志 /
✅ tsc + build / ⏳ 收尾（README + 架构图 + 演示脚本 + start.bat 复核）

### 🔴 E3 核对发现真 bug（已修）
- `entry.py` main 分发分支漏 `"recall"`（dispatch 表有, 分发没接）→
  `dm recall` 报 usage 错误。已在 1216 行分支加 `"recall"`。
- `playwright.config.ts` webServer 5173 dev 启动不稳 → 改 4173 preview
  （同样配 proxy）, 测试 19/19 稳定。

---

## 三、执行顺序
1. E1 服务栈自检（最快, 立刻知道环境状态）
2. E2 核心链路（真实 LLM 一轮）
3. E5 测试回归（找预存在问题）
4. C1-C4 权限补齐（"基本能力"）
5. E3/E4 白盒 + 前端（补缺）
6. 收尾: README + 架构图 + 演示脚本
