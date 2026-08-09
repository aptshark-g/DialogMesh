"""Integration Test — full on_event pipeline with all modules."""

import sys, time
sys.path.insert(0, '.')
from core.agent.topic_tree.manager import TopicTreeManager
from core.agent.cognitive.learning_loop import LearningLoop
from core.agent.pcr_router_v2 import PCRRouterV2
from core.agent.event.event_bus import EventBus
from core.agent.api.api_event_log import EventLog
from core.agent.state.global_decider import GlobalDecider, Command
from core.agent.state.trigger_conditions import TRIGGER_CONDITIONS


def test_full_pipeline():
    """Simulate a conversation flow with all modules active."""
    
    # Init all modules
    tree = TopicTreeManager()
    loop = LearningLoop()
    bus = EventBus()
    log = EventLog("data/test_integration.db")
    decider = GlobalDecider()
    
    # Simulate 5 conversation turns
    messages = [
        ("scan 0x401000 for entry point", "TOOL"),
        ("这个加密算法是什么", "ADVISOR"),
        ("hook frida来分析行为", "TOOL"),
        ("我搞了三天太累了", "COMPANION"),
        ("能帮我总结一下目前的发现吗", "ADVISOR"),
    ]
    
    results = []
    for i, (text, expected_zone) in enumerate(messages):
        msg_id = f"msg_{i}"
        
        # Topic Tree: record fact
        tree.touch(msg_id, text)
        
        # PCR
        pcr = PCRRouterV2.route(text)
        
        # Decider: track events
        decider.evolve(decider.decide(Command(type="pcr")))
        bus.publish_sync("pcr_computed", {"zone": pcr.zone})
        
        # Learning Loop: feed signals
        if i == 3:  # User is frustrated
            loop.on_user_corrected("摘要不准确")
        
        # Context assembly
        ctx = tree.assemble_context(msg_id, token_budget=500)
        
        results.append({
            "turn": i,
            "text": text[:30],
            "zone": pcr.zone,
            "mode": pcr.execution_mode,
            "ctx_count": len(ctx),
            "heat_nodes": tree.heat.stats()["total_nodes"],
        })
    
    # Verify pipeline integrity
    assert len(results) == 5
    assert tree.stats["facts"] == 5, "5 facts should be recorded"
    assert tree.stats["heat"]["total_nodes"] == 5, "5 heat nodes"
    assert tree.stats["relations"] == 4, "4 relations (N-1 sequential)"
    assert loop.correction_count == 1, "1 correction signal"
    assert decider.state.tick > 0, "Decider should have ticks"
    
    print("=== Integration Test Results ===")
    for r in results:
        print(f"  Turn {r['turn']}: {r['zone']:10s} {r['mode']:10s} ctx={r['ctx_count']} heat={r['heat_nodes']} | {r['text']}")
    
    print(f"\nTree: {tree.stats['facts']} facts, {tree.stats['relations']} relations, {tree.stats['heat']['t1_size']} T1 nodes")
    print(f"Learning: {loop.correction_count} corrections, {loop.pending_count} pending signals")
    print(f"Decider: {decider.state.tick} ticks")
    bus.drain_sync()
    print("\n✅ Integration: all modules active, pipeline intact")


if __name__ == "__main__":
    test_full_pipeline()
    print("🎉 P7: End-to-end integration test passed")
