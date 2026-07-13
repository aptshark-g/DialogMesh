"""Integration test: new Context Engineering pipeline.

Tests the full flow:
  Intent → DomainSelector → BudgetAllocator → CrossDomainContextIR
  → CrossDomainExpander(stub) → CrossRefBuilder(stub) → Pruner(stub)
"""
from __future__ import annotations
import sys
sys.path.insert(0, r'C:\Users\APTShark\.codex\worktrees\bd48\DialogMesh')

from core.agent.v4.context import (
    DomainSelector, IntentCategory, Domain, DomainRole,
    BudgetAllocator, DomainBudget, BudgetPlan,
    CrossDomainContextIR, IREntry, CrossRef,
    IRDomainAllocation, IRDomainRole, IRIntentCategory,
    CrossDomainExpander, ExpandedEventNode,
    CrossRefBuilder, CrossRefPointer,
    SubgraphPruner, PruningNode, PruningConfig,
)


def test_full_pipeline():
    """End-to-end: intent → IR with budget + expand + cross_ref + prune."""
    print("=" * 60)
    print("Test: Full Context Engineering Pipeline")
    print("=" * 60)

    # Step 1: Intent → Domain Selection
    selector = DomainSelector()
    selection = selector.select(IntentCategory.TASK)
    print(f"\n[1] DomainSelection: intent={selection.intent_category.value}")
    print(f"    primary={selection.primary_domain.value if selection.primary_domain else None}")
    for a in selection.allocations:
        print(f"    {a.domain.value}: {a.role.value} @ {a.budget_pct*100:.0f}%")
    assert selection.primary_domain == Domain.ENGINEERING
    assert selection.budget_for(Domain.BEHAVIOR) == 0.25

    # Step 2: Budget Allocation
    allocator = BudgetAllocator(strategy_tokens=300)
    plan = allocator.allocate("task")
    print(f"\n[2] BudgetPlan: total={plan.total_budget} tokens")
    print(f"    mandatory={plan.mandatory_tokens}, strategy={plan.strategy_tokens}, flexible={plan.flexible_tokens}")
    for db in plan.strategy_plan:
        print(f"    {db.domain}({db.role}): {db.budget_tokens} tokens")
    assert plan.strategy_plan[0].domain == "E"
    assert plan.strategy_plan[0].budget_tokens == 180
    assert plan.compile_strategy == "primary_deep"

    # Step 3: Build CrossDomainContextIR
    ir = CrossDomainContextIR(
        intent_category=IRIntentCategory.TASK,
        domain_allocation=[
            IRDomainAllocation(domain="E", role=IRDomainRole.PRIMARY, budget_pct=0.60, budget_tokens=180),
            IRDomainAllocation(domain="B", role=IRDomainRole.AUXILIARY, budget_pct=0.25, budget_tokens=75),
            IRDomainAllocation(domain="P", role=IRDomainRole.AUXILIARY, budget_pct=0.15, budget_tokens=45),
        ],
        entries=[
            IREntry(domain="E", type="MODULE", content="ModuleA timeout=5000", confidence=0.95, estimated_tokens=25),
            IREntry(domain="E", type="MODULE", content="ModuleB missing monitor", confidence=0.80, estimated_tokens=30),
            IREntry(domain="B", type="ACTION", content="set_timeout(ModuleA)", confidence=0.90, estimated_tokens=20),
            IREntry(domain="P", type="PREFERENCE", content="visual_debug=True", confidence=0.85, estimated_tokens=15),
        ],
        compile_strategy="primary_deep",
    )
    ir.recalc_total()
    print(f"\n[3] CrossDomainContextIR: {len(ir.entries)} entries, {ir.total_estimated_tokens} tokens")
    assert ir.total_estimated_tokens == 90

    # Step 4: CrossDomainExpander (stub)
    expander = CrossDomainExpander()
    anchor_events = ["evt_001", "evt_002"]
    expanded = expander.expand(anchor_events, "task")
    print(f"\n[4] CrossDomainExpander: {len(expanded)} anchor events expanded")
    for node in expanded:
        print(f"    {node.event_id}: {len(node.projections)} projections")
    assert len(expanded) == 2

    # Step 5: CrossRefBuilder (stub)
    builder = CrossRefBuilder(max_refs_per_entry=2)
    entries_with_refs = builder.build(ir.entries)
    print(f"\n[5] CrossRefBuilder: {len(entries_with_refs)} entries with cross_refs")
    for e in entries_with_refs:
        print(f"    [{e.domain}:{e.type}] {len(e.cross_refs)} cross_refs")
    assert len(entries_with_refs) == 4

    # Step 6: SubgraphPruner (stub)
    pruner = SubgraphPruner()
    pruning_nodes = [
        PruningNode(node_id="n1", domain="E", content="ModuleA", activation_count=10, last_accessed_turn=5, betweenness=0.8, estimated_tokens=25),
        PruningNode(node_id="n2", domain="E", content="ModuleB", activation_count=3, last_accessed_turn=1, betweenness=0.3, estimated_tokens=30),
        PruningNode(node_id="n3", domain="B", content="set_timeout", activation_count=8, last_accessed_turn=4, betweenness=0.5, estimated_tokens=20),
        PruningNode(node_id="n4", domain="P", content="visual_debug", activation_count=2, last_accessed_turn=1, betweenness=0.2, estimated_tokens=15),
    ]
    pruned = pruner.prune(pruning_nodes, budget=50, turn=5, intent="task")
    print(f"\n[6] SubgraphPruner: {len(pruned)} nodes after pruning (budget=50)")
    for n in pruned:
        print(f"    {n.node_id}: {n.estimated_tokens} tokens, compressed={n.compressed}")

    # Step 7: Legacy bridge
    legacy = ir.to_legacy_context()
    print(f"\n[7] Legacy bridge: {legacy.total_items} items")
    assert legacy.total_items == 4

    print("\n" + "=" * 60)
    print("All integration tests passed!")
    print("=" * 60)


def test_intent_matrix_coverage():
    """Verify all 6 intent categories produce correct domain selections."""
    print("\n" + "=" * 60)
    print("Test: Intent Matrix Coverage")
    print("=" * 60)

    selector = DomainSelector()
    expectations = {
        IntentCategory.TASK: ("E", "B", "P"),
        IntentCategory.QUERY: ("C", "E", "P"),
        IntentCategory.CORRECTION: ("B", "E", "K"),
        IntentCategory.DISCUSSION: ("P", "C", "E"),
        IntentCategory.CASUAL: ("C", "P", None),
        IntentCategory.TOPIC_SWITCH: ("C", "B", "P"),
    }

    for intent, (exp_primary, exp_a1, exp_a2) in expectations.items():
        sel = selector.select(intent)
        primary = sel.primary_domain.value if sel.primary_domain else None
        domains = [a.domain.value for a in sel.allocations]
        print(f"  {intent.value:12} → primary={primary}, domains={domains}")
        assert primary == exp_primary, f"{intent.value}: expected primary {exp_primary}, got {primary}"
        assert exp_primary in domains
        if exp_a1:
            assert exp_a1 in domains
    print("\n  All 6 intent categories verified!")


def test_budget_strategies():
    """Test quality_first / balanced / cost_first strategies."""
    print("\n" + "=" * 60)
    print("Test: Budget Strategies")
    print("=" * 60)

    allocator = BudgetAllocator(strategy_tokens=300)

    for strategy in ["quality_first", "balanced", "cost_first"]:
        plan = allocator.allocate("task", user_strategy=strategy)
        primary = plan.strategy_plan[0].budget_tokens
        print(f"  {strategy:14} → primary(E)={primary} tokens ({primary/300*100:.0f}%)")

    # quality_first: 70% → 210
    plan_qf = allocator.allocate("task", user_strategy="quality_first")
    assert plan_qf.strategy_plan[0].budget_tokens == 210

    # cost_first: 50% → 150
    plan_cf = allocator.allocate("task", user_strategy="cost_first")
    assert plan_cf.strategy_plan[0].budget_tokens == 150

    print("\n  All strategies verified!")


if __name__ == "__main__":
    test_full_pipeline()
    test_intent_matrix_coverage()
    test_budget_strategies()
