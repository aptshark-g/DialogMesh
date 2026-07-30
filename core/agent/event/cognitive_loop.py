"""Cognitive closure — heartbeat for behavior learning + meta review.

All components exist but form an open loop:
  Chat → Behavior records edge → ??? (no learning trigger)
  Behavior accumulates edges → ??? (no meta review)  
  Meta reviews → ??? (no feedback loop)

This module closes the loop with scheduled triggers + active invocation."""
import time, threading, logging
from typing import Optional

logger = logging.getLogger(__name__)


class BehaviorLearner:
    """Periodically analyze behavior chains and update weights (RL loop).

    Trigger: every N conversations or via dm alg behavior-learn.
    Process: CausalPlanner.slow_path() → WeightUpdater → saves to disk."""

    def __init__(self, engine, interval_turns: int = 5):
        self._engine = engine
        self._interval = interval_turns  # trigger every N turns
        self._turn_counter = 0
        self._last_learn_at = time.time()
        self._learning_thread = None
        self._results: list = []

    def maybe_learn(self) -> Optional[dict]:
        """Called after each conversation turn. Triggers learning at interval."""
        self._turn_counter += 1
        if self._turn_counter % self._interval != 0:
            return None

        return self.learn_now()

    def learn_now(self) -> dict:
        """Force behavior learning now — analyze recent chains, update weights."""
        bg = getattr(self._engine, '_behavior_graph', None)
        result = {"edges_analyzed": 0, "patterns_found": 0, "weights_updated": 0}

        if bg and hasattr(bg, 'get_recent_chain'):
            chains = bg.get_recent_chain(20)
            result["edges_analyzed"] = len(chains)

            # Analyze chain patterns
            patterns = {}
            for step in chains:
                kind = getattr(step, 'kind', getattr(step, 'event_type', 'unknown'))
                patterns[kind] = patterns.get(kind, 0) + 1
            result["patterns_found"] = len(patterns)
            result["pattern_detail"] = patterns

        # Trigger CausalPlanner slow path if available
        cp = getattr(self._engine, '_causal_planner', None)
        if cp and hasattr(cp, 'slow_path'):
            try:
                cp.slow_path()
                result["causal_path"] = True
            except Exception as e:
                logger.debug("CausalPlanner slow_path failed: %s", e)

        # Persist behavior graph
        if bg and hasattr(bg, 'save'):
            try:
                import os
                root = os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__)))))
                bg.save(os.path.join(root, "data", "behavior_graph.json"))
                result["weights_updated"] = True
            except Exception as e:
                logger.debug("Behavior save failed: %s", e)

        self._last_learn_at = time.time()
        self._results.append(result)
        logger.info("BehaviorLearner: analyzed %d edges, %d patterns",
                     result["edges_analyzed"], result["patterns_found"])
        return result


class MetaReviewer:
    """Periodically review what the system learned from behavior.

    Trigger: after BehaviorLearner.learn_now() or via dm alg meta-review.
    Process: MetaCognition.review_chains() → generates insights → updates profile."""

    def __init__(self, engine):
        self._engine = engine
        self._review_count = 0
        self._insights: list = []

    def review_now(self, behavior_results: dict = None) -> dict:
        """Review behavior patterns and generate meta-level insights."""
        mc = getattr(self._engine, '_meta_cognition', None)
        result = {"reviewed": False, "insights": []}

        behavior_patterns = behavior_results.get("pattern_detail", {}) if behavior_results else {}

        if mc:
            # Tell meta cognition what the behavior learner found
            if hasattr(mc, 'ingest'):
                try:
                    mc.ingest({
                        "type": "behavior_patterns",
                        "patterns": behavior_patterns,
                        "timestamp": time.time(),
                    })
                    result["reviewed"] = True
                except Exception:
                    pass

            if hasattr(mc, 'review_chains'):
                try:
                    insights = mc.review_chains()
                    if insights:
                        result["insights"] = insights[:5]
                        self._insights.extend(insights)
                        result["reviewed"] = True
                except Exception:
                    pass

            if hasattr(mc, 'consolidate'):
                try:
                    mc.consolidate()
                    result["consolidated"] = True
                except Exception:
                    pass

        # Update OCEAN profile based on behavior patterns
        ocean = getattr(self._engine, '_ocean_analyst', None)
        if ocean and behavior_patterns:
            # Frequent "设计/规划" patterns → increase C
            if any(k in str(behavior_patterns).lower() for k in ["plan", "design", "规划", "设计"]):
                profile = getattr(ocean, 'profile', None)
                if profile and hasattr(profile, 'dims'):
                    dims = profile.dims
                    dims["C"] = min(1.0, dims.get("C", 0.5) + 0.05)
                    result["profile_updated"] = "C"

        self._review_count += 1
        result["review_count"] = self._review_count
        logger.info("MetaReviewer: review #%d, %d insights",
                     self._review_count, len(result.get("insights", [])))
        return result


class CognitiveLoop:
    """Closed-loop: conversation → behavior learn → meta review → profile update.

    Wires BehaviorLearner + MetaReviewer together with auto-scheduling."""

    def __init__(self, engine, interval_turns: int = 5):
        self._engine = engine
        self._learner = BehaviorLearner(engine, interval_turns)
        self._reviewer = MetaReviewer(engine)
        self._auto_thread: Optional[threading.Thread] = None
        self._running = True

    def on_turn(self) -> dict:
        """Called after each conversation turn. Returns {learned, reviewed}."""
        result = {"learned": False, "reviewed": False}

        # Step 1: Maybe trigger behavior learning
        learn_result = self._learner.maybe_learn()
        if learn_result:
            result["learned"] = True
            result["learn_detail"] = learn_result

            # Step 2: After learning, trigger meta review
            review_result = self._reviewer.review_now(learn_result)
            if review_result.get("reviewed"):
                result["reviewed"] = True
                result["review_detail"] = review_result

        return result

    def learn_and_review_now(self) -> dict:
        """Force immediate learn + review cycle."""
        learn_result = self._learner.learn_now()
        review_result = self._reviewer.review_now(learn_result)
        return {"learned": learn_result, "reviewed": review_result}

    def start_auto(self, interval_sec: float = 300.0):
        """Background thread: periodic learn+review every N seconds."""
        def _run():
            while self._running:
                time.sleep(interval_sec)
                if not self._running:
                    break
                try:
                    self.learn_and_review_now()
                except Exception:
                    pass
        self._auto_thread = threading.Thread(target=_run, daemon=True)
        self._auto_thread.start()
        logger.info("CognitiveLoop auto-scheduler started (every %ds)", interval_sec)

    def stop(self):
        self._running = False

    def stats(self) -> dict:
        return {
            "learner": {
                "turns": self._learner._turn_counter,
                "last_learn": self._learner._last_learn_at,
                "results": len(self._learner._results),
            },
            "reviewer": {
                "reviews": self._reviewer._review_count,
                "insights": len(self._reviewer._insights),
            },
            "auto": self._auto_thread is not None and self._auto_thread.is_alive(),
        }


def wire_cognitive_loop(engine, interval_turns: int = 5) -> CognitiveLoop:
    """Wire the cognitive closure loop into the engine."""
    loop = CognitiveLoop(engine, interval_turns)
    engine._cognitive_loop = loop

    # Wire into StateMachine: after each pipeline run, trigger on_turn
    original_on_event_sm = getattr(engine, 'on_event_sm', None)
    if original_on_event_sm:
        def on_event_sm_with_loop(event, *args, **kwargs):
            result = original_on_event_sm(event, *args, **kwargs)
            loop.on_turn()
            return result
        engine.on_event_sm = on_event_sm_with_loop

    # Wire into _publish: after each publish, increment turn counter
    original_publish = engine._publish
    def publish_with_loop(kind, payload=None):
        original_publish(kind, payload)
        loop.on_turn()
    engine._publish = publish_with_loop

    logger.info("CognitiveLoop wired: behavior-learn every %d turns, meta-review after",
                 interval_turns)
    return loop
