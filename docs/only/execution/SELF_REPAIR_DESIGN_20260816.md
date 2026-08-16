# SelfRepair 设计 — 元认知自观察/自修复/自迭代（像 codex 开发自己）

> 状态: 设计定案 + 骨架落地 | 触发: 用户"元认知可以读自己的系统代码吗?
> 自修自迭代是最高的设计标准, 像我们用 codex 开发 dialogmesh, 元认知
> 做同样的事 = 极好的设想?"
> 关联: PARADIGM A10（元认知四职责）/ A11（可自我批判）/ A21（安全
> 权限只减不增）/ A24（可逆推）; AGENTS.md 铁律 3（破坏性操作可回滚）。

## 〇、判断

**认同, 且技术上已具备基础**:
- 读代码: OS 工具链（dir_list/grep/file_read/project_map）+ 召回
  （文档/代码可召回）— 已有
- 分析: AsyncDiagnoser（大环）— 已有
- 改代码: 工具链可写, 但**必须过安全 gate**（A21 权限只减不增）
- 验证: pytest 回归 — 已有
- 复盘: 诊断报告/行为链 — 已有

缺的: ①"自我"作为可读对象（系统自画像）② code_fix 修复包 + 审批
gate ③ 修复历史 → 自愈经验沉淀。本设计补这三块。

## 一、与"codex 开发 dialogmesh"的同构

| codex 开发 | 元认知自修（本设计） | 差异 |
|---|---|---|
| 读代码/文档 | SelfIntrospection（系统自画像 + 按需读文件） | 无 |
| 分析/诊断 | AsyncDiagnosis（证据+LLM 根因） | 无 |
| 改代码（审批） | SelfRepair（修复包 + 审批 gate, 默认不改） | **审批权**: codex 有人类; 自修必须有 gate |
| 测试验证 | 验证计划（pytest 回归, 通过才合入） | 无 |
| 复盘沉淀 | SelfIteration（修复历史 → 自愈经验/参数） | 无 |

安全铁律（A21/AGENTS.md）:
- **只读探索自由**（读代码/测试/文档不 gate）
- **写操作必须 gate**: 修复包默认进入待审队列, 人工/元认知确认后
  才应用; 应用前自动生成验证计划; 失败可回滚（git 分支/补丁）

## 二、SelfIntrospection（系统自画像）

模块: `core/agent/meta/introspection.py`
内容（快照落盘 data/system_profile.json + 白盒 /v6/system-profile）:
- 模块地图: core/agent 目录结构 + 各模块职责注释首行
- 测试覆盖: pytest 收集（测试文件数/用例数）+ 关键模块测试文件映射
- 变更历史: git log 最近 N 条（各模块最近修改时间 → 薄弱/活跃区）
- 已知薄弱点: 诊断报告统计（高频失败 scope）+ 执行模式（failing_tools）
- 自画像用途: 诊断/修复时作为证据注入; 元认知"认识自己"（A19 白盒）

## 三、SelfRepair（受控自修复）

诊断建议新增 action_type:
| action_type | 行为 | 风险 | 应用 |
|---|---|---|---|
| adjust_breaker/retry/budget | 调参数 | 低 | 自动（已有） |
| **code_fix** | 生成修复包（文件/修复描述/验证计划） | 高 | **gate 确认后应用** |

code_fix 修复包结构:
```json
{
  "id": "fix_xxx", "ts": ..., "source": "diagnosis.<scope>",
  "files": ["core/agent/..."], "summary": "...", "suggestion": "...",
  "verify_plan": ["pytest core/agent/... -q"], "status": "pending",
  "risk": "high", "apply_result": null
}
```
流程: diagnosis 产出 code_fix → 入修复队列（/v6/repairs, 只读可查）→
人工/元认知确认（POST /v6/repairs/{id}/apply）→ 应用前记录 git 基线
→ 执行验证计划 → 通过 → 标记 applied; 失败 → 标记 failed + 建议回滚。
**默认绝不自动应用 code_fix**（A21）; 本批实现队列+验证骨架,
apply 执行器留 P1（git 分支/补丁落地）。

## 四、SelfIteration（自迭代）

- 修复历史 + 诊断报告 + 执行模式 → 自愈经验库（data/self_repairs.jsonl）:
  {scope, root_cause, fix_summary, verify_result} — 作为未来诊断的
  RAG 证据（相似根因 → 参考既往修复, A24 可逆推）
- 参数自调节（已有 governor.self_tune）+ 修复经验 → 启发链沉淀（P2）

## 五、验收

- introspection: 自画像含模块/测试/变更/薄弱点, 落盘 + 白盒端点
- code_fix: 诊断可产出修复包入队列; 不 gate 不应用（安全默认）
- 修复队列: /v6/repairs 可查可确认; 确认后走验证计划
- 回归: 新增测试 + 230 既有全绿

## 六、落地记录（2026-08-16 追加）

### SelfIntrospection（✅）
- `core/agent/meta/introspection.py`: scan_modules（90 模块+职责注释）/
  scan_tests（174 测试文件 / ~3559 用例, 按模块分布）/ scan_git_history /
  weak_spots（诊断报告数 + 高频失败 scope）→ 快照落盘
  data/system_profile.json + `GET /v6/system-profile`
- 实测: 90 模块 / 174 测试文件 / 3559 用例 / by_module 分布（v3_2 25 /
  blueprint 20 / v4 13 ...）

### SelfRepair（✅ 队列+gate 骨架）
- diagnosis 建议新增 action_type=code_fix → 修复包入待审队列
  （files/summary/suggestion/verify_plan, 风险 high, **默认 pending**）
- `GET /v6/repairs` + `POST /v6/repairs/{id}/apply`（→ verifying + 验证
  计划）+ `POST /v6/repairs/{id}/confirm`（passed→applied / failed→
  建议回滚）; 事件进 bus（repair_applied）
- A21 安全: 不 gate 不自动应用（单测断言）

### SelfIteration（✅ 基础）
- 修复历史/诊断报告 → 自愈经验库（P1: data/self_repairs.jsonl + 诊断
  RAG 证据）; 参数自调节已有（governor.self_tune）

### 测试
- test_introspection 7 项（模块/测试扫描/快照落盘/修复队列全流程/安全
  默认）; 相关回归 237 全绿

## 七、P1 落地（2026-08-16 追加）: 真实补丁应用 + 诊断自动产出 code_fix

### 真实补丁应用（✅）
- `apply_repair`: 审批 gate → `git apply --check` 预检 → `git apply`
  → 白名单验证命令执行 → **失败 `git apply -R` 自动回滚** → 状态
  applied/failed + 全部动作进 bus（repair_applied / repair_failed_*
  rolled_back）
- **A21 安全强化**:
  - patch 必须存在（无补丁 → 拒收）
  - 验证命令白名单 `ALLOWED_VERIFY_PREFIXES`（pytest / python -m
    pytest / python -m compileall / python -c）— 防任意命令执行
  - 坏 patch 预检失败 → 还原 pending, 不落盘
- 实测（临时 git repo, 沙箱内）: 补丁应用+验证通过 / 验证失败自动回滚
  （文件还原）/ 坏 diff 拒绝 / 缺 patch 拒绝 / 白名单拦截恶意命令

### 诊断自动产出 code_fix（✅）
- DIAG_PROMPT_TEMPLATE 引导: code_fix 仅当根因是明确代码缺陷;
  params 必须含 patch（unified diff, 可被 git apply --check 接受）
  + verify_plan（白名单命令）; 不确定用 note 不编造

### 测试
- TestSelfRepairRealApply 5 项（真实 git 流程）+ 白名单/拒收 2 项;
  相关回归 242 全绿

## 八、大命题（Self-Improving Systems）

"元认知自修自迭代" = 系统把自身当作可观察/可修改对象, 且修改必须过
自己的安全门 —— 这是自我改进系统（Self-Improving Systems）研究的
核心形态, 区别于多 agent 协作（外部协作者改系统）。对内自修的优势:
- 执行记录 + 诊断报告 + 修复历史 = 完整的"自我经验"（A24 可逆推）
- 安全 gate 与验证闭环内建（不像外部 agent 需要额外沙箱编排）
- 修复可追溯可回滚（git 原生）

后续（P2）: 自愈经验库 RAG（诊断时检索既往修复）/ 修复模式沉淀为
启发链。
已实施: **自修定期巡检（无触发也主动体检, 复用 introspection 薄弱点）**
—— 2026-08-16 P1-① 落地为 `core/agent/meta/probe.py`（ProactiveHealthProbe,
见 PROACTIVE_PROBE_IMPL_20260816.md）。

## 九、加强: 贝叶斯 prior + 伪二阶抽象凝练（2026-08-16 追加）

> 用户判断（深度讨论）: 外部多 agent 修 a 是无演进的 —— bc 在自己
> 约束上下文执行, 缺 a 的真身设计约束, 只能不断测改; 元认知持有 a 的
> 约束, 才是贝叶斯共识能继续下去的根本。这与我们的设计同构:
> A13（后验喂回先验）+ 伪二阶抽象（逆推验证的凝练）。

### 落地（✅）
- **`core/agent/meta/experience.py` 自愈经验库**（贝叶斯 prior 累积）:
  JSONL 追加（scope/root_cause/fix_summary/**design_lesson**/axioms/
  verify_passed）+ search（诊断时检索相似根因作先验注入）
- **诊断注入 a 的视角**（_design_constraints）: AGENTS.md 铁律 + 追踪
  矩阵公理行 → 诊断 prompt 的"设计约束（被修系统 a 的视角, 先验）";
  既往自愈经验 → "贝叶斯 prior（相似根因参考）"
- **凝练回写（伪二阶抽象）**: 修复 applied → 生成"可逆推的设计教训"
  （scope 失败+修复+复用时先核对设计约束与测试）→ 写经验库 → 下次
  诊断检索到（后验 → 先验, 贝叶斯累积 = 演进）
- **P1-③（2026-08-16）LLM 凝练**: `DM_DIAG_LLM_LESSON=1` 开启后,
  design_lesson 由 LLM 从"scope 失败+修复+设计约束"凝练（更贴合具体
  场景, 可逆推性更强; 失败/超时降级模板）。端到端实测 1.3s, 产出如:
  "工具调用失败若源于网关拒绝, 复用时先核对连接健康与预算余量…禁止
  静默返回空, 确保可回滚可观测。"

### 测试
- test_experience 3 项（add/search 相关性/持久化重载/设计约束非空）+
  凝练回写断言; 相关回归 245 全绿

### 意义
- 多 agent 修复: 多视角观测（likelihood）无仲裁先验 → 试错无演进
- 元认知自修: 多视角证据 + a 的设计约束（prior）→ 逆推验证 → 共识
  结晶为教训 → 回写先验 → **闭环演进**（这正是"为什么先不做多 agent"）
