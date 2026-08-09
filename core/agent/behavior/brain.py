"""BehaviorBrain — behavior chain brain kernel.

Owns the behavior chain "brain": next-action prediction (BehaviorPredictor),
value ranking with full injection (P1-2: load_est + prof_matcher), the single
TrainingFeedbackLoop instance (C1: no dead duplicate), BehaviorRewarder, and
the cognitive profile feed.

ADR-013: prediction results are background priors only — they never
participate in the current turn's fusion decision. Learning happens
post-hoc (observed action vs previous prediction), and the next prediction is
produced in a background thread for the following turn.
"""

from __future__ import annotations

import asyncio
import math
import logging
import random
import threading
from typing import Any, Dict, Optional

from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.cold_start import ColdStartManager
from core.agent.behavior.scheduler import (
    BehaviorScheduler,
    ScheduleMode,
    ci_width_proxy,
    is_risk_action,
)
from core.agent.predictor.predictor import BehaviorPredictor
from core.agent.predictor.candidate_generator import CandidateGenerator
from core.agent.predictor.value_ranker import ValueRanker
from core.agent.predictor.cognitive_load import CognitiveLoadEstimator
from core.agent.predictor.cognitive_profile import (
    CognitiveProfile,
    EnhancedProfileMatcher,
    ProfileUpdater,
)
from core.agent.predictor.training_loop import TrainingFeedbackLoop
from core.agent.rewarder.rewarder import BehaviorRewarder
from core.agent.rewarder.correction_detector import CorrectionDetector
from core.agent.behavior.explicit_commitment import (
    CommitmentRegistry,
    recognize_declaration,
)
from core.agent.behavior.dpo_learner import DPOLearner, OBSERVABLE_ACTION_TYPES

logger = logging.getLogger(__name__)


def extract_action(event) -> tuple:
    """Mirror BehaviorGraphAdapter.record_event mapping: (summary, action_type)."""
    kind = getattr(event, "kind", "unknown") or "unknown"
    payload = getattr(event, "payload", None) or {}
    action_type = "dialog"
    if kind.startswith("ui."):
        action_type = "ui"
    elif kind.startswith("config."):
        action_type = "config"
    elif kind.startswith("api."):
        action_type = "api"
    elif kind.startswith("document."):
        action_type = "document"
    elif kind.startswith("tool."):
        action_type = "tool"
    summary = payload.get("text", payload.get("content", payload.get("action", kind)))
    return str(summary)[:200], action_type


class BehaviorBrain:
    """One kernel, multiple facades: runtime engine + CLI both drive this."""

    def __init__(self, graph: Optional[BehaviorGraph] = None,
                 llm_provider=None, profile: Optional[CognitiveProfile] = None,
                 commitments_store_path: Optional[str] = None):
        self.graph = graph or BehaviorGraph()
        self._llm_provider = llm_provider
        self.profile = profile or CognitiveProfile.create()
        self._candidate_gen = CandidateGenerator(llm_provider)
        load_est = CognitiveLoadEstimator()
        prof_matcher = EnhancedProfileMatcher(self.profile)
        # P1-2: load_est + prof_matcher injected so both dimensions are live.
        self._value_ranker = ValueRanker(
            self.graph, load_est=load_est, prof_matcher=prof_matcher,
        )
        self.predictor = BehaviorPredictor(
            self.graph, self._candidate_gen, self._value_ranker,
            prof_matcher, ColdStartManager(),
        )
        # C1: single TrainingFeedbackLoop instance, always graph-backed.
        self.training_loop = TrainingFeedbackLoop(graph=self.graph)
        self.rewarder = BehaviorRewarder(self.graph)
        self.correction_detector = CorrectionDetector()
        self.profile_updater = ProfileUpdater(self.profile)
        self._scheduler = BehaviorScheduler()
        # Explicit layer: user-declared + distilled commitments (P3).
        # 3.3: 显式承诺持久化挂载 — engine 传固定 store_path，
        # registry 已有 save/_load，on_checkpoint 统一落盘。
        self.commitments = CommitmentRegistry(store_path=commitments_store_path)
        # B6 (LLM_COLLABORATIVE §四): implicit feedback → preference pairs.
        self.dpo = DPOLearner(llm=llm_provider)

        self._pending_prediction = None
        self._predict_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._predict_count = 0
        self._learn_count = 0
        self._last_action_summary: Optional[str] = None
        self._last_error: Optional[str] = None
        self._stopped = False
        self._token_budget_remaining = float(self._scheduler._reg.get(
            "behavior.scheduler_token_budget", 2000.0,
        ))
        self._last_decision = None
        self._llm_calls = 0

    # ── Prediction (ADR-013: background prior only) ────────────────────────

    def _chain_summary(self, n: int = 6) -> str:
        steps = sorted(self.graph.nodes.values(), key=lambda s: s.timestamp)[-n:]
        return " -> ".join(s.action_summary for s in steps) if steps else ""

    def _current_step_id(self) -> Optional[str]:
        if not self.graph.nodes:
            return None
        latest = max(self.graph.nodes.values(), key=lambda s: s.timestamp)
        return latest.step_id

    async def predict_next(self):
        chain = self._chain_summary()
        sid = self._current_step_id()
        profile_dict = self.profile.to_dict()
        anchors = len(getattr(self.graph, "edges", {}))
        decision = self._scheduler.decide(
            token_budget_remaining=self._token_budget_remaining,
            risk_action=is_risk_action(chain),
            total_turns=self.profile.total_turns,
            ci_width=ci_width_proxy(self.graph),
            anchors=anchors,
        )
        self._last_decision = decision

        mode_hint = None
        if decision.mode == ScheduleMode.STATS:
            mode_hint = "stats"
        elif decision.mode == ScheduleMode.ASK:
            mode_hint = "ask"
        elif decision.mode == ScheduleMode.EXPLORE:
            # epsilon-greedy: with prob ε call LLM, else stats.
            mode_hint = "llm" if random.random() < decision.epsilon else "stats"
        elif decision.mode == ScheduleMode.LLM:
            mode_hint = "llm"

        result = await self.predictor.predict(
            chain, sid, profile_dict, mode_hint=mode_hint,
        )
        if mode_hint == "llm":
            self._llm_calls += 1
            self._token_budget_remaining = max(
                0.0, self._token_budget_remaining - 800.0,
            )
        with self._lock:
            self._pending_prediction = result
        self._predict_count += 1
        return result

    def predict_next_background(self) -> bool:
        """Kick off next-step prediction in a daemon thread (BC05 §9 Async)."""
        if self._stopped:
            return False
        if self._predict_thread is not None and self._predict_thread.is_alive():
            return False

        def _run():
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self.predict_next())
                finally:
                    loop.close()
            except Exception as e:  # pragma: no cover - defensive
                self._last_error = str(e)
                logger.debug("Behavior prediction failed: %s", e)

        self._predict_thread = threading.Thread(target=_run, daemon=True)
        self._predict_thread.start()
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop background prediction and join the worker (engine stop)."""
        self._stopped = True
        thread = self._predict_thread
        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except Exception:  # pragma: no cover - defensive
                pass

    # ── Learning (ADR-013: post-hoc, never same-turn) ──────────────────────

    def learn_from_event(self, event, pcr_zone: str = "") -> None:
        """Evaluate the previous prediction against this observed action.

        B7 (3.3): pcr_zone 是第二视角（PCR）输入 — 高压/精确域（ABYSS/PRECISION/
        CHAOS）下用户声明承诺的语义更重，置信度门槛从 0.7 降到 0.6；
        常规域保持 0.7（宁缺勿滥，防误加）。
        """
        summary, action_type = extract_action(event)
        text = ""
        if hasattr(event, "payload") and event.payload:
            text = event.payload.get("text", "")
        is_correction = False
        if text:
            prev = [self._last_action_summary] if self._last_action_summary else []
            sig = self.correction_detector.detect(text, prev, summary)
            is_correction = sig.is_correction

        pred = self._pending_prediction
        if pred is not None:
            self.training_loop.on_user_action(
                pred, summary, action_type, is_correction=is_correction,
            )
            self.rewarder.on_prediction_result(
                pred, summary, is_correction=is_correction,
            )
            self._learn_count += 1
            # B6: implicit feedback → preference pair (DPO pool).
            top1 = getattr(pred, "predicted_top1", "") or ""
            # 3.1a (STATE_SNAPSHOT §1.2): 仅对可观测行为事件记录偏好对。
            # dialog 类 = 用户文本，top1(图内动作摘要) == summary 恒 false →
            # 假 reject 池。ui/tool/api/config/document 才构成偏好信号。
            if action_type in OBSERVABLE_ACTION_TYPES and top1:
                if top1 == summary:
                    feedback = "accept"
                elif is_correction:
                    feedback = "correction"
                else:
                    feedback = "reject"
                self.dpo.record(top1, summary, feedback)
        elif summary and action_type in OBSERVABLE_ACTION_TYPES:
            # No prior prediction → 弱信号：不构成自对（record 内部丢弃
            # predicted==actual），留给蒸馏的只有真实信号。设计保留 ×0.3
            # 语义：此处显式不产生 (summary, summary) 偏好对（3.1b 修复）。
            pass
        self.profile_updater.record_action(
            action_type, summary, stability=0.2 if is_correction else 0.8,
        )
        self._last_action_summary = summary

        # P3 (B7): multi-perspective declaration recognition. Ambiguous
        # declarations are flagged for user confirmation, not auto-added.
        if text:
            decl = recognize_declaration(text)
            if decl is not None:
                when, should, confidence = decl
                zone_boost = pcr_zone in ("ABYSS", "PRECISION", "CHAOS")
                min_conf = 0.6 if zone_boost else 0.7
                if confidence >= min_conf and not self.commitments.match(text):
                    self.commitments.add(
                        when=when, should=should, source="user",
                        metadata={"pcr_zone": pcr_zone},
                    )

    def commitment_context(self, text: str, max_blocks: int = 3) -> list:
        """Hidden context blocks from explicit commitments (design: <=3/turn)."""
        return self.commitments.context_blocks(text, max_blocks=max_blocks)

    # ── Checkpoint / session end ───────────────────────────────────────────

    def on_checkpoint(self) -> None:
        """Session-level decay + rewarder close + profile session end."""
        self.rewarder.on_session_end()
        self.training_loop.on_session_end()
        # 3.3: 显式承诺持久化（有 store_path 才落盘）
        try:
            self.commitments.save()
        except Exception as e:
            logger.debug("Commitments save failed: %s", e)

        # B6: pool full → distill preference deltas → apply to graph (async).
        if self.dpo.ready():
            def _dpo_learn():
                try:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(self.dpo.learn(llm=self._llm_provider))
                    finally:
                        loop.close()
                    self.dpo.apply_to_graph(self.graph)
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("DPO learning failed: %s", e)

            threading.Thread(target=_dpo_learn, daemon=True).start()

        def _profile_end():
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        self.profile_updater.record_session_end(llm=self._llm_provider)
                    )
                finally:
                    loop.close()
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("Profile session end failed: %s", e)

        threading.Thread(target=_profile_end, daemon=True).start()

    # ── White-box (A19) ────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        pred = self._pending_prediction
        pred_info = None
        if pred is not None:
            pred_info = {
                "top1": pred.predicted_top1 or "",
                "mode": pred.query_mode or "",
                "candidates": len(pred.candidates),
                "latency_ms": getattr(pred, "latency_ms", 0.0),
                "ask_clarification": getattr(pred, "ask_clarification", False),
            }
        return {
            "graph": {
                "nodes": len(self.graph.nodes),
                "edges": len(self.graph.edges),
            },
            "pending_prediction": pred_info,
            "predict_count": self._predict_count,
            "learn_count": self._learn_count,
            "scheduler": (
                self._last_decision.to_dict() if self._last_decision else None
            ),
            "token_budget_remaining": round(self._token_budget_remaining, 1),
            "llm_calls": self._llm_calls,
            "commitments": self.commitments.stats(),
            "dpo": self.dpo.stats(),
            "training": self.training_loop.get_training_report(),
            "last_error": self._last_error,
        }
