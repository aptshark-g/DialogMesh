# Literature Cortex v5.4 设计方案：协同层 (Coordinative Layer)

> **文档编号:** LC-DESIGN-v5.4
> **版本:** v5.4-DRAFT
> **状态:** 📋 DRAFT
> **完成度:** 100%（设计）/ 0%（实现）
> **日期:** 2026-06-20
> **依赖:** v5.3 比例控制 + v5.2b 自引用 + 发散层 v0.1 + L0-L4 种子库
> **注册表:** 参见 `DESIGN-REGISTRY.md`
> **核心目标:** 将神经科学的系统巩固、元认知控制、主动遗忘机制工程化，适配计算系统的资源约束

---

## 修正声明（从神经科学到工程化）

| 神经科学机制 | 原始设计 | 修正后 |
|-----------|---------|--------|
| 睡眠巩固（夜间批量） | 每天03:00固定运行 | **可配置间隔 + 空闲检测**：用户不持续运行时，小间隔（5-30分钟）触发轻量压缩 |
| 主动遗忘（默认路径） | 概念退化后删除或归档 | **压缩迁移至低效区**：释放活跃区资源，内容可恢复，非彻底删除 |
| 记忆抽象化（gist提取） | 独立抽象化层 | **直接调用L0-L4公理化库**：草稿内容经L0-L4结构匹配后，归入对应抽象层级 |

---

## 1. 问题陈述

### 1.1 当前系统的资源困境

Literature Cortex 运行中积累的问题是**资源性的，不是知识性的**：

- 假设层膨胀：每轮发散生成假设，验证后未通过的假设堆积
- 草稿层堆积：LLM生成的中间分析、管道输出、临时文件
- 激活表膨胀：节点激活记录随时间线性增长
- 方向统计过时：早期任务的验证历史不再反映当前系统能力
- 跨层引用断裂：收敛层引用已退化的节点，发散层假设基于已失效的链路

**核心问题：系统不会"自己整理"——它只会不断生产，从不清理。**

### 1.2 协同层的重新定义

> 协同层不是"第三层"，而是"渗透层"——在收敛/发散的运行间隙中，执行资源整理、跨层对齐、内容压缩。

**类比操作系统：**
- 收敛层 = 用户进程（执行任务）
- 发散层 = 后台服务（生成假设）
- 协同层 = 内核调度器 + 内存管理器（资源回收、页面置换、缓存管理）

**关键原则：** 协同层**不干预**收敛/发散的核心逻辑，只在**空闲窗口**或**定时触发**时执行整理。

---

## 2. 核心架构：三节拍协调模型

### 2.1 协调节拍（Coordination Beat）

从神经科学的"慢振荡"机制工程化，但改为**可配置的多级节拍**：

```python
class CoordinationConfig:
    """协同层配置。"""
    
    # 微节拍：每次任务完成后（毫秒级）
    micro_beat_interval_ms: int = 100  # 轻量日志更新
    
    # 次节拍：程序空闲时或固定间隔（分钟级）
    meso_beat_interval_min: int = 5    # 跨层同步、健康检查
    
    # 主节拍：深度压缩（小时级，可配置）
    macro_beat_interval_hours: int = 1  # 完整压缩、草稿归档
    
    # 空闲检测阈值：CPU/IO低于此值时，提前触发主节拍
    idle_cpu_threshold: float = 0.2
    idle_io_threshold: float = 0.1
```

**空闲检测机制：**
```python
class IdleDetector:
    def is_idle(self) -> bool:
        """检测系统是否空闲。"""
        # 检测1：无活跃任务
        # 检测2：CPU使用率 < threshold
        # 检测3：IO等待 < threshold
        # 检测4：用户无输入（>5分钟）
        # 如果空闲，可以提前触发主节拍
        pass
```

**三节拍职责：**

| 节拍 | 触发条件 | 执行内容 | 资源消耗 |
|------|---------|---------|---------|
| 微节拍 | 每次任务完成 | 更新激活度日志、更新方向统计 | 极低（<1ms） |
| 次节拍 | 每5分钟或空闲时 | 健康检查、跨层同步、引用修复 | 低（<100ms） |
| 主节拍 | 每1小时或深度空闲 | 压缩归档、草稿整理、L0-L4匹配 | 中等（秒级） |

### 2.2 与神经科学的映射

| 神经机制 | 工程化映射 | 调整原因 |
|---------|-----------|---------|
| 慢振荡（SO，~1Hz） | 主节拍（1小时） | 计算系统不需要生理节律，按资源压力配置 |
| 纺锤波（Spindles，12-14Hz） | 次节拍（5分钟） | 跨层同步窗口，批量处理而非逐事件 |
| 海马涟漪（Ripples，100-250Hz） | 微节拍（任务完成） | 激活度更新，即时但极轻量 |
| 睡眠状态检测 | 空闲检测（IdleDetector） | 程序无"睡眠"，但有"空闲" |

## 2.3 全局权重重标定（突触缩放）

> **神经科学来源：** Tononi & Cirelli (2006), González-Rueda et al. (2018)

**核心发现：** 睡眠期间所有突触按比例降低强度（统一降至~0.8），保留相对差异；弱突触被抹去，强突触保留，SNR从2.5提升至11.2。

**工程化：**

```python
class GlobalWeightRescaling:
    """全局权重重标定：主节拍执行，不是逐节点压缩，而是全局比例缩放。"""
    
    DOWNSCALE_RATE = 0.90      # 每轮全局缩放比例
    MIN_WEIGHT_THRESHOLD = 0.05  # 低于此值标记为可压缩
    HIGH_VALUE_PROTECT = 0.8     # 价值分>0.8的节点受保护
    PROTECT_BOOST = 1.15         # 保护节点反向增强
    
    def rescale(self, all_nodes: list[Node]) -> RescaleReport:
        """执行全局权重重标定。"""
        
        weights = [n.composite_weight for n in all_nodes]
        global_avg = sum(weights) / len(weights)
        w_min, w_max = min(weights), max(weights)
        
        # 自限制：分布过于均匀（极差 < 0.05）或全局平均已极低
        if w_max - w_min < 0.05:
            return RescaleReport(skipped=True, reason="distribution_uniform")
        if global_avg < 0.05:
            return RescaleReport(skipped=True, reason="already_low")
        
        for node in all_nodes:
            # 全局比例缩放（保留相对差异）
            node.composite_weight *= self.DOWNSCALE_RATE
            
            # 高价值节点保护（强者更强）
            if node.value_score > self.HIGH_VALUE_PROTECT:
                node.composite_weight *= self.PROTECT_BOOST
            
            node.composite_weight = clamp(node.composite_weight, 0.001, 1.0)
        
        # 标记可压缩
        compressible = [n for n in all_nodes if n.composite_weight < self.MIN_WEIGHT_THRESHOLD]
        for node in compressible:
            node.compression_flag = True
        
        return RescaleReport(
            global_avg_before=global_avg,
            global_avg_after=sum(n.composite_weight for n in all_nodes) / len(all_nodes),
            compressible_count=len(compressible),
            protected_count=sum(1 for n in all_nodes if n.value_score > self.HIGH_VALUE_PROTECT)
        )
```

**关键变化：** 压缩从"固定阈值"变为"相对排序"——始终压缩权重最低的N%节点。

### 3.1 模块一：跨层同步（Cross-Layer Sync）

**问题：** 收敛层验证节点A，发散层同时生成A的反事实假设，对偶器将A作为锚点——三者可能基于不同版本的A。

**机制：同步窗口（Sync Window）**

```python
class CrossLayerSync:
    """跨层同步器。"""
    
    def sync_window(self):
        """执行同步窗口：
        
        1. 暂停收敛层新任务入队（完成中的任务继续）
        2. 暂停发散层新假设生成
        3. 执行一致性检查
        4. 修复断裂引用
        5. 恢复两层运行
        """
        # 获取当前一致性快照
        snapshot = self._capture_snapshot()
        
        # 检查收敛层引用的节点是否仍在活跃层
        broken_refs = self._find_broken_references(snapshot)
        
        # 检查发散层假设是否基于已退化节点
        stale_hypotheses = self._find_stale_hypotheses(snapshot)
        
        # 修复
        for ref in broken_refs:
            self._redirect_to_limbo(ref)  # 指向limbo区的归档版本
        
        for hyp in stale_hypotheses:
            hyp.status = "stale"  # 标记为过时，不删除
            hyp.note = f"Base node {hyp.source_node} moved to limbo"
        
        # 记录同步日志
        self._log_sync(broken_refs, stale_hypotheses)
```

**同步范围：**
- 节点ID一致性（收敛层引用 → 持久化层存在）
- 视角一致性（node_perspectives 与 nodes_v2 的层级匹配）
- 假设来源一致性（假设的 source_node 未退化）
- 方向统计一致性（direction_stats 中的 seed_node_id 存在）

### 3.2 模块二：压缩归档（Compression Archive）

**核心原则：不是遗忘，是迁移。**

```python
class CompressionArchive:
    """压缩归档器：将低活跃内容从活跃区迁移到低效区/归档区。"""
    
    def compress(self, candidates: list[Node]):
        """压缩流程：
        
        1. 评估压缩价值（保留活跃区空间 vs 压缩成本）
        2. 生成压缩表示（保留核心语义，去除冗余上下文）
        3. 迁移至 limbo_nodes（可恢复）或 archive_nodes（长期存储）
        4. 更新活跃区引用（指向压缩版本）
        5. 释放资源（SQLite VACUUM、缓存清理）
        """
        for node in candidates:
            # 评估
            if node.value_score < self.value_threshold:
                target = "archive"  # 低价值 → 归档区
            else:
                target = "limbo"    # 中等价值 → 低效区（可恢复）
            
            # 压缩表示
            compressed = self._compress_node(node)
            
            # 迁移
            self._migrate(node, compressed, target)
            
            # 更新引用
            self._update_references(node.id, compressed.id, target)
    
    def _compress_node(self, node: Node) -> CompressedNode:
        """节点压缩：保留核心，去除冗余。"""
        return CompressedNode(
            id=node.id,
            core_semantics=extract_core(node),  # 保留：what, why_exists, type
            l0l4_mapping=self._match_l0l4(node),  # 匹配到L0-L4的抽象层级
            edge_summary=compress_edges(node.edges),  # 边关系压缩为统计摘要
            full_content=node.to_json(),  # 完整内容备份（归档区）
            compression_ratio=0.3,  # 目标压缩到30%体积
        )
```

**压缩策略：**

| 内容类型 | 压缩方式 | 保留位置 |
|---------|---------|---------|
| 节点核心语义（what/why） | 保留原样 | 活跃区（如仍被引用） |
| 节点完整内容（content） | 完整JSON备份 | 归档区（archive_nodes） |
| 边关系（edges） | 统计摘要（入度/出度/主要连接） | 低效区（limbo_nodes） |
| 激活历史（activation） | 聚合统计（总访问/最后访问/趋势） | 低效区 |
| 验证历史（validation） | 通过率摘要 | 低效区 |

**L0-L4匹配（抽象化）：**

```python
def _match_l0l4(self, node: Node) -> L0L4Mapping:
    """将节点内容匹配到L0-L4的抽象层级。"""
    # 使用已有的L0-L4反向索引和领域分类器
    matched_abstract = l0l4_classifier.match(node.title + " " + node.what)
    
    # 返回抽象层级归属
    return L0L4Mapping(
        l0_axiom=matched_abstract.get("axiom"),      # 如：因果性公理
        l1_physics=matched_abstract.get("physics"),  # 如：信号传播
        l2_math=matched_abstract.get("math"),         # 如：Wiener-Hopf
        l3_algorithm=matched_abstract.get("algorithm"), # 如：FxLMS
        l4_system=matched_abstract.get("system"),     # 如：MIMO-ANC
    )
```

### 3.3 模块三：六维度节点评估与量化权重

> **核心原则：** 压缩决策不再依赖固定阈值，而是基于六维度的综合量化评分。

**六维度总览：**

| 维度 | 符号 | 含义 | 量化基础 | 衰减机制 | 权重 |
|------|------|------|---------|---------|------|
| **使用频率** | F | 被系统/用户引用的次数 | EMA计数器（7天半衰期） | 时间衰减 | 20% |
| **最近使用** | R | 最后一次使用距今天数 | 指数衰减函数 | 自然衰减 | 15% |
| **根基性** | G | 跨领域引用深度 | 领域覆盖×L0-L4引用×持久化匹配 | 静态 | 20% |
| **解构频率** | D | 发散层引用为桥接的次数 | EMA加权计数（14天半衰期） | 时间衰减 | 15% |
| **拓扑中心性** | C | 在网络中的结构重要性 | Weighted PageRank（阻尼0.85） | 网络演化重算 | 15% |
| **价值评估** | V | 人工/系统综合评分 | 高价值引用×跨层引用×恢复率修正 | 慢速EMA | 15% |

**使用频率（F）：**
```python
class FrequencyTracker:
    DECAY_HALF_LIFE = 7  # 7天半衰期
    
    def record_access(self, node: Node):
        now = time.time()
        days_since_last = (now - node.last_access_time) / 86400
        decay_factor = 0.5 ** (days_since_last / self.DECAY_HALF_LIFE)
        node.frequency_score = node.frequency_score * decay_factor + 1.0
        node.last_access_time = now
```

**最近使用（R）：**
```python
class RecencyTracker:
    def compute_recency(self, node: Node) -> float:
        if node.last_access_time is None:
            return 0.0
        days_ago = (time.time() - node.last_access_time) / 86400
        return math.exp(-days_ago / 10.0)  # 3天热，30天冷
```

**根基性（G）：**
```python
class GroundednessEvaluator:
    MIN_DOMAIN_COUNT = 3
    MAX_DOMAIN_COUNT = 10
    
    def compute_groundedness(self, node: Node) -> float:
        domains = set()
        for edge in node.incoming_edges:
            domains.add(edge.source_domain)
        for edge in node.outgoing_edges:
            domains.add(edge.target_domain)
        
        domain_coverage = min(len(domains) / self.MAX_DOMAIN_COUNT, 1.0)
        l0l4_refs = sum(1 for e in node.incoming_edges if e.source_level <= 4)
        depth_bonus = min(l0l4_refs / 3.0, 1.0)
        persistence_match = 1.0 if node.matched_l0l4 else 0.3
        
        return clamp(domain_coverage * 0.4 + depth_bonus * 0.3 + persistence_match * 0.3, 0.0, 1.0)
```

**解构频率（D）：**
```python
class DeconstructionTracker:
    DECAY_HALF_LIFE = 14
    TYPE_WEIGHTS = {
        "counterfactual": 1.0,
        "abduction": 1.2,
        "inverted_causality": 1.5,
        "analogy": 0.8
    }
    
    def record_deconstruction(self, node: Node, bridge_type: str):
        now = time.time()
        days_since_last = (now - node.last_decon_time) / 86400
        decay_factor = 0.5 ** (days_since_last / self.DECAY_HALF_LIFE)
        weight = self.TYPE_WEIGHTS.get(bridge_type, 1.0)
        node.deconstruction_score = node.deconstruction_score * decay_factor + weight
        node.last_decon_time = now
```

**拓扑中心性（C）：**
```python
class TopologyCentrality:
    """Weighted PageRank变体（Zhang et al. 2022）。"""
    DAMPING = 0.85
    ITERATIONS = 50
    
    def compute_pagerank(self, graph: Graph) -> dict[str, float]:
        N = len(graph.nodes)
        pr = {node.id: 1.0 / N for node in graph.nodes}
        
        for _ in range(self.ITERATIONS):
            new_pr = {}
            for node in graph.nodes:
                rank_sum = 0.0
                for edge in node.incoming_edges:
                    source = edge.source
                    weight = edge.weight if edge.weight else 1.0
                    out_strength = sum(e.weight for e in source.outgoing_edges)
                    if out_strength > 0:
                        rank_sum += pr[source.id] * weight / out_strength
                new_pr[node.id] = (1 - self.DAMPING) / N + self.DAMPING * rank_sum
            pr = new_pr
        
        max_pr = max(pr.values())
        return {k: v / max_pr for k, v in pr.items()}
```

**价值评估（V）：**
```python
class ValueEvaluator:
    def compute_value(self, node: Node) -> float:
        high_value_refs = sum(1 for e in node.incoming_edges if e.source.value_score > 0.8)
        cross_layer_refs = sum(1 for e in node.incoming_edges if e.source.layer != node.layer)
        system_score = min((high_value_refs * 0.3 + cross_layer_refs * 0.2) / 5.0, 1.0)
        human_score = node.human_value_rating if node.human_value_rating else 0.5
        
        if node.compress_count > 0:
            recovery_rate = node.recover_count / node.compress_count
            if recovery_rate > 0.5:
                system_score = min(system_score * (1 + recovery_rate * 0.3), 1.0)
        
        return clamp(system_score * 0.7 + human_score * 0.3, 0.0, 1.0)
```

**综合权重计算：**
```python
class CompositeWeightCalculator:
    WEIGHTS = {
        'frequency': 0.20,
        'recency': 0.15,
        'groundedness': 0.20,
        'deconstruction': 0.15,
        'centrality': 0.15,
        'value': 0.15
    }
    
    def compute_composite(self, node: Node) -> float:
        scores = {
            'frequency': min(math.log1p(node.frequency_score) / math.log1p(1000), 1.0),
            'recency': node.recency_score,
            'groundedness': node.groundedness_score,
            'deconstruction': min(math.log1p(node.deconstruction_score) / math.log1p(1000), 1.0),
            'centrality': node.centrality_score,
            'value': node.value_score
        }
        composite = sum(scores[k] * w for k, w in self.WEIGHTS.items())
        return clamp(composite, 0.001, 1.0)
```

### 3.4 模块四：健康监测与压缩触发（量化版）

```python
class HealthCompressionPipeline:
    """健康监测 → 压缩触发流水线（基于六维度量化）。"""
    
    def run(self, beat_type: str):
        if beat_type == "micro":
            self._update_activation_logs()
            return
        
        if beat_type == "meso":
            # 次节拍：更新六维度评分，轻量同步
            self._update_all_dimensions()
            health_report = self.health_monitor.scan_all()
            degraded = [n for n in health_report if n.composite_weight < 0.3]
            if degraded:
                self.sync.mark_stale(degraded)
            return
        
        if beat_type == "macro":
            # 主节拍：全局重标定 + 完整压缩周期
            all_nodes = self.db.get_all_nodes()
            
            # Step 1: 全局权重重标定
            rescale_report = self.global_rescaling.rescale(all_nodes)
            
            # Step 2: 识别压缩候选（已标记compression_flag的节点）
            candidates = [n for n in all_nodes if n.compression_flag]
            candidates.sort(key=lambda n: n.composite_weight)
            candidates = candidates[:self.max_compress_per_cycle]
            
            # Step 3: 执行压缩
            if candidates:
                self.archive.compress(candidates)
            
            # Step 4: 跨层同步
            self.sync.sync_window()
            
            # Step 5: 资源释放
            self._vacuum_and_cleanup()
            
            return CompressionReport(
                compressed_count=len(candidates),
                global_avg_before=rescale_report.global_avg_before,
                global_avg_after=rescale_report.global_avg_after,
                space_reclaimed=self._estimate_space(candidates),
                sync_fixes=self.sync.last_fix_count,
            )
    
    def _update_all_dimensions(self):
        """次节拍：更新所有节点的六维度评分。"""
        for node in self.db.get_all_nodes():
            node.frequency_score = self.freq_tracker.compute(node)
            node.recency_score = self.recency_tracker.compute_recency(node)
            node.groundedness_score = self.groundedness_eval.compute_groundedness(node)
            node.deconstruction_score = self.decon_tracker.get_score(node)
            node.centrality_score = self.centrality.compute_pagerank(self.graph).get(node.id, 0.0)
            node.value_score = self.value_eval.compute_value(node)
            node.composite_weight = self.composite_calc.compute_composite(node)
```

### 3.5 模块五：恢复机制（Recovery）

```python
class RecoveryManager:
    """从 limbo/archive 恢复节点。"""
    
    def recover(self, node_id: str) -> Node:
        """恢复节点到活跃区。"""
        # 1. 检查 limbo 区
        limbo = self.db.fetchone("SELECT * FROM limbo_nodes WHERE original_node_id = ?", (node_id,))
        if limbo:
            # 恢复完整内容
            full_content = json.loads(limbo["full_content"])
            node = Node.from_dict(full_content)
            
            # 重新激活
            self.activation_tracker.touch(node_id)
            
            # 从 limbo 移除
            self.db.execute("DELETE FROM limbo_nodes WHERE original_node_id = ?", (node_id,))
            
            return node
        
        # 2. 检查 archive 区（更慢，需要完整重建）
        archive = self.db.fetchone("SELECT * FROM archive_nodes WHERE original_node_id = ?", (node_id,))
        if archive:
            full_content = json.loads(archive["final_content"])
            return Node.from_dict(full_content)
        
        raise NodeNotFoundError(f"Node {node_id} not found in limbo or archive")
    
    def lazy_recover(self, reference: Reference) -> Node:
        """懒恢复：当某个被压缩的节点被引用时，自动恢复。"""
        # 检查引用是否指向 limbo 节点
        if reference.target_status == "limbo":
            # 自动恢复
            node = self.recover(reference.target_id)
            # 更新引用
            reference.update_target(node)
            return node
        
        # 如果指向 archive，不自动恢复，返回占位符
        if reference.target_status == "archive":
            return PlaceholderNode(
                id=reference.target_id,
                note="Archived. Use recover() to restore."
            )
```

---

## 4. 数据模型

### 4.1 已有表（schema_divergent_v2.sql）

已有预留表，可直接使用：
- `concept_degradation` — 退化记录（迁移类型、源/目标概念）
- `limbo_nodes` — 低效区（压缩节点、恢复阈值、访问计数）
- `archive_nodes` — 归档区（最终内容、归档原因）

### 4.2 新增表

```sql
-- 跨层同步日志
CREATE TABLE IF NOT EXISTS sync_log (
    id TEXT PRIMARY KEY,
    sync_type TEXT CHECK(sync_type IN ('micro', 'meso', 'macro')),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    broken_refs_fixed INTEGER DEFAULT 0,
    stale_hypotheses_marked INTEGER DEFAULT 0,
    nodes_compressed INTEGER DEFAULT 0,
    space_reclaimed_kb INTEGER DEFAULT 0,
    status TEXT CHECK(status IN ('running', 'completed', 'failed'))
);

-- 压缩记录（详细）
CREATE TABLE IF NOT EXISTS compression_detail (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    original_size_bytes INTEGER,
    compressed_size_bytes INTEGER,
    compression_ratio REAL,
    l0l4_mapping TEXT,  -- JSON: {l0: ..., l1: ..., ...}
    target_zone TEXT CHECK(target_zone IN ('limbo', 'archive')),
    compressed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recovered_at TIMESTAMP,
    recovery_count INTEGER DEFAULT 0
);

-- 恢复日志
CREATE TABLE IF NOT EXISTS recovery_log (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    source_zone TEXT CHECK(source_zone IN ('limbo', 'archive')),
    recovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trigger_reason TEXT  -- "user_request" | "lazy_reference" | "sync_repair"
);
```

---

## 5. 与整体架构的集成

### 5.1 与 v5.3 比例控制的交互（量化反馈闭环）

协同层不修改比例控制的状态，但基于六维度量化指标，向比例控制输出具体的调整建议：

```python
class QuantifiedFeedbackLoop:
    """量化反馈闭环：将健康状态转化为比例调整指令。"""
    
    def compute_adjustment(self, metrics: SystemMetrics) -> RatioAdjustment:
        adjustments = []
        
        # 规则1：全局平均权重过高 → 需要整理，降低发散
        if metrics.global_avg_weight > 0.6:
            adjustments.append(("high_global_weight", -0.15))
        
        # 规则2：可压缩节点比例 > 20% → 系统臃肿
        if metrics.compressible_ratio > 0.2:
            adjustments.append(("compressible_overflow", -0.15))
        
        # 规则3：limbo恢复率 > 30% → 压缩过度
        if metrics.limbo_recovery_rate > 0.3:
            adjustments.append(("over_compression", -0.10))
        
        # 规则4：高价值节点被压缩 → 严重错误
        if metrics.high_value_compressed > 0:
            adjustments.append(("value_violation", -0.25))
        
        # 规则5：解构活跃度低（30天<5次）→ 发散不足
        if metrics.avg_deconstruction_30d < 5.0:
            adjustments.append(("low_divergence", +0.10))
        
        # 规则6：拓扑中心性断层 → 结构危机
        if metrics.centrality_variance > 0.5:
            adjustments.append(("structure_crisis", -0.20))
        
        # 规则7：系统空闲 + 健康良好 → 提高发散（探索窗口）
        if metrics.is_idle and metrics.global_avg_weight < 0.4:
            adjustments.append(("exploration_window", +0.10))
        
        total_delta = sum(delta for _, delta in adjustments)
        return RatioAdjustment(
            diverge_delta=clamp(total_delta, -0.3, +0.2),
            reasons=adjustments
        )
```

### 5.2 与 v5.2b 自引用的交互（量化触发链）

协同层基于压缩统计，主动触发自引用和L0-L4演化：

```python
class QuantifiedTriggerChain:
    """量化触发链：从压缩统计中发现系统级信号。"""
    
    def analyze_compression(self, report: CompressionReport) -> list[SystemTrigger]:
        triggers = []
        
        # 信号1：大量节点无法匹配L0-L4 → 盲区发现 → 触发自引用
        unmatched_ratio = report.unmatched_count / max(report.total_compressed, 1)
        if unmatched_ratio > 0.3:
            triggers.append(SystemTrigger(
                type="BLIND_SPOT_DETECTED",
                priority="HIGH",
                data={
                    "unmatched_nodes": report.unmatched_nodes,
                    "suggested_action": "trigger_self_reference",
                    "reason": f"{unmatched_ratio:.1%}压缩节点无法归入L0-L4"
                }
            ))
        
        # 信号2：某领域节点集中被压缩 → 领域衰退 → 触发发散探索
        for domain, ratio in report.domain_compression_ratios.items():
            if ratio > 0.5:
                triggers.append(SystemTrigger(
                    type="DOMAIN_DECLINE",
                    priority="MEDIUM",
                    data={
                        "domain": domain,
                        "ratio": ratio,
                        "suggested_action": "trigger_divergent_exploration"
                    }
                ))
        
        # 信号3：高解构频率节点被压缩 → 认知深度受损 → 恢复并保护
        for node in report.compressed_nodes:
            if node.deconstruction_score > 10.0:
                triggers.append(SystemTrigger(
                    type="DEPTH_LOSS",
                    priority="HIGH",
                    data={
                        "node_id": node.id,
                        "suggested_action": "restore_and_protect"
                    }
                ))
        
        return triggers
```

### 5.3 与 L0-L4 种子库的交互

```python
class L0L4CompressionMatcher:
    """将压缩节点匹配到L0-L4抽象层级。"""
    
    def match(self, node: Node) -> L0L4Mapping:
        """使用已有的L0-L4反向索引。"""
        # 直接调用 layer1/l0l4_reverse_index.py 中的匹配逻辑
        return l0l4_reverse_index.match_node(node)
```

---

## 6. CLI 接口

```bash
# 手动触发协调节拍
lcortex coordinate --beat meso    # 次节拍
lcortex coordinate --beat macro   # 主节拍
lcortex coordinate --force        # 无视空闲状态，强制执行

# 查看系统健康状态
lcortex health --status           # 当前健康概览
lcortex health --nodes            # 节点健康列表
lcortex health --trends           # 健康趋势（7天）

# 查看压缩状态
lcortex archive --list            # 归档区列表
lcortex archive --list-limbo      # 低效区列表
lcortex archive --stats           # 压缩统计

# 恢复节点
lcortex recover --node <id>       # 从limbo/archive恢复
lcortex recover --lazy <id>       # 懒恢复（仅更新引用，不恢复内容）

# 配置协调节拍
lcortex config --meso-interval 5   # 次节拍间隔（分钟）
lcortex config --macro-interval 60  # 主节拍间隔（分钟）
lcortex config --idle-trigger on    # 启用空闲检测触发
```

---

## 7. 边界条件与降级策略

| 边界条件 | 处理策略 |
|---------|---------|
| 压缩过程中节点被访问 | 压缩事务加乐观锁，冲突时放弃压缩，记录冲突 |
| 恢复时节点已在活跃区 | 幂等操作，直接返回活跃区节点 |
| 恢复时节点不存在 | 返回占位符，标记为"ghost"，触发重建（如有来源） |
| 归档区满 | 按最旧优先清理，或通知用户扩容 |
| 压缩任务执行时间过长 | 设置超时（如30秒），超时后部分完成，记录状态 |
| 系统崩溃时压缩中断 | 下次启动时检查 `sync_log` 中未完成的记录，恢复或回滚 |

---

## 8. 实施计划

### Phase 1：跨层同步（2-3天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 同步窗口协议 | `coordination/sync.py` | 暂停/恢复收敛发散的接口 |
| 一致性检查 | `coordination/sync.py` | 引用完整性、视角一致性 |
| 断裂修复 | `coordination/sync.py` | stale标记、重定向到limbo |
| 同步日志 | `coordination/sync_log.py` | sync_log表操作 |

### Phase 2：压缩归档（3-4天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 压缩引擎 | `coordination/compression.py` | 节点压缩、L0-L4匹配 |
| 归档管理 | `coordination/archive.py` | limbo/archive区CRUD |
| 健康→压缩流水线 | `coordination/pipeline.py` | 健康检查→候选选择→压缩 |
| 恢复管理 | `coordination/recovery.py` | 恢复、懒恢复、占位符 |

### Phase 3：协调节拍（1-2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 空闲检测 | `coordination/idle_detector.py` | CPU/IO/用户输入检测 |
| 节拍调度器 | `coordination/scheduler.py` | micro/meso/macro触发 |
| 配置管理 | `core/config_coordinator.py` | 可配置间隔 |

### Phase 4：集成与测试（2-3天）

| 任务 | 说明 |
|------|------|
| 与比例控制集成 | 协同层不修改比例，但暴露健康API |
| 与自引用集成 | 压缩统计纳入结构反思 |
| 基准测试 | 测量压缩前后的资源占用、查询延迟 |
| 恢复测试 | 验证压缩→恢复的完整闭环 |

---

## 9. 风险与边界

| 风险 | 缓解措施 |
|------|---------|
| 压缩过度（关键节点被压） | 永久节点保护 + 手动恢复 + 懒恢复自动触发 |
| 恢复延迟（limbo节点被频繁恢复） | 恢复计数跟踪，频繁恢复的节点取消压缩资格 |
| 压缩后L0-L4匹配失效 | 压缩时保留L0-L4映射，恢复时重建 |
| 同步窗口阻塞主任务 | 同步窗口设置超时，超时后部分完成 |
| 空闲检测误触发 | 多指标综合判断（CPU+IO+任务队列+用户输入） |
| 配置不合理（间隔过短） | 最小间隔限制（微节拍≥100ms，次节拍≥1min，主节拍≥10min） |

---

## 10. 一句话总结

**协同层是Literature Cortex的"内存管理器"：在用户不感知的间隙中，执行跨层同步、内容压缩、资源释放。压缩不是遗忘——基于六维度量化评估（F/R/G/D/C/V）和全局权重重标定，内容迁移到低效区/归档区，随时可恢复。抽象化不另建层——直接调用L0-L4公理化库，将具体内容匹配到抽象层级。三节拍（微/次/主）适配计算系统的空闲模式，而非强制夜间运行。量化反馈闭环将健康状态转化为比例控制指令，量化触发链从压缩统计中发现系统级盲区信号。**

---

*设计方案版本: v5.4-DRAFT*
*撰写日期: 2026-06-20*
*作者: 合作 (OpenClaw)*
*基于: 神经科学文献综述 + v5.3比例控制 + 用户修正需求*
