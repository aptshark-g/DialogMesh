# DialogMesh do-calculus --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-DO-CALCULUS-011  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S11  
> **前置算法**: 后门准则验证  
> **原则**: do-calculus 只用于验证 HARD_BLOCK, 不用于发现因果。后门准则即可, 无需完整三条规则。  

---
## 1. 文档目标与范围
为 do-calculus 后门准则验证提供工程实现规范。覆盖路径分析、混杂因子检查、HARD_BLOCK 验证。

### 边界
| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | causal_skeleton (DAG) + hypothesis | 因果发现 |
| 输出 | 验证通过/降级 WARN | 因果图构建 |
| 触发 | BlockStore 申请 HARD_BLOCK 标签时 | 在线推理 |

---
## 2. 数据模型
```python
@dataclass
class CausalEdge:
    source: str; target: str; label: str = ""

@dataclass
class CausalSkeleton:
    nodes: list[str]
    edges: list[CausalEdge]
    observed: set[str] = field(default_factory=set)  # 已控制的变量

@dataclass
class BackdoorTestResult:
    hypothesis: str
    verified: bool
    paths_checked: int
    confounders_found: list[str]
    p_y_given_do_x: float  # P(Y|do(X)) 估计值

    def to_negative_level(self):
        if self.verified and self.p_y_given_do_x >= 0.95:
            return "HARD_BLOCK"
        return "WARN"
```

---
## 3. BackdoorCriterion
```python
class BackdoorCriterion:
    MAX_PATH_DEPTH = 5
    PROB_THRESHOLD = 0.95

    def verify(
        self, skeleton: CausalSkeleton,
        intervention_var: str, outcome_var: str
    ) -> BackdoorTestResult:
        all_paths = self._find_paths(skeleton, intervention_var, outcome_var)
        confounders = self._find_confounders(skeleton, all_paths)
        uncontrolled = [c for c in confounders if c not in skeleton.observed]
        verified = len(uncontrolled) == 0
        if verified:
            p = self._estimate_p(skeleton, intervention_var, outcome_var)
        else:
            p = 0.0  # 无法验证
        return BackdoorTestResult(
            hypothesis=f"do({intervention_var}=0) => {outcome_var}=0",
            verified=verified, paths_checked=len(all_paths),
            confounders_found=uncontrolled, p_y_given_do_x=p
        )

    def _find_paths(self, sk, x, y, depth=0, visited=None) -> list[list[str]]:
        if visited is None: visited = set()
        if depth > self.MAX_PATH_DEPTH: return []
        if x == y: return [[x]]
        visited = visited | {x}
        paths = []
        for edge in sk.edges:
            nxt = None
            if edge.source == x and edge.target not in visited:
                nxt = edge.target
            if edge.target == x and edge.source not in visited:
                nxt = edge.source
            if nxt:
                sub = self._find_paths(sk, nxt, y, depth+1, visited)
                for p in sub:
                    paths.append([x] + p)
        return paths

    def _find_confounders(self, sk, paths) -> list[str]:
        """找到所有路径上同时影响 X 和 Y 的节点"""
        confounders = set()
        for path in paths:
            for node in path[1:-1]:  # 排除 X 和 Y 自身
                parents = set()
                for e in sk.edges:
                    if e.target == node: parents.add(e.source)
                    if e.source == node: parents.add(e.target)
                if len(parents) >= 2:  # 有多个父节点 -> 可能是混杂
                    confounders.add(node)
        return list(confounders)

    def _estimate_p(self, sk, x, y) -> float:
        """估计 P(Y|do(X)): 如果所有后门路径被控制, do(X)=0 => P(Y=0|X=0)"""
        # 简化估计: 如果存在 X->...->Y 的路径, 且路径上无混杂,
        # 则 P(Y=0|X=0) ≈ 1.0
        direct = any(e.source == x and e.target == y for e in sk.edges)
        if direct: return 1.0
        paths = self._find_paths(sk, x, y)
        return 0.95 if paths else 0.5
```

---
## 4. DoCalculusValidator
```python
class DoCalculusValidator:
    """do-calculus 验证器入口"""

    def __init__(self, criterion=None):
        self.criterion = criterion or BackdoorCriterion()

    def validate_hard_block(
        self, skeleton: CausalSkeleton,
        rule: ContextualNegativeRule
    ) -> BackdoorTestResult:
        if rule.level.name != "HARD_BLOCK":
            return BackdoorTestResult("", True, 0, [], 1.0)
        # 从 rule.message 解析干预和结果变量
        x, y = self._parse_hypothesis(rule)
        if not x or not y:
            return BackdoorTestResult(rule.rule_id, False, 0, ["parse_error"], 0.0)
        return self.criterion.verify(skeleton, x, y)

    def _parse_hypothesis(self, rule) -> tuple[str|None, str|None]:
        text = rule.message
        # "干预 X => Y" -> (X, Y)
        import re
        m = re.search(r"干预\s*(\w+)\s*=*>?\s*(\w+)", text)
        if m: return (m.group(1), m.group(2))
        return (None, None)
```

---
## 5. 与 NegativeKB 的集成
```python
# NegativeKB 注册 HARD_BLOCK 规则前进行验证
def register_with_validation(kb: NegativeKB, validator: DoCalculusValidator,
                            rule: ContextualNegativeRule, skeleton: CausalSkeleton):
    if rule.level == NegativeLevel.HARD_BLOCK:
        result = validator.validate_hard_block(skeleton, rule)
        if result.verified and result.p_y_given_do_x >= 0.95:
            rule.is_verified = True
            kb.register_rule(rule)
            return True
        raise ValueError(f"HARD_BLOCK verification failed: {result}")
    kb.register_rule(rule)
    return True
```

---
## 6. 测试策略
| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_causal_skeleton | 图构建, 路径查找, 深度限制 | P0 |
| test_backdoor_criterion | 混杂因子检测, 后门路径检查 | P0 |
| test_do_calculus_validator | hypothesis 解析, verify | P0 |
| test_integration_with_kb | HARD_BLOCK 注册验证链路 | P1 |
--- END OF DOCUMENT ---