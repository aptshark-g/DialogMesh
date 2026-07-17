# Quality Gates — Anti-Simplification Firewall

## Problem Diagnosis

Agent implementation under black-box constraints tends to:
1. **Simplify**: "design says Blueprint pattern → I'll just write an if-else"
2. **Bypass**: "there's an existing module → but creating a new file is faster"
3. **Hardcode**: "threshold=5 works now → no need for ParameterRegistry"
4. **Stub**: "module created → tested → never actually called"

These failures are invisible to traditional tests (existence checks pass).

## Measurement Gates

### G1: Soft-Config Coverage

```
SoftConfigRatio = |strings in soft_config/*.json| / |hardcoded strings matching soft-config keys in code|
Target: > 0.95
Current: ~0.60 (perspective_strategies, importance_signals, intent_patterns exist, 
                but engine.py still has hardcoded strings for evidence/text matching)
```

**Implementation check**: `grep -r "architecture\|engineering\|execution\|evolution" engine.py discourse_block_tree.py | grep -v "import\|from\|#" | wc -l` → should be 0 unless in soft_config references.

### G2: Module Reuse Rate

```
ReuseRate = |preexisting modules used| / |total new modules or duplicated functionality|
Target: > 0.80
Current: ~0.75 (used TieredParser, JiebaRelationParser, BGE, but also created
                standalone extraction_blueprint when ExtractionOrchestrator existed)
```

**Detector**: When a new file is created, scan imports. If it imports < 2 existing modules from the target area, flag as potential bypass.

### G3: Integration Completeness

```
IntegrationCompleteness = |modules with call-site in engine.start()| / |total modules with _init_ prefix|
Target: 1.00
Current: ~0.85 (_init_extraction_orchestrator() was defined but never called — 2-week bug)
```

**Auto-check**: `grep -r "_init_" engine.py | grep -o "_init_\w*" | sort | uniq -c | sort -rn` → every method should appear exactly 2× (definition + call).

### G4: Transition Type Completeness

```
TransitionCoverage = |TransitionReason types actually recorded| / |TransitionReason types defined|
Target: > 0.60 (all major: OBSERVE, INFER, REFLECT, REJECT, STRENGTHEN, ACTIVATE)
Current: 4/19 (OBSERVE, ACTIVATE, INFER, REFLECT only)
```

**Live test check**: `trace.meta_analyze()["reason_distribution"]` → should show ≥6 types after 10 turns. Missing: REJECT, STRENGTHEN, WEAKEN, COMPARE, SHIFT_ATTENTION, MERGE.

### G5: Policy Effectiveness

```
PolicyEffective = |policy.apply() calls| / |turns with policy generated|
Target: > 0.80 (policy should change engine behavior at least 80% of the time)
Current: ~0.40 (policy generated but often NOT applied due to confidence gates)
```

**Check**: Monitor `policy` event → check if next `strategy` event shows different strategy name.

### G6: Design-to-Code Fidelity

```
DesignFidelity = |modules matching design doc structure| / |modules in design doc|
Target: > 0.90
Current: ~0.70 (DiscourseBlockTree has HeaderInjector/SyntacticDecomposer/MacroMicroQuantizer
                but InternalSimulationEngine skips UserCognitiveState constructor from design)
```

**Auto-check**: Parse DESIGN_*.md for module names → grep code for matching class names. Ratio < 0.9 = design simplified.

### G7: Test Depth

```
TestDepth = |tests that check specific quality property| / |total tests|
Target: > 0.50
Current: ~0.15 (29 tests, only test_linkage_quality_v2.py checks
                actual content quality, rest are existence assertions)
```

**Quality test pattern** (not existence):
- `assert "architecture" in render.strategy` → `assert primary.strategy != secondary.strategy`
- `assert len(blocks) > 0` → `assert blocks[-1].importance > blocks[-2].importance`
- `assert stats > 0` → `assert camel_ratio > 0.3`
- `assert resp` → `assert len(set(turn.strategies)) > 1` (strategies differ across turns)

## Enforcement

### Pre-commit gate (`make quality`)

```makefile
quality:
	@echo "G1 Soft-Config Coverage:"
	@python scripts/check_softconfig.py
	@echo "G2 Module Reuse:"
	@python scripts/check_module_reuse.py --new-files=$$(git diff --name-only HEAD~1)
	@echo "G3 Integration:"
	@python scripts/check_integration.py engine.py
	@echo "G4 Transition Types:"
	@python scripts/check_transitions.py
```

### Live runtime gate (in-engine)

```python
# At session end, engine.close() logs:
quality_report = {
    "G4_transition_types": len(trace.meta_analyze()["reason_distribution"]),
    "G5_policy_effective": policy_applied_count / max(1, policy_count),
    "G6_design_fidelity": _check_module_coverage(),
}
logger.info("Quality: %s", quality_report)
```

## Target Scores

| Gate | Production | Staging | Dev |
|------|-----------|---------|-----|
| G1 Soft-Config | ≥ 0.95 | ≥ 0.85 | ≥ 0.70 |
| G2 Module Reuse | ≥ 0.90 | ≥ 0.80 | ≥ 0.70 |
| G3 Integration | = 1.00 | = 1.00 | ≥ 0.95 |
| G4 Transition Types | ≥ 8 | ≥ 6 | ≥ 4 |
| G5 Policy Effective | ≥ 0.80 | ≥ 0.60 | ≥ 0.40 |
| G6 Design Fidelity | ≥ 0.95 | ≥ 0.90 | ≥ 0.80 |
| G7 Test Depth | ≥ 0.50 | ≥ 0.35 | ≥ 0.20 |
