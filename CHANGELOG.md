# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **AlgorithmEngine v3.0** — 规则引擎重写：三维噪声检测（语义/结构/指代）、期望推断、规则意图解析器（10组模式→IntentCategory映射）、认知快照生成器。替换原有 20 行桩为完整 280 行实现。
- **FusionEngine v3.0** — 提取为独立模块：5种融合策略（CONFIDENCE_WEIGHTED / ALGORITHM_PREFERRED / LLM_PREFERRED / CONSERVATIVE / VOTE）、四维冲突检测、递归字典合并。
- **HybridEngine** — 认知双工并行调度引擎：4种调度策略（高置信快速通道、低置信等待LLM、加权融合、保守降级）、ThreadPoolExecutor 真正并行、超时管理。
- **6 个 LLM 实例子类**（PCR-LLM / Intent-LLM / Planning-LLM / Meta-Cognitive-LLM / Reflective-LLM / Answer-LLM）：各自独立 Prompt 模板、JSON 输出解析、Cognitive Tree 节点构建。
- **中文 Prompt 模板** — 6 个子类替换英文占位符，源自 ENGINEERING_MULTILAYER_LLM.md 5.3 节。
- **Planning HybridEngine 集成** — _phase_planning 重构，算法侧 generate_plan() + Planning-LLM 并行降级。
- **Meta-Cognitive 资源调度** — Cognitive Tree > 10 节点时每 3 轮执行一次元认知验证。
- **MetaCognitiveValidator** — 三层验证：FactualChecker（事实性）、ConsistencyChecker（一致性）、ReasonablenessChecker（合理性）+ HallucinationDetector（幻觉风险评估）。
- **ReflectiveAnalyzer** — 跨会话复盘：BiasDetector（系统性偏见/置信度高估）、LearningStrategyGenerator（P0/P1 策略）。
- **ProfileUpdater** — EMA 加权用户画像更新（F-02 公式），Track A 趋势跟踪 + Track B 冲突标记。
- **TreeHealthAnalyzer** — Cognitive Tree 健康度分析：失效比例、跨 LLM 偏误检测。
- **ColdStartProbe** — 通用冷启动专业度探测（非领域词表依赖）：5 维语言特征评分（技术词汇/参数精确度/查询复杂度/语言风格/历史行为），Max-based 子信号评分。
- **PCRFeedbackLoop** — 简化 EMA 自适应阈值：滑动窗口噪声-成功率追踪，替换硬编码 fast_path 阈值。
- **RuleConflictDetector** — 规则冲突检测：成对模式重叠分析 + fuzz 测试。
- **SchemaGuard** — Layer 1 实时拦截：JSON 校验、参数范围约束、敏感内容过滤。
- **HallucinationDetector** — Layer 2 跨轮检测：置信度尖峰、高置信失效模式、会话级累积风险。
- **BiasDetector** — Layer 3 长期复盘：置信度膨胀、系统性失效。
- **AnswerConstraintValidator** — 后处理约束验证：长度限制、危险模式过滤、空回答检测。
- **FSM 外部状态映射** — 双向状态映射（ClarificationFSM / TurnPhase）、会话级转换日志。
- **EventRegistry** — WebSocket 事件注册表：Schema 验证、核心事件保护、第三方扩展。
- **DistributedLock** — 分布式锁接口：ThreadingLockAdapter + RedisLockAdapter（自动降级）。
- **Service layer modules** — fsm_mapping.py、event_registry.py（core/service/v3_0/）。
- **Infrastructure modules** — distributed_lock.py（core/infrastructure/）。

### Changed
- **Orchestrator 重构** — 移除内联 LLMInstance/FusionEngine/AlgorithmEngine 类，改用模块导入。_run_llm 优先使用新版 LLMEngine。
- **_phase_pcr / _phase_intent** — 改为通过 HybridEngine 并行调度算法 + LLM（含向后兼容回退）。
- **_phase_answer** — 集成 ColdStartProbe 专业度探测到认知快照。
- **_phase_meta_cognitive** — 集成 MetaCognitiveValidator 规则验证前置。
- **_phase_reflective** — 集成 ReflectiveAnalyzer 规则分析前置。
- **LLM 实例子类 Prompt 模板** — 从英文占位符替换为中文工程模板。
- **ColdStartProbe 重构** — 从领域关键词匹配改为通用语言特征分析（max-based 评分）。
- **__init__.py 更新** — cognitive_compiler/orchestrator/llm_providers 导出新模块。

### Performance
- v3.0 核心测试：**0 → 65**（56 单元 + 9 集成，全部通过）。
- 新增代码：**~75 KB**（22 个新文件 + 4 个修改文件）。
- v3.0 文件总计：**~109 文件**（原 87 + 新增 22）。
- v3.0 代码行数：**~34,516 行**（原 ~31,716 + 新增 ~2,800）。



### Added
- Plugin system (`core/agent/plugin_system.py`) allowing custom `Segmenter`, `SummaryEngine`, and `HeaderInjector` strategies to be registered and injected via `DiscoursePipeline(strategy={...})`.
- Prometheus-compatible DiscourseBlockTree metrics in `core/agent/metrics.py`:
  - `discourse_pipeline_requests_total`
  - `discourse_pipeline_latency_seconds`
  - `discourse_blocks_active`
  - `discourse_blocks_total`
  - `discourse_edu_processed_total`
  - `discourse_summary_v3_triggered_total`
- Full English documentation (`README_EN.md`) parity with the Chinese README.
- API reference docs (`docs/api/README.md`, `docs/api/CONFIGURATION.md`, `docs/api/ARCHITECTURE.md`) with Mermaid diagrams.
- Contribution guidelines (`CONTRIBUTING.md`).

### Changed
- `DiscoursePipeline.__init__` now accepts an optional `strategy` dict for custom component resolution through `PluginRegistry`.
- `process_turn` now records per-request latency, EDU counts, block counts, and v3 trigger events into the lightweight metrics collector.

## [3.0.0] — 2026-07-02

### Added
- **多层 LLM 认知架构**：6 个 LLM 实例协同（PCR-LLM → Intent-LLM → Planning-LLM → Meta-Cognitive-LLM → Reflective-LLM → Answer-LLM），支持级联激活与短路优化。
- **认知双工融合引擎（Cognitive Duplex）**：算法引擎 ∥ LLM 引擎并行运行，Fusion Engine 根据置信度、延迟、成本多维评分进行动态加权融合。
- **认知树（Cognitive Tree）**：节点/边/生命周期/访问控制/事务性写入，ACTIVE → COOLING → COLD → ARCHIVED 状态机。
- **主题树（Topic Tree）**：用户话题追踪，与认知树形成正交双树结构，支持话题延续、切换、回溯、子话题嵌套。
- **认知编译器（Cognitive Compiler）**：输入 → 认知图 → 执行计划的编译器管道，驱动六层 LLM 协同激活。
- **规划 Skill 层（Planning Skill Layer）**：
  - 5 核心原语：DivideConquer、ConditionalBranch、LoopUntil、SearchVerifyExecute、TreeOfThought
  - SkillLevel 三级详细度：HIGH / MEDIUM / DETAIL
  - 模式回退链：ToT → DivideConquer → 单步执行
- **SchemaGuard + ToolBindingEngine**：工具参数 Schema 校验与运行时绑定兼容性检查。
- **异步服务层**：FastAPI + WebSocket 双通道，4 种响应格式（BRIEF / BALANCED / EXPLANATORY / TUTORIAL）。
- **LLM 提供商适配层**：ProviderManager 统一入口，支持 OpenAI、DeepSeek、LMStudio、Ollama，含故障转移、熔断、混合路由。
- **可观测性全链路**：指标（Prometheus）、结构化日志、分布式追踪、阈值告警、诊断面板、遥测聚合六维覆盖。
- **327 个测试用例**，覆盖认知树、编译器、LLM 适配、上下文管理、规划 Skill、工具注册、可观测性、编排器、服务层，全部通过。
- **16 份工程文档**（ENGINEERING_*.md）与 **4 份设计文档**（DESIGN_*.md）。
- **系统启动器**：`main_v3.py` 统一入口，`system_bootstrap.py` 配置加载与依赖注入。

### Changed
- 项目名正式统一为 **DialogMesh**（原 MemoryGraph）。
- 模块路径全面迁移至 `core/agent/v3_0/` 与 `core/service/v3_0/`。
- 测试命令更新为 `pytest core/agent/v3_0/ core/service/v3_0/ -v`。
- 配置系统升级：三级配置合并（环境变量 → user_config.yaml → agent_config.yaml）。

### Deprecated
- `core/agent/` 旧版模块（context_manager、discourse_block_tree、compiler 等）标记为废弃，将在 v3.1 中移除。
- `gui/` 目录下的 NiceGUI 面板将在 v3.2 中替换为新的认知树可视化面板。

## [0.2.0] — 2026-06-28

### Added
- **Industrial-grade refactoring**: complete rewrite of the compiler pipeline with zero LLM dependency for the core path.
- **Compiler three-stage pipeline**: `HeaderInjector` → `SyntacticDecomposer` → `MacroMicroQuantizer`.
- **9-dimensional cohesion quantization**: Macro (M1-M4) + Micro (μ1-μ5) dual-channel fusion, 0.6 × macro + 0.4 × micro.
- **Progressive summarization**: v1 (single-turn compression), v2 (intra-block merge), v3 (evolutionary summary triggered at > 5 turns).
- **Open-domain entity recognition**: jieba POS tagging + BGE semantic filtering; no hard-coded lexicon required.
- **DiscourseBlock lifecycle management**: ACTIVE → COOLING → COLD state machine with automatic turn-distance updates.
- **Configuration system**: three-tier merge (environment variables → YAML file → code defaults) with automatic type coercion.
- **Health check script** (`core/agent/health_check.py`) for BGE model, jieba, encoder, and semantic parser validation.
- **Docker multi-stage build** with model preloading and health checks.
- **Logging setup** (`core/agent/config/logging_setup.py`) supporting colored text and JSON formats.
- **MCP protocol layer** (`core/agent/mcp/`) with client/server stubs and security filters.
- **Service layer** (`core/agent/service/`) with FastAPI-compatible models, session management, and rate limiting.
- **Persistence layer** (`core/agent/persistence/`) with SQLite store, graph store, and tiered storage abstractions.
- **Topic tree v2** (`core/agent/topic_tree/`) for hierarchical topic routing.
- **Context window compressor** (`core/agent/context_window/`) with token counting and LLM-based compression.
- **LLM provider abstraction** (`core/agent/llm_providers/`) supporting OpenAI, local (LMStudio), failover, and hybrid routing.
- **Comprehensive test suite** across compiler stages, segmenter, manager, integration, persistence, and service layers.

### Changed
- Replaced turn-level minimum addressable unit with `DiscourseBlock` (fine-grained sub-turn topic boundaries).
- Migrated all hard-coded thresholds and weights into `DiscourseConfig` dataclasses.
- Refactored `DiscourseBlockTreeManager` to support merge/routing decisions based on inter-block cohesion.
- Unified data models (`EDU`, `DiscourseBlock`, `ProgressiveSummary`, `Entity`) in `core/agent/discourse_block_tree/models.py`.

### Fixed
- Windows console encoding issues in Git Bash by adding `PYTHONIOENCODING=utf-8` to Docker and build scripts.
- BGE model loading race condition when multiple `DiscoursePipeline` instances are created concurrently.
- jieba dictionary cold-start latency reduced by explicit preload in `DiscoursePipeline.preload()`.

## [0.1.0] — 2026-06-15

### Added
- **MVP (Minimum Viable Product)**: end-to-end intent parser with rule-based routing and LLM fallback.
- Basic turn-level memory management with `context_window` and `conversation_history`.
- Rule-based `IntentParser` supporting `analyze`, `execute`, `ask`, `modify` labels.
- Simple `TopicTreeManager` for flat topic clustering.
- `InteractiveAgent` loop with `respond()` entry point for CLI integration.
- `MemoryStore` abstraction for JSON-backed session persistence.
- `SemanticEncoder` stub using sentence-transformers for embedding-based similarity.
- Initial CI pipeline with `pytest` and `ruff` linting.
- Project skeleton: `core/`, `tests/`, `docs/`, `scripts/` directory layout.

[Unreleased]: https://github.com/yourusername/DialogMesh/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/yourusername/DialogMesh/compare/v0.2.0...v3.0.0
[0.2.0]: https://github.com/yourusername/DialogMesh/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yourusername/DialogMesh/releases/tag/v0.1.0
