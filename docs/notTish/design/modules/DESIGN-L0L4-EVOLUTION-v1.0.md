# Literature Cortex — L0-L4 种子库受控演化机制设计

> **文档编号:** LC-L0L4-EVOLUTION
> **版本:** v1.0-DRAFT
> **日期:** 2026-06-20
> **依赖:** v5.4 协同层 + L0-L4 种子库
> **核心目标:** L0-L4 可修改，但有幅度控制、回溯链条、冗余审查

---

## 1. 问题陈述

### 1.1 为什么 L0-L4 必须可修改

L0-L4 不是静态圣经，是**活体的骨骼**：
- 新数学结构出现（如 newform 理论）→ L2 需要扩展
- 新物理范式确立（如量子信息）→ L1 需要更新
- 用户领域扩展（如从振动控制扩展到量子计算）→ L0-L4 的覆盖范围需要调整
- 自引用机制（v5.2b）发现盲区 → 需要主动补充

### 1.2 为什么修改必须受控

L0-L4 是**整个系统的根基**。随意修改的后果：
- 修改一个公理节点 → 所有基于该公理的推导可能失效
- 删除一个数学结构 → 下游 L3-L6 的关联断裂
- 重命名一个概念 → 反向索引失效、跨域类比锚点丢失

> 类比：修改 L0-L4 像修改宪法，不是修改普通法律。

---

## 2. 核心设计：四层防护机制

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: 审计与回溯 (Audit & Traceback)                     │
│  • 完整修改历史记录                                          │
│  • 差异比对（diff）与影响范围分析                             │
│  • 时间点恢复（point-in-time recovery）                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 冗余审查 (Redundant Review)                        │
│  • 多角色审查：自引用系统 + 人工 + 规则引擎                    │
│  • 投票机制：2/3 通过                                        │
│  • 影响评估：修改波及范围自动计算                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 幅度控制 (Amplitude Control)                       │
│  • 修改类型分级：属性级 / 关系级 / 结构级                      │
│  • 修改幅度限制：单轮修改量上限                                │
│  • 冷却期：高频修改的自动抑制                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 版本控制 (Version Control)                         │
│  • 不可变提交（immutable commit）                            │
│  • 分支隔离：修改先在分支，合并才生效                          │
│  • 原子操作：要么全部生效，要么全部回滚                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 版本控制层（Layer 1）

### 3.1 不可变提交模型

```python
class L0L4Commit:
    """L0-L4 的不可变提交。"""
    
    commit_id: str      # SHA-256 哈希
    parent_id: str      # 父提交（形成链条）
    timestamp: datetime
    author: str         # "human:<name>" / "system:<module>" / "self-ref:<cycle_id>"
    
    # 修改内容（不是全量快照，是差异）
    delta: L0L4Delta    # 结构化差异
    
    # 元数据
    change_type: str    # "attribute" / "relation" / "structural" / "meta"
    scope: str          # 修改影响的节点范围（JSON Path 或 node_id 列表）
    rationale: str      # 修改理由（强制填写）
    
    # 影响预计算（提交时自动计算）
    impact_analysis: ImpactReport  # 波及范围分析

class L0L4Delta:
    """结构化差异。"""
    
    # 节点级操作
    node_additions: list[Node]      # 新增节点
    node_removals: list[str]       # 删除节点（仅 node_id）
    node_modifications: list[NodePatch]  # 修改节点（属性级）
    
    # 关系级操作
    edge_additions: list[Edge]
    edge_removals: list[str]
    edge_modifications: list[EdgePatch]
    
    # 索引级操作
    index_updates: list[IndexUpdate]  # 反向索引更新
```

### 3.2 分支隔离

```python
class L0L4Branch:
    """L0-L4 的分支模型。"""
    
    name: str           # "main" / "staging" / "self-ref-cycle-42" / "human-review-2026-06-20"
    head_commit: str    # 分支最新提交
    base_commit: str    # 从哪个提交分叉
    
    # 分支类型
    branch_type: str    # "protected"(main) / "staging"(预发布) / "experimental"(实验)
    
    # 合并要求
    merge_requirements: MergeRequirements

class MergeRequirements:
    """合并到 main 的要求。"""
    
    min_review_votes: int = 2       # 最少审查票数（2/3）
    max_impact_score: float = 0.3   # 最大影响范围（30%节点）
    require_human_approval: bool     # 结构级修改必须人工审批
    cooldown_hours: int = 24        # 同一分支冷却期
```

**分支策略：**

```
main (受保护，只读)
  ← staging (预发布，可修改)
      ← self-ref-cycle-N (自引用生成)
      ← human-review-YYYY-MM-DD (人工审查)
      ← experimental-XXX (实验性)
```

- `main`：只接受合并，不接受直接修改
- `staging`：自引用和人工修改的汇集点
- 临时分支：修改先在此验证，通过后才合并到 staging

### 3.3 原子操作

```python
class L0L4Transaction:
    """原子事务：要么全部生效，要么全部回滚。"""
    
    def commit(self) -> L0L4Commit:
        """提交事务。"""
        # 1. 验证差异合法性（schema校验、ID唯一性）
        self._validate()
        
        # 2. 计算影响范围
        impact = self._compute_impact()
        
        # 3. 检查幅度限制
        if not self._check_amplitude(impact):
            raise AmplitudeExceededError()
        
        # 4. 写入临时区
        self._write_to_staging()
        
        # 5. 执行审查（异步或同步）
        if self._requires_review():
            review_result = self._execute_review()
            if not review_result.passed:
                self._rollback()
                raise ReviewRejectedError(review_result)
        
        # 6. 正式生效（原子操作）
        self._atomic_apply()
        
        # 7. 生成提交记录
        return self._create_commit()
    
    def rollback(self):
        """回滚事务。"""
        self._staging_cleanup()
        self._lock_release()
```

---

## 4. 幅度控制层（Layer 2）

### 4.1 修改类型分级

| 级别 | 类型 | 示例 | 影响范围 | 审查要求 |
|------|------|------|---------|---------|
| **属性级** | 修改节点的非关键属性 | 修正description拼写、补充aliases | 单个节点 | 自动通过（规则引擎） |
| **关系级** | 修改节点间关系 | 新增/删除边、修改关联强度 | 2-5个节点 | 自引用审查 + 规则检查 |
| **结构级** | 修改节点结构或新增/删除节点 | 新增L2数学结构、删除过时公理 | 5-20+个节点 | **人工审查必须** |
| **元级** | 修改L0-L4的整体结构 | 新增层级、修改层级定义 | 全部 | **人工审查 + 多轮讨论** |

### 4.2 修改幅度限制

```python
class AmplitudeController:
    """修改幅度控制器。"""
    
    # 单轮限制
    MAX_NODES_PER_COMMIT = 5          # 单次最多修改5个节点
    MAX_EDGES_PER_COMMIT = 10         # 单次最多修改10条边
    MAX_DESCRIPTION_CHANGE_RATIO = 0.3  # description修改不超过30%字符
    
    # 周期限制（冷却期）
    COOLDOWN_HOURS = {
        "attribute": 0,     # 属性级无冷却
        "relation": 1,      # 关系级1小时
        "structural": 24,   # 结构级24小时
        "meta": 168,        # 元级7天
    }
    
    # 影响范围限制
    MAX_IMPACT_NODE_RATIO = 0.3       # 影响节点不超过总节点30%
    MAX_IMPACT_EDGE_RATIO = 0.2       # 影响边不超过总边20%
    
    def check(self, delta: L0L4Delta) -> AmplitudeReport:
        """检查修改幅度是否合规。"""
        violations = []
        
        # 检查节点数量
        if len(delta.node_additions) + len(delta.node_removals) + len(delta.node_modifications) > self.MAX_NODES_PER_COMMIT:
            violations.append("节点修改数超限")
        
        # 检查边数量
        if len(delta.edge_additions) + len(delta.edge_removals) > self.MAX_EDGES_PER_COMMIT:
            violations.append("边修改数超限")
        
        # 检查冷却期
        last_commit = self._get_last_commit_type(delta.author)
        required_cooldown = self.COOLDOWN_HOURS[last_commit.change_type]
        if (datetime.now() - last_commit.timestamp).hours < required_cooldown:
            violations.append(f"冷却期未满足（需{required_cooldown}小时）")
        
        # 检查影响范围
        impact = self._compute_impact(delta)
        if impact.node_ratio > self.MAX_IMPACT_NODE_RATIO:
            violations.append(f"影响节点比例{impact.node_ratio:.1%}超过{self.MAX_IMPACT_NODE_RATIO:.1%}")
        
        return AmplitudeReport(
            allowed=len(violations) == 0,
            violations=violations,
            impact=impact,
        )
```

### 4.3 影响范围自动计算

```python
class ImpactAnalyzer:
    """影响范围分析器。"""
    
    def analyze(self, delta: L0L4Delta) -> ImpactReport:
        """分析修改的波及范围。"""
        
        # 直接影响：被修改的节点/边
        direct_nodes = self._get_direct_nodes(delta)
        direct_edges = self._get_direct_edges(delta)
        
        # 1级间接影响：被修改节点的邻居
        level1_nodes = set()
        for node_id in direct_nodes:
            level1_nodes.update(self._get_neighbors(node_id, distance=1))
        
        # 2级间接影响：邻居的邻居（仅结构级修改需要）
        level2_nodes = set()
        if delta.change_type == "structural":
            for node_id in level1_nodes:
                level2_nodes.update(self._get_neighbors(node_id, distance=1))
        
        # 下游影响：基于反向索引的推导领域
        downstream_domains = self._get_downstream_domains(direct_nodes)
        
        # 验证影响：基于假设层中引用这些节点的假设
        verification_impact = self._get_verification_impact(direct_nodes)
        
        return ImpactReport(
            direct_node_count=len(direct_nodes),
            indirect_node_count=len(level1_nodes | level2_nodes),
            total_node_ratio=(len(direct_nodes) + len(level1_nodes) + len(level2_nodes)) / self.total_nodes,
            affected_edges=len(direct_edges),
            downstream_domains=downstream_domains,
            verification_risk=verification_impact,
            
            # 关键指标：如果影响L1公理，风险倍增
            is_axiom_affected=any(self._is_axiom(n) for n in direct_nodes),
            risk_multiplier=2.0 if any(self._is_axiom(n) for n in direct_nodes) else 1.0,
        )
```

---

## 5. 冗余审查层（Layer 3）

### 5.1 三角色审查机制

```python
class ReviewSystem:
    """冗余审查系统：2/3投票通过。"""
    
    def review(self, commit: L0L4Commit) -> ReviewResult:
        """执行多角色审查。"""
        
        # 角色1：规则引擎（自动化）
        rule_review = self._rule_engine_review(commit)
        
        # 角色2：自引用系统（v5.2b）
        self_ref_review = self._self_reference_review(commit)
        
        # 角色3：人工审查（仅结构级和元级）
        human_review = self._human_review(commit) if commit.change_type in ("structural", "meta") else None
        
        # 投票统计
        votes = [rule_review.passed, self_ref_review.passed]
        if human_review:
            votes.append(human_review.passed)
        
        passed = sum(votes) >= 2
        
        return ReviewResult(
            passed=passed,
            votes={
                "rule_engine": rule_review,
                "self_reference": self_ref_review,
                "human": human_review,
            },
            required_votes=2 if human_review else 2,
            total_votes=3 if human_review else 2,
        )
```

### 5.2 规则引擎审查（自动化）

```python
def _rule_engine_review(self, commit: L0L4Commit) -> ReviewVote:
    """规则引擎自动审查。"""
    
    checks = []
    
    # 检查1：schema合规性
    checks.append(self._check_schema_validity(commit.delta))
    
    # 检查2：ID唯一性（不冲突）
    checks.append(self._check_id_uniqueness(commit.delta))
    
    # 检查3：层级一致性（L3节点不能引用不存在的L2节点）
    checks.append(self._check_level_consistency(commit.delta))
    
    # 检查4：反向索引可更新性
    checks.append(self._check_index_updatability(commit.delta))
    
    # 检查5：无循环引用（新增边不能形成环）
    checks.append(self._check_no_cycles(commit.delta))
    
    # 检查6：公理保护（L1节点的删除需要特殊标记）
    if self._has_axiom_deletion(commit.delta):
        checks.append(False)  # 公理删除自动拒绝，需人工override
    
    return ReviewVote(
        passed=all(checks),
        checks=checks,
        reason="Schema/ID/Level/Index/Cycle/Axion checks",
    )
```

### 5.3 自引用审查（v5.2b）

```python
def _self_reference_review(self, commit: L0L4Commit) -> ReviewVote:
    """自引用系统审查：修改是否改善系统结构。"""
    
    # 获取修改前的结构报告
    before_report = self.self_ref_layer2.analyze_structure()
    
    # 在临时分支上应用修改
    temp_branch = self._create_temp_branch(commit)
    self._apply_to_temp(temp_branch, commit)
    
    # 获取修改后的结构报告
    after_report = self.self_ref_layer2.analyze_structure(temp_branch)
    
    # 比较指标
    improvements = []
    regressions = []
    
    # 指标1：层级完整性（是否更完整）
    if after_report.level_completeness > before_report.level_completeness:
        improvements.append("层级完整性提升")
    elif after_report.level_completeness < before_report.level_completeness:
        regressions.append("层级完整性下降")
    
    # 指标2：跨层连接密度
    if after_report.cross_layer_density > before_report.cross_layer_density:
        improvements.append("跨层连接增强")
    
    # 指标3：多视角覆盖率
    if after_report.perspective_coverage > before_report.perspective_coverage:
        improvements.append("多视角覆盖率提升")
    
    # 指标4：盲点数（应减少或不变）
    if len(after_report.blind_spots) <= len(before_report.blind_spots):
        improvements.append("盲点数未增加")
    else:
        regressions.append(f"盲点数增加{len(after_report.blind_spots) - len(before_report.blind_spots)}")
    
    # 决策：改善 > 退化，且无致命退化
    passed = len(improvements) >= len(regressions) and not any(r.startswith("层级完整性") for r in regressions)
    
    return ReviewVote(
        passed=passed,
        improvements=improvements,
        regressions=regressions,
    )
```

### 5.4 人工审查

```python
def _human_review(self, commit: L0L4Commit) -> ReviewVote:
    """人工审查：结构级和元级修改必须。"""
    
    # 生成审查报告
    report = self._generate_human_review_report(commit)
    
    # 提交到待审队列
    review_request = self._submit_to_review_queue(report)
    
    # 等待人工响应（异步，有超时）
    # 超时默认：拒绝（保守策略）
    response = self._wait_for_human_response(review_request, timeout=timedelta(days=7))
    
    return ReviewVote(
        passed=response.approved,
        reviewer=response.reviewer,
        comments=response.comments,
    )
```

---

## 6. 审计与回溯层（Layer 4）

### 6.1 完整修改历史

```sql
-- L0-L4 修改历史
CREATE TABLE l0l4_commit_history (
    commit_id TEXT PRIMARY KEY,
    parent_id TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    author_type TEXT CHECK(author_type IN ('human', 'system', 'self-ref')),
    author_id TEXT,
    change_type TEXT CHECK(change_type IN ('attribute', 'relation', 'structural', 'meta')),
    scope TEXT,                    -- JSON: 影响的节点列表
    rationale TEXT NOT NULL,       -- 修改理由（强制）
    
    -- 差异存储
    delta_before TEXT,             -- JSON: 修改前状态
    delta_after TEXT,              -- JSON: 修改后状态
    
    -- 审查记录
    rule_review_passed INTEGER,    -- 0/1
    self_ref_review_passed INTEGER,
    human_review_passed INTEGER,
    review_notes TEXT,             -- JSON
    
    -- 影响分析
    impact_node_count INTEGER,
    impact_edge_count INTEGER,
    downstream_domains TEXT,       -- JSON
    
    -- 执行状态
    status TEXT CHECK(status IN ('pending', 'applied', 'rolled_back', 'rejected'))
);

-- 时间点快照（每24小时自动创建）
CREATE TABLE l0l4_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    timestamp TIMESTAMP,
    commit_id TEXT,                -- 基于哪个commit
    full_state TEXT,               -- 完整L0-L4 JSON（压缩存储）
    size_bytes INTEGER
);
```

### 6.2 差异比对（Diff）

```python
class L0L4Diff:
    """差异比对工具。"""
    
    def diff(self, commit_a: str, commit_b: str) -> DiffReport:
        """比较两个提交的差异。"""
        state_a = self._get_state_at(commit_a)
        state_b = self._get_state_at(commit_b)
        
        # 节点差异
        node_diffs = self._compare_nodes(state_a.nodes, state_b.nodes)
        
        # 边差异
        edge_diffs = self._compare_edges(state_a.edges, state_b.edges)
        
        # 索引差异
        index_diffs = self._compare_indices(state_a.index, state_b.index)
        
        return DiffReport(
            added_nodes=[n for n in node_diffs if n.type == "added"],
            removed_nodes=[n for n in node_diffs if n.type == "removed"],
            modified_nodes=[n for n in node_diffs if n.type == "modified"],
            added_edges=[...],
            removed_edges=[...],
            modified_edges=[...],
        )
    
    def blame(self, node_id: str) -> list[CommitBlame]:
        """追溯一个节点的修改历史（类似git blame）。"""
        commits = self._get_commits_affecting_node(node_id)
        return [
            CommitBlame(
                commit_id=c.commit_id,
                author=c.author,
                timestamp=c.timestamp,
                change=c.get_change_for_node(node_id),
                rationale=c.rationale,
            )
            for c in commits
        ]
```

### 6.3 时间点恢复

```python
class PointInTimeRecovery:
    """时间点恢复。"""
    
    def recover(self, target_time: datetime) -> L0L4State:
        """恢复到指定时间点的状态。"""
        # 找到最近的快照
        snapshot = self._find_nearest_snapshot(target_time)
        
        # 从快照开始，重放后续提交到目标时间
        commits_to_replay = self._get_commits_between(snapshot.timestamp, target_time)
        
        state = snapshot.state
        for commit in commits_to_replay:
            state = self._apply_delta(state, commit.delta)
        
        return state
    
    def rollback(self, commit_id: str) -> L0L4State:
        """回滚到指定提交（撤销该提交及之后的所有提交）。"""
        # 找到该提交的父提交
        commit = self._get_commit(commit_id)
        parent_state = self._get_state_at(commit.parent_id)
        
        return parent_state
```

---

## 7. 与协同层的集成

### 7.1 协同层触发 L0-L4 修改

```python
class CoordinativeLayer:
    def __init__(self, ...):
        self.l0l4_evolution = L0L4EvolutionManager()
    
    def on_self_ref_intention(self, intention: Intention):
        """自引用系统生成意图，需要修改 L0-L4。"""
        if intention.type == "expand_level":
            # 创建修改提案
            proposal = self.l0l4_evolution.create_proposal(
                change_type="structural",  # 新增节点是结构级
                delta=self._generate_delta_for_expansion(intention),
                author=f"self-ref:{intention.cycle_id}",
                rationale=intention.description,
            )
            
            # 提交审查（自动进入队列）
            review_result = self.l0l4_evolution.submit_for_review(proposal)
            
            # 如果通过，自动生效（如果审查是自动的）
            # 如果需要人工，进入待审队列
            return review_result
    
    def on_compression_match(self, node: Node, l0l4_mapping: L0L4Mapping):
        """压缩时发现节点可匹配到 L0-L4，但匹配度不高，建议修改 L0-L4。"""
        # 生成属性级修改（补充 aliases/keywords）
        proposal = self.l0l4_evolution.create_proposal(
            change_type="attribute",
            delta=self._generate_delta_for_enrichment(node, l0l4_mapping),
            author="system:compression",
            rationale=f"Compression match enrichment for {node.id}",
        )
        
        # 属性级修改通常自动通过
        return self.l0l4_evolution.submit_for_review(proposal)
```

### 7.2 L0-L4 修改触发协同层响应

```python
class L0L4EvolutionManager:
    def after_commit_applied(self, commit: L0L4Commit):
        """提交生效后，通知协同层执行后续操作。"""
        
        # 1. 更新反向索引
        self.index_manager.update_reverse_index(commit.delta)
        
        # 2. 标记引用该节点的下游假设为 "stale"（需要重新验证）
        affected_nodes = commit.scope
        for node_id in affected_nodes:
            downstream = self._get_downstream_hypotheses(node_id)
            for hyp in downstream:
                hyp.mark_stale(reason=f"L0-L4 node {node_id} modified in commit {commit.commit_id}")
        
        # 3. 触发对偶器重新计算（如果修改影响节点特征）
        if commit.change_type in ("structural", "meta"):
            self.dual_matcher.invalidate_cache_for(affected_nodes)
        
        # 4. 记录到同步日志
        self.sync_log.record_l0l4_change(commit)
```

---

## 8. 实施计划

### Phase 1：版本控制基础（2-3天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 提交模型 | `l0l4/evolution/commit.py` | L0L4Commit, L0L4Delta, 不可变提交 |
| 分支管理 | `l0l4/evolution/branch.py` | Branch, MergeRequirements |
| 事务原子性 | `l0l4/evolution/transaction.py` | L0L4Transaction, 原子apply/rollback |
| 历史存储 | `persistence/schema_l0l4_evolution.sql` | commit_history表 |

### Phase 2：幅度控制（2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 幅度控制器 | `l0l4/evolution/amplitude.py` | AmplitudeController, 限制规则 |
| 影响分析器 | `l0l4/evolution/impact.py` | ImpactAnalyzer, 波及范围计算 |
| 修改分级 | `l0l4/evolution/classification.py` | 自动判断change_type |

### Phase 3：冗余审查（2-3天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 审查系统 | `l0l4/evolution/review.py` | ReviewSystem, 投票机制 |
| 规则引擎审查 | `l0l4/evolution/review_rule.py` | 自动化规则检查 |
| 自引用审查 | `l0l4/evolution/review_self_ref.py` | 结构改善/退化评估 |
| 人工审查队列 | `l0l4/evolution/review_human.py` | 待审队列、通知、超时处理 |

### Phase 4：审计与回溯（1-2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 差异比对 | `l0l4/evolution/diff.py` | L0L4Diff, blame |
| 时间点恢复 | `l0l4/evolution/recovery.py` | PointInTimeRecovery |
| 快照管理 | `l0l4/evolution/snapshot.py` | 自动快照创建 |

### Phase 5：集成（2天）

| 任务 | 说明 |
|------|------|
| 协同层集成 | 协同层触发L0-L4修改 |
| 自引用集成 | 自引用意图→L0-L4修改提案 |
| CLI接口 | `lcortex l0l4 commit`, `lcortex l0l4 diff`, `lcortex l0l4 blame` |

---

## 9. 风险与边界

| 风险 | 缓解措施 |
|------|---------|
| 提交历史无限增长 | 自动归档：30天前的完整快照压缩，仅保留diff链 |
| 审查队列堆积 | 超时自动拒绝（保守策略）+ 审查优先级分级 |
| 自引用系统误判 | 人工override机制，always允许人工final decision |
| 并发修改冲突 | 分支隔离 + 乐观锁 + 合并冲突检测 |
| 误删公理 | 公理删除自动拒绝（规则引擎）+ 需两人人工override |

---

## 10. 一句话总结

**L0-L4 的修改不是"想改就改"，而是"提案→幅度检查→三重审查→审计记录→原子生效"的完整闭环。版本控制保证可追溯，幅度控制保证不地震，冗余审查保证不独裁，审计回溯保证可纠正。这是系统的"宪法修正案"机制。**

---

*文档版本: v1.0-DRAFT*
*日期: 2026-06-20*
*作者: 合作 (OpenClaw)*
