"""Learning Loop Test."""

import sys
sys.path.insert(0, '.')
from core.agent.cognitive.learning_loop import LearningLoop


def test_learning_loop():
    loop = LearningLoop()
    
    # User corrects
    loop.on_user_corrected("摘要漏了关键实体")
    assert loop.correction_count == 1
    assert loop.pending_count == 2  # signal to profile + meta
    
    # Behavior finds pattern
    loop.on_pattern_discovered("scan→patch→verify", confidence=0.85)
    assert len(loop.behavior_patterns) == 1
    assert loop.pending_count == 4  # +2 more signals
    
    # Profile drifts
    loop.on_profile_drift("conscientiousness", 0.8, 0.5)
    assert loop.drift_detected
    assert loop.get_meta_review_needed()  # drift triggers review
    
    # Profile gets adjustments
    adj = loop.get_profile_adjustment()
    assert adj["trust_delta"] < 0  # correction + drift → negative
    
    print(f"✅ LearningLoop: {loop.pending_count} signals, meta_review={loop.get_meta_review_needed()}")
    print(f"   Profile adjustment: trust_delta={adj['trust_delta']:.3f}")


if __name__ == "__main__":
    test_learning_loop()
    print("🎉 P0-3 Learning Loop works")
