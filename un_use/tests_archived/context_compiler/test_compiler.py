# Tests for ContextCompiler Phase 1
import pytest
from core.agent.context_compiler import (
    Domain, IntentCategory, IntentEstimate, ContextEntry, CrossRef, CrossDomainContextIR,
    DomainSelector, BudgetAllocator, ContextSerializer, CompilerMonitor,
)
from core.agent.context_compiler.models import DomainFeedback


class TestDomainSelector:
    def test_single_task_intent(self):
        ds = DomainSelector()
        r = ds.select([IntentEstimate(IntentCategory.TASK, 0.9)])
        assert r.primary_domain == Domain.ENGINEERING

    def test_single_discussion_intent(self):
        ds = DomainSelector()
        r = ds.select([IntentEstimate(IntentCategory.DISCUSSION, 0.9)])
        assert r.primary_domain == Domain.PROFILE

    def test_multi_intent_blend(self):
        ds = DomainSelector()
        r = ds.select([
            IntentEstimate(IntentCategory.TASK, 0.6),
            IntentEstimate(IntentCategory.CORRECTION, 0.4),
        ])
        assert r.weights[Domain.ENGINEERING] > 0.3
        assert r.weights[Domain.BEHAVIOR] > 0.1

    def test_weights_sum_to_one(self):
        ds = DomainSelector()
        r = ds.select([IntentEstimate(IntentCategory.CASUAL, 0.8)])
        assert abs(sum(r.weights.values()) - 1.0) < 0.001

    def test_adaptive_delta(self):
        ds = DomainSelector()
        ds.feed_missing_domain(DomainFeedback(
            turn_number=1, missing_domain=Domain.ENGINEERING,
            current_intent=IntentCategory.TASK, confidence=1.0,
        ))
        r = ds.select([IntentEstimate(IntentCategory.TASK, 0.9)])
        assert r.weights[Domain.ENGINEERING] > 0.60

    def test_detect_missing_domain(self):
        ds = DomainSelector()
        domain = ds.detect_missing_domain(
            "why is this module missing monitoring?",
            IntentCategory.TASK,
        )
        assert domain is not None
