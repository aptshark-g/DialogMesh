# Cognitive Profile v2 Implementation Plan

> **For Hermes:** Implement task-by-task in order. Each task is a self-contained ~5min unit.

**Goal:** Implement the dual-track Cognitive Profile v2 as designed in `design_cognitive_profile_v2.md` + `ENGINEERING_COGNITIVE_PROFILE_V2.md`

**Architecture:** Track A (cognitive dynamics) + Track B (tag layer) → Fusion → ProfileContextSource → Context IR

**Files to create:** `core/agent/v4/cognitive/` package (~4 modules), wire into engine

---

## Task 1: Create data models (`core/agent/v4/cognitive/models.py`)

UserTag, MemoryPoint, MemoryChunk, CognitiveDynamics dataclasses from ENGINEERING_COGNITIVE_PROFILE_V2.md §2.

## Task 2: Memory decay system (`core/agent/v4/cognitive/memory_decay.py`)

MemoryChunk.get_effective_weight() with stage factors (hot/warm/cool/cold), MemoryPoint.compute_composite_weight() with power-law decay.

## Task 3: Cognitive dynamics — inertia + trust + emotion (`core/agent/v4/cognitive/dynamics.py`)

Track A 9 dimensions:
- `cognitive_inertia`: Pearson autocorrelation of style preference over last N turns
- `trust_score`: system commitment fulfillment rate T(S,O)
- `emotional_entropy`: Shannon entropy of recent emotion polarities
- `attention_anchor`: TF-IDF weighted topic of current branch
- `expectation_deviation`: running average of satisfaction deltas
- `memory_points`: accumulation + decay of high-impact events
- `self_value_score`: self-affirmation language frequency
- `cognitive_resource`: inferred from response speed + query complexity
- `behavior_inertia`: acceptance/clarification/dispute rate of system suggestions

## Task 4: Tag layer + inference (`core/agent/v4/cognitive/tag_layer.py`)

Track B with L1-L4 acquisition:
- L1 (passive): language detection, emoji usage, device type, session_context
- L2 (inferred): occupation, domain, education, technical_depth from dialogue patterns
- UserTag with confidence gating + Bayesian update

## Task 5: Fusion + ProfileContextSource upgrade

Combine Track A dynamics + Track B tags into structured LLM context. Upgrade existing ProfileContextSource.

## Task 6: Wire into engine

Update `_create_context_assembler()` to use CognitiveProfileV2. Update profile after each turn.

## Task 7: Tests

Unit tests for memory decay math, dynamics computation, tag inference, fusion output format.

---

**Verification:** `PYTHONPATH=C:\Users\APTShark\PycharmProjects\DialogMesh .venv-test\Scripts\python -m pytest core/agent/v4/cognitive/tests/ -q`
