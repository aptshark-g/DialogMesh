"""Topic Tree Tests — fact store, relation metadata, dual perspective, branch view, refresh."""

import sys, time
sys.path.insert(0, '.')
from core.agent.topic_tree.fact_store import FactBlock, FactStore, RelationMetadata, RelationMetadataStore
from core.agent.topic_tree.context import (
    DualPerspectiveContext, MultiPerspectiveBranchView, BehaviorDrivenRefresh, Summary
)


def test_fact_store():
    """Immutable facts — content never changes."""
    fs = FactStore()
    a = FactBlock(block_id="a", content="用户扫描内存 0x401000", entities=["0x401000", "scan"])
    b = FactBlock(block_id="b", content="用户分析 AES 加密", entities=["AES", "encrypt"])
    fs.put(a)
    fs.put(b)
    
    assert fs.get("a").content == "用户扫描内存 0x401000"
    assert len(fs.by_entity("0x401000")) == 1
    assert len(fs.by_entity("AES")) == 1
    
    # Put again — should be idempotent (no duplicate)
    fs.put(a)
    assert len(fs) == 2
    print("✅ FactStore: immutable, idempotent")


def test_relation_metadata():
    """Relations change — versioned metadata."""
    rs = RelationMetadataStore()
    rs.update("a", "b", "sequential")
    assert rs.get("a", "b").relation_type == "sequential"
    assert rs.get("a", "b").version == 1
    assert not rs.get("a", "b").is_changed
    
    # Relation changes
    rs.update("a", "b", "causal")
    assert rs.get("a", "b").relation_type == "causal"
    assert rs.get("a", "b").version == 2
    assert rs.get("a", "b").is_changed  # a→b 从 sequential 变成 causal
    
    # History
    history = rs.history("a", "b")
    assert len(history) == 2
    assert history[0].relation_type == "sequential"
    assert history[1].relation_type == "causal"
    
    # Rollback
    assert rs.rollback("a", "b", 1)
    assert rs.get("a", "b").relation_type == "sequential"
    print("✅ RelationMetadata: versioned, rollback, change tracking")


def test_dual_perspective():
    """User channel (temperature) + system channel (distance)."""
    fs = FactStore()
    rs = RelationMetadataStore()
    dp = DualPerspectiveContext(fs, rs)
    
    a = FactBlock(block_id="a", content="扫描内存 0x401000" * 5)
    b = FactBlock(block_id="b", content="分析加密算法 AES" * 3)
    c = FactBlock(block_id="c", content="hook frida 函数" * 4)
    fs.put(a); fs.put(b); fs.put(c)
    rs.update("a", "b", "sequential")
    rs.update("a", "c", "causal")
    
    # Heat up 'a' and 'b'
    dp.touch("a"); dp.touch("a"); dp.touch("b")
    
    user = dp.user_channel("a", budget=500)
    sys_ctx = dp.system_channel("a", budget=500)
    
    assert len(user) > 0, "Should have hot blocks in user channel"
    assert len(sys_ctx) > 0, "Should have topology neighbors in system channel"
    
    # Full assembly
    full = dp.assemble("a", token_budget=1000)
    assert len(full) > 0
    print(f"✅ DualPerspective: user={len(user)} blocks, system={len(sys_ctx)} blocks, total={len(full)}")


def test_multi_perspective_branch():
    """Multiple modules disagree on branch — don't pick, present all."""
    mp = MultiPerspectiveBranchView()
    mp.register("discourse_tree", "block_x", "branch_A", "词汇链相似度 0.85")
    mp.register("graph_community", "block_x", "branch_B", "跨域模块度 0.62")
    mp.register("association", "block_x", "branch_A", "语义类型兼容")
    
    view = mp.get_view("block_x")
    assert not view["consensus"], "Should NOT have consensus (2 say A, 1 says B)"
    assert len(view["perspectives"]) == 3
    print(f"✅ MultiPerspective: {view['summary']}")


def test_behavior_refresh():
    """Correction = P0, topic switch = P1, TTL = P2."""
    br = BehaviorDrivenRefresh()
    
    # Initially, no refresh needed
    assert not br.should_refresh("block_x", layer=1)
    
    # Correction: P0 — immediate
    br.on_correction("block_x", "用户指出摘要漏了关键实体")
    assert br.should_refresh("block_x", layer=1)
    br.mark_refreshed("block_x")
    assert not br.should_refresh("block_x", layer=1)
    
    # Topic switch: P1
    br.on_topic_switch("branch_active")
    assert br.should_refresh("branch_active", layer=2)
    
    # Local model: L1 can refresh every turn
    br.set_local_model(True)
    assert br.should_refresh("any_block", layer=1)  # L1 always OK with local model
    
    # L2 without local model: needs TTL expiration
    br.set_local_model(False)
    assert not br.should_refresh("cold_block", layer=2, ttl_rounds=100)  # TTL not expired
    
    print("✅ BehaviorDrivenRefresh: P0 correction, P1 topic switch, local model L1, TTL")


if __name__ == "__main__":
    test_fact_store()
    test_relation_metadata()
    test_dual_perspective()
    test_multi_perspective_branch()
    test_behavior_refresh()
    print("\n🎉 All Topic Tree tests passed")
