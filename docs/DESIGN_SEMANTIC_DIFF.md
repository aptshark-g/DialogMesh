# SemanticDiff — AST 级代码变更约束

> 2026-07-25 · Python ast 模块 · 10种变更分类 · 5级风险

---

## 理念

```
Before: "auth.py can be edited, /etc blocked"     ← 文件级,粗糙
After:  "auth.py: new function OK, delete BLOCKED, ← AST级,精确
         signature change NEEDS_APPROVAL"
```

---

## 10 种语义变更

```
new_function        新增函数 → RiskLevel评估 (SQL/exec=CRITICAL)
deleted_function    删除函数 → 默认 CRITICAL
signature_change    签名变化 → HIGH
body_change         函数体修改 → MEDIUM (auth/login=HIGH)
docstring_only      仅文档 → LOW
import_change       导入变化 → MEDIUM (danger=CRITICAL)
class_change        类变更 → MEDIUM
variable_change     变量变更 → LOW
decorator_change    装饰器变更 → LOW
comment_only        仅注释 → SAFE
```

## 安全检测

```
SQL注入:  regex "execute.*SELECT.*\{", "execute.*f['\"]SELECT"
exec/eval: regex "exec\(", "eval\("
网络调用:  regex "requests/socket/http.(get|post|connect)"
```

## 策略引擎

```python
constraint = SemanticConstraint()
constraint.block("login")        # 永不修改 login
constraint.protect("get_profile")  # 修改需审批
constraint.set_policy(ChangeClass.NEW_FUNCTION, "allow")
constraint.set_policy(ChangeClass.DELETED_FUNCTION, "block")

allowed, action, reason = constraint.evaluate(change)
# → (True, "allow", "") | (False, "block", "SQL injection")
```

## 接入

```python
differ = SemanticDiffer()
changes = differ.diff(old_code, new_code, "auth.py")
for c in changes:
    allowed, action, reason = constraint.evaluate(c)
```
