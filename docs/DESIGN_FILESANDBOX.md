# FileSandbox — 原子文件执行沙箱

> 2026-07-25 · Git-staging+OverlayFS+WAL 三模式融合

---

## 模式吸收

```
Git staging:     snapshot(workspace) → worktree → diff → commit/reset
Docker Overlay:  base(lower) ⊕ overlay(upper) → merged → commit layer/discard
SQLite WAL:      append changes → review → checkpoint/truncate
```

---

## 生命周期

```
snapshot()          捕获工作区状态 (sha256快照)
  │
write/edit/delete   所有操作写入临时层 (OverlayFS COW)
                   原始文件永不修改
  │
diff()              计算快照→临时层差异
                   输出: List[FileChange] (added/modified/deleted)
  │
review()            ConstraintTree规则检查
                    system path检测
                    用户审计回调
  │
commit()/rollback() 通过→合并到工作区 / 不通过→丢弃临时层
```

---

## 关键设计

- **不改原有设计**: OverlayFS copy-on-write, 原文件永不接触
- **可回滚**: rollback() → 一键丢弃所有临时文件
- **修改意图**: diff暴露给约束树+用户 → 审批 → commit
- **低概率高价值**: 改造原有文件 → Transition记录 → L5学习

## 接入

```python
sb = FileSandbox(workspace, constraint_tree)
sb.snapshot()
sb.edit("auth.py", [{"old_string": "x", "new_string": "y"}])
changes = sb.diff()
approved, violations = sb.review()
if approved: sb.commit() else sb.rollback()
```
