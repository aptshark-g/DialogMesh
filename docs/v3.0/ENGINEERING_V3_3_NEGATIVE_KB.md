# DialogMesh 负知识库 --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-NEGATIVE-KB-008  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S8  
> **前置算法**: v3.3 算法设计 S8 --- 三级分类 + 三次熔断 + 上下文开关  
> **原则**: HARD_BLOCK 不靠人工标注, 必须由 do-calculus 验证或形式化证明。  

---
## 1. 文档目标与范围

为负知识库提供工程实现规范。覆盖三级分类、三次熔断、上下文开关、规则冲突仲裁。

### 边界
| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | 用户意图 + 当前上下文 | 用户原始输入 |
| 输出 | BLOCK / WARN / ALLOW 决策 | 行为预测 |
| 触发 | 规则预先注册 + do-calculus 验证 | 在线学习（只在熔断后记录）|

---
## 2. 架构总览
### 文件结构
```
core/agent/v3_2/negative_kb/
  __init__.py
  models.py            # NegativeLevel, ContextualNegativeRule, NegativeResult
  rule_store.py        # RuleStore (规则注册/查询/验证)
  fuse_controller.py   # FuseController (三次熔断)
  negative_kb.py       # NegativeKB 入口
```

---
## 3. 数据模型 (models.py)
```python
class NegativeLevel(str, Enum):
    HARD_BLOCK = "hard_block"
    WARN = "warn"
    SOFT_DISCOURAGE = "soft_discourage"

@dataclass
class ContextualNegativeRule:
    rule_id: str
    level: NegativeLevel
    condition: Callable | None  # (context) -> bool
    message: str
    domain: str = "general"
    is_verified: bool = False   # do-calculus 验证通过

    def is_applicable(self, ctx) -> bool:
        return self.condition(ctx) if self.condition else True

@dataclass
class NegativeResult:
    level: NegativeLevel | None
    rule_id: str | None
    message: str
    blocked: bool = False
    learned: bool = False  # 经过三次熔断后学习到新上下文
    domain_exception: str = ""
```

---
## 4. RuleStore
```python
class RuleStore:
    def __init__(self):
        self.rules: list[ContextualNegativeRule] = []

    def register(self, rule: ContextualNegativeRule):
        self.rules.append(rule)

    def query(self, ctx) -> list[ContextualNegativeRule]:
        return [r for r in self.rules if r.is_applicable(ctx)]

    def verify_hard_block(self, rule: ContextualNegativeRule) -> bool:
        if rule.level != NegativeLevel.HARD_BLOCK:
            return True
        return rule.is_verified

    def get_conflict_highest(self, ctx) -> NegativeLevel | None:
        applicable = self.query(ctx)
        if not applicable: return None
        levels = [r.level for r in applicable]
        if NegativeLevel.HARD_BLOCK in levels:
            return NegativeLevel.HARD_BLOCK  # HARD 覆盖一切
        if NegativeLevel.WARN in levels:
            return NegativeLevel.WARN
        return NegativeLevel.SOFT_DISCOURAGE
```

---
## 5. FuseController (三次熔断)
```python
class FuseController:
    FUSE_LIMIT = 3

    def __init__(self):
        self.hit_counts: dict[str, int] = {}     # rule_id -> count
        self.learned_exceptions: dict[str, str] = {}  # rule_id -> exception

    def evaluate(self, rule: ContextualNegativeRule, ctx) -> NegativeResult:
        if rule.level == NegativeLevel.HARD_BLOCK:
            return NegativeResult(NegativeLevel.HARD_BLOCK, rule.rule_id, rule.message, blocked=True)

        if rule.level == NegativeLevel.SOFT_DISCOURAGE:
            return NegativeResult(NegativeLevel.SOFT_DISCOURAGE, rule.rule_id, rule.message)

        # WARN 级别: 三次熔断
        rule_id = rule.rule_id
        if rule_id not in self.hit_counts:
            self.hit_counts[rule_id] = 0
        self.hit_counts[rule_id] += 1
        count = self.hit_counts[rule_id]

        if count == 1:
            return NegativeResult(NegativeLevel.WARN, rule_id, rule.message, blocked=True)
        elif count == 2:
            return NegativeResult(NegativeLevel.WARN, rule_id, f"注意: {rule.message}", blocked=False)
        else:
            # 第 3 次 -> 降级并学习
            exception = self._learn_exception(rule, ctx)
            return NegativeResult(None, rule_id, "", learned=True, domain_exception=exception)

    def _learn_exception(self, rule, ctx) -> str:
        exception = f"{rule.rule_id}: user explicitly requested blocked action"
        self.learned_exceptions[rule.rule_id] = exception
        return exception

    def reset_fuse(self, rule_id: str):
        if rule_id in self.hit_counts:
            del self.hit_counts[rule_id]
```

---
## 6. NegativeKB (入口)
```python
class NegativeKB:
    def __init__(self, store=None, fuse=None):
        self.store = store or RuleStore()
        self.fuse = fuse or FuseController()

    def check(self, ctx) -> NegativeResult:
        level = self.store.get_conflict_highest(ctx)
        if level is None:
            return NegativeResult(None, None, "")
        for rule in self.store.query(ctx):
            if rule.level == level:
                if level == NegativeLevel.HARD_BLOCK and not self.store.verify_hard_block(rule):
                    continue  # 未验证的 HARD -> 跳过
                return self.fuse.evaluate(rule, ctx)
        return NegativeResult(None, None, "")

    def register_rule(self, rule: ContextualNegativeRule):
        if rule.level == NegativeLevel.HARD_BLOCK and not rule.is_verified:
            raise ValueError("HARD_BLOCK rules must be do-calculus verified")
        self.store.register(rule)
```

---
## 7. 测试策略
| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_models | NegativeLevel, ContextualNegativeRule, NegativeResult | P0 |
| test_rule_store | 注册, 查询, 冲突仲裁, 验证检查 | P0 |
| test_fuse_controller | 三次熔断, 学习, 重置 | P0 |
| test_negative_kb | 检查流程, HARD_BLOCK 未验证跳过 | P0 |

---
## 8. 附录
### 对照
| 算法 S8 | 实现 | 状态 |
|---------|------|------|
| 三级分类 | NegativeLevel | 待实现 |
| 上下文开关 | ContextualNegativeRule.condition | 待实现 |
| 三次熔断 | FuseController | 待实现 |
| HARD_BLOCK 验证 | RuleStore.verify_hard_block | 待实现 |
| 入口 | NegativeKB | 待实现 |
--- END OF DOCUMENT ---