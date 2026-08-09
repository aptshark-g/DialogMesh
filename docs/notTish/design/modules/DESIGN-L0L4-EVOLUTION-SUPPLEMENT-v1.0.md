# Literature Cortex — L0-L4 数据驱动演化机制（补充设计）

> **文档编号:** LC-L0L4-EVOLUTION-SUPPLEMENT
> **版本:** v1.0
> **日期:** 2026-06-20
> **核心目标:** 不是人工添加，而是系统从运行数据中自发发现值得加入 L0-L4 的概念

---

## 1. 核心原则

L0-L4 的演化不是管理员驱动的"新增节点"，而是系统从运行数据中**自发发现**的"概念升格"。

> 一个概念值得进入 L0-L4，不是因为它"看起来重要"，而是因为它在系统运行中**反复出现**、**跨领域共享**、**被解构时多次提及**。

---

## 2. 触发条件：三重信号

### 2.1 使用频率（高频使用）

```python
class UsageFrequencyTrigger:
    """使用频率触发器。"""
    
    THRESHOLD_COLD = 3      # 3次以上被引用 → 进入观察列表
    THRESHOLD_WARM = 10     # 10次以上 → 进入候选列表
    THRESHOLD_HOT = 50      # 50次以上 → 强制生成提案
    
    WINDOW_DAYS = 30        # 统计窗口：30天
    
    def evaluate(self, node_id: str) -> FrequencySignal:
        """评估节点的使用频率。"""
        # 统计：收敛层引用、发散层引用、用户查询、跨域类比中的出现
        stats = self._get_usage_stats(node_id, window_days=self.WINDOW_DAYS)
        
        total_refs = (
            stats.convergent_refs +      # 收敛层验证时引用
            stats.divergent_refs +       # 发散层假设中引用
            stats.user_queries +         # 用户直接查询
            stats.analogy_matches        # 跨域类比中作为桥接
        )
        
        if total_refs >= self.THRESHOLD_HOT:
            return FrequencySignal(level="HOT", count=total_refs, action="propose")
        elif total_refs >= self.THRESHOLD_WARM:
            return FrequencySignal(level="WARM", count=total_refs, action="observe")
        elif total_refs >= self.THRESHOLD_COLD:
            return FrequencySignal(level="COLD", count=total_refs, action="log")
        
        return FrequencySignal(level="NONE", count=total_refs, action="ignore")
```

**引用来源统计：**
- 收敛层引用：节点在正向演绎、验证、规则匹配中被作为前提或结论
- 发散层引用：节点在反事实破坏、溯因假设、倒置因果中被作为替代或桥接
- 用户查询：用户直接查询该节点或以其为起点探索
- 类比匹配：跨域类比中该节点被作为共享结构

### 2.2 根基性（跨领域共享）

```python
class RootednessTrigger:
    """根基性触发器：概念是否被多个领域共享。"""
    
    THRESHOLD_DOMAIN_COUNT = 3   # 至少3个领域引用 → 候选
    THRESHOLD_DEPTH = 2          # 类比深度至少2层（不是表面相似）
    
    def evaluate(self, node_id: str) -> RootednessSignal:
        """评估概念的根基性。"""
        # 获取该节点在跨域类比中的出现
        analogies = self._get_analogies_involving(node_id)
        
        # 统计涉及的领域
        domains = set()
        for analogy in analogies:
            domains.add(analogy.source_domain)
            domains.add(analogy.target_domain)
        
        # 统计深度：该节点在类比中作为什么角色
        roles = self._get_analogy_roles(node_id)
        deep_roles = [r for r in roles if r.depth >= self.THRESHOLD_DEPTH]
        
        if len(domains) >= self.THRESHOLD_DOMAIN_COUNT and len(deep_roles) > 0:
            return RootednessSignal(
                level="ROOT",
                domain_count=len(domains),
                domains=list(domains),
                deep_role_count=len(deep_roles),
                action="propose"
            )
        
        return RootednessSignal(level="SHALLOW", domain_count=len(domains), action="log")
```

**根基性判断标准：**
- 不是"被多个领域提到"，而是"被多个领域作为**底层约束**引用"
- 例如："信号传播延迟"在控制、通信、热控中都被作为物理前提 → 根基性强
- 反例："FxLMS"在控制领域高频使用，但在其他领域很少作为底层约束 → 根基性弱（应留在L3，不升L2）

### 2.3 解构频率（发散层多次提及）

```python
class DeconstructionTrigger:
    """解构频率触发器：概念在发散层被多次提及。"""
    
    THRESHOLD_MENTIONS = 5       # 5次以上在解构中被提及
    THRESHOLD_AS_BRIDGE = 3      # 3次以上作为桥接概念
    
    def evaluate(self, node_id: str) -> DeconstructionSignal:
        """评估概念在解构中的出现频率。"""
        # 反事实破坏：作为替代路径的关键节点
        counterfactual_as_alternative = self._count_counterfactual_alternative(node_id)
        
        # 溯因假设：作为中间解释节点
        abductive_as_intermediate = self._count_abductive_intermediate(node_id)
        
        # 倒置因果：作为约束调整的目标
        inverted_as_constraint = self._count_inverted_constraint(node_id)
        
        total_mentions = (
            counterfactual_as_alternative +
            abductive_as_intermediate +
            inverted_as_constraint
        )
        
        bridge_count = self._count_as_bridge(node_id)  # 跨域类比中的桥接
        
        if total_mentions >= self.THRESHOLD_MENTIONS and bridge_count >= self.THRESHOLD_AS_BRIDGE:
            return DeconstructionSignal(
                level="BRIDGE",
                total_mentions=total_mentions,
                bridge_count=bridge_count,
                action="propose"
            )
        
        return DeconstructionSignal(level="MENTIONED", total_mentions=total_mentions, action="log")
```

**解构中的角色：**
- **反事实替代**：链路 A→B→C 被破坏后，A→D→C 中的 D 被反复选中 → D 是"隐藏的关键节点"
- **溯因桥接**：观察 A 和 C 后，D 作为最可能的中间解释被反复推断 → D 是"知识断裂中的默认填充"
- **约束调整目标**：倒置因果中，约束 c 的修改反复影响结果 → c 是"系统的敏感控制点"
- **跨域桥接**：两个领域的类比中，D 作为结构映射的中间点 → D 是"跨域通用结构"

---

## 3. 冗余检测（加入前检查）

### 3.1 冗余定义

```python
class RedundancyChecker:
    """冗余检测器。"""
    
    SIMILARITY_THRESHOLD = 0.85   # 语义相似度 > 0.85 → 视为冗余
    COVERAGE_THRESHOLD = 0.9      # 已有节点组合覆盖率 > 0.9 → 视为冗余
    
    def check(self, candidate: Node) -> RedundancyReport:
        """检查候选概念是否冗余。"""
        
        # 检查1：直接语义相似
        similar_nodes = self._find_semantically_similar(candidate, threshold=self.SIMILARITY_THRESHOLD)
        if similar_nodes:
            return RedundancyReport(
                is_redundant=True,
                reason="语义相似",
                similar_nodes=similar_nodes,
                recommendation="补充已有节点的aliases/keywords，不新增节点"
            )
        
        # 检查2：已有节点的组合覆盖
        coverable = self._check_combinatorial_coverage(candidate)
        if coverable.is_covered:
            return RedundancyReport(
                is_redundant=True,
                reason="组合可覆盖",
                cover_nodes=coverable.nodes,
                recommendation="新增关系边，不新增节点"
            )
        
        # 检查3：别名/关键词重叠
        alias_overlap = self._check_alias_overlap(candidate)
        if alias_overlap.score > 0.7:
            return RedundancyReport(
                is_redundant=True,
                reason="别名重叠",
                overlapping_aliases=alias_overlap.matches,
                recommendation="合并到已有节点，扩展aliases"
            )
        
        return RedundancyReport(is_redundant=False, reason="无冗余")
```

### 3.2 冗余检测的三层防线

| 防线 | 机制 | 示例 |
|------|------|------|
| **直接相似** | 语义相似度 > 0.85 | 候选"梯度流" vs 已有"梯度下降" → 补充aliases |
| **组合覆盖** | 两个已有节点的组合描述同一概念 | 候选"热-振耦合" = 已有"热传导" + "振动" + 关系边 → 新增边，不新增节点 |
| **别名重叠** | 关键词重叠 > 70% | 候选"自适应滤波器" vs 已有"自适应算法" → 合并aliases |

### 3.3 非冗余的判定标准

候选概念**不冗余**当且仅当：
- 语义相似度 < 0.85（与所有已有节点）
- 无法被两个以内已有节点的组合覆盖
- 引入新的**约束类型**或**推理模式**（不只是新实例）

---

## 4. 演化闭环

```
系统运行（收敛/发散/类比）
    ↓
激活度日志 + 解构日志 + 类比日志
    ↓
触发器评估（频率/根基/解构）
    ↓
满足条件 → 候选列表
    ↓
冗余检测（三层防线）
    ↓
通过 → 生成提案（属性级/关系级/结构级）
    ↓
幅度控制（单轮限制）
    ↓
冗余审查（2/3投票）
    ↓
通过 → 原子生效 + 审计记录
    ↓
更新反向索引 + 标记下游假设为stale
    ↓
下一轮运行...
```

---

## 5. 与协同层的集成

### 5.1 协同层触发 L0-L4 演化

```python
class CoordinativeLayer:
    def run_macro_beat(self):
        """主节拍：执行完整压缩 + L0-L4 演化检查。"""
        
        # 1. 常规压缩
        self.compression_pipeline.run()
        
        # 2. L0-L4 演化检查（新增）
        self._check_l0l4_evolution()
    
    def _check_l0l4_evolution(self):
        """检查是否有候选概念值得加入 L0-L4。"""
        
        # 从激活度日志获取高频节点（非L0-L4的）
        hot_nodes = self.activation_tracker.get_hot_nodes(
            exclude_l0l4=True,  # 只考虑非L0-L4节点
            threshold=10,       # 10次以上引用
            window_days=30
        )
        
        for node_id in hot_nodes:
            # 三重触发评估
            freq_signal = self.freq_trigger.evaluate(node_id)
            root_signal = self.rootedness_trigger.evaluate(node_id)
            decon_signal = self.deconstruction_trigger.evaluate(node_id)
            
            # 至少两个触发器达到"propose"级别
            propose_count = sum([
                freq_signal.action == "propose",
                root_signal.action == "propose",
                decon_signal.action == "propose"
            ])
            
            if propose_count >= 2:
                # 获取节点完整信息
                candidate = self.store.get_node(node_id)
                
                # 冗余检测
                redundancy = self.redundancy_checker.check(candidate)
                
                if not redundancy.is_redundant:
                    # 生成结构级提案（新增节点）
                    proposal = self.l0l4_evolution.create_proposal(
                        change_type="structural",
                        delta=self._generate_new_node_delta(candidate),
                        author="system:evolution",
                        rationale=f"Triple-signal trigger: freq={freq_signal.level}, "
                                  f"rootedness={root_signal.level}, "
                                  f"deconstruction={decon_signal.level}",
                        trigger_signals={
                            "frequency": freq_signal.to_dict(),
                            "rootedness": root_signal.to_dict(),
                            "deconstruction": decon_signal.to_dict(),
                        }
                    )
                    
                    # 提交审查
                    self.l0l4_evolution.submit_for_review(proposal)
                
                else:
                    # 冗余 → 执行推荐操作（补充aliases或新增边）
                    self._execute_redundancy_recommendation(candidate, redundancy)
```

### 5.2 演化日志的特殊标记

```sql
-- L0-L4 演化提案表（触发信号详细记录）
CREATE TABLE l0l4_evolution_proposals (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    
    -- 触发信号（三重）
    trigger_frequency_level TEXT,      -- HOT / WARM / COLD
    trigger_frequency_count INTEGER,
    trigger_rootedness_level TEXT,     -- ROOT / SHALLOW
    trigger_rootedness_domains TEXT,   -- JSON: ["control", "thermal", ...]
    trigger_deconstruction_level TEXT, -- BRIDGE / MENTIONED
    trigger_deconstruction_mentions INTEGER,
    
    -- 冗余检测结果
    redundancy_check_passed INTEGER,   -- 0/1
    redundancy_reason TEXT,            -- 冗余原因（如果未通过）
    
    -- 提案状态
    status TEXT CHECK(status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    
    -- 关联到 commit_history
    commit_id TEXT,                    -- 如果最终生效，关联的commit
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. 关键设计决策

### 6.1 为什么需要三重触发，而不是单一触发

- 仅高频使用：可能是领域专有概念（如"FxLMS"），不适合升格到L0-L4
- 仅根基性：可能是孤立的多领域术语，但缺乏内部结构支撑
- 仅解构频率：可能是发散层的幻觉产物，需要其他信号验证
- **三重同时满足**：概念既有使用价值、又有跨域通用性、又被系统自发发现为结构关键点

### 6.2 为什么冗余检测必须前置

L0-L4的膨胀比缺失更危险：
- 冗余节点 → 反向索引歧义 → 领域分类错误
- 冗余节点 → 对偶器锚点分散 → 概念浮动失准
- 冗余节点 → 演绎规则冲突 → 推理不一致

**宁可少加一个，不要多加一个。**

### 6.3 人类在循环中的位置

- 系统自动发现候选、自动检测冗余、自动提案
- **但生效前，结构级修改必须人工审查**
- 人类审查的重点不是"是否值得加入"（系统已经筛选过），而是"是否有遗漏的冗余"和"层级归属是否正确"

---

## 7. 一句话总结

**L0-L4的演化是"系统发现自己需要什么"，而不是"人告诉系统该有什么"。使用频率、跨域根基性、解构桥接性三个信号共同触发，冗余检测前置过滤，审查后生效。系统运行时自己长出来的骨骼，比人工移植的骨头更稳。**

---

*补充文档版本: v1.0*
*日期: 2026-06-20*
*作者: 合作 (OpenClaw)*
*说明: 本文档补充 DESIGN-L0L4-EVOLUTION-v1.0.md 的"触发条件"部分，明确数据驱动的发现机制*
