# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/yourusername/memorygraph/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/yourusername/memorygraph/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yourusername/memorygraph/releases/tag/v0.1.0
