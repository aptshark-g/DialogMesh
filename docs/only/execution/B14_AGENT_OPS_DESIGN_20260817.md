# B14 元认知代操作协议 — NL → 规划 → 审批 → 受控操作（像委托 codex 干活）

> 状态: 设计定案（2026-08-17）| 触发: UI_REFACTOR_PLAN B14
> （万能搜索栏"帮我操作"用法）+ 用户"元认知代操作协议: 自然语言指令 →
> 元认知规划 → GUI/系统操作（经 checkpoint 审批）"
> 关联: PARADIGM A10（元认知协同）/ A11（可回溯可修正）/ A16（不阻断）/
> A19（白盒操作必记录）/ A21（权限只减不增）/ A24（可逆推）;
> AGENTS.md 铁律 3（破坏性操作必须可回滚）; 复用 SELF_REPAIR 审批 gate 模式。

## 〇、判断

**可行, 且与 SelfRepair 同构但范围更大**:

| 维度 | SelfRepair（已落地） | B14 代操作（本设计） |
|---|---|---|
| 对象 | 自己（系统代码/参数） | 用户委托的任意 GUI/系统操作 |
| 触发 | 诊断报告自动产出修复包 | 用户自然语言显式委托 |
| 计划 | code_fix 修复包 | 多步操作计划（步骤 = 工具/参数/预期） |
| 审批 | /v6/repairs gate | checkpoint 审批（批准/调整/拒绝） |
| 执行 | apply 执行器（P1） | 受控执行器（复用 ExecutionGovernor） |
| 验证 | 验证计划（pytest） | 每步白名单验证 + 最终结果确认 |
| 沉淀 | 自愈经验库（贝叶斯 prior） | 操作经验库（同构复用） |

关键差异: SelfRepair 是"元认知修自己", B14 是"元认知替用户干活"——
因此 **B14 的审批权更高、每步必须可回滚、执行边界受权限门约束**。

## 一、协议总览

```
用户 NL 指令（"帮我…"）
   │
   ▼
1. 意图判定（LLM + 启发式）—— 是"代操作"还是普通对话/检索?
   │（普通意图 → 走既有管线, 不进 B14）
   ▼
2. 规划（LLM 生成操作计划, 结构化为步骤序列）
   │ 每步: 目标 / 工具 / 参数 / 预期结果 / 风险 / 回滚方式
   ▼
3. checkpoint 审批（User-In-Loop, A16 不阻断）
   │ approved / adjusted（改参数或删步骤）/ rejected
   ▼
4. 受控执行（ExecutionGovernor 逐 step: 熔断/超时/幂等）
   │ 每步执行前白名单校验（A21 权限门）
   │ 每步执行后记录 + 验证（A17 记录, 失败定向重试）
   ▼
5. 结果汇总 + 回滚（任一步失败可回滚到操作前基线）
   │
   ▼
6. 经验沉淀（操作历史 → 操作经验库, 贝叶斯 prior 供下次规划参考）
```

## 二、范围（Phase 1 边界）

**可操作对象（P1 白名单）**:
- 系统内: 设置项（参数注册表）/ 项目 CRUD / 会话管理 / 数据文件（JSON 白盒）
- 只读系统操作: 服务状态、日志查询、指标查询
- GUI 操作: 前端路由跳转、面板切换（经 ws_bridge 或直接前端 store）

**P1 明确不做**:
- 外部任意 shell 命令执行（需新权限域, 后置设计）
- 文件系统任意写（除 data/ 白名单 JSON）
- 网络请求（归 connectivity 模块, 与召回一致原则）

## 三、数据模型

```json
{
  "id": "op_<uuid8>",
  "instruction": "把项目 A 改名为 B",
  "intent": "agent_op",
  "plan": [
    {
      "step": 0,
      "goal": "定位项目 A",
      "tool": "projects.get",
      "params": {"name": "A"},
      "expect": "找到 id",
      "risk": "low",
      "rollback": "无（只读）"
    },
    {
      "step": 1,
      "goal": "改名",
      "tool": "projects.rename",
      "params": {"id": "<step0.id>", "name": "B"},
      "expect": "PATCH 200",
      "risk": "low",
      "rollback": "改名回 A"
    }
  ],
  "checkpoint": {
    "status": "pending", "note": ""
  },
  "execution": {
    "status": "idle", "current_step": null,
    "results": {}, "error": null
  },
  "created_at": 0, "ts": 0
}
```

## 四、端点（骨架）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v6/agent-ops/plan` | 入参 `{instruction}` → 返回 op + 计划 + checkpoint_id（不入执行） |
| GET | `/v6/agent-ops/{id}` | 查计划/执行状态（白盒） |
| POST | `/v6/agent-ops/{id}/checkpoint` | `{decision: approved/adjusted/rejected, note?, steps?}` → 审批 |
| POST | `/v6/agent-ops/{id}/execute` | 受控执行（每步过权限门 + 记录） |
| POST | `/v6/agent-ops/{id}/rollback` | 回滚到操作前基线 |
| GET | `/v6/agent-ops` | 历史列表（含经验库入口） |

## 五、安全铁律（A21 + AGENTS.md 铁律 3）

1. **计划阶段不执行任何写操作**（plan 只读 + LLM 生成; 可做只读探测）
2. **审批前零副作用** — checkpoint 未 approved 不做任何修改
3. **每步白名单校验**: 工具 ∈ 注册表 + 参数 ∈ 约束（越权拒绝, 有测试）
4. **破坏性操作可回滚**: 执行前记录基线（git/JSON 快照）; rollback 原样恢复
5. **默认拒绝**: 意图模糊 / 工具不在白名单 / 参数越界 → 拒绝并说明原因
6. **链式命令禁止**: 计划步只能调白名单工具, 不拼接 shell 链（与权限门同源）

## 六、与现有模块的接线

- **意图判定**: 复用 v3_session_api 的 LLM 意图分类（classify_intent）;
  新增 intent 类别 `agent_op`（低置信不误入, 宁可不触发）
- **规划 LLM**: 复用 _PlanningGatewayProvider（deepseek-v4-flash, thinking 关）;
  输出严格 JSON 计划, 失败降级"无法规划, 请描述更具体"
- **受控执行**: 复用 ExecutionGovernor（熔断/超时/幂等）+ tool_registry
  白名单工具; 每步 injectable（可被元认知异步诊断观察, A10 大环）
- **审批**: 复用 checkpoint 语义（chat_api 已有 pending_review 模式）
- **记录**: 全部走 EventLog（A17）+ 操作历史 JSONL（data/agent_ops.jsonl）
- **经验库**: 复用自愈经验库模式（贝叶斯 prior: 操作成功/失败 → 下次规划参考）

## 七、验收

- plan: NL 指令 → 结构化计划（步骤含 tool/params/expect/risk/rollback）
- checkpoint: 未审批不执行（测试断言零副作用）
- execute: 白名单工具执行 + 每步记录 + 失败定向重试（Governor）
- rollback: 可回滚到操作前基线（测试: 改名 → rollback → 原名）
- 意图隔离: "帮我"类进 agent_op, 普通对话不误入

## 八、分期

- **P1（本协议骨架）**: plan + checkpoint + execute（白名单: projects CRUD /
  settings / 只读状态）+ rollback + 记录
- **P2**: GUI 操作（路由跳转/面板切换）+ 前端搜索栏"帮我操作"接线
- **P3**: 操作经验库语义检索（复用经验 RAG）+ 自动化视口配对（B9 协同）

## 九、关联设计

- SELF_REPAIR_DESIGN_20260816.md（审批 gate 模式同构）
- PARADIGM.md A10/A16/A19/A21/A24（公理锚点）
- AGENTS.md 铁律 3（破坏性操作可回滚）
- UI_REFACTOR_PLAN.md B14 登记行（触发源）
