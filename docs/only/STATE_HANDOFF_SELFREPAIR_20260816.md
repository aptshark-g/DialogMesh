# 压缩交接 — 执行链路高可用 + 元认知治理/自修自迭代（2026-08-16）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: docs/only/STATE_HANDOFF_20260815.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN（顶部已指向）→ 读 AGENTS.md +
>  追踪矩阵 + 四个新设计文档（HA/Governor/AsyncDiagnosis/SelfRepair）
> 环境: 8000（.venv API, 本轮代码）+ 8080（网关 23796）在跑;
>  模型预加载完成; clash 7877 可出网; deepseek 直连不需要 clash

## 〇、本轮主线（用户深度讨论 + 施工）

**用户判断（架构定调）**:
1. 高可用匮乏 → 需要 AOP 横切治理模块, 属元认知子模块（此前吸收开源
   把熔断归给网关 = 归错层）
2. 纠错要更上一层 → 失误交给元认知异步诊断（第二大脑, A10 大环）
3. 元认知应能读自己代码 → 自修自迭代 = 像 codex 开发 dialogmesh,
   但**审批 gate 内建**（A21）
4. **对内自修 vs 多 agent**（本批最深的判断）: 外部多 agent 修 a 是
   无演进的 —— bc 在自己约束上下文执行, 缺 a 的真身设计约束, 只能
   不断测改; 元认知持有 a 的约束 → 才是贝叶斯共识能继续的根本。
   与设计同构: A13（后验喂回先验）+ 伪二阶抽象（逆推验证的凝练）。
   → **先不做多 agent 的架构理由**: 多 agent = likelihood 提供者,
   元认知 = prior 持有者 + 仲裁者; 共识需先有仲裁先验。

## 一、本轮完成（全部实测）

### 1. 执行链路高可用（HA_EXECUTION_ANALYSIS_20260816.md）
- 共因: 高可用只做到网关层, 执行链路各调用点独立超时串行叠加
  （180s+ 卡死实测）; LLM 调用无集中观测; async 语义漂移
- 请求级总预算: send_message 150s deadline → classify/planning/
  TaskRunner/tool_loop 传剩余（tool_loop 单轮按剩余截断, 原 90s×3=270s）
- LLM 调用观测: `call_recorder`（JSONL+窗口）+ /v6/llm-calls
  （网关挂 30s 定位 WinError 10061, 不再靠猜）
- 三个真实阻塞根治: run_dag llm_reply 双重 LLM 调用（defer_llm）/
  BehaviorBrain 同步阻塞 19s（defer_async）/ post-LLM _publish 名为
  fire-and-forget 实为同步（改后台线程）/ 通用路径 60s×3 无预算

### 2. ExecutionGovernor（EXECUTION_GOVERNOR_DESIGN_20260816.md）
- 元认知子模块 AOP 横切治理: 熔断（ScopeBreaker 三态+半开恢复）/
  错误定向重试（timeout/empty/connection/parse）/ 幂等短路 /
  治理事件进 decision_bus（kind=governor_action）+ /v6/governor
- 自调节接口: adjust(scope, **params) / adjust_retry(kind, n)
- 接入 4 调用点: tool_loop/classify/planning/llm_reply

### 3. AsyncDiagnoser（ASYNC_DIAGNOSIS_DESIGN_20260816.md, A10 大环）
- 门槛触发: breaker OPEN / 重复失败（connection 1 次立即, 其他 3 次）/
  频率门控 300s per scope
- 证据收集（breaker/llm-calls/执行树）→ LLM 根因分析 → 决策事件 +
  MetaTree + 自调节 apply（低风险自动）
- 实测: 网关挂 → 3 scope 自动触发诊断 → 报告落盘（LLM 不通降级
  stats_only）; 正常链路不误触发
- /v6/diagnosis 白盒

### 4. SelfIntrospection / SelfRepair / SelfIteration
  （SELF_REPAIR_DESIGN_20260816.md）
- introspection: 系统自画像（90 模块/174 测试文件/~3559 用例/git 历史/
  薄弱点）→ data/system_profile.json + /v6/system-profile —— 元认知
  读自己的系统（A19）
- SelfRepair P1: code_fix 修复包（patch 必带 + 白名单验证命令）→
  git apply --check → git apply → 验证 → 失败自动回滚 → 事件进 bus;
  /v6/repairs + apply/confirm
- SelfIteration: 自愈经验库 `experience.py`（贝叶斯 prior 累积）+
  诊断注入设计约束（AGENTS.md 铁律+追踪矩阵, a 的视角）+ 既往经验 +
  修复后凝练回写 design_lesson（伪二阶抽象, 后验→先验）

### 5. 顺带修复
- 诊断器惰性 get_engine 污染测试（改只 attach 已存在 engine）
- 意图分类强化（写代码/做程序 → 代码分析, 不再误判 casual）
- PlanningSkill 第二规划通道（上轮）与工具预算感知已稳定

## 二、提交状态（均本地, 未推 GitHub）

- DialogMesh: `713b27c`（PlanningSkill 接线+高可用修复）→ `dde499c`
  （Governor+AsyncDiagnoser）→ `9b8ab82`（SelfRepair/经验库, 最新）
- switch: 117aceb（此前）
- 注意: 项目根多了 `gomoku.py` + `tests/test_gomoku.py`（LLM 真实
  任务产物, 已随提交收纳; 是否需要保留待定）

## 三、环境坑（新增）

1. **API 重启后第一次 message 请求可能冷启动卡死**（Phase 1/2 懒加载
   + /v6/profile 自调用, 实测一次 170s+ 无 CPU）→ 先 GET /v6/health
   预热再发请求（warm 后 75.7s 正常）。根因深挖（Phase 1/2 预算接入）
   留待办
2. 沙箱 git 写 .git 受限 → commit 需提权
3. 沙箱进程无出网 → 网关需提权/start.bat 起（沙箱起的 API 无法调外部）
4. PowerShell 管道 GBK → 中文测试脚本必须写 UTF-8 文件再执行
5. 测试污染: AsyncDiagnoser 触发会 lazy 初始化真实 engine（已修:
   auto_attach + 只 attach 已存在）

## 四、待办（优先级）

- **P1**:
  ① 主动体检（无触发定期用 introspection 薄弱点巡检, 复用诊断器）
  ② Phase 1/2 预算接入（根治重启后首次请求卡死）
  ③ LLM 凝练 design_lesson（DM_DIAG_LLM_LESSON 开关, 当前模板凝练）
- **P2**:
  ① 自愈经验 RAG 升级（向量检索, 当前关键词）
  ② 贝叶斯概率加权（A13 P=prior+(1-prior)×likelihood 数值化）
  ③ 约束空间化（A12 合法/可达/禁止, 当前设计约束是文本摘要注入）
  ④ 诊断报告/教训落 meta 树（当前内存+总线）
  ⑤ 真实补丁应用扩展到多文件/新文件（当前 git apply 单文件 diff）
  ⑥ 执行效率: 复杂任务 6 轮探索不完（LLM 多轮 dir_list/file_read,
     doom 止损只拦同工具连续）→ 步骤级约束收紧 / 工具预算分级
  ⑦ 前端绑定: /v6/governor /v6/diagnosis /v6/repairs /v6/system-profile
  ⑧ 博客 chapter4 + 本轮"对内自修 vs 多 agent"可成博客素材

## 五、关键设计文档（本轮 4 份, 恢复必读）

- docs/only/execution/HA_EXECUTION_ANALYSIS_20260816.md（共因+预算+观测）
- docs/only/execution/EXECUTION_GOVERNOR_DESIGN_20260816.md（熔断/重试/幂等）
- docs/only/execution/ASYNC_DIAGNOSIS_DESIGN_20260816.md（大环诊断+自调节）
- docs/only/execution/SELF_REPAIR_DESIGN_20260816.md（自修自迭代+贝叶斯+
  二阶抽象）
