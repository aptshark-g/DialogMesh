# SemanticDiff 设计 ↔ 实现对照审计（DESIGN_SEMANTIC_DIFF 补盲）

> 日期: 2026-08-03 | 触发: 用户核查新增「DESIGN_SEMANTIC_DIFF.md 设计文档 0 引用，
> 但实现 execution/semantic_diff.py 已被 agent_native/bootstrap 消费——审计盲区」。
> 方法: 设计文档全文精读 + 实现全文精读 + 消费方核查。

---

## 〇、结论

1. **设计 ↔ 实现基本一致**：10 种变更分类（ChangeClass）+ 5 级风险（RiskLevel）+
   SemanticConstraint 策略引擎，实现完整对应设计。
2. **接线真相**：`bootstrap_v6._load_semantic_diff()` 真创建 `SemanticDiffer()` 实例并
   注入 `AgentOrchestrator`——但 `agent_native.py:42` 只存 `self._semantic_diff`，
   **全类再无调用**（与执行层多树图 X9-X14 同型：组件加载、零消费）。
3. **设计文档未被引用**：docs/only 全量 89 文件无一处引用 DESIGN_SEMANTIC_DIFF
   （BATCH 系列未覆盖）——现已补读，从 A 类缺口移除。

---

## 一、设计文档核心（DESIGN_SEMANTIC_DIFF.md, 全文已读）

**理念**: 文件级约束（"auth.py can be edited, /etc blocked"）→ AST 级约束
（"auth.py: new function OK, delete BLOCKED, signature change NEEDS_APPROVAL"）。

**10 种语义变更**:
```
new_function（SQL/exec → CRITICAL）/ deleted_function（默认 CRITICAL）/
signature_change（HIGH）/ body_change（MEDIUM，auth/login=HIGH）/
docstring_only（LOW）/ import_change（MEDIUM，danger=CRITICAL）/
class_change（MEDIUM）/ variable_change（LOW）/ decorator_change（LOW）/ comment_only（SAFE）
```

**安全检测**: SQL 注入（execute.*SELECT 正则）/ exec、eval / 网络调用（requests/socket/
http.get/post/connect）。

**策略引擎**: SemanticConstraint.block("login") / protect("get_profile") /
set_policy(ChangeClass, action)；evaluate(change) → (allowed, action, reason)。

---

## 二、实现对照（execution/semantic_diff.py, 370+ 行）

| 设计要素 | 实现 | 一致 |
|---|---|:--:|
| 10 分类 | ChangeClass Enum（含 FORMATTING 扩展）| ✅ 超集 |
| 5 级风险 | RiskLevel（SAFE/LOW/MEDIUM/HIGH/CRITICAL）| ✅ |
| AST 解析 | ASTAnalyzer.parse + CodeAST._extract（函数/类/导入）| ✅ |
| 函数级 diff | SemanticDiffer.diff + _compare_functions | ✅ |
| 安全检测 | FunctionInfo.contains_sql/exec/network + _security_flags | ✅ |
| 风险评估 | _assess_risk_new_function（SQL/exec→CRITICAL，auth/login/admin→HIGH）| ✅ |
| 策略 | SemanticConstraint（默认策略表 + protect/block + evaluate）| ✅ |
| 保护实体 | _protected_entities / _blocked_entities | ✅ |

**实现补充**: body_change 中 auth/login/admin/token/password 关键词 → HIGH；
new_function 网络调用 → HIGH；均与设计一致。

---

## 三、消费方核查（rg 实锤）

```
bootstrap_v6.py:69    sem_diff = _load_semantic_diff()      ← 创建
bootstrap_v6.py:93    semantic_diff=sem_diff                 ← 注入
bootstrap_v6.py:221-224 _load_semantic_diff → SemanticDiffer()  ← 真实加载（探针可见）
agent_native.py:42    self._semantic_diff = semantic_diff     ← 仅存储
agent_native.py:全类 0 处调用（rg 无 self._semantic_diff. 使用点）
```

→ **SemanticDiff 是"已接线但零调用"**：引擎持有了差异检测器，但没有任何路径调用
`differ.diff(old, new, path)` 或 `constraint.evaluate(change)`——文件修改审查从未发生。

---

## 四、问题清单

| # | 级别 | 问题 | 方向 |
|---|---|---|---|
| SD-1 | P1 | SemanticDiffer 注入后零调用（AST 级变更约束从未生效）| agent_native 写文件路径接 diff+constraint |
| SD-2 | P2 | 设计文档 0 引用（已补读）| 并入执行层/工程链设计索引 |
| SD-3 | P3 | 实现无独立测试（与 execution/ 无测试同型）| 补 diff 单测 + 安全检测用例 |

---

## 五、与全局拍板池的关系

- **P-1 接线断裂** +1: SemanticDiffer 是"加载→注入→不调用"链条的新实例（与
  CausalPlanner、closure.py 同型）。
- 与工程链约束（B7-5 负知识库 vs ConstraintTree）同域：AST 级约束 vs 文件级约束 vs
  负知识库三套约束机制 → 约束体系归一待哲学统一。

