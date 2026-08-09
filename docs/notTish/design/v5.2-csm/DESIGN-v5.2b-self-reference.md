# Literature Cortex v5.2b 设计方案：自引用机制 (Self-Reference)

> **文档编号:** LC-DESIGN-v5.2b
> **版本:** v5.2b-DRAFT
> **状态:** ⏸️ BLOCKED（等待前置条件）
> **完成度:** 30%
> **日期:** 2026-06-16
> **依赖:** v5.2a 对偶器（需先完成批量应用）
> **注册表:** 参见 `DESIGN-REGISTRY.md` 第 #design-文档清单 节
> **核心目标:** 让系统能反思自己的知识结构，识别盲区并主动扩展

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-16 | v5.2b-DRAFT | 初始设计完成，启用条件未满足 |

---

## 1. 问题陈述

### 1.1 当前系统的盲区

v5.2 + v5.2a 解决了"单节点多视角"问题，但系统仍然是被动的：

- 节点由外部输入（文献提取、人工录入）
- 视角由关键词匹配或对偶器生成
- 系统不会问自己："我还缺什么？"

**示例盲区：**

```
当前图谱：
  L1: causality-principle → signal-propagation-delay
  L2: wiener-hopf → gradient-descent
  L3: fxlms → lms
  L4: mimo-fxlms → single-channel-anc
  L5: fpga-real-time → fixed-point-arithmetic
  L6: convergence-proof → failure-modes

缺失（系统不自知）：
  - L1 到 L2 之间缺少"数学变换"桥梁（如傅里叶变换、拉普拉斯变换）
  - L3 到 L4 之间缺少"系统架构设计"（如分布式控制、MIMO拓扑）
  - 跨域连接：振动控制 ↔ 热控（thermal-vibration-coupling 孤立存在）
```

### 1.2 自引用的定义

**自引用 = 系统把自身知识图谱作为对象进行反思和操作。**

不是"知道 FxLMS 是什么"，而是"知道我知道 FxLMS，但不知道它的热控耦合形式"。

---

## 2. 自引用的三层架构

```
┌─────────────────────────────────────────────────────────────┐
│              Layer 3: 意图生成 (Intention Generation)         │
│  "系统想要什么？"                                            │
│  • 识别知识盲区                                              │
│  • 生成探索意图（如"需要找到热-振耦合的数学形式"）              │
│  • 评估当前图谱的完整性                                       │
└─────────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────────┐
│              Layer 2: 结构反思 (Structural Reflection)        │
│  "系统的知识结构长什么样？"                                   │
│  • 层级完整性检查（L1-L6 每层是否有足够节点）                   │
│  • 跨层连接密度（每层到相邻层的边数）                         │
│  • 域覆盖度（哪些领域只有孤立节点）                           │
│  • 视角多样性（哪些节点只有单视角）                           │
└─────────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────────┐
│              Layer 1: 元数据自指 (Meta-Self-Reference)        │
│  "系统知道自己在知道什么？"                                   │
│  • 节点总数、边总数、层级分布                                 │
│  • 视角统计、对偶匹配统计                                     │
│  • 验证历史、发散方向统计                                     │
│  • 矛盾归档记录                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 各层详细设计

### 3.1 Layer 1: 元数据自指

**功能：** 系统能查询自己的统计信息，如同查询外部数据库。

```python
class SelfReferenceLayer1:
    """元数据自指层。"""
    
    def __init__(self, store: ConvergentStoreV2):
        self.store = store
    
    def get_knowledge_summary(self) -> dict:
        """获取知识图谱的自描述摘要。"""
        stats = self.store.stats()
        
        # 视角统计
        conn = self.store._connect()
        perspective_stats = conn.execute('''
            SELECT knowledge_level, COUNT(*) 
            FROM node_perspectives 
            GROUP BY knowledge_level
        ''').fetchall()
        
        multi_perspective_count = conn.execute('''
            SELECT COUNT(DISTINCT node_id) 
            FROM node_perspectives 
            GROUP BY node_id 
            HAVING COUNT(*) > 1
        ''').fetchone()[0]
        
        conn.close()
        
        return {
            "total_nodes": stats["nodes"],
            "total_edges": stats["edges"],
            "level_distribution": stats["level_distribution"],
            "perspective_distribution": {r[0]: r[1] for r in perspective_stats},
            "multi_perspective_ratio": multi_perspective_count / stats["nodes"],
            "semantic_distribution": stats["semantic_distribution"],
        }
    
    def get_blind_spots(self) -> list[BlindSpot]:
        """识别明显的知识盲区。"""
        spots = []
        
        # 盲区1：只有单视角的节点
        single_perspective = self._get_single_perspective_nodes()
        if single_perspective:
            spots.append(BlindSpot(
                type="under_perspectived",
                severity=len(single_perspective) / self.store.stats()["nodes"],
                description=f"{len(single_perspective)} 个节点只有单视角",
                suggestion="运行对偶器 enrich_all_single_perspective_nodes()",
            ))
        
        # 盲区2：某层级节点过少
        level_dist = self.store.stats()["level_distribution"]
        for level in ["L1", "L2", "L3", "L4", "L5", "L6"]:
            count = level_dist.get(level, 0)
            if count < 2:
                spots.append(BlindSpot(
                    type="level_sparse",
                    severity=0.8,
                    description=f"{level} 层级只有 {count} 个节点",
                    suggestion=f"需要补充 {level} 层级的概念",
                ))
        
        # 盲区3：跨层连接稀疏
        cross_layer_edges = self._count_cross_layer_edges()
        total_edges = self.store.stats()["edges"]
        if total_edges > 0 and cross_layer_edges / total_edges < 0.3:
            spots.append(BlindSpot(
                type="low_cross_layer_connectivity",
                severity=0.6,
                description=f"跨层边比例仅 {cross_layer_edges/total_edges:.1%}",
                suggestion="增加层级间的 causal_semantics 边",
            ))
        
        return spots
```

### 3.2 Layer 2: 结构反思

**功能：** 系统分析自己的知识结构，识别模式缺陷。

```python
class SelfReferenceLayer2:
    """结构反思层。"""
    
    def __init__(self, layer1: SelfReferenceLayer1):
        self.layer1 = layer1
    
    def analyze_structure(self) -> StructureReport:
        """分析知识图谱的结构健康度。"""
        summary = self.layer1.get_knowledge_summary()
        
        # 检查1：层级完整性
        level_completeness = self._check_level_completeness()
        
        # 检查2：跨域隔离度
        domain_isolation = self._check_domain_isolation()
        
        # 检查3：演绎闭环率
        closure_rate = self._check_deductive_closure()
        
        return StructureReport(
            level_completeness=level_completeness,
            domain_isolation=domain_isolation,
            closure_rate=closure_rate,
            overall_health=(level_completeness + (1-domain_isolation) + closure_rate) / 3,
        )
    
    def _check_level_completeness(self) -> float:
        """检查 L1-L6 每层是否有足够节点（至少2个）。"""
        level_dist = self.layer1.store.stats()["level_distribution"]
        complete_levels = sum(1 for level in ["L1", "L2", "L3", "L4", "L5", "L6"]
                             if level_dist.get(level, 0) >= 2)
        return complete_levels / 6
    
    def _check_domain_isolation(self) -> float:
        """检查是否存在孤立域（无跨域边）。"""
        # 统计每个域的节点和跨域边
        # 返回：孤立域比例
        pass
    
    def _check_deductive_closure(self) -> float:
        """检查演绎闭环率：有多少边是通过演绎生成的。"""
        # 统计 derived edges / total edges
        pass
```

### 3.3 Layer 3: 意图生成

**功能：** 系统基于结构反思结果，生成主动探索意图。

```python
class SelfReferenceLayer3:
    """意图生成层。"""
    
    def __init__(self, layer2: SelfReferenceLayer2):
        self.layer2 = layer2
    
    def generate_intentions(self) -> list[Intention]:
        """生成系统的主动探索意图。"""
        report = self.layer2.analyze_structure()
        intentions = []
        
        # 意图1：如果某层级稀疏，生成"补充该层级"的意图
        if report.level_completeness < 1.0:
            sparse_levels = self._get_sparse_levels()
            for level in sparse_levels:
                intentions.append(Intention(
                    type="expand_level",
                    target=level,
                    priority=0.8,
                    description=f"补充 {level} 层级的概念节点",
                    action="search_literature",
                    query=f"{level} 基础概念 {self._get_domain_context()}",
                ))
        
        # 意图2：如果跨域隔离度高，生成"建立跨域桥接"的意图
        if report.domain_isolation > 0.3:
            isolated_domains = self._get_isolated_domains()
            for domain in isolated_domains:
                intentions.append(Intention(
                    type="bridge_domains",
                    target=domain,
                    priority=0.7,
                    description=f"建立 {domain} 与其他域的连接",
                    action="run_dual_matcher",
                    query=domain,
                ))
        
        # 意图3：如果演绎闭环率低，生成"扩展规则集"的意图
        if report.closure_rate < 0.3:
            intentions.append(Intention(
                type="expand_rules",
                target="deduction_rules",
                priority=0.6,
                description="扩展正向演绎规则集",
                action="analyze_rule_gaps",
            ))
        
        return sorted(intentions, key=lambda i: i.priority, reverse=True)
```

---

## 4. 自引用循环

```
┌─────────────────────────────────────────────────────────────┐
│                    自引用循环 (Self-Reference Loop)            │
│                                                             │
│  Step 1: Layer 1 收集元数据                                  │
│     ↓                                                       │
│  Step 2: Layer 2 分析结构                                   │
│     ↓                                                       │
│  Step 3: Layer 3 生成意图                                   │
│     ↓                                                       │
│  Step 4: 执行意图（搜索文献 / 运行对偶器 / 扩展规则）          │
│     ↓                                                       │
│  Step 5: 更新知识图谱                                       │
│     ↓                                                       │
│  Step 6: 回到 Step 1（新一轮自引用）                         │
│                                                             │
│  触发条件：                                                 │
│  - 定时触发：每天 03:00 运行一次                             │
│  - 事件触发：新增节点数 > 10 时运行                          │
│  - 人工触发：用户执行 `lcortex self-reflect`                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 与 v5.2/v5.2a 的集成

```python
class MetaCognitiveArbiter:
    def __init__(self, ...):
        ...
        # v5.2b 新增：自引用三层
        self.self_ref_l1 = SelfReferenceLayer1(convergent_store)
        self.self_ref_l2 = SelfReferenceLayer2(self.self_ref_l1)
        self.self_ref_l3 = SelfReferenceLayer3(self.self_ref_l2)
    
    def self_reflect(self) -> ReflectionReport:
        """运行完整的自引用循环。"""
        # Layer 1: 元数据
        summary = self.self_ref_l1.get_knowledge_summary()
        
        # Layer 2: 结构反思
        structure = self.self_ref_l2.analyze_structure()
        
        # Layer 3: 意图生成
        intentions = self.self_ref_l3.generate_intentions()
        
        # 执行高优先级意图
        executed = []
        for intent in intentions[:3]:  # 每次最多执行 3 个意图
            if intent.type == "expand_level":
                # 提示用户需要补充文献
                executed.append(intent)
            elif intent.type == "bridge_domains":
                # 运行对偶器
                self.dual_matcher.enrich_all_single_perspective_nodes()
                executed.append(intent)
            elif intent.type == "expand_rules":
                # 分析规则缺口
                executed.append(intent)
        
        return ReflectionReport(
            summary=summary,
            structure=structure,
            intentions=intentions,
            executed=executed,
        )
```

---

## 6. 启用条件

| 条件 | 当前状态 | 建议 |
|------|---------|------|
| 节点数 ≥ 50 | 17 ❌ | 继续扩展文献输入 |
| 多视角比例 ≥ 70% | 65% ❌ | 先完成对偶器批量应用 |
| 跨域节点 ≥ 2 个域 | 1 个域 ❌ | 需要引入热控/切削等域 |
| 规则集 ≥ 10 条 | 3 类 ❌ | 扩展演绎规则 |

**结论：** 自引用机制在当前 17 节点 demo 数据上无法有效运行。建议：
1. 先完成对偶器的批量应用（让多视角比例达到 80%+）
2. 扩展节点规模到 50+
3. 引入至少 2 个域（振动控制 + 热控）
4. 然后启用自引用循环

---

## 7. 一句话总结

**自引用是系统的「自我意识」——不是知道 FxLMS 是什么，而是知道"我知道 FxLMS，但我不知道它的热控耦合形式，所以我应该去找"。当前节点太少，自我意识没有素材。先养大身体，再觉醒灵魂。**

---

*设计方案版本: v5.2b-DRAFT*  
*撰写日期: 2026-06-16*  
*作者: 合作 (OpenClaw)*
