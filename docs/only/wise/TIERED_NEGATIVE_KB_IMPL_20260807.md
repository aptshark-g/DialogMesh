# 施工记录 — TieredNegativeKB 负知识约束接入（2026-08-07）

> 状态: 完成 ✅ | 触发: UN_USE_AUDIT 第二个高价值断线候选 →
> 用户确认继续剩余候选

---

## 一、恢复（v4/un_use → core/agent/negative_kb/tiered.py）

- 原 `v4/un_use/negative_kb.py`（TieredNegativeKB）依赖
  `core.agent.v4.tiered.pipeline`（Tier/MultiTierPipeline）— **该模块已删**,
  恢复时改为自包含两层（不重建 v4/tiered）
- 底层 `core.agent.negative_kb`（活跃, RuleStore + FuseController + 门面）
  — import 修正: `v3_2.negative_kb.negative_kb` → `core.agent.negative_kb`
- **FuseController 语义瑕疵修正**（tiered 层）: WARN 首次命中原始
  blocked=True → 改为只提醒不拦截（WARN/SOFT_DISCOURAGE → blocked=False）

## 二、接入（executor 工具调用前校验）

- engine `_ensure_negative_kb()`: TieredNegativeKB 懒加载 + 种子规则注册
  （HARD_BLOCK 需 verified: rm -rf / chmod 777 / 硬编码密钥;
   WARN: sudo 提权需审批）
- executor `_handle_tool`（T2 必填参数校验后）: `_lazy_negative_kb().check()`
  - HARD_BLOCK → 返回 `{status: "blocked", reason: "negative_kb", message}`
    （工具不执行）
  - WARN/SOFT → 执行但 `_turn_tainted=True`（GAP-5 联动: 需注意）
  - 无 engine/无规则 → 跳过（不破坏现有）

## 三、验证

- 新测试 `negative_kb/tests/test_tiered.py` **5/5**: HARD_BLOCK 拦截 /
  WARN 不拦截 / 无关上下文空 / 未验证 HARD_BLOCK 不拦截 / stats
- executor 接入测试（test_taint.py 新增 2）: HARD_BLOCK → blocked /
  无 engine 正常执行
- 回归 36/36 全绿（tool_node + tool_batch + intervention + taint + tiered）

## 四、对齐

- 负知识约束与权限引擎（PermissionEngine, 决策前安全门）互补:
  权限引擎 = 结构规则（RiskClass/Mode/路径根）;
  负知识库 = 内容模式（危险操作/密钥/提权关键词）
- GAP-5 taint 联动: WARN 工具结果污染回合（[不可信] 标注）
- A21 安全底线: HARD_BLOCK 不可绕过（需 verified 才能注册）

## 五、遗留

- FuseController 底层语义修正（active 模块, 本批在 tiered 层修;
  底层 blocked=True 语义可后续对齐）
- 负知识规则的持久化/管理 API（当前种子内存注册, P2）
- 前端负知识规则视图（RightDock, P2 — 与启发/变更日志同列）
