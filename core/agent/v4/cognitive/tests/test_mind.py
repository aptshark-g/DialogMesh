"""Mind validation — tests RelationPrior, AttentionPrior, MistakeMemory.

Uses synthetic trace data (no LLM needed) to verify:
  1. RelationPrior: edge activation → confidence boost → learned priority
  2. AttentionPrior: profile feed → EMA accumulation → top anchors
  3. MistakeMemory: warning patterns → 3-threshold → avoidance rules
  4. Cross-session: save → load → prior persists
"""
import sys, os, json, tempfile, time
sys.path.insert(0, '.')

from core.agent.v4.cognitive.mind_relation import RelationPrior, MindRelation
from core.agent.v4.cognitive.mind_attention import AttentionPrior, MindAttention
from core.agent.v4.cognitive.mind_mistakes import MistakeMemory, MindMistakes
from core.agent.state.state_object import Transition, TransitionReason, StateDelta, StateObject


def test_relation_prior():
    """Edge activation → confidence boost → learned priority."""
    rp = RelationPrior()
    
    # Simulate: Runtime→Scheduler edge activated, then confidence rises
    t1 = Transition(reason=TransitionReason.ACTIVATE, evidence=["Runtime→Scheduler"])
    t2 = Transition(reason=TransitionReason.INFER, evidence=["Runtime→Scheduler"], confidence=0.6)
    t3 = Transition(reason=TransitionReason.STRENGTHEN, confidence=0.8)
    
    n = rp.learn_from_trace([t1, t2, t3])
    # Single pass gives score ~0.21, need >0.3 for best_relations
    # Run 3 more cycles to build up the score
    for _ in range(3):
        rp.learn_from_trace([t1, t2, t3])
    best = rp.best_relations()
    
    assert n > 0, f"Should learn relations, got {n}"
    assert len(best) > 0, f"Should have best relations, got {best}"
    print(f"  RelationPrior: learned={n}, best={best[0] if best else 'none'}")

    # Save + Load
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    rp.save(path)
    rp2 = RelationPrior()
    assert rp2.load(path), "Load should succeed"
    os.unlink(path)
    print(f"  Persist: saved + loaded OK")


def test_attention_prior():
    """Profile feed → EMA accumulation → top anchors."""
    ap = AttentionPrior(alpha=0.2)
    
    # Simulate 5 turns of attention to 'Runtime'
    class MockTrackA:
        attention_anchor = 0.6
        attention_label = 'Runtime'
    
    for _ in range(5):
        ap.feed_profile(MockTrackA())
    
    anchors = ap.top_anchors()
    assert len(anchors) > 0, f"Should have anchors, got {anchors}"
    assert anchors[0][1] > 0.52, f"Runtime weight should rise above neutral: {anchors[0]}"
    print(f"  AttentionPrior: anchors={anchors}")


def test_mistake_memory():
    """3-occurrence threshold → avoidance rule."""
    mm = MistakeMemory()
    
    # Feed "consecutive_rejects" warning 3 times
    for _ in range(3):
        n = mm.learn_from_warnings(
            ["consecutive_rejects"],
            ["switch perspective", "lower depth"],
            {"perspective": "architecture", "domain": "runtime", "depth": 3}
        )
    
    # After 3, should have avoidance rule
    rules = mm.should_avoid({"perspective": "architecture", "domain": "runtime", "depth": 3})
    assert len(rules) > 0, f"Should have rules after 3 occurrences, got {rules}"
    print(f"  MistakeMemory: rules={rules}")
    
    # Same context triggers rules, different doesn't
    no_rules = mm.should_avoid({"perspective": "engineering", "domain": "ui", "depth": 1})
    assert len(no_rules) == 0, f"Different context should have no rules: {no_rules}"
    print(f"  Context isolation: engineering→no rules ✅")


def test_cross_session():
    """Save → restart → load → prior persists."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        rpath = f.name
    
    # Session 1: learn relations
    mr1 = MindRelation(persist_path=rpath)
    t1 = Transition(reason=TransitionReason.ACTIVATE, evidence=["Observer→Workspace"])
    t2 = Transition(reason=TransitionReason.STRENGTHEN, confidence=0.75)
    # Need multiple cycles to build score above 0.3
    for _ in range(5):
        mr1.learn([t1, t2])
    mr1.save()
    
    # Session 2: load and should have prior
    mr2 = MindRelation(persist_path=rpath)
    assert mr2.load(), "Should load saved priors"
    stats = mr2.stats()
    assert stats['active_relations'] > 0, f"Should have active relations: {stats}"
    print(f"  Cross-session: {stats}")
    os.unlink(rpath)


if __name__ == "__main__":
    print("Mind Validation\n═══════════")
    test_relation_prior()
    test_attention_prior()
    test_mistake_memory()
    test_cross_session()
    print("\n✅ All Mind tests passed")
