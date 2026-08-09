# SemanticDiff 施工记录 — SD-1/2/3（AST 约束接线生效）

> 日期: 2026-08-05 | 批次: SD（模块级补全第九批）
> 审计依据: `docs/only/landscape_read/SEMANTIC_DIFF_AUDIT_20260803.md`
> + `docs/only/execution/AUDIT_ENTRY_20260803.md`
> 状态: ✅ 完成（SD 19/19 + 回归 88/88 + import 探针 6/6 全通）

---

## 一、根因

`SemanticDiffer`（execution/semantic_diff.py，17.8KB，10 分类 + 5 级风险 +
SemanticConstraint 策略引擎）被 bootstrap_v6 真实创建并注入
AgentOrchestrator，但 `agent_native.py:42` 仅存储 `self._semantic_diff`，
全类零调用 → AST 级变更约束从未生效（与 CausalPlanner / 多树图同型
「加载→注入→不调用」断链）。

---

## 二、SD-1: FileSandbox.review 接入 AST 级约束（真实写路径）

**接线点选择**: agent_native 无文件写操作（rg 实证），真实写路径 =
`execution/sandbox.py`（FileSandbox → SandboxIntegration → ExecutionEngine）。
在 `FileSandbox.review()` 增加 AST 级语义审查：

```
FileSandbox.__init__(workspace, constraint_tree, semantic_differ=None,
                     semantic_constraint=None)
  → review() 对 MODIFIED/ADDED 且 .py 结尾的 change:
      _semantic_violations(change)
        → SemanticDiffer.diff(old_content, new_content, path)
        → SemanticConstraint.evaluate(change) 逐个评估
        → 非 allow 追加 violation（semantic[action]: path::entity (class) — reason）
  → 惰性创建 differ/constraint（无注入时自动装配，import 失败静默降级）
```

**默认策略生效**（SemanticConstraint 内置）:
- deleted_function → block（删除函数 = violation）
- signature_change / import_change → require_approval（violation）
- security_concerns（SQL/exec/网络）→ 恒 block
- new_function / body_change / docstring / comment → allow（不阻塞）

## 三、SD-1 装配（bootstrap_v6）

```
_load_file_sandbox():
  FileSandbox(os.getcwd(), semantic_differ=SemanticDiffer(),
              semantic_constraint=SemanticConstraint())
  （differ 加载失败 → 退回纯 FileSandbox，不破坏既有装配）
SandboxIntegration.__init__ 增加 semantic_differ/semantic_constraint 透传，
execute_batch 内部新建 FileSandbox 时注入。
```

## 四、SD-3: 独立测试套件（新增 19 项）

`core/agent/execution/tests/test_semantic_diff.py`（execution 首个测试目录）:
```
TestSemanticDiffer（8）: new_function / deleted=CRITICAL / signature=HIGH /
  docstring=LOW / import+danger / SQL→CRITICAL / no_change=SAFE / parse_error 降级
TestSemanticConstraint（7）: allow / block / require_approval / security 恒 block /
  blocked entity / protected entity / custom policy
TestFileSandboxSemanticWiring（4）: 删函数 blocked / SQL 新增 blocked /
  安全新增 allowed / 非 .py 不检查
```

## 五、SD-2: 设计文档索引补录

`DOCS_LANDSCAPE_MAPPING_20260803.md` 执行层/StateMachine 行补
`DESIGN_SEMANTIC_DIFF（SD 批次补录）`（实现属 execution/，此前只在外围服务
行标注"已补读"）。

---

## 六、验证

```
SD 测试 19/19 | 组合回归 88/88（execution+planner+runtime+event 子集）
import 探针 6/6（semantic_diff/sandbox/permissions/bootstrap_v6/
agent_native/v6_app）
装配探针: _load_file_sandbox 返回的 FileSandbox 已带 differ+constraint
```

## 七、改动文件
```
M core/agent/execution/sandbox.py       review 接 AST 约束 + _semantic_violations
M core/agent/orchestrator/bootstrap_v6.py  _load_file_sandbox 注入 differ+constraint
A core/agent/execution/tests/__init__.py
A core/agent/execution/tests/test_semantic_diff.py  19 项
M docs/only/DOCS_LANDSCAPE_MAPPING_20260803.md  SD-2 索引补录
```

## 八、记录不施工（边界纪律）
- `agent_native._semantic_diff` 仍为存储属性（agent_native 已退数据容器，
  按 G3 定案不再承担写路径职责）——真实审查在 FileSandbox，装配在 bootstrap。
- 约束体系三套归一（AST 级 semantic_diff / 文件级 ConstraintTree / 负知识库
  B7-5）留待哲学统一拍板，本批仅让 AST 约束生效，不做归一。
