# Literature Cortex 算法继承图谱 v1.0

> 生成时间：2026-06-21
> 范围：lcortex/ 下全部 90+ Python 文件
> 目的：识别冗余、定义继承关系、规划重构

---

## 1. 算法层级全景

```
L5 生成层
├── LLM 适配 (6 providers) — OpenAI/Claude/DeepSeek/Ollama/Noop/Claw
└── Claw 模式 (本地模板) — 无 LLM 的兜底推理

L4 控制层
├── 算力调度 (比例控制器) — 协调层内部资源分配
├── 反馈闭环 (7条规则) — 健康状态→比例调整
├── 触发链 (3类信号) — 事件驱动的系统响应
├── 同步窗口 — 分布式/并发控制
└── 遗忘引擎 — 记忆衰减 (EMA-based)

L3 认知层
├── 扩散激活 (ACT-R) — 双权重：频率 + 近因
├── 反事实链路破坏 — 移除边，评估关键性
├── 反事实扰动生成 — 属性反转/关系置换
├── 溯因推理 — 逆向假设生成
├── 倒置因果 — 约束调整，因果反转
└── 语义桥/结构同构 — 跨域类比

L2 统计/启发层
├── BM25 评分 (Dry Scorer) — 无 LLM 的 NLP 评分
├── TF-IDF/6维评分 (Scorer) — LLM 增强的评分
├── 置信度系统 — 规则化的置信评估
├── 价值标签 — 规则化的价值评估
├── PMI 过滤 — 互信息邻居筛选
└── MAB 搜索优化 — 多臂老虎机

L1 符号/规则层
├── 文本清洗 — 多级清洗 Pipeline
├── 存疑系统 — 模糊匹配 + 希腊字母 + 上下文
├── 关键词提取 — 频率/共现驱动
├── 领域分类 — 关键词匹配
├── 分词 (3 variants) — 普通 + MWE + 分词
├── 嵌入编码 — 向量表示
├── 正则匹配 — 变量定义/公式提取
├── 查表映射 — 学科变量库
├── Levenshtein 距离 — 编辑距离模糊匹配
├── 图遍历 (BFS/DFS) — 双向搜索
├── 冲突仲裁 — 事实冲突裁决
├── 约束验证 — 一致性检查
└── 结构解构 — 论文六层分解

L0 基础设施
├── 持久化 (SQLite) — 收敛/发散/嵌入三层
├── 搜索适配 — arXiv/OpenAlex/流式
├── 导出 — Obsidian/Markdown/JSON
└── 监控 — TUI/日志/告警
```

---

## 2. 按功能域归类

### 2.1 文本预处理域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 文本清洗 | `analysis/text_cleaner.py` | 规则 | 活跃 | **保留** |
| 存疑系统 | `analysis/uncertainty_tracker.py` | 规则+模糊 | 活跃 | **保留** (刚增强) |
| 普通分词 | `layer1/tokenizer.py` | 规则 | 活跃 | **合并** → 统一分词接口 |
| MWE 识别 | `layer1/mwe_tokenizer.py` | 规则 | 活跃 | **合并** → 统一分词接口 |
| 中文分词 | `layer1/分词` (注：无此文件) | — | — | 已包含在 tokenizer |
| 关键词提取 | `layer1/keyword_extractor.py` | 统计 | 活跃 | **保留** |
| 领域分类 | `layer1/domain_classifier.py` | 规则+统计 | 活跃 | **保留** |
| 嵌入编码 | `layer1/embedding.py` | 向量 | 活跃 | **保留** |
| 参数调优 | `layer1/parameter_tuner.py` | 规则 | ? | **评估** |
| PMI 过滤 | `layer1/pmi_neighbor_filter.py` | 统计 | 活跃 | **保留** |

**合并建议**：将 `tokenizer.py` + `mwe_tokenizer.py` 合并为 `UnifiedTokenizer`，提供 `tokenize(mode="standard|mwe|language")` 接口。

---

### 2.2 搜索检索域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| arXiv 检索 | `search/arxiv.py` | API | 活跃 | **保留** |
| OpenAlex 检索 | `search/openalex.py` | API | 活跃 | **保留** |
| 搜索适配器 | `search/adapter.py` | 接口 | 部分 | **重构** → 统一多源接口 |
| 多级搜索 | `search/multi_level.py` | 策略 | 活跃 | **保留** |
| 去重引擎 | `search/dedup.py` | 规则 | 活跃 | **保留** |
| 流式处理 | `search/stream.py` | 流 | 活跃 | **保留** |

**重构建议**：`search/adapter.py` 是统一接口，但 `arxiv.py`/`openalex.py` 未完全使用它。应重构为 `SearchAdapter` 基类 + `ArxivAdapter`/`OpenAlexAdapter` 实现。

---

### 2.3 评估评分域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| TF-IDF/4C+L 评分 | `analysis/scorer.py` | LLM依赖 | 活跃 | **合并** → 统一评分接口 |
| BM25 Dry 评分 | `analysis/dry_scorer.py` | 纯统计 | 活跃 | **合并** → 统一评分接口 |
| 置信度系统 | `evaluation/confidence_system.py` | 规则 | ? | **合并** → 评分接口扩展 |
| 价值标签 | `evaluation/value_tag_system.py` | 规则 | ? | **合并** → 评分接口扩展 |

**合并建议**：

```python
class Scorer(ABC):
    """统一评分接口。"""
    def score(self, paper: Paper, query: str) -> ScoreResult: ...

class LLMScorer(Scorer):  # 原 scorer.py
class DryScorer(Scorer):  # 原 dry_scorer.py
class ConfidenceScorer(Scorer):  # 原 confidence_system.py
class ValueTagScorer(Scorer):  # 原 value_tag_system.py
```

---

### 2.4 收敛推理域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 正向演绎 | `inference/convergent/deduction_engine.py` | 规则 | 活跃 | **保留** |
| 双向搜索 | `inference/convergent/bi_bfs_engine.py` | 图遍历 | 活跃 | **保留** |
| 冲突仲裁 | `inference/convergent/conflict_arbitrator.py` | 规则 | 活跃 | **合并** → 验证层 |
| 约束验证 | `inference/convergent/constraint_validator.py` | 规则 | 活跃 | **合并** → 验证层 |
| 核心收敛 | `inference/convergent/core.py` | 编排 | 活跃 | **保留** |
| 对偶匹配 | `inference/dual_matcher.py` | 多层融合 | 活跃 | **保留** |
| L0-L4 匹配 | `coordination/l0l4_matcher.py` | 映射 | 活跃 | **合并** → 跨域映射接口 |
| 简单 WL | `inference/simple_wl.py` | 图匹配 | 活跃 | **保留** (函数树专用) |

**合并建议**：
- `conflict_arbitrator.py` + `constraint_validator.py` → 统一 `ValidationEngine`（验证层已有类似概念）
- `l0l4_matcher.py` + `inference/divergent/semantic_bridge.py` → 统一 `CrossLayerMapper`

---

### 2.5 发散推理域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 扩散激活 | `divergence/activation.py` | 认知模型 | 活跃 | **保留** |
| 反事实链路破坏 | `divergence/counterfactual.py` | 图遍历 | 活跃 | **保留** |
| 反事实扰动生成 | `inference/divergent/counterfactual_perturbation.py` | 启发式 | 活跃 | **合并** → 反事实接口 |
| 溯因推理 | `divergence/abductive.py` | 启发式 | 活跃 | **保留** |
| 倒置因果 | `divergence/inverted_causality.py` | 约束调整 | 活跃 | **保留** |
| 结构同构 | `inference/divergent/structural_isomorphism.py` | 图匹配 | 活跃 | **保留** (跨域专用) |
| 语义桥 | `inference/divergent/semantic_bridge.py` | 图 | 活跃 | **合并** → 跨域映射接口 |
| 拓扑模式 | `inference/divergent/topology_pattern_library.py` | 模板 | 活跃 | **保留** |
| 发散核心 | `inference/divergent/core.py` | 编排 | 活跃 | **保留** |

**合并建议**：
- `counterfactual.py` (链路破坏) + `counterfactual_perturbation.py` (扰动生成) → 统一 `CounterfactualEngine` 提供 `break_link()` + `generate_perturbation()` 两个 API
- `semantic_bridge.py` + `l0l4_matcher.py` + `persistence/bridge.py` → 统一 `CrossLayerMapper` 接口

---

### 2.6 形式化转译域 (L2)

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 插件基类 | `layer2/plugin_base.py` | 接口 | 活跃 | **保留** |
| 函数树 | `schema/function_tree.py` | 数据结构 | 活跃 | **保留** |
| 键合图 | `layer2/plugins/bond_graph.py` | 形式化 | 活跃 | **保留** |
| 控制系统 | `layer2/plugins/control_system.py` | 形式化 | 活跃 | **保留** |
| 范畴论 | `layer2/plugins/category_theory.py` | 形式化 | ? | **评估** |
| 有限元 | `layer2/plugins/finite_element.py` | 形式化 | ? | **评估** |
| 图网络 | `layer2/plugins/petri_net.py` | 形式化 | ? | **评估** |
| 模态 | `layer2/plugins/modelica.py` | 形式化 | ? | **评估** |
| 其他 24 个插件 | `layer2/plugins/*.py` | 形式化 | 多数? | **精简** |

**精简建议**：
- 当前 28 个插件，很多可能只是模板。应分类为：
  - **核心插件** (有实质代码): bond_graph, control_system, modelica, category_theory, petri_net, information_theory, quantum_mechanics, robotics, heat_transfer, fluid_mechanics, optics, power_electronics, pharmacokinetics, system_dynamics, sysml, narrative_structure, gene_ontology, sbml, cellml, biopax, devs, process_algebra, formal_grammar, functional_basis, game_theory, idef0, ast_cfg, generic_llm, act_r, signal_flow_graph, port_hamiltonian
  - **空壳插件** (只有模板): 需逐一审查，空壳可删或合并为 "generic" 插件

---

### 2.7 协同控制域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|
| 核心调度器 | `core/scheduler.py` | 任务调度 | 活跃 | **合并** → 统一调度器 |
| 协调调度器 | `coordination/scheduler.py` | 算力协调 | 活跃 | **合并** → 统一调度器 |
| 反馈闭环 | `coordination/feedback_loop.py` | 控制 | 活跃 | **保留** |
| 触发链 | `coordination/trigger_chain.py` | 事件 | 活跃 | **保留** |
| 同步窗口 | `coordination/sync.py` | 并发 | 活跃 | **保留** |
| 健康监控 | `coordination/health_monitor.py` | 监控 | 活跃 | **保留** |
| 遗忘引擎 | `coordination/forgetting_engine.py` | 衰减 | 活跃 | **保留** |
| 空闲检测 | `coordination/idle_detector.py` | 触发 | 活跃 | **保留** |
| 量化评估 | `coordination/quant_eval.py` | 评估 | 活跃 | **保留** |
| 队列系统 | `coordination/queues.py` | 数据结构 | 活跃 | **保留** |
| 归档 | `coordination/archive.py` | 存储 | 活跃 | **保留** |
| 恢复 | `coordination/recovery.py` | 容错 | 活跃 | **保留** |
| 主 CLI | `cli.py` | 接口 | 活跃 | **合并** → 统一 CLI |
| 协调 CLI | `coordination/cli.py` | 接口 | 活跃 | **合并** → 统一 CLI |
| 管道 | `coordination/pipeline.py` | 编排 | 活跃 | **保留** |
| 模型 | `coordination/models.py` | 数据 | 活跃 | **保留** |

**合并建议**：
- `core/scheduler.py` (任务调度) + `coordination/scheduler.py` (算力协调) → 统一 `Scheduler`，支持 `schedule_task()` 和 `schedule_resource()` 两种模式
- `cli.py` (主入口) + `coordination/cli.py` (协调子命令) → 统一 CLI，协调层命令作为子命令 `lcortex coord ...`

---

### 2.8 验证域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 反回声室 | `validation/anti_echo_chamber.py` | 规则 | 活跃 | **保留** |
| 交叉验证 | `validation/cross_track_coordinator.py` | 编排 | 活跃 | **保留** |
| MAB 搜索 | `validation/mab_search_optimizer.py` | 统计 | 活跃 | **保留** |
| 开放验证 | `validation/open_validation.py` | 规则 | 活跃 | **合并** → 验证接口 |
| 规则演化 | `validation/rule_evolution.py` | 规则 | 活跃 | **合并** → 验证接口 |
| 规则效用 | `validation/rule_utility_updater.py` | 统计 | 活跃 | **合并** → 验证接口 |
| 命中回溯 | `validation/hit_backtracker.py` | 追踪 | 活跃 | **保留** |

**合并建议**：`open_validation.py` + `rule_evolution.py` + `rule_utility_updater.py` → 统一 `ValidationEngine` 提供 `validate()`, `evolve_rules()`, `update_utility()` 三个 API。

---

### 2.9 结构解析域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| 结构解构 | `structure/deconstructor.py` | 规则 | 活跃 | **保留** |
| 结构提取 | `structure/extractor.py` | 规则 | 活跃 | **合并** → 统一解析器 |
| 轻量匹配 | `structure/lite_matcher.py` | 规则 | 活跃 | **合并** → 统一解析器 |
| 六层解构 | `inference/deconstruction.py` | 规则 | 活跃 | **保留** |
| 发散解构 | `inference/divergent_deconstructor.py` | 启发式 | 活跃 | **合并** → 解构接口 |

**合并建议**：`extractor.py` + `lite_matcher.py` → 统一 `StructureParser`；`deconstruction.py` + `divergent_deconstructor.py` → 统一 `DeconstructionEngine` 提供 `deconstruct(mode="convergent|divergent")`。

---

### 2.10 导出域

| 算法 | 文件 | 类型 | 状态 | 建议 |
|------|------|------|------|------|
| Obsidian 导出 | `export/obsidian.py` | 格式 | 活跃 | **保留** |
| 解构导出 | `export/obsidian_deconstructed.py` | 格式 | 活跃 | **合并** → 统一导出 |
| 双核导出 | `export/obsidian_dualcore.py` | 格式 | 活跃 | **合并** → 统一导出 |
| 语言处理 | `export/language.py` | 工具 | 活跃 | **保留** |
| 导出 v5.1 | `export/export_v51.py` | 格式 | 活跃 | **合并** → 统一导出 |

**合并建议**：4 个 Obsidian 导出 → 统一 `ObsidianExporter` 提供 `export(mode="standard|deconstructed|dualcore|v51")`。

---

## 3. 合并优先级矩阵

| 优先级 | 合并项 | 复杂度 | 收益 | 建议时间 |
|--------|--------|--------|------|----------|
| P0 | `scorer` + `dry_scorer` + `confidence` + `value_tag` → 统一 `Scorer` | 中 | 高 | 4h |
| P0 | `cli` + `coordination/cli` → 统一 CLI | 低 | 高 | 2h |
| P1 | `tokenizer` + `mwe_tokenizer` → 统一 `Tokenizer` | 低 | 中 | 2h |
| P1 | `core/scheduler` + `coordination/scheduler` → 统一 `Scheduler` | 中 | 中 | 3h |
| P1 | `counterfactual` + `counterfactual_perturbation` → 统一 `CounterfactualEngine` | 中 | 高 | 3h |
| P2 | `semantic_bridge` + `l0l4_matcher` + `bridge` → 统一 `CrossLayerMapper` | 高 | 高 | 6h |
| P2 | `conflict_arbitrator` + `constraint_validator` + 验证层 → 统一 `ValidationEngine` | 高 | 中 | 5h |
| P2 | `extractor` + `lite_matcher` → 统一 `StructureParser` | 低 | 低 | 2h |
| P3 | 4 个 Obsidian 导出 → 统一 `ObsidianExporter` | 低 | 低 | 2h |
| P3 | `deconstruction` + `divergent_deconstructor` → 统一 `DeconstructionEngine` | 中 | 中 | 3h |
| P4 | 28 个 L2 插件 → 审查空壳，精简为 10-15 核心插件 | 高 | 中 | 8h |
| P4 | `search/arxiv` + `search/openalex` → 统一适配器模式 | 中 | 中 | 4h |

---

## 4. 删除候选清单

> ⚠️ 需逐一审查代码确认后再删除

| 文件 | 疑似原因 | 置信度 | 审查动作 |
|------|----------|--------|----------|
| `layer2/plugins/` 中无实质内容的插件 | 只有模板/空函数 | 中 | 逐行检查 `def` 数量 |
| `core/scheduler.py` 或 `coordination/scheduler.py` | 合并后保留一个 | 高 | 比较功能差异 |
| `inference/simple_wl.py` | 与 `structural_isomorphism` 重叠 | 低 | 确认用途差异（函数树 vs 跨域结构） |
| `coordination/models.py` | 可能只有数据类，无算法 | 中 | 检查是否纯 DTO |
| `export/export_v51.py` | 可能被 `obsidian.py` 覆盖 | 中 | 检查功能差异 |
| `layer1/parameter_tuner.py` | 可能无实质算法 | 中 | 检查内容 |
| `evaluation/confidence_system.py` | 合并后可删 | 高 | 确认合并后无独立调用 |
| `evaluation/value_tag_system.py` | 合并后可删 | 高 | 确认合并后无独立调用 |

---

## 5. 统一接口设计草案

### 5.1 统一评分接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ScoreResult:
    total: float
    dimensions: Dict[str, float]
    confidence: float
    metadata: Dict[str, Any]

class Scorer(ABC):
    @abstractmethod
    def score(self, paper: Paper, query: str) -> ScoreResult: ...
    
    @property
    @abstractmethod
    def requires_llm(self) -> bool: ...

class LLMScorer(Scorer): ...      # 原 scorer.py
class DryScorer(Scorer): ...      # 原 dry_scorer.py
class ConfidenceScorer(Scorer): ...  # 原 confidence_system.py
class ValueTagScorer(Scorer): ...     # 原 value_tag_system.py
```

### 5.2 统一反事实接口

```python
class CounterfactualEngine:
    def break_link(self, path: Path, edge: Edge) -> BreakReport: ...
    def perturb(self, fact: Fact, mode: str) -> List[Hypothesis]: ...
    def evaluate_criticality(self, edge: Edge) -> float: ...
```

### 5.3 统一跨域映射接口

```python
class CrossLayerMapper:
    def map_layer_to_layer(self, source: Node, source_layer: int, target_layer: int) -> Node: ...
    def map_domain_to_domain(self, source: Node, source_domain: str, target_domain: str) -> IsomorphMatch: ...
    def semantic_bridge(self, concept_a: str, concept_b: str) -> float: ...
```

### 5.4 统一调度器接口

```python
class Scheduler:
    def schedule_task(self, task: Task, priority: int) -> TaskId: ...
    def schedule_resource(self, resource: Resource, allocation: float) -> ResourceId: ...
    def query_status(self) -> ScheduleStatus: ...
```

---

## 6. 当前统计

| 指标 | 数值 |
|------|------|
| 总 Python 文件 | 90+ |
| 可合并的文件组 | 12 组 |
| 估计删除/精简后 | 70-75 文件 |
| 核心接口数（建议） | 5-6 个统一接口 |
| 重构工作量 | 约 40-50 小时 |

---

## 7. 下一步建议

1. **先 P0**：合并 scorer + dry_scorer（统一评分接口），这是最重要的一个，因为评分是系统核心路径
2. **再 P1**：合并 CLI + 调度器，改善用户体验
3. **审查插件**：逐一检查 `layer2/plugins/` 中哪些有实质内容，哪些只有模板
4. **然后 P2**：跨域映射和验证层合并，需要更仔细的设计

是否要我直接开始 P0（统一评分接口）的代码实现？
