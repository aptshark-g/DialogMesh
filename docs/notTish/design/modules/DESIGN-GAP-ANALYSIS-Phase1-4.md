# Literature Cortex — Phase 1-4 缺口分析与设计补充文档

> **文档编号**: LC-DESIGN-GAP-ANALYSIS-Phase1-4
> **版本**: v1.0
> **日期**: 2026-07-02
> **状态**: 设计文档补充（缺口清单+修复方案）
> **对应主设计**: DESIGN-v6.0-UNIFIED.md

---

## 一、评估方法论

### 1.1 交叉核查流程

本次评估采用**设计文档 ↔ 代码实现**双向交叉验证：

1. **文档要求提取**：逐节扫描 DESIGN-v6.0-UNIFIED.md 及 13 份补充文档（v6.0-rev1~rev5.2、附录 D/E），提取所有明确声明的功能要求。
2. **代码实现扫描**：遍历 313 个 Python 文件、75,685 行代码，定位对应的实现模块。
3. **差距标注**：按以下四级分类标注每项要求的状态。

### 1.2 状态分类

| 符号 | 含义 | 判定标准 |
|------|------|---------|
| ✅ | 完整实现 | 代码与设计文档一致，测试覆盖 |
| ⚠️ | 部分实现 | 核心逻辑存在，但缺少设计文档要求的边界条件或扩展能力 |
| ❌ | 未实现 | 代码中无对应实现，或仅有空壳/占位符 |
| 🔴 | 架构性缺口 | 缺失会导致上下游模块断裂，或系统无法完成闭环 |

---

## 二、Phase 1 管道贯通

### 2.1 已实现项（✅）

| 模块 | 文件 | 行数 | 验证状态 |
|------|------|------|---------|
| 键合图元解析器 | `layer2/bond_graph_meta_parser.py` | 544 | 10 tests pass |
| 物理域 YAML 配置 | `config/{thermal,mechanical,electrical,fluid,control}.yaml` | 5 文件 | 测试覆盖 |
| 元角色注册表 | `layer2/meta_roles.py` | ~200 | 23 tests pass |
| 编排引擎 v6 | `orchestration/` | ~1500 | 8 capabilities + DAG 管道 |
| SGF 统一格式 | `schema.py` | — | StandardGraphFormat 已定义 |

### 2.2 关键缺口

#### 缺口 P1.1: CSM 四层认知流仅实现两层

**设计文档要求**（v6.0-rev4.2，第 14 节）：

```
CSM 完整流程：
Step 1: 匹配（三层降级链）
Step 2: 判定（综合置信度）
Step 3: 决策（L5 元认知介入）→ 确认 / 否决 / 推迟
Step 4: 学习（元认知学习钩子）→ 权重调整、负知识记录、观察队列更新
```

**实际实现**（`layer3/csm_orchestrator.py`）：

```python
class CSMOrchestrator:
    def compare(self, source_sgf, target_sgf):
        # Step 1: 结构匹配（VF2）
        struct_result = self.structural.match(source_graph, target_graph)
        # Step 2: 角色对齐
        role_result = self.role.align(struct_result, ...)
        # Step 3: 语义过滤（可选）
        semantic_score = self.semantic.similarity(...)
        # Step 4: 综合评分（加权平均）
        combined = weighted_average(...)
        return CSMMatchDetail(...)  # 仅返回评分，无决策/学习
```

**缺失内容**：
- **Step 3 决策层**：`CSMMatchDetail` 仅有 `combined_score` 和 `tier_reached`，无 `decision` 字段（确认/否决/推迟）。
- **Step 4 学习层**：无 `update_weights()`、无 `record_negative_match()`、无 `enqueue_observation()`。
- **负知识库**：`negative_matches` 表未创建。
- **观察队列**：`observation_queue` 表未创建。

**影响**：CSM 生成的高分匹配直接暴露给上层，无审核机制；失败匹配未被记录，导致重复计算。

**修复建议**：

```python
@dataclass
class CSMDecision:
    """Step 3: 决策输出。"""
    decision: str  # "confirm" / "reject" / "defer"
    confidence: float
    reasoning: str
    process_evidence: Dict[str, float]  # {structural: 0.8, role: 0.6, semantic: 0.4}

class CSMOrchestrator:
    def compare(self, source_sgf, target_sgf, context: str = "") -> CSMDecision:
        detail = self._match(source_sgf, target_sgf)  # Step 1-2
        
        # Step 3: 决策
        decision = self._decide(detail, context)
        
        # Step 4: 学习
        if decision.decision == "reject":
            self._record_negative_match(source_sgf, target_sgf, detail)
        elif decision.decision == "defer":
            self._enqueue_observation(source_sgf, target_sgf, detail)
        elif decision.decision == "confirm":
            self._update_positive_weights(detail)
        
        return decision
```

---

#### 缺口 P1.2: CL0 阻断机制未覆盖 LLM 兜底绕过

**设计文档要求**（v6.0-UNIFIED，第 13.3 节）：

> "CL0 失败时直接阻断上层流程，不允许 LLM '兜底绕过'。"

**实际实现**：

`CL0HardConstraintLayer.validate()` 返回 `HardConstraintReport`，其中 `is_valid = False` 时：
- `CLPipeline.execute()` 检查 `cl0_report.cl0_passed` 并跳过后续层。
- 但 `CognitiveLoop` 中 `DivergenceCapability` 失败时直接降级到 L5 内部假设，**实质上构成了 LLM 兜底绕过**。

**影响**：CL0 硬约束的权威性被破坏，系统可能基于未通过硬约束的结构生成假设。

**修复建议**：

```python
class CLPipeline:
    def execute(self, ...):
        cl0_report = self.cl0.validate(source_sgf)
        if not cl0_report.is_valid:
            # 硬失败：记录并阻断，不进入任何后续层
            return CLPipelineReport(
                status=PipelineStatus.BLOCKED_BY_CL0,
                cl0_passed=False,
                cl0_violations=cl0_report.violations,
                # 后续层全部为空
            )
```

---

#### 缺口 P1.3: DivergenceCapability 降级路径质量不足

**设计文档要求**：DivergenceCapability 应接入 Divergent Core 的反事实/溯因/类比引擎。

**实际实现**：`DivergenceCapability.execute()` 在 DB 不可用时降级到 L5 内部假设，假设为随机占位符。

**影响**：端到端测试中 L5 假设始终为 "continue" 或 "far_think"，无实际认知价值。

**修复建议**：提供基于规则的假设生成器作为降级路径（不依赖 DB 但利用键合图结构）。

---

## 三、Phase 2 认知核心

### 3.1 已实现项（✅）

| 模块 | 文件 | 行数 | 验证状态 |
|------|------|------|---------|
| L5 元认知拍板 | `analysis/meta_cognitive_arbiter.py` | 825 | 停滞检测+视角仲裁+预算控制 |
| CognitiveLoop v2 | `orchestration/cognitive_loop.py` | ~300 | L5→Divergence/CSM→CL→L5 闭环 |
| CL0 硬约束 | `inference/convergent/cl0_hard_constraint.py` | 1311 | 11 项检查 |
| CL1 近迁移 | `inference/convergent/cl1_near_transfer.py` | 678 | 规则执行+局部一致性 |
| CL2 远迁移 | `inference/convergent/cl2_far_transfer.py` | 931 | 持久化锚点+类比推理 |
| CL3 质疑层 | `inference/convergent/cl3_questioning.py` | 400 | 边界审查+假设失效 |
| CL4 协调层 | `inference/convergent/cl4_coordination.py` | 539 | 算力分配+仲裁 |

### 3.2 关键缺口

#### 缺口 P2.1: L5 紧急资源再分配未实现

**设计文档要求**（v6.0-rev5，死穴 1）：

> "当发散预算耗尽且探索型查询仍有新发现时，系统应回收已遗忘节点的资源，重新分配给高价值方向。"

**实际实现**：`MetaCognitiveArbiter` 中无 `_emergency_reallocate()` 方法。

**影响**：预算耗尽时，探索型查询静默失败，系统无法自动回收僵尸节点资源。

**修复建议**：

```python
class MetaCognitiveArbiter:
    def _emergency_reallocate(self, state: SystemState) -> ExecutionMode:
        """紧急资源再分配：预算耗尽时回收僵尸节点资源。"""
        if state.divergence_budget <= 0:
            # 查询遗忘引擎：找出可压缩的僵尸节点
            reclaimable = self.forgetting_engine.find_reclaimable_resources()
            if reclaimable > 0:
                # 回收资源，重新分配
                self.budget_allocator.inject_emergency_budget(reclaimable)
                return ExecutionMode.FAR_THINK
            return ExecutionMode.HARD_CODED
```

---

#### 缺口 P2.2: L5 意图优先级（IntentPriority）未实现

**设计文档要求**（v6.0-rev5）：

> "区分探索型（EXPLORATION）与验证型（VERIFICATION）查询，不同阈值策略。"

**实际实现**：`MetaCognitiveArbiter.process()` 仅接收 `query_context` 字符串，无 `intent` 参数。

**影响**：所有查询使用同一阈值，探索型查询（如"有没有新方向"）的停滞判定过于严格。

**修复建议**：

```python
class IntentPriority(Enum):
    EXPLORATION = "exploration"    # 探索型：容忍低置信度，放宽停滞阈值
    VERIFICATION = "verification"  # 验证型：严格要求高置信度
    SYNTHESIS = "synthesis"       # 综合型：平衡策略

class MetaCognitiveArbiter:
    def process(self, node_id, query_context, intent: IntentPriority = IntentPriority.SYNTHESIS, ...):
        # 根据意图调整阈值
        if intent == IntentPriority.EXPLORATION:
            stagnation_threshold = 0.5  # 更宽松
        elif intent == IntentPriority.VERIFICATION:
            stagnation_threshold = 0.8  # 更严格
```

---

#### 缺口 P2.3: CSM 负知识库与观察队列

**设计文档要求**（v6.0-rev4.2）：

```sql
CREATE TABLE negative_matches (
    id INTEGER PRIMARY KEY,
    source_id TEXT,
    target_id TEXT,
    rejection_reason TEXT,  -- "structural_mismatch" / "semantic_incompatible" / "domain_exclusion"
    confidence_at_rejection REAL,
    timestamp TIMESTAMP
);

CREATE TABLE observation_queue (
    id INTEGER PRIMARY KEY,
    source_id TEXT,
    target_id TEXT,
    initial_score REAL,
    observation_count INTEGER DEFAULT 0,
    score_velocity REAL DEFAULT 0.0,  -- 爬升速度
    last_checked TIMESTAMP
);
```

**实际实现**：数据库仅 3 个表（`audit_queue`, `node_perspectives`, `perspective_validation`），`negative_matches` 和 `observation_queue` 均未创建。

**影响**：
- 系统无法从历史拒绝中学习，重复计算相同的失败匹配。
- 弱匹配对无法积累证据后触发重检，错失潜在类比。

**修复建议**：

```python
class NegativeMatchCache:
    """负知识库 + BloomFilter 缓存。"""
    def __init__(self, db_path: str):
        self.bloom = BloomFilter(capacity=10000, error_rate=0.01)
        self.db = sqlite3.connect(db_path)
        self._init_tables()
    
    def is_known_negative(self, source_id: str, target_id: str) -> bool:
        # 先查 BloomFilter（O(1) 无假阴性）
        if not self.bloom.check(f"{source_id}::{target_id}"):
            return False
        # 再查 SQLite（确认非假阳性）
        return self._db_check(source_id, target_id)
    
    def record_negative(self, source_id, target_id, reason: str, confidence: float):
        self.bloom.add(f"{source_id}::{target_id}")
        self._db_insert(source_id, target_id, reason, confidence)

class ObservationQueue:
    """观察队列：弱匹配对的置信度爬升跟踪。"""
    def enqueue(self, source_id, target_id, initial_score: float):
        self._db_insert(source_id, target_id, initial_score)
    
    def update_score(self, pair_id: int, new_score: float):
        old = self._db_get(pair_id)
        velocity = (new_score - old['initial_score']) / days_since(old['timestamp'])
        if velocity > 0.05:  # 爬升速度超过阈值
            self._promote_to_recheck(pair_id)
```

---

#### 缺口 P2.4: CL3 未强制绑定 L0-L4 公理审查

**设计文档要求**（v6.0-UNIFIED，第 13.3 节）：

> "CL3 质疑层用公理层作为'正确性标准'。"

**实际实现**：`CL3QuestioningLayer` 生成质疑问题，但未与 `L0-L4` 的 49 个公理节点建立可编程的审查接口。

**影响**：质疑层的问题是通用的（"此假设是否可验证？"），无法针对具体公理（如 L0 "因果律"）生成精确挑战。

**修复建议**：

```python
class CL3QuestioningLayer:
    def __init__(self, axiom_layer: L0L4AxiomLayer):
        self.axiom_layer = axiom_layer  # 注入公理层
    
    def challenge(self, hypothesis, cl0_report, cl1_report, cl2_report):
        questions = []
        
        # 检查是否违反 L0 公理（因果律）
        if hypothesis.contains("acausal_correlation"):
            axiom = self.axiom_layer.get_axiom("L0_CAUSALITY")
            questions.append(Question(
                severity="critical",
                question=f"假设违反 {axiom.name}：{axiom.description}",
                axiom_violated="L0_CAUSALITY"
            ))
        
        return CL3Report(questions=questions)
```

---

## 四、Phase 3 生命机制

### 4.1 已实现项（✅）

| 模块 | 文件 | 行数 | 验证状态 |
|------|------|------|---------|
| 概念退化引擎 | `lifecycle/degradation_engine.py` | 290 | 17/17 tests pass |
| 复活审查器 | `lifecycle/resurrection.py` | 262 | 测试通过 |
| 阈值自校准器 | `lifecycle/threshold_calibrator.py` | 220 | 测试通过 |
| 生命周期管理器 | `lifecycle/lifecycle_manager.py` | 328 | 统一封装 |
| BloomFilter 缓存 | `divergence/negative_match_cache.py` | ~200 | 骨架存在 |

### 4.2 关键缺口

#### 缺口 P3.1: BloomFilter + LRU 未集成到生命周期流程

**设计文档要求**（附录 D，性能优化项）：

> "negative_matches 的 BloomFilter + LRU 缓存：高并发场景减少数据库查询。"

**实际实现**：`negative_match_cache.py` 存在，但 `CSMOrchestrator` 和 `LifecycleManager` 均未导入使用。

**影响**：每次负知识查询都走 SQLite，高并发时成为瓶颈。

**修复建议**：

```python
class CSMOrchestrator:
    def __init__(self, ..., negative_cache: Optional[NegativeMatchCache] = None):
        self.negative_cache = negative_cache or NegativeMatchCache()
    
    def compare(self, source_sgf, target_sgf):
        # 先查负知识缓存
        if self.negative_cache.is_known_negative(source_sgf.graph_id, target_sgf.graph_id):
            return CSMDecision(decision="reject", confidence=1.0, reasoning="Known negative match")
        # ... 正常匹配流程
```

---

#### 缺口 P3.2: 遗忘审查自动化触发未验证

**设计文档要求**：

> "健康监控发现节点 → 长期无激活 → 遗忘审查 → 可能进入 Limbo。"

**实际实现**：`LifecycleManager.heartbeat()` 有调度逻辑，但自动化触发是否在生产环境中可靠运行，未在测试中验证（测试仅验证单次调用）。

**影响**：系统部署后，遗忘机制可能因 cron/heartbeat 配置错误而失效。

**修复建议**：增加 `heartbeat_integration_test.py`，模拟 30 天运行周期，验证自动触发频率。

---

## 五、Phase 4 场景验证

### 5.1 已实现项（✅）

| 模块 | 文件 | 验证状态 |
|------|------|---------|
| 合成 benchmark | `benchmark/synthetic_benchmark.py` | 12 场景 |
| 端到端测试 | `tests/test_phase4_end_to_end.py` | 13/13 tests pass |
| 系统功能测试 | `tests/e2e_system_test.py` | 10 步骤 |

### 5.2 关键缺口

#### 缺口 P4.1: 真实论文集 benchmark 缺失

**设计文档要求**（Week 10）：

> "收集 50-100 篇机床控制领域论文（振动+热控+RTCP），标注领域分类、关键概念、跨域类比关系。"

**实际实现**：仅用 12 个合成文本片段，无真实论文。

**影响**：无法证明系统在实际学术场景中的可用性。

**修复建议**：
1. 使用用户自身的机床项目论文作为核心测试集（确保领域深度）。
2. 从 arXiv 下载 20-30 篇振动控制+热控论文，人工标注标准答案。
3. 构建 `benchmark/real_paper_benchmark.py`：输入 PDF → 输出结构化报告 → 与人工标注对比。

---

#### 缺口 P4.2: 纯 LLM Baseline 未建立

**设计文档要求**（Week 10）：

> "纯 LLM（GPT-4/DeepSeek）在同样提示词下的输出，记录准确率、幻觉率、一致性。"

**实际实现**：无 Baseline 对比数据。

**影响**：无法定量证明"形式化+LLM"优于"纯 LLM"。

**修复建议**：

```python
class LLMBaseline:
    """纯 LLM 基线对比。"""
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.client = DeepSeekClient(api_key, model)
    
    def evaluate(self, text: str, task: str) -> BaselineResult:
        prompt = self._build_prompt(text, task)
        response = self.client.chat(prompt)
        return BaselineResult(
            output=response,
            latency_ms=response.latency,
            token_count=response.tokens,
        )

class BenchmarkRunner:
    def run_comparison(self, cases: List[BenchmarkCase]):
        results = []
        for case in cases:
            # Literature Cortex 结果
            lc_result = self.lcortex_pipeline.run(case.text)
            # LLM Baseline 结果
            llm_result = self.llm_baseline.evaluate(case.text, case.task)
            # 对比
            results.append(ComparisonReport(
                case_id=case.id,
                lc_score=self._score(lc_result, case.ground_truth),
                llm_score=self._score(llm_result, case.ground_truth),
                hallucination_lc=self._detect_hallucination(lc_result),
                hallucination_llm=self._detect_hallucination(llm_result),
            ))
        return results
```

---

#### 缺口 P4.3: ContentTypeClassifier + ContentAdmissionFilter 未实现

**设计文档要求**（附录 E）：

> "非论文内容摄取的架构适配：学术、新闻、博客、评论分类。"
> "四种决策分支：FULL（完整处理）、SHALLOW（浅层处理）、AGGREGATE（聚合处理）、REJECT（拒绝）。"

**实际实现**：无对应文件。

**影响**：系统无法处理非学术内容（如新闻、博客），只能处理论文文本。

**修复建议**：

```python
class ContentTypeClassifier:
    """内容类型分类器。"""
    def classify(self, text: str) -> ContentType:
        # 特征：引用格式、数学公式密度、章节结构
        if self._has_citation_format(text) and self._has_formula(text):
            return ContentType.ACADEMIC
        elif self._has_news_structure(text):
            return ContentType.NEWS
        elif self._has_blog_tone(text):
            return ContentType.BLOG
        else:
            return ContentType.COMMENT

class ContentAdmissionFilter:
    """内容准入筛子。"""
    def decide(self, content_type: ContentType, credibility: float) -> AdmissionDecision:
        if content_type == ContentType.ACADEMIC and credibility >= 0.7:
            return AdmissionDecision.FULL
        elif content_type == ContentType.NEWS and credibility >= 0.5:
            return AdmissionDecision.SHALLOW
        elif content_type == ContentType.BLOG and credibility >= 0.3:
            return AdmissionDecision.AGGREGATE
        else:
            return AdmissionDecision.REJECT
```

---

#### 缺口 P4.4: 语义过滤在端到端测试中禁用

**实际实现**：`EndToEndTester` 使用 `_DisabledSemanticFilter()`，始终返回 `0.0`。

**影响**：端到端测试未验证真实语义匹配效果，CSM 的语义层从未在集成测试中运行。

**修复建议**：提供离线模式测试（使用已下载的 sentence-transformers 模型，但限制内存使用）。

---

## 六、持久化层缺口

### 6.1 设计文档要求 vs 实际

设计文档 v6.0-UNIFIED 要求 15+ 个数据库表，实际仅有 3 个表：

| 表名 | 状态 | 用途 |
|------|------|------|
| `audit_queue` | ✅ | 审计队列 |
| `node_perspectives` | ✅ | 多视角存储 |
| `perspective_validation` | ✅ | 视角验证记录 |
| `nodes_v2` | ❌ | 节点主表（含六层解构） |
| `edges_v2` | ❌ | 边表（含因果语义标记） |
| `direction_stats` | ❌ | 发散方向统计 |
| `hypothesis_archive` | ❌ | 假设归档 |
| `node_activation` | ❌ | ACT-R 激活记录 |
| `counterfactual_log` | ❌ | 反事实日志 |
| `abductive_hypothesis` | ❌ | 溯因假设 |
| `analogical_matches` | ❌ | 类比匹配 |
| `inverted_causality` | ❌ | 倒置因果 |
| `constraint_space_matches` | ❌ | 约束空间匹配 |
| `difference_analysis` | ❌ | 差异分析 |
| `negative_matches` | ❌ | 负知识库 |
| `observation_queue` | ❌ | 观察队列 |
| `limbo_nodes` | ❌ | 低效区 |
| `archive_nodes` | ❌ | 归档节点 |

**影响**：系统无法真正持久化知识图谱，重启后数据丢失；历史假设、类比、反事实日志无法追溯。

**修复建议**：
1. 创建 `persistence/schema_v2.py`，定义所有缺失的表。
2. 使用 `sqlalchemy` 或 `pydantic-sqlite` 简化 ORM 映射。
3. 优先实现 `nodes_v2`、`edges_v2`、`negative_matches`、`observation_queue`（核心数据）。

---

## 七、修复优先级

| 优先级 | 缺口 | 预估工作量 | 阻塞项 |
|--------|------|-----------|--------|
| 🔴 P0 | 负知识库 + 观察队列 | 2-3 天 | 无 |
| 🔴 P0 | L5 紧急资源再分配 | 1-2 天 | 无 |
| 🔴 P0 | 持久化核心表 (nodes/edges) | 3-5 天 | 无 |
| 🟡 P1 | ContentTypeClassifier + AdmissionFilter | 2-3 天 | 无 |
| 🟡 P1 | CSM 决策层 (确认/否决/推迟) | 1-2 天 | 依赖 P0 负知识库 |
| 🟡 P1 | CL3 公理审查绑定 | 2-3 天 | 依赖 L0-L4 ORM 化 |
| 🟡 P1 | L5 IntentPriority | 1-2 天 | 无 |
| 🟢 P2 | 真实论文集 benchmark | 1-2 周 | 需人工标注 |
| 🟢 P2 | 纯 LLM Baseline | 3-5 天 | 需 DeepSeek API Key |
| 🟢 P2 | BloomFilter + LRU 集成 | 1 天 | 依赖 P0 负知识库 |
| 🟢 P2 | 领域分类准确率提升 | 1-2 天 | 无 |
| 🟢 P2 | 语义过滤端到端测试 | 1 天 | 需内存优化 |

---

## 八、结论

Phase 1-4 的**骨架已完整**（116 测试通过），但以下三类缺口尚未填补：

1. **数据闭环缺口**：负知识库、观察队列、持久化核心表缺失，导致系统无法从历史中学习。
2. **决策闭环缺口**：CSM 决策层、L5 紧急资源再分配、IntentPriority 缺失，导致系统无法自主完成"生成-判定-调整"的完整循环。
3. **验证闭环缺口**：真实论文集 benchmark、LLM Baseline、ContentTypeClassifier 缺失，导致系统价值无法被定量证明。

建议按优先级分阶段修复：先完成 P0（数据闭环），再推进 P1（决策闭环），最后进行 P2（验证闭环）。

---

*文档完成。如需对任一缺口展开详细设计或实施修复，请指定具体条目。*
