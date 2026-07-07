# DialogMesh v3.0 / v3.2

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Tests: 217/217](https://img.shields.io/badge/tests-217%2F217-green)](docs/TEST_REPORT.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

Multi-layer LLM Cognitive Architecture with **Behavioral Cognitive Framework**.

---

## Overview

DialogMesh is an industrial-grade conversational agent system combining:

- **v3.0**: Six-layer LLM collaborative architecture with Cognitive Duplex fusion, dual-tree structure (Cognitive Tree + Topic Tree), dynamic planning, tool registry, and full-stack observability.
- **v3.2**: Behavioral Cognitive Framework with 12 modules for learning user behavior patterns (BehaviorGraph), building cognitive profiles, predicting intent, multi-track fusion, and self-evolving memory.

**Key differentiator**: Unlike pure RAG or graph-memory systems, DialogMesh learns *how the user behaves*, not just *what the user said*.

---

## Quick Start

### Installation
\`\`\`bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh
pip install -r requirements.txt
\`\`\`

### CLI (Mock Mode, no API key needed)
\`\`\`bash
python scripts/cli_v32.py "write a python function"
python scripts/cli_v32.py --demo                    # 3-query demo
python scripts/cli_v32.py --interactive              # Interactive mode
python scripts/cli_v32.py --bridge --profile --blocks # Diagnostic flags
\`\`\`

### CLI (DeepSeek)
\`\`\`bash
set DEEPSEEK_API_KEY=sk-your-key
python scripts/cli_v32.py "scan memory address 0x004000"
\`\`\`

### API Server
\`\`\`bash
python scripts/api_v32.py --provider mock --port 9100
python scripts/api_v32.py --provider deepseek --port 9100
curl http://127.0.0.1:9100/v3/process -d '{"query":"hello"}'
\`\`\`

---

## Architecture

### v3.2 Pipeline (per-turn)
\`\`\`
User Input -> Compiler (LLM+Rule) -> Causal + NegativeKB -> BehaviorGraph (EMA weights)
 -> CognitiveProfile (8 traits) -> Predictor (LLM + 4-dim ranking) -> Rewarder (correction detection)
 -> FusionEngine (4 tracks x 3 stages + Strategic Stage4)
 -> pull_v32_state() -> v3.0 Orchestrator.v32_context
 -> v3.0 phase methods inject v3.2 data into LLM prompts
\`\`\`

### v3.0 Infrastructure
Six layers: PCR -> Intent -> Planning -> Execution -> Answer -> Meta-Cognitive + Reflective (async).

### Bridge
After each turn, V32Pipeline.pull_v32_state() pushes:
- compiler: slot extraction results
- behavior_graph: high-weight edges
- cognitive_profile: metacognition/confidence/divergence
- block_tree: discourse block hierarchy

---

## Key Modules (v3.2)

| Module | Files | Purpose |
|:-------|:-----:|:--------|
| Compiler | 7 | LLM+Rule hybrid parsing, degradation chain, streaming validation |
| BehaviorGraph | 7 | EMA 4-factor weight, cold start, graph pruning, fast correction |
| FusionEngine | 5 | 4 tracks + 3 stages + Strategic stage 4, conflict resolution |
| NegativeKB | 4 | 3-level blocking (HARD_BLOCK/WARN/LEARN), fuse controller |
| BehaviorPredictor | 8 | LLM candidate gen, 4-dim value ranking, profile matching |
| BehaviorRewarder | 7 | Correction detector, reward rules, time decay, noise adaptation |
| CognitiveProfile | 8 | 8-trait stable profile, evidence chain, profile matcher, cross-session merge |
| CausalSubstrate | 6 | 8-meta-role mapping, skeleton library, delta adjuster |
| L1Summary | 5 | 3-level content classifier, meta extractor, summary generator |
| FoA | 3 | ACT-R activation propagation with inhibition, focus selection |
| DoCalculus | 3 | Backdoor criterion validator, confounder detection |
| L2Summary | 1 | Session-level aggregation, LLM compression |

### Recent Additions
- **ColdIndexer**: Layer 3 cold storage for pruned graph edges
- **ConsolidationCycle**: Batch event consolidation, activation-count pruning
- **ComplexityScorer**: Dynamic similarity threshold (anchor 0.25, range [0.08, 0.25])

---

## Test Status

**217/217 unit tests passing (100%). 8/8 edge cases passing. 13/13 LOCOMO-style integration tests passing (5 scenarios). DeepSeek 20/20 real LLM verification passing.**

| Module | Tests | Status |
|:-------|:-----:|:------:|
| Compiler | 27 | PASS |
| BehaviorGraph | 24 | PASS |
| FusionEngine | 18 | PASS |
| Predictor | 7 | PASS |
| Rewarder | 11 | PASS |
| CausalSubstrate | 5 | PASS |
| NegativeKB | 8 | PASS |
| DoCalculus | 6 | PASS |
| FoA | 6 | PASS |
| L1Summary | 6 | PASS |
| Integration | 7 | PASS |
| Pipeline | 6 | PASS |
| Benchmarks | 4 | PASS |

### LOCOMO-Style Memory Test (5 scenarios)
| Scenario | Checks | Result | Key Metrics |
|:---------|:------:|:------:|:------------|
| Memory Retention | 5/5 | PASS | 10 turns, 10 blocks, 9 edges |
| Behavior Learning | 2/2 | PASS | 10 actions, graph edges=9 |
| Topic Switching | 2/2 | PASS | 10 blocks across 3 topics |
| Correction Handling | 1/1 | PASS | 3+ edges on corrections |
| Profile Convergence | 3/3 | PASS | meta range 0.07 (15 turns), last 5 variance 0.02 |

### DeepSeek Real LLM Verification (20 queries)
- 20/20 turns completed, 100% success rate
- Compiler: 5 slots per query, stability 0.90-0.97
- BehaviorGraph: 20 nodes, 19 edges, **16 distinct action types** (vs MockLLM "run" only)
- CognitiveProfile: meta=0.600, conf=0.530, divergent=0.200 (converging)
- Monitor: 207 events across 12 module categories
- MetaCognition: self-assessed confidence aligns with system confidence (0.95 vs 0.96)

### Edge Cases Tested
Empty string, 500-char input, special characters, Chinese text, mixed EN+CN, repeated spaces, numeric only, rapid 5 consecutive turns.

### Benchmarks

| Benchmark | Latency | Description |
|:----------|:-------:|:------------|
| Degradation | 7.8 us | Cold path cache miss |
| Graph ops | 531 us | Edge record + weight update |
| Fusion | 743 us | 3-stage 4-track fusion |
| Compiler | 969 us | LLM+Rule hybrid parse |

Measured on: Windows 10, Python 3.9, 4-core CPU.

---

## Related Projects Compared

| Feature | DialogMesh | HY-Memory | HyperMem | TiMem | HiGMem |
|:--------|:----------:|:---------:|:--------:|:-----:|:------:|
| Behavior learning | YES | NO | NO | NO | NO |
| User profiling | YES | NO | NO | NO | NO |
| Causal reasoning | YES | NO | NO | NO | NO |
| Safety guardrails | YES | NO | NO | NO | NO |
| 4-track fusion | YES | System1/2 | NO | NO | NO |
| Cross-session memory | YES | YES | YES | YES | YES |
| Self-evolving updates | YES | YES | NO | YES | NO |
| Public test results | 217/217 | +22.5% | 92.73% | YES | YES |

---

## Related Projects
- [HY-Memory (Tencent)](https://memory.hunyuan.tencent.com/) - System1/System2 memory management
- [HyMEM](https://github.com/NickSiboZhu/HyMEM-GUI-Agent) - Hybrid self-evolving memory for GUI agents
- [HyperMem](https://github.com/EverMind-AI/HyperMem) - Hypergraph memory (ACL 2026)
- [TiMem](https://github.com/TiMEM-AI/timem) - Temporal hierarchical memory (ACL 2026 Findings)
- [HiGMem](https://github.com/ZeroLoss-Lab/HiGMem) - Hierarchical LLM-guided memory

---

## Performance

- Pipeline: ~30ms/turn (after BGE model load, ~15s first turn)
- BehaviorGraph: ~100KB per 100 edges
- ColdIndexer: ~10KB per 5000 records
- Config: Single-user, local BGE embedding (384-dim), DeepSeek API

---

## License

MIT License
