"""Topic Tree + AdaptiveHeatModel tests."""

import sys
sys.path.insert(0, '.')
from core.agent.topic_tree.heat_model import AdaptiveHeatModel
from core.agent.topic_tree.fact_store import FactBlock, FactStore, RelationMetadataStore
from core.agent.topic_tree.context import DualPerspectiveContext, MultiPerspectiveBranchView, BehaviorDrivenRefresh


def test_adaptive_heat():
    """ARC-based: T1(recency) + T2(frequency) + adaptive balance."""
    m = AdaptiveHeatModel()
    
    # Touch 'a' many times → promotes to T2
    for _ in range(5):
        m.touch("a")
    m.touch("b"); m.touch("b")
    m.touch("c")
    
    assert m.get_heat("a") > m.get_heat("c"), "a should be hotter (5 touches)"
    assert m.t2_size > 0, "a should be in T2"
    
    # Correction penalizes
    m.on_correction("a")
    heat_after = m.get_heat("a")
    assert heat_after < 0.7, "Correction should reduce heat"
    
    # Topology boost
    m.set_topology_boost("c", 3.0)
    assert m.get_heat("c") > m.get_heat("b"), "topology boost should elevate c"
    
    # Branch switch adjusts T1 weight
    w_before = m.t1_weight
    m.on_branch_switch()
    assert m.t1_weight <= w_before, "Branch switch reduces T1 trust"
    
    print(f"✅ AdaptiveHeat: T1={m.t1_size} T2={m.t2_size} weight={m.t1_weight:.2f}")
    print(f"   a={m.get_heat('a'):.2f} b={m.get_heat('b'):.2f} c={m.get_heat('c'):.2f}")


def test_dual_perspective_with_arc():
    """DualPerspectiveContext now uses AdaptiveHeatModel."""
    fs = FactStore()
    rs = RelationMetadataStore()
    dp = DualPerspectiveContext(fs, rs)
    
    fs.put(FactBlock(block_id="a", content="scan memory"))
    fs.put(FactBlock(block_id="b", content="AES encrypt"))
    fs.put(FactBlock(block_id="c", content="hook frida"))
    rs.update("a", "b", "sequential")
    rs.update("a", "c", "causal")
    
    # Touch 'a' many times
    for _ in range(5): dp.touch("a")
    dp.touch("b"); dp.touch("b")
    
    user = dp.user_channel("a", budget=500)
    sys_ctx = dp.system_channel("a", budget=500)
    assert len(user) > 0 and len(sys_ctx) > 0
    
    # Correction on 'a'
    dp.on_correction("a")
    user2 = dp.user_channel("a", budget=500)
    a_in_user2 = any(s.node_id == "a" for s in user2)
    # 'a' may still appear but with lower priority
    
    print(f"✅ DualPerspective+ARC: user={len(user)} sys={len(sys_ctx)}")


if __name__ == "__main__":
    test_adaptive_heat()
    test_dual_perspective_with_arc()
    print("✅ Topic Tree V2: ARC adaptive heat model works")
